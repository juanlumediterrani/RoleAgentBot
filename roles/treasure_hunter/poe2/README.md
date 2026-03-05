# Subrol POE2 - Buscador de Tesoros

Subrol especializado para buscar tesoros en Path of Exile 2.

## Funcionalidad

Este subrol permite:
- Monitorizar precios de items específicos en POE2
- Detectar oportunidades de compra/venta
- Configurar objetivos personalizados
- Cambiar entre ligas (Standard y Fate of the Vaal)

## Comandos

### Control del Subrol
- `!buscartesoros poe2` - Activa el subrol POE2
- `!nobuscartesoros poe2` - Desactiva el subrol POE2

### Gestión de Configuración
- `!poe2liga` - Muestra la liga actual
- `!poe2liga <liga>` - Establece la liga (Standard o Fate of the Vaal)
- `!poe2add "nombre item"` - Añade un item a los objetivos
- `!poe2del "nombre item"` - Elimina un item de los objetivos
- `!poe2list` - Muestra la configuración actual y objetivos

## Ejemplos de Uso

```
!buscartesoros poe2
!poe2liga Fate of the Vaal
!poe2add "Ancient Rib"
!poe2add "Fracturing Orb"
!poe2list
```

## Items Conocidos

El sistema tiene predefinidos los siguientes items:
- Ancient Rib (ID: 4379)
- Ancient Collarbone (ID: 4385)
- Ancient Jawbone (ID: 4373)
- Fracturing Orb (ID: 294)
- Igniferis (ID: 25)
- Idol of Uldurn (ID: 24)

## Análisis de Precios

El sistema analiza los precios históricos y envía alertas cuando:
- **COMPRA**: Precio actual ≤ mínimo histórico * 1.15
- **VENTA**: Precio actual ≥ máximo histórico * 0.85

## Estructura de Archivos

```
roles/buscador_tesoros/poe2/
├── __init__.py          # Definición del módulo
├── poe2_subrole.py      # Lógica principal del subrol
└── README.md           # Esta documentación
```

## Integración

El subrol se integra con:
- API de poe2scout para obtener datos de precios
- Sistema de roles principal del agente
- Base de datos SQLite para persistencia
- Bot de Discord para notificaciones
