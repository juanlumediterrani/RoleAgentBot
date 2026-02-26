# Contributing to RoleAgentBot

¡Gracias por tu interés en contribuir al RoleAgentBot! Este documento te guiará sobre cómo contribuir al proyecto.

## 🤝 Cómo Contribuir

### Reportar Issues

Si encuentras un bug o tienes una sugerencia:

1. **Busca issues existentes** antes de crear uno nuevo
2. **Usa plantillas claras** para bugs y features
3. **Incluye detalles específicos**:
   - Versión de Python
   - Sistema operativo
   - Pasos para reproducir el error
   - Logs relevantes (ocultando datos sensibles)

### Pull Requests

1. **Fork el repositorio**
2. **Crea una rama** para tu feature:
   ```bash
   git checkout -b feature/nueva-caracteristica
   ```
3. **Sigue las convenciones de código** del proyecto
4. **Añade tests** si aplica
5. **Actualiza la documentación** si es necesario
6. **Haz commit de tus cambios**:
   ```bash
   git commit -m "Añadir: nueva característica X"
   ```
7. **Push a tu fork**:
   ```bash
   git push origin feature/nueva-caracteristica
   ```
8. **Crea un Pull Request**

## 📝 Convenciones de Código

### Estilo de Código

- Usa **Python 3.8+**
- Sigue **PEP 8** para estilo
- Usa **type hints** cuando sea posible
- **Documenta funciones** con docstrings

### Mensajes de Commit

Usa el formato:
- `feat:` para nuevas características
- `fix:` para correcciones de bugs
- `docs:` para documentación
- `style:` para cambios de formato
- `refactor:` para refactorización
- `test:` para tests
- `chore:` para tareas de mantenimiento

Ejemplos:
```
feat: añadir nuevo rol de moderación automática
fix: corregir manejo de errores en API de Discord
docs: actualizar README con nueva configuración
```

### Estructura de Archivos

```
RoleAgentBot/
├── agent_*.py          # Módulos principales del bot
├── run.py              # Punto de entrada
├── roles/              # Roles automáticos
│   └── nombre_rol.py
├── personalities/      # Configuraciones de personalidad
├── databases/          # Base de datos (gitignored)
├── logs/              # Logs (gitignored)
└── tests/             # Tests unitarios
```

## 🧀 Creación de Roles

Los roles deben seguir esta estructura:

```python
#!/usr/bin/env python3
"""
Nombre del Rol - Descripción breve
"""

import asyncio
import logging
from datetime import datetime

# Configurar logging para el rol
logger = logging.getLogger(f"role.nombre_del_rol")

async def main():
    """
    Función principal del rol.
    Se ejecuta automáticamente según el intervalo configurado.
    """
    try:
        logger.info(f"[{datetime.now()}] Iniciando rol...")
        
        # Tu lógica aquí
        
        logger.info(f"[{datetime.now()}] Rol completado exitosamente")
    except Exception as e:
        logger.error(f"[{datetime.now()}] Error en rol: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Configuración de Roles

Añade tu rol a `agent_config.json`:

```json
{
  "roles": {
    "mi_rol": {
      "script": "roles/mi_rol.py",
      "interval_hours": 1,
      "enabled": true,
      "description": "Descripción de lo que hace el rol"
    }
  }
}
```

## 🧪 Testing

### Tests Unitarios

Crea tests para nuevas funcionalidades:

```python
import unittest
from agent_engine import pensar

class TestAgentEngine(unittest.TestCase):
    def test_pensar_basic(self):
        response = pensar("Hola")
        self.assertIsNotNone(response)
```

### Tests de Integración

Prueba la integración entre componentes:
- Bot Discord + Motor IA
- Roles automáticos + Base de datos
- Configuración + Ejecución

## 📖 Documentación

### Actualizar README

Si añades nuevas características:
1. Actualiza la sección de características
2. Añade instrucciones de configuración
3. Incluye ejemplos de uso

### Code Comments

Añade comentarios claros:
```python
def procesar_mensaje(mensaje):
    """
    Procesa un mensaje de Discord y genera respuesta.
    
    Args:
        mensaje (discord.Message): Mensaje recibido
        
    Returns:
        str: Respuesta generada por la IA
    """
    # Validar entrada
    if not mensaje.content:
        return ""
    
    # Procesar con IA
    return pensar(mensaje.content)
```

## 🔍 Review Process

### Qué revisaremos en tu PR:

1. **Funcionalidad**: ¿El código funciona como esperado?
2. **Estilo**: ¿Sigue las convenciones del proyecto?
3. **Tests**: ¿Tiene tests adecuados?
4. **Documentación**: ¿Está documentado correctamente?
5. **Seguridad**: ¿Expone datos sensibles?
6. **Performance**: ¿Impacta negativamente el rendimiento?

### Feedback Cycle

1. **Submit PR** → **Review inicial** (24-48h)
2. **Feedback** → **Correcciones** (según sea necesario)
3. **Aprobación** → **Merge** → **Release**

## 🚀 Áreas de Contribución

### Alta Prioridad

- [ ] Tests unitarios para módulos principales
- [ ] Mejoras en el sistema de logging
- [ ] Optimización de base de datos
- [ ] Soporte para más APIs de IA

### Media Prioridad

- [ ] Nuevos roles automáticos
- [ ] Mejoras en la documentación
- [ ] Interface web de configuración
- [ ] Sistema de plugins

### Baja Prioridad

- [ ] Soporte para Telegram
- [ ] Interface gráfica
- [ ] Sistema de estadísticas
- [ ] Integración con servicios externos

## 💡 Ideas para Contribuir

### Roles Automáticos

- **Moderador**: Detectar y manejar contenido inapropiado
- **Bienvenida**: Dar la bienvenida a nuevos miembros
- **Estadísticas**: Generar reportes del servidor
- **RSS**: Publicar noticias de feeds RSS
- **Backup**: Hacer backup de mensajes importantes

### Mejoras Técnicas

- **Caching**: Implementar caché para respuestas de IA
- **Rate Limiting**: Mejorar manejo de límites de API
- **Monitoring**: Sistema de métricas y alertas
- **Scaling**: Soporte para múltiples servidores

## 📞 Contacto

Si tienes dudas:

1. **Abre un issue** para preguntas técnicas
2. **Discusiones** para ideas y propuestas
3. **Discord** (si tenemos servidor)

## 📜 Licencia

Al contribuir, aceptas que tus contribuciones se licencien bajo la **MIT License**, misma que el proyecto principal.

---

¡Gracias por contribuir a RoleAgentBot! 🎉
