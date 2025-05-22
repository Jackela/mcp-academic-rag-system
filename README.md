# MCP学术文献RAG服务器

基于Model Context Protocol (MCP)的学术文献检索增强生成(RAG)服务器，提供文献OCR处理、自动分类、智能检索与AI交互功能。

## ⚠️ 开发状态警告

**当前项目状态：原型开发中 - 尚未完成**

本项目目前处于积极开发阶段，尚未准备好用于生产环境。API、功能和结构可能会发生重大变化。欢迎贡献和反馈，但请注意当前的不稳定性。

## MCP集成功能

作为MCP服务器，本项目将提供以下MCP功能：

### 工具 (Tools)

- **文献搜索工具**：通过关键词、主题或语义查询查找相关文献
- **文献处理工具**：上传、OCR处理和结构化文献内容
- **聊天会话工具**：管理基于文献内容的对话交互

### 资源 (Resources)

- **文献资源**：访问已处理文献的结构化内容
- **会话历史**：查看和继续之前的交互记录
- **文献集合**：管理主题相关的文献分组

### 提示模板 (Prompts)

- **文献分析提示**：用于分析和总结文献内容
- **比较研究提示**：比较多篇文献的内容和观点
- **论文撰写辅助提示**：帮助构建论文结构和引用

## 系统功能

本系统是一个基于API的学术文献OCR电子化、自动分类与智能检索平台，采用流水线架构处理学术文献，将扫描文档转换为结构化电子格式，并提供基于向量数据库的智能检索与自然语言对话功能。

- **文档OCR处理**：将扫描的学术文献转换为可搜索文本
- **文档结构识别**：自动识别标题、摘要、章节等结构元素
- **内容自动分类**：基于内容对文献进行主题分类和标签标注
- **格式转换**：生成Markdown和PDF输出，保留原文排版
- **向量化存储**：将文档内容转换为向量表示并存入向量数据库
- **智能检索**：通过自然语言查询检索相关文献内容
- **知识对话**：基于文献内容回答用户问题，提供引用来源

## 开发路线图

- [x] 基础文档处理流水线实现
- [x] 命令行工具开发
- [x] 基本RAG功能实现
- [x] **MCP服务器接口实现** (STDIO transport, basic tool execution)
- [ ] MCP工具 (Tools) 功能开发
- [ ] MCP资源 (Resources) 功能开发
- [ ] MCP提示 (Prompts) 功能开发
- [ ] Web界面开发
- [ ] 高级RAG功能增强
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