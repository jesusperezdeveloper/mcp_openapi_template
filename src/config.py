"""
Módulo de configuración centralizada para el MCP.

Carga la configuración desde:
1. config/service.yaml - Configuración del servicio
2. Variables de entorno - Sobreescriben valores del YAML
3. .env file - Variables de entorno locales

Orden de precedencia (mayor a menor):
1. Variables de entorno
2. service.yaml
3. Valores por defecto
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

# Cargar .env
load_dotenv()


@dataclass
class ServiceConfig:
    """Configuración del servicio."""
    name: str = "myservice"
    display_name: str = "My Service"
    version: str = "1.0.0"
    description: str = "MCP Server"


@dataclass
class APIConfig:
    """Configuración de la API."""
    base_url: str = ""
    openapi_spec_url: str = ""
    tool_prefix: str = "api"
    timeout: float = 30.0


@dataclass
class CredentialMapping:
    """Mapeo de una credencial a parámetro de API."""
    name: str
    query_param: Optional[str] = None
    header: Optional[str] = None
    prefix: str = ""


@dataclass
class AuthConfig:
    """Configuración de autenticación."""
    gateway_endpoint: str = "/credentials/myservice"
    credentials_format: list[CredentialMapping] = field(default_factory=list)


@dataclass
class ValidationConfig:
    """Configuración de validación."""
    id_pattern: str = r"^[a-zA-Z0-9_-]+$"
    id_description: str = "alphanumeric string"
    max_name_length: int = 16384
    max_description_length: int = 16384


@dataclass
class PoliciesConfig:
    """Configuración de políticas de herramientas."""
    blocked_patterns: list[str] = field(default_factory=list)
    require_confirmation: list[str] = field(default_factory=list)
    audit_all: bool = False


@dataclass
class DefaultsConfig:
    """Configuración de valores por defecto."""
    values: dict[str, str] = field(default_factory=dict)


@dataclass
class MCPConfig:
    """Configuración completa del MCP."""
    service: ServiceConfig = field(default_factory=ServiceConfig)
    api: APIConfig = field(default_factory=APIConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    policies: PoliciesConfig = field(default_factory=PoliciesConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    """Carga configuración desde archivo YAML."""
    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_credentials_format(creds_list: list[dict[str, Any]]) -> list[CredentialMapping]:
    """Parsea la lista de credenciales desde YAML."""
    result = []
    for cred in creds_list:
        result.append(CredentialMapping(
            name=cred.get("name", ""),
            query_param=cred.get("query_param"),
            header=cred.get("header"),
            prefix=cred.get("prefix", ""),
        ))
    return result


def load_config(config_path: Optional[Path] = None) -> MCPConfig:
    """
    Carga la configuración del MCP.

    Args:
        config_path: Ruta al archivo service.yaml.
                    Si no se especifica, busca en config/service.yaml

    Returns:
        MCPConfig con la configuración cargada
    """
    # Determinar ruta del config
    if config_path is None:
        # Buscar en config/service.yaml relativo al directorio de trabajo
        config_path = Path("config/service.yaml")
        if not config_path.exists():
            # Buscar relativo al módulo
            config_path = Path(__file__).parent.parent / "config" / "service.yaml"

    # Cargar YAML
    yaml_config = _load_yaml_config(config_path)

    # Construir configuración con valores de YAML y env vars

    # Service
    service_yaml = yaml_config.get("service", {})
    service = ServiceConfig(
        name=os.getenv("SERVICE_NAME", service_yaml.get("name", "myservice")),
        display_name=os.getenv("SERVICE_DISPLAY_NAME", service_yaml.get("display_name", "My Service")),
        version=service_yaml.get("version", "1.0.0"),
        description=service_yaml.get("description", "MCP Server"),
    )

    # API
    api_yaml = yaml_config.get("api", {})
    api = APIConfig(
        base_url=os.getenv("API_BASE_URL", api_yaml.get("base_url", "")),
        openapi_spec_url=os.getenv("OPENAPI_SPEC_URL", api_yaml.get("openapi_spec_url", "")),
        tool_prefix=os.getenv("TOOL_PREFIX", api_yaml.get("tool_prefix", service.name)),
        timeout=float(os.getenv("API_TIMEOUT", str(api_yaml.get("timeout", 30)))),
    )

    # Auth
    auth_yaml = yaml_config.get("auth", {})
    gateway_endpoint = auth_yaml.get("gateway_endpoint", f"/credentials/{service.name}")
    auth = AuthConfig(
        gateway_endpoint=os.getenv("AUTH_GATEWAY_ENDPOINT", gateway_endpoint),
        credentials_format=_parse_credentials_format(auth_yaml.get("credentials_format", [])),
    )

    # Validation
    validation_yaml = yaml_config.get("validation", {})
    validation = ValidationConfig(
        id_pattern=validation_yaml.get("id_pattern", r"^[a-zA-Z0-9_-]+$"),
        id_description=validation_yaml.get("id_description", "alphanumeric string"),
        max_name_length=int(validation_yaml.get("max_name_length", 16384)),
        max_description_length=int(validation_yaml.get("max_description_length", 16384)),
    )

    # Policies
    policies_yaml = yaml_config.get("policies", {})
    policies = PoliciesConfig(
        blocked_patterns=policies_yaml.get("blocked_patterns", []),
        require_confirmation=policies_yaml.get("require_confirmation", []),
        audit_all=policies_yaml.get("audit_all", False),
    )

    # Defaults
    defaults_yaml = yaml_config.get("defaults", {})
    defaults = DefaultsConfig(values=defaults_yaml)

    return MCPConfig(
        service=service,
        api=api,
        auth=auth,
        validation=validation,
        policies=policies,
        defaults=defaults,
    )


# Instancia global de configuración (lazy loading)
_config: Optional[MCPConfig] = None


def get_config() -> MCPConfig:
    """Obtiene la configuración global del MCP."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Resetea la configuración (útil para testing)."""
    global _config
    _config = None
