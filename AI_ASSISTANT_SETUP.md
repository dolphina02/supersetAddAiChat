# Superset AI Assistant 설정 가이드

이 문서는 Apache Superset에 AI 어시스턴트 기능을 추가하는 전체 과정을 설명합니다.

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐    ┌──────────────┐
│  Superset UI    │───▶│  Superset API    │───▶│   MCP Client    │───▶│  OpenRouter  │
│  (AI Chat)      │    │  (mcp_client.py) │    │  (FastAPI)      │    │  (LLM API)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘    └──────────────┘
                                │                        │
                                │                        ▼
                                │               ┌─────────────────┐
                                └──────────────▶│  Superset MCP   │
                                                │     Server      │
                                                └─────────────────┘
```

## 🚀 빠른 시작

### 1. OpenRouter API 키 발급

1. [OpenRouter](https://openrouter.ai) 회원가입
2. API 키 발급
3. `docker/.env` 파일에 추가:

```bash
OPENROUTER_API_KEY=your_api_key_here
```

### 2. Docker Compose로 실행

```bash
# MCP 프로필과 함께 모든 서비스 실행
docker-compose --profile mcp up -d

# 빌드가 필요한 경우
docker-compose --profile mcp build
docker-compose --profile mcp up -d
```

### 3. 접속 확인

- **Superset UI**: http://localhost:8088 (admin/admin)
- **MCP Client**: http://localhost:8000
- **AI 채팅**: Superset UI 우측 하단 채팅 버튼

## 📁 주요 파일 구조

```
superset/
├── superset-frontend/src/components/AiChat/
│   └── index.tsx                           # AI 채팅 컴포넌트
├── superset/views/api/
│   └── mcp_client.py                       # MCP 클라이언트 API
├── superset/initialization/__init__.py     # API 등록
├── docker/mcp-client/                      # MCP 클라이언트 서비스
│   ├── Dockerfile
│   ├── main.py                            # FastAPI 서버
│   ├── requirements.txt
│   └── README.md
├── docker/.env                            # 환경 변수
├── docker/pythonpath_dev/superset_config.py  # Superset 설정
└── docker-compose.yml                     # Docker 구성
```

## 🛠️ 주요 컴포넌트

### 1. AI 채팅 컴포넌트 (`AiChat`)

**위치**: `superset-frontend/src/components/AiChat/index.tsx`

**기능**:
- 플로팅 채팅 버튼
- 패널 모드 / 플로팅 모드 전환
- 실시간 채팅 인터페이스
- 테마 연동 (다크/라이트 모드)

**주요 특징**:
- Kiro IDE 스타일 UI
- TypeScript로 작성
- Ant Design 컴포넌트 사용
- 반응형 디자인

### 2. MCP 클라이언트 API (`McpClientApi`)

**위치**: `superset/views/api/mcp_client.py`

**엔드포인트**:
- `POST /api/v1/mcp_client/chat` - AI 채팅
- `GET /api/v1/mcp_client/models` - 모델 목록
- `GET /api/v1/mcp_client/health` - 헬스 체크

**기능**:
- Superset 인증 연동
- MCP 클라이언트 프록시
- 오류 처리 및 로깅

### 3. MCP 클라이언트 서비스

**위치**: `docker/mcp-client/main.py`

**기능**:
- OpenRouter API 연동
- Superset MCP 서버 통신
- RESTful API 제공
- CORS 지원

**지원 모델**:
- Qwen 2.5 7B Instruct (기본값)
- Llama 3.1 8B Instruct
- Mistral 7B Instruct
- DeepSeek Coder 6.7B

## 🔧 설정 옵션

### 환경 변수 (`docker/.env`)

```bash
# MCP Client Configuration
OPENROUTER_API_KEY=your_api_key_here
MCP_CLIENT_URL=http://mcp-client:8000
```

### Superset 설정 (`docker/pythonpath_dev/superset_config.py`)

```python
# 언어 설정
BABEL_DEFAULT_LOCALE = "ko"
LANGUAGES = {
    "en": {"flag": "us", "name": "English"},
    "ko": {"flag": "kr", "name": "Korean"},
}

# MCP Client 설정
MCP_CLIENT_URL = "http://mcp-client:8000"
```

## 🧪 테스트

### 1. MCP 클라이언트 테스트

```bash
# 컨테이너 내에서 실행
docker exec -it superset_mcp_client python test_client.py

# 또는 로컬에서 실행
cd docker/mcp-client
python test_client.py
```

### 2. 수동 테스트

```bash
# MCP 클라이언트 헬스 체크
curl http://localhost:8000/health

# Superset API 테스트
curl http://localhost:8088/api/v1/mcp_client/health

# 채팅 테스트
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"안녕하세요"}]}'
```

## 🐛 트러블슈팅

### 1. AI 채팅이 응답하지 않는 경우

**확인사항**:
1. OpenRouter API 키가 설정되었는지 확인
2. MCP 클라이언트 컨테이너가 실행 중인지 확인
3. 네트워크 연결 상태 확인

```bash
# 컨테이너 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs mcp-client
docker-compose logs superset
```

### 2. MCP 서버 연결 오류

```bash
# Superset MCP 서버 상태 확인
curl http://localhost:5008/health

# MCP 서버 로그 확인
docker-compose logs superset | grep -i mcp
```

### 3. 프론트엔드 빌드 오류

```bash
# 프론트엔드 재빌드
docker-compose exec superset-node npm run build

# 또는 컨테이너 재시작
docker-compose restart superset-node
```

## 🔒 보안 고려사항

1. **API 키 관리**: OpenRouter API 키를 안전하게 보관
2. **네트워크 보안**: 프로덕션에서는 내부 네트워크만 허용
3. **인증**: Superset 사용자 인증과 연동
4. **로깅**: 민감한 정보가 로그에 기록되지 않도록 주의

## 📈 성능 최적화

1. **모델 선택**: 용도에 맞는 적절한 크기의 모델 선택
2. **캐싱**: 자주 사용되는 응답 캐싱
3. **타임아웃**: 적절한 타임아웃 설정
4. **로드 밸런싱**: 높은 부하 시 여러 인스턴스 운영

## 🚀 향후 개선 사항

1. **로컬 모델 지원**: GPU 서버에서 직접 모델 실행
2. **대화 기록**: 사용자별 채팅 히스토리 저장
3. **고급 MCP 기능**: 더 많은 Superset 기능과 연동
4. **다국어 지원**: 더 많은 언어 지원
5. **음성 인터페이스**: 음성 입력/출력 지원

## 📞 지원

문제가 발생하면 다음을 확인하세요:

1. [Superset 공식 문서](https://superset.apache.org/docs/)
2. [OpenRouter API 문서](https://openrouter.ai/docs)
3. [MCP 프로토콜 문서](https://modelcontextprotocol.io/)
4. 로그 파일 및 오류 메시지