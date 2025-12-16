# AI 어시스턴트가 통합된 Apache Superset

🤖 **AI 강화 데이터 시각화 플랫폼** - 자연어 데이터 탐색 및 시각화를 위한 지능형 AI 어시스턴트가 통합된 Apache Superset

> 🇰🇷 **한국어**: README_KO.md | 🇺🇸 **English**: [README.md](./README.md)

## 🚀 새로운 기능

이 프로젝트는 강력한 AI 어시스턴트가 통합된 Apache Superset으로, 다음과 같은 기능을 제공합니다:

- **자연어 쿼리**: 평범한 한국어로 데이터에 대해 질문하기
- **지능형 차트 생성**: 대화형 AI를 통한 시각화 생성
- **실시간 데이터 탐색**: 스트리밍 응답으로 즉시 인사이트 획득
- **다중 LLM 지원**: GPT-4, Claude 등 주요 AI 모델과 연동

> 📖 **원본 Apache Superset 문서**: [ORIGINAL_SUPERSET_README.md](./ORIGINAL_SUPERSET_README.md)

## 🎯 주요 기능

### AI 어시스턴트 기능
- **대시보드 관리**: 자연어로 대시보드 목록 조회, 생성, 관리
- **차트 생성**: "지역별 매출을 보여줘"와 같은 간단한 설명으로 차트 생성
- **데이터 탐색**: 데이터셋 쿼리 및 포맷된 테이블 결과 제공
- **SQL 실행**: AI 지원 및 안전성 검증을 통한 SQL 쿼리 실행
- **실시간 스트리밍**: 실시간 도구 실행 업데이트와 함께 점진적 응답 제공

### 기술 아키텍처
- **MCP 프로토콜**: 안전한 AI-데이터 연결을 위한 Model Context Protocol
- **스트리밍 인터페이스**: Server-Sent Events를 통한 실시간 응답
- **다중 모델 지원**: 다양한 AI 제공업체를 위한 OpenRouter 통합
- **타입 안전 구현**: Python 타입 힌트와 완전한 TypeScript 프론트엔드

## 🏗️ 아키텍처 개요

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   React UI      │    │   MCP Client     │    │   MCP Server    │
│   (프론트엔드)    │◄──►│   (스트리밍)      │◄──►│   (Superset)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                        │                        │
        │                        │                        │
   ┌────▼────┐              ┌────▼────┐              ┌────▼────┐
   │ AiChat  │              │ FastAPI │              │ Flask   │
   │컴포넌트  │              │ 서버     │              │ 백엔드   │
   └─────────┘              └─────────┘              └─────────┘
```

## 🛠️ 빠른 시작

### 사전 요구사항
- Docker 및 Docker Compose
- OpenRouter API 키 (AI 기능용)

### 1. 클론 및 설정
```bash
git clone https://github.com/dolphina02/supersetAddAiChat.git
cd supersetAddAiChat
```

### 2. 환경 설정
```bash
# 환경 파일 복사 및 편집
cp docker/.env.example docker/.env

# OpenRouter API 키 추가
echo "OPENROUTER_API_KEY=your-api-key-here" >> docker/.env
```

### 3. 서비스 시작
```bash
# 모든 서비스 시작
docker-compose up -d

# 서비스 상태 확인
curl http://localhost:8088/health  # Superset
curl http://localhost:8000/health  # MCP Client
```

### 4. 애플리케이션 접속
- **Superset UI**: http://localhost:8088
- **AI 채팅**: 상단 네비게이션 바에서 이용 가능
- **기본 로그인**: admin/admin

## 🔧 상세 구현 내용

### MCP 서버 아키텍처

MCP(Model Context Protocol) 서버는 Superset 컨테이너 내부에서 실행되며 데이터 작업을 위한 21개 이상의 도구를 제공합니다:

**위치**: `superset/mcp_service/`

**핵심 컴포넌트**:
#### 핵심 도구들
- **대시보드 도구**: `list_dashboards`, `get_dashboard_info`, `generate_dashboard`
- **차트 도구**: `list_charts`, `get_chart_data`, `generate_chart`, `update_chart`
- **데이터셋 도구**: `list_datasets`, `get_dataset_info`
- **SQL 도구**: `execute_sql`, `open_sql_lab_with_context`
- **시스템 도구**: `get_instance_info`, `health_check`

#### 도구 등록 시스템
```python
# superset/mcp_service/server.py
@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """모든 MCP 도구를 동적으로 발견하고 등록"""
    return discover_mcp_tools()

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """적절한 오류 처리 및 검증과 함께 도구 실행"""
    return await execute_mcp_tool(name, arguments)
