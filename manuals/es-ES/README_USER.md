# RoleAgentBot — Guía de Usuario

RoleAgentBot es un compañero de Discord impulsado por personalidades. No es solo un bot de comandos — tiene un personaje, una voz, memoria de interacciones pasadas y un conjunto de capacidades especializadas que lleva a través de tu servidor. Puedes hablar con él, confiar en él para alertas automatizadas, jugar con él y configurarlo para adaptarlo a tu comunidad.

---

## Personalidades

El bot encarna una personalidad a la vez por servidor. Cada personalidad tiene un nombre único, avatar, estilo de habla y tono que da forma a cada respuesta — conversaciones, notificaciones, reacciones, todo.

Personalidades disponibles:

- **Rab** — androide futurista que puede cambiar su personalidad
- **Putre** — orco agresivo, directo y sin filtros
- **Yuki** — estilo y voz distintivos
- **Hans** — estilo y voz distintivos
- **Igorrr** — estilo y voz distintivos

Cada servidor puede tener una personalidad activa diferente. El idioma también es configurable por servidor (inglés, español, chino). Usa `!canvas` para cambiar la personalidad y el idioma de tu servidor.

El bot también **evoluciona**. Cada semana analiza silenciosamente los últimos siete días de actividad del servidor y ajusta sutilmente su personaje — no lo suficiente para sentirse como un bot diferente, pero suficiente para sentir que crece con el tiempo.

---

## Cómo Hablar con el Bot

Menciona al bot o envíale un mensaje directo.

- En un **canal del servidor**, menciónalo: `@NombreDelBot tu mensaje aquí`
- En **MDs**, escribe directamente — la experiencia es más personal y enfocada

El bot recuerda intercambios recientes y construye una imagen de cada usuario con el tiempo. No es sin estado — las interacciones repetidas se sienten más continuas y familiares.

Cuando el bot te saluda en privado (saludo de presencia, mensaje de bienvenida), verás un botón **Reply**. Al presionarlo, fijas esa sesión de MD al servidor, para que tu respuesta privada se maneje en el contexto correcto.

---

## Qué Hace el Bot por Su Cuenta

RoleAgentBot no es solo reactivo. Actúa sin ser invocado explícitamente:

- **Saludo de presencia** — te envía un MD cuando te conectas (si está activado)
- **Mensaje de bienvenida** — saluda a nuevos miembros cuando se unen al servidor (si está activado)
- **Reacciones de tabú** — reacciona a palabras configuradas en canales vigilados
- **Alertas programadas de roles** — envía notificaciones curadas basadas en roles que has configurado (noticias, seguimiento de precios, bono de banquero, etc.)
- **Comentarios** — hace comentarios breves impulsados por el personaje sobre la actividad de roles activos

Todos estos comportamientos pueden ser activados, desactivados o ajustados por administradores.

---

## Roles

Los roles son paquetes de características que extienden lo que el bot puede hacer. Cada rol se ejecuta de forma independiente, pero todos comparten la misma capa de personalidad — la salida siempre se siente como el mismo bot.

Los roles pueden gestionarse a través de la interfaz Canvas (`!canvas`) o mediante comandos.

---

### News Watcher

Un explorador de noticias personalizado. Te suscribes a temas y estableces premisas; el bot filtra artículos entrantes y entrega solo lo relevante para ti — sin volcados de feeds crudos.

Puedes navegar feeds y categorías disponibles, suscribirte a lo que te interesa y definir palabras clave o premisas que guíen el filtrado del bot. Los artículos se analizan con IA y solo aquellos que coinciden con tus preferencias te llegan. Los usuarios gestionan sus propias suscripciones, mientras que los administradores pueden configurar la entrega a nivel de canal.

---

### Scholar

Un archivero erudito que extrae conocimiento del entrenamiento previo del bot y de Wikipedia para responder a tus preguntas. Pregunta lo que quieras — el Scholar responderá con sabiduría extraída de su vasta biblioteca, usando la personalidad del bot y el recuerdo de tu relación para que la respuesta se sienta personal. Cuando el Scholar detecta un tema que se beneficia de una referencia externa, puede obtener extractos de Wikipedia para proporcionar un contexto más rico. La experiencia es como consultar a un compañero conocedor que recuerda tus interacciones pasadas y adapta sus respuestas al idioma de tu servidor.

