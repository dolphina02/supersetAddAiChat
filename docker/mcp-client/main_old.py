#!/usr/bin/env python3
"""
MCP Client for Superset AI Assistant

This service acts as a bridge between the Superset frontend AI chat
and the Superset MCP server, using OpenRouter for LLM inference.
"""

import json
import logging
import os
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Environment variables are loaded from Docker environment

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MCP Response standardization classes
class MCPResultType(str, Enum):
    """Standard MCP result types for consistent handling"""
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"
    EMPTY = "empty"

class MCPDataType(str, Enum):
    """Standard data types returned by MCP tools"""
    LIST = "list"
    OBJECT = "object"
    TEXT = "text"
    BINARY = "binary"
    STRUCTURED = "structured"

class StandardMCPResult(BaseModel):
    """Standardized MCP result format for all servers"""
    result_type: MCPResultType
    data_type: MCPDataType
    data: Any
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    tool_name: str
    server_name: str = "superset"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    class Config:
        use_enum_values = True

app = FastAPI(title="Superset MCP Client", version="1.0.0")

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://superset:5008")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini")

logger.info(f"OpenRouter API Key configured: {'Yes' if OPENROUTER_API_KEY else 'No'}")
logger.info(f"MCP Server URL: {MCP_SERVER_URL}")
logger.info(f"Default Model: {DEFAULT_MODEL}")

