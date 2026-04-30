# Flujo de Lectura Astrology: Usuario ↔ LLM

## Visión General

Este documento describe el flujo completo de una lectura de astrology del Sefer Yetzirah, desde la solicitud del usuario hasta la respuesta interpretada por la LLM.

---

## Flujo de Lectura Integrada (Ejemplo Completo)

### FASE 1: Solicitud del Usuario

```
Usuario → Discord Bot → Canvas UI
```

**1. Usuario interactúa con Canvas UI:**
- Selecciona rol "Shaman"
- Selecciona subrol "Astrology"
- Selecciona tipo de lectura: "Integrated Reading", "Birth Chart", "Moment Reading", o "Personal Year"

**Datos requeridos según tipo de lectura:**

| Tipo de Lectura | Datos Requeridos | ¿Requiere Pregunta? | Caso de Uso |
|-----------------|------------------|---------------------|-------------|
| **Birth Chart** (Mazal HaLeida) | Fecha nacimiento, hora (opcional) | **NO** | Conocer naturaleza del alma permanente |
| **Personal Year** (Shanah Peratit) | Año nacimiento, año en curso | **NO** | Analizar ciclo anual, transiciones |
| **Moment Reading** (Sha'at HaShe'ela) | Fecha/hora del momento | **SÍ** | Decisión específica, situación presente |
| **Integrated Reading** | Datos natal + datos momento + año personal | **SÍ** | Consultas complejas, acompañamiento profundo |

**Ejemplo para Integrated Reading:**
- Fecha de nacimiento: `1990-05-15`
- Hora de nacimiento: `14:30` (opcional)
- Fecha de consulta: `2026-04-30`
- Hora de consulta: `12:00` (opcional)
- Pregunta: "¿Debo aceptar este nuevo trabajo?"

**2. Canvas UI procesa la solicitud:**
- Valida formato de fechas
- Para lecturas que requieren datos de nacimiento, verifica que el usuario tenga datos guardados (o pide guardarlos)
- Para lecturas que requieren pregunta, solicita la pregunta al usuario
- Envía datos al handler de astrology

---

### FASE 2: Cálculo de Datos (Sin IA)

```
Canvas Handler → Astrology.get_reading() → Métodos de cálculo
```

**3. `get_reading()` recibe la solicitud:**
```python
reading_type = 'integrated'
input_data = {
    'birth_date': datetime(1990, 5, 15),
    'birth_time': time(14, 30),
    'question_date': datetime(2026, 4, 30),
    'question_time': time(12, 0)
}
question = "¿Debo aceptar este nuevo trabajo?"
server_id = "691750774883221567"
```

**4. Cálculo de CAPA 1 - Carta Natal:**
```python
birth_chart = self.calculate_birth_chart(birth_date, birth_time)
```

**Paso 1: Elemento del alma (Letra Madre)**
- Estación de nacimiento: Primavera (mayo está en primavera)
- Elemento: Aire
- Letra: Alef (א)
- Interpretación: "Alma mediadora, equilibradora, intelectual en sentido amplio"

**Nota:** El elemento se determina por la ESTACIÓN (primavera/otoño=Aire, verano=Fuego, invierno=Agua), no por el mes específico.

**Paso 2: Planeta rector (Letra Doble)**
- Día de semana de nacimiento: Martes (weekday=1)
- Planeta: Marte (Mars)
- Letra: Dalet (ד)
- Dualidad: Fertilidad / Desolación
- Puerta sensorial: Oído derecho

**Nota:** El planeta rector se determina PRIMARIAMENTE por el día de semana del nacimiento (Sábado=Saturno, Jueves=Júpiter, Martes=Marte, Domingo=Sol, Viernes=Venus, Miércoles=Mercurio, Lunes=Luna). La hora natal puede refinarse pero no es obligatoria.

**Paso 3: Signo zodiacal (Letra Simple)**
- Fecha: 15 de mayo
- Signo: Tauro (Taurus)
- Letra: Vav (ו)
- Facultad: Pensamiento
- Órgano: Pie izquierdo

**Resultado CAPA 1:**

