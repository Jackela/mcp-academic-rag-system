#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP服务器实现 - 骨架代码，开发中

注意：本模块是计划中的功能，尚未完全实现。
"""

import logging
import sys
import json
from typing import Any, Dict, List, Optional, Type
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import functools # For functools.partial
import urllib.parse # For parsing URL in handler

# 日志配置
logger = logging.getLogger(__name__)


# Define SSE_PATH and COMMAND_PATH for clarity
SSE_PATH = "/mcp_sse"
COMMAND_PATH = "/mcp_command"


class _McpSseHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for MCP SSE transport."""

    def __init__(self, mcp_server_instance: 'McpServer', *args, **kwargs):
        self.mcp_server = mcp_server_instance
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handles GET requests, primarily for establishing SSE connections."""
        if self.path == SSE_PATH:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()

            logger.info(f"SSE client connected: {self.client_address}")
            self.mcp_server.sse_clients.append(self.wfile)

            try:
                # Send initial capabilities
                logger.debug(f"SSE client {self.client_address}: Sending capabilities.")
                capabilities = {
                    "mcp_protocol_version": "1.0",
                    "server_name": self.mcp_server.name,
                    "server_version": self.mcp_server.version,
                    "tools": [
                        {"name": t_name, "description": t_info.get("description"), "schema": t_info.get("schema")}
                        for t_name, t_info in self.mcp_server.tools.items()
                    ],
                    "resources": [res_info for res_info in self.mcp_server.resources.values()],
                    "prompts": [prompt_info for prompt_info in self.mcp_server.prompts.values()]
                }
                capabilities_json = json.dumps(capabilities)
                self.wfile.write(f"event: capabilities\ndata: {capabilities_json}\n\n".encode('utf-8'))
                self.wfile.flush()
                logger.debug(f"SSE client {self.client_address}: Capabilities sent.")

                # Keep the connection alive and send periodic keep-alive comments
                keep_alive_interval = 15 # seconds
                while self.mcp_server.running:
                    if self.wfile.closed:
                        logger.info(f"SSE client stream closed for {self.client_address} (detected by wfile.closed).")
                        break
                    try:
                        logger.debug(f"SSE client {self.client_address}: Sending keepalive.")
                        self.wfile.write(": keepalive\n\n".encode('utf-8'))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
                        logger.info(f"SSE client {self.client_address} disconnected during keepalive: {type(e).__name__}.")
                        break # Client disconnected
                    except Exception as e:
                        logger.error(f"Error sending keepalive to SSE client {self.client_address}: {e}", exc_info=True)
                        break # Unknown error, terminate connection handler for safety

                    # Wait for the next keep-alive or until server stops
                    # Use a loop with shorter waits to be responsive to self.mcp_server.running
                    for _ in range(int(keep_alive_interval / 0.5)): # Check every 0.5s
                        if not self.mcp_server.running:
                            break
                        threading.Event().wait(0.5)
                    if not self.mcp_server.running:
                         logger.info(f"SSE client {self.client_address}: Server stopping, closing connection handler.")
                         break
                
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                logger.info(f"SSE client disconnected (pipe error): {self.client_address}")
            except Exception as e:
                logger.error(f"Error in SSE connection for {self.client_address}: {e}", exc_info=True)
            finally:
                if self.wfile in self.mcp_server.sse_clients:
                    self.mcp_server.sse_clients.remove(self.wfile)
                logger.info(f"SSE client connection closed: {self.client_address}")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Handles POST requests, intended for receiving MCP commands."""
        if self.path == COMMAND_PATH:
            content_length_str = self.headers.get('Content-Length')
            if not content_length_str:
                logger.warning(f"POST request from {self.client_address} to {self.path} missing Content-Length.")
                self.send_response(411) # Length Required
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Content-Length required"}).encode('utf-8'))
                return

            content_length = int(content_length_str)
            post_data_bytes = self.rfile.read(content_length)
            
            try:
                request_data = json.loads(post_data_bytes.decode('utf-8'))
                logger.info(f"Received POST on {COMMAND_PATH} from {self.client_address} with JSON data: {request_data}")
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received in POST from {self.client_address} to {self.path}: {post_data_bytes.decode('utf-8')[:200]}")
                self.send_response(400) # Bad Request
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode('utf-8'))
                return

            command = request_data.get("command")
            tool_name = request_data.get("tool_name")
            tool_params = request_data.get("tool_params", {})

            if command == "execute_tool":
                if not tool_name:
                    logger.warning(f"execute_tool command from {self.client_address} missing 'tool_name'.")
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Missing 'tool_name' for execute_tool command"}).encode('utf-8'))
                    return

                # Asynchronously execute the tool command. McpServer will handle broadcasting.
                # Use a thread to avoid blocking the HTTP handler
                threading.Thread(target=self.mcp_server.execute_tool_command, 
                                 args=(tool_name, tool_params), daemon=True).start()
                
                self.send_response(202) # Accepted
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "accepted", "message": f"Tool '{tool_name}' execution initiated."}).encode('utf-8'))
            else:
                logger.warning(f"Unknown command '{command}' received in POST from {self.client_address}.")
                self.send_response(400) # Bad Request
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unknown command"}).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use application's logger."""
        # Log actual HTTP requests at INFO, less important at DEBUG
        if "GET /mcp_sse" in format or "POST /mcp_command" in format :
             logger.info(f"HTTP: {self.address_string()} - {format % args}")
        else:
             logger.debug(f"HTTP: {self.address_string()} - {format % args}")


