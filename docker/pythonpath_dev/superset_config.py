# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information regarding
# copyright ownership.  The ASF licenses this file to you under
# the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License.  You may
# obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

# Superset 커스텀 설정

# ---------------------------------------------------
# 언어 설정
# ---------------------------------------------------
# 기본 언어를 한국어로 설정
BABEL_DEFAULT_LOCALE = "ko"

# 사용 가능한 언어 목록 (한국어와 영어)
LANGUAGES = {
    "en": {"flag": "us", "name": "English"},
    "ko": {"flag": "kr", "name": "Korean"},
}

# ---------------------------------------------------
# 데이터베이스 설정 (선택사항)
# ---------------------------------------------------
# 환경 변수로 설정되므로 보통 여기서 설정 안 함
# 필요시 아래 주석 해제:
# import os
# SQLALCHEMY_DATABASE_URI = os.getenv(
#     "SQLALCHEMY_DATABASE_URI",
#     f"postgresql://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}"
#     f"@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}/{os.getenv('DATABASE_DB')}"
# )

# ---------------------------------------------------
# Redis 캐시 설정 (선택사항)
# ---------------------------------------------------
# 환경 변수로 설정되므로 보통 여기서 설정 안 함
# 필요시 아래 주석 해제:
# CACHE_CONFIG = {
#     "CACHE_TYPE": "RedisCache",
#     "CACHE_REDIS_HOST": os.getenv("REDIS_HOST", "redis"),
#     "CACHE_REDIS_PORT": int(os.getenv("REDIS_PORT", 6379)),
#     "CACHE_REDIS_DB": 1,
#     "CACHE_DEFAULT_TIMEOUT": 86400,
# }
# DATA_CACHE_CONFIG = CACHE_CONFIG

# ---------------------------------------------------
# 브랜딩 설정 (로고, 앱 이름)
# ---------------------------------------------------
# 앱 이름 변경
APP_NAME = "My Analytics"

# 로고 이미지 경로 (static 폴더 경로)
APP_ICON = "/static/assets/images/custom-logo.png"

# 로고 클릭 시 이동할 경로 (None이면 홈으로)
LOGO_TARGET_PATH = None

# 로고에 마우스 올렸을 때 툴팁
LOGO_TOOLTIP = "My Analytics Platform"

# 로고 오른쪽에 표시할 텍스트 (선택사항)
# LOGO_RIGHT_TEXT = ""

# ---------------------------------------------------
# MCP Client 설정 (AI Assistant)
# ---------------------------------------------------
# MCP 클라이언트 URL (AI 어시스턴트 백엔드)
MCP_CLIENT_URL = "http://mcp-client:8000"

# ---------------------------------------------------
# MCP Server 설정 (내장 MCP 서버)
# ---------------------------------------------------
import os

# MCP 서버 활성화
ENABLE_MCP_SERVER = True

# MCP 서버 포트 (내부 통신용)
MCP_SERVER_PORT = 5008

# MCP 서버 호스트
MCP_SERVER_HOST = "0.0.0.0"

# MCP 개발 사용자 (인증 우회용)
MCP_DEV_USERNAME = os.getenv("MCP_DEV_USERNAME", "admin")

# ---------------------------------------------------
# 기타 커스텀 설정
# ---------------------------------------------------
# 필요한 추가 설정을 여기에 작성
