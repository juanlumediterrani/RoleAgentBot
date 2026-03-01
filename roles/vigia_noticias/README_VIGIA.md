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

### � Comando de Ayuda Principal
```
!vigiaayuda    # Muestra ayuda completa de todos los comandos
```

### � Ver Opciones
```
!vigia feeds          # Lista todos los feeds disponibles
!vigia categorias     # Muestra categorías con feeds activos
!vigia estado         # Tus suscripciones activas
```

### 🎯 Nivel 1 - Suscripciones Especializadas (Simple)
```
!vigia suscribir <categoría> [feed_id]     # Suscribirse a feeds especializados
!vigia cancelar <categoría> [feed_id]     # Cancelar suscripción
```

### 🤖 Nivel 2 - Suscripciones Generales con IA (Inteligente)
```
!vigia general <categoría>              # Feeds generales con clasificación IA
!vigia mixto <categoría>                 # Especializado + General (máxima cobertura)
```

### 🔍 Nivel 3 - Suscripciones por Palabras Clave (Preciso)
```
!vigia palabras "palabra1,palabra2,palabra3"  # Suscribir a palabras clave
!vigia cancelar_palabras "palabras"           # Cancelar suscripción
!vigia estado_palabras                        # Ver palabras clave suscritas
```

### 📢 Gestión de Suscripciones de Canal (requiere permisos)
```
!vigiacanal suscribir <categoría> [feed_id]  # Suscribir canal actual
!vigiacanal cancelar <categoría> [feed_id]  # Cancelar suscripción de canal
!vigiacanal estado                           # Ver suscripciones del canal
!vigiacanal palabras "palabras"              # Suscribir canal a palabras clave
```

### ⚙️ Administración (solo admins)
```
!vigia agregar_feed <nombre> <url> <categoría> [país] [idioma] [tipo]
# Tipos: especializado, general, palabras_clave
```

## 💡 Ejemplos de Uso

### Obtener Ayuda Rápida
```
!vigiaayuda
```
*Resultado:* Muestra ayuda completa organizada por niveles

### Ver feeds disponibles
```
!vigia feeds
```
*Resultado:*
```
📡 Feeds Disponibles
📂 Economía (2 feeds)
**CNBC Noticias** (1) 🇺🇸 [ESPECIALIZADO]
**CNN World** (5) 🇺🇸 [GENERAL]

📂 Internacional (2 feeds)
**El País Internacional** (3) 🇪🇸 [ESPECIALIZADO]
**Reuters World** (4) 🇺🇸 [GENERAL]

📂 Tecnología (2 feeds)
**BBC Technology** (2) 🇬🇧 [ESPECIALIZADO]
**Crypto News Feed** (6) 🇺🇸 [PALABRAS CLAVE]
```

### Nivel 1 - Para Principiantes
```
!vigia suscribir economia
```
*Resultado:* `✅ Te has suscrito a todas las noticias de 'economia'`

### Nivel 2 - Para Usuarios Avanzados
```
!vigia general internacional
```
*Resultado:* `✅ Suscrito a feeds generales de 'internacional' con clasificación IA`

```
!vigia mixto tecnologia
```
*Resultado:* `✅ Suscrito a cobertura mixta de 'tecnologia' (especializado + general)`

### Nivel 3 - Para Usuarios Específicos
```
!vigia palabras "bitcoin,cryptocurrency,blockchain"
```
*Resultado:* `✅ Suscrito a palabras clave: 'bitcoin,cryptocurrency,blockchain'`

```
!vigia estado_palabras
```
*Resultado:*
```
🔍 Tus Palabras Clave - Juan
🔑 **bitcoin,cryptocurrency,blockchain**
📅 Suscrito: 2024-02-28
```

### Suscribir Canal a Categoría (requiere permisos)
```
!vigiacanal suscribir tecnologia
```
*Resultado:* `✅ Este canal ha sido suscrito a todas las noticias de 'tecnologia'`