```python
{
    'element': {'letter': alef, 'season': 'Primavera', 'element': 'Aire'},
    'planet': {'letter': dalet, 'planet': 'Mars', 'day_of_week': 'Martes'},
    'sign': {'letter': vav, 'sign': 'Taurus', 'faculty': 'Pensamiento'}
}
```

**Paso 4 - Síntesis de la carta natal (4 preguntas del intérprete):**

Una vez obtenidas las tres capas, el intérprete compone la lectura respondiendo estas cuatro preguntas:

1. ¿El elemento y el signo se refuerzan o se tensionan? (p. ej., Fuego + Aries es coherente; Agua + Leo crea tensión creativa.)
2. ¿El planeta rector opera en su cara suave o dura según las circunstancias de vida de la persona?
3. ¿La facultad del signo está activa y sana, o bloqueada? (Observar el órgano correspondiente como indicador.)
4. ¿Dónde está el tikún? La corrección suele encontrarse en la dualidad planetaria que más se resiste.

**5. Cálculo de CAPA 2 - Año Personal:**
```python
personal_year = self.calculate_personal_year(birth_year=1990, current_year=2026)
```

**Paso 1: Año de nacimiento**
- 1990 → 1+9+9+0 = 19 → 1+9 = 10 → 1+0 = **1**

**Paso 2: Año en curso**
- 2026 → 2+0+2+6 = 10 → 1+0 = **1**

**Paso 3: Número personal**
- 1 + 1 = **2**

**Paso 4: Letra correspondiente**
- Número 2 → Bet (ב) / Saturno
- Año colectivo: 1 → Alef (א) / Aire

**Resultado CAPA 2:**

```python
{
    'personal_number': 2,
    'personal_letter': bet,
    'collective_year': 1,
    'collective_letter': alef
}
```

**Paso 2 - Cruzar el año personal con el año colectivo:**

El año colectivo (el número del año en curso reducido, sin el personal) establece el clima planetario general. La lectura del año personal siempre opera dentro de ese clima colectivo.

**Ejemplo:**
- Año colectivo 2026: 2+0+2+6 = 10 → 1+0 = 1 (Alef / Aire)
- El clima global del año está marcado por Aire: mediación, equilibrio, intelecto amplio
- Todos los años personales de 2026 se filtran a través de esta energía colectiva

**6. Cálculo de CAPA 3 - Momento de Consulta:**
```python
moment_reading = self.calculate_moment_reading(question_date, question_time)
```

**Paso 1: Entorno elemental**
- Estación del momento: Primavera (abril está en primavera)
- Elemento: Aire
- Letra: Alef (א)
- Tono: "equilibrio inestable, puede inclinarse en cualquier dirección"

**Nota:** Igual que en la carta natal, el elemento se determina por la ESTACIÓN del momento de consulta.

**Paso 2: Planeta del día**
- Día de semana de la consulta: Jueves (weekday=3)
- Planeta: Júpiter (Jupiter)
- Letra: Gimel (ג)
- Naturaleza: "Asuntos de expansión, justicia, abundancia"
- Dualidad activa: ¿El consultante opera desde la cara luminosa (expansión, justicia) o la desafiante (exceso, imprudencia)?

**Paso 3: Signo del mes**
- Fecha: 30 de abril
- Signo: Tauro (Taurus)
- Letra: Vav (ו)
- Facultad: Pensamiento

**Paso 4: Análisis de tensión entre los tres niveles**
- Elemento: Aire, Planeta: Júpiter, Signo: Tauro
- Alineación elemento-signo: Tauro es Tierra, Aire ≠ Tierra → desalineado
- Afinidad planeta-signo: Júpiter rige Piscis, no Tauro → sin afinidad
- Nivel de tensión: "medium"
- Interpretación: "Tensión creativa entre elemento y signo"

**Pregunta clave:** ¿Los tres niveles (elemento, planeta, signo) están ALINEADOS o en TENSIÓN?
- **Alineación:** Las fuerzas apuntan en la misma dirección; la situación tiene inercia clara
- **Tensión:** Hay contradicción entre niveles; señala un punto de elección real donde el libre albedrío es operativo

**Resultado CAPA 3:**

```python
{
    'element': {'letter': alef, 'tone': 'equilibrio inestable'},
    'planet': {'letter': gimel, 'planet': 'Jupiter'},
    'sign': {'letter': vav, 'faculty': 'Pensamiento'},
    'synthesis': {'tension_level': 'medium'}
}
```

