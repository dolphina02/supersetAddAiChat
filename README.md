# Apache Superset with AI Assistant

🤖 **AI-Enhanced Data Visualization Platform** - Apache Superset integrated with intelligent AI assistant for natural language data exploration and visualization.

> 🇰🇷 **한국어 문서**: [README_KO.md](./README_KO.md) | 🇺🇸 **English**: README.md

## 🚀 What's New

This is Apache Superset enhanced with a powerful AI Assistant that allows you to:

- **Natural Language Queries**: Ask questions about your data in plain English
- **Intelligent Chart Generation**: Create visualizations through conversational AI
- **Real-time Data Exploration**: Get instant insights with streaming responses
- **Multi-LLM Support**: Works with GPT-4, Claude, and other leading AI models

> 📖 **Original Apache Superset Documentation**: [ORIGINAL_SUPERSET_README.md](./ORIGINAL_SUPERSET_README.md)

## 🎯 Key Features

### AI Assistant Capabilities
- **Dashboard Management**: List, create, and manage dashboards through natural language
- **Chart Creation**: Generate charts with simple descriptions like "show sales by region"
- **Data Exploration**: Query datasets and get formatted table results
- **SQL Execution**: Run SQL queries with AI assistance and safety validation
- **Real-time Streaming**: Get progressive responses with live tool execution updates

### Technical Architecture
- **MCP Protocol**: Model Context Protocol for secure AI-to-data connections
- **Streaming Interface**: Real-time responses with Server-Sent Events
- **Multi-Model Support**: OpenRouter integration for various AI providers
- **Type-Safe Implementation**: Full TypeScript frontend with Python type hints

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   React UI      │    │   MCP Client     │    │   MCP Server    │
│   (Frontend)    │◄──►│   (Streaming)    │◄──►│   (Superset)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                        │                        │
        │                        │                        │
   ┌────▼────┐              ┌────▼────┐              ┌────▼────┐
   │ AiChat  │              │ FastAPI │              │ Flask   │
   │Component│              │ Server  │              │ Backend │
   └─────────┘              └─────────┘              └─────────┘
```

## 🛠️ Quick Start

### Prerequisites
- Docker and Docker Compose
- OpenRouter API key (for AI functionality)

### 1. Clone and Setup
```bash
git clone https://github.com/dolphina02/supersetAddAiChat.git
cd supersetAddAiChat
```

### 2. Configure Environment
```bash
# Copy and edit environment file
cp docker/.env.example docker/.env

# Add your OpenRouter API key
echo "OPENROUTER_API_KEY=your-api-key-here" >> docker/.env
```

### 3. Start Services
```bash
# Start all services
docker-compose up -d

