#!/usr/bin/env python3
"""
Script para demostrar cómo cada personalidad tiene sus propios mensajes del Vigía.
"""

import os
import sys
import json

# Añadir el directorio del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from roles.vigia_noticias.vigia_messages import get_message

def test_personalidad_vigia(personalidad_file, nombre):
    """Prueba los mensajes de una personalidad específica."""
    print(f"\n{'='*60}")
    print(f"🎭 Probando Personalidad: {nombre}")
    print(f"📁 Archivo: {personalidad_file}")
    print('='*60)
    
    # Temporalmente cambiar la personalidad activa
    try:
        # Leer el config actual
        with open('agent_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Guardar la personalidad original
        original_personality = config.get('personality')
        
        # Cambiar a la personalidad de prueba
        config['personality'] = personalidad_file
        
        # Escribir el config temporal
        with open('agent_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # Probar algunos mensajes clave
        mensajes_clave = [
            ('suscripcion_exitosa_categoria', {'categoria': 'economia'}),
            ('suscripcion_exitosa_feed', {'feed_id': 1, 'categoria': 'tecnologia'}),
            ('error_general', {'error': 'Conexión fallida'}),
            ('feeds_disponibles_title', {}),
            ('notificacion_critica_detectada', {'titulo': 'Guerra mundial'})
        ]
        
        print(f"\n✅ Mensajes de {nombre}:")
        for key, kwargs in mensajes_clave:
            try:
                mensaje = get_message(key, **kwargs)
                print(f"• {key}: {mensaje}")
            except Exception as e:
                print(f"• {key}: ❌ Error - {e}")
        
        # Restaurar la personalidad original
        config['personality'] = original_personality
        with open('agent_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        print(f"❌ Error probando {nombre}: {e}")

def main():
    """Función principal para probar todas las personalidades."""
    print("🦅 Prueba de Mensajes Personalizados del Vigía por Personalidad")
    
    # Personalidades disponibles
    personalidades = [
        ('personalities/kronk.json', 'Kronk'),
        ('personalities/putre.json', 'Putre')
    ]
    
    # Probar cada personalidad
    for personality_file, nombre in personalidades:
        if os.path.exists(personality_file):
            test_personalidad_vigia(personality_file, nombre)
        else:
            print(f"\n❌ No existe el archivo: {personality_file}")
    
    print(f"\n{'='*60}")
    print("🎉 ¡Prueba completada! Cada personalidad tiene sus propios mensajes.")
    print("💡 Para usar: Cambia 'personality' en agent_config.json a la personalidad deseada")

if __name__ == "__main__":
    main()