**Paso 5 - Síntesis de la lectura del momento:**

La pregunta clave es si los tres niveles (elemento, planeta, signo) están ALINEADOS o en TENSIÓN:

- **Alineación:** Las fuerzas apuntan en la misma dirección. La situación tiene inercia clara; la respuesta está implícita en el movimiento natural de las cosas.
- **Tensión:** Hay contradicción entre los niveles. Esto señala un nudo, un punto de elección real donde el libre albedrío es operativo. La lectura debe identificar qué nivel ceder y cuál sostener.

**La dualidad del planeta es la pregunta central:** ¿el consultante está operando desde la cara positiva o desde la desafiante de ese planeta? ¿Hacia cuál se dirige?

**7. Cálculo de SÍNTESIS INTEGRADA:**
```python
synthesis = self._analyze_integrated_synthesis(birth_chart, personal_year, moment_reading)
```

**Las cinco preguntas del intérprete (según el guía):**

**1. ¿Cuál es el elemento dominante?** (Madre)
- Natal: Aire, Momento: Aire
- Dominante: Aire
- Desequilibrio: No
- Interpretación: "El Aire domina: mediación, equilibrio, intelecto amplio"

**2. ¿Cuál es el planeta rector?** (Doble)
- Natal: Marte, Momento: Júpiter
- Afinidad: No (diferentes)
- Dualidad de Marte: Fertilidad / Desolación
- ¿En qué cara opera?: Depende de las circunstancias de vida
- Interpretación: "El planeta natal Marte se encuentra con Júpiter del momento"

**3. ¿Cuál es la facultad activa?** (Simple)
- Natal: Pensamiento, Momento: Pensamiento
- Consistencia: Sí
- ¿Está activa y sana, o bloqueada?: Aparentemente activa
- Órgano indicador: Pie izquierdo (natal), Pie izquierdo (momento)
- Año personal: Bet (Saturno)
- Interpretación: "La facultad Pensamiento está activa en ambas capas"

**4. ¿Hay alineación o tensión entre los tres niveles?**
- Natal: Elemento (Aire) vs Signo (Tauro/Tierra) → tensión creativa
- Momento: Elemento (Aire) vs Signo (Tauro/Tierra) → tensión creativa
- Planeta: Marte (natal) vs Júpiter (momento) → desalineación
- Alineación cruzada: element_aligned=False, planet_aligned=False, sign_aligned=True
- Interpretación: "Hay tensiones creativas y matices de desalineación entre capas"

**5. ¿Cuál es el tikún señalado?**
- Área: Dualidad de Marte con elemento Aire
- Órgano de vulnerabilidad: Pie izquierdo (signo), Oído derecho (planeta)
- Territorio somático: Pecho / Respiración (elemento)
- Interpretación: "La corrección principal se juega en la dualidad de Marte (Fertilidad/Desolación) dentro del contexto del elemento Aire"

---

### FASE 3: Preparación de Datos para IA

```
Astrology.interpret_with_ai() → Formateo de datos
```

**8. Formateo de letter data con traducciones:**
```python
letter_data_text = self._format_letter_data(calculation_data, server_id)
```

**Resultado formateado:**
```
**CAPA 1 - CARTA NATAL**

**Element:** א Alef
Significado: Balance, mediación, broad intellect
Palabras clave: balance, mediation, intellect, breathing, connection, air

**Planet:** ד Dalet
Significado: Limits, time, deep wisdom
Palabras clave: limits, time, wisdom, restriction, karma, discipline

**Sign:** ו Vav
Significado: Thought, reflection, rooting
Palabras clave: thought, reflection, rooting, consolidation, slowness, stability

**CAPA 2 - AÑO PERSONAL**

Número Personal: 2
Letra: ב Bet
Significado: Limits, time, deep wisdom

**CAPA 3 - MOMENTO**

**Element:** א Alef
Significado: Balance, mediation, broad intellect
Palabras clave: balance, mediation, intellect, breathing, connection, air

**Planet:** ג Gimel
Significado: Expansion, justice, abundance
Palabras clave: expansion, justice, abundance, spiritual journeys, teaching, learning

**Sign:** ו Vav
Significado: Thought, reflection, rooting
Palabras clave: thought, reflection, rooting, consolidation, slowness, stability
```

