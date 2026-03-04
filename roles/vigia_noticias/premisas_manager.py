"""
Gestor de premisas simple para el Vigía de Noticias.
Usa una lista estática que se puede modificar fácilmente.
"""

from agent_logging import get_logger

logger = get_logger('premisas_manager')

# Premisas clave configurables (se pueden modificar aquí)
PREMISAS_CLAVE = [
    "Estallido de una guerra o escalada nuclear",
    "Bancarota de un país o una gran corporación",
    "Catástrofe de magnitud global"
]

class PremisasManager:
    """Gestiona las premisas clave para el análisis de noticias con IA."""
    
    def __init__(self, server_name: str = "default"):
        self.server_name = server_name
    
    def obtener_premisas_activas(self) -> list:
        """Obtiene todas las premisas activas."""
        return PREMISAS_CLAVE
    
    def construir_prompt_premisas(self) -> str:
        """Construye el texto de premisas para inyectar en el prompt."""
        premisas = self.obtener_premisas_activas()
        if not premisas:
            return ""
        
        texto_premisas = "Una noticia es CRÍTICA solo si cumple ALGUNA de estas premisas:\n"
        for i, premisa in enumerate(premisas, 1):
            texto_premisas += f"{i}. {premisa}\n"
        
        return texto_premisas
    
    def añadir_premisa(self, texto: str) -> bool:
        """Añade una nueva premisa."""
        global PREMISAS_CLAVE
        if texto not in PREMISAS_CLAVE:
            PREMISAS_CLAVE.append(texto)
            logger.info(f"✅ Premisa añadida: {texto}")
            return True
        return False
    
    def quitar_premisa(self, texto: str) -> bool:
        """Quita una premisa."""
        global PREMISAS_CLAVE
        if texto in PREMISAS_CLAVE:
            PREMISAS_CLAVE.remove(texto)
            logger.info(f"✅ Premisa quitada: {texto}")
            return True
        return False


# Instancia global por servidor
_premisas_instances = {}

def get_premisas_manager(server_name: str = "default") -> PremisasManager:
    """Obtiene o crea una instancia del gestor de premisas."""
    if server_name not in _premisas_instances:
        _premisas_instances[server_name] = PremisasManager(server_name)
    return _premisas_instances[server_name]