```

#### 스키마 검증
모든 도구는 입력/출력 검증을 위해 Pydantic 스키마를 사용합니다:
```python
# 예시: 차트 생성 스키마
class GenerateChartRequest(BaseModel):
    dataset_id: Union[int, str]
    config: Union[XYChartConfig, TableChartConfig]
    chart_name: Optional[str] = None
    save_chart: bool = False
```

### MCP 클라이언트 아키텍처

MCP 클라이언트는 AI 모델과 Superset 데이터를 연결하는 FastAPI 기반 스트리밍 서비스입니다.

**위치**: `docker/mcp-client/`

#### 핵심 컴포넌트

**1. 스트리밍 클라이언트 (`main.py`)**
```python
class StreamingMCPClient:
    """실시간 스트리밍으로 MCP 프로토콜 통신 처리"""
    
    async def stream_tool_execution(self, tool_name: str, arguments: Dict) -> AsyncGenerator[StreamChunk, None]:
        """스트리밍 진행 업데이트와 함께 MCP 도구 실행"""
        
    def _extract_mcp_content(self, mcp_result: Any) -> Any:
        """MCP 프로토콜 래퍼에서 깨끗한 데이터 추출"""
        
    def _truncate_large_data(self, data: Any, max_rows: int = 50) -> Any:
        """대용량 데이터셋으로 인한 컨텍스트 길이 문제 방지"""
```

**2. OpenAI 통합**
```python
class StreamingOpenRouterClient:
    """함수 호출 지원이 포함된 OpenAI 호환 클라이언트"""
    
    async def stream_chat_with_tools(self, messages: List[Dict], tools: List[Dict]) -> AsyncGenerator[StreamChunk, None]:
        """실시간 도구 실행과 함께 채팅 응답 스트리밍"""
```

#### 데이터 플로우 아키텍처

**1. 요청 처리**
```
사용자 메시지 → 시스템 메시지 + 도구 → OpenAI API → 도구 호출 → MCP 서버 → 결과 → 포맷된 응답
```

**2. 스트리밍 구현**
```python
# Server-Sent Events 형식
async def generate_streaming_response():
    async for chunk in openai_stream:
        if chunk.type == "tool_calls":
            # 진행 업데이트와 함께 MCP 도구 실행
            for tool_call in chunk.tool_calls:
                async for progress in mcp_client.stream_tool_execution():
                    yield f"data: {progress.json()}\n\n"
```

#### 오류 처리 및 컨텍스트 관리

**컨텍스트 길이 보호**:
```python
def _truncate_large_data(self, data: Any, max_rows: int = 50, max_chars: int = 50000) -> Any:
    """OpenAI 컨텍스트 제한을 방지하기 위한 지능적 데이터 절단"""
    if isinstance(data, dict) and "data" in data:
        if len(data["data"]) > max_rows:
            return {
                **data,
                "data": data["data"][:max_rows],
                "_truncated": True,
                "_truncation_message": f"⚠️ {len(data['data'])}개 중 {max_rows}개 행 표시"
            }
```

**강력한 오류 복구**:
```python
try:
    # MCP 도구 실행
    result = await session.call_tool(request)
except Exception as e:
    if "context length" in str(e).lower():
        yield StreamChunk(
            type="error", 
            error="⚠️ 데이터셋이 너무 큽니다. 더 구체적인 필터를 사용해주세요."
        )
```

### 프론트엔드 통합

**위치**: `superset-frontend/src/components/AiChat/`

#### React 컴포넌트 아키텍처
```typescript
// AiChat/index.tsx
export const AiChat: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  
  const handleStreamingResponse = useCallback(async (userMessage: string) => {
    const eventSource = new EventSource('/api/v1/mcp-client/chat');
    
    eventSource.onmessage = (event) => {
      const chunk = JSON.parse(event.data);
      
      switch (chunk.type) {
        case 'tool_start':
          // 도구 실행 진행 상황 표시
          break;
        case 'content':
          // AI 응답 콘텐츠 스트리밍
          break;
        case 'tool_result':
          // 포맷된 결과 표시
          break;
      }
    };
  }, []);
};
```

#### 테이블 포맷팅 시스템
클라이언트는 데이터 응답을 자동으로 마크다운 테이블로 포맷합니다:

```python
def _format_tool_result_for_display(self, tool_result: Dict) -> str:
    """MCP 결과를 사용자 친화적인 마크다운 테이블로 변환"""
    
    if "dashboards" in content:
        table_lines = ["| 제목 | ID | 상태 | 생성일 |", "|------|----|----|--------|"]
        for dash in content["dashboards"]:
            title = dash.get("dashboard_title", "")[:30]
            status = "공개" if dash.get("published") else "비공개"
            table_lines.append(f"| {title} | {dash['id']} | {status} | {dash['created_on'][:10]} |")
        return "\n".join(table_lines)
