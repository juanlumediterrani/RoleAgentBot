import sqlite3
import threading
import os
import stat
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('db_role_treasure_hunter')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_treasure_hunter')

from agent_db import get_shared_data_path

def get_db_path(server_id: str = "default", liga: str = "Standard") -> Path:
    """Generate the database path based on the league name."""
    if liga.lower() == "fate of the vaal":
        db_name = "PoE2FOTV.db"
    elif liga.lower() == "standard":
        db_name = "PoE2Standard.db"
    else:
        liga_sanitized = liga.lower().replace(' ', '_').replace('-', '_')
        db_name = f"PoE2{liga_sanitized}.db"

    return get_shared_data_path(db_name, "shared_poe2")


class DatabaseRolePoe:
    """Specialized database for Treasure Hunter.
    Manages price history with retention of 720 entries (30 days).
    """
    
    def __init__(self, server_id: str = "default", liga: str = "Standard", db_path: Path = None):
        if db_path is None:
            self.db_path = get_db_path(server_id, liga)
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_writable_db()
        self._init_db()
    
    def _ensure_writable_db(self):
        """Ensure the database is accessible and enforce valid permissions."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._fix_permissions(self.db_path.parent)

            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=DELETE;')
            conn.close()

            self._fix_permissions(self.db_path)
            
        except Exception as e:
            logger.error(f"Cannot access database at {self.db_path}: {e}")
            raise
    
    def _fix_permissions(self, path: Path):
        """Enforce current user/group permissions on a file or directory."""
        try:
            if path.exists():
                uid = os.getuid()
                gid = os.getgid()
                os.chown(path, uid, gid)

                if path.is_file():
                    current_mode = path.stat().st_mode
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP
                    os.chmod(path, new_mode)
                elif path.is_dir():
                    current_mode = path.stat().st_mode  
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP | stat.S_IXUSR | stat.S_IXGRP
                    os.chmod(path, new_mode)
                    
                logger.debug(f"Fixed permissions for {path}: uid={uid}, gid={gid}")
        except Exception as e:
            logger.warning(f"Could not fix permissions for {path}: {e}")
    
    def _init_db(self):
        """Initialize the database with DELETE journal mode."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=DELETE;")
                conn.commit()

                self._init_notifications_table()

                logger.info(f"✅ Treasure Hunter database ready at {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error initializing Treasure Hunter database: {e}")
    
    def _sanitize_table_name(self, item_name: str) -> str:
        """Convert an item name into a valid SQL table name."""
        sanitized = item_name.lower()
        sanitized = sanitized.replace(' ', '_').replace('-', '_')
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c == '_')
        return f"precio_{sanitized}"
    
    def _ensure_table_exists(self, item_name: str, conn: sqlite3.Connection):
        """Create the item table if it does not exist."""
        table_name = self._sanitize_table_name(item_name)
        cursor = conn.cursor()
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                precio REAL NOT NULL,
                cantidad INTEGER DEFAULT NULL,
                liga TEXT NOT NULL,
                fecha TEXT NOT NULL
            )
        ''')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_fecha ON {table_name} (fecha)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_liga ON {table_name} (liga)')
        conn.commit()
    
    def insert_prices_bulk(self, item_name: str, entries: list, league: str):
        """Insert multiple price entries and keep at most 720 entries.
        Avoid duplicates by date and league.
        """
        inserted_count = 0
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    
                    # Format league
                    formatted_league = ''.join([word[0].upper() for word in league.split()])
                    
                    # Insert new entries while avoiding duplicates
                    for entry in entries:
                        if not entry.time:
                            continue
                            
                        # Parse and format date
                        try:
                            parsed_date = datetime.fromisoformat(entry.time.replace('Z', '+00:00')).replace(tzinfo=None)
                            formatted_date = parsed_date.strftime('%m-%d %H:%M')
                        except:
                            continue
                        
                        # Check for duplicates
                        cursor.execute(f'''
                            SELECT COUNT(*) FROM {table_name}
                            WHERE fecha = ? AND liga = ?
                        ''', (formatted_date, formatted_league))
                        if cursor.fetchone()[0] > 0:
                            continue
                        
                        # Insert row
                        cursor.execute(f'''
                            INSERT INTO {table_name} 
                            (precio, cantidad, liga, fecha)
                            VALUES (?, ?, ?, ?)
                        ''', (round(entry.price, 2),
                              entry.quantity if entry.quantity is not None else None,
                              formatted_league,
                              formatted_date))
                        inserted_count += 1
                    
                    # Keep at most 720 entries per item/league
                    cursor.execute(f'''
                        DELETE FROM {table_name}
                        WHERE liga = ? AND id NOT IN (
                            SELECT id FROM {table_name}
                            WHERE liga = ?
                            ORDER BY fecha DESC
                            LIMIT 720
                        )
                    ''', (formatted_league, formatted_league))
                    
                    removed_count = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"✅ {inserted_count} new, {removed_count} removed for {item_name} ({formatted_league})")
                    return inserted_count
        except Exception as e:
            logger.exception(f"⚠️ Error during bulk insert for {item_name}: {e}")
            return inserted_count
    
    def get_statistics(self, item_name: str, liga: str):
        """Get the minimum and maximum historical prices for an item."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    cursor.execute(f'''
                        SELECT MIN(precio), MAX(precio) 
                        FROM {table_name} 
                        WHERE liga = ?
                    ''', (liga_formateada,))
                    result = cursor.fetchone()
                    return result if result else (None, None)
        except Exception as e:
            logger.exception(f"⚠️ Error getting statistics for {item_name}: {e}")
            return (None, None)
    
    def get_price_history(self, item_name: str, liga: str):
        """Get all historical prices ordered by date for zone analysis."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    cursor.execute(f'''
                        SELECT precio, fecha
                        FROM {table_name}
                        WHERE liga = ?
                        ORDER BY fecha DESC
                    ''', (liga_formateada,))
                    return cursor.fetchall()
        except Exception as e:
            logger.exception(f"⚠️ Error getting history for {item_name}: {e}")
            return []
    
    def get_count(self, item_name: str, liga: str):
        """Get the number of entries for an item."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    cursor.execute(f'SELECT COUNT(*) FROM {table_name} WHERE liga = ?', (liga_formateada,))
                    return cursor.fetchone()[0]
        except Exception as e:
            logger.exception(f"⚠️ Error getting count for {item_name}: {e}")
            return 0
    
    def get_current_price(self, item_name: str, league: str):
        """Get the most recent price for an item."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    formatted_league = ''.join([word[0].upper() for word in league.split()])
                    cursor.execute(f'''
                        SELECT precio 
                        FROM {table_name}
                        WHERE liga = ?
                        ORDER BY fecha DESC
                        LIMIT 1
                    ''', (formatted_league,))
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logger.exception(f"⚠️ Error getting current price for {item_name}: {e}")
            return None
    
    def get_latest_date(self, item_name: str, league: str):
        """Get the date of the latest entry for an item."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    formatted_league = ''.join([word[0].upper() for word in league.split()])
                    cursor.execute(f'''
                        SELECT MAX(fecha) 
                        FROM {table_name} 
                        WHERE liga = ?
                    ''', (formatted_league,))
                    result = cursor.fetchone()
                    return result[0] if result and result[0] else None
        except Exception as e:
            logger.exception(f"⚠️ Error getting latest date for {item_name}: {e}")
            return None
    
    def has_stale_data(self, item_name: str, league: str, hours: int = 24):
        """Check whether the data is older than N hours."""
        try:
            latest_date_str = self.get_latest_date(item_name, league)
            if not latest_date_str:
                return True
            
            # Convert formatted date (MM-DD HH:mm) to datetime
            try:
                # Assume the current year for the formatted date
                current_year = datetime.now().year
                full_date = f"{current_year}-{latest_date_str}"
                latest_date = datetime.strptime(full_date, '%Y-%m-%d %H:%M')
                
                # If the date is in the future, assume the previous year
                if latest_date > datetime.now():
                    previous_year = current_year - 1
                    full_date = f"{previous_year}-{latest_date_str}"
                    latest_date = datetime.strptime(full_date, '%Y-%m-%d %H:%M')
            except ValueError:
                return True
            
            cutoff_date = datetime.now() - timedelta(hours=hours)
            return latest_date < cutoff_date
        except Exception as e:
            logger.exception(f"⚠️ Error checking stale data for {item_name}: {e}")
            return True
    
    def _init_notifications_table(self):
        """Initialize the notifications table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS notificaciones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_name TEXT NOT NULL,
                        liga TEXT NOT NULL,
                        tipo_señal TEXT NOT NULL,  -- 'COMPRA' or 'VENTA'
                        precio REAL NOT NULL,
                        fecha_envio TEXT NOT NULL  -- timestamp ISO
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notificaciones_item_fecha ON notificaciones (item_name, liga, fecha_envio)')
                conn.commit()
                logger.info("✅ Notifications table initialized")
        except Exception as e:
            logger.exception(f"❌ Error initializing notifications table: {e}")
    
    def register_notification(self, item_name: str, league: str, signal_type: str, price: float):
        """Register a sent notification."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    formatted_league = ''.join([word[0].upper() for word in league.split()])
                    send_date = datetime.now().isoformat()
                    
                    cursor.execute('''
                        INSERT INTO notificaciones (item_name, liga, tipo_señal, precio, fecha_envio)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (item_name, formatted_league, signal_type, price, send_date))
                    conn.commit()
                    logger.info(f"✅ Notification registered: {item_name} - {signal_type} at {price}")
        except Exception as e:
            logger.exception(f"⚠️ Error registering notification: {e}")
    
    def has_recent_similar_notification(self, item_name: str, league: str, signal_type: str, current_price: float, hours: int = 6, similarity_threshold: float = 0.15):
        """Check if there was a similar notification in the last N hours.
        
        Args:
            item_name: Item name
            league: Current league
            signal_type: Signal type ('COMPRA' or 'VENTA')
            current_price: Current price
            hours: Time window in hours (default: 6)
            similarity_threshold: Price similarity threshold (default: 15% = 0.15)
        
        Returns:
            bool: True if there's a recent similar notification, False if not
        """
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    formatted_league = ''.join([word[0].upper() for word in league.split()])
                    
                    # Calculate deadline
                    deadline = datetime.now() - timedelta(hours=hours)
                    deadline_iso = deadline.isoformat()
                    
                    # Search for recent notifications of same item and type
                    cursor.execute('''
                        SELECT precio, fecha_envio
                        FROM notificaciones
                        WHERE item_name = ? AND liga = ? AND tipo_señal = ? AND fecha_envio > ?
                        ORDER BY fecha_envio DESC
                    ''', (item_name, formatted_league, signal_type, deadline_iso))
                    
                    notifications = cursor.fetchall()
                    
                    for previous_price, send_date in notifications:
                        # Calculate percentage difference
                        if previous_price > 0:
                            difference = abs(current_price - previous_price) / previous_price
                            if difference <= similarity_threshold:
                                logger.info(f"🚫 Similar notification found: {item_name} - {signal_type} at {previous_price} ({(datetime.now() - datetime.fromisoformat(send_date)).total_seconds() / 3600:.1f}h ago)")
                                return True
                    
                    return False
        except Exception as e:
            logger.exception(f"⚠️ Error checking recent notification: {e}")
            return False


# Dictionary to maintain instances per server and league
_db_poe_instances = {}

def get_poe_db_instance(server_id: str = "default", liga: str = "Standard") -> DatabaseRolePoe:
    """Get or create a POE database instance for a specific server and league."""
    # Generate the current database path for this server and league
    current_db_path = get_db_path(server_id, liga)
    cache_key = f"{server_id}:{liga}:{current_db_path}"
    
    # Check if we have a cached instance with the same database path
    if cache_key not in _db_poe_instances:
        _db_poe_instances[cache_key] = DatabaseRolePoe(server_id, liga)
    
    return _db_poe_instances[cache_key]

def invalidate_poe_db_instance(server_id: str = None):
    """Invalidate cached POE database instance for a server or all servers."""
    global _db_poe_instances
    if server_id:
        # Invalidate all instances for this server (any league)
        keys_to_remove = [k for k in _db_poe_instances.keys() if k.startswith(f"{server_id}:")]
        for key in keys_to_remove:
            del _db_poe_instances[key]
            logger.info(f"🗄️ [POE] Invalidated cached db instance for server: {server_id}")
    else:
        # Invalidate all instances
        _db_poe_instances.clear()
        logger.info("🗄️ [POE] Invalidated all cached db instances")
