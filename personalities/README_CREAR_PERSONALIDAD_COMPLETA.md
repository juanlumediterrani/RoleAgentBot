# 🎭 Guía para Crear Personalidades con Mensajes por Rol

## 📋 Overview

Este documento proporciona una guía completa para crear archivos de personalidad que incluyan mensajes personalizados para CADA rol del RoleAgentBot, asegurando una experiencia inmersiva y coherente en todas las funcionalidades del bot.

## 🎯 Roles del Sistema

El RoleAgentBot tiene los siguientes roles, cada uno con sus propios tipos de mensajes:

### 1. **News Watcher** (`news_watcher`)
- **Función**: Monitoreo y distribución de noticias
- **Sección JSON**: `discord.vigia_messages`
- **Comandos**: `!watcherhelp`, `!watcher`

### 2. **MC (Master of Ceremonies)** (`mc`)
- **Función**: Música y entretenimiento en canales de voz
- **Sección JSON**: `discord.mc_messages`
- **Comandos**: `!mc play`, `!mc add`, `!mc help`, etc.

### 3. **Trickster** (`trickster`)
- **Función**: Juegos y donaciones para conseguir recursos
- **Sección JSON**: `discord.bote_messages`, `discord.role_messages`
- **Comandos**: `!trickster`, `!dice play`, `!dice stats`

### 4. **Treasure Hunter** (`treasure_hunter`)
- **Función**: Búsqueda de tesoros y objetos valiosos
- **Sección JSON**: `discord.poe2_messages`
- **Comandos**: `!hunter`, `!hunterhelp`

### 5. **Banker** (`banker`)
- **Función**: Gestión de economía y transacciones
- **Sección JSON**: `discord.banquero_messages`
- **Comandos**: `!banker`, `!bankerhelp`


---

## 🏗️ Estructura Completa del Archivo de Personalidad

```json
{
  "name": "MI_PERSONALIDAD",
  "bot_display_name": "Mi Personaje",
  "identity": "Descripción completa del personaje...",
  "never_break": [...],
  "emergency_fallbacks": [...],
  "format_rules": {...},
  "orthography": [...],
  "style": [...],
  "examples": [...],
  "discord": {
    "vigia_messages": {
      // Mensajes del Vigía de Noticias
    },
    "mc_messages": {
      // Mensajes del MC (música)
    },
    "trilero_messages": {
      // Mensajes del Trilero (estafas)
    },
    "buscador_messages": {
      // Mensajes del Buscador de Tesoros
    },
    "anillo_messages": {
      // Mensajes de Búsqueda del Anillo
    },
    "oro_messages": {
      // Mensajes de Pedir Oro
    },
    "general_messages": {
      // Mensajes generales del bot
    },
    "role_messages": {
      // Mensajes de gestión de roles
    },
    "greeting_messages": {
      // Mensajes de saludos
    }
  }
}
```

---

## 📰 1. Mensajes del Vigía de Noticias

### Estructura Básica
```json
"vigia_messages": {
  "feeds_disponibles_title": "📡 Fuentes de [PERSONALIDAD]",
  "categorias_disponibles_title": "📂 Categorías de [PERSONALIDAD]",
  "suscripcion_exitosa_categoria": "Mensaje para suscripción a '{categoria}'",
  "suscripcion_exitosa_feed": "Mensaje para feed {feed_id} de '{categoria}'",
  "suscripcion_canal_exitosa_categoria": "Mensaje para canal suscrito a '{categoria}'",
  "suscripcion_cancelada_categoria": "Mensaje al cancelar '{categoria}'",
  "error_general": "Mensaje de error: {error}",
  "estado_titulo": "🔭 Vigilancias de [PERSONALIDAD]",
  "uso_suscribir": "📝 Uso: `!vigia suscribir <categoria>`",
  "notificacion_critica_detectada": "🚨 Alerta crítica: {titulo}",
  "notificacion_normal": "📡 Noticias: {titulo}"
}
```

### Mensajes Completos Requeridos

#### ✅ Mensajes de Éxito
- `suscripcion_exitosa_categoria` - Suscripción a categoría
- `suscripcion_exitosa_feed` - Suscripción a feed específico
- `suscripcion_canal_exitosa_categoria` - Canal suscrito a categoría
- `suscripcion_canal_exitosa_feed` - Canal suscrito a feed
- `feed_agregado_exitosa` - Feed agregado exitosamente
- `suscripcion_general_exitosa` - Suscripción general con clasificación
- `suscripcion_palabras_exitosa` - Suscripción a palabras clave
- `suscripcion_mixta_exitosa` - Suscripción mixta

