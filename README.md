# MCP学术文献RAG服务器

基于Model Context Protocol (MCP)的学术文献检索增强生成(RAG)服务器，提供文献OCR处理、自动分类、智能检索与AI交互功能。

## ⚠️ 开发状态警告

**当前项目状态：原型开发中 - 尚未完成**

本项目目前处于积极开发阶段，尚未准备好用于生产环境。API、功能和结构可能会发生重大变化。欢迎贡献和反馈，但请注意当前的不稳定性。

## MCP集成功能

作为MCP服务器，本项目将提供以下MCP功能：

### 工具 (Tools)

Currently implemented tools (some are placeholders):

-   **`echo`**
    *   **Description:** Echoes back the input message.
    *   **MCP Command Parameters (`tool_params`):**
        *   `message` (string, required): The message to echo.
    *   **Example Result:** `{"echo_response": "your message"}`

-   **`document_search`**
    *   **Description:** Searches a persistent list of academic documents. The document store is loaded from `documents.json` on server start and saved to this file when new documents are added. Documents added via the `add_document_to_store` tool will persist across server restarts. The search is case-insensitive and covers document titles, abstracts, and keywords.
    *   **MCP Command Parameters (`tool_params`):**
        *   `query` (string, required): The search term or question.
        *   `max_results` (integer, optional, default: 3): The maximum number of search results to return.
    *   **Example MCP Command (for POST to `/mcp_command` or STDIO input):**
        ```json
        {
            "command": "execute_tool",
            "tool_name": "document_search",
            "tool_params": {
                "query": "healthcare",
                "max_results": 1
            }
        }
        ```
    *   **Example Result (in `data` field of `tool_result` SSE event or STDIO output):**
        ```json
        {
            "search_results": [
                {
                    "id": "doc101",
                    "title": "Exploring Artificial Intelligence in Modern Healthcare",
                    "abstract": "This paper discusses the impact of AI on diagnostics and treatment, highlighting machine learning advancements.",
                    "keywords": ["ai", "healthcare", "diagnostics", "machine learning", "treatment"]
                }
            ],
            "query_received": "healthcare"
        }
        ```
        (Note: The actual results will depend on the query and the content of the `documents.json` file.)

-   **`add_document_to_store`**
    *   **Description:** Adds a new document to the persistent document store (saved in `documents.json`) from its raw text content. A title is automatically derived from the first line of the text. Keywords are optional. Added documents will be available after server restarts.
    *   **MCP Command Parameters (`tool_params`):**
        *   `document_text` (string, required): The full text content of the document.
        *   `keywords` (string, optional): Comma-separated list of keywords.
    *   **Example MCP Command:**
        ```json
        {
            "command": "execute_tool",
            "tool_name": "add_document_to_store",
            "tool_params": {
                "document_text": "First line as derived title.\nThis is the rest of the document content, which will be stored as the abstract.",
                "keywords": "text processing, auto-title, mcp"
            }
        }
        ```
    *   **Example Result (in `data` field of `tool_result` SSE event or STDIO output):**
        Success:
        ```json
        {
            "message": "Document added successfully from text.",
            "document_id": "doc201", // Example ID, this ID will be persistent.
            "derived_title": "First line as derived title."
        }
        ```
        Error (e.g., empty text):
        ```json
        {
            "error": "Missing required parameter: document_text cannot be empty."
        }
        ```

- **(Planned) 文献搜索工具**：Through keyword, topic, or semantic queries to find relevant documents from a larger, persistent database.
- **(Planned) 文献处理工具**：上传、OCR处理和结构化文献内容
- **(Planned) 聊天会话工具**：管理基于文献内容的对话交互

### 资源 (Resources)

The server can register and serve various resources. Resource `content` is not included in the initial capabilities discovery but can be fetched using the `get_resource` command (see "MCP Commands" section).

-   **Sample Resource:**
    *   **URI:** `mcp://resources/literature/doc123`
    *   **Name:** Sample Document 123
    *   **Description:** A sample academic paper providing placeholder content. Its content includes fields like `title`, `author`, `abstract`, etc.
    *   This resource is registered by default and can be retrieved using the `get_resource` command.

