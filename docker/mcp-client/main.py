#!/usr/bin/env python3
"""
Streaming MCP Client for Superset AI Assistant

Standard MCP Protocol Client:
- Uses MCP Python SDK (mcp) for stdio transport
- Connects to local Superset MCP Service via process pipe
- Server-Sent Events (SSE) based real-time response for frontend
- OpenRouter streaming API integration
- Agentic Loop (Multi-turn execution)
"""

import asyncio
import json
import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# OpenAI Official Client (OpenRouter Support)
from openai import AsyncOpenAI

# MCP Official Client Library
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool

# Configure structured logging
LOG_LEVEL = logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Helper to find python executable
def get_python_command() -> str:
    # Use specific python path if provided, otherwise default to "python"
    return os.getenv("SUP_PYTHON_PATH", "python")

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o")

# Global State
class GlobalState:
    session: Optional[ClientSession] = None
    exit_stack: Optional[Any] = None

state = GlobalState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the MCP Client connection"""
    logger.info("🚀 Starting MCP Client (Stdio Transport)...")
    
    python_cmd = get_python_command()
    server_params = StdioServerParameters(
        command=python_cmd,
        args=["-m", "superset.mcp_service"],
        env={
            **os.environ,
            "FASTMCP_TRANSPORT": "stdio",
            "PYTHONUNBUFFERED": "1" 
        }
    )
    
    logger.info(f"🔌 Connecting to local process: {python_cmd} -m superset.mcp_service")
    
    try:
        from contextlib import AsyncExitStack
        exit_stack = AsyncExitStack()
        
        read_stream, write_stream = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        
        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        
        await session.initialize()
        
        state.session = session
        state.exit_stack = exit_stack
        
        tools = await session.list_tools()
        logger.info(f"✅ Connected! Available tools: {len(tools.tools)}")
        
        yield
        
    except Exception as e:
        logger.error(f"❌ Failed to start MCP Client: {e}")
        raise e
    finally:
        logger.info("🛑 Shutting down MCP Client...")
        if state.exit_stack:
            await state.exit_stack.aclose()


app = FastAPI(
    title="Streaming Superset MCP Client", 
    version="2.2.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = ""
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = DEFAULT_MODEL
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2000

class StreamChunk(BaseModel):
    type: str  # "progress", "tool_start", "tool_result", "content", "error", "done"
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_result: Optional[Dict] = None
    error: Optional[str] = None
    metadata: Optional[Dict] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class StreamingOpenRouterClient:
    """OpenRouter Client using OpenAI Compatibility"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    
    def _convert_mcp_tool_to_openai_function(self, mcp_tool: Tool) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": mcp_tool.name,
                "description": mcp_tool.description,
                "parameters": mcp_tool.inputSchema
            }
        }
    
    async def stream_chat_with_tools(
        self, 
        messages: List[Dict[str, Any]], 
        tools: List[Tool], 
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[StreamChunk, None]:
        
        if not self.api_key:
            yield StreamChunk(type="error", error="OpenRouter API key not configured")
            return
        
        openai_tools = [self._convert_mcp_tool_to_openai_function(t) for t in tools] if tools else None
        
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
                "extra_headers": {
                    "HTTP-Referer": "http://localhost:8088",
                    "X-Title": "Superset AI Assistant",
                }
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"
            
            stream = await self.client.chat.completions.create(**kwargs)
            
            tool_calls = []
            
            async for chunk in stream:
                if not chunk.choices: continue
                choice = chunk.choices[0]
                delta = choice.delta
                
                if delta.content:
                    yield StreamChunk(type="content", content=delta.content)
                
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        while len(tool_calls) <= tc.index:
                            tool_calls.append({
                                "id": "", "type": "function", "function": {"name": "", "arguments": ""}
                            })
                        if tc.id: tool_calls[tc.index]["id"] = tc.id
                        if tc.function.name: tool_calls[tc.index]["function"]["name"] += tc.function.name
                        if tc.function.arguments: tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
                
                if choice.finish_reason == "tool_calls":
                    yield StreamChunk(type="tool_calls", metadata={"tool_calls": tool_calls})
                    return
                elif choice.finish_reason == "stop":
                    yield StreamChunk(type="done")
                    return
            yield StreamChunk(type="done")
                    
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            yield StreamChunk(type="error", error=str(e))

try:
    streaming_openrouter_client = StreamingOpenRouterClient(OPENROUTER_API_KEY)
except Exception as e:
    logger.error(f"Failed to initialize OpenRouter: {e}")
    streaming_openrouter_client = None

@app.get("/health")
async def health_check():
    return {"status": "healthy", "transport": "stdio", "connected": state.session is not None}

@app.get("/models")
async def list_models():
    return {
        "models": [
            {"id": "openai/gpt-4o", "name": "GPT-4o", "supports_functions": True},
            {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "supports_functions": True},
        ],
        "default": DEFAULT_MODEL
    }

@app.get("/mcp/tools")
async def list_mcp_tools():
    if not state.session:
        raise HTTPException(status_code=503, detail="MCP Session not connected")
    result = await state.session.list_tools()
    return {"tools": result.tools}

@app.post("/chat")
async def chat_completion_stream(request: ChatRequest):
    async def generate():
        if not streaming_openrouter_client or not state.session:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Services not initialized'})}\n\n"
            return
        
        try:
            # Prepare initial messages
            # Convert Pydantic models to dicts for OpenAI API
            current_messages = []
            for m in request.messages:
                msg = {"role": m.role, "content": m.content}
                if m.tool_calls: msg["tool_calls"] = m.tool_calls
                if m.tool_call_id: msg["tool_call_id"] = m.tool_call_id
                if m.name: msg["name"] = m.name
                current_messages.append(msg)
            
            # Agentic Loop
            MAX_LOOPS = 5
            loop_count = 0
            
            while loop_count < MAX_LOOPS:
                loop_count += 1
                
                # Get Tools
                try:
                    tools_result = await state.session.list_tools()
                    mcp_tools = tools_result.tools
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'error': f'Failed to list tools: {e}'})}\n\n"
                    return

                tool_calls_buffer = []
                full_content_buffer = ""
                
                # Stream Chat from LLM
                async for chunk in streaming_openrouter_client.stream_chat_with_tools(
                    current_messages, mcp_tools, request.model, request.temperature, request.max_tokens
                ):
                    def send(c): return f"data: {c.json()}\n\n"
                    
                    if chunk.type == "tool_calls":
                        tool_calls_buffer = chunk.metadata.get("tool_calls", [])
                    elif chunk.type == "content":
                        full_content_buffer += (chunk.content or "")
                        yield send(chunk)
                    elif chunk.type == "error":
                        yield send(chunk)
                        return
                    # catch 'done' or others but don't break yet
                
                # If no tool calls were generated, we are done
                if not tool_calls_buffer:
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
                    
                # If there are tool calls, we need to:
                # 1. Append Assistant Message (with tool calls) to history
                current_messages.append({
                    "role": "assistant",
                    "content": full_content_buffer,
                    "tool_calls": tool_calls_buffer
                })
                
                # 2. Execute Tools
                for tc in tool_calls_buffer:
                    fn = tc["function"]
                    name = fn["name"]
                    call_id = tc["id"]
                    
                    try:
                        args = json.loads(fn["arguments"])
                        
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': name, 'content': f'🔧 {name} 실행 중...'})}\n\n"
                        
                        # Call Tool via MCP Session
                        result = await state.session.call_tool(name, args)
                        
                        # Format content for History
                        content_str = ""
                        if result.content:
                            for c in result.content:
                                if c.type == "text": content_str += c.text
                                elif c.type == "image": content_str += "[Image]"
                        
                        # Memory Safeguard: Truncate large outputs
                        # This prevents Context Window overflow and Memory Bloat
                        MAX_CHARS = 20000 # Approx 5k tokens
                        if len(content_str) > MAX_CHARS:
                            content_str = content_str[:MAX_CHARS] + f"\n... (Truncated {len(content_str)-MAX_CHARS} chars)"

                        # Append Tool Result to History
                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": name,
                            "content": content_str
                        })
                        
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': name, 'content': f'✅ {name} 완료'})}\n\n"
                        
                    except Exception as e:
                        error_msg = f"Tool execution error: {str(e)}"
                        logger.error(error_msg)
                        
                        # Append Error to History so LLM knows it failed
                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": name,
                            "content": error_msg
                        })
                        
                        yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"
                
                # Loop continues to next iteration (LLM will see tool results and respond)
            
            if loop_count >= MAX_LOOPS:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Agent loop limit reached'})}\n\n"

        except Exception as e:
            logger.error(f"Chat error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)