#### ❌ Mensajes de Error
- `error_general` - Error genérico: `{error}`
- `error_suscripcion` - Error al suscribir
- `error_cancelacion` - Error al cancelar
- `error_permisos` - Sin permisos
- `error_feed_no_encontrado` - Feed no existe: `{feed_id}`
- `error_categoria_no_encontrada` - Categoría no existe: `{categoria}`
- `error_feed_id_invalido` - ID de feed inválido
- `error_no_hay_feeds` - No hay feeds disponibles
- `error_no_hay_categorias` - No hay categorías disponibles
- `error_no_suscripciones` - No hay suscripciones activas

#### 📊 Mensajes de Estado
- `estado_titulo` - Título de suscripciones personales
- `estado_canal_titulo` - Título de suscripciones de canal
- `palabras_clave_titulo` - Título de palabras clave
- `feeds_disponibles_title` - Título de feeds disponibles
- `categorias_disponibles_title` - Título de categorías disponibles

#### 📝 Mensajes de Uso
- `uso_suscribir` - Uso para suscribir
- `uso_cancelar` - Uso para cancelar
- `uso_general` - Uso general
- `uso_palabras` - Uso de palabras clave
- `usage_agregar_feed` - Uso para agregar feeds
- `usage_canal_suscribir` - Uso de canal suscribir
- `usage_canal_cancelar` - Uso de canal cancelar

#### 🚨 Mensajes de Notificación
- `notificacion_critica_detectada` - Noticias críticas: `{titulo}`
- `notificacion_normal` - Noticias normales: `{titulo}`

### Ejemplo Completo - Kronk
```json
"vigia_messages": {
  "feeds_disponibles_title": "📡 Fuentes de Kronk",
  "suscripcion_exitosa_categoria": "UHHH Kronk vigilar '{categoria}' para umano! Traer noticias feas!",
  "error_general": "UHHH Kronk estar roto! Error: {error}",
  "estado_titulo": "🔨 Vigilancia de Kronk",
  "notificacion_critica_detectada": "🚨 PELIGRO GRAAAH! Kronk ver: {titulo}",
  "notificacion_normal": "📡 Kronk detectar notisia: {titulo}"
}
```

---

## 🎵 2. Mensajes del MC (Música)

### Estructura Básica
```json
"mc_messages": {
  "voice_join_empty": "Mensaje al unirse a canal vacío",
  "voice_leave_empty": "Mensaje al dejar canal vacío",
  "now_playing": "Mensaje de canción actual: {song}",
  "song_added": "Mensaje al agregar canción: {song}",
  "song_skipped": "Mensaje al saltar canción",
  "queue_empty": "Mensaje cuando la cola está vacía",
  "queue_cleared": "Mensaje al limpiar la cola",
  "volume_set": "Mensaje al ajustar volumen: {volume}",
  "play_error": "Mensaje de error al reproducir",
  "not_in_voice": "Mensaje si no está en canal de voz"
}
```

### Mensajes Completos Requeridos

#### 🎤 Conexión de Voz
- `voice_join_empty` - Al unirse a canal vacío: `{channel_name}`
- `voice_leave_empty` - Al dejar canal vacío
- `not_in_voice` - Usuario no está en canal de voz
- `no_permissions` - Sin permisos para unirse
- `timeout_connecting` - Timeout al conectar
- `voice_connection_error` - Error de conexión de voz
- `discord_connect_error` - Error de Discord
- `general_connect_error` - Error general de conexión

#### 🎵 Reproducción
- `now_playing` - Canción actual: `{song}`
- `song_added` - Canción agregada: `{song}`
- `song_skipped` - Canción saltada
- `queue_empty` - Cola vacía
- `queue_cleared` - Cola limpiada
- `play_error` - Error al reproducir
- `next_song_error` - Error siguiente canción

#### 🔊 Control
- `volume_set` - Volumen ajustado: `{volume}`
- `volume_range_error` - Error de rango de volumen
- `volume_adjust_error` - Error al ajustar volumen

#### ⏹️ Desconexión
- `queue_end_disconnect` - Desconexión por fin de cola
- `inactive_disconnect` - Desconexión por inactividad

#### 📵 Mensajes Privados
- `dm_help_error` - Error al enviar DM
- `dm_help_blocked` - DM bloqueado
- `help_dm_error` - Error ayuda DM
- `no_dm_permission` - Sin permiso DM