- **(Planned) 文献资源**：访问已处理文献的结构化内容
- **(Planned) 会话历史**：查看和继续之前的交互记录
- **(Planned) 文献集合**：管理主题相关的文献分组

### 提示模板 (Prompts)

The server can register and provide definitions for various prompt templates. Prompt definitions (including name, description, and arguments) can be retrieved using the `get_prompt_definition` command (see "MCP Commands" section). The actual execution of prompts (i.e., generating text based on a template and arguments) is a planned feature.

-   **Sample Prompt: `summarize_document_abstract`**
    *   **Description:** Generates a brief summary of a document's abstract. Requires the document's resource URI.
    *   **Arguments:**
        *   `document_uri` (string, required): The MCP URI of the document resource (e.g., `mcp://resources/literature/doc123`) whose abstract needs summarizing.
    *   This prompt is registered by default. Its full definition can be fetched using the `get_prompt_definition` command.
    *   **Execution Example:**
        ```json
        {
            "command": "execute_prompt",
            "name": "summarize_document_abstract",
            "arguments": {
                "document_uri": "mcp://resources/literature/doc123"
            }
        }
        ```
    *   **Expected Result (from `prompt_result` event or STDIO):**
        ```json
        {
            "mcp_protocol_version": "1.0",
            "status": "success",
            "prompt_name": "summarize_document_abstract",
            "result": {
                "summary": "Summary of abstract: This paper explores the fundamental principles of sciences that don't actually exist."
            }
        }
        ```

- **(Planned) 文献分析提示**：用于分析和总结文献内容
- **(Planned) 比较研究提示**：比较多篇文献的内容和观点
- **(Planned) 论文撰写辅助提示**：帮助构建论文结构和引用

## 系统功能

本系统是一个基于API的学术文献OCR电子化、自动分类与智能检索平台，采用流水线架构处理学术文献，将扫描文档转换为结构化电子格式，并提供基于向量数据库的智能检索与自然语言对话功能。

- **文档OCR处理**：将扫描的学术文献转换为可搜索文本
- **文档结构识别**：自动识别标题、摘要、章节等结构元素
- **内容自动分类**：基于内容对文献进行主题分类和标签标注
- **格式转换**：生成Markdown和PDF输出，保留原文排版
- **向量化存储**：将文档内容转换为向量表示并存入向量数据库
- **智能检索**：通过自然语言查询检索相关文献内容
- **知识对话**：基于文献内容回答用户问题，提供引用来源
- **持久化存储**：学术文献元数据和内容（或其引用）通过 `documents.json` 文件进行持久化存储，确保服务器重启后数据不丢失。

## 开发路线图

- [x] 基础文档处理流水线实现
- [x] 命令行工具开发
- [x] 基本RAG功能实现
- [x] **MCP服务器接口实现** (STDIO transport, basic tool execution, basic SSE transport)
- [/] MCP工具 (Tools) 功能开发 (echo, document_search, add_document_to_store now use persistent storage)
- [/] MCP资源 (Resources) 功能开发 (sample 'literature/doc123' registered, `get_resource` command implemented)
- [x] MCP提示 (Prompts) 功能开发 (sample 'summarize_document_abstract' definition and execution implemented)
- [/] Web界面开发 (interactive viewer: can execute echo, summarize_abstract, document_search, and add_document_to_store)
- [x] 高级RAG功能增强 (document_search and add_document_to_store now use a persistent JSON-based document store 'documents.json')
- [ ] 安全性和性能优化
- [ ] 文档与教程完善

## Basic Usage (STDIO)

The server can be run using `app.py` and defaults to STDIO transport.

1.  **Start the server:**
    ```bash
    python3 app.py
    ```

2.  **Interact with the server via STDIN/STDOUT:**
    Once the server is running, you can send commands to its standard input and receive JSON responses on its standard output.

    *   **Discover capabilities:**
        Send the plain text command:
        ```
        discover
        ```
        The server will respond with a JSON object detailing its capabilities, including available tools. Example (structure may vary):
        ```json
        {"mcp_protocol_version": "1.0", "server_name": "Academic RAG Server", "server_version": "0.1.0", "tools": [...], "resources": [], "prompts": []}
        ```

    *   **Execute the echo tool:**
        Send the following JSON command:
        ```json
        {"command": "execute_tool", "tool_name": "echo", "tool_params": {"message": "Hello MCP"}}
        ```
        Receive (example):
        ```json
        {"mcp_protocol_version": "1.0", "status": "success", "tool_name": "echo", "result": {"echo_response": "Hello MCP"}}
        ```

    *   **Stop the server:**
        Send the plain text command:
        ```
        quit
        ```

