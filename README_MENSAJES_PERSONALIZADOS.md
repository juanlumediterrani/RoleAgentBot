# 🦅 Sistema de Mensajes Personalizados del Vigía por Personalidad

## 📋 Overview

Este sistema permite que **cada personalidad** del bot (Kronk, Putre, etc.) tenga sus propios mensajes personalizados para el Vigía de Noticias, manteniendo la coherencia con el carácter de cada personaje.

## 🎭 Personalidades Disponibles

### 1. **Kronk** (`personalities/kronk.json`)
- **Estilo**: Orco herrero tosco y poco hablador
- **Características**: Usa "k" en lugar de "qu", onomatopeyas (GRRR, BLEGH, UHHH)
- **Ejemplos**:
  - ✅ Suscripción: `GRRR Kronk vigilará 'economia' para ti umano! Traer noticias de batalla!`
  - ❌ Error: `UHHH Kronk confundido! Error: {error}`
  - 📡 Título: `📡 Fuentes de Kronk`

### 2. **Putre** (`personalities/putre.json`)
- **Estilo**: Orco guerrero malhumorado y desagradable
- **Características**: Más agresivo, usa lenguaje más fuerte, insultos frecuentes
- **Ejemplos**:
  - ✅ Suscripción: `GRRR Putre vigilará 'economia' para ti umano! Traeré las peores noticias!`
  - ❌ Error: `UHHH Putre está jodido! Error: {error}`
  - 📡 Título: `📡 Fuentes de Putre`

### 3. **Vigía de Noticias** (`personalities/vigia_noticias.json`)
- **Estilo**: Águila vigilante profesional
- **Características**: Metáforas de vigilancia, tono formal pero con personalidad
- **Ejemplos**:
  - ✅ Suscripción: `🦅 He comenzado a vigilar 'economia' para ti. Mi vista aguda te mantendrá informado.`
  - ❌ Error: `🦅 Mi vista aguda se ha nublado temporalmente. Error: {error}`
  - 📡 Título: `📡 Fuentes Bajo Vigilancia`

## 🛠️ Cómo Funciona

### 1. **Estructura del Archivo de Personalidad**

Cada archivo de personalidad debe incluir la sección `vigia_messages`:

```json
{
  "name": "NOMBRE_PERSONALIDAD",
  "discord": {
    "vigia_messages": {
      "suscripcion_exitosa_categoria": "Mensaje personalizado para '{categoria}'",
      "error_general": "Mensaje de error: {error}",
      // ... más mensajes
    }
  }
}
```

### 2. **Mensajes Disponibles**

El sistema soporta los siguientes tipos de mensajes:

#### ✅ **Mensajes de Éxito**
- `suscripcion_exitosa_categoria` - Suscripción a categoría
- `suscripcion_exitosa_feed` - Suscripción a feed específico
- `suscripcion_canal_exitosa_categoria` - Canal suscrito a categoría
- `feed_agregado_exitosa` - Feed agregado exitosamente

#### ❌ **Mensajes de Error**
- `error_general` - Error genérico con variable `{error}`
- `error_suscripcion` - Error al suscribir
- `error_permisos` - Sin permisos
- `error_feed_no_encontrado` - Feed no existe
- `error_categoria_no_encontrada` - Categoría no existe

#### 📊 **Mensajes de Estado**
- `estado_titulo` - Título de suscripciones personales
- `estado_canal_titulo` - Título de suscripciones de canal
- `palabras_clave_titulo` - Título de palabras clave

#### 📝 **Mensajes de Uso**
- `uso_suscribir`, `uso_cancelar`, `uso_general` - Instrucciones de comandos
- `usage_agregar_feed` - Uso para agregar feeds
- `usage_canal_*` - Comandos de canal

#### 🚨 **Mensajes de Notificación**
- `notificacion_critica_detectada` - Noticias críticas
- `notificacion_normal` - Noticias normales

### 3. **Variables de Formato**

Los mensajes pueden incluir variables que se reemplazan automáticamente:

- `{categoria}` - Nombre de la categoría
- `{feed_id}` - ID del feed
- `{error}` - Mensaje de error específico
- `{palabras}` - Palabras clave
- `{titulo}` - Título de noticia
- `{nombre}` - Nombre del feed

## 🔄 Cambiar de Personalidad

### Método 1: Editar `agent_config.json`

```json
{
  "personality": "personalities/kronk.json"
}
```

### Método 2: Variables de Entorno

```bash
export AGENT_PERSONALITY="personalities/putre.json"
```

## 🧪 Probar el Sistema

### Script de Prueba

```bash
python3 test_personalidades_vigia.py
```

Este script prueba todas las personalidades y muestra cómo cada una tiene sus propios mensajes.

### Prueba Manual

```bash
python3 test_vigia_messages.py
```

## 📁 Archivos del Sistema

- `personalities/*.json` - Archivos de personalidad con mensajes
- `roles/vigia_noticias/vigia_messages.py` - Cargador de mensajes
- `roles/vigia_noticias/vigia_commands.py` - Comandos que usan mensajes
- `test_personalidades_vigia.py` - Script de prueba

## 🎨 Crear Nueva Personalidad

1. **Copia una personalidad existente**:
   ```bash
   cp personalities/kronk.json personalities/mi_personalidad.json
   ```

2. **Edita los campos principales**:
   ```json
   {
     "name": "MI_PERSONALIDAD",
     "identity": "Describe tu personaje...",
     "style": ["Estilo1", "Estilo2"],
     "examples": ["Ejemplo1", "Ejemplo2"]
   }
   ```

3. **Personaliza los mensajes del vigía**:
   ```json
   "vigia_messages": {
     "suscripcion_exitosa_categoria": "Tu mensaje para '{categoria}'",
     "error_general": "Tu error: {error}",
     // ... personaliza todos los mensajes
   }
   ```

4. **Prueba tu personalidad**:
   ```bash
   python3 test_personalidades_vigia.py
   ```

## 🚀 Ejemplos de Uso

### Kronk Vigilando Noticias
```
Usuario: !vigia suscribir economia
Kronk: GRRR Kronk vigilará 'economia' para ti umano! Traer noticias de batalla!
```

### Putre Vigilando Noticias
```
Usuario: !vigia feeds
Putre: 📡 Fuentes de Putre
```

### Vigía Profesional
```
Usuario: !vigia estado
Vigía: 🦅 Mis Vigilancias Activas
```

## 💡 Tips de Diseño

1. **Mantén coherencia** - Los mensajes deben reflejar la personalidad del personaje
2. **Usa emojis característicos** - Cada personalidad debe tener sus propios emojis
3. **Variables obligatorias** - Asegúrate de incluir todas las variables necesarias
4. **Longitud apropiada** - Mensajes concisos pero con personalidad
5. **Prueba exhaustivamente** - Verifica todos los mensajes antes de usar

---

**¡Listo!** Ahora cada personalidad del bot puede tener sus propios mensajes personalizados para el Vigía de Noticias, manteniendo la inmersión y coherencia del personaje. 🎭✨