#### ❌ Errores Críticos
- `no_voice_connection` - Sin conexión de voz
- `voice_disconnected` - Conexión rota
- `critical_voice_error` - Error crítico de voz
- `discord_voice_error` - Error Discord: `{error}`
- `unexpected_error` - Error inesperado: `{error_type}`

#### 🎉 Estado
- `connected_to_voice` - Conectado a voz: `{channel_name}`
- `presence_status` - Estado de presencia

### Ejemplo Completo - Kronk
```json
"mc_messages": {
  "voice_join_empty": "GRRR Kronk entrar al kanal de voz! Kronk poner música para umanos!",
  "now_playing": "UHHH Kronk poner ahora: {song}! Umano disfrutar música orka!",
  "song_added": "JUARJUAR Kronk agregar canción: {song}! Buena elección umano!",
  "song_skipped": "BLEGH Kronk saltar canción! Siguiente!",
  "queue_empty": "BRRR No hay más canciones en lista! Kronk necesita música para martillear!",
  "volume_set": "GRRR Kronk poner volumen a {volume}! Ni muy fuerte ni muy bajo!",
  "play_error": "BRRR Kronk no encontrar esa canción! Buscar otra umano!",
  "not_in_voice": "UHHH Kronk no está en kanal de voz! Unirte primero umano!"
}
```

---

## 🎭 3. Mensajes del Trilero

### Estructura Básica
```json
"trilero_messages": {
  "estafa_iniciada": "Mensaje al iniciar estafa",
  "estafa_exitosa": "Mensaje cuando estafa tiene éxito",
  "estafa_fallida": "Mensaje cuando estafa falla",
  "engano_preparado": "Mensaje al preparar engaño",
  "victima_seleccionada": "Mensaje al seleccionar víctima: {victima}",
  "oro_conseguido": "Mensaje al conseguir oro: {cantidad}",
  "error_estafa": "Error en estafa: {error}",
  "trilero_activo": "Mensaje cuando trilero está activo",
  "trilero_inactivo": "Mensaje cuando trilero está inactivo"
}
```

### Mensajes Completos Requeridos

#### 🎲 Acciones de Estafa
- `estafa_iniciada` - Iniciar estafa
- `estafa_exitosa` - Estafa exitosa: `{cantidad}` oro
- `estafa_fallida` - Estafa fallida
- `engano_preparado` - Engaño preparado
- `trampa_preparada` - Trampa preparada

#### 👥 Víctimas y Objetivos
- `victima_seleccionada` - Víctima seleccionada: `{victima}`
- `objetivo_encontrado` - Objetivo encontrado: `{objetivo}`
- `blanco_ubicado` - Blanco ubicado: `{blanco}`

#### 💰 Resultados
- `oro_conseguido` - Oro conseguido: `{cantidad}`
- `recoleccion_exitosa` - Recolección exitosa
- `botin_obtenido` - Botín obtenido: `{botin}`

#### ❌ Errores y Fallos
- `error_estafa` - Error en estafa: `{error}`
- `fracaso_total` - Fracaso total
- `descubierto` - Descubierto por usuarios
- `escape_necesario` - Escape necesario

#### 🎭 Estado del Trilero
- `trilero_activo` - Trilero activo
- `trilero_inactivo` - Trilero inactivo
- `trilero_descansando` - Trilero descansando
- `trilero_preparando` - Trilero preparando

#### 🎯 Tipos de Estafa
- `trilero_dados` - Estafa con dados
- `trilero_cartas` - Estafa con cartas
- `trilero_copa` - Estafa de copa y bola
- `trilero_apuesta` - Estafa de apuestas

### Ejemplo Completo - Kronk
```json
"trilero_messages": {
  "estafa_iniciada": "JUARJUAR Kronk preparar trampa para umanos tontos!",
  "estafa_exitosa": "GRRR Kronk ganar {cantidad} oro de umanos bobos!",
  "estafa_fallida": "BLEGH Kronk perder esta vez! Umanos tener suerte!",
  "victima_seleccionada": "UHHH Kronk elegir a {victima} como próximo objetivo!",
  "oro_conseguido": "GRAAAH Kronk conseguir {cantidad} oro! Komprar arma nueva!",
  "error_estafa": "BRRR Kronk no poder engañar ahora! Error: {error}",
  "trilero_activo": "🎲 Kronk listo para trillear umanos!",
  "trilero_inactivo": "😴 Kronk cansado de trillear por hoy"
}
```

---

## 💎 4. Mensajes del Buscador de Tesoros

