# RoleAgentBot - Sistema de Bot Discord Modular con Roles Autónomos

Un bot de Discord modular con sistema de roles autónomos programables, motor de IA integrado y persistencia de datos.

## 🚀 Características

- **Bot Discord Modular**: Sistema extensible con arquitectura basada en roles
- **Roles Autónomos**: Ejecución automática de tareas programadas en intervalos configurables
- **Motor de IA**: Integración con múltiples APIs (Google Gemini, Groq) para procesamiento de lenguaje natural
- **Personalidad Configurable**: Sistema de personalidad ajustable para el bot
- **Persistencia de Datos**: Base de datos SQLite para almacenar interacciones y contexto
- **Logging Completo**: Sistema de logging estructurado para depuración y monitoreo

## 📋 Requisitos

- Python 3.8+
- Cuenta de Bot de Discord
- API Keys para servicios de IA (Google Gemini y/o Groq)

## 🛠️ Instalación

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/tu-usuario/RoleAgentBot.git
   cd RoleAgentBot
   ```

2. **Crear entorno virtual**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # o
   venv\Scripts\activate  # Windows
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno**
   ```bash
   cp .env.example .env
   # Editar .env con tus API keys y configuración
   ```

5. **Configurar el bot**
   - Editar `agent_config.json` según tus necesidades
   - Configurar los roles automáticos deseados
   - Ajustar la personalidad del bot en `personality.json`

## ⚙️ Configuración

### Archivos de Configuración

- **`.env`**: Variables de entorno (API keys, tokens)
- **`agent_config.json`**: Configuración principal del bot y roles
- **`personality.json`**: Configuración de personalidad del bot

### Variables de Entorno (.env)

```env
DISCORD_TOKEN=tu_token_de_discord
GOOGLE_API_KEY=tu_api_key_de_google
GROQ_API_KEY=tu_api_key_de_groq
```

### Configuración de Roles (agent_config.json)

```json
{
  "platform": "discord",
  "roles": {
    "nombre_del_rol": {
      "script": "roles/nombre_del_rol.py",
      "interval_hours": 1,
      "enabled": true
    }
  }
}
```

## 🚀 Ejecución

```bash
python run.py
```

El bot iniciará automáticamente:
- El bot de Discord principal
- El planificador de roles automáticos
- Todos los roles configurados y habilitados

## 📁 Estructura del Proyecto

```
RoleAgentBot/
├── run.py                 # Punto de entrada principal
├── agent_discord.py       # Bot de Discord
├── agent_engine.py        # Motor de IA
├── agent_db.py           # Sistema de base de datos
├── agent_logging.py      # Sistema de logging
├── agent_config.json     # Configuración principal
├── personality.json      # Configuración de personalidad
├── roles/                # Directorio de roles automáticos
│   └── ejemplo_rol.py
├── databases/            # Base de datos SQLite
├── requirements.txt      # Dependencias Python
├── .env.example         # Plantilla de variables de entorno
└── README.md            # Este archivo
```

## 🤖 Creación de Roles

Los roles son scripts Python que se ejecutan automáticamente en intervalos configurados. Ejemplo:

```python
# roles/mi_rol.py
import asyncio
from datetime import datetime

async def main():
    print(f"[{datetime.now()}] Mi rol automático ejecutándose")
    # Tu lógica aquí

if __name__ == "__main__":
    asyncio.run(main())
```

## 🔧 Comandos del Bot

- **Menciones**: `@NombreDelBot tu mensaje` - Conversación con IA
- **DM**: Mensaje directo al bot para conversación privada
- **Prefijo**: Usa el prefijo configurado para comandos específicos

## 📊 Monitoreo y Logging

El sistema incluye logging completo:
- Logs del bot principal
- Logs de cada rol automático
- Logs del motor de IA
- Logs de la base de datos

Los logs se guardan automáticamente en archivos con rotación.

## 🗄️ Base de Datos

El sistema utiliza SQLite para persistencia:
- Almacenamiento de interacciones
- Contexto del bot
- Historial de conversaciones
- Datos de roles

La base de datos se crea automáticamente en `databases/agent.db`.

## 🤝 Contribuir

1. Fork el proyecto
2. Crear una rama (`git checkout -b feature/nueva-caracteristica`)
3. Commit tus cambios (`git commit -am 'Añadir nueva característica'`)
4. Push a la rama (`git push origin feature/nueva-caracteristica`)
5. Crear un Pull Request

## 📝 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo [LICENSE](LICENSE) para detalles.

## 🔗 Enlaces Útiles

- [Documentación de Discord.py](https://discordpy.readthedocs.io/)
- [Google Generative AI](https://ai.google.dev/)
- [Groq API](https://groq.com/)

## 🐛 Issues y Soporte

Si encuentras algún bug o necesitas ayuda:
1. Revisa los logs para identificar el problema
2. Abre un issue en GitHub con detalles del error
3. Incluye la configuración relevante (ocultando datos sensibles)

## 🔄 Actualizaciones

El bot soporta actualizaciones en caliente:
- Roles pueden ser añadidos/modificados sin reiniciar
- Configuración de personalidad ajustable
- Sistema de logging persistente

---

**Desarrollado con ❤️ para la comunidad**
# RoleAgentBot
