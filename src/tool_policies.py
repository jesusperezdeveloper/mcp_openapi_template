"""
Políticas de herramientas para el MCP.

Este módulo define qué herramientas están permitidas, requieren confirmación,
o están bloqueadas por defecto. Usa la configuración de service.yaml para
determinar las políticas específicas del servicio.

Niveles de riesgo:
- LOW: Operaciones cotidianas, permitidas sin restricción
- MEDIUM: Operaciones que modifican datos, con logging
- HIGH: Operaciones destructivas reversibles, requieren confirmación
- CRITICAL: Operaciones destructivas irreversibles, bloqueadas por defecto
"""

from __future__ import annotations

import os
import re
from enum import Enum
from typing import Optional

import structlog

from .config import get_config

logger = structlog.get_logger(__name__)


class RiskLevel(Enum):
    """Niveles de riesgo para operaciones."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolAction(Enum):
    """Acciones posibles para una herramienta."""
    ALLOW = "allow"
    ALLOW_WITH_LOGGING = "log"
    REQUIRE_CONFIRMATION = "confirm"
    BLOCK = "block"


# =============================================================================
# Configuración por variables de entorno
# =============================================================================

def _get_bool_env(name: str, default: bool = False) -> bool:
    """Obtiene una variable de entorno booleana."""
    value = os.getenv(name, "").lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    return default


# Habilitar herramientas críticas (PELIGROSO - solo para desarrollo/testing)
ENABLE_CRITICAL_TOOLS = _get_bool_env("ENABLE_CRITICAL_TOOLS", False)

# Deshabilitar logging de operaciones (no recomendado en producción)
DISABLE_OPERATION_LOGGING = _get_bool_env("DISABLE_OPERATION_LOGGING", False)


# =============================================================================
# Funciones de política
# =============================================================================

def _matches_pattern(tool_name: str, patterns: list[str]) -> bool:
    """Verifica si un tool_name coincide con alguno de los patrones."""
    for pattern in patterns:
        if re.search(pattern, tool_name, re.IGNORECASE):
            return True
    return False


def is_tool_blocked(tool_name: str) -> bool:
    """
    Verifica si una herramienta está bloqueada.

    Args:
        tool_name: Nombre de la herramienta

    Returns:
        True si la herramienta está bloqueada
    """
    if ENABLE_CRITICAL_TOOLS:
        return False

    config = get_config()
    return _matches_pattern(tool_name, config.policies.blocked_patterns)


def get_tool_policy(tool_name: str) -> tuple[RiskLevel, ToolAction]:
    """
    Obtiene la política para una herramienta.

    Args:
        tool_name: Nombre de la herramienta

    Returns:
        Tupla (nivel_de_riesgo, acción)
    """
    config = get_config()

    # Verificar si está bloqueada
    if _matches_pattern(tool_name, config.policies.blocked_patterns):
        return (RiskLevel.CRITICAL, ToolAction.BLOCK)

    # Verificar si requiere confirmación
    if _matches_pattern(tool_name, config.policies.require_confirmation):
        return (RiskLevel.HIGH, ToolAction.REQUIRE_CONFIRMATION)

    # Inferir por el nombre de la operación
    tool_lower = tool_name.lower()

    # Operaciones GET son de bajo riesgo
    if "_get_" in tool_lower or tool_lower.startswith("get_"):
        return (RiskLevel.LOW, ToolAction.ALLOW)

    # Operaciones DELETE son de riesgo medio-alto
    if "_delete_" in tool_lower or tool_lower.startswith("delete_"):
        return (RiskLevel.MEDIUM, ToolAction.ALLOW_WITH_LOGGING)

    # Por defecto: riesgo bajo, permitido con logging
    return (RiskLevel.LOW, ToolAction.ALLOW_WITH_LOGGING)


def requires_confirmation(tool_name: str) -> bool:
    """
    Verifica si una herramienta requiere confirmación explícita.

    Args:
        tool_name: Nombre de la herramienta

    Returns:
        True si requiere parámetro confirm=true
    """
    config = get_config()

    if _matches_pattern(tool_name, config.policies.require_confirmation):
        return True

    _, action = get_tool_policy(tool_name)
    return action == ToolAction.REQUIRE_CONFIRMATION


def should_log_operation(tool_name: str) -> bool:
    """
    Verifica si una operación debe ser logueada.

    Args:
        tool_name: Nombre de la herramienta

    Returns:
        True si la operación debe registrarse
    """
    if DISABLE_OPERATION_LOGGING:
        return False

    config = get_config()
    if config.policies.audit_all:
        return True

    _, action = get_tool_policy(tool_name)
    return action in (
        ToolAction.ALLOW_WITH_LOGGING,
        ToolAction.REQUIRE_CONFIRMATION,
    )


def get_blocked_tools_list() -> list[str]:
    """
    Retorna la lista de patrones de herramientas bloqueadas.

    Returns:
        Lista de patrones de herramientas bloqueadas
    """
    if ENABLE_CRITICAL_TOOLS:
        return []
    config = get_config()
    return config.policies.blocked_patterns


def log_tool_execution(
    tool_name: str,
    *,
    params: Optional[dict] = None,
    result_summary: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """
    Registra la ejecución de una herramienta para auditoría.

    Args:
        tool_name: Nombre de la herramienta ejecutada
        params: Parámetros (se filtran datos sensibles)
        result_summary: Resumen del resultado
        error: Error si ocurrió
    """
    if DISABLE_OPERATION_LOGGING:
        return

    if not should_log_operation(tool_name):
        return

    risk, action = get_tool_policy(tool_name)

    safe_params = _filter_sensitive_params(params) if params else {}

    log_data = {
        "tool": tool_name,
        "risk_level": risk.value,
        "action": action.value,
        "params": safe_params,
    }

    if result_summary:
        log_data["result"] = result_summary

    if error:
        log_data["error"] = error
        logger.warning("tool_execution_failed", **log_data)
    else:
        logger.info("tool_executed", **log_data)


def _filter_sensitive_params(params: dict) -> dict:
    """
    Filtra parámetros sensibles para logging seguro.

    No registra:
    - Contenido completo de descripciones largas
    - Tokens o credenciales
    - Datos personales
    """
    SENSITIVE_KEYS = {"key", "token", "password", "secret", "credential", "api_key", "apikey"}
    TRUNCATE_KEYS = {"desc", "description", "text", "body", "content"}
    MAX_VALUE_LENGTH = 100

    filtered = {}
    for key, value in params.items():
        key_lower = key.lower()

        if any(s in key_lower for s in SENSITIVE_KEYS):
            filtered[key] = "[REDACTED]"
            continue

        if any(s in key_lower for s in TRUNCATE_KEYS):
            if isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
                filtered[key] = value[:MAX_VALUE_LENGTH] + "..."
                continue

        if isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
            filtered[key] = value[:MAX_VALUE_LENGTH] + "..."
        else:
            filtered[key] = value

    return filtered
