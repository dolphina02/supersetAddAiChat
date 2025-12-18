# MCP Client for Superset AI Assistant

Streaming MCP (Model Context Protocol) Client that connects Superset with OpenRouter AI models.

## Overview

This service acts as a bridge between:
- **Superset Frontend** - AI chat interface
- **MCP Server** (FastMCP) - Provides tools for database queries, chart creation, etc.
- **OpenRouter API** - LLM provider (GPT-4o, GPT-4o-mini, etc.)

## Architecture

```
┌─────────────────┐
│ Superset UI     │
│ (AI Chat)       │
└────────┬────────┘
         │ HTTP/SSE
         ▼
┌─────────────────┐      ┌──────────────┐
│  MCP Client     │◄────►│ MCP Server   │
│  (This Service) │      │ (FastMCP)    │
└────────┬────────┘      └──────────────┘
         │
         │ OpenAI API
         ▼
┌─────────────────┐
│  OpenRouter     │
│  (LLM Provider) │
└─────────────────┘
```

## Features

- ✅ **Streaming Responses** - Real-time SSE streaming from LLM
- ✅ **Tool Execution** - Automatic MCP tool calling (agentic loop)
- ✅ **Multi-turn Conversations** - Context-aware chat history
- ✅ **Memory Management** - Automatic truncation of large tool outputs
- ✅ **Error Handling** - Graceful error recovery and reporting

## Configuration

### Environment Variables

Set in `docker/.env`:

```bash
# OpenRouter API Key (Required)
OPENROUTER_API_KEY=sk-or-v1-xxxxx

# MCP Server URL
MCP_SERVER_URL=http://superset:5008/mcp

# Default Model
DEFAULT_MODEL=openai/gpt-4o-mini

# Debug Mode
DEBUG=false
```

### Supported Models

- `openai/gpt-4o` - Most capable, higher cost
- `openai/gpt-4o-mini` - Fast and cost-effective (default)

## API Endpoints

### Health Check
```bash
GET /health
```

Returns MCP connection status.

### List Models
```bash
GET /models
```

Returns available LLM models.

### List MCP Tools
```bash
GET /mcp/tools
```

Returns available MCP tools from the server.

### Chat Completion (Streaming)
```bash
POST /chat
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "Show me sales data"}
  ],
  "model": "openai/gpt-4o-mini",
  "temperature": 0.7,
  "max_tokens": 2000
}
```

Returns Server-Sent Events (SSE) stream with:
- `type: "content"` - LLM response chunks
- `type: "tool_start"` - Tool execution started
- `type: "tool_result"` - Tool execution completed
- `type: "error"` - Error occurred
- `type: "done"` - Stream completed

## Development

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py
```

### Docker Build

```bash
# Build image
docker-compose build mcp-client

# Start service
docker-compose up -d mcp-client

# View logs
docker-compose logs -f mcp-client
```

## Troubleshooting

### 401 Unauthorized Error

**Problem:** `No cookie auth credentials found`

**Solution:** Check that `OPENROUTER_API_KEY` is set correctly in `docker/.env`

```bash
# Verify API key is loaded
docker-compose exec mcp-client printenv OPENROUTER_API_KEY
```

### MCP Connection Failed

**Problem:** `connect_tcp.failed exception=ConnectError`

**Solution:** Ensure MCP server is running and healthy

```bash
# Check MCP server
docker-compose exec superset curl http://localhost:5008/mcp

# Should return: {"jsonrpc":"2.0","id":"server-error","error":...}
```

### Service Not Starting

**Problem:** Container exits immediately

**Solution:** Check logs for errors

```bash
docker-compose logs mcp-client --tail=100
```

## Implementation Details

### Transport Protocol

Uses `streamable-http` transport to match FastMCP server:
- HTTP-based communication
- SSE for server-to-client streaming
- Compatible with FastMCP's transport layer

### Agentic Loop

Implements multi-turn tool execution:

1. Send user message to LLM
2. If LLM requests tool calls:
   - Execute tools via MCP
   - Add results to conversation
   - Send back to LLM (repeat up to 5 times)
3. Return final response

### Memory Management

Large tool outputs are automatically truncated to prevent:
- Context window overflow
- Memory bloat
- Slow response times

Max output size: 20,000 characters (~5k tokens)

## Dependencies

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `openai` - OpenAI/OpenRouter client
- `mcp` - Model Context Protocol SDK
- `httpx` - HTTP client

## License

Apache License 2.0