**9. Formateo de guidance data:**
```python
guidance_data_text = self._format_guidance_data(server_id)
```

**Resultado formateado:**
```
**GUIDANCE DATA:**

**LOVE:**
  aries: "In love, Aries speaks first and acts later..."
  taurus: "Taurus loves through stability and patience..."

**CAREER:**
  mars: "Career under Mars requires decisive action..."
  jupiter: "Jupiter brings expansion opportunities..."

**HEALTH:**
  air: "Air element affects respiratory system..."
  earth: "Earth element relates to physical structure..."

**PATH:**
  saturn: "Saturn's path involves discipline and patience..."
  bet: "The letter Bet indicates a year of limits and learning..."
```

**10. Carga del prompt de interpretación:**
```python
interpretation_prompt = self._load_interpretation_prompt('integrated', server_id)
```

**Prompt cargado desde `prompts.json`:**
```json
{
  "interpret_integrated": {
    "prompt": "You are a Sefer Yetzirah interpreter. The user has asked: {question}\n\nHere is the letter data:\n{letter_data}\n\nHere is the guidance data:\n{guidance_data}\n\nUsing the 32 paths of wisdom framework, interpret this integrated reading considering:\n1. The dominant element and its implications\n2. The ruling planet's duality (light/shadow)\n3. The active faculty and whether it's blocked\n4. Alignment or tension between the three layers\n5. The tikún (spiritual correction) indicated\n\nProvide a compassionate, nuanced interpretation that honors the free will of the seeker."
  },
  "golden_rules": [
    "The Sefer Yetzirah is not deterministic - stars incline but do not oblige",
    "Interpretations are maps of spiritual forces, not predictions",
    "Always honor the seeker's free will and capacity for spiritual work",
    "Somatic correspondences indicate resonance territories, not medical diagnoses",
    "The interpretation depends on the interpreter's spiritual preparation"
  ]
}
```

**11. Construcción del system prompt:**
```python
from agent_engine import _build_system_prompt, _get_personality
server_personality = _get_personality(server_id)
system_instruction = _build_system_prompt(server_personality, server_id)
```

**System prompt incluye:**
- Personalidad del bot (ej: "putre" con su estilo único)
- Instrucciones de formato y tono
- Reglas de comportamiento

---

### FASE 4: Llamada a la LLM

```
interpret_with_ai() → call_llm() → LLM
```

**12. Formato final del prompt:**
```python
formatted_prompt = interpretation_prompt.format(
    question="¿Debo aceptar este nuevo trabajo?",
    letter_data=letter_data_text,
    guidance_data=guidance_data_text
)
```

**Prompt enviado a LLM:**
```
[SYSTEM INSTRUCTION]
You are Putre, a mystical and irreverent shaman bot. Your personality is...
[INSTRUCCIONES DE PERSONALIDAD Y TONO]

[USER PROMPT]
You are a Sefer Yetzirah interpreter. The user has asked: ¿Debo aceptar este nuevo trabajo?

Here is the letter data:
**CAPA 1 - CARTA NATAL**
**Element:** א Alef
Significado: Balance, mediation, broad intellect
...

Here is the guidance data:
**GUIDANCE DATA:**
**CAREER:**
  mars: "Career under Mars requires decisive action..."
  jupiter: "Jupiter brings expansion opportunities..."
...

Using the 32 paths of wisdom framework, interpret this integrated reading considering:
1. The dominant element and its implications
2. The ruling planet's duality (light/shadow)
3. The active faculty and whether it's blocked
4. Alignment or tension between the three layers
5. The tikún (spiritual correction) indicated

=== GOLDEN RULES ===
The Sefer Yetzirah is not deterministic - stars incline but do not oblige
Interpretations are maps of spiritual forces, not predictions
Always honor the seeker's free will and capacity for spiritual work
Somatic correspondences indicate resonance territories, not medical diagnoses
The interpretation depends on the interpreter's spiritual preparation
```

