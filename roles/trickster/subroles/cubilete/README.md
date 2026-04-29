# Cubilete - Subrol de Trickster

## Descripción

Juego de poker de dados (Cubilete) implementado como subrol de Trickster. Se juega contra la banca con un sistema de bote acumulativo estilo jackpot progresivo.

## Mecánica del Juego

### Configuración Básica
- **Dados**: 5 dados de 6 caras
- **Tiradas**: Hasta 3 tiradas por ronda (Yahtzee-style)
- **Apuesta**: 2x TAE (2 veces la daily allowance del servidor)
- **Modo**: 1 ronda contra la banca (bote acumulativo)

### Valor de los Dados
Orden de mayor a menor valor:
1. As (A)
2. Rey (K)
3. Reina (Q)
4. Jota (J)
5. Roja (8)
6. Negra (7)

### Combinaciones y Multiplicadores

| Combinación | Descripción | Multiplicador | Pagado por |
|-------------|-------------|---------------|------------|
| **Repóker** | 5 dados iguales | BOTE (completo) | Bote acumulado |
| **Póker** | 4 dados iguales | 4x | Banca |
| **Full** | 3 iguales + 2 iguales | 3x | Banca |
| **Trío** | 3 dados iguales | 1.5x | Banca |
| **Doble Pareja** | 2 parejas distintas | 1x | Banca |
| **Pareja** | 2 dados iguales | 0.5x | Banca |
| **Nada** | Sin combinación | 0x | - |

### Reglas de Juego
1. El jugador realiza hasta 3 tiradas de 5 dados
2. Puede mantener los dados que desee entre tiradas
3. La combinación final determina el premio según la tabla
4. Premios menores son pagados por la banca
5. Repóker se lleva todo el bote acumulado
6. Si el bote está vacío, se reinicia con un monto base

## Estadísticas

### Probabilidades (con 3 tiradas)

| Combinación | Probabilidad | Frecuencia |
|-------------|--------------|------------|
| Repóker | 0.08% | 1 en 1,299 |
| Póker | 1.93% | 1 en 52 |
| Full | 3.86% | 1 en 26 |
| Trío | 15.43% | 1 en 6 |
| Doble Pareja | 20.83% | 1 en 5 |
| Pareja | 45.84% | 1 en 2 |
| Nada | 12.04% | 1 en 8 |

### RTP y Crecimiento del Bote
- **RTP total**: 86.19%
- **Crecimiento del bote**: 13.80% de la apuesta por jugada
- **Promedio para bote de 10x TAE**: ~36 jugadas
- **Promedio para bote de 20x TAE**: ~73 jugadas
- **Promedio para bote de 40x TAE**: ~146 jugadas

**Nota**: La apuesta es 2x TAE, por lo que los valores absolutos dependen de la TAE configurada en el servidor.

### Variabilidad
El repoker puede salir en cualquier momento:
- Mínimo: jugada 1 (bote pequeño)
- Promedio: jugada 36
- Máximo: 500+ jugadas (bote grande)
- Esta variabilidad es la emoción del jackpot

## Reglas Visuales

### Emojis de Dados
```
🎲1 🎲2 🎲3 🎲4 🎲5 🎲6
```

### Emojis de Cartas/Palos (decoración)
```
♠️ ♥️ ♦️ ♣️
```

### Emojis Especiales
```
🎰 - Jackpot/Repóker
🏆 - Ganador
💸 - Perdedor
🎲 - Juego de dados
💰 - Dinero/Oro
```

### Formato de Mensajes

#### Título del Juego
```
🎲 **CUBILETE** 🎲
```

#### Resultado de la Tirada
```
🎲 **TU TIRADA:**
🎲A 🎲K 🎲Q 🎲J 🎲8

📊 **COMBINACIÓN:**
Full de Ases y Reyes

💰 **PREMIO:**
30 monedas (3x apuesta)

🏆 **BOTE ACTUAL:**
150 monedas
```

#### Anuncio de Jackpot
```
🎰🎰🎰 **¡JACKPOT!** 🎰🎰🎰
**{jugador}** ha ganado el bote completo de **{monto}** monedas
```

#### Mensaje de Perdedor
```
😅 Sin suerte esta vez
🎲 {combinación} - Sin premio
Mejor suerte la próxima
```

## Interfaz Interactiva de Tiradas

### Sistema de Selección de Dados (Discord UI)

El sistema de selección de datos durante las tiradas utiliza componentes interactivos de Discord, similar al sistema de shortcuts del Canvas.

#### Componentes UI

**Botones de Dados** (`discord.ui.Button`)
- Cada dado se representa como un botón clickeable
- Estado visual: Normal (no mantenido) / Resaltado (mantenido)
- Click: Alterna el estado de mantener/no mantener

