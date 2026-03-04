# 🎲 Subrole "Bote" - Juego de Dados contra la Banca

## 📋 Descripción

El subrole **"Bote"** es un juego de dados donde los usuarios pueden apostar oro contra una banca acumulada. El bot actúa como la banca, gestionando las apuestas y pagando premios según las combinaciones de dados. El juego requiere obligatoriamente que el rol banquero esté activo para gestionar las transacciones de oro.

## 🎯 Características Principales

- **Integración con Banquero**: El bote tiene su propia cuenta en el sistema del banquero
- **Juego de 3 dados**: Sistema probabilístico con diferentes combinaciones premiadas
- **Bote acumulativo**: Crece con cada tirada fallida hasta que alguien saca 1-1-1
- **Límites y seguridad**: Protección contra abusos y control de apuestas
- **Estadísticas detalladas**: Registro de partidas, rankings e historial

## 🎲 Tabla de Combinaciones

| Combinación | Probabilidad | Premio | Descripción |
|-------------|-------------|---------|-------------|
| 1-1-1 | 0.46% | **TODO EL BOTE** | El gran premio, se lleva todo el acumulado |
| Triple cualquiera | 2.78% | x3 apuesta | La banca paga 3 veces lo apostado |
| Escalera 4-5-6 | 2.78% | x5 apuesta | La banca paga 5 veces lo apostado |
| Par | 41.67% | x1 apuesta | Recupera su apuesta (empate) |
| Cualquier otra | 52.31% | Sin premio | Pierde la apuesta (va al bote) |

## 💰 Comandos del Juego

### Comandos de Usuario
- `!bote jugar` - Realiza una tirada de dados con la apuesta fija configurada
- `!bote saldo` - Muestra el saldo actual del bote
- `!bote stats` - Muestra tus estadísticas personales
- `!bote ranking` - Muestra el ranking de jugadores del servidor
- `!bote historial` - Muestra las últimas partidas jugadas
- `!bote ayuda` - Muestra la ayuda del juego

### Comandos de Administración
- `!bote config apuesta <cantidad>` - Configura la apuesta fija (solo admins)
- `!bote config anuncios on/off` - Activa/desactiva anuncios automáticos (solo admins)

## 🏦 Integración con el Banquero

El sistema del bote está completamente integrado con el rol banquero:

1. **Cuenta propia del bote**: El bote tiene su propia cuenta en el sistema del banquero (`bote_banca`)
2. **Transacciones automáticas**: Todas las apuestas y premios se registran como transacciones del banquero
3. **Saldo inicial**: El bote se crea automáticamente con 100 monedas de saldo inicial
4. **Verificación de saldos**: Se verifica que los jugadores tengan suficiente saldo antes de apostar

## 📊 Estadísticas y Registro

El sistema mantiene registro detallado de:

- **Partidas jugadas**: Cada tirada queda registrada con dados, apuesta y resultado
- **Estadísticas personales**: Total jugado, ganado, botes ganados, mayor premio
- **Ranking del servidor**: Clasificación de jugadores según diferentes métricas
- **Historial reciente**: Últimas partidas jugadas en el servidor
- **Balance general**: Estadísticas globales del juego en el servidor

## 🎮 Ejemplo de Juego

```
Usuario: !bote jugar
Bot: 🎲 **TIRADA:** 🎲3 🎲5 🎲2
Bot: 📊 **COMBINACIÓN:** SIN PREMIO
Bot: 💰 **PREMIO:** 😅 SIN PREMIO - Sin premio. ¡Suerte la próxima!
Bot: 💎 **BOTE ACTUAL:** 156 monedas

Usuario: !bote jugar
Bot: 🎲 **TIRADA:** 🎲4 🎲4 🎲4
Bot: 📊 **COMBINACIÓN:** TRIPLE
Bot: 💰 **PREMIO:** 🎊 ¡GANASTE! TRIPLE - Premio: 30 monedas
Bot: 💎 **BOTE ACTUAL:** 141 monedas
```

## 🔧 Configuración

### Configuración por Defecto
- **Apuesta fija**: 10 monedas
- **Bote inicial**: 100 monedas
- **Anuncios automáticos**: Activados

### Personalización
Los administradores pueden configurar:
- **Apuesta fija**: Cantidad única que todos los jugadores deben apostar
- **Frecuencia de anuncios automáticos**: Control de cuándo se anuncia el bote grande
- **Mensajes personalizados**: Según la personalidad del bot

## 🛡️ Seguridad y Límites

- **Verificación de saldo**: No se permite jugar si no se tiene suficiente saldo para la apuesta fija
- **Apuesta única**: Todos los jugadores apostan la misma cantidad (configurable por admins)
- **Registro completo**: Todas las transacciones quedan registradas
- **Protección contra spam**: Límites en la frecuencia de juego

## 📁 Estructura de Archivos

```
roles/trilero/subroles/bote/
├── bote.py              # Lógica principal del juego
├── db_bote.py          # Base de datos específica del bote
├── README_BOTE.md      # Esta documentación
└── El_Bote_Manual.txt  # Reglas originales del juego
```

## 🚀 Funcionamiento Técnico

1. **Inicialización**: El bote crea su cuenta en el sistema del banquero
2. **Gestión de apuestas**: Cada apuesta se descuenta del jugador y se añade al bote
3. **Evaluación de dados**: Sistema probabilístico con combinaciones predefinidas
4. **Pago de premios**: Los premios se pagan directamente desde la cuenta del bote
5. **Registro estadístico**: Todas las partidas se registran para análisis histórico

## 🎭 Mensajes Personalizados

Cada personalidad puede tener sus propios mensajes:

### Kronk
- **Invitación**: "¡KRONK TE RETA A JUGAR AL BOTE! 🎲 Tira dados y gana oro como orco verdadero!"
- **Ganador**: "¡¡¡KRONK APROBUEBA TU VICTORIA!!! 🎉 ¡Eres bueno en los dados!"
- **Perdedor**: "Kronk se ríe de tu mala suerte... ¡Prueba otra vez, humano débil!"

### Putre
- **Invitación**: "🕐 ¡JUEGA AL BOTE PUTRE! 🎲 Apuesta tu mierda de oro y quizás ganes algo."
- **Ganador**: "¡PUTRE JODER! ¡GANASTE! 🎉 Ni que fuera tan bueno..."
- **Perdedor**: "JAJAJA ¡PERDISTE! 🤣 Tu oro es mío ahora, inútil."

## 📈 Estrategia y Probabilidades

- **Rentabilidad del bote**: El bote crece en promedio 0.36 monedas por tirada
- **Frecuencia del gran premio**: El 1-1-1 aparece estadísticamente cada 216 tiradas
- **Tamaño típico del bote**: 15-40 monedas (pequeño), 40-100 (mediano), 100+ (grande)

## 🔮 Futuras Mejoras

- **Torneos especiales**: Eventos con botes incrementados
- **Sistema de niveles**: Recompensas por jugadores frecuentes
- **Variaciones del juego**: Diferentes modos de apuesta
- **Integración con otros roles**: Premios especiales para otros roles

---

**🎲 ¡El Bote está listo para aceptar tus apuestas!**
