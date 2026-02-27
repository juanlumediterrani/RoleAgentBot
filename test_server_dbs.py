#!/usr/bin/env python3
"""
Script de prueba para verificar el funcionamiento de bases de datos por servidor.
"""

import os
import sys
from pathlib import Path

# Añadir el directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))

def test_server_dbs():
    """Prueba la creación y uso de bases de datos por servidor."""
    
    print("🧪 Probando bases de datos por servidor...")
    
    # Importar después de añadir al path
    try:
        from db_utils import get_server_db_path, get_server_db_path_fallback
        from agent_db import get_db_instance
        from roles.vigia_noticias.db_role_vigia import get_vigia_db_instance
        from roles.buscador_tesoros.db_putre_poe import get_poe_db_instance
        from roles.pedir_oro.db_oro import get_oro_db_instance
        from roles.buscar_anillo.db_anillo import get_anillo_db_instance
    except ImportError as e:
        print(f"❌ Error importando módulos: {e}")
        return False
    
    # Lista de servidores de prueba
    test_servers = [
        "Putre Club",
        "Kronk Server", 
        "Otro Servidor"
    ]
    
    print(f"\n📁 Probando con servidores: {test_servers}")
    
    # Probar rutas de bases de datos
    print("\n🗂️  Probando rutas de bases de datos:")
    for server in test_servers:
        # Probar ruta principal
        path = get_server_db_path(server, "test.db")
        print(f"  📂 {server} -> {path}")
        
        # Probar fallback
        fallback_path = get_server_db_path_fallback(server, "test.db")
        print(f"  🔄 {server} fallback -> {fallback_path}")
    
    # Probar instancias de bases de datos
    print("\n🗄️  Probando instancias de bases de datos:")
    
    for server in test_servers:
        print(f"\n  🏠 Servidor: {server}")
        
        try:
            # Base de datos principal
            db = get_db_instance(server)
            print(f"    ✅ BD principal: {db.db_path}")
            
            # Base de datos del vigía
            db_vigia = get_vigia_db_instance(server)
            print(f"    ✅ BD vigía: {db_vigia.db_path}")
            
            # Base de datos POE
            db_poe = get_poe_db_instance(server, "Standard")
            print(f"    ✅ BD POE: {db_poe.db_path}")
            
            # Base de datos de oro
            db_oro = get_oro_db_instance(server)
            print(f"    ✅ BD oro: {db_oro.db_path}")
            
            # Base de datos del anillo
            db_anillo = get_anillo_db_instance(server)
            print(f"    ✅ BD anillo: {db_anillo.db_path}")
            
        except Exception as e:
            print(f"    ❌ Error creando instancias: {e}")
            return False
    
    # Probar operaciones básicas
    print("\n🔧 Probando operaciones básicas:")
    try:
        # Probar con el primer servidor
        server = test_servers[0]
        db = get_db_instance(server)
        
        # Registrar una interacción de prueba
        success = db.registrar_interaccion(
            usuario_id="123456789",
            usuario_nombre="UsuarioTest",
            tipo_interaccion="TEST",
            contexto="Mensaje de prueba",
            canal_id="987654321",
            servidor_id="111222333",
            metadata={"test": True}
        )
        
        if success:
            print(f"  ✅ Interacción registrada en {server}")
            
            # Obtener historial
            historial = db.obtener_historial_usuario("123456789")
            print(f"  📚 Historial obtenido: {len(historial)} registros")
            
        else:
            print(f"  ❌ Error registrando interacción")
            return False
            
    except Exception as e:
        print(f"  ❌ Error en operaciones: {e}")
        return False
    
    # Verificar estructura de directorios
    print("\n📁 Verificando estructura de directorios:")
    base_dir = Path(__file__).parent / "databases"
    if base_dir.exists():
        print(f"  📂 Directorio base existe: {base_dir}")
        
        for server in test_servers:
            server_dir = base_dir / server.lower().replace(' ', '_').replace('-', '_')
            if server_dir.exists():
                print(f"  ✅ Directorio de {server}: {server_dir}")
                files = list(server_dir.glob("*.db"))
                print(f"    📄 Archivos .db: {len(files)}")
                for f in files:
                    print(f"      - {f.name}")
            else:
                print(f"  ❌ Directorio de {server} no encontrado")
    else:
        print(f"  ❌ Directorio base no encontrado: {base_dir}")
    
    print("\n🎉 ¡Prueba completada!")
    return True

if __name__ == "__main__":
    success = test_server_dbs()
    sys.exit(0 if success else 1)