**Botones de Acción**
- **Relanzar 🎲**: Lanza los dados no mantenidos
- **Terminar ✅**: Finaliza la ronda antes de 3 tiradas
- **Cancelar ❌**: Abandona la partida (pierde apuesta)

**Indicador de Tiradas**
- Muestra tirada actual: `Tirada 1/3`, `Tirada 2/3`, `Tirada 3/3 (Final)`

#### Flujo de Interacción

**Tirada 1**
1. Bot muestra 5 botones de dados con valores aleatorios
2. Jugador hace click en dados que quiere mantener
3. Dados seleccionados cambian de estilo (resaltado)
4. Jugador hace click en "Relanzar" → Dados no seleccionados se relanzan

**Tirada 2**
1. Bot actualiza dados: mantenidos conservan valor, otros se relanzan
2. Jugador puede mantener más dados o cambiar selección
3. Jugador hace click en "Relanzar" → Dados no seleccionados se relanzan
4. O puede hacer click en "Terminar" → Finaliza con combinación actual

**Tirada 3 (Final)**
1. Bot actualiza dados por última vez
2. Botón "Relanzar" se deshabilita
3. Solo disponible "Terminar" para finalizar

#### Ejemplo de Implementación

```python
class DiceButton(discord.ui.Button):
    """Button representing a single die."""
    
    def __init__(self, die_value: int, position: int, is_held: bool = False):
        self.die_value = die_value
        self.position = position
        self.is_held = is_held
        
        emoji = f"🎲{die_value}"
        label = emoji if not is_held else f"🔒{emoji}"
        style = discord.ButtonStyle.success if is_held else discord.ButtonStyle.secondary
        
        super().__init__(label=label, style=style, row=position // 3)
    
    async def callback(self, interaction: discord.Interaction):
        """Toggle hold state when clicked."""
        self.is_held = not self.is_held
        # Update button style and label
        await interaction.response.edit_message(view=self.view)


class CubileteGameView(discord.ui.View):
    """View for cubilete game interaction."""
    
    def __init__(self, dice_values: list, current_roll: int):
        super().__init__(timeout=300)
        self.dice_values = dice_values
        self.held_dice = [False] * 5
        self.current_roll = current_roll
        self.max_rolls = 3
        
        self._add_dice_buttons()
        self._add_action_buttons()
    
    def _add_dice_buttons(self):
        """Add 5 dice buttons."""
        for i, value in enumerate(self.dice_values):
            button = DiceButton(value, i, self.held_dice[i])
            self.add_item(button)
    
    def _add_action_buttons(self):
        """Add action buttons based on current roll."""
        if self.current_roll < self.max_rolls:
            reroll_btn = discord.ui.Button(label="🎲 Relanzar", style=discord.ButtonStyle.primary)
            reroll_btn.callback = self._reroll
            self.add_item(reroll_btn)
        
        finish_btn = discord.ui.Button(label="✅ Terminar", style=discord.ButtonStyle.success)
        finish_btn.callback = self._finish
        self.add_item(finish_btn)
        
        cancel_btn = discord.ui.Button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)
    
    async def _reroll(self, interaction: discord.Interaction):
        """Reroll non-held dice."""
        # Reroll logic here
        pass
    
    async def _finish(self, interaction: discord.Interaction):
        """Finish game with current combination."""
        # Calculate prize and finish
        pass
    
    async def _cancel(self, interaction: discord.Interaction):
        """Cancel game (lose bet)."""
        # Cancel logic
        pass
```

#### Estado Visual de Dados

| Estado | Estilo | Label |
|--------|-------|-------|
| No mantenido | Secondary | 🎲X |
| Mantenido | Success | 🔒🎲X |
| Relanzado | Primary | 🎲X (nuevo valor) |

#### Mensajes de Estado

**Inicio de tirada:**
```
🎲 **TIRADA 1/3**
Selecciona los dados que quieres mantener y haz click en "Relanzar"
```

**Dados seleccionados:**
```
🎲 **TIRADA 2/3**
Dados mantenidos: 🔒🎲A 🔒🎲K
Haz click en "Relanzar" para tirar los demás, o "Terminar" para finalizar
```

**Última tirada:**
```
🎲 **TIRADA 3/3 (FINAL)**
Esta es tu última tirada. Haz click en "Terminar" para ver tu resultado.
```

## Estructura de Implementación

```
roles/trickster/subroles/cubilete/
├── __init__.py
├── cubilete.py              # Lógica del juego (combinaciones, premios)
├── cubilete_db.py           # Persistencia (stats, historial, bote)
├── cubilete_discord.py      # Comandos Discord (interacción)
└── cubilete_messages.py     # Mensajes localizados (por personalidad)
```