---

### Treasure Hunter

Un vigilante de mercado para **Path of Exile 2**. Rastreas items; el bot monitorea precios en segundo plano y te notifica cuando las condiciones coinciden con tu objetivo.

Le dices al bot qué items te interesan, estableces la liga activa y configuras con qué frecuencia verifica. Cuando los precios se mueven de una manera que coincide con tus criterios, recibes una notificación. Está diseñado para jugadores que quieren estar al tanto de oportunidades sin vigilar el mercado manualmente.

---

### Trickster

Lúdico y orientado a juegos. El rol Trickster está construido para la diversión y la sorpresa, y se conecta a la economía virtual a través del rol Banker.

**Subrol de Juego de Dados**

Un juego de dados simple donde tiras tres dados contra una apuesta fija. El juego tiene reglas de pago claras: `1-1-1` gana todo el bote, mientras que otras combinaciones como tríos, escaleras y pares pagan según el sistema incorporado. El bote se comparte entre jugadores, así que las victorias se sienten más significativas. Puedes verificar tus estadísticas personales, ver el historial de tiradas recientes y ver el ranking del servidor. Los administradores pueden ajustar la apuesta predeterminada y alternar si los resultados se anuncian públicamente.

---

### Shaman

Interpretativo y místico. El rol Shaman trae un tipo diferente de interacción — simbólica, reflexiva y personal.

**Subrol de Runas Nórdicas**

Haz una pregunta. El bot lanza runas y proporciona una lectura personalizada generada por IA. Puedes elegir entre varias tiradas: `single` para una respuesta rápida, `three` para contexto pasado-presente-futuro, `cross` para una perspectiva equilibrada, o `runic_cross` para una interpretación más profunda. Cada lectura se almacena en tu historial personal, así que puedes revisar sesiones pasadas y ver cómo las runas te han guiado con el tiempo. La experiencia se siente como un ritual privado — el bot usa su personalidad y su memoria de relación para que la lectura se sienta adaptada a ti.

---

### Banker

La capa de economía virtual del bot. Rastrea saldos de oro, procesa transacciones y distribuye bonos diarios. Otros roles se conectan a él — el juego de dados de Trickster usa un bote compartido gestionado por el Banker.

**Subrol Mendigo**

El bot se acerca periódicamente a un usuario por su cuenta y pide una donación — completamente en personaje. Usa su memoria de interacciones recientes y su relación con el objetivo para personalizar la solicitud. El tono puede ir desde lúdico hasta dramático dependiendo de la personalidad. Los administradores controlan con qué frecuencia sucede esto y dónde se publican las solicitudes (MD o un canal específico). Los fondos recolectados alimentan la economía virtual, apoyando otras actividades como el juego de dados.

---

### Juggler

Un rol lúdico impulsado por un mecánica misteriosa. El bot está buscando algo (el "Anillo Único") y puede cuestionar o acusar usuarios con el tiempo.

**Subrol del Anillo**

El bot interactúa periódicamente con el servidor, construyendo sospecha y eventualmente acusando a un usuario. Lo hace a través de diálogo generado por IA — el bot puede emitir una acusación a mitad de conversación, y si el objetivo no coincide con un miembro real, reacciona con un seguimiento que mantiene la narrativa. La experiencia se desarrolla como una historia de combustión lenta: el bot hace preguntas, deja pistas y reduce la lista de sospechosos. Los administradores pueden controlar la frecuencia de estos eventos y establecer manualmente un objetivo si quieren dirigir la historia en una dirección particular.

---

### Music Controller (MC)

Reproducción de música práctica en canales de voz de Discord. Totalmente integrado — no se requiere configuración para empezar a usarlo.

