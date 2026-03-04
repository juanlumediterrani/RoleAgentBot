# Bases de Datos por Servidor

Este documento describe la implementación del esquema de bases de datos por servidor para RoleAgentBot.

## Esquema de Directorios

Las bases de datos ahora se organizan por servidor con la siguiente estructura:

```
databases/
├── nombredelservidor/
│   ├── putre.db              # Base de datos principal
│   ├── kronk.db              # Base de datos principal (nombre de personalidad)
│   ├── noticiasputre.db      # Base de datos del vigía de noticias
│   ├── PoE2FOTV.db          # Base de datos del buscador de tesoros (Fate of the Vaal)
│   ├── PoE2Standard.db      # Base de datos del buscador de tesoros (Standard)
│   ├── role_limosna.db      # Base de datos del rol de limosna
│   └── role_anillo.db       # Base de datos del rol del anillo
└── nombredeotroservidor/
    ├── putre.db
    ├── kronk.db
    └── ...
```

## Cambios Realizados

### 1. `agent_db.py` Actualizado

- `get_server_db_path(server_name, db_name)`: Genera rutas de BD para servidores
- `get_server_db_path_fallback(server_name, db_name)`: Versión con fallback para Docker
- `get_server_log_path(server_name, log_name)`: Genera rutas de logs por servidor
- `get_personality_name()`: Obtiene nombre de personalidad desde variable de entorno o configuración

### 2. `AgentDatabase` Modificado

- El constructor `AgentDatabase` ahora acepta `server_name`
- Función `get_db_instance(server_name)` para obtener instancias por servidor
- Diccionario `_db_instances` para mantener caché de instancias

### 3. Roles de Bases de Datos Actualizados

#### `roles/vigia_noticias/db_role_vigia.py`
- `get_vigia_db_instance(server_name)` para instancias por servidor
- Base de datos: `noticias_{personalidad}.db`

#### `roles/buscador_tesoros/db_role_poe.py`
- `get_poe_db_instance(server_name, liga)` para instancias por servidor y liga
- Base de datos: `PoE2FOTV.db` (Fate of the Vaal) o `PoE2Standard.db` (Standard)

#### `roles/trilero/subroles/limosna/db_limosna.py`
- `get_limosna_db_instance(server_name)` para instancias por servidor
- Base de datos: `role_limosna.db`

#### `roles/buscar_anillo/db_anillo.py`
- `get_anillo_db_instance(server_name)` para instancias por servidor
- Base de datos: `role_anillo.db`

### 4. `agent_discord.py` Actualizado

- Nuevas funciones auxiliares:
  - `get_server_name(guild)`: Sanitiza nombre de servidor
  - `get_db_for_server(guild)`: Obtiene BD principal para servidor
  - `get_vigia_db_for_server(guild)`: Obtiene BD del vigía para servidor

- Todas las operaciones de bases de datos ahora usan instancias por servidor
- Limpieza automática ahora itera sobre todos los servidores conectados

## Uso

### Para Desarrolladores

```python
# Obtener base de datos principal para un servidor
from agent_db import get_db_instance
db = get_db_instance("Mi Servidor")

# Obtener base de datos del vigía para un servidor
from roles.vigia_noticias.db_role_vigia import get_vigia_db_instance
db_vigia = get_vigia_db_instance("Mi Servidor")

# Obtener base de datos POE para servidor y liga
from roles.buscador_tesoros.db_role_poe import get_poe_db_instance
db_poe = get_poe_db_instance("Mi Servidor", "Standard")
```

### Para Administradores

1. **No se requiere configuración adicional** - el bot detecta automáticamente los servidores
2. **Cada servidor tiene sus propias bases de datos** - no hay interferencia entre servidores
3. **Migración automática** - las bases de datos existentes se mantienen para compatibilidad
4. **Backup** - cada directorio de servidor puede respaldarse independientemente

## Compatibilidad

- **Mantención de instancias globales**: `db`, `db_vigia`, etc. siguen funcionando para código existente
- **Rutas de fallback**: En entornos Docker o con permisos restringidos, usa `~/.roleagentbot/databases/`
- **Nombres sanitizados**: Los nombres de servidor se convierten automáticamente a formato válido para archivos

## Pruebas

Para probar la implementación:

```bash
python3 test_server_dbs.py
```

Este script verifica:
- Creación correcta de rutas por servidor
- Instanciación de todas las bases de datos
- Operaciones básicas de lectura/escritura
- Estructura de directorios esperada

## Beneficios

1. **Aislamiento completo**: Cada servidor tiene sus propios datos
2. **Escalabilidad**: Fácil añadir nuevos servidores sin configuración
3. **Mantenimiento**: Limpieza y backup por servidor
4. **Seguridad**: Datos separados por servidor
5. **Rendimiento**: Menor tamaño de bases de datos individuales

## Migración desde Versión Anterior

Las bases de datos existentes en `databases/` se mantienen para compatibilidad. Para migrar datos antiguos a un servidor específico:

1. Identificar el servidor destino
2. Copiar archivos `.db` al directorio correspondiente
3. Renombrar si es necesario para coincidir con el nuevo esquema

El sistema continuará funcionando con las bases de datos globales existentes mientras se completa la migración.