## Integración con el Sistema

### Cambios en `trickster.py`
```python
ROLE_CONFIG = {
    "name": "trickster",
    "description": "Role specialized in scams and deceptions to get resources",
    "subroles": ["dice_game", "cubilete"]  # Añadir cubilete
}

# Cargar función de tarea
_cubilete_task = _load_subrole_function(
    os.path.join(_TRICKSTER_DIR, "subroles", "cubilete", "cubilete.py"),
    "cubilete_task"
)

async def trickster_task():
    """Execute all trickster role tasks."""
    logger.info("🎭 Starting trickster role tasks...")
    
    if _dice_game_task:
        try:
            await _dice_game_task()
        except Exception as e:
            logger.exception(f"❌ Error in dice game task: {e}")
    
    if _cubilete_task:
        try:
            await _cubilete_task()
        except Exception as e:
            logger.exception(f"❌ Error in cubilete task: {e}")
    
    logger.info("✅ Trickster role tasks completed")
```

### Integración con Banker
- Crear wallet `cubilete_pot` para el bote acumulado
- Usar `update_balance` para transacciones
- Integrar con sistema de TAE para refill del bote después de jackpot

### Integración con Canvas UI
- Añadir botón "Cubilete" en la vista de Trickster
- Comandos: Play, Stats, Ranking, History, Admin
- Configuración: apuesta fija, anuncios de jackpot

## Configuración

### Configuración por Servidor (agent_config.json)
```json
{
  "roles": {
    "trickster": {
      "enabled": true,
      "subroles": {
        "cubilete": {
          "enabled": true,
          "config": {
            "bet_multiplier_tae": 2,
            "announcements_active": true,
            "pot_refill_multiplier": 15
          }
        }
      }
    }
  }
}
```

**Nota**: La apuesta se calcula dinámicamente como `bet_multiplier_tae * TAE` del servidor.

### Configuración por Personalidad
Archivo: `personalities/{personality}/descriptions/trickster.json`
```json
{
  "cubilete": {
    "invitation": "🎲 **¡CUBILETE!** 🎲 Apuesta al bote acumulado",
    "winner": "🎉 **¡GANADOR!**",
    "loser": "😅 Sin suerte",
    "jackpot": "🎰 **¡JACKPOT!**",
    "repoker": "🎰 (REPÓKER)",
    "poker": "(PÓKER)",
    "full": "(FULL)",
    "trio": "(TRÍO)",
    "doble_pareja": "(DOBLE PAREJA)",
    "pareja": "(PAREJA)",
    "nothing": "(SIN PREMIO)"
  }
}
```

## Modelo de Pagos

### Estándar de Casinos (Jackpot Progresivo)
- **Premios menores**: Pagados por la banca según tabla de pagos
- **Jackpot**: Pagado del bote acumulativo
- Parte de cada apuesta se destina al bote

### Implementación en Cubilete
- Apuesta: 2x TAE (dinámico según configuración del servidor)
- Si pareja (45.84%): Banca paga 1x TAE, bote recibe 1x TAE
- Si nada (12.04%): Banca paga 0, bote recibe 2x TAE
- Si repoker (0.08%): Bote paga todo al jugador
- Premios mayores (poker, full, etc.): Banca paga según multiplicador

## Flujo de Ejecución

### 1. Jugador inicia juego
1. Verificar balance suficiente (2x TAE del servidor)
2. Deducir apuesta del wallet del jugador
3. Añadir apuesta al bote temporal

### 2. Ejecutar tiradas
1. Tirada 1: Lanzar 5 dados
2. Opción: Mantener dados, relanzar el resto
3. Tirada 2: Relanzar dados no mantenidos
4. Opción: Mantener más dados, relanzar el resto
5. Tirada 3: Relanzar dados no mantenidos (final)

### 3. Calcular resultado
1. Analizar combinación final
2. Determinar premio según tabla
3. Si repoker: Pagar bote completo, reiniciar bote
4. Si otro premio: Banca paga premio, bote recibe diferencia
5. Si nada: Bote recibe apuesta completa

### 4. Actualizar estadísticas
1. Guardar jugada en historial
2. Actualizar stats del jugador
3. Actualizar balance del bote
4. Enviar anuncios si corresponde

## Anuncios Automáticos

### Jackpot Ganado
- Anunciar en el canal del servidor
- Incluir nombre del jugador y monto ganado
- Refill del bote con 15x TAE del servidor

### Bote Alto (Opcional)
- Anunciar cuando el bote supera un umbral
- Umbral configurable (ej. 72x apuesta = 720 monedas)