class McpServer:
    """
    MCP服务器类 - 实现MCP规范的服务器
    
    注意：此类是计划中的功能，尚未完全实现
    """
    
    def __init__(self, name: str, version: str):
        """
        初始化MCP服务器
        
        Args:
            name: 服务器名称
            version: 服务器版本
        """
        self.name = name
        self.version = version
        self.tools = {}
        self.resources = {}
        self.prompts = {}
        self.running = False # Initialized self.running
        self.sse_clients = [] # List to store client output streams (wfile)
        self.http_server_thread = None
        self.http_server = None
        logger.info(f"创建MCP服务器: {name} v{version}")

        # Register default "echo" tool
        self.register_tool(
            name="echo",
            description="Echo the input",
            schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"]
            },
            callback=lambda params: {"echo_response": params.get("message", "")}
        )

        # Register "document_search" tool
        self.register_tool(
            name="document_search",
            description="Searches academic documents based on a query.",
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "max_results": {"type": "integer", "description": "Maximum number of results to return.", "default": 3}
                },
                "required": ["query"]
            },
            callback=_execute_document_search # Reference to the callback function
        )
    
    def register_tool(self, name: str, description: str, schema: Dict[str, Any], callback: callable) -> None:
        """
        注册MCP工具
        
        Args:
            name: 工具名称
            description: 工具描述
            schema: 工具的JSON Schema
            callback: 工具执行回调函数
        """
        self.tools[name] = {
            'name': name,
            'description': description,
            'schema': schema,
            'callback': callback
        }
        logger.info(f"注册MCP工具: {name}")
    
    def register_resource(self, uri: str, name: str, description: str, 
                         mime_type: Optional[str] = None) -> None:
        """
        注册MCP资源
        
        Args:
            uri: 资源URI
            name: 资源名称
            description: 资源描述
            mime_type: MIME类型(可选)
        """
        self.resources[uri] = {
            'uri': uri,
            'name': name,
            'description': description,
            'mime_type': mime_type
        }
        logger.info(f"注册MCP资源: {name} ({uri})")
    
    def register_prompt(self, name: str, description: str, 
                        arguments: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        注册MCP提示模板
        
        Args:
            name: 提示模板名称
            description: 提示模板描述
            arguments: 提示模板参数(可选)
        """
        self.prompts[name] = {
            'name': name,
            'description': description,
            'arguments': arguments or []
        }
        logger.info(f"注册MCP提示模板: {name}")
    
    def start(self, transport_type: str, **kwargs) -> None:
        """
        启动MCP服务器
        
        Args:
            transport_type: 传输类型 ('stdio'或'sse')
            **kwargs: 其他传输参数
        """
        logger.info(f"启动MCP服务器 (传输类型: {transport_type})")
        self.running = True # Set self.running to True

        if transport_type == 'stdio':
            logger.info("Starting McpServer in STDIO mode.")
            try:
                while self.running:
                    line = sys.stdin.readline()
                    line = line.strip() # Strip whitespace
                    if not line or line == "quit":
                        logger.info("Received quit signal or empty line, stopping STDIO listener.")
                        break
                    
                    if line == "discover": # Simple "discover" command for now
                        logger.info("Received capabilities discovery request.")
                        capabilities = {
                            "mcp_protocol_version": "1.0",
                            "server_name": self.name,
                            "server_version": self.version,
                            # Refined tools list for capabilities: ensure no callback is included
                            "tools": [
                                {
                                    "name": t_name,
                                    "description": t_info.get("description"),
                                    "schema": t_info.get("schema")
                                } for t_name, t_info in self.tools.items()
                            ],
                            "resources": [res_info for res_info in self.resources.values()],
                            "prompts": [prompt_info for prompt_info in self.prompts.values()]
                        }
                        capabilities_json = json.dumps(capabilities)
                        print(capabilities_json)
                        sys.stdout.flush()
                    else:
                        # Try to parse as JSON for other commands
                        try:
                            request_data = json.loads(line)
                            logger.debug(f"Received MCP JSON message: {request_data}")

                            if isinstance(request_data, dict) and request_data.get("command") == "execute_tool":
                                logger.info("Received execute_tool request.")
                                tool_name = request_data.get("tool_name")
                                tool_params = request_data.get("tool_params", {})
                                response = {}

                                if tool_name in self.tools:
                                    tool_definition = self.tools[tool_name]
                                    callback = tool_definition.get('callback')

                                    if callable(callback):
                                        try:
                                            result = callback(tool_params)
                                            response = {
                                                "mcp_protocol_version": "1.0",
                                                "status": "success",
                                                "tool_name": tool_name,
                                                "result": result
                                            }
                                        except Exception as e:
                                            logger.exception(f"Error executing tool '{tool_name}': {e}")
                                            response = {
                                                "mcp_protocol_version": "1.0",
                                                "status": "error",
                                                "tool_name": tool_name,
                                                "error": str(e)
                                            }
                                    else:
                                        logger.error(f"Tool '{tool_name}' has no callable callback.")
                                        response = {
                                            "mcp_protocol_version": "1.0",
                                            "status": "error",
                                            "tool_name": tool_name,
                                            "error": "Tool has no callback"
                                        }
                                else:
                                    logger.warning(f"Tool '{tool_name}' not found.")
                                    response = {
                                        "mcp_protocol_version": "1.0",
                                        "status": "error",
                                        "error": f"Tool '{tool_name}' not found"
                                    }
                                
                                print(json.dumps(response))
                                sys.stdout.flush()
                            else:
                                logger.warning(f"Unknown command or malformed request: {request_data}")
                                response = {
                                    "mcp_protocol_version": "1.0",
                                    "status": "error",
                                    "error": "Unknown command or malformed request"
                                }
                                print(json.dumps(response))
                                sys.stdout.flush()

                        except json.JSONDecodeError:
                            logger.warning(f"Received non-JSON message or unknown simple command: {line}")
                            response = {
                                "mcp_protocol_version": "1.0",
                                "status": "error",
                                "error": "Invalid JSON message"
                            }
                            print(json.dumps(response))
                            sys.stdout.flush()
            except KeyboardInterrupt:
                logger.info("STDIO listener interrupted by user.")
            finally:
                logger.info("STDIO listener stopped.")
        elif transport_type == 'sse':
            port = kwargs.get('port')
            if not port:
                logger.error("SSE transport requires a port to be specified.")
                self.running = False 
                return

            logger.info(f"Initializing SSE transport on port {port}")
            
            handler_class_with_instance = functools.partial(_McpSseHandler, self)
            
            self.http_server = HTTPServer(('', port), handler_class_with_instance)
            self.http_server_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
            self.http_server_thread.start()
            logger.info(f"SSE HTTP server started on port {port}. Listening on {SSE_PATH} for SSE and {COMMAND_PATH} for commands.")
            # self.running is already True. Main thread of app.py will keep process alive.
        else:
            logger.error(f"Unsupported transport type: {transport_type}")
            # Set running to False as server cannot start with unsupported type
            self.running = False 
            return # Exit if transport type is not supported

        # TODO: Further implementation for MCP protocol handling might be needed here
        
        # For STDIO, the loop above blocks. For SSE, the http_server_thread runs in background.
        # Do not set self.running to False here if SSE server is active.
        if transport_type == 'stdio':
            self.running = False 
    
    def stop(self) -> None:
        """停止MCP服务器"""
        logger.info("McpServer stopping...") 
        self.running = False # Signal all loops (including SSE handler loops) to stop

        if self.http_server:
            logger.info("Stopping SSE HTTP server...")
            self.http_server.shutdown() 
            self.http_server.server_close() 
            if self.http_server_thread:
                self.http_server_thread.join(timeout=5) 
            self.http_server = None
            self.http_server_thread = None
        
        # Clear SSE clients
        # Note: individual client handler loops should also detect self.running == False
        # and exit, which then removes them from sse_clients.
        # Clearing here is a final measure.
        for client_wfile in self.sse_clients[:]: # Iterate over a copy
             try:
                 client_wfile.close() # Attempt to close any remaining client connections
             except Exception as e:
                 logger.debug(f"Error closing an SSE client stream: {e}")
        self.sse_clients.clear()
        logger.info("McpServer stopped.")

# 示例用法，未来将扩展
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    server = McpServer("example-server", "0.1.0")
    
    server_mode = "sse" # Change to "stdio" to test STDIO mode

    if server_mode == "sse":
        server.start(transport_type="sse", port=3000)
        if server.running: # Check if server started successfully (e.g., port was available)
            logger.info("SSE Server is running. Press Ctrl+C to stop.")
            try:
                # Keep the main thread alive, otherwise the daemon HTTP server thread will also exit
                # if this script is the main program.
                while server.running: 
                    threading.Event().wait(1) # Keep main thread alive
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received from console.")
            finally:
                logger.info("Main thread initiating server stop sequence.")
                server.stop()
        else:
            logger.error("Server failed to start in SSE mode.")
    else:
        server.start(transport_type="stdio")
        # For stdio, start() is blocking, so it will run until "quit" or EOF.
    
    logger.info("McpServer example finished.")


# Callback function for document_search tool (defined at module level or as a static/member method)
def _execute_document_search(params: dict) -> dict:
    query = params.get("query")
    # max_results is int, ensure conversion if it comes as string from some JSON parsers, though schema says integer.
    # Default value from schema is handled by tool caller or can be re-verified here.
    max_results_str = params.get("max_results", "3") # Default to 3 if not provided
    
    try:
        max_results = int(max_results_str)
    except ValueError:
        # Handle case where max_results is not a valid integer, though schema should prevent this.
        # For robustness, return an error or use a default.
        logger.warning(f"Invalid max_results value '{max_results_str}', defaulting to 3.")
        max_results = 3

    if not query or not query.strip():
        # This error case should ideally be caught by schema validation if fully implemented by the client
        # or a validation layer before calling the callback.
        # For now, the callback handles it as per instructions.
        return {"error": "Missing or empty query parameter"}

    dummy_results = []
    for i in range(1, max_results + 1):
        dummy_results.append({
            "id": f"doc_{i}",
            "title": f"Dummy Document {i} about '{query}'",
            "snippet": f"This is a snippet for document {i} which matches the query: '{query}'.",
            "score": round(1.0 / i, 2)
        })
    return {"search_results": dummy_results, "query_received": query}
