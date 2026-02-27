# Configuración Docker (x86_64)

Esta carpeta contiene los archivos Docker para despliegue en arquitectura x86_64 (por defecto).

## Archivos

- `Dockerfile` - Dockerfile principal para x86_64
- `Dockerfile.base` - Imagen base con dependencias compartidas
- `docker-compose.default.yml` - Configuración individual por defecto
- `docker-compose.putre.yml` - Configuración individual para Putre
- `docker-compose.shared.yml` - Configuración compartida para múltiples instancias

## Uso

```bash
# Para ejecutar con configuración compartida (desde raíz del proyecto)
docker compose -f docker/docker-compose.shared.yml up --build -d

# Para ejecutar instancia por defecto (desde raíz del proyecto)
docker compose -f docker/docker-compose.default.yml up --build -d

# Para ejecutar instancia Putre (desde raíz del proyecto)
docker compose -f docker/docker-compose.putre.yml up --build -d
```

## Nota

Esta configuración se mantiene localmente y no se sube a GitHub (ver .gitignore).
Los archivos están ajustados para funcionar desde la subcarpeta `docker/` apuntando al directorio raíz del proyecto.