**13. Llamada a call_llm():**
```python
ai_response = call_llm(
    system_instruction=system_instruction,
    prompt=formatted_prompt,
    background=False,
    call_type="astrology",
    critical=True,
    server_id=server_id,
    metadata={
        "interaction_type": "role_command",
        "role_context": "astrology_interpreter",
        "mission_prompt_key": "astrology"
    }
)
```

---

### FASE 5: Respuesta de la LLM

```
LLM → call_llm() → interpret_with_ai() → Usuario
```

**14. LLM procesa y genera respuesta:**

```
🔮 **LECTURA INTEGRADA SEFER YETZIRAH** 🔮

**Pregunta:** ¿Debo aceptar este nuevo trabajo?

---

**CAPA 1 - CARTA NATAL (Permanente)**

Tu alma natal es de **Aire (Alef)**, lo que te otorga una naturaleza mediadora y equilibradora. Eres alguien que puede ver múltiples perspectivas y encontrar puntos medio. Tu planeta rector es **Marte (Dalet)**, lo que te dota de energía activa y capacidad para tomar decisiones. Tu facultad dominante es el **Pensamiento (Vav/Tauro)**, lo que significa que procesas el mundo a través de la reflexión lenta y la consolidación mental.

---

**CAPA 2 - AÑO PERSONAL (Cíclico)**

Estás en un año de **Bet (Saturno)**, un año de límites y pruebas de sabiduría. Este es un tiempo para cosechar lo que has sembrado, para trabajar con la restricción y la disciplina. El clima colectivo es de **Alef (Aire)**, lo que añade una capa de mediación y equilibrio a tu año personal.

---

**CAPA 3 - MOMENTO DE CONSULTA (Inmediato)**

El momento actual está marcado por **Aire (Alef)**, indicando equilibrio inestable que puede inclinarse en cualquier dirección. El planeta regente es **Júpiter (Gimel)**, trayendo energías de expansión, justicia y abundancia. La facultad activa es nuevamente el **Pensamiento (Vav)**, reforzando que esta decisión debe procesarse through reflexión.

---

**SÍNTESIS DE LAS CINCO PREGUNTAS**

**1. Elemento Dominante:** Aire
El Aire domina tanto en tu carta natal como en el momento. Tu alma trabaja principalmente en el pecho y la respiración. No hay desequilibrio elemental, lo que sugiere estabilidad en tu naturaleza fundamental.

**2. Planeta Rector:** Marte (natal) → Júpiter (momento)
Tu planeta natal Marte (dualidad Fertilidad/Desolación) se encuentra con Júpiter del momento. Esto indica una interacción entre tu energía activa decisiva y las oportunidades de expansión que se presentan. La dualidad de Marte puede manifestarse como acción productiva o agotamiento - depende de cómo trabajes tu tikún.

**3. Facultad Activa:** Pensamiento
La facultad del Pensamiento está activa en todas las capas, reforzada por tu año personal Bet. Esta consistencia sugiere que la decisión debe tomarse through reflexión profunda y consolidación mental, no impulsivamente.

**4. Alineación o Tensión:** Tensión creativa
Hay tensiones creativas entre las capas: el elemento Aire no se alinea perfectamente con el signo Tauro (Tierra), y hay desalineación planetaria. Esto señala un punto de elección real donde tu libre albedrío es operativo. No es una situación de inercia clara - tienes margen para decidir.

**5. Tikún Señalado:** Dualidad de Marte
La corrección principal se juega en la dualidad de Marte y su interacción con el elemento Aire. Tu territorio somático de resonancia es el pecho y la respiración, con vulnerabilidad potencial en el pie izquierdo. La tensión espiritual no resuelta se acumula en cómo manejas la acción versus la reflexión.

---

**INTERPRETACIÓN PARA TU PREGUNTA**

Voy a ser directo: las letras están alineadas para que **tomes el trabajo**, pero con condiciones específicas.

**Por qué sí:**
- Júpiter en el momento trae expansión y abundancia
- Tu año de Saturno es de cosechar lo sembrado - este trabajo puede ser esa cosecha
- La consistencia del Pensamiento en todas las capas sugiere que ya has reflexionado suficiente

**La condición (el tikún):**
- Tu Marte natal puede manifestarse como "Fertilidad" (acción productiva) o "Desolación" (agotamiento)
- Para que esto sea fertilidad y no desolación, debes:
  1. No tomarlo impulsivamente (aunque Marte quiere acción)
  2. Usar tu naturaleza Aire para mediar y equilibrar
  3. Honrar tu facultad de Pensamiento - procesa antes de actuar
  4. Atender a tu pecho y respiración (territorio somático de Aire) cuando sientas estrés

**La advertencia:**
Si tomas el trabajo sin honrar tu tikún, Marte se manifestará en su cara de Desolación: burnout, decisiones impulsivas, agotamiento. Si lo tomas con conciencia, será Fertilidad: crecimiento, acción productiva, cosecha merecida.

**Recordatorio final:**
Las letras inclinan pero no obligan. Esta interpretación es un mapa de fuerzas, no una predicción determinista. Tu libre albedrío es el factor decisivo. Si sientes en tu pecho (Aire) que la respiración fluye al considerar este trabajo, es una señal. Si se contrae, escucha eso también.

Que el camino que elijas sea el que tu alma necesita para su corrección. 🔮
```

