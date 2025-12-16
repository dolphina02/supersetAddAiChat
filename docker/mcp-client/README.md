# Superset MCP Client

Superset AI Assistant를 위한 MCP (Model Context Protocol) 클라이언트 서비스입니다.

## 🚀 기능

- **OpenRouter 연동**: 다양한 오픈소스 LLM 모델 지원
- **MCP 프로토콜**: Superset MCP 서버와 통신
- **RESTful API**: Superset 프론트엔드와 HTTP API로 통신
- **한국어 지원**: 한국어 질문과 응답 지원
- **🆕 표준화된 응답 처리**: 여러 MCP 서버의 응답을 표준 형식으로 통합
- **🆕 멀티 서버 지원**: 여러 MCP 서버를 동시에 관리
- **🆕 구조화된 로깅**: 디버깅과 모니터링을 위한 상세 로깅
- **🆕 LLM 컨텍스트 최적화**: 응답 크기와 형식을 LLM에 최적화

## 🏗️ 아키텍처

### MCP 응답 표준화 시스템

```
MCP Server Response → MCPResponseNormalizer → StandardMCPResult → MCPContextOptimizer → LLM Context
```

#### 표준화된 응답 형식 (StandardMCPResult)
```python
{
    "result_type": "success" | "error" | "partial" | "empty",
    "data_type": "list" | "object" | "text" | "binary" | "structured",
    "data": Any,
    "metadata": {
        "count": int,           # 리스트의 경우
        "truncated": bool,      # 잘린 데이터 여부
        "fields": List[str],    # 객체의 필드명들
        ...
    },
    "error": Optional[str],
    "tool_name": str,
    "server_name": str,
    "timestamp": str
}
```

#### LLM 최적화된 형식
```python
{
    "status": "success" | "error" | "empty",
    "type": "list" | "object" | "text" | "structured",
    "data": Any,              # 최적화된 데이터
    "count": int,             # 리스트의 경우
    "truncated": bool,        # 컨텍스트 크기로 인한 잘림
    "note": str,              # 사용자에게 표시할 메모
    "tool": str,
    "server": str
}
```

### 멀티 서버 지원

```python
# 서버 등록
mcp_registry = MCPServerRegistry()
mcp_registry.servers = {
    "superset": MCPClient("http://superset:5008", "superset"),
    "weather": MCPClient("http://weather-mcp:8080", "weather"),
    # 추가 서버들...
}

# 도구 호출 시 자동 서버 선택
await mcp_registry.call_tool("superset", "list_dashboards", {})
```

## 🛠️ 지원 모델

### 추천 오픈소스 모델들:

1. **Qwen 2.5 7B Instruct** (기본값)
   - 최신 모델, 다국어 지원 우수
   - 16GB VRAM 필요

2. **Llama 3.1 8B Instruct**
   - Meta의 최신 모델
   - 24GB VRAM 필요

3. **Mistral 7B Instruct**
   - 효율적이고 빠른 추론
   - 16GB VRAM 필요

4. **DeepSeek Coder 6.7B**
   - 코딩 특화 모델
   - 16GB VRAM 필요

## 🔧 설정

### 1. OpenRouter API 키 설정

```bash
# docker/.env 파일에 추가
OPENROUTER_API_KEY=your_api_key_here
```

### 2. Docker Compose로 실행

```bash
# MCP 프로필과 함께 실행
docker-compose --profile mcp up -d

# 또는 특정 서비스만 실행
docker-compose up -d mcp-client
```

### 3. 환경 변수

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `OPENROUTER_API_KEY` | - | OpenRouter API 키 (필수) |
| `MCP_SERVER_URL` | `http://superset:5008` | Superset MCP 서버 URL |
| `DEFAULT_MODEL` | `qwen/qwen-2.5-7b-instruct` | 기본 AI 모델 |
| `PORT` | `8000` | 서비스 포트 |

## 📡 API 엔드포인트

### 채팅 API
```http
POST /chat
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "대시보드 목록을 보여줘"}
  ],
  "model": "openai/gpt-4o-mini",
  "temperature": 0.7,
  "max_tokens": 2000
}
```

### 모델 목록
```http
GET /models
```

### 헬스 체크 (개선됨)
```http
GET /health

# 응답 예시
{
  "status": "healthy",
  "mcp_client_version": "1.0.0",
  "servers": {
    "superset": {
      "status": "healthy",
      "url": "http://superset:5008",
      "tool_count": 12
    }
  }
}
```

