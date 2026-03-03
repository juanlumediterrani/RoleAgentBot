# 🎭 Rol Trilero - Maestro del Engaño

## 📋 Descripción

El rol **Trilero** es un rol especializado en estafas y engaños para conseguir recursos de los humanos. Actualmente incluye el subrol **pedir_oro** que solicita donaciones mediante trucos y manipulación.

## 🎯 Subroles Disponibles

### 1. **Pedir Oro** (`pedir_oro`)
- **Propósito**: Solicitar oro a los humanos mediante diversas excusas
- **Métodos**: Mensajes privados y públicos
- **Límites**: 
  - Máximo 2 mensajes privados por servidor al día
  - Máximo 4 mensajes públicos por servidor al día
  - No molestar al mismo usuario en 12 horas

## 🛠️ Comandos

### Comandos de Usuario
- `!trilero` - Suscribirse al rol trilero
- `!notrilero` - Desuscribirse del rol trilero
- `!trilerofrecuencia <horas>` - Configurar frecuencia (1-168 horas)

### Comandos de Administración
- `!activar trilero` - Activar el rol (solo admins)
- `!desactivar trilero` - Desactivar el rol (solo admins)

## 🎭 Mensajes Personalizados

Cada personalidad tiene sus propios mensajes para el rol trilero:

### Kronk
- **Activación**: "GRRR Kronk activar trilero! Orco listo para engañar umanos y robar oro!"
- **Suscripción**: "JUARJUAR Kronk suscrito a trilero! Kronk pedir oro con truquitos orkos!"

### Putre
- **Activación**: "🕐 Putre activar trilero! Orco listo para joder a umanos y robar su mierda de oro!"
- **Suscripción**: "GRRR Putre suscrito a trilero! Putre pedir oro con puterias orkas!"

## 📊 Estadísticas y Límites

El sistema mantiene registro de:
- Peticiones de oro por usuario
- Límites diarios por servidor
- Historial de interacciones
- Suscripciones activas

## 🔧 Configuración

### Variables de Entorno
```bash
TRILERO_ENABLED=true
```

### Configuración JSON
```json
{
  "roles": {
    "trilero": {
      "enabled": true,
      "interval_hours": 12,
      "script": "roles/trilero/trilero.py"
    }
  }
}
```

## 📁 Estructura de Archivos

```
roles/trilero/
├── trilero.py              # Archivo principal del rol
├── subroles/
│   └── pedir_oro/
│       ├── pedir_oro.py    # Lógica de pedir oro
│       └── db_oro.py       # Base de datos específica
└── README.md               # Esta documentación
```

## 🚀 Funcionamiento

1. **Inicio**: El rol se inicia según la frecuencia configurada
2. **Selección**: Elige entre mensaje privado o público aleatoriamente
3. **Ejecución**: Envía mensajes según los límites configurados
4. **Registro**: Guarda todas las interacciones en la base de datos

## 🛡️ Seguridad y Límites

- Protección contra spam (límites diarios)
- Respeto a la privacidad del usuario
- Limpieza automática de registros antiguos (30 días)
- Verificación de permisos de Discord

## 🔮 Futuras Expansiones

El rol trilero está diseñado para incluir más subroles:
- **Trucos de cartas** - Mini-juegos de apuestas
- **Estafas elaboradas** - Esquemas complejos
- **Robo de información** - Recolección sutil de datos

---

**🎭 ¡El Trilero está listo para sus trucos!**
