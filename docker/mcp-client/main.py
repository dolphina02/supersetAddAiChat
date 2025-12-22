#!/usr/bin/env python3
"""
Streaming MCP Client for Superset AI Assistant

이 서비스는 Superset AI 어시스턴트의 핵심 브리지 역할을 수행합니다:
1. Superset 프론트엔드로부터 사용자 메시지를 받음
2. OpenRouter API를 통해 LLM과 통신
3. LLM이 요청한 도구를 MCP 서버를 통해 실행
4. 결과를 실시간 스트리밍으로 프론트엔드에 전달

주요 기능:
- MCP Protocol: Model Context Protocol을 사용한 안전한 도구 실행
- Streaming: Server-Sent Events(SSE)를 통한 실시간 응답
- Agentic Loop: LLM이 여러 도구를 순차적으로 호출할 수 있는 다중 턴 실행
- Memory Management: 대용량 데이터 자동 절단으로 컨텍스트 오버플로우 방지

Transport: streamable-http (FastMCP 서버와 호환)
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
# MCP Official Client Library
from mcp import ClientSession
from mcp.types import Tool
# Note: sse_client is imported inside lifespan to avoid circular imports or runtime errors if not needed

# ============================================================
# 로깅 설정
# ============================================================
# DEBUG 환경변수가 true면 상세 로그, 아니면 INFO 레벨만 출력
LOG_LEVEL = logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# MCP 서버 URL 헬퍼 함수
# ============================================================
def get_mcp_server_url() -> str:
    """
    MCP 서버 URL을 환경변수에서 가져옵니다.
    
    중요: FastMCP의 streamable-http transport는 /mcp 엔드포인트를 사용하며,
    trailing slash(/)가 있으면 307 리다이렉트가 발생하여 SSE 연결이 끊어집니다.
    따라서 반드시 /mcp로 끝나야 합니다 (예: http://superset:5008/mcp)
    """
    return os.getenv("MCP_SERVER_URL", "http://superset:5008/mcp")

# ============================================================
# 환경 설정
# ============================================================
# OpenRouter API 키 (LLM 호출에 필요)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# 기본 사용 모델 (gpt-4o 또는 gpt-4o-mini)
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o")

# ============================================================
# 전역 상태 관리
# ============================================================
class GlobalState:
    """
    애플리케이션 전역 상태를 관리하는 클래스
    
    Attributes:
        session: MCP ClientSession - MCP 서버와의 연결 세션
        exit_stack: AsyncExitStack - 리소스 정리를 위한 컨텍스트 매니저
    """
    session: Optional[ClientSession] = None
    exit_stack: Optional[Any] = None

state = GlobalState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 애플리케이션의 생명주기를 관리합니다.
    
    이 함수는 애플리케이션 시작 시 MCP 서버와의 연결을 설정하고,
    종료 시 연결을 정리합니다.
    
    연결 프로세스:
    1. streamable-http transport로 MCP 서버에 연결
    2. ClientSession 생성
    3. MCP 프로토콜 초기화 (initialize 요청)
    4. 사용 가능한 도구 목록 조회
    
    Transport: streamable-http (FastMCP 서버와 호환)
    """
    mcp_url = get_mcp_server_url()
    logger.info("=" * 60)
    logger.info("🚀 Starting MCP Client (streamable-http Transport)")
    logger.info(f"📡 Target MCP Server: {mcp_url}")
    logger.info("=" * 60)
    
    try:
        from contextlib import AsyncExitStack
        from mcp.client.streamable_http import streamable_http_client

        exit_stack = AsyncExitStack()
        
        # ============================================================
        # STEP 1: Connect via streamable-http transport
        # This matches FastMCP's streamable-http server transport
        # ============================================================
        logger.info("📬 STEP 1: Connecting via streamable-http...")
        logger.debug(f"   → Connecting to {mcp_url}")
        
        read_stream, write_stream, get_session_id = await exit_stack.enter_async_context(
            streamable_http_client(mcp_url)
        )
        
        logger.info("✓ streamable-http connection established")
        logger.debug(f"   Session ID: {get_session_id() if get_session_id else 'N/A'}")
        
        # ============================================================
        # STEP 2: Create MCP ClientSession
        # ============================================================
        logger.info("🔧 STEP 2: Creating MCP ClientSession...")
        
        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        
        logger.info("✓ ClientSession created")
        
        # ============================================================
        # STEP 3: Initialize MCP Protocol
        # ============================================================
        logger.info("🤝 STEP 3: Initializing MCP session...")
        logger.debug("   → Sending initialize request")
        
        await session.initialize()
        
        logger.info("✓ Initialize response received")
        
        # Store session in global state
        state.session = session
        state.exit_stack = exit_stack
        
        # ============================================================
        # STEP 4: List Available Tools
        # ============================================================
        logger.info("📋 STEP 4: Requesting tool list...")
        logger.debug("   → Sending tools/list request")
        
        tools = await session.list_tools()
        
        logger.info("✓ Tool list received")
        
        # ============================================================
        # SUCCESS: Connection Established
        # ============================================================
        logger.info("=" * 60)
        logger.info(f"✅ MCP Connection Established!")
        logger.info(f"   Transport: streamable-http")
        logger.info(f"   Available tools: {len(tools.tools)}")
        logger.info("=" * 60)
        
        # Log first few tools
        if tools.tools:
            logger.info("Sample tools:")
            for tool in tools.tools[:5]:
                desc = tool.description[:50] + "..." if len(tool.description) > 50 else tool.description
                logger.info(f"  • {tool.name}: {desc}")
            if len(tools.tools) > 5:
                logger.info(f"  ... and {len(tools.tools) - 5} more")
        
        logger.info("=" * 60)
        
        yield
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error("❌ MCP Connection Failed!")
        logger.error(f"   URL: {mcp_url}")
        logger.error(f"   Error: {e}")
        logger.error("=" * 60)
        logger.debug("Full traceback:", exc_info=True)
        
        # Don't raise here, allow the app to start even if MCP is down
        # Health check endpoint will report the connection status
        yield
        
    finally:
        logger.info("🛑 Shutting down MCP Client...")
        if state.exit_stack:
            try:
                await state.exit_stack.aclose()
                logger.info("✓ MCP connection closed cleanly")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")


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

# ============================================================
# 데이터 모델 정의
# ============================================================

class ChatMessage(BaseModel):
    """
    채팅 메시지 모델 (OpenAI Chat Completion API 형식)
    
    Attributes:
        role: 메시지 역할 ("user", "assistant", "tool", "system")
        content: 메시지 내용
        tool_calls: LLM이 요청한 도구 호출 목록 (assistant 메시지에서 사용)
        tool_call_id: 도구 호출 ID (tool 메시지에서 사용)
        name: 도구 이름 (tool 메시지에서 사용)
    """
    role: str
    content: Optional[str] = ""
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

class ChatRequest(BaseModel):
    """
    채팅 요청 모델
    
    Attributes:
        messages: 대화 히스토리 (사용자 메시지 포함)
        model: 사용할 LLM 모델 (예: "openai/gpt-4o-mini")
        temperature: 응답의 창의성 (0.0~1.0, 높을수록 창의적)
        max_tokens: 최대 생성 토큰 수
    """
    messages: List[ChatMessage]
    model: Optional[str] = DEFAULT_MODEL
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2000

class StreamChunk(BaseModel):
    """
    스트리밍 응답 청크 모델 (Server-Sent Events 형식)
    
    Attributes:
        type: 청크 타입
            - "content": LLM 응답 텍스트
            - "tool_start": 도구 실행 시작
            - "tool_result": 도구 실행 완료
            - "tool_calls": LLM이 도구 호출 요청
            - "error": 오류 발생
            - "done": 스트림 종료
        content: 텍스트 내용
        tool_name: 실행 중인 도구 이름
        tool_result: 도구 실행 결과
        error: 오류 메시지
        metadata: 추가 메타데이터 (예: tool_calls 목록)
        timestamp: 청크 생성 시각 (ISO 8601 형식)
    """
    type: str
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_result: Optional[Dict] = None
    error: Optional[str] = None
    metadata: Optional[Dict] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

# ============================================================
# OpenRouter 클라이언트
# ============================================================

class StreamingOpenRouterClient:
    """
    OpenRouter API를 사용하는 스트리밍 LLM 클라이언트
    
    OpenRouter는 OpenAI API와 호환되는 인터페이스를 제공하므로
    OpenAI 공식 클라이언트를 사용할 수 있습니다.
    
    주요 기능:
    - 스트리밍 응답 (Server-Sent Events)
    - Function Calling (도구 호출)
    - 다양한 LLM 모델 지원 (GPT-4, Claude, Gemini 등)
    """
    
    def __init__(self, api_key: str):
        """
        OpenRouter 클라이언트를 초기화합니다.
        
        Args:
            api_key: OpenRouter API 키 (sk-or-v1-로 시작)
        """
        self.api_key = api_key
        
        # API 키 상태 로깅 (디버깅용)
        if not api_key or api_key.strip() == "":
            logger.error("❌ OpenRouter API key is EMPTY!")
        else:
            logger.info(f"✓ OpenRouter API key loaded: {api_key[:10]}...{api_key[-4:]}")
        
        # OpenAI 호환 클라이언트 생성
        # OpenRouter는 Authorization: Bearer {api_key} 헤더를 사용
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "http://localhost:8088",  # OpenRouter 요구사항
                "X-Title": "Superset AI Assistant",       # 앱 식별용
            }
        )
    
    def _convert_mcp_tool_to_openai_function(self, mcp_tool: Tool) -> Dict[str, Any]:
        """
        MCP Tool을 OpenAI Function Calling 형식으로 변환합니다.
        
        MCP Tool 형식:
        {
            "name": "list_dashboards",
            "description": "대시보드 목록 조회",
            "inputSchema": {...}
        }
        
        OpenAI Function 형식:
        {
            "type": "function",
            "function": {
                "name": "list_dashboards",
                "description": "대시보드 목록 조회",
                "parameters": {...}
            }
        }
        
        Args:
            mcp_tool: MCP Tool 객체
            
        Returns:
            OpenAI Function Calling 형식의 딕셔너리
        """
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
        """
        LLM과 스트리밍 채팅을 수행하며, 도구 호출을 지원합니다.
        
        이 함수는 OpenAI의 Function Calling 기능을 사용하여
        LLM이 필요한 도구를 호출할 수 있도록 합니다.
        
        스트리밍 프로세스:
        1. LLM에게 메시지와 사용 가능한 도구 목록 전달
        2. LLM 응답을 실시간으로 스트리밍
        3. LLM이 도구 호출을 요청하면 tool_calls 청크 반환
        4. 일반 텍스트 응답이면 content 청크 반환
        
        Args:
            messages: 대화 히스토리
            tools: 사용 가능한 MCP 도구 목록
            model: 사용할 LLM 모델
            temperature: 응답의 창의성 (0.0~1.0)
            max_tokens: 최대 생성 토큰 수
            
        Yields:
            StreamChunk: 스트리밍 응답 청크
                - type="content": LLM 텍스트 응답
                - type="tool_calls": LLM이 도구 호출 요청
                - type="done": 스트림 종료
                - type="error": 오류 발생
        """
        
        # API 키 검증
        if not self.api_key:
            yield StreamChunk(type="error", error="OpenRouter API key not configured")
            return
        
        # MCP Tool을 OpenAI Function 형식으로 변환
        openai_tools = [self._convert_mcp_tool_to_openai_function(t) for t in tools] if tools else None
        
        try:
            # OpenAI API 호출 파라미터 구성
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,  # 스트리밍 활성화
            }
            
            # 도구가 있으면 Function Calling 활성화
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"  # LLM이 자동으로 도구 선택
            
            # 스트리밍 시작
            stream = await self.client.chat.completions.create(**kwargs)
            
            # 도구 호출 버퍼 (스트리밍 중 조각난 tool_calls를 모음)
            tool_calls = []
            
            # 스트림 청크 처리
            async for chunk in stream:
                if not chunk.choices: 
                    continue
                    
                choice = chunk.choices[0]
                delta = choice.delta
                
                # 텍스트 콘텐츠 스트리밍
                if delta.content:
                    yield StreamChunk(type="content", content=delta.content)
                
                # 도구 호출 스트리밍 (조각난 데이터를 버퍼에 누적)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        # 버퍼 크기 확장
                        while len(tool_calls) <= tc.index:
                            tool_calls.append({
                                "id": "", 
                                "type": "function", 
                                "function": {"name": "", "arguments": ""}
                            })
                        
                        # 조각난 데이터 누적
                        if tc.id: 
                            tool_calls[tc.index]["id"] = tc.id
                        if tc.function.name: 
                            tool_calls[tc.index]["function"]["name"] += tc.function.name
                        if tc.function.arguments: 
                            tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
                
                # 스트림 종료 처리
                if choice.finish_reason == "tool_calls":
                    # LLM이 도구 호출 요청
                    yield StreamChunk(type="tool_calls", metadata={"tool_calls": tool_calls})
                    return
                elif choice.finish_reason == "stop":
                    # 정상 종료
                    yield StreamChunk(type="done")
                    return
                    
            # 스트림 완료
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
    """Health check endpoint - returns MCP connection status"""
    is_connected = state.session is not None
    return {
        "status": "healthy" if is_connected else "degraded",
        "transport": "streamable-http",
        "connected": is_connected,
        "message": "MCP session active" if is_connected else "MCP session not connected"
    }

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