### Suscribir Canal a Feed Específico
```
!vigiacanal suscribir internacional 4
```
*Resultado:* `✅ Este canal ha sido suscrito al feed 4 de la categoría 'internacional'`

### Ver suscripciones del canal
```
!vigiacanal estado
```
*Resultado:*
```
📊 Suscripciones del Canal - #noticias
💰 Economía
Todos los feeds de esta categoría

💻 Tecnología  
Feeds específicos: 2
```

### Cancelar suscripción
```
!vigia cancelar economia
```
*Resultado:* `✅ Suscripción cancelada a la categoría 'economia'`

### Cancelar suscripción de canal
```
!vigiacanal cancelar tecnologia
```
*Resultado:* `✅ Suscripción cancelada a la categoría 'tecnologia'`

### Agregar nuevo feed (admin)
```
!vigia agregar_feed "Reuters Tech" "https://reuters.com/tech/rss" "tecnologia" "US" "en" "general"
```
*Resultado:* `✅ Feed 'Reuters Tech' agregado a categoría 'tecnologia'`

## 🗄️ Estructura de Base de Datos

### Tablas Nuevas

#### `feeds_config`
- Almacena configuración de feeds RSS
- Campos: nombre, url, categoría, país, idioma, prioridad, palabras_clave, tipo_feed
- Tipos: especializado, general, palabras_clave

#### `suscripciones_categorias`  
- Gestiona suscripciones por categoría/feed específico
- Relaciona usuarios con categorías y feeds individuales

#### `suscripciones_canales`
- Gestiona suscripciones de canales completos
- Relaciona canales con categorías y feeds específicos
- Requiere permisos de "Gestionar Canales"

#### `suscripciones_palabras`
- Gestiona suscripciones por palabras clave específicas
- Soporta usuarios y canales
- Búsqueda exacta en títulos de noticias

### Feeds por Defecto

1. **CNBC Noticias** (economia) - 🇺🇸 EN [ESPECIALIZADO]
2. **El País Internacional** (internacional) - 🇪🇸 ES [ESPECIALIZADO]
3. **Reuters World** (internacional) - 🇺🇸 EN [GENERAL - IA]
4. **BBC Technology** (tecnologia) - 🇬🇧 EN [ESPECIALIZADO]
5. **CNN World** (general) - 🇺🇸 EN [GENERAL - IA]
6. **Crypto News Feed** (cripto) - 🇺🇸 EN [PALABRAS CLAVE]

## 🔄 Flujo de Trabajo Híbrido

1. **Inicialización**: El vigía crea tablas e inserta feeds por defecto
2. **Procesamiento**: Revisa cada feed según tipo y prioridad
3. **Filtrado Inteligente**:
   - **Feeds especializados**: Procesamiento directo
   - **Feeds generales**: Clasificación con IA antes de filtrar
   - **Feeds de palabras clave**: Búsqueda exacta en títulos
4. **Análisis**: Usa Cohere para detectar noticias críticas
5. **Notificación**: Envía alertas a usuarios (DM) y canales (público)

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
- ✅ Suscripción global → Suscripciones por categoría + canal
- ✅ Comandos de Discord para gestión
- ✅ Base de datos extendida con nuevas tablas
- ✅ Notificaciones a usuarios (DM) y canales (público)

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
- Verificar suscripciones con `!vigia estado` (personal) o `!vigiacanal estado` (canal)
- Confirmar que feeds estén activos con `!vigia feeds`
- Revisar si hay noticias críticas recientes
- Para canales, verificar permisos del bot en el canal

### Error en comandos
- Verificar sintaxis: `!vigia <comando> [args]` o `!vigiacanal <comando> [args]`
- Confirmar permisos (algunos comandos requieren admin/manage_channels)
- Revisar logs del bot para errores detallados

---

**El Vigía de Noticias 2.0** - Más flexible, más personalizable, más inteligente 🦅