```

## 🔒 보안 및 설정

### 환경 변수
```bash
# AI 설정
OPENROUTER_API_KEY=your-openrouter-key
DEFAULT_MODEL=openai/gpt-4o-mini
MCP_CLIENT_URL=http://mcp-client:8000

# 개발 설정
DEBUG=true                    # 상세 로깅 활성화
FLASK_DEBUG=true             # Flask 개발 모드
SUPERSET_LOG_LEVEL=info      # 애플리케이션 로그 레벨
```

### 보안 기능
- **입력 검증**: 모든 MCP 도구에서 Pydantic 스키마 사용
- **SQL 인젝션 보호**: 매개변수화된 쿼리 및 검증
- **속도 제한**: 내장 요청 스로틀링
- **인증**: Superset RBAC 통합
- **데이터 절단**: 자동 대용량 데이터셋 처리

## 🧪 개발 및 테스트

### 테스트 실행
```bash
# MCP 서버 테스트
pytest tests/unit_tests/mcp_service/

# MCP 클라이언트 테스트  
cd docker/mcp-client && python -m pytest

# 프론트엔드 테스트
cd superset-frontend && npm test
```

### 개발 워크플로
```bash
# 개발 환경 시작
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

# MCP 클라이언트 로그 확인
docker logs -f superset_mcp_client

# 개발 도구 접근
curl http://localhost:8000/mcp/tools  # 사용 가능한 도구 목록
curl http://localhost:5008/health     # MCP 서버 상태
```

## 📊 사용 예시

### 자연어 쿼리
```
"이번 달에 생성된 모든 대시보드를 보여줘"
"매출 데이터셋을 사용해서 지역별 매출 막대 차트를 만들어줘"
"examples 데이터베이스에서 사용 가능한 데이터셋이 뭐가 있어?"
"매출 상위 10개 고객을 조회하는 쿼리를 실행해줘"
```

### API 통합
```python
# 직접 MCP 도구 사용
import httpx

async def call_mcp_tool():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/chat",
            json={
                "messages": [{"role": "user", "content": "모든 대시보드 목록을 보여줘"}],
                "model": "openai/gpt-4o-mini"
            }
        )
```

## 🤝 기여하기

이 프로젝트는 AI 기능으로 Apache Superset을 확장합니다. 기여 방법:

1. **AI 어시스턴트 기능**: `docker/mcp-client/` 및 `superset/mcp_service/`에 집중
2. **프론트엔드 통합**: `superset-frontend/src/components/AiChat/`에서 작업
3. **Superset 가이드라인 준수**: [ORIGINAL_SUPERSET_README.md](./ORIGINAL_SUPERSET_README.md) 참조

### 코드 표준
- **Python**: 타입 힌트 필수, MyPy 준수
- **TypeScript**: 엄격한 타이핑, `any` 타입 금지
- **테스트**: 모든 새로운 MCP 도구에 대한 단위 테스트
- **문서화**: 새로운 기능에 대해 이 README 업데이트

## 📝 라이선스

이 프로젝트는 원본 Apache Superset과 동일한 Apache License 2.0을 유지합니다.

## 🔗 링크

- **원본 Apache Superset**: [ORIGINAL_SUPERSET_README.md](./ORIGINAL_SUPERSET_README.md)
- **설정 가이드**: [AI_ASSISTANT_SETUP.md](./AI_ASSISTANT_SETUP.md)
- **MCP 프로토콜**: [Model Context Protocol 명세](https://modelcontextprotocol.io/)
- **OpenRouter**: [OpenRouter API 문서](https://openrouter.ai/docs)

---

**Apache Superset 위에 ❤️로 구축됨** | **AI 강화 데이터 시각화**