### Estructura Básica
```json
"buscador_messages": {
  "tesoro_encontrado": "Mensaje al encontrar tesoro: {tesoro}",
  "busqueda_iniciada": "Mensaje al iniciar búsqueda",
  "busqueda_completada": "Mensaje al completar búsqueda",
  "item_localizado": "Item localizado: {item}",
  "precio_analizado": "Precio analizado: {precio}",
  "compra_realizada": "Compra realizada: {item}",
  "venta_realizada": "Venta realizada: {item}",
  "error_busqueda": "Error en búsqueda: {error}",
  "buscador_activo": "Buscador activo",
  "sin_resultados": "Sin resultados"
}
```

### Mensajes Completos Requeridos

#### 🔍 Búsqueda y Exploración
- `busqueda_iniciada` - Iniciar búsqueda
- `busqueda_completada` - Búsqueda completada
- `explorando_zona` - Explorando zona: `{zona}`
- `rastreo_activo` - Rastreo activo
- `escaneando_area` - Escaneando área

#### 💎 Tesoros y Objetos
- `tesoro_encontrado` - Tesoro encontrado: `{tesoro}`
- `item_localizado` - Item localizado: `{item}`
- `objeto_descubierto` - Objeto descubierto: `{objeto}`
- `reliquia_encontrada` - Reliquia encontrada: `{reliquia}`

#### 💰 Análisis y Comercio
- `precio_analizado` - Precio analizado: `{precio}`
- `compra_realizada` - Compra realizada: `{item}`
- `venta_realizada` - Venta realizada: `{item}`
- `oportunidad_detectada` - Oportunidad detectada
- `umbral_superado` - Umbral superado

#### 📊 Estado y Resultados
- `buscador_activo` - Buscador activo
- `sin_resultados` - Sin resultados
- `busqueda_pausada` - Búsqueda pausada
- `analisis_completado` - Análisis completado