### MCP 도구 목록 (개선됨)
```http
GET /mcp/tools

# 응답 예시
{
  "tools": [...],           # 모든 도구의 평면 목록 (하위 호환성)
  "servers": {              # 서버별 도구 목록
    "superset": [...],
    "weather": [...]
  },
  "server_names": ["superset", "weather"]
}
```

### MCP 서버 목록 (신규)
```http
GET /mcp/servers

# 응답 예시
{
  "servers": [
    {
      "name": "superset",
      "url": "http://superset:5008",
      "status": "active"
    }
  ]
}
```

### 특정 서버의 도구 호출 (신규)
```http
POST /mcp/servers/{server_name}/tools/{tool_name}
Content-Type: application/json

{
  "arguments": {...}
}
```

### 디버그 정보 (신규)
```http
GET /debug/mcp-logs

# 개발 환경에서 MCP 통신 로그 정보 확인
```

## 🔗 Superset 연동

Superset 프론트엔드의 AI 채팅 컴포넌트는 다음 경로로 MCP 클라이언트와 통신합니다:

```
Superset Frontend → Superset Backend API → MCP Client → OpenRouter → AI Model
                                      ↓
                                   MCP Server (Superset 데이터 접근)
```

## � 로러깅 및 모니터링

### 구조화된 로깅 레벨

- **DEBUG**: 원시 JSON-RPC 요청/응답 전문
- **INFO**: 도구 호출 결과 요약 및 표준화 정보
- **WARNING**: 파싱 실패나 예상치 못한 응답 형식
- **ERROR**: 네트워크 오류나 JSON-RPC 에러

### 로그 예시
```json
{
  "timestamp": "2024-12-16T10:30:00Z",
  "level": "INFO",
  "message": "MCP Tool Call Completed",
  "extra": {
    "tool_name": "list_dashboards",
    "server": "superset",
    "result_type": "success",
    "data_type": "list",
    "success": true,
    "metadata": {"count": 25, "truncated": false}
  }
}
```

## 🐛 트러블슈팅

### 1. MCP 클라이언트 연결 실패
```bash
# 컨테이너 상태 확인
docker-compose ps mcp-client

# 로그 확인 (구조화된 로깅)
docker-compose logs mcp-client | grep "ERROR\|WARNING"

# 헬스 체크로 서버 상태 확인
curl http://localhost:8000/health
```

### 2. OpenRouter API 오류
- API 키가 올바른지 확인
- 계정 크레딧이 충분한지 확인
- 모델명이 정확한지 확인 (`GET /models`로 지원 모델 확인)

### 3. MCP 서버 연결 실패
```bash
# 모든 MCP 서버 상태 확인
curl http://localhost:8000/mcp/servers

# 특정 서버 직접 확인
curl http://localhost:5008/health
```

### 4. 응답 표준화 문제
```bash
# 디버그 정보 확인
curl http://localhost:8000/debug/mcp-logs

# 특정 도구 직접 테스트
curl -X POST http://localhost:8000/mcp/tools/list_dashboards \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 🔒 보안 고려사항

- OpenRouter API 키를 안전하게 관리하세요
- 프로덕션 환경에서는 CORS 설정을 적절히 구성하세요
- 네트워크 접근 제한을 고려하세요

## 📈 성능 최적화

### LLM 컨텍스트 최적화
- 큰 리스트는 자동으로 50개 항목으로 제한
- 컨텍스트 크기가 4000자를 초과하면 자동 압축
- 메타데이터를 통해 원본 데이터 크기 정보 제공

### 응답 처리 최적화
- 표준화된 형식으로 일관된 처리
- 에러 상황에 대한 명확한 분류
- 서버별 독립적인 에러 처리

### 모니터링
- 구조화된 로깅으로 성능 병목 지점 파악
- 도구별 실행 시간 및 성공률 추적
- 서버별 헬스 체크 자동화

## 🔄 향후 MCP 서버 추가 방법

### 1. 새 서버 등록
```python
# main.py의 MCPServerRegistry._initialize_default_servers()에 추가
weather_url = os.getenv("WEATHER_MCP_URL")
if weather_url:
    self.servers["weather"] = MCPClient(weather_url, "weather")
```

### 2. 환경 변수 설정
```bash
# docker/.env에 추가
WEATHER_MCP_URL=http://weather-mcp:8080
```

### 3. 자동 통합
- 새 서버의 도구들이 자동으로 `/mcp/tools`에 포함
- 표준화된 응답 처리 자동 적용
- 구조화된 로깅 자동 활성화
- LLM 컨텍스트 최적화 자동 적용

### 4. 테스트
```bash
# 새 서버 상태 확인
curl http://localhost:8000/mcp/servers

# 새 서버의 도구 목록 확인
curl http://localhost:8000/mcp/tools
```