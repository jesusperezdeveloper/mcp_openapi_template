# Dockerfile for MCP OpenAPI Template Server (SSE/HTTP)
#
# Architecture:
# - FastMCP natively supports SSE transport (no external proxy required)
# - Server exposes HTTP/SSE on port 8000
# - Endpoints: /sse (Server-Sent Events), /messages/ (HTTP POST)
#
# AUTHENTICATION:
# This MCP requires authentication via Auth Gateway.
# API credentials are dynamically obtained when the user
# provides their JWT via the set_auth_token() tool.
#
# Required environment variables:
# - AUTH_GATEWAY_URL: Auth Gateway URL (e.g., https://auth.example.com)
# - AUTH_GATEWAY_API_KEY: API Key for Auth Gateway
#
# Optional environment variables:
# - MCP_TRANSPORT: "sse" for HTTP/SSE mode (default in Docker)
# - MCP_HOST: Listen host (default: 0.0.0.0)
# - MCP_PORT: Listen port (default: 8000)
# - AUTH_CREDENTIALS_CACHE_TTL: Credential cache TTL in seconds (default: 3600)

FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Download OpenAPI spec if URL is configured
# This is done at build time if OPENAPI_SPEC_URL is set
ARG OPENAPI_SPEC_URL=""
RUN if [ -n "$OPENAPI_SPEC_URL" ]; then \
    python -m scripts.fetch_openapi --url "$OPENAPI_SPEC_URL" --output openapi/spec.json; \
    fi

# Environment configuration
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/vendor

# SSE transport configuration (native FastMCP)
ENV MCP_TRANSPORT=sse
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

# Exposed port
EXPOSE 8000

# Healthcheck for orchestrators
# Uses --max-time 2 because /sse is SSE and keeps connection open
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf --max-time 2 http://localhost:8000/sse > /dev/null || exit 0

# Run MCP server with SSE transport
CMD ["python", "-m", "src.server"]