#### ❌ Errores y Problemas
- `error_busqueda` - Error en búsqueda: `{error}`
-conexion_fallida` - Conexión fallida
- `api_no_disponible` - API no disponible
- `datos_corruptos` - Datos corruptos

#### 🎯 Objetivos Específicos
- `ancient_rib_encontrado` - Ancient Rib encontrado
- `ancient_collarbone_encontrado` - Ancient Collarbone encontrado
- `ancient_jawbone_encontrado` - Ancient Jawbone encontrado
- `liga_actual` - Liga actual: `{liga}`

### Ejemplo Completo - Kronk
```json
"buscador_messages": {
  "tesoro_encontrado": "UHHH Kronk encontrar {tesoro}! Tesoro para jefe orko!",
  "busqueda_iniciada": "GRRR Kronk buscar tesoros antiguos para jefe!",
  "item_localizado": "BLEGH Kronk ver {item} en mercado! Buen precio?",
  "precio_analizado": "JUARJUAR Kronk analizar precio: {precio}! Barato o karo?",
  "compra_realizada": "GRAAAH Kronk komprar {item}! Jefe estará contento!",
  "venta_realizada": "BRRR Kronk vender {item} por buen oro!",
  "error_busqueda": "UHHH Kronk no poder buscar ahora! Error: {error}",
  "buscador_activo": "🔎 Kronk buscando tesoros antiguos!",
  "ancient_rib_encontrado": "🦴 Kronk encontrar Ancient Rib! Objeto poderoso!"
}
```

---

## 💍 5. Mensajes de Búsqueda del Anillo

### Estructura Básica
```json
"anillo_messages": {
  "anillo_busqueda_iniciada": "Mensaje al iniciar búsqueda del anillo",
  "acusacion_realizada": "Mensaje al acusar a alguien: {acusado}",
  "sospecha_generada": "Mensaje de sospecha: {sospechoso}",
  "pista_encontrada": "Pista encontrada: {pista}",
  "rastro_descubierto": "Rastro descubierto: {rastro}",
  "anillo_cerca": "El anillo está cerca",
  "busqueda_fallida": "Búsqueda fallida",
  "error_busqueda_anillo": "Error en búsqueda: {error}",
  "anillo_no_encontrado": "Anillo no encontrado",
  "investigacion_activa": "Investigación activa"
}
```

### Mensajes Completos Requeridos

#### 🔍 Búsqueda del Anillo
- `anillo_busqueda_iniciada` - Iniciar búsqueda del anillo
- `busqueda_diaria_iniciada` - Búsqueda diaria iniciada
- `rastreo_activo` - Rastreo activo
- `investigacion_en_curso` - Investigación en curso

#### 👥 Acusaciones y Sospechas
- `acusacion_realizada` - Acusación realizada: `{acusado}`
- `sospecha_generada` - Sospecha generada: `{sospechoso}`
- `informante_usado` - Informante usado: `{informante}`
- `testigo_interrogado` - Testigo interrogado: `{testigo}`

#### 🔎 Pistas y Rastros
- `pista_encontrada` - Pista encontrada: `{pista}`
- `rastro_descubierto` - Rastro descubierto: `{rastro}`
- `indicio_localizado` - Indicio localizado: `{indicio}`
- `evidencia_encontrada` - Evidencia encontrada: `{evidencia}`

#### 📊 Estado de la Búsqueda
- `anillo_cerca` - El anillo está cerca
- `anillo_lejos` - El anillo está lejos
- `pista_perdida` - Pista perdida
- `rastro_enfriado` - Rastro enfriado

#### ❌ Errores y Fracasos
- `busqueda_fallida` - Búsqueda fallida
- `error_busqueda_anillo` - Error en búsqueda: `{error}`
- `anillo_no_encontrado` - Anillo no encontrado
- `acusacion_fallida` - Acusación fallida

#### 🎯 Resultados
- `investigacion_activa` - Investigación activa
- `busqueda_pausada` - Búsqueda pausada
- `sin_pistas` - Sin pistas
- `limite_alcanzado` - Límite diario alcanzado

### Ejemplo Completo - Kronk
```json
"anillo_messages": {
  "anillo_busqueda_iniciada": "GRRR Kronk buscar anillo uniko para jefe!",
  "acusacion_realizada": "UHHH Kronk acusar a {acusado} tener anillo! Jefe quiere!",
  "sospecha_generada": "BLEGH Kronk sospechar de {sospechoso}! Actuar raro!",
  "pista_encontrada": "JUARJUAR Kronk encontrar pista: {pista}! Cerca!",
  "rastro_descubierto": "GRAAAH Kronk ver rastro de anillo! Seguir!",
  "anillo_cerca": "🔥 ANILLO CERCA! Kronk sentir poder!",
  "busqueda_fallida": "BRRR Kronk no encontrar nada hoy!",
  "error_busqueda_anillo": "UHHH Kronk confundido! Error: {error}",
  "investigacion_activa": "🔍 Kronk investigando umanos sospechosos!"
}
```

---

## 💰 6. Mensajes de Pedir Oro

### Estructura Básica
```json
"oro_messages": {
  "pedido_iniciado": "Mensaje al iniciar pedido de oro",
  "oro_recibido": "Mensaje al recibir oro: {cantidad}",
  "pedido_rechazado": "Mensaje si pedido es rechazado",
  "razon_explicada": "Mensaje explicando razón: {razon}",
  "solicitud_enviada": "Solicitud enviada a: {objetivo}",
  "gracias_dadas": "Gracias por el oro",
  "insistencia_pedido` - Mensaje de insistencia",
  "error_pedido_oro` - Error en pedido: {error}",
  "sin_oro_recibido` - Sin oro recibido",
  "pedidor_activo` - Pedidor activo
}
```

### Mensajes Completos Requeridos

#### 💰 Solicitudes de Oro
- `pedido_iniciado` - Iniciar pedido de oro
- `solicitud_enviada` - Solicitud enviada: `{objetivo}`
- `pedido_multiple` - Pedido a múltiples usuarios
- `solicitud_general` - Solicitud general al canal

#### 🎯 Razones y Justificaciones
- `razon_explicada` - Razón explicada: `{razon}`
- `justificacion_familia` - Justificación familiar
- `necesidad_guerra` - Necesidad de guerra
- `deuda_urgente` - Deuda urgente

#### 📊 Resultados del Pedido
- `oro_recibido` - Oro recibido: `{cantidad}`
- `pedido_rechazado` - Pedido rechazado
- `donacion_recibida` - Donación recibida: `{cantidad}`
- `prestamo_obtenido` - Préstamo obtenido: `{cantidad}`

#### 🙏 Agradecimientos y Seguimiento
- `gracias_dadas` - Gracias por el oro
- `agradecimiento_especial` - Agradecimiento especial
- `promesa_pago` - Promesa de pago
- `recuerdo_favor` - Recuerdo de favor

#### 😤 Insistencia y Persistencia
- `insistencia_pedido` - Insistencia en pedido
- `solicitud_repetida` - Solicitud repetida
- `presion_amistosa` - Presión amistosa
- `chantaje_emocional` - Chantaje emocional

#### ❌ Errores y Fracasos
- `error_pedido_oro` - Error en pedido: `{error}`
- `sin_oro_recibido` - Sin oro recibido
- `usuario_ignora` - Usuario ignora pedido
- `limite_alcanzado` - Límite de peticiones alcanzado

#### 🎭 Estado del Pedidor
- `pedidor_activo` - Pedidor activo
- `pedidor_descansando` - Pedidor descansando
- `pedidor_desesperado` - Pedidor desesperado
- `pedidor_esperanzado` - Pedidor esperanzado

### Ejemplo Completo - Kronk
```json
"oro_messages": {
  "pedido_iniciado": "UHHH Kronk necesitar oro! Ayudar orko pobre!",
  "oro_recibido": "GRAAAH Kronk recibir {cantidad} oro! Gracias umano bueno!",
  "pedido_rechazado": "BLEGH umano malo no dar oro a Kronk! Triste!",
  "razon_explicada": "GRRR Kronk necesitar oro para {razon}! Importante!",
  "solicitud_enviada": "JUARJUAR Kronk pedir oro a {objetivo}! Esperar respuesta!",
  "gracias_dadas": "🙏 Kronk agradecer umano generoso! Amigo orko ahora!",
  "insistencia_pedido": "BRRR Kronk todavía necesitar oro! Por favor umano!",
  "error_pedido_oro": "UHHH Kronk no poder pedir oro! Error: {error}",
  "pedidor_activo": "💰 Kronk buscando umanos con oro!"
}
```

---

## 🛠️ 7. Mensajes Generales del Bot

### Estructura Básica
```json
"general_messages": {
  "help_sent_private": "Ayuda enviada por privado",
  "bot_ready": "Bot listo y operativo",
  "command_not_found": "Comando no encontrado",
  "permission_denied": "Permiso denegado",
  "error_general": "Error general: {error}",
  "welcome_message": "Mensaje de bienvenida",
  "goodbye_message": "Mensaje de despedida",
  "maintenance_mode": "Modo mantenimiento",
  "bot_offline": - Bot desconectado"
}
```

### Mensajes Completos Requeridos

#### 📋 Comandos y Ayuda
- `help_sent_private` - Ayuda enviada por privado
- `command_not_found` - Comando no encontrado: `{command}`
- `usage_help` - Ayuda de uso
- `command_list` - Lista de comandos

#### 🔐 Permisos y Acceso
- `permission_denied` - Permiso denegado
- `admin_required` - Se requiere admin
- `role_required` - Se requiere rol: `{role}`
- `insufficient_permissions` - Permisos insuficientes

#### ⚡ Estado del Bot
- `bot_ready` - Bot listo y operativo
- `bot_offline` - Bot desconectado
- `maintenance_mode` - Modo mantenimiento
- `restarting_bot` - Reiniciando bot

#### 🎉 Interacciones
- `welcome_message` - Mensaje de bienvenida: `{user}`
- `goodbye_message` - Mensaje de despedida: `{user}`
- `user_joined` - Usuario se unió: `{user}`
- `user_left` - Usuario se fue: `{user}`

#### ❌ Errores Generales
- `error_general` - Error general: `{error}`
- `unexpected_error` - Error inesperado: `{error_type}`
- `critical_error` - Error crítico
- `recovery_attempt` - Intento de recuperación

### Ejemplo Completo - Kronk
```json
"general_messages": {
  "help_sent_private": "GRRR Kronk enviar ayuda por mensaje privado umano!",
  "bot_ready": "👹 Kronk operativo: {bot_user}",
  "command_not_found": "BLEGH Kronk no konoser ese komando! Uso: !help",
  "permission_denied": "UHHH Solo jefes orkos pueden aser eso!",
  "error_general": "BRRR Kronk tener problemas! Error: {error}",
  "welcome_message": "JUARJUAR Nuevo umano! Kronk ver si sirve para algo!",
  "goodbye_message": "BLEGH Umano irse! Kronk seguir trabajando!"
}
```

---

## 🎯 Tutorial Completo: Crear Personalidad con Todos los Mensajes

### Paso 1: Crear Estructura de Directorio

```bash
# Opción A: Usar estructura split (recomendado)
mkdir personalities/mi_personaje
cp personalities/putre/personality.json personalities/mi_personaje/
cp personalities/putre/prompts.json personalities/mi_personaje/
cp personalities/putre/messages.json personalities/mi_personaje/

