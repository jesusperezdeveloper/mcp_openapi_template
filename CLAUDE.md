# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP OpenAPI Template - A template for building MCP (Model Context Protocol) servers from OpenAPI specifications. Built with FastMCP, it provides dynamic tool generation from any OpenAPI spec.

## Development Commands

```bash
# Setup (Python 3.11 required)
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Initialize a new service
python -m scripts.init_service \
  --name "myservice" \
  --display-name "My Service" \
  --base-url "https://api.example.com" \
  --openapi-url "https://api.example.com/openapi.json"

# Download OpenAPI spec
python -m scripts.fetch_openapi

# Run server (stdio mode for local MCP clients)
PYTHONPATH=vendor python -m src.server

# Run server (SSE mode for remote deployment)
MCP_TRANSPORT=sse MCP_PORT=8000 PYTHONPATH=vendor python -m src.server

# Docker
docker build -t my-mcp .
docker run -p 8000:8000 --env-file .env my-mcp

# Linting
ruff check src/ tests/
ruff format src/ tests/

# Tests
PYTHONPATH=vendor pytest tests/ -v
```

## Architecture

### Core Components

- **src/server.py**: Main FastMCP server with authentication tools. Supports `stdio` (local) and `sse` (remote) transports.

- **src/config.py**: Configuration loader that reads from `config/service.yaml` and environment variables.

- **src/openapi_tools.py**: Dynamic tool registration from OpenAPI spec. Generates `{prefix}_{operationId}` tools for full API coverage.

- **src/auth_gateway.py**: Auth Gateway integration for obtaining API credentials dynamically via JWT.

- **src/validation.py**: Configurable input validation using patterns from `service.yaml`.

- **src/tool_policies.py**: Risk-based policies for blocking/logging operations.

- **vendor/mcp**: Vendorized MCP Python SDK. Must be in `PYTHONPATH` for imports to work.

### Configuration

The template uses a two-layer configuration:

1. **config/service.yaml**: Service-specific configuration (API URL, auth endpoint, validation patterns, policies)
2. **Environment variables**: Override YAML values and provide secrets (AUTH_GATEWAY_URL, AUTH_GATEWAY_API_KEY)

### Transport Modes

The server runs in two modes controlled by `MCP_TRANSPORT` env var:
- `stdio` (default): For local use with Claude Desktop/Cursor
- `sse`: For remote deployment, exposes `/sse` and `/messages/` endpoints

### Environment Variables

**Auth Gateway (Required):**
- `AUTH_GATEWAY_URL`: URL of the Auth Gateway
- `AUTH_GATEWAY_API_KEY`: API Key for Auth Gateway authentication

**API (Optional - uses service.yaml values):**
- `API_BASE_URL`: Override API base URL
- `OPENAPI_SPEC_PATH`: Path to OpenAPI spec (default: openapi/spec.json)

**Server (Optional):**
- `MCP_TRANSPORT`: `stdio` or `sse`
- `MCP_HOST`: Listen host (default: 0.0.0.0)
- `MCP_PORT`: Listen port (default: 8000)
- `LOG_FORMAT`: `json` or `console`

### Tool Naming Convention

OpenAPI tools follow the pattern `{prefix}_{operationId}` where prefix is configured in `service.yaml`. Example: `github_get_repos`, `trello_post_cards`.

### Key Files

- `config/service.yaml`: Main service configuration
- `config/service.example.yaml`: Configuration template with documentation
- `.env.example`: Environment variable template
- `examples/trello/`: Complete Trello MCP example

## Creating a New MCP

1. Use `init_service.py` to create initial configuration
2. Adjust `config/service.yaml` for your API's authentication requirements
3. Configure validation patterns for your API's ID format
4. Add blocked/confirmation patterns in policies section
5. (Optional) Add helper tools in `src/helpers.py` using `examples/trello/helpers.py` as reference

## Git Policy

**Do NOT perform Git operations without explicit user authorization:**
- No commits
- No push/pull
- No merge/rebase
- No checkout/branch operations

When changes are ready, inform the user and wait for their approval before any Git operation.
