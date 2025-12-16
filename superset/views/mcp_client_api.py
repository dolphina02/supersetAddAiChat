# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
MCP Client API endpoints for Superset AI Assistant
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from flask import current_app, request, Response
from flask_appbuilder.api import BaseApi, expose, safe
from flask_appbuilder.security.decorators import has_access_api
from marshmallow import fields, Schema

logger = logging.getLogger(__name__)


class ChatMessageSchema(Schema):
    role = fields.String(required=True)
    content = fields.String(required=True)


class ChatRequestSchema(Schema):
    messages = fields.List(fields.Nested(ChatMessageSchema), required=True)
    model = fields.String(missing="qwen/qwen-2.5-7b-instruct")
    temperature = fields.Float(missing=0.7)
    max_tokens = fields.Integer(missing=2000)


class ChatResponseSchema(Schema):
    response = fields.String()
    model = fields.String()
    usage = fields.Dict(missing=None)


class McpClientApi(BaseApi):
    """API for integrated MCP Client functionality"""

    resource_name = "mcp_client"
    allow_browser_login = True

    def __init__(self) -> None:
        super().__init__()
        self.mcp_client_url = current_app.config.get(
            "MCP_CLIENT_URL", "http://mcp-client:8000"
        )

    @expose("/chat", methods=["POST"])
    @safe
    def chat(self) -> Any:
        """
        Streaming chat with AI assistant via MCP client
        ---
        post:
          summary: Send chat message to AI assistant (streaming)
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/ChatRequestSchema'
          responses:
            200:
              description: Streaming chat response
              content:
                text/event-stream:
                  schema:
                    type: string
            400:
              $ref: '#/components/responses/400'
            500:
              $ref: '#/components/responses/500'
        """
        from flask import Response, stream_template
        import httpx
        
        try:
            # Validate request data
            schema = ChatRequestSchema()
            data = schema.load(request.json)
            
            # Ensure we use GPT-4o-mini for function calling support
            if not data.get('model') or data.get('model') == 'qwen/qwen-2.5-7b-instruct':
                data['model'] = 'openai/gpt-4o-mini'

            def generate_stream():
                """Generate streaming response from MCP client"""
                try:
                    with httpx.Client(timeout=60.0) as client:
                        with client.stream(
                            "POST",
                            f"{self.mcp_client_url}/chat",
                            json=data,
                            headers={
                                "Content-Type": "application/json",
                                "Accept": "text/event-stream"
                            }
                        ) as response:
                            
                            if response.status_code != 200:
                                error_data = {
                                    "type": "error",
                                    "error": f"MCP client error: {response.status_code}",
                                    "timestamp": datetime.now().isoformat()
                                }
                                yield f"data: {json.dumps(error_data)}\n\n"
                                return
                            
                            # Stream the response
                            for chunk in response.iter_text():
                                if chunk:
                                    yield chunk
                                    
                except Exception as e:
                    logger.error(f"Streaming error: {e}")
                    error_data = {
                        "type": "error", 
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"

            return Response(
                generate_stream(),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': '*',
                }
            )

        except Exception as e:
            logger.error(f"Unexpected error in streaming MCP client API: {e}")
            return self.response_500(message="스트리밍 채팅에서 오류가 발생했습니다.")

    @expose("/models", methods=["GET"])
    @safe
    def models(self) -> Dict[str, Any]:
        """
        Get available AI models
        ---
        get:
          summary: List available AI models
          responses:
            200:
              description: List of available models
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      models:
                        type: array
                        items:
                          type: object
                      default:
                        type: string
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self.mcp_client_url}/models")
                response.raise_for_status()
                
                result = response.json()
                return self.response(200, result=result)

        except Exception as e:
            logger.error(f"Failed to get models from MCP client: {e}")
            # Return fallback models
            fallback_models = {
                "models": [
                    {
                        "id": "qwen/qwen-2.5-7b-instruct",
                        "name": "Qwen 2.5 7B Instruct",
                        "description": "기본 AI 모델",
                        "parameters": "7B",
                        "vram_required": "16GB"
                    }
                ],
                "default": "qwen/qwen-2.5-7b-instruct"
            }
            return self.response(200, result=fallback_models)

    @expose("/health", methods=["GET"])
    @safe
    def health(self) -> Dict[str, Any]:
        """
        Check MCP client health
        ---
        get:
          summary: Health check for MCP client
          responses:
            200:
              description: Health status
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.mcp_client_url}/health")
                response.raise_for_status()
                
                result = response.json()
                result["status"] = "connected"
                return self.response(200, result=result)

        except Exception as e:
            logger.warning(f"MCP client health check failed: {e}")
            return self.response(200, result={
                "status": "disconnected",
                "error": str(e),
                "mcp_client_url": self.mcp_client_url
            })