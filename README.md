# MCP OpenAPI Template

A template for building MCP (Model Context Protocol) servers from OpenAPI specifications.

This template provides a production-ready foundation for creating MCP servers that expose any REST API with an OpenAPI specification to LLM-powered tools.

## Features

- **Dynamic Tool Generation**: Automatically creates MCP tools from OpenAPI specs
- **Auth Gateway Integration**: Centralized authentication via Auth Gateway
- **Dual Transport**: Supports both `stdio` (local) and `sse` (remote) transports
- **Configurable Validation**: Customizable ID patterns and input validation
- **Tool Policies**: Risk-based policies for blocking/logging operations
- **Docker Ready**: Production-ready Dockerfile and docker-compose

## Quick Start

### 1. Clone/Use Template

```bash
# Using GitHub template feature (recommended)
# Click "Use this template" on GitHub

# Or clone directly
git clone https://github.com/jesusperezdeveloper/mcp_openapi_template my-api-mcp
cd my-api-mcp
```

### 2. Initialize Your Service

```bash
python -m scripts.init_service \
  --name "github" \
  --display-name "GitHub" \
  --base-url "https://api.github.com" \
  --openapi-url "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"
```

### 3. Configure Auth Gateway

Edit `.env` with your Auth Gateway credentials:

```env
AUTH_GATEWAY_URL=https://your-auth-gateway.com
AUTH_GATEWAY_API_KEY=your-api-key
```

### 4. Download OpenAPI Spec

```bash
python -m scripts.fetch_openapi
```

### 5. Run the Server

```bash
# Local mode (stdio)
PYTHONPATH=vendor python -m src.server

# Remote mode (SSE)
MCP_TRANSPORT=sse PYTHONPATH=vendor python -m src.server
```

## Project Structure

```
mcp_openapi_template/
├── src/
│   ├── server.py           # Main MCP server
│   ├── config.py           # Configuration loader
│   ├── openapi_tools.py    # Dynamic tool generator
│   ├── auth_gateway.py     # Auth Gateway integration
│   ├── validation.py       # Input validation
│   └── tool_policies.py    # Risk policies
├── config/
│   ├── service.yaml        # Service configuration
│   ├── mcp.local.json      # Local MCP config
│   └── mcp.remote.json     # Remote MCP config
├── scripts/
│   ├── fetch_openapi.py    # Download OpenAPI spec
│   └── init_service.py     # Initialize new service
├── examples/
│   └── trello/             # Complete Trello example
├── openapi/                # OpenAPI specs (downloaded)
├── vendor/mcp/             # Vendorized MCP SDK
├── Dockerfile
└── docker-compose.yml
```

## Configuration

### service.yaml

The main configuration file (`config/service.yaml`) defines:

```yaml
service:
  name: "myservice"
  display_name: "My Service"

api:
  base_url: "https://api.example.com"
  openapi_spec_url: "https://api.example.com/openapi.json"
  tool_prefix: "myservice"

auth:
  gateway_endpoint: "/credentials/myservice"
  credentials_format:
    - name: "api_key"
      query_param: "key"

validation:
  id_pattern: "^[a-zA-Z0-9]+$"

policies:
  blocked_patterns:
    - "delete_organization"
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AUTH_GATEWAY_URL` | Yes | Auth Gateway URL |
| `AUTH_GATEWAY_API_KEY` | Yes | API Key for Auth Gateway |
| `API_BASE_URL` | No | Override API base URL |
| `MCP_TRANSPORT` | No | `stdio` (default) or `sse` |
| `MCP_PORT` | No | Port for SSE mode (default: 8000) |

## Authentication Flow

1. User obtains JWT from Auth Gateway (login)
2. User calls `set_auth_token(jwt)` in the MCP
3. MCP fetches API credentials from Auth Gateway
4. Credentials are cached for the session
5. User can now use all available tools

## Adding Custom Helper Tools

See `examples/trello/helpers.py` for a complete example of adding user-friendly wrapper tools.

```python
# In src/helpers.py
def register_helper_tools(mcp, auth_params, client_factory, require_auth):
    @mcp.tool(description="My custom tool")
    async def my_tool(param: str) -> dict:
        require_auth()
        # Implementation
        pass
```

## Docker Deployment

```bash
# Build with OpenAPI spec
docker build \
  --build-arg OPENAPI_SPEC_URL="https://api.example.com/openapi.json" \
  -t my-mcp .

# Run
docker run -p 8000:8000 --env-file .env my-mcp
```

## Examples

See the `examples/` directory for complete configurations:

- **Trello**: Full configuration with helper tools, validation, and policies

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