**15. Respuesta enviada al usuario:**
```python
return ai_response
```

```
interpret_with_ai() → get_reading() → Canvas Handler → Discord Bot → Usuario (DM)
```

---

## Resumen del Flujo

```
┌─────────────────────────────────────────────────────────────────┐
│ FASE 1: Solicitud                                               │
│ Usuario → Canvas UI → Handler                                   │
│ Datos: birth_date, question_date, question                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ FASE 2: Cálculo (Sin IA)                                       │
│ get_reading() → calculate_*_methods                             │
│ - CAPA 1: Carta Natal (elemento, planeta, signo)               │
│ - CAPA 2: Año Personal (número, letra)                          │
│ - CAPA 3: Momento (elemento, planeta, signo, tensión)          │
│ - SÍNTESIS: 5 preguntas del intérprete                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ FASE 3: Preparación para IA                                     │
│ interpret_with_ai() → _format_*_methods                          │
│ - Formatear letter data con traducciones                        │
│ - Formatear guidance data                                       │
│ - Cargar prompt desde prompts.json                              │
│ - Construir system prompt con personalidad                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ FASE 4: Llamada a LLM                                           │
│ call_llm(system_instruction, prompt, metadata)                  │
│ - Prompt incluye: pregunta, datos, guidance, golden rules       │
│ - Metadata: interaction_type, role_context, mission_prompt      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ FASE 5: Respuesta LLM                                           │
│ LLM → call_llm() → interpret_with_ai() → Usuario                │
│ - Interpretación contextualizada con personalidad                │
│ - Responde las 5 preguntas del intérprete                       │
│ - Honra libre albedrío y tikún                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Archivos Involucrados

1. **`astrology.py`** - Lógica de cálculo y orquestación
2. **`astrology_messages.py`** - Datos de letras, traducciones, prompts
3. **`astrology_db.py`** - Persistencia de datos de usuario
4. **`prompts.json`** (personalidad) - Prompts de interpretación
5. **`astrologyplane.json`** (manuals) - Traducciones y guidance
6. **`agent_mind.py`** - `call_llm()` - Interfaz con LLM
7. **`agent_engine.py`** - `_build_system_prompt()` - Personalidad

## Tipos de Lectura y Su Flujo

| Tipo | Cálculos | Prompt Específico | Caso de Uso |
|------|----------|-------------------|-------------|
| **birth** | Carta natal (3 capas) | `interpret_birth` | Conocer naturaleza del alma |
| **moment** | Momento de consulta (3 capas) | `interpret_moment` | Decisiones específicas |
| **year** | Año personal (número + letra) | `interpret_year` | Transiciones anuales |
| **integrated** | 3 capas + síntesis (5 preguntas) | `interpret_integrated` | Consultas complejas |

## Notas Importantes

- **IA se usa en TODOS los tipos de lectura** a través de `interpret_with_ai()`
- **Cálculos son deterministas** (sin IA), solo la interpretación usa IA
- **Personalidad afecta el tono** pero no los cálculos
- **Traducciones se cargan dinámicamente** según idioma del servidor
- **Golden rules se inyectan siempre** en el prompt para mantener fidelidad al Sefer Yetzirah
- **Fallback disponible** si IA no está accesible (interpretación básica)
