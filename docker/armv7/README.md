# Configuración Docker ARMv7 (Raspberry Pi 32 bits)

Esta carpeta contiene los archivos Docker específicos para despliegue en arquitectura ARMv7.

## Archivos

- `Dockerfile.armv7` - Dockerfile optimizado para Raspberry Pi 32 bits
- `docker-compose.armv7.yml` - Configuración individual para ARMv7
- `docker-compose.shared.armv7.yml` - Configuración compartida para múltiples instancias

## Uso

```bash
# Para ejecutar con configuración compartida (desde raíz del proyecto)
docker compose -f docker/armv7/docker-compose.shared.armv7.yml up --build -d

# Para ejecutar instancia individual (desde raíz del proyecto)
docker compose -f docker/armv7/docker-compose.armv7.yml up --build -d
```

## Nota

Esta configuración se mantiene localmente y no se sube a GitHub (ver .gitignore).
Los archivos están ajustados para funcionar desde la subcarpeta `docker/armv7/` apuntando al directorio raíz del proyecto.