class MCPServerRegistry:
    """Registry for managing multiple MCP servers"""
    
    def __init__(self):
        self.servers: Dict[str, MCPClient] = {}
        self._initialize_default_servers()
    
    def _initialize_default_servers(self):
        """Initialize default MCP servers"""
        # Superset MCP server (primary)
        self.servers["superset"] = MCPClient(MCP_SERVER_URL, "superset")
        
        # Future servers can be added here
        # Example:
        # weather_url = os.getenv("WEATHER_MCP_URL")
        # if weather_url:
        #     self.servers["weather"] = MCPClient(weather_url, "weather")
    
    def get_server(self, server_name: str) -> Optional[MCPClient]:
        """Get MCP server by name"""
        return self.servers.get(server_name)
    
    def list_servers(self) -> List[str]:
        """List all available server names"""
        return list(self.servers.keys())
    
    async def get_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get tools from all servers"""
        all_tools = {}
        for server_name, client in self.servers.items():
            try:
                tools = await client.list_tools()
                # Add server name to each tool for identification
                for tool in tools:
                    tool["_server"] = server_name
                all_tools[server_name] = tools
            except Exception as e:
                logger.error(f"Failed to get tools from server {server_name}: {e}")
                all_tools[server_name] = []
        return all_tools
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> StandardMCPResult:
        """Call a tool on a specific server"""
        server = self.get_server(server_name)
        if not server:
            return StandardMCPResult(
                result_type=MCPResultType.ERROR,
                data_type=MCPDataType.TEXT,
                data=None,
                error=f"Server '{server_name}' not found",
                tool_name=tool_name,
                server_name=server_name
            )
        
        return await server.call_tool(tool_name, arguments)

class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: Optional[List[Dict]] = None

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = DEFAULT_MODEL
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2000

class ChatResponse(BaseModel):
    response: str
    model: str
    usage: Optional[Dict] = None
    tool_calls: Optional[List[Dict]] = None

class MCPResponseNormalizer:
    """Normalizes MCP responses from different servers into a standard format"""
    
    @staticmethod
    def normalize_response(raw_result: Any, tool_name: str, server_name: str = "superset") -> StandardMCPResult:
        """
        Convert raw MCP response to standardized format
        
        Args:
            raw_result: Raw response from MCP server
            tool_name: Name of the tool that was called
            server_name: Name of the MCP server
            
        Returns:
            StandardMCPResult: Normalized response
        """
        try:
            # Handle error responses
            if isinstance(raw_result, dict) and "error" in raw_result:
                return StandardMCPResult(
                    result_type=MCPResultType.ERROR,
                    data_type=MCPDataType.TEXT,
                    data=None,
                    error=str(raw_result["error"]),
                    tool_name=tool_name,
                    server_name=server_name
                )
            
            # Handle empty responses
            if not raw_result or (isinstance(raw_result, (list, dict)) and len(raw_result) == 0):
                return StandardMCPResult(
                    result_type=MCPResultType.EMPTY,
                    data_type=MCPDataType.TEXT,
                    data=None,
                    tool_name=tool_name,
                    server_name=server_name,
                    metadata={"message": "No data found"}
                )
            
            # Determine data type and normalize
            if isinstance(raw_result, list):
                return MCPResponseNormalizer._normalize_list_response(raw_result, tool_name, server_name)
            elif isinstance(raw_result, dict):
                return MCPResponseNormalizer._normalize_dict_response(raw_result, tool_name, server_name)
            elif isinstance(raw_result, str):
                return MCPResponseNormalizer._normalize_text_response(raw_result, tool_name, server_name)
            else:
                # Fallback for other types
                return StandardMCPResult(
                    result_type=MCPResultType.SUCCESS,
                    data_type=MCPDataType.TEXT,
                    data=str(raw_result),
                    tool_name=tool_name,
                    server_name=server_name
                )
                
        except Exception as e:
            logger.error(f"Failed to normalize MCP response for {tool_name}: {e}")
            return StandardMCPResult(
                result_type=MCPResultType.ERROR,
                data_type=MCPDataType.TEXT,
                data=None,
                error=f"Normalization failed: {str(e)}",
                tool_name=tool_name,
                server_name=server_name
            )
    
    @staticmethod
    def _normalize_list_response(data: List[Any], tool_name: str, server_name: str) -> StandardMCPResult:
        """Normalize list responses"""
        metadata = {
            "count": len(data),
            "has_pagination": False  # Can be enhanced based on tool response
        }
        
        # Check if it's a large list that should be truncated for LLM
        if len(data) > 50:
            metadata["truncated"] = True
            metadata["original_count"] = len(data)
            metadata["showing_count"] = 50
            data = data[:50]  # Show first 50 items
        
        return StandardMCPResult(
            result_type=MCPResultType.SUCCESS,
            data_type=MCPDataType.LIST,
            data=data,
            metadata=metadata,
            tool_name=tool_name,
            server_name=server_name
        )
    
    @staticmethod
    def _normalize_dict_response(data: Dict[str, Any], tool_name: str, server_name: str) -> StandardMCPResult:
        """Normalize dictionary responses"""
        # Check if it's structured content (has specific fields)
        if "structuredContent" in data or "content" in data:
            return StandardMCPResult(
                result_type=MCPResultType.SUCCESS,
                data_type=MCPDataType.STRUCTURED,
                data=data,
                tool_name=tool_name,
                server_name=server_name
            )
        
        # Regular object response
        metadata = {
            "fields": list(data.keys()) if isinstance(data, dict) else [],
            "field_count": len(data) if isinstance(data, dict) else 0
        }
        
        return StandardMCPResult(
            result_type=MCPResultType.SUCCESS,
            data_type=MCPDataType.OBJECT,
            data=data,
            metadata=metadata,
            tool_name=tool_name,
            server_name=server_name
        )
    
    @staticmethod
    def _normalize_text_response(data: str, tool_name: str, server_name: str) -> StandardMCPResult:
        """Normalize text responses"""
        metadata = {
            "length": len(data),
            "is_json": False
        }
        
        # Try to parse as JSON
        try:
            json_data = json.loads(data)
            metadata["is_json"] = True
            return MCPResponseNormalizer.normalize_response(json_data, tool_name, server_name)
        except json.JSONDecodeError:
            pass
        
        return StandardMCPResult(
            result_type=MCPResultType.SUCCESS,
            data_type=MCPDataType.TEXT,
            data=data,
            metadata=metadata,
            tool_name=tool_name,
            server_name=server_name
        )

class MCPContextOptimizer:
    """Optimizes MCP results for LLM context consumption"""
    
    @staticmethod
    def optimize_for_llm(result: StandardMCPResult, max_context_size: int = 4000) -> Dict[str, Any]:
        """
        Optimize standardized MCP result for LLM consumption
        
        Args:
            result: Standardized MCP result
            max_context_size: Maximum context size in characters
            
        Returns:
            Optimized result for LLM
        """
        if result.result_type == MCPResultType.ERROR:
            return {
                "status": "error",
                "error": result.error,
                "tool": result.tool_name,
                "server": result.server_name
            }
        
        if result.result_type == MCPResultType.EMPTY:
            return {
                "status": "empty",
                "message": result.metadata.get("message", "No data found"),
                "tool": result.tool_name,
                "server": result.server_name
            }
        
        # Optimize based on data type
        if result.data_type == MCPDataType.LIST:
            return MCPContextOptimizer._optimize_list_for_llm(result, max_context_size)
        elif result.data_type == MCPDataType.OBJECT:
            return MCPContextOptimizer._optimize_object_for_llm(result, max_context_size)
        elif result.data_type == MCPDataType.STRUCTURED:
            return MCPContextOptimizer._optimize_structured_for_llm(result, max_context_size)
        else:
            return MCPContextOptimizer._optimize_text_for_llm(result, max_context_size)
    
    @staticmethod
    def _optimize_list_for_llm(result: StandardMCPResult, max_context_size: int) -> Dict[str, Any]:
        """Optimize list data for LLM"""
        data = result.data
        metadata = result.metadata
        
        optimized = {
            "status": "success",
            "type": "list",
            "count": metadata.get("count", len(data) if data else 0),
            "items": data,
            "tool": result.tool_name,
            "server": result.server_name
        }
        
        # Add truncation info if applicable
        if metadata.get("truncated"):
            optimized["truncated"] = True
            optimized["total_count"] = metadata.get("original_count")
            optimized["note"] = f"Showing first {metadata.get('showing_count')} of {metadata.get('original_count')} items"
        
        # Further truncate if still too large
        current_size = len(json.dumps(optimized))
        if current_size > max_context_size and data:
            # Reduce items further
            items_per_char = len(data) / current_size
            max_items = int(max_context_size * items_per_char * 0.8)  # 80% safety margin
            if max_items < len(data):
                optimized["items"] = data[:max_items]
                optimized["truncated"] = True
                optimized["note"] = f"Context-optimized: showing {max_items} items"
        
        return optimized
    
    @staticmethod
    def _optimize_object_for_llm(result: StandardMCPResult, max_context_size: int) -> Dict[str, Any]:
        """Optimize object data for LLM"""
        return {
            "status": "success",
            "type": "object",
            "data": result.data,
            "fields": result.metadata.get("fields", []),
            "tool": result.tool_name,
            "server": result.server_name
        }
    
    @staticmethod
    def _optimize_structured_for_llm(result: StandardMCPResult, max_context_size: int) -> Dict[str, Any]:
        """Optimize structured content for LLM"""
        data = result.data
        
        # Extract content from structured format
        if isinstance(data, dict):
            if "structuredContent" in data and data["structuredContent"]:
                content = data["structuredContent"]
            elif "content" in data and data["content"]:
                content = data["content"]
                # Extract text from content array if needed
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[0], dict) and "text" in content[0]:
                        content = content[0]["text"]
            else:
                content = data
        else:
            content = data
        
        return {
            "status": "success",
            "type": "structured",
            "content": content,
            "tool": result.tool_name,
            "server": result.server_name
        }
    
    @staticmethod
    def _optimize_text_for_llm(result: StandardMCPResult, max_context_size: int) -> Dict[str, Any]:
        """Optimize text data for LLM"""
        data = result.data
        
        # Truncate if too long
        if isinstance(data, str) and len(data) > max_context_size:
            data = data[:max_context_size - 100] + "... [truncated]"
        
        return {
            "status": "success",
            "type": "text",
            "content": data,
            "length": result.metadata.get("length", len(str(data))),
            "tool": result.tool_name,
            "server": result.server_name
        }

class MCPClient:
    """MCP Client using JSON-RPC protocol for communicating with Superset MCP server"""
    
    def __init__(self, server_url: str, server_name: str = "superset"):
        self.server_url = server_url
        self.server_name = server_name
        self.request_id = 0
    
    def _get_next_id(self) -> int:
        """Get next request ID for JSON-RPC"""
        self.request_id += 1
        return self.request_id
    
    async def _send_jsonrpc_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send JSON-RPC request to MCP server using streamable-http transport"""
        request_id = self._get_next_id()
        request_payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }
        
        # Structured logging for request
        logger.debug("MCP Request", extra={
            "request_id": request_id,
            "method": method,
            "params": params,
            "server": self.server_name,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Use /mcp endpoint for streamable-http transport
        mcp_url = f"{self.server_url}/mcp"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    mcp_url,
                    json=request_payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                
                # Handle streamable-http response format
                response_text = response.text.strip()
                
                # Structured logging for raw response
                logger.debug("MCP Raw Response", extra={
                    "request_id": request_id,
                    "method": method,
                    "server": self.server_name,
                    "response_length": len(response_text),
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "raw_response": response_text[:1000] + "..." if len(response_text) > 1000 else response_text
                })
                
                # FastMCP streamable-http response parsing
                result = None
                
                # Check Content-Type to determine parsing strategy
                content_type = response.headers.get("content-type", "").lower()
                is_event_stream = "text/event-stream" in content_type or "text/plain" in content_type
                
                logger.debug("MCP Response Format", extra={
                    "request_id": request_id,
                    "content_type": content_type,
                    "is_event_stream": is_event_stream,
                    "response_length": len(response_text)
                })
                
                if not is_event_stream:
                    # Try regular JSON first (single response)
                    try:
                        result = response.json()
                        logger.debug("MCP Regular JSON", extra={
                            "request_id": request_id,
                            "has_result": "result" in result if isinstance(result, dict) else False,
                            "has_error": "error" in result if isinstance(result, dict) else False
                        })
                    except json.JSONDecodeError:
                        # Fallback to event-stream parsing even if content-type doesn't indicate it
                        is_event_stream = True
                
                if is_event_stream or result is None:
                    # Parse Server-Sent Events format
                    json_objects = []
                    notifications = []
                    responses = []
                    
                    # Handle both "data: " prefixed lines and plain JSON lines
                    for line_num, line in enumerate(response_text.split('\n'), 1):
                        line = line.strip()
                        if not line:
                            continue
                            
                        json_line = None
                        if line.startswith("data: "):
                            json_line = line[6:]  # Remove "data: " prefix
                        elif line.startswith("{") and line.endswith("}"):
                            json_line = line  # Plain JSON line
                        
                        if json_line:
                            try:
                                json_obj = json.loads(json_line)
                                json_objects.append(json_obj)
                                
                                # Classify JSON-RPC objects
                                if "method" in json_obj and "id" not in json_obj:
                                    # Notification (has method, no id)
                                    notifications.append(json_obj)
                                    logger.debug("MCP Notification", extra={
                                        "request_id": request_id,
                                        "line_num": line_num,
                                        "method": json_obj.get("method"),
                                        "params": json_obj.get("params", {})
                                    })
                                elif "id" in json_obj:
                                    # Response (has id, may have result or error)
                                    responses.append(json_obj)
                                    logger.debug("MCP Response", extra={
                                        "request_id": request_id,
                                        "line_num": line_num,
                                        "response_id": json_obj.get("id"),
                                        "has_result": "result" in json_obj,
                                        "has_error": "error" in json_obj
                                    })
                                else:
                                    logger.debug("MCP Unknown Object", extra={
                                        "request_id": request_id,
                                        "line_num": line_num,
                                        "object_keys": list(json_obj.keys()) if isinstance(json_obj, dict) else "not_dict"
                                    })
                                    
                            except json.JSONDecodeError as e:
                                logger.debug("MCP JSON Parse Error", extra={
                                    "request_id": request_id,
                                    "line_num": line_num,
                                    "line_content": json_line[:100],
                                    "error": str(e)
                                })
                    
                    # Select the correct response using JSON-RPC ID matching
                    for response_obj in responses:
                        if response_obj.get("id") == request_id:
                            result = response_obj
                            logger.debug("MCP Response Selected", extra={
                                "request_id": request_id,
                                "response_id": response_obj.get("id"),
                                "selection_method": "exact_id_match"
                            })
                            break
                    
                    # Fallback strategies if exact ID match fails
                    if not result and responses:
                        # Use the first response with result or error
                        for response_obj in responses:
                            if "result" in response_obj or "error" in response_obj:
                                result = response_obj
                                logger.debug("MCP Response Selected", extra={
                                    "request_id": request_id,
                                    "response_id": response_obj.get("id"),
                                    "selection_method": "first_with_result_or_error"
                                })
                                break
                    
                    if not result and responses:
                        # Last resort: use the last response
                        result = responses[-1]
                        logger.debug("MCP Response Selected", extra={
                            "request_id": request_id,
                            "response_id": result.get("id"),
                            "selection_method": "last_response"
                        })
                    
                    # Log comprehensive parsing summary
                    logger.debug("MCP SSE Parsing Summary", extra={
                        "request_id": request_id,
                        "total_lines": len(response_text.split('\n')),
                        "json_objects": len(json_objects),
                        "notifications": len(notifications),
                        "responses": len(responses),
                        "result_found": result is not None,
                        "notification_methods": [n.get("method") for n in notifications]
                    })
                
                if not result:
                    error_msg = "No response from MCP server"
                    logger.warning("MCP No Response", extra={
                        "request_id": request_id,
                        "method": method,
                        "server": self.server_name,
                        "error": error_msg
                    })
                    return {"error": error_msg}
                
                # Check for JSON-RPC errors
                if "error" in result:
                    logger.warning("MCP JSON-RPC Error", extra={
                        "request_id": request_id,
                        "method": method,
                        "server": self.server_name,
                        "error": result["error"]
                    })
                    return {"error": result["error"]}
                
                # Get the actual result from JSON-RPC response
                mcp_result = result.get("result", {})
                
                # Extract content using existing logic
                extracted_result = self._extract_content(mcp_result)
                
                # Structured logging for processed response
                logger.info("MCP Response Processed", extra={
                    "request_id": request_id,
                    "method": method,
                    "server": self.server_name,
                    "success": True,
                    "result_type": type(extracted_result).__name__,
                    "has_data": bool(extracted_result)
                })
                
                return extracted_result
                
            except Exception as e:
                logger.error("MCP Request Failed", extra={
                    "request_id": request_id,
                    "method": method,
                    "server": self.server_name,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
                return {"error": f"MCP request failed: {e}"}
    
    def _extract_content(self, mcp_result: Dict[str, Any]) -> Any:
        """Extract content from MCP result using existing logic"""
        if isinstance(mcp_result, dict):
            if "structuredContent" in mcp_result and mcp_result["structuredContent"]:
                return mcp_result["structuredContent"]
            elif "content" in mcp_result and mcp_result["content"]:
                # Extract text from content array
                content = mcp_result["content"]
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[0], dict) and "text" in content[0]:
                        return content[0]["text"]
                return content
        
        # Fallback to raw result
        return mcp_result
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> StandardMCPResult:
        """Call a tool on the MCP server using JSON-RPC and return standardized result"""
        params = {
            "name": tool_name,
            "arguments": arguments
        }
        
        # Log tool call initiation
        logger.info("MCP Tool Call Started", extra={
            "tool_name": tool_name,
            "server": self.server_name,
            "arguments": arguments,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Make the JSON-RPC call
        raw_result = await self._send_jsonrpc_request("tools/call", params)
        
        # Normalize the response
        normalized_result = MCPResponseNormalizer.normalize_response(
            raw_result, tool_name, self.server_name
        )
        
        # Log the normalized result
        logger.info("MCP Tool Call Completed", extra={
            "tool_name": tool_name,
            "server": self.server_name,
            "result_type": normalized_result.result_type,
            "data_type": normalized_result.data_type,
            "success": normalized_result.result_type == MCPResultType.SUCCESS,
            "error": normalized_result.error,
            "metadata": normalized_result.metadata
        })
        
        return normalized_result
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from MCP server using JSON-RPC"""
        try:
            result = await self._send_jsonrpc_request("tools/list")
            if "error" in result:
                logger.error("MCP Tools List Error", extra={
                    "server": self.server_name,
                    "error": result["error"]
                })
                return []
            
            # MCP tools/list response format - tools should be directly in result
            if isinstance(result, dict):
                tools = result.get("tools", [])
            elif isinstance(result, list):
                tools = result
            else:
                logger.warning("MCP Tools List Unexpected Format", extra={
                    "server": self.server_name,
                    "result_type": type(result).__name__,
                    "result": str(result)[:200]
                })
                tools = []
            
            logger.info("MCP Tools Listed", extra={
                "server": self.server_name,
                "tool_count": len(tools),
                "tool_names": [tool.get('name', 'unknown') for tool in tools]
            })
            return tools
        except Exception as e:
            logger.error("MCP Tools List Failed", extra={
                "server": self.server_name,
                "error": str(e),
                "error_type": type(e).__name__
            })
            return []

class OpenRouterClient:
    """OpenRouter API client for LLM inference with function calling support"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def _convert_mcp_tool_to_openai_function(self, mcp_tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MCP tool schema to OpenAI function format"""
        return {
            "type": "function",
            "function": {
                "name": mcp_tool["name"],
                "description": mcp_tool["description"],
                "parameters": mcp_tool.get("inputSchema", {"type": "object", "properties": {}})
            }
        }
    
    async def chat_completion_with_tools(self, request: ChatRequest, tools: List[Dict[str, Any]]) -> ChatResponse:
        """Generate chat completion with function calling support"""
        if not self.api_key:
            raise HTTPException(status_code=500, detail="OpenRouter API key not configured")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:8088",
            "X-Title": "Superset AI Assistant",
            "Content-Type": "application/json"
        }
        
        # Convert MCP tools to OpenAI function format
        openai_tools = [self._convert_mcp_tool_to_openai_function(tool) for tool in tools]
        
        payload = {
            "model": request.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "tools": openai_tools,
            "tool_choice": "auto"  # Let the model decide when to use tools
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=60.0
                )
                response.raise_for_status()
                
                data = response.json()
                choice = data["choices"][0]
                message = choice["message"]
                
                # Check if the model wants to call a function
                if message.get("tool_calls"):
                    return ChatResponse(
                        response="",  # Will be filled after function execution
                        model=data["model"],
                        usage=data.get("usage"),
                        tool_calls=message["tool_calls"]
                    )
                else:
                    return ChatResponse(
                        response=message["content"],
                        model=data["model"],
                        usage=data.get("usage")
                    )
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"OpenRouter HTTP error: {e.response.status_code} - {e.response.text}")
                raise HTTPException(status_code=500, detail=f"LLM API error: {e.response.status_code}")
            except Exception as e:
                logger.error(f"OpenRouter API call failed: {e}")
                raise HTTPException(status_code=500, detail=f"LLM API call failed: {str(e)}")
    
    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """Generate chat completion using OpenRouter (fallback without tools)"""
        if not self.api_key:
            raise HTTPException(status_code=500, detail="OpenRouter API key not configured")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:8088",
            "X-Title": "Superset AI Assistant",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": request.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=60.0
                )
                response.raise_for_status()
                
                data = response.json()
                return ChatResponse(
                    response=data["choices"][0]["message"]["content"],
                    model=data["model"],
                    usage=data.get("usage")
                )
            except httpx.HTTPStatusError as e:
                logger.error(f"OpenRouter HTTP error: {e.response.status_code} - {e.response.text}")
                raise HTTPException(status_code=500, detail=f"LLM API error: {e.response.status_code}")
            except Exception as e:
                logger.error(f"OpenRouter API call failed: {e}")
                raise HTTPException(status_code=500, detail=f"LLM API call failed: {str(e)}")

# Initialize clients
mcp_registry = MCPServerRegistry()
openrouter_client = OpenRouterClient(OPENROUTER_API_KEY or "")

@app.get("/health")
async def health_check():
    """Health check endpoint with MCP server status"""
    health_status = {
        "status": "healthy",
        "mcp_client_version": "1.0.0",
        "servers": {}
    }
    
    # Check health of all MCP servers
    for server_name in mcp_registry.list_servers():
        server = mcp_registry.get_server(server_name)
        if server:
            try:
                # Try to list tools as a health check
                tools = await server.list_tools()
                health_status["servers"][server_name] = {
                    "status": "healthy",
                    "url": server.server_url,
                    "tool_count": len(tools)
                }
            except Exception as e:
                health_status["servers"][server_name] = {
                    "status": "unhealthy",
                    "url": server.server_url,
                    "error": str(e)
                }
    
    return health_status

@app.get("/debug/mcp-logs")
async def get_mcp_debug_info():
    """Debug endpoint for MCP communication logs (development only)"""
    return {
        "message": "MCP debug logs are available in application logs",
        "log_levels": {
            "DEBUG": "Raw JSON-RPC requests/responses",
            "INFO": "Tool calls and results summary",
            "WARNING": "Parsing failures and unexpected formats",
            "ERROR": "Network errors and JSON-RPC errors"
        },
        "structured_logging": True,
        "servers": mcp_registry.list_servers()
    }

@app.get("/models")
async def list_models():
    """List available models with function calling support"""
    recommended_models = [
        {
            "id": "openai/gpt-4o-mini",
            "name": "GPT-4o Mini",
            "description": "Fast and efficient with function calling support",
            "supports_functions": True,
            "cost": "Low"
        },
        {
            "id": "openai/gpt-4o",
            "name": "GPT-4o",
            "description": "Most capable model with excellent function calling",
            "supports_functions": True,
            "cost": "Medium"
        },
        {
            "id": "anthropic/claude-3.5-sonnet",
            "name": "Claude 3.5 Sonnet",
            "description": "Excellent reasoning with function calling support",
            "supports_functions": True,
            "cost": "Medium"
        },
        {
            "id": "qwen/qwen-2.5-7b-instruct",
            "name": "Qwen 2.5 7B Instruct",
            "description": "Good multilingual support (no function calling)",
            "supports_functions": False,
            "cost": "Very Low"
        }
    ]
    return {"models": recommended_models, "default": DEFAULT_MODEL}

@app.get("/mcp/tools")
async def list_mcp_tools():
    """List available MCP tools from all servers"""
    all_tools = await mcp_registry.get_all_tools()
    
    # Flatten tools for backward compatibility
    flattened_tools = []
    for server_name, tools in all_tools.items():
        flattened_tools.extend(tools)
    
    return {
        "tools": flattened_tools,
        "servers": all_tools,
        "server_names": mcp_registry.list_servers()
    }

@app.get("/mcp/servers")
async def list_mcp_servers():
    """List available MCP servers"""
    servers = []
    for server_name in mcp_registry.list_servers():
        server = mcp_registry.get_server(server_name)
        if server:
            servers.append({
                "name": server_name,
                "url": server.server_url,
                "status": "active"  # Could add health check here
            })
    
    return {"servers": servers}

@app.post("/mcp/tools/{tool_name}")
async def call_mcp_tool(tool_name: str, arguments: Dict[str, Any], server_name: str = "superset"):
    """Call a specific MCP tool and return standardized result"""
    standardized_result = await mcp_registry.call_tool(server_name, tool_name, arguments)
    
    # Convert to LLM-optimized format for API response
    optimized_result = MCPContextOptimizer.optimize_for_llm(standardized_result)
    
    return optimized_result

@app.post("/mcp/servers/{server_name}/tools/{tool_name}")
async def call_mcp_tool_on_server(server_name: str, tool_name: str, arguments: Dict[str, Any]):
    """Call a specific MCP tool on a specific server"""
    standardized_result = await mcp_registry.call_tool(server_name, tool_name, arguments)
    
    # Convert to LLM-optimized format for API response
    optimized_result = MCPContextOptimizer.optimize_for_llm(standardized_result)
    
    return optimized_result

from fastapi.responses import StreamingResponse

@app.post("/chat")
async def chat_completion_stream(request: ChatRequest):
    """Generate streaming chat completion with real-time MCP tool integration"""
    
    # Get available MCP tools from all servers
    all_tools_by_server = await mcp_registry.get_all_tools()
    mcp_tools = []
    for server_name, tools in all_tools_by_server.items():
        mcp_tools.extend(tools)
    
    logger.info("MCP Tools Available", extra={
        "total_tools": len(mcp_tools),
        "servers": list(all_tools_by_server.keys()),
        "tools_by_server": {k: len(v) for k, v in all_tools_by_server.items()}
    })
    
    # Add system message with MCP context
    system_message = ChatMessage(
        role="system",
        content="""You are a Superset AI Assistant with access to powerful MCP (Model Context Protocol) tools for data visualization and analysis.

🎯 CRITICAL: You MUST use the available tools to provide accurate, real-time data from Superset. NEVER make up or assume data.

📊 When users ask about:
- "대시보드" or "dashboard" → ALWAYS call list_dashboards first to get real dashboard data
- "차트" or "chart" → ALWAYS call list_charts first to get real chart data  
- "데이터셋" or "dataset" → ALWAYS call list_datasets first to get real dataset data
- "현재" or "목록" or "보여줘" → ALWAYS use the appropriate list tool
- Creating visualizations → use generate_chart or generate_explore_link
- SQL queries → use execute_sql
- Specific dashboard/chart info → use get_dashboard_info or get_chart_info

🔧 Available tools: """ + ", ".join([tool.get("name", "unknown") for tool in mcp_tools]) + """

💡 Best practices:
- Always call tools to get current data before responding
- Provide specific, actionable information
- Include URLs when available (dashboard_url, explore_url, etc.)
- Suggest next steps or related actions
- Be helpful and proactive

🌐 Language: Always respond in Korean when the user speaks Korean, English when they speak English."""
    )
    
    # Prepend system message if not already present
    messages = request.messages
    if not messages or messages[0].role != "system":
        messages = [system_message] + messages
    
    # Create new request with system message
    enhanced_request = ChatRequest(
        messages=messages,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )
    
    # Check if model supports function calling
    model_supports_functions = request.model in [
        "openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-3.5-turbo",
        "anthropic/claude-3.5-sonnet", "anthropic/claude-3-opus"
    ]
    
    if model_supports_functions and mcp_tools:
        # Use function calling
        response = await openrouter_client.chat_completion_with_tools(enhanced_request, mcp_tools)
        
        # If the model wants to call functions, execute them
        if response.tool_calls:
            logger.info(f"Model requested {len(response.tool_calls)} function calls")
            
            # Execute function calls with standardized processing
            function_results = []
            for tool_call in response.tool_calls:
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])
                
                logger.info("LLM Function Call", extra={
                    "function_name": function_name,
                    "arguments": function_args,
                    "tool_call_id": tool_call["id"]
                })
                
                # Determine which server to use for this tool
                # Check if tool has server information
                server_name = "superset"  # default
                for tool in mcp_tools:
                    if tool.get("name") == function_name:
                        server_name = tool.get("_server", "superset")
                        break
                
                # Call the MCP tool and get standardized result
                standardized_result = await mcp_registry.call_tool(server_name, function_name, function_args)
                
                # Optimize for LLM context
                optimized_result = MCPContextOptimizer.optimize_for_llm(standardized_result)
                
                function_results.append({
                    "tool_call_id": tool_call["id"],
                    "function_name": function_name,
                    "result": optimized_result,
                    "standardized_result": standardized_result  # Keep for logging
                })
                
                # Log the function execution result
                logger.info("LLM Function Result", extra={
                    "function_name": function_name,
                    "tool_call_id": tool_call["id"],
                    "result_type": standardized_result.result_type,
                    "data_type": standardized_result.data_type,
                    "success": standardized_result.result_type == MCPResultType.SUCCESS,
                    "optimized_size": len(json.dumps(optimized_result))
                })
            
            # Add function results to conversation and get final response
            # Convert tool_calls to proper format for OpenAI API
            assistant_message = {
                "role": "assistant", 
                "content": None,
                "tool_calls": response.tool_calls
            }
            
            # Add tool result messages with optimized content
            tool_messages = []
            for result in function_results:
                # Use the optimized result for LLM context
                optimized_content = result["result"]
                
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "content": json.dumps(optimized_content)
                })
                
                # Log context size for monitoring
                content_size = len(json.dumps(optimized_content))
                logger.debug("LLM Context Added", extra={
                    "function_name": result["function_name"],
                    "tool_call_id": result["tool_call_id"],
                    "content_size": content_size,
                    "content_preview": str(optimized_content)[:200] + "..." if content_size > 200 else str(optimized_content)
                })
            
            messages_with_results = [{"role": msg.role, "content": msg.content} for msg in messages] + [assistant_message] + tool_messages
            
            # Create payload directly for OpenAI API
            final_payload = {
                "model": request.model,
                "messages": messages_with_results,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }
            
            # Make direct API call for final response
            async with httpx.AsyncClient() as client:
                try:
                    final_response = await client.post(
                        f"{OPENROUTER_BASE_URL}/chat/completions",
                        json=final_payload,
                        headers={
                            "Authorization": f"Bearer {openrouter_client.api_key}",
                            "HTTP-Referer": "http://localhost:8088",
                            "X-Title": "Superset AI Assistant",
                            "Content-Type": "application/json"
                        },
                        timeout=60.0
                    )
                    final_response.raise_for_status()
                    
                    final_data = final_response.json()
                    return ChatResponse(
                        response=final_data["choices"][0]["message"]["content"],
                        model=final_data["model"],
                        usage=final_data.get("usage")
                    )
                except Exception as e:
                    logger.error(f"Final response API call failed: {e}")
                    return ChatResponse(
                        response=f"도구 실행 완료했지만 최종 응답 생성에 실패했습니다: {str(e)}",
                        model=request.model
                    )
        else:
            return response
    else:
        # Fallback to regular chat without function calling
        logger.info("Using fallback chat without function calling")
        return await openrouter_client.chat_completion(enhanced_request)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)