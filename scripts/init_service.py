#!/usr/bin/env python
"""
Script de inicialización para configurar un nuevo servicio MCP.

Este script ayuda a configurar rápidamente un nuevo MCP a partir del template.

Uso:
  python -m scripts.init_service \
    --name "github" \
    --display-name "GitHub" \
    --base-url "https://api.github.com" \
    --openapi-url "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


TEMPLATE_SERVICE_YAML = '''# =============================================================================
# {display_name} MCP Configuration
# =============================================================================

service:
  name: "{name}"
  display_name: "{display_name}"
  version: "1.0.0"
  description: "MCP Server for {display_name} API"

api:
  base_url: "{base_url}"
  openapi_spec_url: "{openapi_url}"
  tool_prefix: "{name}"
  timeout: 30

auth:
  gateway_endpoint: "/credentials/{name}"
  credentials_format:
    # Adjust based on your API's authentication requirements
    - name: "api_key"
      query_param: "key"
    # Alternative: header-based auth
    # - name: "access_token"
    #   header: "Authorization"
    #   prefix: "Bearer "

validation:
  # Adjust the ID pattern for your API
  id_pattern: "^[a-zA-Z0-9_-]+$"
  id_description: "alphanumeric string with underscores and hyphens"
  max_name_length: 16384
  max_description_length: 16384

policies:
  blocked_patterns:
    # Add patterns for dangerous operations
    # - "delete_organization"
  require_confirmation:
    # Add patterns that require explicit confirmation
    # - "delete_.*"
  audit_all: false

defaults:
  # Add default values for common parameters
  # default_org_id: ""
'''

TEMPLATE_ENV = '''# =============================================================================
# Auth Gateway (REQUIRED)
# =============================================================================
AUTH_GATEWAY_URL=https://auth.example.com
AUTH_GATEWAY_API_KEY=your-api-key-here

# TTL for credential cache in seconds (optional, default: 3600 = 1 hour)
# AUTH_CREDENTIALS_CACHE_TTL=3600

# =============================================================================
# API Configuration (optional - values from service.yaml are used by default)
# =============================================================================
# API_BASE_URL={base_url}

# =============================================================================
# Server Configuration (optional - only for SSE/Docker mode)
# =============================================================================
# MCP_TRANSPORT=sse
# MCP_HOST=0.0.0.0
# MCP_PORT=8000
# LOG_FORMAT=json
'''


def create_service_yaml(
    name: str,
    display_name: str,
    base_url: str,
    openapi_url: str,
    output_dir: Path,
) -> Path:
    """Crea el archivo service.yaml."""
    content = TEMPLATE_SERVICE_YAML.format(
        name=name,
        display_name=display_name,
        base_url=base_url,
        openapi_url=openapi_url,
    )

    output_path = output_dir / "config" / "service.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    return output_path


def create_env_file(base_url: str, output_dir: Path) -> Path:
    """Crea el archivo .env."""
    content = TEMPLATE_ENV.format(base_url=base_url)

    output_path = output_dir / ".env"
    if output_path.exists():
        print(f"  ⚠ {output_path} ya existe, no se sobrescribirá")
        return output_path

    output_path.write_text(content)
    return output_path


def create_directories(output_dir: Path) -> None:
    """Crea la estructura de directorios necesaria."""
    dirs = [
        "config",
        "openapi",
        "src",
        "tests",
        "vendor",
        "docs",
    ]
    for d in dirs:
        (output_dir / d).mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inicializa un nuevo servicio MCP"
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Nombre interno del servicio (lowercase, sin espacios)",
    )
    parser.add_argument(
        "--display-name",
        required=True,
        help="Nombre para mostrar del servicio",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="URL base de la API",
    )
    parser.add_argument(
        "--openapi-url",
        default="",
        help="URL del OpenAPI spec (opcional)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        type=Path,
        help="Directorio de salida (default: directorio actual)",
    )
    parser.add_argument(
        "--download-spec",
        action="store_true",
        help="Descarga el OpenAPI spec después de la configuración",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Validar nombre
    if not args.name.replace("_", "").replace("-", "").isalnum():
        print(
            f"Error: El nombre '{args.name}' contiene caracteres inválidos.\n"
            "Use solo letras, números, guiones y guiones bajos.",
            file=sys.stderr,
        )
        return 1

    print(f"\n🚀 Inicializando {args.display_name} MCP\n")

    output_dir = args.output_dir.resolve()

    # Crear directorios
    print("📁 Creando estructura de directorios...")
    create_directories(output_dir)

    # Crear service.yaml
    print("📝 Creando config/service.yaml...")
    service_path = create_service_yaml(
        name=args.name,
        display_name=args.display_name,
        base_url=args.base_url,
        openapi_url=args.openapi_url,
        output_dir=output_dir,
    )
    print(f"  ✓ {service_path}")

    # Crear .env
    print("📝 Creando .env...")
    env_path = create_env_file(args.base_url, output_dir)
    print(f"  ✓ {env_path}")

    # Descargar spec si se solicita
    if args.download_spec and args.openapi_url:
        print("\n📥 Descargando OpenAPI spec...")
        os.chdir(output_dir)
        import subprocess
        result = subprocess.run(
            [
                sys.executable, "-m", "scripts.fetch_openapi",
                "--url", args.openapi_url,
                "--output", "openapi/spec.json",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  ✓ openapi/spec.json")
        else:
            print(f"  ⚠ Error al descargar: {result.stderr}")

    # Instrucciones finales
    print(f"""
✅ {args.display_name} MCP inicializado correctamente!

Próximos pasos:

1. Configura tus credenciales de Auth Gateway en .env:
   AUTH_GATEWAY_URL=https://tu-auth-gateway.com
   AUTH_GATEWAY_API_KEY=tu-api-key

2. Ajusta la configuración de autenticación en config/service.yaml
   según los requisitos de tu API.

3. {"" if args.download_spec else "Descarga el OpenAPI spec:"}
   {"" if args.download_spec else f"python -m scripts.fetch_openapi --url '{args.openapi_url}' --output openapi/spec.json"}

4. Ejecuta el servidor:
   PYTHONPATH=vendor python -m src.server

5. (Opcional) Añade helpers personalizados en src/helpers.py
   Usa examples/trello/helpers.py como referencia.
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
