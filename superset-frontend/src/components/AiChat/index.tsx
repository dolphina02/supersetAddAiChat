/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { useState, useRef, useEffect } from 'react';
import { css, useTheme } from '@apache-superset/core/ui';
import { Button, Input } from '@superset-ui/core/components';
import { 
  CloseOutlined, 
  MessageOutlined, 
  SendOutlined, 
  ExpandOutlined,
  CompressOutlined,
  MinusOutlined 
} from '@ant-design/icons';

interface Message {
  id: string;
  text: string;
  isUser: boolean;
  timestamp: Date;
}

interface AiChatProps {
  onSendMessage?: (message: string) => Promise<string>;
}

const AiChat = ({ onSendMessage }: AiChatProps) => {
  const theme = useTheme();
  const [isOpen, setIsOpen] = useState(false);
  const [isPanelMode, setIsPanelMode] = useState(false); // 패널 모드 vs 플로팅 모드
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      text: '안녕하세요! Superset AI 어시스턴트입니다. 대시보드나 차트에 대해 궁금한 것이 있으시면 언제든 물어보세요.',
      isUser: false,
      timestamp: new Date(),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 패널 모드일 때 메인 콘텐츠 영역에만 패딩 추가
  useEffect(() => {
    // 여러 가능한 선택자로 메인 콘텐츠 영역 찾기
    const selectors = [
      '.ant-layout-content',
      '[class*="ant-layout-content"]',
      'main',
      '[role="main"]'
    ];
    
    let layoutContent: HTMLElement | null = null;
    for (const selector of selectors) {
      layoutContent = document.querySelector(selector);
      if (layoutContent) break;
    }

    if (layoutContent) {
      if (isPanelMode && isOpen) {
        layoutContent.style.paddingRight = '400px';
        layoutContent.style.transition = 'padding-right 0.3s ease';
      } else {
        layoutContent.style.paddingRight = '0';
      }
    }

    // 컴포넌트 언마운트 시 정리
    return () => {
      if (layoutContent) {
        layoutContent.style.paddingRight = '0';
      }
    };
  }, [isPanelMode, isOpen]);

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputValue,
      isUser: true,
      timestamp: new Date(),
    };

    // 사용자 메시지 추가
    setMessages(prev => [...prev, userMessage]);
    
    // 빈 AI 메시지 추가 (스트리밍으로 채워질 예정)
    const aiMessageId = (Date.now() + 1).toString();
    const initialAiMessage: Message = {
      id: aiMessageId,
      text: '🤔 생각 중...',
      isUser: false,
      timestamp: new Date(),
    };
    
    setMessages(prev => [...prev, initialAiMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      // 스트리밍 AI 응답
      const response = onSendMessage 
        ? await onSendMessage(inputValue)
        : await callMcpClient(inputValue);

      // 최종 응답으로 업데이트
      setMessages(prev => 
        prev.map(msg => 
          msg.id === aiMessageId 
            ? { ...msg, text: response, timestamp: new Date() }
            : msg
        )
      );
    } catch (error) {
      // 에러 메시지로 업데이트
      setMessages(prev => 
        prev.map(msg => 
          msg.id === aiMessageId 
            ? { 
                ...msg, 
                text: '죄송합니다. 오류가 발생했습니다. 다시 시도해주세요.',
                timestamp: new Date() 
              }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const callMcpClient = async (message: string): Promise<string> => {
    return new Promise((resolve, reject) => {
      try {
        // 스트리밍 응답을 위한 fetch 요청
        fetch('/api/v1/mcp_client/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
          },
          body: JSON.stringify({
            messages: [
              {
                role: 'user',
                content: message,
              },
            ],
            model: 'openai/gpt-4o-mini',
            temperature: 0.7,
            max_tokens: 2000,
          }),
        }).then(response => {
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }

          const reader = response.body?.getReader();
          if (!reader) {
            throw new Error('Response body is not readable');
          }

          let fullResponse = '';
          let currentToolMessage = '';

          const readStream = () => {
            reader.read().then(({ done, value }) => {
              if (done) {
                resolve(fullResponse || '응답을 받지 못했습니다.');
                return;
              }

              // 텍스트 디코딩
              const chunk = new TextDecoder().decode(value);
              const lines = chunk.split('\n');

              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  try {
                    const data = JSON.parse(line.slice(6));
                    
                    switch (data.type) {
                      case 'tool_start':
                        currentToolMessage = `🔧 ${data.tool_name} 실행 중...`;
                        // 실시간으로 메시지 업데이트 (선택사항)
                        updateCurrentMessage(currentToolMessage);
                        break;
                        
                      case 'progress':
                        currentToolMessage = data.content || '처리 중...';
                        updateCurrentMessage(currentToolMessage);
                        break;
                        
                      case 'tool_result':
                        currentToolMessage = `✅ ${data.tool_name} 완료`;
                        updateCurrentMessage(currentToolMessage);
                        break;
                        
                      case 'content':
                        fullResponse += data.content || '';
                        // 실시간으로 응답 내용 업데이트
                        updateCurrentMessage(fullResponse);
                        break;
                        
                      case 'error':
                        console.error('스트리밍 오류:', data.error);
                        reject(new Error(data.error));
                        return;
                        
                      case 'done':
                        resolve(fullResponse || '응답 완료');
                        return;
                    }
                  } catch (parseError) {
                    console.warn('JSON 파싱 오류:', parseError, 'Line:', line);
                  }
                }
              }

              readStream(); // 다음 청크 읽기
            }).catch(reject);
          };

          readStream();
        }).catch(error => {
          console.error('MCP Client API 호출 실패:', error);
          // Fallback to simulation if MCP client is not available
          simulateAiResponse(message).then(resolve).catch(reject);
        });

      } catch (error) {
        console.error('스트리밍 설정 실패:', error);
        simulateAiResponse(message).then(resolve).catch(reject);
      }
    });
  };

  // 실시간 메시지 업데이트를 위한 헬퍼 함수
  const updateCurrentMessage = (content: string) => {
    setMessages(prev => {
      const newMessages = [...prev];
      const lastMessage = newMessages[newMessages.length - 1];
      
      // 마지막 메시지가 AI 메시지이고 로딩 중이면 업데이트
      if (lastMessage && !lastMessage.isUser) {
        lastMessage.text = content;
        lastMessage.timestamp = new Date();
      }
      
      return newMessages;
    });
  };

  const simulateAiResponse = async (message: string): Promise<string> => {
    // 실제 AI API 호출 대신 시뮬레이션 (fallback)
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    if (message.includes('대시보드')) {
      return '대시보드 관련 질문이시군요! 대시보드 생성, 편집, 공유에 대해 도움을 드릴 수 있습니다. 구체적으로 어떤 부분이 궁금하신가요?';
    }
    if (message.includes('차트')) {
      return '차트에 대한 질문이시네요! Superset에서는 다양한 차트 타입을 지원합니다. 어떤 종류의 차트를 만들고 싶으신가요?';
    }
    return `"${message}"에 대한 답변을 준비 중입니다. 좀 더 구체적인 질문을 해주시면 더 정확한 답변을 드릴 수 있어요!`;
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const chatButtonStyles = css`
    position: fixed;
    bottom: 24px;
    right: 24px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: ${theme.colorPrimary};
    border: none;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.3s ease;

    &:hover {
      background: ${theme.colorPrimaryHover};
      transform: scale(1.05);
    }

    .anticon {
      color: white;
      font-size: 24px;
    }
  `;

  const chatWindowStyles = css`
    position: fixed;
    ${isPanelMode ? `
      top: 48px;
      right: 0;
      width: 400px;
      height: calc(100vh - 48px);
      border-radius: 0;
      border-left: 1px solid ${theme.colorBorder};
    ` : `
      bottom: 90px;
      right: 24px;
      width: 380px;
      height: 500px;
      border-radius: 12px;
      border: 1px solid ${theme.colorBorder};
    `}
    background: ${theme.colorBgContainer};
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
    z-index: 1001;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `;

  const chatHeaderStyles = css`
    padding: 0 20px;
    background: ${theme.colorBgContainer};
    color: ${theme.colorText};
    border-bottom: 1px solid ${theme.colorBorderSecondary};
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
    height: 48px !important;
    min-height: 48px !important;
    max-height: 48px !important;
    flex-shrink: 0;
    box-sizing: border-box;
    line-height: 1;
  `;

  const headerButtonsStyles = css`
    display: flex;
    gap: 4px;
    align-items: center;
    height: 24px;
    flex-shrink: 0;
  `;

  const headerButtonStyle = css`
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: transparent;
    color: ${theme.colorText};
    cursor: pointer;
    border-radius: 4px;
    transition: background-color 0.2s ease;

    &:hover {
      background-color: ${theme.colorFillQuaternary};
    }

    .anticon {
      font-size: 14px;
    }
  `;

  const messagesStyles = css`
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  `;

  const messageStyles = (isUser: boolean) => css`
    display: flex;
    justify-content: ${isUser ? 'flex-end' : 'flex-start'};
  `;

  const messageBubbleStyles = (isUser: boolean) => css`
    max-width: 80%;
    padding: 12px 16px;
    border-radius: 18px;
    background: ${isUser ? theme.colorPrimary : theme.colorBgContainer};
    color: ${isUser ? 'white' : theme.colorText};
    font-size: 14px;
    line-height: 1.4;
    border: ${isUser ? 'none' : `1px solid ${theme.colorBorder}`};
  `;

  const inputAreaStyles = css`
    padding: 16px;
    border-top: 1px solid ${theme.colorBorder};
    display: flex;
    gap: 8px;
    align-items: flex-end;
  `;

  const inputStyles = css`
    flex: 1;
    border-radius: 20px;
    padding: 8px 16px;
    border: 1px solid ${theme.colorBorder};
    resize: none;
    max-height: 100px;
    min-height: 40px;

    &:focus {
      border-color: ${theme.colorPrimary};
      box-shadow: 0 0 0 2px ${theme.colorPrimary}20;
    }
  `;

  const sendButtonStyles = css`
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: ${theme.colorPrimary};
    border: none;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover:not(:disabled) {
      background: ${theme.colorPrimaryHover};
      transform: scale(1.05);
    }

    &:disabled {
      background: ${theme.colorBgContainer};
      opacity: 0.5;
      cursor: not-allowed;
    }

    .anticon {
      color: white;
      font-size: 16px;
    }
  `;

  return (
    <>
      {/* 채팅 버튼 - 패널 모드가 아닐 때만 표시 */}
      {!isPanelMode && (
        <Button
          css={chatButtonStyles}
          onClick={() => setIsOpen(!isOpen)}
          icon={<MessageOutlined />}
        />
      )}

      {/* 채팅 창 - 패널 모드이거나 플로팅 모드에서 열려있을 때 표시 */}
      {(isPanelMode || isOpen) && (
        <div css={chatWindowStyles}>
          {/* 헤더 */}
          <div css={chatHeaderStyles}>
            <span>AI Assistant</span>
            <div css={headerButtonsStyles}>
              <button
                css={headerButtonStyle}
                onClick={() => setIsPanelMode(!isPanelMode)}
                title={isPanelMode ? '플로팅 모드로 전환' : '패널 모드로 전환'}
              >
                {isPanelMode ? <CompressOutlined /> : <ExpandOutlined />}
              </button>
              <button
                css={headerButtonStyle}
                onClick={() => {
                  if (isPanelMode) {
                    setIsPanelMode(false);
                    setIsOpen(false);
                  } else {
                    setIsOpen(false);
                  }
                }}
                title={isPanelMode ? '최소화' : '닫기'}
              >
                {isPanelMode ? <MinusOutlined /> : <CloseOutlined />}
              </button>
            </div>
          </div>

          {/* 메시지 영역 */}
          <div css={messagesStyles}>
            {messages.map(message => (
              <div key={message.id} css={messageStyles(message.isUser)}>
                <div css={messageBubbleStyles(message.isUser)}>
                  {message.text}
                </div>
              </div>
            ))}
            {isLoading && (
              <div css={messageStyles(false)}>
                <div css={messageBubbleStyles(false)}>
                  AI가 답변을 생성 중입니다...
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 입력 영역 */}
          <div css={inputAreaStyles}>
            <Input.TextArea
              css={inputStyles}
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="메시지를 입력하세요..."
              autoSize={{ minRows: 1, maxRows: 3 }}
              disabled={isLoading}
            />
            <Button
              css={sendButtonStyles}
              onClick={handleSendMessage}
              disabled={!inputValue.trim() || isLoading}
              icon={<SendOutlined />}
            />
          </div>
        </div>
      )}
    </>
  );
};

export default AiChat;