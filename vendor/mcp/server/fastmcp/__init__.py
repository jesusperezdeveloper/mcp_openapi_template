"""FastMCP - A more ergonomic interface for MCP servers."""

from mcp.types import Icon

from .server import Context, FastMCP
from .utilities.types import Audio, Image

# Versión hardcodeada porque el SDK está vendorizado (no instalado via pip)
__version__ = "1.0.0"
__all__ = ["FastMCP", "Context", "Image", "Audio", "Icon"]
