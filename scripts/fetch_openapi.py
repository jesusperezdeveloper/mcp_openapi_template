#!/usr/bin/env python
"""
Descarga una especificación OpenAPI y opcionalmente la valida.

Uso:
  # Descargar spec (URL desde config o argumento)
  python -m scripts.fetch_openapi --output openapi/spec.json

  # Descargar desde URL específica
  python -m scripts.fetch_openapi --url https://api.example.com/openapi.json --output openapi/spec.json

  # Descargar y validar
  python -m scripts.fetch_openapi --output openapi/spec.json --validate
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


def get_spec_url_from_config() -> str | None:
    """Intenta obtener la URL del spec desde service.yaml."""
    try:
        import yaml

        config_path = Path("config/service.yaml")
        if config_path.exists():
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
                return config.get("api", {}).get("openapi_spec_url")
    except ImportError:
        pass
    except Exception:
        pass
    return None


def download(url: str, dest: Path) -> None:
    """Descarga un archivo desde una URL."""
    print(f"Descargando desde: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        data = response.read()
    dest.write_bytes(data)
    print(f"Guardado en: {dest}")


def validate_spec(path: Path) -> None:
    """Valida la especificación OpenAPI."""
    try:
        from openapi_spec_validator import validate_spec
    except ImportError as exc:
        raise SystemExit(
            "Para validar, instala openapi-spec-validator:\n"
            "  pip install openapi-spec-validator"
        ) from exc

    print(f"Validando: {path}")
    payload = json.loads(path.read_text())
    validate_spec(payload)
    print("✓ Especificación válida")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga una especificación OpenAPI"
    )
    parser.add_argument(
        "--url",
        type=str,
        help="URL del OpenAPI spec (usa config/service.yaml si no se especifica)",
    )
    parser.add_argument(
        "--output",
        default="openapi/spec.json",
        type=Path,
        help="Ruta destino del OpenAPI (default: openapi/spec.json)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Valida la especificación tras la descarga",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Obtener URL
    url = args.url or get_spec_url_from_config()
    if not url:
        print(
            "Error: No se especificó URL.\n\n"
            "Opciones:\n"
            "  1. Usa --url para especificar la URL\n"
            "  2. Configura api.openapi_spec_url en config/service.yaml\n",
            file=sys.stderr,
        )
        return 1

    # Descargar
    try:
        download(url, args.output)
    except Exception as e:
        print(f"Error al descargar: {e}", file=sys.stderr)
        return 1

    # Validar si se solicita
    if args.validate:
        try:
            validate_spec(args.output)
        except Exception as e:
            print(f"Error de validación: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