## SSE Usage

### Starting the Server in SSE Mode

To use Server-Sent Events (SSE) for communication, run the server with the `--transport sse` flag. You can also specify a port (defaults to 3000):

```bash
python3 app.py --transport sse --port 8000
```

### Interacting over SSE

Once the server is running in SSE mode (e.g., on port 8000):

1.  **Listen for events (including initial capabilities):**
    Use `curl` or a similar tool to connect to the SSE endpoint. The server will stream events here.
    The correct path for SSE is `/mcp_sse`.
    ```bash
    curl -N http://localhost:8000/mcp_sse
    ```
    You should immediately receive an `event: capabilities` with the server details. Subsequent events (like tool results or errors) will appear here.

2.  **Send commands:**
    Commands are sent via HTTP POST requests to the `/mcp_command` endpoint.
    ```bash
    # Example: Execute the "echo" tool
    curl -X POST -H "Content-Type: application/json" \
         -d '{"command": "execute_tool", "tool_name": "echo", "tool_params": {"message": "Hello from SSE client"}}' \
         http://localhost:8000/mcp_command
    ```
    The POST request will receive an HTTP 202 Accepted response: `{"status": "accepted", "message": "Tool execution initiated."}`.
    The actual result of the "echo" tool will then be broadcast as an SSE event (e.g., `event: tool_result`) to all connected SSE clients (including your `curl -N` session).

## MCP Commands

This section details common MCP commands supported by the server across different transports.

### `get_resource`

*   **Description:** Retrieves a registered MCP resource, including its content.
*   **Parameters (in JSON payload):**
    *   `command` (string, required): Must be `"get_resource"`.
    *   `uri` (string, required): The URI of the resource to retrieve.
*   **Example MCP Command (for POST to `/mcp_command` or STDIO input):**
    ```json
    {
        "command": "get_resource",
        "uri": "mcp://resources/literature/doc123"
    }
    ```
*   **Success Response (STDIO or `resource_data` SSE event data):**
    The full resource object, including its `uri`, `name`, `description`, `mime_type`, and `content`.
    Example for `mcp://resources/literature/doc123`:
    ```json
    {
        "mcp_protocol_version": "1.0",
        "status": "success",
        "uri": "mcp://resources/literature/doc123",
        "resource_data": {
            "uri": "mcp://resources/literature/doc123",
            "name": "Sample Document 123",
            "description": "A sample academic paper providing placeholder content.",
            "mime_type": "application/json",
            "content": {
                "title": "Foundations of Fictional Science",
                "author": "Dr. A.I. Construct",
                "publication_year": 2024,
                "abstract": "This paper explores the fundamental principles of sciences that don't actually exist.",
                "body_paragraphs": [
                    "Paragraph 1 discussing a made-up theory.",
                    "Paragraph 2 with some fabricated data.",
                    "Paragraph 3 concluding with speculative insights."
                ],
                "keywords": ["fiction", "dummy data", "mcp resource"]
            }
        }
    }
    ```
*   **Error Responses (STDIO or `resource_error` SSE event data):**
    *   If resource not found: `{"mcp_protocol_version": "1.0", "status": "error", "uri": "<requested_uri>", "error": "Resource not found"}`
    *   If URI missing: `{"mcp_protocol_version": "1.0", "status": "error", "error": "Missing URI for get_resource"}`

### `get_prompt_definition`

*   **Description:** Retrieves the definition (name, description, arguments) of a registered MCP prompt.
*   **Parameters (in JSON payload):**
    *   `command` (string, required): Must be `"get_prompt_definition"`.
    *   `name` (string, required): The name of the prompt to retrieve.
*   **Example MCP Command (for POST to `/mcp_command` or STDIO input):**
    ```json
    {
        "command": "get_prompt_definition",
        "name": "summarize_document_abstract"
    }
    ```
