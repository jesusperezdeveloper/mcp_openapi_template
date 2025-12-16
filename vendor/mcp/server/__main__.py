import logging
import sys

import anyio

from mcp.server.models import InitializationOptions
from mcp.server.session import ServerSession
from mcp.server.stdio import stdio_server
from mcp.types import ServerCapabilities

if not sys.warnoptions:
    import warnings

    warnings.simplefilter("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")


def get_version() -> str:
    """Get MCP version, with fallback for vendorized SDK."""
    try:
        import importlib.metadata
        return importlib.metadata.version("mcp")
    except Exception:
        return "1.0.0"


async def receive_loop(session: ServerSession):
    logger.info("Starting receive loop")
    async for message in session.incoming_messages:
        if isinstance(message, Exception):
            logger.error("Error: %s", message)
            continue

        logger.info("Received message from client: %s", message)


async def main():
    version = get_version()
    async with stdio_server() as (read_stream, write_stream):
        async with (
            ServerSession(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="mcp",
                    server_version=version,
                    capabilities=ServerCapabilities(),
                ),
            ) as session,
            write_stream,
        ):
            await receive_loop(session)


if __name__ == "__main__":
    anyio.run(main, backend="trio")
