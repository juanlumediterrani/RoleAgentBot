# Vigía de Noticias Multi-Feed y Multi-Categoría

## 📋 Overview

El Vigía de Noticias ha sido actualizado para soportar múltiples feeds RSS y categorías configurables, permitiendo a los usuarios suscribirse a tipos específicos de noticias según sus intereses.

## 🚀 Características Nuevas

### 📡 Feeds Configurables
- **Múltiples fuentes RSS** con diferentes categorías
- **Feeds por defecto** preconfigurados (CNBC, El País, Reuters, BBC)
- **Gestión dinámica** de feeds (agregar/activar/desactivar)
- **Prioridades** para ordenar feeds importantes primero

### 📂 Categorías Disponibles
- `economia` - Noticias financieras, bolsas, empresas
- `internacional` - Política internacional, conflictos, diplomacia  
- `tecnologia` - IA, gadgets, innovación, ciberseguridad
- `sociedad` - Clima, salud, educación, cultura
- `politica` - Gobiernos, elecciones, legislación

### 🎯 Suscripciones Granulares
- **Por categoría completa** - Todas las noticias de una categoría
- **Por feed específico** - Noticias de una fuente particular
- **Gestión individual** - Cada usuario controla sus suscripciones

## 🛠️ Comandos de Discord

### 👀 Ver Opciones
```
!vigia feeds          # Lista todos los feeds disponibles
!vigia categorias     # Muestra categorías con feeds activos
!vigia estado         # Tus suscripciones activas
```

### 📝 Gestión de Suscripciones
```
!vigia suscribir <categoría> [feed_id]     # Suscribirse a categoría o feed
!vigia cancelar <categoría> [feed_id]     # Cancelar suscripción
```

### ⚙️ Administración (solo admins)
```
!vigia agregar_feed <nombre> <url> <categoría> [país] [idioma]
```

## 💡 Ejemplos de Uso

### Ver feeds disponibles
```
!vigia feeds
```
*Resultado:*
```
📡 Feeds Disponibles
📂 Economía (2 feeds)
**CNBC Noticias** (1) 🇺🇸
Prioridad: 1 | Idioma: EN

**Bloomberg Markets** (2) 🇺🇸  
Prioridad: 2 | Idioma: EN

📂 Internacional (2 feeds)
**El País Internacional** (3) 🇪🇸
Prioridad: 1 | Idioma: ES

**Reuters World** (4) 🇺🇸
Prioridad: 2 | Idioma: EN
```

### Suscribirse a categoría completa
```
!vigia suscribir economia
```
*Resultado:* `✅ Te has suscrito a todas las noticias de 'economia'`

### Suscribirse a feed específico
```
!vigia suscribir tecnologia 4
```
*Resultado:* `✅ Te has suscrito al feed 4 de la categoría 'tecnologia'`

### Ver tus suscripciones
```
!vigia estado
```
*Resultado:*
```
📊 Tus Suscripciones - Juan
💰 Economía
Todos los feeds de esta categoría

💻 Tecnología  
Feeds específicos: 4
```

### Cancelar suscripción
```
!vigia cancelar economia
```
*Resultado:* `✅ Suscripción cancelada a la categoría 'economia'`

### Agregar nuevo feed (admin)
```
!vigia agregar_feed "TechCrunch" "https://techcrunch.com/feed/" "tecnologia" "US" "en"
```
*Resultado:* `✅ Feed 'TechCrunch' agregado a categoría 'tecnologia'`

## 🗄️ Estructura de Base de Datos

### Tablas Nuevas

#### `feeds_config`
- Almacena configuración de feeds RSS
- Campos: nombre, url, categoría, país, idioma, prioridad, palabras_clave

#### `suscripciones_categorias`  
- Gestiona suscripciones por categoría/feed específico
- Relaciona usuarios con categorías y feeds individuales

### Feeds por Defecto

1. **CNBC Noticias** (economia) - 🇺🇸 EN
2. **El País Internacional** (internacional) - 🇪🇸 ES  
3. **Reuters World** (internacional) - 🇺🇸 EN
4. **BBC Technology** (tecnologia) - 🇬🇧 EN

## 🔄 Flujo de Trabajo

1. **Inicialización**: El vigía crea tablas e inserta feeds por defecto
2. **Procesamiento**: Revisa cada feed activo según prioridad
3. **Filtrado**: Solo procesa noticias para usuarios suscritos
4. **Análisis**: Usa Cohere para detectar noticias críticas
5. **Notificación**: Envía alertas solo a suscriptores relevantes

## 🎛️ Configuración

### Variables de Entorno
- `COHERE_API_KEY` - Para análisis de noticias
- `DISCORD_TOKEN` - Token del bot de Discord

### Personalización
- Modificar `feeds_por_defecto` en `db_role_vigia.py` para agregar feeds iniciales
- Ajustar `ROL_VIGIA` para cambiar el comportamiento del análisis
- Configurar categorías adicionales según necesidades

## 📊 Monitoreo

### Estadísticas Disponibles
- Noticias leídas por feed
- Notificaciones enviadas por categoría  
- Suscriptores activos por tipo
- Última actividad del sistema

### Logs
- `vigia` - Operaciones principales del vigía
- `vigia_commands` - Ejecución de comandos
- `db_role_vigia` - Operaciones de base de datos

## 🚨 Detección de Noticias Críticas

El vigía detecta automáticamente noticias críticas cuando:
- ⚔️ Escala una guerra o conflicto armado
- 💥 Caída en bancarrota de país o gran empresa  
- 🆘 Crisis humanitaria grave
- 🌍 Evento con impacto global inminente

Las noticias no críticas son filtradas con `"basura umana"`.

## 🔄 Migración desde Versión Anterior

### Cambios Principales
- ✅ Feed único CNBC → Múltiples feeds configurables
- ✅ Suscripción global → Suscripciones por categoría
- ✅ Comandos de Discord para gestión
- ✅ Base de datos extendida con nuevas tablas

### Datos Preservados
- ✅ Noticias leídas históricas
- ✅ Notificaciones enviadas  
- ✅ Suscriptores existentes (convertidos a suscripción global)

## 🛠️ Solución de Problemas

### Feed no responde
- Verificar URL del feed con `!vigia feeds`
- Revisar logs para errores de conexión
- Probar feed manualmente en navegador

### No recibo noticias
- Verificar suscripciones con `!vigia estado`
- Confirmar que feeds estén activos
- Revisar si hay noticias críticas recientes

### Error en comandos
- Verificar sintaxis: `!vigia <comando> [args]`
- Confirmar permisos (algunos comandos requieren admin)
- Revisar logs del bot para errores detallados

---

**El Vigía de Noticias 2.0** - Más flexible, más personalizable, más inteligente 🦅
