#!/usr/bin/env python3
"""
Streaming MCP Client for Superset AI Assistant

정식 MCP 프로토콜을 사용한 클라이언트
- MCP HTTP 클라이언트 라이브러리 사용
- Server-Sent Events (SSE) 기반 실시간 응답
- OpenRouter 스트리밍 API 연동
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# OpenAI 공식 클라이언트 (OpenRouter 지원)
from openai import AsyncOpenAI

# MCP 정식 클라이언트 라이브러리 사용
from mcp import ClientSession
from mcp.client.session import ClientSession as MCPClientSession
from mcp.types import (
    CallToolRequest,
    ListToolsRequest,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

# Configure structured logging - 로그 레벨을 WARNING으로 변경하여 불필요한 로그 줄이기
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 개발 모드에서만 상세 로깅 활성화
if os.getenv("DEBUG", "false").lower() == "true":
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.WARNING)

app = FastAPI(title="Streaming Superset MCP Client", version="2.0.0")

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://superset:5008")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini")

# 시작 시에만 기본 정보 로깅 (WARNING 레벨로 변경하여 항상 표시)
logger.warning(f"🚀 MCP Client 시작 - OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}, MCP: {MCP_SERVER_URL}, Model: {DEFAULT_MODEL}")

# Pydantic models
class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: Optional[List[Dict]] = None

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = DEFAULT_MODEL
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2000

class StreamChunk(BaseModel):
    """Standard streaming chunk format"""
    type: str  # "progress", "tool_start", "tool_result", "content", "error", "done"
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_result: Optional[Dict] = None
    error: Optional[str] = None
    metadata: Optional[Dict] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class StreamingMCPClient:
    """정식 MCP 프로토콜을 사용한 스트리밍 클라이언트"""
    
    def __init__(self, server_url: str, server_name: str = "superset"):
        self.server_url = server_url
        self.server_name = server_name
        self._session: Optional[MCPClientSession] = None
        self._tools_cache: Optional[List[Tool]] = None
        # 초기화 로그 제거 (불필요한 로그)
    
    async def _get_session(self) -> Optional[MCPClientSession]:
        """MCP 세션 생성 또는 반환 (현재는 None 반환으로 HTTP fallback 사용)"""
        # 임시로 MCP 세션 생성을 비활성화하고 HTTP fallback만 사용
        # 로그 제거 - 매번 호출될 때마다 로그가 찍히는 것을 방지
        return None
    
    async def stream_tool_execution(self, tool_name: str, arguments: Dict[str, Any]) -> AsyncGenerator[StreamChunk, None]:
        """정식 MCP 프로토콜로 도구 실행"""
        
        # 시작 알림
        yield StreamChunk(
            type="tool_start",
            tool_name=tool_name,
            content=f"🔧 Executing {tool_name}...",
            metadata={"arguments": arguments}
        )
        
        try:
            session = await self._get_session()
            
            if session:
                # 정식 MCP 프로토콜 사용
                # 로그 제거 - 도구 호출 시마다 로그가 찍히는 것을 방지
                
                # 진행 상황 알림
                yield StreamChunk(
                    type="progress",
                    tool_name=tool_name,
                    content=f"📊 Processing {tool_name} via MCP...",
                    metadata={"status": "processing"}
                )
                
                # MCP 도구 호출
                request = CallToolRequest(
                    method="tools/call",
                    params={
                        "name": tool_name,
                        "arguments": arguments
                    }
                )
                
                result = await session.call_tool(request)
                # 로그 제거 - 결과 로깅 불필요
                
                # 결과 처리
                content = self._extract_mcp_content(result)
                
                # Check if data was truncated and add appropriate messaging
                metadata = {"protocol": "mcp"}
                if isinstance(content, dict) and content.get("_truncated"):
                    metadata["data_truncated"] = True
                    metadata["truncation_info"] = {
                        "original_count": content.get("_original_count"),
                        "showing_count": content.get("_showing_count"),
                        "message": content.get("_truncation_message")
                    }
                
                yield StreamChunk(
                    type="tool_result",
                    tool_name=tool_name,
                    content=f"✅ {tool_name} completed via MCP",
                    tool_result={"content": content, "mcp_result": result},
                    metadata=metadata
                )
            else:
                # Fallback: HTTP 직접 호출
                # 로그 제거 - HTTP fallback 사용 시마다 로그가 찍히는 것을 방지
                
                yield StreamChunk(
                    type="progress",
                    tool_name=tool_name,
                    content=f"📊 Processing {tool_name} via HTTP...",
                    metadata={"status": "processing", "fallback": True}
                )
                
                # HTTP 직접 호출 - MCP JSON-RPC 프로토콜 사용
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.server_url}/mcp",
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json, text/event-stream"
                        },
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/call",
                            "params": {
                                "name": tool_name,
                                "arguments": arguments
                            }
                        },
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        # SSE 응답 파싱
                        response_text = response.text.strip()
                        logger.debug(f"Tool call response: {response_text}")
                        
                        # SSE 형식 파싱: "event: message\ndata: {json}"
                        if "event: message" in response_text and "data: " in response_text:
                            lines = response_text.split('\n')
                            
                            # 모든 SSE 메시지를 파싱하여 실제 결과를 찾기
                            for i, line in enumerate(lines):
                                if line.startswith("data: "):
                                    json_data = line[6:]  # "data: " 제거
                                    try:
                                        data = json.loads(json_data)
                                        # 실제 결과가 있는 메시지만 처리 (디버그 알림 무시)
                                        if "result" in data and data.get("jsonrpc") == "2.0":
                                            result = data["result"]
                                            # MCP 결과에서 실제 콘텐츠 추출
                                            content = self._extract_mcp_content(result)
                                            
                                            # Check if data was truncated and add appropriate messaging
                                            metadata = {"protocol": "http"}
                                            if isinstance(content, dict) and content.get("_truncated"):
                                                metadata["data_truncated"] = True
                                                metadata["truncation_info"] = {
                                                    "original_count": content.get("_original_count"),
                                                    "showing_count": content.get("_showing_count"),
                                                    "message": content.get("_truncation_message")
                                                }
                                            
                                            yield StreamChunk(
                                                type="tool_result",
                                                tool_name=tool_name,
                                                content=f"✅ {tool_name} completed via HTTP",
                                                tool_result={"content": content, "mcp_result": result},
                                                metadata=metadata
                                            )
                                            return  # 결과를 찾았으므로 종료
                                    except json.JSONDecodeError:
                                        # JSON 파싱 실패 시 다음 라인 시도
                                        continue
                            
                            # 결과를 찾지 못한 경우
                            raise Exception(f"No valid result found in SSE response")
                        else:
                            # 일반 JSON 응답 처리 (fallback)
                            try:
                                data = response.json()
                                if "result" in data:
                                    result = data["result"]
                                    content = self._extract_mcp_content(result)
                                    
                                    # Check if data was truncated and add appropriate messaging
                                    metadata = {"protocol": "http"}
                                    if isinstance(content, dict) and content.get("_truncated"):
                                        metadata["data_truncated"] = True
                                        metadata["truncation_info"] = {
                                            "original_count": content.get("_original_count"),
                                            "showing_count": content.get("_showing_count"),
                                            "message": content.get("_truncation_message")
                                        }
                                    
                                    yield StreamChunk(
                                        type="tool_result",
                                        tool_name=tool_name,
                                        content=f"✅ {tool_name} completed via HTTP",
                                        tool_result={"content": content, "mcp_result": result},
                                        metadata=metadata
                                    )
                                else:
                                    raise Exception(f"No result in response: {data}")
                            except json.JSONDecodeError as e:
                                raise Exception(f"Failed to parse JSON response: {e}")
                    else:
                        raise Exception(f"HTTP call failed: {response.status_code} - {response.text}")
                        
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            yield StreamChunk(
                type="error",
                tool_name=tool_name,
                error=str(e)
            )
    
    def _extract_mcp_content(self, mcp_result: Any) -> Any:
        """Extract clean content from MCP result without wrapper structure"""
        # First extract the core content from MCP wrapper
        core_content = self._unwrap_mcp_structure(mcp_result)
        
        # Then apply truncation if needed
        return self._truncate_large_data(core_content)
    
    def _unwrap_mcp_structure(self, mcp_result: Any) -> Any:
        """Remove MCP wrapper structure and extract just the data"""
        if isinstance(mcp_result, dict):
            # Extract from structuredContent first
            if "structuredContent" in mcp_result and mcp_result["structuredContent"]:
                return mcp_result["structuredContent"]
            
            # Extract from content array
            elif "content" in mcp_result and mcp_result["content"]:
                content = mcp_result["content"]
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[0], dict) and "text" in content[0]:
                        text_content = content[0]["text"]
                        # Try to parse as JSON to get structured data
                        try:
                            return json.loads(text_content)
                        except (json.JSONDecodeError, TypeError):
                            return text_content
                return content
        
        return mcp_result
    
    def _truncate_large_data(self, data: Any, max_rows: int = 50, max_chars: int = 50000) -> Any:
        """Truncate large datasets to prevent context length issues"""
        if isinstance(data, dict):
            # Handle structured data with rows
            if "data" in data and isinstance(data["data"], list):
                original_count = len(data["data"])
                if original_count > max_rows:
                    # Truncate rows and add summary
                    truncated_data = data.copy()
                    truncated_data["data"] = data["data"][:max_rows]
                    truncated_data["_truncated"] = True
                    truncated_data["_original_count"] = original_count
                    truncated_data["_showing_count"] = max_rows
                    truncated_data["_truncation_message"] = f"⚠️ 데이터가 너무 많아 {max_rows}개 행만 표시합니다. (전체: {original_count}개)"
                    return truncated_data
            
            # Handle other dict structures
            result = {}
            for key, value in data.items():
                result[key] = self._truncate_large_data(value, max_rows, max_chars)
            return result
            
        elif isinstance(data, list):
            if len(data) > max_rows:
                # Truncate list and add metadata
                return {
                    "data": data[:max_rows],
                    "_truncated": True,
                    "_original_count": len(data),
                    "_showing_count": max_rows,
                    "_truncation_message": f"⚠️ 데이터가 너무 많아 {max_rows}개 항목만 표시합니다. (전체: {len(data)}개)"
                }
            return [self._truncate_large_data(item, max_rows, max_chars) for item in data]
            
        elif isinstance(data, str):
            if len(data) > max_chars:
                return data[:max_chars] + f"\n\n⚠️ 텍스트가 너무 길어 {max_chars}자로 잘렸습니다. (전체: {len(data)}자)"
            return data
            
        return data
    
    def _format_tool_result_for_display(self, tool_result: Dict[str, Any]) -> str:
        """Format tool result as user-friendly text with tables"""
        try:
            content = tool_result.get("content", {})
            
            # Handle dashboard lists
            if isinstance(content, dict) and "dashboards" in content:
                dashboards = content["dashboards"]
                if isinstance(dashboards, list) and len(dashboards) > 0:
                    table_lines = ["| 제목 | ID | 상태 | 생성일 |", "|------|----|----|--------|"]
                    for dash in dashboards:
                        title = dash.get("dashboard_title", "").replace("|", "\\|")[:30]
                        dash_id = dash.get("id", "")
                        status = "공개" if dash.get("published") else "비공개"
                        created = dash.get("created_on", "")[:10] if dash.get("created_on") else "-"
                        table_lines.append(f"| {title} | {dash_id} | {status} | {created} |")
                    
                    result = "\n".join(table_lines)
                    if content.get("_truncated"):
                        result += f"\n\n⚠️ {content.get('_truncation_message', '데이터가 일부만 표시됩니다.')}"
                    return result
            
            # Handle dataset lists  
            elif isinstance(content, dict) and "datasets" in content:
                datasets = content["datasets"]
                if isinstance(datasets, list) and len(datasets) > 0:
                    table_lines = ["| 테이블명 | ID | 데이터베이스 | 생성일 |", "|---------|----|-----------|---------| "]
                    for dataset in datasets:
                        table_name = dataset.get("table_name", "").replace("|", "\\|")[:25]
                        dataset_id = dataset.get("id", "")
                        db_name = dataset.get("database_name", "").replace("|", "\\|")[:15]
                        created = dataset.get("created_on", "")[:10] if dataset.get("created_on") else "-"
                        table_lines.append(f"| {table_name} | {dataset_id} | {db_name} | {created} |")
                    
                    result = "\n".join(table_lines)
                    if content.get("_truncated"):
                        result += f"\n\n⚠️ {content.get('_truncation_message', '데이터가 일부만 표시됩니다.')}"
                    return result
            
            # Handle chart lists
            elif isinstance(content, dict) and "charts" in content:
                charts = content["charts"]
                if isinstance(charts, list) and len(charts) > 0:
                    table_lines = ["| 차트명 | ID | 타입 | 생성일 |", "|-------|----|----|--------|"]
                    for chart in charts:
                        chart_name = chart.get("slice_name", "").replace("|", "\\|")[:25]
                        chart_id = chart.get("id", "")
                        viz_type = chart.get("viz_type", "").replace("|", "\\|")[:15]
                        created = chart.get("created_on", "")[:10] if chart.get("created_on") else "-"
                        table_lines.append(f"| {chart_name} | {chart_id} | {viz_type} | {created} |")
                    
                    result = "\n".join(table_lines)
                    if content.get("_truncated"):
                        result += f"\n\n⚠️ {content.get('_truncation_message', '데이터가 일부만 표시됩니다.')}"
                    return result
            
            # Fallback to JSON for other data types
            return json.dumps(tool_result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Error formatting tool result: {e}")
            return json.dumps(tool_result, ensure_ascii=False, indent=2)
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """정식 MCP 프로토콜로 도구 목록 조회"""
        if self._tools_cache:
            # 캐시된 도구 반환 시 로그 제거
            return [{"name": tool.name, "description": tool.description} for tool in self._tools_cache]
            
        try:
            session = await self._get_session()
            
            if session:
                # 정식 MCP 프로토콜 사용
                # 로그 제거 - 도구 목록 조회 시마다 로그가 찍히는 것을 방지
                
                request = ListToolsRequest(method="tools/list")
                response = await session.list_tools(request)
                
                self._tools_cache = response.tools
                tools = [{"name": tool.name, "description": tool.description} for tool in response.tools]
                
                # 로그 제거 - 도구 개수 로깅 불필요
                return tools
            else:
                # Fallback: HTTP 직접 호출
                logger.debug(f"Attempting to connect to MCP server: {self.server_url}")
                
                async with httpx.AsyncClient() as client:
                    # MCP server에서 정식 JSON-RPC 프로토콜로 도구 목록 요청
                    request_payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list"
                    }
                    logger.debug(f"Sending MCP request: {request_payload}")
                    
                    response = await client.post(
                        f"{self.server_url}/mcp",
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json, text/event-stream"
                        },
                        json=request_payload,
                        timeout=10.0
                    )
                    
                    logger.debug(f"MCP server response status: {response.status_code}")
                    logger.debug(f"MCP server response headers: {dict(response.headers)}")
                    
                    if response.status_code == 200:
                        # Server-Sent Events 응답 파싱
                        response_text = response.text.strip()
                        logger.debug(f"Raw MCP response: {response_text}")
                        
                        # SSE 형식 파싱: "event: message\ndata: {json}"
                        if "event: message" in response_text and "data: " in response_text:
                            lines = response_text.split('\n')
                            
                            # 모든 SSE 메시지를 파싱하여 실제 결과를 찾기
                            for line in lines:
                                if line.startswith("data: "):
                                    json_data = line[6:]  # "data: " 제거
                                    try:
                                        data = json.loads(json_data)
                                        logger.debug(f"Parsed SSE JSON: {data}")
                                        # 실제 결과가 있는 메시지만 처리 (디버그 알림 무시)
                                        if "result" in data and "tools" in data.get("result", {}) and data.get("jsonrpc") == "2.0":
                                            tools = data["result"]["tools"]
                                            logger.debug(f"Found {len(tools)} tools from MCP server")
                                            return tools
                                    except json.JSONDecodeError as e:
                                        logger.debug(f"Failed to parse SSE JSON: {e}, data: {json_data}")
                                        continue
                        
                        # 일반 JSON 응답 처리 (fallback) - SSE가 아닌 경우에만 시도
                        elif not response_text.startswith("event:"):
                            try:
                                data = response.json()
                                logger.debug(f"Parsed regular JSON: {data}")
                                if "result" in data and "tools" in data["result"]:
                                    tools = data["result"]["tools"]
                                    logger.debug(f"Found {len(tools)} tools from regular JSON")
                                    return tools
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse regular JSON: {e}")
                                logger.error(f"Response content type: {response.headers.get('content-type')}")
                                logger.error(f"Response text: {response_text[:500]}...")
                    else:
                        logger.error(f"MCP server tools list failed: {response.status_code}")
                        
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            if logger.isEnabledFor(logging.DEBUG):
                import traceback
                logger.debug(f"Full traceback: {traceback.format_exc()}")
            
        # MCP 서버 연결 실패 시 빈 목록 반환
        logger.error(f"Failed to connect to MCP server at {self.server_url}")
        return []

class StreamingOpenRouterClient:
    """OpenAI 공식 클라이언트를 사용한 OpenRouter 클라이언트"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        # OpenAI 클라이언트를 OpenRouter로 설정
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        # 초기화 로그 제거
    
    def _format_tool_result_for_display(self, tool_result: Dict[str, Any]) -> str:
        """Format tool result as user-friendly text with tables"""
        try:
            content = tool_result.get("content", {})
            
            # Handle dashboard lists
            if isinstance(content, dict) and "dashboards" in content:
                dashboards = content["dashboards"]
                if isinstance(dashboards, list) and len(dashboards) > 0:
                    table_lines = ["| 제목 | ID | 상태 | 생성일 |", "|------|----|----|--------|"]
                    for dash in dashboards:
                        title = dash.get("dashboard_title", "").replace("|", "\\|")[:30]
                        dash_id = dash.get("id", "")
                        status = "공개" if dash.get("published") else "비공개"
                        created = dash.get("created_on", "")[:10] if dash.get("created_on") else "-"
                        table_lines.append(f"| {title} | {dash_id} | {status} | {created} |")
                    
                    result = "\n".join(table_lines)
                    if content.get("_truncated"):
                        result += f"\n\n⚠️ {content.get('_truncation_message', '데이터가 일부만 표시됩니다.')}"
                    return result
            
            # Handle dataset lists  
            elif isinstance(content, dict) and "datasets" in content:
                datasets = content["datasets"]
                if isinstance(datasets, list) and len(datasets) > 0:
                    table_lines = ["| 테이블명 | ID | 데이터베이스 | 생성일 |", "|---------|----|-----------|---------| "]
                    for dataset in datasets:
                        table_name = dataset.get("table_name", "").replace("|", "\\|")[:25]
                        dataset_id = dataset.get("id", "")
                        db_name = dataset.get("database_name", "").replace("|", "\\|")[:15]
                        created = dataset.get("created_on", "")[:10] if dataset.get("created_on") else "-"
                        table_lines.append(f"| {table_name} | {dataset_id} | {db_name} | {created} |")
                    
                    result = "\n".join(table_lines)
                    if content.get("_truncated"):
                        result += f"\n\n⚠️ {content.get('_truncation_message', '데이터가 일부만 표시됩니다.')}"
                    return result
            
            # Handle chart lists
            elif isinstance(content, dict) and "charts" in content:
                charts = content["charts"]
                if isinstance(charts, list) and len(charts) > 0:
                    table_lines = ["| 차트명 | ID | 타입 | 생성일 |", "|-------|----|----|--------|"]
                    for chart in charts:
                        chart_name = chart.get("slice_name", "").replace("|", "\\|")[:25]
                        chart_id = chart.get("id", "")
                        viz_type = chart.get("viz_type", "").replace("|", "\\|")[:15]
                        created = chart.get("created_on", "")[:10] if chart.get("created_on") else "-"
                        table_lines.append(f"| {chart_name} | {chart_id} | {viz_type} | {created} |")
                    
                    result = "\n".join(table_lines)
                    if content.get("_truncated"):
                        result += f"\n\n⚠️ {content.get('_truncation_message', '데이터가 일부만 표시됩니다.')}"
                    return result
            
            # Fallback to JSON for other data types
            return json.dumps(tool_result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Error formatting tool result: {e}")
            return json.dumps(tool_result, ensure_ascii=False, indent=2)
    
    def _convert_mcp_tool_to_openai_function(self, mcp_tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MCP tool schema to OpenAI function format"""
        # MCP server에서 제공하는 실제 input schema 사용 (필수)
        if "inputSchema" not in mcp_tool:
            logger.error(f"Tool {mcp_tool.get('name', 'unknown')} missing inputSchema")
            raise ValueError(f"Tool {mcp_tool.get('name', 'unknown')} must have inputSchema")
        
        return {
            "type": "function",
            "function": {
                "name": mcp_tool["name"],
                "description": mcp_tool["description"],
                "parameters": mcp_tool["inputSchema"]
            }
        }
    
    async def stream_chat_with_tools(
        self, 
        messages: List[Dict[str, Any]], 
        tools: List[Dict[str, Any]], 
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[StreamChunk, None]:
        """OpenAI 클라이언트를 사용한 스트리밍 채팅"""
        
        if not self.api_key:
            yield StreamChunk(type="error", error="OpenRouter API key not configured")
            return
        
        # Convert MCP tools to OpenAI format
        openai_tools = [self._convert_mcp_tool_to_openai_function(tool) for tool in tools] if tools else None
        
        # 스트리밍 시작 로그 제거 - 매 요청마다 로그가 찍히는 것을 방지
        
        try:
            # OpenAI 클라이언트로 스트리밍 요청
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
            
            # 도구가 있을 때만 추가
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"
            
            # 요청 파라미터 로그 제거
            
            stream = await self.client.chat.completions.create(**kwargs)
            
            tool_calls = []
            chunk_count = 0
            
            async for chunk in stream:
                chunk_count += 1
                # 모든 청크 로깅 제거 - 이것이 주요 로그 스팸 원인
                
                if not chunk.choices:
                    # 빈 choices 로그 제거
                    continue
                    
                choice = chunk.choices[0]
                delta = choice.delta
                
                # Delta와 finish reason 로그 제거
                
                # 콘텐츠 스트리밍
                if delta.content:
                    # 콘텐츠 스트리밍 로그 제거 - 매 청크마다 로그가 찍히는 것을 방지
                    yield StreamChunk(
                        type="content",
                        content=delta.content
                    )
                
                # 도구 호출 처리
                if delta.tool_calls:
                    # 도구 호출 발견 로그 제거
                    
                    # 도구 호출 누적 (OpenAI는 청크별로 부분 전송)
                    for tool_call_delta in delta.tool_calls:
                        # 새로운 도구 호출인지 확인
                        while len(tool_calls) <= tool_call_delta.index:
                            tool_calls.append({
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            })
                        
                        # 도구 호출 정보 누적
                        if tool_call_delta.id:
                            tool_calls[tool_call_delta.index]["id"] = tool_call_delta.id
                        if tool_call_delta.function:
                            if tool_call_delta.function.name:
                                tool_calls[tool_call_delta.index]["function"]["name"] += tool_call_delta.function.name
                            if tool_call_delta.function.arguments:
                                tool_calls[tool_call_delta.index]["function"]["arguments"] += tool_call_delta.function.arguments
                
                # 완료 처리
                if choice.finish_reason == "tool_calls":
                    # 도구 호출 완료 로그 제거
                    yield StreamChunk(
                        type="tool_calls",
                        metadata={"tool_calls": tool_calls}
                    )
                    return
                elif choice.finish_reason == "stop":
                    # 정상 완료 로그 제거
                    yield StreamChunk(type="done")
                    return
            
            # 스트리밍 완료 로그 제거
            yield StreamChunk(type="done")
                    
        except Exception as e:
            error_str = str(e)
            # 에러만 로깅하고 상세 traceback은 DEBUG 모드에서만
            logger.error(f"OpenAI 스트리밍 실패: {e}")
            if logger.isEnabledFor(logging.DEBUG):
                import traceback
                logger.debug(f"Full traceback: {traceback.format_exc()}")
            
            # Context length 에러 처리
            if "context length" in error_str.lower() or "maximum context length" in error_str.lower():
                yield StreamChunk(
                    type="error", 
                    error="⚠️ 데이터가 너무 많아 처리할 수 없습니다. 더 구체적인 조건으로 필터링하거나 작은 범위의 데이터를 요청해주세요.",
                    metadata={"error_type": "context_length_exceeded", "original_error": error_str}
                )
            else:
                yield StreamChunk(type="error", error=str(e))

# Initialize clients
streaming_mcp_client = StreamingMCPClient(MCP_SERVER_URL, "superset")

try:
    streaming_openrouter_client = StreamingOpenRouterClient(OPENROUTER_API_KEY)
    # 초기화 성공 로그 제거
except Exception as e:
    logger.error(f"StreamingOpenRouterClient 초기화 실패: {e}")
    if logger.isEnabledFor(logging.DEBUG):
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
    streaming_openrouter_client = None

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0-streaming",
        "mcp_server": MCP_SERVER_URL,
        "streaming_enabled": True
    }

@app.get("/models")
async def list_models():
    """List available models"""
    recommended_models = [
        {
            "id": "openai/gpt-4o-mini",
            "name": "GPT-4o Mini",
            "description": "Fast and efficient with function calling support",
            "supports_functions": True,
            "supports_streaming": True,
            "cost": "Low"
        },
        {
            "id": "openai/gpt-4o",
            "name": "GPT-4o",
            "description": "Most capable model with excellent function calling",
            "supports_functions": True,
            "supports_streaming": True,
            "cost": "Medium"
        },
        {
            "id": "anthropic/claude-3.5-sonnet",
            "name": "Claude 3.5 Sonnet",
            "description": "Excellent reasoning with function calling support",
            "supports_functions": True,
            "supports_streaming": True,
            "cost": "Medium"
        }
    ]
    return {"models": recommended_models, "default": DEFAULT_MODEL}

@app.get("/mcp/tools")
async def list_mcp_tools():
    """List available MCP tools"""
    # API 호출 로그 제거 - 매번 호출될 때마다 로그가 찍히는 것을 방지
    tools = await streaming_mcp_client.list_tools()
    # 도구 개수 로그 제거
    return {"tools": tools, "server": "superset"}

@app.post("/chat")
async def chat_completion_stream(request: ChatRequest):
    """Streaming chat completion with real-time MCP tool integration"""
    
    async def generate_streaming_response() -> AsyncGenerator[str, None]:
        try:
            # OpenRouter 클라이언트 체크
            if streaming_openrouter_client is None:
                error_chunk = StreamChunk(type="error", error="OpenRouter client not initialized")
                yield f"data: {error_chunk.model_dump_json()}\n\n"
                return
            
            # Get available MCP tools
            mcp_tools = await streaming_mcp_client.list_tools()
            
            # 도구 개수와 클라이언트 타입 로그 제거
            
            # Add system message with MCP context
            system_message = {
                "role": "system",
                "content": f"""You are a Superset AI Assistant with access to powerful MCP tools for data visualization and analysis.

🎯 CRITICAL: You MUST use the available tools to provide accurate, real-time data from Superset. NEVER make up or assume data.

📊 Available tools: {', '.join([tool.get('name', 'unknown') for tool in mcp_tools])}

💡 Always call tools to get current data before responding. Provide specific, actionable information.

� MANDATRORY TABLE FORMAT RULES:
1. NEVER show raw JSON data to users
2. ALWAYS convert data arrays to markdown tables
3. When you receive tool results with arrays like "dashboards", "charts", "datasets", you MUST format them as tables
4. Do NOT show metadata like count, page_size, total_count, pagination info
5. Extract ONLY the core data array and present it as a clean table

📋 REQUIRED TABLE FORMAT:
For dashboards:
| 제목 | ID | 상태 | 생성일 | UUID |
|------|----|----|--------|------|
| [title] | [id] | [published status] | [date] | [uuid] |

For datasets:
| 테이블명 | ID | 데이터베이스 | 생성일 | UUID |
|---------|----|-----------|---------|----|
| [table_name] | [id] | [database_name] | [date] | [uuid] |

For charts:
| 차트명 | ID | 타입 | 생성일 | UUID |
|-------|----|----|--------|------|
| [slice_name] | [id] | [viz_type] | [date] | [uuid] |

🔥 FORMATTING RULES:
- Dates: Show as YYYY-MM-DD only
- Boolean published: "공개" for true, "비공개" for false  
- NULL values: Show as "-"
- Long text: Truncate to 30 characters with "..."
- NEVER show raw JSON objects or arrays

🚨 EXAMPLE TRANSFORMATION:
If tool returns: {{"dashboards": [{{"id": 1, "dashboard_title": "Sales", "published": true}}]}}
You MUST show:
| 제목 | ID | 상태 |
|------|----|----|
| Sales | 1 | 공개 |

NOT the raw JSON!"""
            }
            
            # Prepare messages
            messages = [system_message] + [{"role": msg.role, "content": msg.content} for msg in request.messages]
            
            # Check if model supports function calling
            model_supports_functions = request.model in [
                "openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-3.5-turbo",
                "anthropic/claude-3.5-sonnet", "anthropic/claude-3-opus"
            ]
            
            # 실제 OpenAI 스트리밍 활성화
            if model_supports_functions and mcp_tools:
                # Stream with function calling
                async for chunk in streaming_openrouter_client.stream_chat_with_tools(
                    messages, mcp_tools, request.model, request.temperature, request.max_tokens
                ):
                    if chunk.type == "tool_calls":
                        # Execute tools and continue streaming
                        tool_calls = chunk.metadata["tool_calls"]
                        
                        # Execute each tool with streaming progress
                        tool_results = []
                        for tool_call in tool_calls:
                            function_name = tool_call["function"]["name"]
                            try:
                                function_args_str = tool_call["function"]["arguments"]
                                # 빈 문자열이나 공백만 있는 경우 처리
                                if not function_args_str or not function_args_str.strip():
                                    function_args = {}
                                else:
                                    function_args = json.loads(function_args_str)
                            except (json.JSONDecodeError, KeyError, TypeError) as e:
                                logger.error(f"Failed to parse tool arguments: {e}, raw: {tool_call}")
                                function_args = {}
                            
                            async for tool_chunk in streaming_mcp_client.stream_tool_execution(function_name, function_args):
                                yield f"data: {tool_chunk.model_dump_json()}\n\n"
                                
                                if tool_chunk.type == "tool_result":
                                    # Format tool result for better presentation
                                    formatted_content = self._format_tool_result_for_display(tool_chunk.tool_result)
                                    tool_results.append({
                                        "tool_call_id": tool_call["id"],
                                        "role": "tool",
                                        "content": formatted_content
                                    })
                        
                        # Continue with tool results
                        messages_with_results = messages + [
                            {"role": "assistant", "tool_calls": tool_calls}
                        ] + tool_results
                        
                        # Stream final response
                        async for final_chunk in streaming_openrouter_client.stream_chat_with_tools(
                            messages_with_results, [], request.model, request.temperature, request.max_tokens
                        ):
                            yield f"data: {final_chunk.model_dump_json()}\n\n"
                        
                        return
                    else:
                        yield f"data: {chunk.model_dump_json()}\n\n"
            else:
                # Stream without function calling
                async for chunk in streaming_openrouter_client.stream_chat_with_tools(
                    messages, [], request.model, request.temperature, request.max_tokens
                ):
                    yield f"data: {chunk.model_dump_json()}\n\n"
            
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            error_chunk = StreamChunk(type="error", error=str(e))
            yield f"data: {error_chunk.model_dump_json()}\n\n"
    
    return StreamingResponse(
        generate_streaming_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)