*   **Success Response (STDIO or `prompt_definition_data` SSE event data):**
    Contains the prompt's full definition.
    Example for `summarize_document_abstract`:
    ```json
    {
        "mcp_protocol_version": "1.0",
        "status": "success",
        "name": "summarize_document_abstract",
        "prompt_definition": {
            "name": "summarize_document_abstract",
            "description": "Generates a brief summary of a document's abstract. Requires the document's resource URI.",
            "arguments": [
                {
                    "name": "document_uri",
                    "type": "string",
                    "description": "The MCP URI of the document resource (e.g., mcp://resources/literature/doc123) whose abstract needs summarizing.",
                    "required": true
                }
            ]
        }
    }
    ```
*   **Error Responses (STDIO or `prompt_definition_error` SSE event data):**
    *   If prompt not found: `{"mcp_protocol_version": "1.0", "status": "error", "name": "<requested_name>", "error": "Prompt not found"}`
    *   If name missing: `{"mcp_protocol_version": "1.0", "status": "error", "error": "Missing name for get_prompt_definition"}`

### `execute_prompt`

*   **Description:** Executes a registered MCP prompt with the provided arguments. (Currently, only "summarize_document_abstract" has implemented execution logic).
*   **Parameters (in JSON payload):**
    *   `command` (string, required): Must be `"execute_prompt"`.
    *   `name` (string, required): The name of the prompt to execute.
    *   `arguments` (object, required): An object containing key-value pairs for the arguments required by the prompt.
*   **Example MCP Command (for POST to `/mcp_command` or STDIO input to execute "summarize_document_abstract"):**
    ```json
    {
        "command": "execute_prompt",
        "name": "summarize_document_abstract",
        "arguments": {
            "document_uri": "mcp://resources/literature/doc123"
        }
    }
    ```
*   **Success Response (STDIO or `prompt_result` SSE event data):**
    Contains the result of the prompt execution.
    Example for "summarize_document_abstract":
    ```json
    {
        "mcp_protocol_version": "1.0",
        "status": "success",
        "prompt_name": "summarize_document_abstract",
        "result": {
            "summary": "Summary of abstract: This paper explores the fundamental principles of sciences that don't actually exist."
        }
    }
    ```
*   **Error Responses (STDIO or `prompt_error` SSE event data):**
    *   Prompt not found: `{"mcp_protocol_version": "1.0", "status": "error", "name": "<prompt_name>", "error": "Prompt not found"}`
    *   Argument missing: `{"mcp_protocol_version": "1.0", "status": "error", "name": "<prompt_name>", "error": "Missing <argument_name> argument for <prompt_name>"}` (e.g., "Missing document_uri argument for summarize_document_abstract")
    *   Resource not found (if applicable to prompt): `{"mcp_protocol_version": "1.0", "status": "error", "name": "<prompt_name>", "error": "Resource not found: <uri>"}`
    *   Abstract not found (if applicable): `{"mcp_protocol_version": "1.0", "status": "error", "name": "<prompt_name>", "error": "Abstract not found in resource: <uri>"}`
    *   Prompt execution not implemented: `{"mcp_protocol_version": "1.0", "status": "error", "name": "<prompt_name>", "error": "Prompt execution not implemented yet"}`

## Web Interface

A web interface is available to display the server's capabilities and interact with some of its features. It currently allows:
*   Viewing available tools, resources, and prompts.
*   Executing the "echo" tool by providing a message.
*   Executing the "summarize_document_abstract" prompt by providing a document URI.
*   Executing the "document_search" tool by providing a query and maximum number of results.
    *   **Adding a new document to the persistent store (`documents.json`) by providing its text content and optional keywords.**

Results of executions are displayed on the page, updated via Server-Sent Events.

**How to Access:**

1.  Start the MCP server in SSE mode (as this also enables the web server functionality on the same port):
    ```bash
    python3 app.py --transport sse --port 8000
    ```
    (Replace `8000` with your desired port if different).

2.  Open your web browser and navigate to:
    ```
    http://localhost:8000/
    ```
    (Or `http://127.0.0.1:8000/`)

The page will connect to the server's SSE endpoint and display the information it receives.