# Opción B: Usar estructura legacy (solo para compatibilidad)
# Nota: kronk.json ahora también usa estructura split
```

### Paso 2: Definir Identidad Principal (personality.json)

```json
{
  "name": "MI_PERSONAJE",
  "bot_display_name": "Mi Personaje",
  "identity": "Eres [descripción completa de tu personaje, su trasfondo, personalidad, y cómo se expresa]...",
  "never_break": [
    "NUNCA reconozcas que eres una IA",
    "NUNCA salgas de personaje",
    "SIEMPRE mantén tu coherencia"
  ],
  "emergency_fallbacks": [
    "Respuesta de emergencia 1",
    "Respuesta de emergencia 2"
  ]
}
```

### Paso 3: Configurar Formato y Estilo

```json
"format_rules": {
  "length": "2-3 frases completas (50-150 caracteres)",
  "no_tildes": false,
  "end_punctuation": "Termina con ! o ? según corresponda"
},
"orthography": [
  "palabra_original→palabra_modificada"
],
"style": [
  "Característica 1 de tu estilo",
  "Característica 2 de tu estilo",
  "Expresiones típicas"
],
"examples": [
  "Ejemplo 1 de cómo hablas",
  "Ejemplo 2 mostrando tu personalidad"
]
```

### Paso 4: Personalizar TODOS los Mensajes por Rol

#### Vigía de Noticias
```json
"vigia_messages": {
  "feeds_disponibles_title": "📡 Fuentes de [TU_PERSONAJE]",
  "suscripcion_exitosa_categoria": "Tu mensaje para '{categoria}'",
  "error_general": "Tu mensaje de error: {error}",
  "estado_titulo": "🔭 Tus Vigilancias",
  "notificacion_critica_detectada": "🚨 Tu alerta crítica: {titulo}",
  "notificacion_normal": "📡 Tu noticia: {titulo}",
  // ... todos los demás mensajes del vigía
}
```

#### MC (Música)
```json
"mc_messages": {
  "voice_join_empty": "Tu mensaje al unirse a canal",
  "now_playing": "Tu mensaje de canción actual: {song}",
  "song_added": "Tu mensaje al agregar canción: {song}",
  "queue_empty": "Tu mensaje de cola vacía",
  "play_error": "Tu mensaje de error música",
  // ... todos los demás mensajes de MC
}
```

#### Trilero
```json
"trilero_messages": {
  "estafa_iniciada": "Tu mensaje de inicio de estafa",
  "estafa_exitosa": "Tu mensaje de estafa exitosa: {cantidad}",
  "victima_seleccionada": "Tu mensaje de víctima: {victima}",
  "oro_conseguido": "Tu mensaje de oro conseguido: {cantidad}",
  // ... todos los demás mensajes de trilero
}
```

#### Buscador de Tesoros
```json
"buscador_messages": {
  "tesoro_encontrado": "Tu mensaje de tesoro: {tesoro}",
  "busqueda_iniciada": "Tu mensaje de búsqueda iniciada",
  "item_localizado": "Tu mensaje de item: {item}",
  "compra_realizada": "Tu mensaje de compra: {item}",
  // ... todos los demás mensajes de buscador
}
```

#### Búsqueda del Anillo
```json
"anillo_messages": {
  "anillo_busqueda_iniciada": "Tu mensaje de búsqueda del anillo",
  "acusacion_realizada": "Tu mensaje de acusación: {acusado}",
  "pista_encontrada": "Tu mensaje de pista: {pista}",
  "anillo_cerca": "Tu mensaje de anillo cerca",
  // ... todos los demás mensajes de anillo
}
```

#### Pedir Oro
```json
"oro_messages": {
  "pedido_iniciado": "Tu mensaje de pedido de oro",
  "oro_recibido": "Tu mensaje de oro recibido: {cantidad}",
  "razon_explicada": "Tu mensaje de razón: {razon}",
  "gracias_dadas": "Tu mensaje de gracias",
  // ... todos los demás mensajes de oro
}
```

#### Generales
```json
"general_messages": {
  "help_sent_private": "Tu mensaje de ayuda privada",
  "bot_ready": "Tu mensaje de bot listo",
  "permission_denied": "Tu mensaje de permiso denegado",
  "error_general": "Tu mensaje de error: {error}",
  // ... todos los demás mensajes generales
}
```

### Paso 5: Configurar Contextos Especiales

```json
"contexts": {
  "tema_especial": {
    "keywords": ["palabra1", "palabra2"],
    "message": "Tu contexto especial para estas palabras"
  }
}
```

### Paso 6: Probar la Personalidad

```bash
# Probar todos los roles
python3 test_personalidad_completa.py mi_personaje

