# Guía de Implementación: Subrol Astrology (Sefer Yetzirah)

## Resumen del Sistema

Subrol de Shaman que implementa el sistema de adivinación del Sefer Yetzirah con 22 letras hebreas (3 Madres, 7 Dobles, 12 Simples). Lecturas deterministas basadas en cálculos de fecha/hora, con soporte multilingüe y almacenamiento NoSQL.

---

## FASE 1: Creación de Estructura de Archivos

### Paso 1.1: Crear Directorio del Subrol

```bash
cd /home/mtx/Documentos/RoleAgentBot/roles/shaman/subroles
mkdir -p astrology
cd astrology
```

### Paso 1.2: Crear __init__.py

```python
"""
Astrology Subrole - Sefer Yetzirah
Implementation of the 32 paths of wisdom through Hebrew letters.
"""

from .astrology import Astrology
from .astrology_db import AstrologyDB, get_astrology_db_instance
from .astrology_messages import (
    HEBREW_LETTERS, READING_TYPES, get_message, get_reading_type,
    load_personality_messages, get_guidance_messages, get_letter_translations,
    get_position_translation, clear_message_cache
)

__all__ = [
    'Astrology',
    'AstrologyDB',
    'get_astrology_db_instance',
    'HEBREW_LETTERS',
    'READING_TYPES',
    'get_message',
    'get_reading_type',
    'load_personality_messages',
    'get_guidance_messages',
    'get_letter_translations',
    'get_position_translation',
    'clear_message_cache'
]
```

### Paso 1.3: Crear astrology_messages.py

Contenido completo del archivo con:
- `ENGLISH_MESSAGES` (fallback en inglés)
- `READING_TYPES` (4 tipos de lectura)
- `HEBREW_LETTERS` (22 letras con datos en inglés)
- Funciones de carga: `_load_shaman_json`, `_load_astrologyplane_json`
- `load_personality_messages`, `get_message`, `get_guidance_messages`

### Paso 1.4: Crear astrology_db.py

Clase `AstrologyDB` usando `RoleConfigsNoSQL` con métodos:
- `save_birth_data`, `get_birth_data`
- `save_reading`, `get_user_readings`, `get_reading_stats`

### Paso 1.5: Crear astrology.py

Clase `Astrology` con lógica de cálculos:
- `get_reading` (entry point)
- `calculate_birth_chart`
- `calculate_moment_reading`
- `calculate_personal_year`
- `calculate_integrated_reading`
- `interpret_with_ai`

### Paso 1.6: Crear astrology_discord.py

Clase `AstrologyCommands` con comandos:
- `cmd_astrology` (dispatcher)
- `cmd_astrology_birth`, `cmd_astrology_moment`, `cmd_astrology_year`, `cmd_astrology_integrated`
- `cmd_astrology_save_birth`, `cmd_astrology_history`, `cmd_astrology_letters`

---

## FASE 2: Configuración NoSQL

### Paso 2.1: Actualizar validation/role_schemas.py

Agregar schemas:
```python
class AstrologyReading(BaseModel):
    """Schema for astrology reading history."""
    user_id: str
    reading_type: str
    calculation_data: Dict[str, Any]
    interpretation: str
    question: str = ""
    created_at: str

class AstrologyBirthData(BaseModel):
    """Schema for user birth data."""
    user_id: str
    birth_date: str
    birth_time: Optional[str] = None
    created_at: str
    updated_at: str
```

### Paso 2.2: Actualizar roles/role_configs_nosql.py

Agregar en `__init__`:
```python
self._astrology_birth_data = JsonStore(
    db_dir / "astrology_birth_data.json",
    default_factory=lambda: {},
    keep_backup=False,
)

self._astrology_readings = JsonlRingBuffer(
    db_dir / "astrology_readings.jsonl",
    max_lines=100,
    max_bytes=200 * 1024,
    keep_lines=80,
    schema=AstrologyReading if VALIDATION_AVAILABLE else None,
    validate_on_append=True,
)
```

Agregar métodos:
- `save_astrology_birth_data`
- `get_astrology_birth_data`
- `save_astrology_reading`
- `get_astrology_readings`
- `get_astrology_stats`

---

## FASE 3: Configuración de Traducciones

### Paso 3.1: Crear manuals/en-US/astrologyplane.json

