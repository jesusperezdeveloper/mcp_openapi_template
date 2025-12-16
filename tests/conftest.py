"""
Pytest configuration and fixtures for MCP OpenAPI Template tests.
"""

from __future__ import annotations

import os
from typing import Generator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_env() -> Generator[None, None, None]:
    """Set up test environment variables."""
    env_vars = {
        "AUTH_GATEWAY_URL": "https://test-auth-gateway.com",
        "AUTH_GATEWAY_API_KEY": "test-api-key",
        "API_BASE_URL": "https://test-api.com",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield


@pytest.fixture
def sample_openapi_spec() -> dict:
    """Sample OpenAPI specification for testing."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Test API",
            "version": "1.0.0",
        },
        "paths": {
            "/items": {
                "get": {
                    "operationId": "getItems",
                    "summary": "Get all items",
                    "responses": {
                        "200": {"description": "Success"},
                    },
                },
                "post": {
                    "operationId": "createItem",
                    "summary": "Create an item",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"},
                            },
                        },
                    },
                    "responses": {
                        "201": {"description": "Created"},
                    },
                },
            },
            "/items/{id}": {
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                ],
                "get": {
                    "operationId": "getItem",
                    "summary": "Get an item by ID",
                    "responses": {
                        "200": {"description": "Success"},
                    },
                },
                "delete": {
                    "operationId": "deleteItem",
                    "summary": "Delete an item",
                    "responses": {
                        "204": {"description": "Deleted"},
                    },
                },
            },
        },
    }


@pytest.fixture
def sample_credentials() -> dict:
    """Sample API credentials."""
    return {
        "api_key": "test-api-key-12345",
        "token": "test-token-67890",
    }
