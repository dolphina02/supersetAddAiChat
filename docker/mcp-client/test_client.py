#!/usr/bin/env python3
"""
MCP Client 테스트 스크립트

이 스크립트는 MCP 클라이언트가 올바르게 작동하는지 테스트합니다.
"""

import asyncio
import json
import sys
from typing import Dict, Any

import httpx


async def test_mcp_client(base_url: str = "http://localhost:8000") -> None:
    """MCP 클라이언트 테스트"""
    
    async with httpx.AsyncClient() as client:
        print(f"🧪 MCP 클라이언트 테스트 시작: {base_url}")
        
        # 1. 헬스 체크
        try:
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print("✅ 헬스 체크 성공")
                print(f"   응답: {response.json()}")
            else:
                print(f"❌ 헬스 체크 실패: {response.status_code}")
                return
        except Exception as e:
            print(f"❌ 헬스 체크 연결 실패: {e}")
            return
        
        # 2. 모델 목록 확인
        try:
            response = await client.get(f"{base_url}/models")
            if response.status_code == 200:
                models = response.json()
                print("✅ 모델 목록 조회 성공")
                print(f"   기본 모델: {models.get('default')}")
                print(f"   사용 가능한 모델 수: {len(models.get('models', []))}")
            else:
                print(f"❌ 모델 목록 조회 실패: {response.status_code}")
        except Exception as e:
            print(f"❌ 모델 목록 조회 오류: {e}")
        
        # 3. MCP 도구 목록 확인
        try:
            response = await client.get(f"{base_url}/mcp/tools")
            if response.status_code == 200:
                tools = response.json()
                print("✅ MCP 도구 목록 조회 성공")
                print(f"   사용 가능한 도구 수: {len(tools.get('tools', []))}")
            else:
                print(f"⚠️  MCP 도구 목록 조회 실패: {response.status_code}")
                print("   (MCP 서버가 실행되지 않았을 수 있습니다)")
        except Exception as e:
            print(f"⚠️  MCP 도구 목록 조회 오류: {e}")
        
        # 4. 채팅 테스트 (OpenRouter API 키가 있는 경우)
        chat_payload = {
            "messages": [
                {"role": "user", "content": "안녕하세요! 간단한 테스트 메시지입니다."}
            ],
            "model": "qwen/qwen-2.5-7b-instruct",
            "temperature": 0.7,
            "max_tokens": 100
        }
        
        try:
            response = await client.post(
                f"{base_url}/chat",
                json=chat_payload,
                timeout=30.0
            )
            if response.status_code == 200:
                chat_response = response.json()
                print("✅ 채팅 테스트 성공")
                print(f"   AI 응답: {chat_response.get('response', 'N/A')[:100]}...")
                print(f"   사용된 모델: {chat_response.get('model', 'N/A')}")
            else:
                print(f"⚠️  채팅 테스트 실패: {response.status_code}")
                error_detail = response.text
                if "OpenRouter API key not configured" in error_detail:
                    print("   💡 OpenRouter API 키가 설정되지 않았습니다.")
                    print("   docker/.env 파일에 OPENROUTER_API_KEY를 설정하세요.")
                else:
                    print(f"   오류 내용: {error_detail}")
        except Exception as e:
            print(f"⚠️  채팅 테스트 오류: {e}")
        
        print("\n🎉 테스트 완료!")


async def test_superset_integration(superset_url: str = "http://localhost:8088") -> None:
    """Superset 연동 테스트"""
    
    async with httpx.AsyncClient() as client:
        print(f"\n🔗 Superset 연동 테스트: {superset_url}")
        
        # Superset MCP Client API 테스트
        try:
            response = await client.get(f"{superset_url}/api/v1/mcp_client/health")
            if response.status_code == 200:
                print("✅ Superset MCP Client API 연결 성공")
            else:
                print(f"❌ Superset MCP Client API 연결 실패: {response.status_code}")
        except Exception as e:
            print(f"❌ Superset 연결 오류: {e}")
            print("   💡 Superset이 실행 중인지 확인하세요.")


if __name__ == "__main__":
    # 명령행 인자로 URL 지정 가능
    mcp_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    superset_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8088"
    
    asyncio.run(test_mcp_client(mcp_url))
    asyncio.run(test_superset_integration(superset_url))