Puedes pedirle al bot que reproduzca canciones o URLs, agregar pistas a una cola y ver qué viene a continuación. Maneja la reproducción de YouTube, incluida la lógica de reintento cuando el acceso está restringido. Cuando el canal de voz está vacío durante un tiempo configurado, el bot se desconecta automáticamente para mantener todo ordenado. La experiencia es sencilla: solicitas, el bot reproduce.

---

## Canvas — Configuración Interactiva

Canvas es una interfaz guiada con botones, menús desplegables y vistas estructuradas. Proporciona una forma más navegable de interactuar con el bot en comparación con comandos crudos.

Abre Canvas con `!canvas`. Si tu servidor tiene múltiples bots, puedes dirigirte a uno específico: `!canvas <nombre_bot>`.

A través de Canvas puedes:

- Navegar y configurar roles
- Gestionar configuración personal (suscripciones, preferencias)
- Administrar comportamiento a nivel de servidor (solo administradores)
- Cambiar la personalidad activa y el idioma de tu servidor

---

## Comandos Generales

Puedes acceder a un menú de ayuda que muestra todas las opciones disponibles, verificar que el bot está respondiendo y recibir esta guía directamente por MD para referencia futura. También hay un comando para ver la identidad actual del bot — qué personalidad e idioma están activos en el servidor. Para una interacción lúdica con el personaje, puedes pedirle al bot un insulto entregado en su estilo.

---

## Controles de Administrador

Los administradores tienen control adicional sobre el comportamiento del bot:

- **Personalidad e idioma** — cambiar qué personaje encarna el bot y qué idioma usa en el servidor
- **Apodo** — establecer un nombre de visualización personalizado para el bot
- **Saludos** — activar o desactivar MDs automáticos cuando los usuarios se conectan
- **Mensajes de bienvenida** — activar o desactivar saludos para nuevos miembros del servidor
- **Activación de roles** — activar o desactivar roles específicos (News Watcher, Treasure Hunter, etc.)
- **Comentarios** — controlar si el bot hace comentarios impulsados por el personaje sobre sus actividades

Estos controles están disponibles tanto a través de comandos como a través de la interfaz Canvas.

---

## Fatiga y Límites de Tasa

El bot tiene un sistema de protección incorporado para evitar el uso excesivo. Si alcanzas el límite para tu sesión (ráfaga, por hora o diario), el bot te lo hará saber con un mensaje amigable en lugar de llamar a la IA. Las primeras solicitudes del día siempre se permiten como período de gracia.

---

## Público vs. Privado

**En canales del servidor**, el bot se comporta como un actor comunitario visible. Es consciente de que está en un espacio compartido, responde a menciones y reacciona a eventos del servidor.

**En MDs**, la experiencia es más directa. Alertas, verificaciones de saldo, gestión de suscripciones y flujos de configuración personal funcionan mejor en mensajes privados.

Una regla simple: el servidor es social, los MDs son personales.

---

## Memoria y Continuidad

El bot mantiene varias capas de contexto por servidor:

- **Diálogo reciente** — la ventana de conversación actual
- **Memoria reciente** — un resumen rodante de actividad reciente, actualizado cada pocas horas
- **Memoria diaria** — una síntesis corta del día del servidor, actualizada cada 24 horas
- **Memoria de relación** — un resumen por usuario actualizado cada hora, capturando cómo el bot percibe a cada persona con el tiempo

Es por eso que el bot puede sentirse como si recuerda cosas. No recupera registros completos — lleva una imagen sintetizada que evoluciona continuamente.

---

## Términos y Licencia

Antes de usar RoleAgentBot, revisa los archivos [LICENSE](../../LICENSE) y [TERMS_OF_SERVICE.md](../../TERMS_OF_SERVICE.md).

Puntos clave:

- Gratuito para uso no comercial
- El uso comercial requiere consentimiento escrito previo
- El software está en desarrollo activo — úsalo bajo tu propio riesgo
- Destinado a usuarios adultos (18+)
- No recomendado para personas con condiciones de salud mental
- Se aplican consideraciones de privacidad a todas las conversaciones procesadas por LLM
