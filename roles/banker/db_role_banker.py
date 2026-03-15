import sqlite3
import threading
import os
import stat
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('db_role_banquero')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_banquero')

from agent_db import get_server_db_path_fallback, get_personality_name

def get_db_path(server_name: str = "default") -> Path:
    """Generate database path for banker with personality name."""
    personality_name = get_personality_name()
    db_name = f"banker_{personality_name}"
    return get_server_db_path_fallback(server_name, db_name)


class DatabaseRoleBanker:
    """Base de datos especializada para el Banquero.
    Gestiona wallets de oro, transactions y distribución diaria.
    """
    
    def __init__(self, server_name: str = "default", db_path: Path = None):
        if db_path is None:
            self.db_path = get_db_path(server_name)
        else:
            self.db_path = db_path
        self._lock = threading.RLock()
        self._ensure_writable_db()
        self._init_db()
    
    def _ensure_writable_db(self):
        """Verifica que la BD sea accesible y force permisos correctos."""
        try:
            # Asegurar que el directorio exista con permisos correctos
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._fix_permissions(self.db_path.parent)
            
            # Conectar y forzar permisos del archivo
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=WAL;')
            conn.close()
            
            # Forzar permisos del archivo de BD
            self._fix_permissions(self.db_path)
            
        except Exception as e:
            logger.error(f"Cannot access database at {self.db_path}: {e}")
            raise
    
    def _fix_permissions(self, path: Path):
        """Fuerza permisos de usuario/grupo actual en archivo/directorio."""
        try:
            if path.exists():
                # Obtener uid/gid actual
                uid = os.getuid()
                gid = os.getgid()
                
                # Cambiar owner
                os.chown(path, uid, gid)
                
                # Permisos: 664 para archivos, 775 para directorios
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
        """Inicializa la base de datos con todas las tablas necesarias."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                conn.commit()
                
                # Inicializar tablas
                self._init_wallets_table()
                self._init_transactions_table()
                self._init_config_table()
                
                logger.info(f"✅ Banker database ready at {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error initializing banker database: {e}")
    
    def _init_wallets_table(self):
        """Inicializa tabla de wallets de los usuarios."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS wallets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        user_name TEXT NOT NULL,
                        server_id TEXT NOT NULL,
                        server_name TEXT NOT NULL,
                        balance INTEGER DEFAULT 0,
                        created_date TEXT NOT NULL,
                        updated_date TEXT DEFAULT NULL,
                        UNIQUE(user_id, server_id)
                    )
                ''')

                cursor.execute("PRAGMA table_info(wallets)")
                columns = [row[1] for row in cursor.fetchall()]

                cursor.execute("PRAGMA index_list(wallets)")
                indexes = cursor.fetchall()
                has_unique_user_id_only = False
                for _seq, idx_name, is_unique, *_rest in indexes:
                    if not is_unique:
                        continue
                    cursor.execute(f"PRAGMA index_info({idx_name})")
                    idx_cols = [r[2] for r in cursor.fetchall()]
                    if idx_cols == ["user_id"]:
                        has_unique_user_id_only = True
                        break

                if "server_id" in columns and has_unique_user_id_only:
                    logger.info("🔄 Migrating wallets table: UNIQUE(user_id) -> UNIQUE(user_id, server_id)")

                    cursor.execute('''
                        CREATE TABLE wallets_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id TEXT NOT NULL,
                            user_name TEXT NOT NULL,
                            server_id TEXT NOT NULL,
                            server_name TEXT NOT NULL,
                            balance INTEGER DEFAULT 0,
                            created_date TEXT NOT NULL,
                            updated_date TEXT DEFAULT NULL,
                            UNIQUE(user_id, server_id)
                        )
                    ''')
                    cursor.execute('''
                        INSERT OR IGNORE INTO wallets_new
                        (id, user_id, user_name, server_id, server_name, balance, created_date, updated_date)
                        SELECT id, user_id, user_name, server_id, server_name, balance, created_date, updated_date
                        FROM wallets
                    ''')
                    cursor.execute('DROP TABLE wallets')
                    cursor.execute('ALTER TABLE wallets_new RENAME TO wallets')

                cursor.execute('CREATE INDEX IF NOT EXISTS idx_wallets_user ON wallets (user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_wallets_server ON wallets (server_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_wallets_user_server ON wallets (user_id, server_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla wallets: {e}")
    
    def _init_transactions_table(self):
        """Inicializa tabla de transactions."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        user_name TEXT NOT NULL,
                        server_id TEXT NOT NULL,
                        server_name TEXT NOT NULL,
                        type TEXT NOT NULL,
                        amount INTEGER NOT NULL,
                        balance_before INTEGER NOT NULL,
                        balance_after INTEGER NOT NULL,
                        description TEXT,
                        date TEXT NOT NULL,
                        admin_id TEXT DEFAULT NULL,
                        admin_name TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions (user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_server ON transactions (server_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions (type)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla transactions: {e}")
    
    def _init_config_table(self):
        """Inicializa tabla de configuración del banquero."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id TEXT NOT NULL UNIQUE,
                        daily_rate INTEGER DEFAULT 1,
                        opening_bonus INTEGER DEFAULT 10,
                        last_distribution TEXT DEFAULT NULL,
                        updated_date TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_config_servidor ON config (server_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla config: {e}")
    
    def create_wallet(self, user_id: str, user_name: str, 
                      server_id: str, server_name: str) -> tuple[bool, int]:
        """Create a new wallet for a user and apply opening bonus.
        
        Returns:
            tuple: (was_created, initial_balance)
        """
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Check if already exists
                    cursor.execute('''
                        SELECT balance FROM wallets 
                        WHERE user_id = ? AND server_id = ?
                    ''', (user_id, server_id))
                    existing = cursor.fetchone()
                    
                    if existing:
                        return False, existing[0]
                    
                    # Get opening bonus from server
                    cursor.execute('''
                        SELECT opening_bonus FROM config WHERE server_id = ?
                    ''', (server_id,))
                    bonus_result = cursor.fetchone()
                    opening_bonus = bonus_result[0] if bonus_result else 10
                    
                    # Insert new wallet with bonus
                    cursor.execute('''
                        INSERT INTO wallets 
                        (user_id, user_name, server_id, server_name, balance, created_date)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (user_id, user_name, server_id, server_name, 
                          opening_bonus, datetime.now().isoformat()))
                    
                    # Register opening bonus transaction
                    cursor.execute('''
                        INSERT INTO transactions 
                        (user_id, user_name, server_id, server_name, 
                         type, amount, balance_before, balance_after, description, date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (user_id, user_name, server_id, server_name,
                          "opening_bonus", opening_bonus, 0, opening_bonus,
                          f"Opening bonus for new account", datetime.now().isoformat()))
                    
                    conn.commit()
                    return True, opening_bonus
        except Exception as e:
            logger.exception(f"Error creando cartera: {e}")
            return False, 0
    
    def get_balance(self, user_id: str, server_id: str) -> int:
        """Get balance for a user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT balance FROM wallets WHERE user_id = ? AND server_id = ?', (user_id, server_id))
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.exception(f"Error getting balance: {e}")
            return 0
    
    def update_balance(self, user_id: str, user_name: str,
                        server_id: str, server_name: str,
                        amount: int, type: str, description: str = None,
                        admin_id: str = None, admin_name: str = None) -> bool:
        """Update user balance and register transaction."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Create wallet if it doesn't exist (with opening bonus)
                    was_created, existing_balance = self.create_wallet(user_id, user_name, server_id, server_name)
                    
                    # Get current balance (after possible creation)
                    cursor.execute('''SELECT balance FROM wallets WHERE user_id = ? AND server_id = ?''', 
                                 (user_id, server_id))
                    current_balance = cursor.fetchone()[0]
                    
                    # Calculate new balance
                    new_balance = current_balance + amount
                    
                    # Update balance
                    cursor.execute('''UPDATE wallets SET balance = ?, user_name = ? 
                                    WHERE user_id = ? AND server_id = ?''',
                                 (new_balance, user_name, user_id, server_id))
                    
                    # Register transaction
                    cursor.execute('''INSERT INTO transactions 
                                    (user_id, user_name, server_id, server_name, type, amount, balance_before, balance_after, 
                                    description, date, admin_id, admin_name)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                 (user_id, user_name, server_id, server_name, type, amount, current_balance, new_balance,
                                  description or f"{type} {amount}", datetime.now().isoformat(),
                                  admin_id, admin_name))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error updating balance: {e}")
            return False
    
    def configurar_tae(self, server_id: str, server_name: str, daily_rate: int, admin_id: str) -> bool:
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT opening_bonus, last_distribution FROM config WHERE server_id = ?', (server_id,))
                    current = cursor.fetchone()
                    opening_bonus = current[0] if current else 10
                    last_distribution = current[1] if current else None
                    cursor.execute('''
                        INSERT OR REPLACE INTO config
                        (server_id, daily_rate, opening_bonus, last_distribution, updated_date)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (server_id, daily_rate, opening_bonus, last_distribution, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error configuring TAE: {e}")
            return False

    def configurar_bono(self, server_id: str, server_name: str, opening_bonus: int, admin_id: str) -> bool:
        try:
            return self.establecer_opening_bonus(server_id, opening_bonus, admin_id, admin_id)
        except Exception as e:
            logger.exception(f"Error configuring opening bonus: {e}")
            return False

    def obtener_bono(self, server_id: str) -> int:
        return self.obtener_opening_bonus(server_id)

    def obtener_ultima_distribucion(self, server_id: str) -> str:
        return self.obtener_last_distribution(server_id)

    def establecer_opening_bonus(self, server_id: str, opening_bonus: int,
                                admin_id: str, admin_name: str) -> bool:
        """Establece el bono de apertura del servidor."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO config 
                        (server_id, opening_bonus, updated_date)
                        VALUES (?, ?, ?)
                    ''', (server_id, opening_bonus, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error estableciendo bono de apertura: {e}")
            return False
    
    def obtener_opening_bonus(self, server_id: str) -> int:
        """Obtiene el bono de apertura del servidor."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT opening_bonus FROM config WHERE server_id = ?
                ''', (server_id,))
                result = cursor.fetchone()
                return result[0] if result else 10
        except Exception as e:
            logger.exception(f"Error obteniendo bono de apertura: {e}")
            return 10
    
    def obtener_tae(self, server_id: str) -> int:
        """Obtiene la TAE diaria del servidor."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT daily_rate FROM config WHERE server_id = ?
                ''', (server_id,))
                result = cursor.fetchone()
                return result[0] if result else 1
        except Exception as e:
            logger.exception(f"Error obteniendo TAE: {e}")
            return 0
    
    def obtener_last_distribution(self, server_id: str) -> str:
        """Obtiene la date de la última distribución."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT last_distribution FROM config WHERE server_id = ?
                ''', (server_id,))
                result = cursor.fetchone()
                return result[0] if result and result[0] else None
        except Exception as e:
            logger.exception(f"Error obteniendo última distribución: {e}")
            return None
    
    def registrar_distribucion_diaria(self, server_id: str) -> bool:
        """Registra que se hizo una distribución diaria hoy."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE config 
                        SET last_distribution = ?
                        WHERE server_id = ?
                    ''', (datetime.now().isoformat(), server_id))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error registrando distribución diaria: {e}")
            return False
    
    def distribuir_daily_rate(self, server_id: str, server_name: str) -> dict:
        """Distribuye la TAE diaria a todos los usuarios del servidor."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Obtener TAE diaria
                    cursor.execute('''
                        SELECT daily_rate FROM config WHERE server_id = ?
                    ''', (server_id,))
                    result = cursor.fetchone()
                    daily_rate = result[0] if result else 0
                    
                    if daily_rate <= 0:
                        return {"success": False, "message": "No hay TAE configurada"}
                    
                    # Obtener todos los usuarios del servidor
                    cursor.execute('''
                        SELECT user_id, user_name, balance FROM wallets 
                        WHERE server_id = ?
                    ''', (server_id,))
                    usuarios = cursor.fetchall()
                    
                    if not usuarios:
                        return {"success": False, "message": "No hay usuarios con cartera"}
                    
                    # Distribuir a cada usuario
                    distribuciones = []
                    for user_id, user_name, balance_actual in usuarios:
                        nuevo_balance = balance_actual + daily_rate
                        
                        # Actualizar balance
                        cursor.execute('''
                            UPDATE wallets 
                            SET balance = ?, updated_date = ?
                            WHERE user_id = ? AND server_id = ?
                        ''', (nuevo_balance, datetime.now().isoformat(), user_id, server_id))
                        
                        # Registrar transacción
                        cursor.execute('''
                            INSERT INTO transactions 
                            (user_id, user_name, server_id, server_name, 
                             type, amount, balance_before, balance_after, description, date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (user_id, user_name, server_id, server_name,
                              "daily_rate", daily_rate, balance_actual, nuevo_balance,
                              f"Daily rate distribution", datetime.now().isoformat()))
                        
                        distribuciones.append({
                            "user_id": user_id,
                            "user_name": user_name,
                            "amount": daily_rate,
                            "balance_before": balance_actual,
                            "balance_after": nuevo_balance
                        })
                    
                    # Registrar distribución
                    cursor.execute('''
                        UPDATE config 
                        SET last_distribution = ?
                        WHERE server_id = ?
                    ''', (datetime.now().isoformat(), server_id))
                    
                    conn.commit()
                    
                    return {
                        "success": True,
                        "daily_rate": daily_rate,
                        "usuarios_distribuidos": len(distribuciones),
                        "distribuciones": distribuciones
                    }
        except Exception as e:
            logger.exception(f"Error distribuyendo TAE diaria: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}
    
    def get_transaction_history(self, user_id: str, server_id: str, limit: int = 10) -> list:
        """Get transaction history for a user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT type, amount, balance_before, balance_after, description, date,
                           admin_name
                    FROM transactions 
                    WHERE user_id = ? AND server_id = ?
                    ORDER BY date DESC
                    LIMIT ?
                ''', (user_id, server_id, limit))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting transaction history: {e}")
            return []
    
    def obtener_estadisticas(self, server_id: str = None) -> dict:
        """Obtiene estadísticas básicas del banquero."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                if server_id:
                    # Estadísticas de un servidor específico
                    cursor.execute("""
                        SELECT COUNT(*) as total_wallets,
                               COALESCE(SUM(balance), 0) as total_oro
                        FROM wallets
                        WHERE server_id = ?
                    """, (server_id,))
                    stats = cursor.fetchone()
                    
                    cursor.execute("""
                        SELECT COUNT(*) as total_transactions_hoy
                        FROM transactions
                        WHERE server_id = ? 
                        AND DATE(date) = DATE('now')
                    """, (server_id,))
                    transactions_hoy = cursor.fetchone()[0]
                    
                    return {
                        "total_wallets": stats[0],
                        "total_oro": stats[1],
                        "transactions_hoy": transactions_hoy
                    }
                else:
                    # Estadísticas globales
                    cursor.execute("SELECT COUNT(*) FROM wallets")
                    total_wallets = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COALESCE(SUM(balance), 0) FROM wallets")
                    total_oro = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM transactions")
                    total_transactions = cursor.fetchone()[0]
                    
                    return {
                        "total_wallets": total_wallets,
                        "total_oro": total_oro,
                        "total_transactions": total_transactions
                    }
        except Exception as e:
            logger.exception(f"Error obteniendo estadísticas: {e}")
            return {}
    
    def obtener_todas_wallets(self) -> list:
        """Obtiene todas las wallets de todos los servidores."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, user_name, server_id, server_name
                    FROM wallets
                    ORDER BY server_name, user_name
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo todas las wallets: {e}")
            return []


def get_banker_db_instance(server_name: str = "default") -> DatabaseRoleBanker:
    """Get banker database instance."""
    return DatabaseRoleBanker(server_name)