# Check service health
curl http://localhost:8088/health  # Superset
curl http://localhost:8000/health  # MCP Client
```

### 4. Access the Application
- **Superset UI**: http://localhost:8088
- **AI Chat**: Available in the top navigation bar
- **Default Login**: admin/admin

## 🔧 Detailed Implementation

### MCP Server Architecture

The MCP (Model Context Protocol) Server runs inside the Superset container and provides 21+ tools for data operations:

**Location**: `superset/mcp_service/`

**Key Components**:
#### Core Tools
- **Dashboard Tools**: `list_dashboards`, `get_dashboard_info`, `generate_dashboard`
- **Chart Tools**: `list_charts`, `get_chart_data`, `generate_chart`, `update_chart`
- **Dataset Tools**: `list_datasets`, `get_dataset_info`
- **SQL Tools**: `execute_sql`, `open_sql_lab_with_context`
- **System Tools**: `get_instance_info`, `health_check`

#### Tool Registration System
```python
# superset/mcp_service/server.py
@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """Dynamically discover and register all MCP tools"""
    return discover_mcp_tools()

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute tools with proper error handling and validation"""
    return await execute_mcp_tool(name, arguments)
```

#### Schema Validation
All tools use Pydantic schemas for input/output validation:
```python
# Example: Chart generation schema
class GenerateChartRequest(BaseModel):
    dataset_id: Union[int, str]
    config: Union[XYChartConfig, TableChartConfig]
    chart_name: Optional[str] = None
    save_chart: bool = False
```

### MCP Client Architecture

The MCP Client is a FastAPI-based streaming service that bridges AI models with Superset data.

**Location**: `docker/mcp-client/`

#### Core Components

**1. Streaming Client (`main.py`)**
```python
class StreamingMCPClient:
    """Handles MCP protocol communication with real-time streaming"""
    
    async def stream_tool_execution(self, tool_name: str, arguments: Dict) -> AsyncGenerator[StreamChunk, None]:
        """Execute MCP tools with streaming progress updates"""
        
    def _extract_mcp_content(self, mcp_result: Any) -> Any:
        """Extract clean data from MCP protocol wrappers"""
        
    def _truncate_large_data(self, data: Any, max_rows: int = 50) -> Any:
        """Prevent context length issues with large datasets"""
```

**2. OpenAI Integration**
```python
class StreamingOpenRouterClient:
    """OpenAI-compatible client with function calling support"""
    
    async def stream_chat_with_tools(self, messages: List[Dict], tools: List[Dict]) -> AsyncGenerator[StreamChunk, None]:
        """Stream chat responses with real-time tool execution"""
```

#### Data Flow Architecture

**1. Request Processing**
```
User Message → System Message + Tools → OpenAI API → Tool Calls → MCP Server → Results → Formatted Response
```

**2. Streaming Implementation**
```python
# Server-Sent Events format
async def generate_streaming_response():
    async for chunk in openai_stream:
        if chunk.type == "tool_calls":
            # Execute MCP tools with progress updates
            for tool_call in chunk.tool_calls:
                async for progress in mcp_client.stream_tool_execution():
                    yield f"data: {progress.json()}\n\n"
```

#### Error Handling & Context Management

**Context Length Protection**:
```python
def _truncate_large_data(self, data: Any, max_rows: int = 50, max_chars: int = 50000) -> Any:
    """Intelligent data truncation to prevent OpenAI context limits"""
    if isinstance(data, dict) and "data" in data:
        if len(data["data"]) > max_rows:
            return {
                **data,
                "data": data["data"][:max_rows],
                "_truncated": True,
                "_truncation_message": f"⚠️ Showing {max_rows} of {len(data['data'])} rows"
            }
```

**Robust Error Recovery**:
```python
try:
    # MCP tool execution
    result = await session.call_tool(request)
except Exception as e:
    if "context length" in str(e).lower():
        yield StreamChunk(
            type="error", 
            error="⚠️ Dataset too large. Please use more specific filters."
        )
```

### Frontend Integration

**Location**: `superset-frontend/src/components/AiChat/`

#### React Component Architecture
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
          // Show tool execution progress
          break;
        case 'content':
          // Stream AI response content
          break;
        case 'tool_result':
          // Display formatted results
          break;
      }
    };
  }, []);
};
```

#### Markdown Rendering
AI responses are rendered with full markdown support including tables, code blocks, and lists:

```typescript
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';

// Render AI messages with markdown
<ReactMarkdown
  remarkPlugins={[remarkGfm]}
  components={{
    code({ inline, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '');
      return !inline && match ? (
        <SyntaxHighlighter language={match[1]} {...props}>
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code className={className} {...props}>{children}</code>
      );
    },
  }}
>
  {message.text}
</ReactMarkdown>
```

**Supported Markdown Features:**
- ✅ Tables with proper styling
- ✅ Code blocks with syntax highlighting
- ✅ Inline code formatting
- ✅ Lists (ordered and unordered)
- ✅ Headers, blockquotes, links
- ✅ Real-time streaming rendering

#### Table Formatting System
The client automatically formats data responses as markdown tables:

```python
def _format_tool_result_for_display(self, tool_result: Dict) -> str:
    """Convert MCP results to user-friendly markdown tables"""
    
    if "dashboards" in content:
        table_lines = ["| 제목 | ID | 상태 | 생성일 |", "|------|----|----|--------|"]
        for dash in content["dashboards"]:
            title = dash.get("dashboard_title", "")[:30]
            status = "공개" if dash.get("published") else "비공개"
            table_lines.append(f"| {title} | {dash['id']} | {status} | {dash['created_on'][:10]} |")
        return "\n".join(table_lines)
```

## 🔒 Security & Configuration

### Environment Variables
```bash
# AI Configuration
OPENROUTER_API_KEY=your-openrouter-key
DEFAULT_MODEL=openai/gpt-4o-mini
MCP_CLIENT_URL=http://mcp-client:8000

# Development Settings
DEBUG=true                    # Enable detailed logging
FLASK_DEBUG=true             # Flask development mode
SUPERSET_LOG_LEVEL=info      # Application log level
```

### Security Features
- **Input Validation**: All MCP tools use Pydantic schemas
- **SQL Injection Protection**: Parameterized queries and validation
- **Rate Limiting**: Built-in request throttling
- **Authentication**: Superset RBAC integration
- **Data Truncation**: Automatic large dataset handling

## 🧪 Development & Testing

### Running Tests
```bash
# MCP Server tests
pytest tests/unit_tests/mcp_service/

# MCP Client tests  
cd docker/mcp-client && python -m pytest

# Frontend tests
cd superset-frontend && npm test
```

### Development Workflow
```bash
# Start development environment
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

# Watch MCP client logs
docker logs -f superset_mcp_client

# Access development tools
curl http://localhost:8000/mcp/tools  # List available tools
curl http://localhost:5008/health     # MCP server health
```

## 📊 Usage Examples

### Natural Language Queries
```
"Show me all dashboards created this month"
"Create a bar chart of sales by region using the sales dataset"
"What datasets are available in the examples database?"
"Execute a query to get top 10 customers by revenue"
```

### API Integration
```python
# Direct MCP tool usage
import httpx

async def call_mcp_tool():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/chat",
            json={
                "messages": [{"role": "user", "content": "List all dashboards"}],
                "model": "openai/gpt-4o-mini"
            }
        )
```

## 🤝 Contributing

This project extends Apache Superset with AI capabilities. For contributing:

1. **AI Assistant Features**: Focus on `docker/mcp-client/` and `superset/mcp_service/`
2. **Frontend Integration**: Work in `superset-frontend/src/components/AiChat/`
3. **Follow Superset Guidelines**: See [ORIGINAL_SUPERSET_README.md](./ORIGINAL_SUPERSET_README.md)

### Code Standards
- **Python**: Type hints required, MyPy compliant
- **TypeScript**: Strict typing, no `any` types
- **Testing**: Unit tests for all new MCP tools
- **Documentation**: Update this README for new features

## 📝 License

This project maintains the same Apache License 2.0 as the original Apache Superset.

## 🔗 Links

- **Original Apache Superset**: [ORIGINAL_SUPERSET_README.md](./ORIGINAL_SUPERSET_README.md)
- **Setup Guide**: [AI_ASSISTANT_SETUP.md](./AI_ASSISTANT_SETUP.md)
- **MCP Protocol**: [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- **OpenRouter**: [OpenRouter API Documentation](https://openrouter.ai/docs)

---

**Built with ❤️ on top of Apache Superset** | **AI-Enhanced Data Visualization**