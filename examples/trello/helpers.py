"""
Helper tools amigables para Trello MCP.

Este archivo contiene herramientas de alto nivel que simplifican
las operaciones más comunes de Trello. Puedes usarlo como referencia
para crear helpers similares en tu propio MCP.

Para usar estos helpers:
1. Copia este archivo a src/helpers.py
2. Importa y registra las herramientas en server.py

Ejemplo en server.py:
    from .helpers import register_helper_tools
    register_helper_tools(mcp, _auth_params, _client, _require_auth)
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional, Union

import httpx
from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP

from src.validation import ValidationError


# =============================================================================
# Validación específica de Trello
# =============================================================================

TRELLO_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{24}$")
TRELLO_SHORTLINK_PATTERN = re.compile(r"^[a-zA-Z0-9]{8}$")

ALLOWED_LABEL_COLORS = frozenset({
    "green", "yellow", "orange", "red", "purple",
    "blue", "sky", "lime", "pink", "black",
})

VALID_POSITIONS = frozenset({"top", "bottom"})


def validate_trello_id(value: Optional[str], param_name: str = "id") -> str:
    """Valida un ID de Trello (24 hex chars) o shortLink (8 chars)."""
    if value is None:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} es requerido",
            expected="ID de Trello (24 hex) o shortLink (8 alfanuméricos)",
            received=None,
        )

    if not isinstance(value, str):
        raise ValidationError(
            param=param_name,
            message=f"{param_name} debe ser un string",
            expected="ID de Trello (24 hex) o shortLink (8 alfanuméricos)",
            received=type(value).__name__,
        )

    cleaned = value.strip()

    if TRELLO_ID_PATTERN.match(cleaned.lower()):
        return cleaned.lower()

    if TRELLO_SHORTLINK_PATTERN.match(cleaned):
        return cleaned

    raise ValidationError(
        param=param_name,
        message=f"{param_name} debe ser un ID válido de Trello o shortLink",
        expected="ID (24 caracteres hex) o shortLink (8 caracteres alfanuméricos)",
        received=value,
    )


def validate_color(color: Optional[str], param_name: str = "color") -> str:
    """Valida un color de etiqueta de Trello."""
    if color is None:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} es requerido",
            expected=f"uno de: {', '.join(sorted(ALLOWED_LABEL_COLORS))}",
            received=None,
        )

    cleaned = color.strip().lower()
    if cleaned not in ALLOWED_LABEL_COLORS:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} no es un color válido",
            expected=f"uno de: {', '.join(sorted(ALLOWED_LABEL_COLORS))}",
            received=color,
        )

    return cleaned


def validate_position(pos: Union[str, int, float, None], param_name: str = "pos") -> Union[str, int, float]:
    """Valida una posición de Trello."""
    if pos is None:
        raise ValidationError(
            param=param_name,
            message=f"{param_name} es requerido",
            expected="'top', 'bottom', o un número positivo",
            received=None,
        )

    if isinstance(pos, (int, float)):
        if pos < 0:
            raise ValidationError(
                param=param_name,
                message=f"{param_name} debe ser un número positivo",
                expected="número >= 0",
                received=str(pos),
            )
        return pos

    if isinstance(pos, str):
        cleaned = pos.strip().lower()
        if cleaned in VALID_POSITIONS:
            return cleaned
        try:
            num = float(cleaned) if "." in cleaned else int(cleaned)
            if num < 0:
                raise ValidationError(
                    param=param_name,
                    message=f"{param_name} debe ser un número positivo",
                    expected="número >= 0",
                    received=cleaned,
                )
            return num
        except ValueError:
            pass

    raise ValidationError(
        param=param_name,
        message=f"{param_name} no es una posición válida",
        expected="'top', 'bottom', o un número positivo",
        received=str(pos),
    )


def require_non_empty(value: Optional[str], param_name: str) -> str:
    """Valida que un string no esté vacío."""
    if value is None or not value.strip():
        raise ValidationError(
            param=param_name,
            message=f"{param_name} es requerido y no puede estar vacío",
            expected="string no vacío",
            received=value,
        )
    return value.strip()


# =============================================================================
# Registro de Helper Tools
# =============================================================================

def register_helper_tools(
    mcp: FastMCP,
    auth_params: Callable[[], dict[str, str]],
    client_factory: Callable[[], httpx.AsyncClient],
    require_auth: Callable[[], Any],
    default_board_id: Optional[str] = None,
) -> None:
    """
    Registra las herramientas helper de Trello en el servidor MCP.

    Args:
        mcp: Instancia de FastMCP
        auth_params: Función que retorna parámetros de autenticación
        client_factory: Función que crea un cliente HTTP
        require_auth: Función que verifica autenticación
        default_board_id: ID de board por defecto (opcional)
    """

    def _merge_auth(params: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(params or {})
        auth = auth_params()
        merged.setdefault("key", auth["key"])
        merged.setdefault("token", auth["token"])
        return merged

    # -------------------------------------------------------------------------
    # Lectura
    # -------------------------------------------------------------------------

    @mcp.tool(description="Lista los boards del usuario autenticado (id, nombre, url).")
    async def list_boards() -> list[dict[str, Any]]:
        require_auth()
        async with client_factory() as client:
            resp = await client.get("/members/me/boards", params=auth_params())
            resp.raise_for_status()
            boards = resp.json()
            return [
                {"id": b.get("id"), "name": b.get("name"), "url": b.get("url")}
                for b in boards
            ]

    @mcp.tool(description="Lista las listas de un board.")
    async def list_lists(board_id: str | None = None) -> list[dict[str, Any]]:
        require_auth()
        bid = board_id or default_board_id
        if not bid:
            raise HTTPException(
                status_code=400,
                detail="board_id es requerido (o configura default_board_id)",
            )
        validated_bid = validate_trello_id(bid, "board_id")
        async with client_factory() as client:
            resp = await client.get(f"/boards/{validated_bid}/lists", params=auth_params())
            resp.raise_for_status()
            lists = resp.json()
            return [
                {"id": lst.get("id"), "name": lst.get("name"), "closed": lst.get("closed")}
                for lst in lists
            ]

    @mcp.tool(description="Lista las tarjetas de una lista.")
    async def list_cards(list_id: str) -> list[dict[str, Any]]:
        require_auth()
        validated_list_id = validate_trello_id(list_id, "list_id")
        async with client_factory() as client:
            resp = await client.get(f"/lists/{validated_list_id}/cards", params=auth_params())
            resp.raise_for_status()
            cards = resp.json()
            return [
                {"id": c.get("id"), "name": c.get("name"), "url": c.get("url")}
                for c in cards
            ]

    # -------------------------------------------------------------------------
    # Creación
    # -------------------------------------------------------------------------

    @mcp.tool(description="Crea una tarjeta en una lista dada.")
    async def create_card(
        list_id: str,
        name: str,
        desc: str | None = None,
        pos: str = "top",
    ) -> dict[str, Any]:
        require_auth()
        validated_list_id = validate_trello_id(list_id, "list_id")
        validated_name = require_non_empty(name, "name")
        validated_pos = validate_position(pos)
        async with client_factory() as client:
            params = _merge_auth({
                "idList": validated_list_id,
                "name": validated_name,
                "pos": validated_pos,
            })
            if desc:
                params["desc"] = desc
            resp = await client.post("/cards", params=params)
            resp.raise_for_status()
            return resp.json()

    @mcp.tool(description="Crea un checklist en una tarjeta.")
    async def create_checklist(card_id: str, name: str) -> dict[str, Any]:
        require_auth()
        card = validate_trello_id(card_id, "card_id")
        checklist_name = require_non_empty(name, "name")
        async with client_factory() as client:
            resp = await client.post(
                "/checklists",
                params=_merge_auth({"idCard": card, "name": checklist_name}),
            )
            resp.raise_for_status()
            return resp.json()

    @mcp.tool(description="Crea una etiqueta en un board.")
    async def create_label(board_id: str, name: str, color: str) -> dict[str, Any]:
        require_auth()
        board = validate_trello_id(board_id, "board_id")
        label_name = require_non_empty(name, "name")
        label_color = validate_color(color)
        async with client_factory() as client:
            resp = await client.post(
                "/labels",
                params=_merge_auth({
                    "idBoard": board,
                    "name": label_name,
                    "color": label_color,
                }),
            )
            resp.raise_for_status()
            return resp.json()

    # -------------------------------------------------------------------------
    # Modificación
    # -------------------------------------------------------------------------

    @mcp.tool(description="Mueve una tarjeta a otra lista.")
    async def move_card(card_id: str, list_id: str) -> dict[str, Any]:
        require_auth()
        validated_card_id = validate_trello_id(card_id, "card_id")
        validated_list_id = validate_trello_id(list_id, "list_id")
        async with client_factory() as client:
            params = _merge_auth({"idList": validated_list_id})
            resp = await client.put(f"/cards/{validated_card_id}", params=params)
            resp.raise_for_status()
            return resp.json()

    @mcp.tool(description="Edita el nombre de una tarjeta.")
    async def update_card_name(card_id: str, new_name: str) -> dict[str, Any]:
        require_auth()
        card = validate_trello_id(card_id, "card_id")
        name = require_non_empty(new_name, "new_name")
        async with client_factory() as client:
            resp = await client.put(
                f"/cards/{card}",
                params=_merge_auth({"name": name}),
            )
            resp.raise_for_status()
            return resp.json()

    @mcp.tool(description="Edita la descripción de una tarjeta.")
    async def update_card_description(card_id: str, new_desc: str) -> dict[str, Any]:
        require_auth()
        card = validate_trello_id(card_id, "card_id")
        desc = require_non_empty(new_desc, "new_desc")
        async with client_factory() as client:
            resp = await client.put(
                f"/cards/{card}",
                params=_merge_auth({"desc": desc}),
            )
            resp.raise_for_status()
            return resp.json()

    @mcp.tool(description="Añade una etiqueta a una tarjeta.")
    async def add_label_to_card(card_id: str, label_id: str) -> dict[str, Any]:
        require_auth()
        card = validate_trello_id(card_id, "card_id")
        label = validate_trello_id(label_id, "label_id")
        async with client_factory() as client:
            resp = await client.post(
                f"/cards/{card}/idLabels",
                params=_merge_auth({"value": label}),
            )
            resp.raise_for_status()
            return resp.json()

    # -------------------------------------------------------------------------
    # Eliminación
    # -------------------------------------------------------------------------

    @mcp.tool(description="Elimina una tarjeta de Trello.")
    async def delete_card(card_id: str) -> dict[str, Any]:
        require_auth()
        card = validate_trello_id(card_id, "card_id")
        async with client_factory() as client:
            resp = await client.delete(
                f"/cards/{card}",
                params=auth_params(),
            )
            resp.raise_for_status()
            return {"deleted": True, "card_id": card}

    @mcp.tool(description="Elimina un checklist.")
    async def delete_checklist(checklist_id: str) -> dict[str, Any]:
        require_auth()
        checklist = validate_trello_id(checklist_id, "checklist_id")
        async with client_factory() as client:
            resp = await client.delete(
                f"/checklists/{checklist}",
                params=auth_params(),
            )
            resp.raise_for_status()
            return {"deleted": True, "checklist_id": checklist}