Estructura:
```json
{
    "positions": {...},
    "translations": {
        "alef": {...},
        "mem": {...},
        ...
    },
    "guidance": {
        "love": {...},
        "career": {...},
        "health": {...},
        "path": {...},
        "general": {...}
    }
}
```

### Paso 3.2: Crear manuals/es-ES/astrologyplane.json

Traducciones en español de las 22 letras y guidance.

### Paso 3.3: Agregar sección astrology a personalities/{personality}/{language}/descriptions/shaman.json

```json
{
  "astrology": {
    "welcome": "...",
    "birth_title": "...",
    ...
    "labels": {
      "question": "...",
      "element": "...",
      ...
    }
  }
}
```

---

## FASE 4: Integración con Sistema Shaman

### Paso 4.1: Actualizar roles/shaman/shaman.py

Agregar imports y registrar comandos en `SHAMAN_COMMANDS`.

---

## FASE 5: Configuración de Prompts AI

### Paso 5.1: Actualizar personalities/{personality}/{language}/prompts.json

Agregar sección `roles.shaman.subroles.astrology` con golden_rules y interpretation_tasks.

---

## FASE 6: Verificación y Pruebas

### Paso 6.1: Verificar Importación

```bash
python3 -c "from roles.shaman.subroles.astrology import Astrology, AstrologyDB; print('Import successful')"
```

### Paso 6.2: Verificar NoSQL Schema

```bash
python3 -c "from validation.role_schemas import AstrologyReading, AstrologyBirthData; print('Schemas imported successfully')"
```

### Paso 6.3: Prueba de Cálculo

```python
from roles.shaman.subroles.astrology.astrology import Astrology
from datetime import datetime
astro = Astrology()
result = astro.calculate_birth_chart(datetime(1990, 5, 15))
print(result)
```

### Paso 6.4: Prueba de Comandos Discord

```
!astrology help
!astrology letters
!astrology save_birth 1990-05-15
!astrology birth
!astrology year
```

### Paso 6.5: Verificar Carga de Traducciones

```python
from roles.shaman.subroles.astrology.astrology_messages import load_personality_messages, get_message
messages = load_personality_messages()
print(messages.get('welcome'))
print(get_message('birth_title'))
```

---

## FASE 7: Integración Canvas UI (Opcional)

### Paso 7.1: Actualizar discord_bot/canvas/content.py

Agregar botones de navegación para astrology.

### Paso 7.2: Actualizar discord_bot/canvas/canvas_shaman.py

Agregar handlers para acciones de astrology.

---

## Checklist de Implementación

- [ ] Crear directorio `roles/shaman/subroles/astrology/`
- [ ] Crear `__init__.py`
- [ ] Crear `astrology_messages.py` con datos en inglés y loaders
- [ ] Crear `astrology_db.py` con NoSQL
- [ ] Crear `astrology.py` con lógica de cálculos
- [ ] Crear `astrology_discord.py` con comandos Discord
- [ ] Actualizar `validation/role_schemas.py` con schemas
- [ ] Actualizar `roles/role_configs_nosql.py` con stores y métodos
- [ ] Crear `manuals/en-US/astrologyplane.json`
- [ ] Crear `manuals/es-ES/astrologyplane.json`
- [ ] Actualizar `personalities/*/descriptions/shaman.json` con sección astrology
- [ ] Actualizar `roles/shaman/shaman.py` con comandos
- [ ] Actualizar `personalities/*/prompts.json` con prompts AI
- [ ] Verificar importación de módulos
- [ ] Probar cálculos básicos
- [ ] Probar comandos Discord
- [ ] Verificar carga de traducciones
- [ ] Probar guardar datos de nacimiento
- [ ] Probar historial de lecturas
- [ ] Integrar con Canvas UI (opcional)

---

## Notas Importantes

1. **Fallback**: Todos los mensajes en código están en inglés. Las traducciones se cargan desde `shaman.json` y `astrologyplane.json`.

2. **NoSQL**: Usa `JsonStore` para datos de nacimiento y `JsonlRingBuffer` para historial de lecturas (máx 100, mantiene 80).

3. **Determinista**: Las lecturas no son aleatorias como las runas; se basan en cálculos de fecha/hora.

4. **Datos Persistentes**: Requiere que los usuarios guarden su fecha de nacimiento para lecturas de tipo `birth` e `integrated`.

5. **Interpretación AI**: Usa el sistema de prompts.json similar a nordic_runes, con golden_rules específicas del Sefer Yetzirah.