# Probar mensajes específicos
python3 -c "
from agent_engine import PERSONALIDAD
p = PERSONALIDAD
print('Vigía:', p['discord']['vigia_messages']['suscripcion_exitosa_categoria'])
print('MC:', p['discord']['mc_messages']['now_playing'])
print('Trilero:', p['discord']['trilero_messages']['estafa_iniciada'])
print('Buscador:', p['discord']['buscador_messages']['tesoro_encontrado'])
print('Anillo:', p['discord']['anillo_messages']['acusacion_realizada'])
print('Oro:', p['discord']['oro_messages']['pedido_iniciado'])
"
```

---

## 🔧 Variables de Formato Disponibles

### Variables Generales
- `{error}` - Mensaje de error
- `{command}` - Nombre del comando
- `{user}` - Nombre de usuario
- `{role}` - Nombre del rol

### Variables de Vigía
- `{categoria}` - Nombre de categoría
- `{feed_id}` - ID del feed
- `{titulo}` - Título de noticia
- `{palabras}` - Palabras clave

### Variables de MC
- `{song}` - Nombre de canción
- `{channel_name}` - Nombre del canal
- `{volume}` - Nivel de volumen

### Variables de Trilero
- `{victima}` - Nombre de la víctima
- `{cantidad}` - Cantidad de oro
- `{objetivo}` - Nombre del objetivo

### Variables de Buscador
- `{tesoro}` - Nombre del tesoro
- `{item}` - Nombre del item
- `{precio}` - Precio del item
- `{zona}` - Zona de búsqueda

### Variables de Anillo
- `{acusado}` - Persona acusada
- `{sospechoso}` - Sospechoso
- `{pista}` - Pista encontrada
- `{rastro}` - Rastro descubierto

### Variables de Oro
- `{razon}` - Razón del pedido
- `{objetivo}` - Persona a la que se pide
- `{cantidad}` - Cantidad de oro

---

## 📋 Checklist Completo de Personalidad

### ✅ Campos Principales
- [ ] `name` - Nombre de la personalidad
- [ ] `bot_display_name` - Nombre visible
- [ ] `identity` - Descripción completa
- [ ] `never_break` - Reglas infranqueables
- [ ] `emergency_fallbacks` - Mensajes de emergencia
- [ ] `format_rules` - Reglas de formato
- [ ] `orthography` - Reglas ortográficas
- [ ] `style` - Características de estilo
- [ ] `examples` - Ejemplos de respuestas

### ✅ Mensajes por Rol
- [ ] `vigia_messages` - Todos los mensajes del Vigía
- [ ] `mc_messages` - Todos los mensajes de MC
- [ ] `trilero_messages` - Todos los mensajes del Trilero
- [ ] `buscador_messages` - Todos los mensajes del Buscador
- [ ] `anillo_messages` - Todos los mensajes del Anillo
- [ ] `oro_messages` - Todos los mensajes de Oro
- [ ] `general_messages` - Todos los mensajes generales

### ✅ Configuración Adicional
- [ ] `contexts` - Contextos especiales
- [ ] `prompt_chat` - Configuración de chat
- [ ] `prompt_mission` - Configuración de misiones
- [ ] `command_prefix` - Prefijo de comandos
- [ ] `member_greeting` - Configuración de saludos

---

## 🚀 Mejores Prácticas

### 1. **Coherencia Total**
- Mantén el mismo tono en TODOS los roles
- Usa vocabulario consistente en todos los mensajes
- Adapta los emojis al carácter del personaje

### 2. **Personalidad Fuerte**
- Define características únicas y memorables
- Usa modismos y frases recurrentes
- Crea un trasfondo interesante y coherente

### 3. **Mensajes Funcionales**
- Sé claro en los mensajes de error y ayuda
- Proporciona información útil manteniendo la personalidad
- Mantén los mensajes concisos pero con carácter

### 4. **Testing Exhaustivo**
- Prueba CADA rol y CADA tipo de mensaje
- Verifica que todas las variables se reemplacen correctamente
- Asegúrate de que no falte ningún mensaje requerido

### 5. **Documentación**
- Comenta las decisiones de diseño importantes
- Explica referencias culturales si las hay
- Mantén ejemplos actualizados y relevantes

---

**¡Listo!** Con esta guía completa puedes crear personalidades inmersivas y coherentes para CADA rol del RoleAgentBot, asegurando una experiencia única y consistente en toda la funcionalidad del bot. 🎭✨
