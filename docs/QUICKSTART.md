# Quick Start Guide

This guide will help you create a new MCP server for your API in 5 minutes.

## Prerequisites

- Python 3.11+
- An API with OpenAPI specification
- Auth Gateway credentials (or modify auth for your needs)

## Step 1: Use the Template

### Option A: GitHub Template (Recommended)

1. Go to https://github.com/jesusperezdeveloper/mcp_openapi_template
2. Click "Use this template"
3. Create your new repository
4. Clone it locally

### Option B: Direct Clone

```bash
git clone https://github.com/jesusperezdeveloper/mcp_openapi_template my-api-mcp
cd my-api-mcp
rm -rf .git
git init
```

## Step 2: Set Up Python Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Step 3: Initialize Your Service

Run the initialization script with your API details:

```bash
python -m scripts.init_service \
  --name "myapi" \
  --display-name "My API" \
  --base-url "https://api.example.com/v1" \
  --openapi-url "https://api.example.com/openapi.json"
```

This creates:
- `config/service.yaml` with your service configuration
- `.env` with placeholder credentials

## Step 4: Configure Authentication

Edit `.env`:

```env
AUTH_GATEWAY_URL=https://your-auth-gateway.com
AUTH_GATEWAY_API_KEY=your-api-key-here
```

Edit `config/service.yaml` to match your API's authentication:

```yaml
auth:
  gateway_endpoint: "/credentials/myapi"
  credentials_format:
    # For query parameter auth (like Trello)
    - name: "api_key"
      query_param: "key"

    # For header auth (like GitHub)
    # - name: "access_token"
    #   header: "Authorization"
    #   prefix: "Bearer "
```

## Step 5: Download OpenAPI Spec

```bash
python -m scripts.fetch_openapi
```

This downloads your API's OpenAPI spec to `openapi/spec.json`.

## Step 6: Copy the MCP SDK

Copy the vendorized MCP SDK from an existing installation or download it:

```bash
# If you have another MCP project with vendor/mcp:
cp -r /path/to/other/mcp/vendor/mcp vendor/
```

## Step 7: Run the Server

```bash
# Local mode (for Claude Desktop, Cursor, etc.)
PYTHONPATH=vendor python -m src.server

# Remote mode (for deployment)
MCP_TRANSPORT=sse PYTHONPATH=vendor python -m src.server
```

## Step 8: Configure Your MCP Client

### Claude Desktop / Cursor (Local)

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "myapi": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/my-api-mcp",
      "env": {
        "PYTHONPATH": "vendor",
        "AUTH_GATEWAY_URL": "https://your-auth-gateway.com",
        "AUTH_GATEWAY_API_KEY": "your-key"
      }
    }
  }
}
```

### Remote Client (SSE)

```json
{
  "mcpServers": {
    "myapi": {
      "url": "https://your-server.com/sse"
    }
  }
}
```

## Next Steps

1. **Customize Validation**: Edit `validation.id_pattern` in `service.yaml` for your API's ID format

2. **Add Policies**: Define blocked operations and confirmation requirements in `policies` section

3. **Add Helper Tools**: Create `src/helpers.py` using `examples/trello/helpers.py` as reference

4. **Deploy**: Use Docker for production deployment

## Example: Creating a GitHub MCP

```bash
# Initialize
python -m scripts.init_service \
  --name "github" \
  --display-name "GitHub" \
  --base-url "https://api.github.com" \
  --openapi-url "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"

# Configure auth for Bearer token
# Edit config/service.yaml:
# auth:
#   credentials_format:
#     - name: "access_token"
#       header: "Authorization"
#       prefix: "token "

# Download spec
python -m scripts.fetch_openapi

# Run
PYTHONPATH=vendor python -m src.server
```

## Troubleshooting

### "AUTH_GATEWAY_URL not configured"

Make sure `.env` file exists and contains `AUTH_GATEWAY_URL`.

### "OpenAPI spec not found"

Run `python -m scripts.fetch_openapi` to download the spec.

### "Module mcp not found"

Ensure `vendor/mcp` exists and `PYTHONPATH=vendor` is set.
