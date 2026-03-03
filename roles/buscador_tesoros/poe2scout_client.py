from dataclasses import dataclass
from typing import List, Any, Optional
import requests
from requests.adapters import HTTPAdapter, Retry
from datetime import datetime, timezone, timedelta
import logging

try:
    from agent_logging import get_logger
    logger = get_logger('poe2scout')
except Exception:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('poe2scout')


class APIError(Exception):
    pass


class ResponseFormatError(Exception):
    pass


@dataclass
class PriceEntry:
    price: float
    time: Optional[str]
    quantity: Optional[int]
    raw: Any


class Poe2ScoutClient:
    """Minimal, stricter client for poe2scout API.

    Usage:
        client = Poe2ScoutClient()
        history = client.get_item_history(item_id, league='Standard')
    """

    BASE = 'https://poe2scout.com/api'

    def __init__(self, session: Optional[requests.Session] = None, timeout: int = 10):
        if session is None:
            session = requests.Session()
            retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
            session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session = session
        self.timeout = timeout

    def _find_price_list(self, obj: Any) -> Optional[List[Any]]:
        """Recursively find a candidate list of price-like dicts inside a JSON object."""
        if isinstance(obj, dict):
            for key in ('price_history', 'history', 'prices', 'priceHistory', 'data', 'result', 'results', 'items', 'chart', 'series'):
                if key in obj and isinstance(obj[key], list):
                    return obj[key]
            for v in obj.values():
                res = self._find_price_list(v)
                if res:
                    return res
        elif isinstance(obj, list):
            # detect list of dicts with numeric-like keys
            if obj:
                first = obj[0]
                # list of dicts
                if isinstance(first, dict):
                    keys = set().union(*(set(x.keys()) for x in obj if isinstance(x, dict)))
                    if any(p in keys for p in ('price', 'value', 'p', 'amount')):
                        return obj
                    # accept if any dict contains a numeric value
                    for x in obj:
                        if isinstance(x, dict):
                            if any(isinstance(v, (int, float)) for v in x.values()):
                                return obj
                # list of [time, price] pairs
                if isinstance(first, list) and len(first) >= 2:
                    if isinstance(first[1], (int, float)) or (isinstance(first[1], str) and first[1].replace('.', '', 1).isdigit()):
                        return obj
            for el in obj:
                res = self._find_price_list(el)
                if res:
                    return res
        return None

    def _extract_price(self, entry: Any) -> Optional[float]:
        # list-like entry [time, price]
        if isinstance(entry, list) and len(entry) >= 2:
            try:
                return float(entry[1])
            except Exception:
                s = str(entry[1]).replace(',', '')
                try:
                    return float(s)
                except Exception:
                    return None

        if not isinstance(entry, dict):
            return None

        for key in ('price', 'value', 'p', 'amount'):
            if key in entry:
                try:
                    return float(entry[key])
                except Exception:
                    s = str(entry[key]).replace(',', '')
                    try:
                        return float(s)
                    except Exception:
                        return None

        # nested candidate
        data = entry.get('data') if isinstance(entry.get('data', None), dict) else None
        if data and 'price' in data:
            try:
                return float(data['price'])
            except Exception:
                return None

        # fallback: return first numeric value found in the dict
        for v in entry.values():
            if isinstance(v, (int, float)):
                try:
                    return float(v)
                except Exception:
                    continue
            if isinstance(v, str):
                s = v.replace(',', '')
                if s.replace('.', '', 1).isdigit():
                    try:
                        return float(s)
                    except Exception:
                        continue

        return None

    def get_item_history_old(self, item_id: int, league: str = 'Standard',
                         log_count: int = None, days: int = None,
                         reference_currency: str = 'divine') -> List[PriceEntry]:
        """Retrieve item price history from poe2scout API.

        Args:
            item_id: ID of the item to query
            league: League name (default: 'Standard')
            log_count: Number of price entries to retrieve (overrides days if both provided)
            days: Number of days of history to retrieve (assumes ~24 entries per day for complete data)
            reference_currency: Currency to express prices in ('divine' or 'exalted')

        The upstream API requires `logCount` to be a multiple of 4 (and >= 4).
        API response format (PriceLogEntry): {price: float, time: datetime, quantity: int}
        """
        if log_count is None:
            if days is not None:
                log_count = days * 24  # 24 entradas por día para datos completos
            else:
                log_count = 50

        def _round_up_to_4(n: int) -> int:
            if n < 4:
                return 4
            return n if n % 4 == 0 else n + (4 - (n % 4))

        url = f"{self.BASE}/items/{item_id}/history"
        adjusted_log_count = _round_up_to_4(log_count)
        if adjusted_log_count != log_count:
            logger.debug(f"Adjusting log_count {log_count} -> {adjusted_log_count} (multiple of 4)")

        # Añadir endTime con fecha actual para obtener los datos más recientes
        from datetime import datetime, timezone
        end_time = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        params = {
            'league': league,
            'logCount': adjusted_log_count,
            'referenceCurrency': reference_currency,
            'endTime': end_time,
        }


        attempted_retry = False
        try:
            r = self.session.get(url, params=params, timeout=self.timeout,
                                headers={'User-Agent': 'RoleAgentBot/1.0'})
        except Exception as e:
            logger.exception(f"Network error calling {url}: {e}")
            raise APIError(e)

        if r.status_code == 400 and isinstance(r.text, str) and 'logcount must be a multiple of 4' in r.text.lower() and not attempted_retry:
            attempted_retry = True
            params['logCount'] = _round_up_to_4(params['logCount'] + 4)
            logger.debug(f"Server rejected logCount; retrying with logCount={params['logCount']}")
            try:
                r = self.session.get(url, params=params, timeout=self.timeout,
                                    headers={'User-Agent': 'RoleAgentBot/1.0'})
            except Exception as e:
                logger.exception(f"Network error calling {url} on retry: {e}")
                raise APIError(e)

        if r.status_code != 200:
            logger.warning(f"Unexpected status {r.status_code} from {url} params={params}: {r.text[:200]}")
            raise APIError(f"Status {r.status_code}")

        try:
            payload = r.json()
        except Exception as e:
            logger.exception(f"Invalid JSON from {url}: {e}")
            raise ResponseFormatError("Invalid JSON")

        # API returns PriceLogEntry list: [{price, time, quantity}, ...]
        # First try known format from priceLogs key, then fallback to heuristic
        price_list = None
        if isinstance(payload, list):
            price_list = payload
        elif isinstance(payload, dict):
            for key in ('priceLogs', 'price_history', 'history', 'data'):
                if key in payload and isinstance(payload[key], list):
                    price_list = payload[key]
                    break
            if price_list is None:
                price_list = self._find_price_list(payload)

        if not price_list:
            preview = None
            try:
                preview = r.text if isinstance(r.text, str) else str(payload)
            except Exception:
                preview = repr(payload)
            preview = (preview[:800] + '...') if len(preview) > 800 else preview
            logger.debug(f"Payload preview for item {item_id}: {preview[:400]}")
            raise ResponseFormatError(f"No price history found for item {item_id} (preview={preview[:200]})")

        entries: List[PriceEntry] = []
        for entry in price_list:
            if entry is None:
                continue
            # Known PriceLogEntry format: {price, time, quantity}
            if isinstance(entry, dict) and 'price' in entry:
                try:
                    p = float(entry['price'])
                    t = entry.get('time')
                    q = entry.get('quantity')
                    
                    # Filtrar por últimos 30 días desde ahora (dinámico)
                    if t:
                        try:
                            entry_time = datetime.fromisoformat(t.replace('Z', '+00:00')).replace(tzinfo=None)
                            fecha_fin = datetime.now()
                            fecha_inicio = fecha_fin - timedelta(days=30)
                            if not (fecha_inicio <= entry_time <= fecha_fin):
                                continue  # Saltar entradas fuera del rango
                        except (ValueError, TypeError):
                            # Si no podemos parsear la fecha, incluimos la entrada
                            pass
                    
                    entries.append(PriceEntry(price=p, time=t,
                                             quantity=int(q) if q is not None else None,
                                             raw=entry))
                    continue
                except (ValueError, TypeError):
                    pass
            # Fallback to generic extraction
            p = self._extract_price(entry)
            if p is not None:
                t = entry.get('time') if isinstance(entry, dict) else None
                
                # Filtrar por últimos 30 días desde ahora (dinámico)
                if t:
                    try:
                        entry_time = datetime.fromisoformat(t.replace('Z', '+00:00')).replace(tzinfo=None)
                        fecha_fin = datetime.now()
                        fecha_inicio = fecha_fin - timedelta(days=30)
                        if not (fecha_inicio <= entry_time <= fecha_fin):
                            continue
                    except (ValueError, TypeError):
                        pass
                
                entries.append(PriceEntry(price=p, time=t, quantity=None, raw=entry))

        if not entries:
            raise ResponseFormatError("Found price list but no parsable price entries")

        return entries

    def get_item_history(self, item_name: str, league: str = None, days: int = 30) -> List[PriceEntry]:
        """Obtener historial de precios usando la API oficial de poe2scout.
        
        Args:
            item_name: Nombre del item a buscar
            league: Liga (si no se especifica, usa Standard)
            days: Días de historial (default: 30)
        """
        # Mapeo actualizado de nombres a IDs según la API
        item_ids = {
            'ancient rib': 4379,
            'ancient jawbone': 4373,
            'ancient collarbone': 4385,
            'preserved jawbone': 4371,
            'fracturing orb': 294,
        }
        
        item_name_lower = item_name.lower().strip()
        league = league or "Standard"
        
        # Buscar el ID del item
        item_id = None
        for name, id in item_ids.items():
            if item_name_lower == name.lower():
                item_id = id
                break
        
        if item_id:
            try:
                # Usar parámetros correctos según la API: 720 entradas, endTime actual, divine currency
                entries = self.get_item_history_old(
                    item_id, 
                    league=league, 
                    log_count=720,  # 24h * 30d = 720 entradas
                    reference_currency='divine'
                )
                logger.info(f"Historial obtenido para {item_name} (ID {item_id}): {len(entries)} entradas")
                return entries
            except Exception as e:
                logger.error(f"Error obteniendo historial para {item_name}: {e}")
                return []
        else:
            logger.warning(f"No se encontró ID para el item: {item_name}")
            return []

