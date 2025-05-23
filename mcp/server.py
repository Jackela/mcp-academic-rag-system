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
import os # Added for path operations

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
        """Handles GET requests, for SSE connections and serving index.html."""
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
                    "resources": [ # Exclude 'content' from capabilities
                        {k: v for k, v in res_info.items() if k != 'content'}
                        for res_info in self.mcp_server.resources.values()
                    ],
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
                    for _ in range(int(keep_alive_interval / 0.5)): 
                        if not self.mcp_server.running: break
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
        
        elif self.path == '/' or self.path == '/index.html':
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__)) 
                file_path = os.path.join(script_dir, '..', 'web', 'index.html') 
                
                if not os.path.exists(file_path):
                    self.send_error(404, "File Not Found: index.html")
                    logger.warning(f"index.html not found at expected path: {file_path}")
                    return

                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
                logger.info(f"Served index.html to {self.client_address}")
            except Exception as e:
                self.send_error(500, f"Server error serving index.html: {str(e)}")
                logger.error(f"Error serving index.html: {e}", exc_info=True)
        elif self.path == '/script.js':
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                file_path = os.path.join(script_dir, '..', 'web', 'script.js')
                if not os.path.exists(file_path):
                    self.send_error(404, "File Not Found: script.js")
                    logger.warning(f"script.js not found at expected path: {file_path}")
                    return
                self.send_response(200)
                self.send_header('Content-type', 'application/javascript')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
                logger.info(f"Served script.js to {self.client_address}")
            except Exception as e:
                self.send_error(500, f"Server error serving script.js: {str(e)}")
                logger.error(f"Error serving script.js: {e}", exc_info=True)
        else:
            self.send_error(404, 'File Not Found or Invalid Endpoint')

    def do_POST(self):
        if self.path == COMMAND_PATH:
            content_length_str = self.headers.get('Content-Length')
            if not content_length_str:
                logger.warning(f"POST request from {self.client_address} to {self.path} missing Content-Length.")
                self.send_response(411); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps({"error": "Content-Length required"}).encode('utf-8'))
                return

            content_length = int(content_length_str)
            post_data_bytes = self.rfile.read(content_length)
            
            try:
                request_data = json.loads(post_data_bytes.decode('utf-8'))
                logger.info(f"Received POST on {COMMAND_PATH} from {self.client_address} with JSON data: {request_data}")
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received in POST from {self.client_address} to {self.path}: {post_data_bytes.decode('utf-8')[:200]}")
                self.send_response(400); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode('utf-8'))
                return

            command = request_data.get("command")
            response_sent = False 
            
            if command == "execute_tool":
                tool_name = request_data.get("tool_name")
                if not tool_name:
                    self.send_response(400); self.send_header('Content-Type', 'application/json'); self.end_headers()
                    self.wfile.write(json.dumps({"error": "Missing 'tool_name' for execute_tool command"}).encode('utf-8'))
                    return
                tool_params = request_data.get("tool_params", {})
                threading.Thread(target=self.mcp_server.execute_tool_command, args=(tool_name, tool_params), daemon=True).start()
                self.send_response(202); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps({"status": "accepted", "message": f"Tool '{tool_name}' execution initiated."}).encode('utf-8'))
                response_sent = True

            elif command == "get_resource":
                resource_uri = request_data.get("uri")
                if not resource_uri:
                    self.send_response(400); self.send_header('Content-Type', 'application/json'); self.end_headers()
                    self.wfile.write(json.dumps({"error": "Missing 'uri' for get_resource command"}).encode('utf-8'))
                    return
                threading.Thread(target=self.mcp_server.get_resource_command, args=(resource_uri,), daemon=True).start()
                self.send_response(202); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps({"status": "accepted", "message": "Get resource request initiated."}).encode('utf-8'))
                response_sent = True
            
            elif command == "get_prompt_definition":
                prompt_name = request_data.get("name")
                if not prompt_name:
                    self.send_response(400); self.send_header('Content-Type', 'application/json'); self.end_headers()
                    self.wfile.write(json.dumps({"error": "Missing name for get_prompt_definition command"}).encode('utf-8'))
                    return
                threading.Thread(target=self.mcp_server.get_prompt_definition_command, args=(prompt_name,), daemon=True).start()
                self.send_response(202); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps({"status": "accepted", "message": "Get prompt definition request initiated."}).encode('utf-8'))
                response_sent = True

            elif command == "execute_prompt":
                prompt_name = request_data.get("name")
                prompt_args = request_data.get("arguments", {})
                if not prompt_name:
                    self.send_response(400); self.send_header('Content-Type', 'application/json'); self.end_headers()
                    self.wfile.write(json.dumps({"error": "Missing name for execute_prompt command"}).encode('utf-8'))
                    return
                threading.Thread(target=self.mcp_server.execute_prompt_command, args=(prompt_name, prompt_args), daemon=True).start()
                self.send_response(202); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps({"status": "accepted", "message": f"Prompt '{prompt_name}' execution initiated."}).encode('utf-8'))
                response_sent = True

            if not response_sent: 
                logger.warning(f"Unknown command '{command}' received in POST from {self.client_address}.")
                self.send_response(400); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps({"error": "Unknown command"}).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")

    def log_message(self, format: str, *args: Any) -> None:
        if "GET /mcp_sse" in format or \
           "POST /mcp_command" in format or \
           "GET / HTTP" in format or \
           "GET /index.html HTTP" in format or \
           "GET /script.js HTTP" in format:
             logger.info(f"HTTP: {self.address_string()} - {format % args}")
        else:
             logger.debug(f"HTTP: {self.address_string()} - {format % args}")


class McpServer:
    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        self.tools = {}
        self.resources = {}
        self.prompts = {}
        self.running = False 
        self.sse_clients = [] 
        self.http_server_thread = None
        self.http_server = None
        self.next_doc_id_counter = 200
        logger.info(f"创建MCP服务器: {name} v{version}")

        self.document_store_file = "documents.json"
        default_documents = [
            {
                "id": "doc101", "title": "Exploring Artificial Intelligence in Modern Healthcare",
                "abstract": "This paper discusses the impact of AI on diagnostics and treatment, highlighting machine learning advancements.",
                "keywords": ["ai", "healthcare", "diagnostics", "machine learning", "treatment"]
            },
            {
                "id": "doc102", "title": "The Future of Renewable Energy Sources",
                "abstract": "A comprehensive review of solar, wind, and geothermal energy technologies and their potential.",
                "keywords": ["renewable energy", "solar", "wind", "geothermal", "sustainability"]
            },
            {
                "id": "doc103", "title": "Quantum Computing: A New Paradigm",
                "abstract": "This article introduces the fundamental concepts of quantum computing and its applications.",
                "keywords": ["quantum computing", "qubits", "algorithms", "cryptography"]
            },
            {
                "id": "doc104", "title": "Advanced Machine Learning Techniques for NLP",
                "abstract": "Deep learning models and transformers are revolutionizing Natural Language Processing.",
                "keywords": ["machine learning", "nlp", "deep learning", "transformers", "ai"]
            }
        ]

        try:
            with open(self.document_store_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content: # Check for empty file
                    raise ValueError("File is empty")
                self.document_store = json.loads(content)
            logger.info(f"Loaded document store from {self.document_store_file}")
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"{self.document_store_file} not found, empty, or invalid JSON ({e}). Initializing with default documents and creating/overwriting the file.")
            self.document_store = default_documents
            try:
                with open(self.document_store_file, 'w', encoding='utf-8') as f:
                    json.dump(self.document_store, f, indent=4)
                logger.info(f"Saved default document store to {self.document_store_file}")
            except IOError as ioe:
                logger.error(f"Could not write initial document store to {self.document_store_file}: {ioe}")


        self.register_tool(
            name="echo",
            description="Echo the input",
            schema={"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
            callback=lambda params: {"echo_response": params.get("message", "")}
        )
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
            callback=self._execute_document_search_impl 
        )
        self.register_tool(
            name="add_document_to_store",
            description="Adds a new document to the in-memory store from raw text. A title is auto-generated. Keywords are optional.",
            schema={
                "type": "object",
                "properties": {
                    "document_text": {"type": "string", "description": "The full text content of the document."},
                    "keywords": {"type": "string", "description": "Optional comma-separated list of keywords."}
                },
                "required": ["document_text"]
            },
            callback=self._execute_add_document_to_store_impl
        )
        self.register_resource(
            uri="mcp://resources/literature/doc123",
            name="Sample Document 123",
            description="A sample academic paper providing placeholder content.",
            mime_type="application/json",
            content={
                "title": "Foundations of Fictional Science", "author": "Dr. A.I. Construct", "publication_year": 2024,
                "abstract": "This paper explores the fundamental principles of sciences that don't actually exist.",
                "body_paragraphs": ["Paragraph 1...", "Paragraph 2...", "Paragraph 3..."],
                "keywords": ["fiction", "dummy data", "mcp resource"]
            }
        )
        self.register_prompt(
            name="summarize_document_abstract",
            description="Generates a brief summary of a document's abstract. Requires the document's resource URI.",
            arguments=[
                {
                    "name": "document_uri", "type": "string", 
                    "description": "The MCP URI of the document resource (e.g., mcp://resources/literature/doc123) whose abstract needs summarizing.",
                    "required": True
                }
            ]
        )
    
    def register_tool(self, name: str, description: str, schema: Dict[str, Any], callback: callable) -> None:
        self.tools[name] = {'name': name, 'description': description, 'schema': schema, 'callback': callback}
        logger.info(f"注册MCP工具: {name}")
    
    def register_resource(self, uri: str, name: str, description: str, 
                         mime_type: Optional[str] = None, content: Any = None) -> None:
        self.resources[uri] = {
            'uri': uri, 'name': name, 'description': description, 
            'mime_type': mime_type, 'content': content
        }
        logger.info(f"注册MCP资源: {name} ({uri})")
    
    def register_prompt(self, name: str, description: str, 
                        arguments: Optional[List[Dict[str, Any]]] = None) -> None:
        self.prompts[name] = {'name': name, 'description': description, 'arguments': arguments or []}
        logger.info(f"注册MCP提示模板: {name}")

    def broadcast_sse_message(self, event_name: str, data: dict) -> None:
        if not self.running:
            logger.info("Server not running, skipping SSE broadcast.")
            return
        if not self.sse_clients:
            logger.debug(f"No SSE clients connected, not broadcasting event: {event_name}")
            return
        message_str = f"event: {event_name}\ndata: {json.dumps(data)}\n\n"
        message_bytes = message_str.encode('utf-8')
        clients_to_remove = []
        for client_wfile in list(self.sse_clients): 
            try:
                client_wfile.write(message_bytes); client_wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
                logger.info(f"SSE client disconnected ({type(e).__name__}). Removing client.")
                clients_to_remove.append(client_wfile)
            except Exception as e:
                logger.exception(f"Error writing to SSE client: {e}. Removing client.")
                clients_to_remove.append(client_wfile)
        for client_wfile in clients_to_remove:
            if client_wfile in self.sse_clients:
                self.sse_clients.remove(client_wfile)
                try: client_wfile.close()
                except Exception: pass

    def _generate_next_doc_id(self) -> str:
        doc_id = f"doc{self.next_doc_id_counter}"
        self.next_doc_id_counter += 1
        return doc_id

    def _save_document_store_to_file(self) -> None:
        """Saves the current document store to the JSON file."""
        try:
            with open(self.document_store_file, 'w', encoding='utf-8') as f:
                json.dump(self.document_store, f, indent=4)
            logger.info(f"Document store successfully saved to {self.document_store_file}")
        except IOError as e:
            logger.error(f"Could not save document store to {self.document_store_file}: {e}")
        except Exception as e: # Catch any other unexpected errors during saving
            logger.error(f"An unexpected error occurred while saving document store: {e}", exc_info=True)

    def _execute_add_document_to_store_impl(self, params: dict) -> dict:
        document_text = params.get("document_text")
        keywords_str = params.get("keywords", "")

        if not document_text or not document_text.strip():
            return {"error": "Missing required parameter: document_text cannot be empty."}

        stripped_text = document_text.strip()
        lines = stripped_text.split('\n', 1)
        derived_title = lines[0][:100].strip() # First line, max 100 chars, stripped
        
        if not derived_title: # If the first line was all whitespace or very long and then stripped to nothing
             # This part of ID generation in title is a bit complex if _generate_next_doc_id has side effects
             # For now, let's use a simpler default if title is empty after processing.
             # The ID will be generated once for the document itself.
             derived_title = f"Untitled Document (ID will be generated)"


        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        
        new_doc_id = self._generate_next_doc_id()
        
        new_document = {
            "id": new_doc_id,
            "title": derived_title if derived_title != "Untitled Document (ID will be generated)" else f"Untitled Document {new_doc_id}",
            "abstract": document_text, # Store full text as abstract
            "keywords": keywords
        }
        
        self.document_store.append(new_document)
        logger.info(f"Added new document from text: {new_doc_id} - {new_document['title']}")
        self._save_document_store_to_file() # Persist changes
        
        return {
            "message": "Document added successfully from text.",
            "document_id": new_doc_id,
            "derived_title": new_document['title']
        }

    def _execute_document_search_impl(self, params: dict) -> dict:
        query_str = params.get("query", "").lower()
        try:
            max_results = int(params.get("max_results", 3))
        except ValueError:
            logger.warning(f"Invalid max_results value '{params.get('max_results')}', defaulting to 3.")
            max_results = 3

        if not query_str: 
            return {"search_results": [], "query_received": params.get("query", "")}

        found_documents = []
        for doc in self.document_store:
            match = False
            if query_str in doc.get("title", "").lower():
                match = True
            elif query_str in doc.get("abstract", "").lower():
                match = True
            elif any(query_str in keyword.lower() for keyword in doc.get("keywords", [])):
                match = True
            
            if match:
                found_documents.append(doc.copy()) 

        results_to_return = found_documents[:max_results]
        return {"search_results": results_to_return, "query_received": params.get("query")}

    def execute_tool_command(self, tool_name: str, tool_params: dict) -> None:
        logger.info(f"Executing tool command: {tool_name} with params: {tool_params}")
        if tool_name in self.tools:
            tool_definition = self.tools[tool_name]
            callback = tool_definition.get('callback')
            if callable(callback):
                try:
                    result = callback(tool_params)
                    response_data = {"mcp_protocol_version": "1.0", "status": "success", "tool_name": tool_name, "result": result}
                    self.broadcast_sse_message(event_name="tool_result", data=response_data)
                except Exception as e:
                    logger.exception(f"Error executing tool '{tool_name}': {e}")
                    error_data = {"mcp_protocol_version": "1.0", "status": "error", "tool_name": tool_name, "error": str(e)}
                    self.broadcast_sse_message(event_name="tool_error", data=error_data)
            else:
                error_data = {"mcp_protocol_version": "1.0", "status": "error", "tool_name": tool_name, "error": "Tool has no callback"}
                self.broadcast_sse_message(event_name="tool_error", data=error_data)
        else:
            error_data = {"mcp_protocol_version": "1.0", "status": "error", "tool_name": tool_name, "error": f"Tool '{tool_name}' not found"}
            self.broadcast_sse_message(event_name="tool_error", data=error_data)

    def get_resource_command(self, resource_uri: str) -> None:
        logger.info(f"Handling get_resource command for URI: {resource_uri}")
        if not resource_uri:
            error_data = {"mcp_protocol_version": "1.0", "status": "error", "error": "Missing URI for get_resource"}
            self.broadcast_sse_message(event_name="resource_error", data=error_data)
            return
        resource_info = self.resources.get(resource_uri)
        if resource_info:
            response_data = {"mcp_protocol_version": "1.0", "status": "success", "uri": resource_uri, "resource_data": resource_info}
            self.broadcast_sse_message(event_name="resource_data", data=response_data)
        else:
            error_data = {"mcp_protocol_version": "1.0", "status": "error", "uri": resource_uri, "error": "Resource not found"}
            self.broadcast_sse_message(event_name="resource_error", data=error_data)

    def get_prompt_definition_command(self, prompt_name: str) -> None:
        logger.info(f"Handling get_prompt_definition command for: {prompt_name}")
        if not prompt_name:
            error_data = {"mcp_protocol_version": "1.0", "status": "error", "error": "Missing name for get_prompt_definition"}
            self.broadcast_sse_message(event_name="prompt_definition_error", data=error_data)
            return
        prompt_info = self.prompts.get(prompt_name)
        if prompt_info:
            response_data = {"mcp_protocol_version": "1.0", "status": "success", "name": prompt_name, "prompt_definition": prompt_info}
            self.broadcast_sse_message(event_name="prompt_definition_data", data=response_data)
        else:
            error_data = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Prompt not found"}
            self.broadcast_sse_message(event_name="prompt_definition_error", data=error_data)

    def execute_prompt_command(self, prompt_name: str, prompt_args: dict) -> None:
        logger.info(f"Executing prompt command: {prompt_name} with args: {prompt_args}")
        
        if not prompt_name:
            error_data = {"mcp_protocol_version": "1.0", "status": "error", "error": "Missing prompt name for execute_prompt"}
            self.broadcast_sse_message(event_name="prompt_error", data=error_data)
            return

        prompt_info = self.prompts.get(prompt_name)
        if not prompt_info:
            error_data = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Prompt not found"}
            self.broadcast_sse_message(event_name="prompt_error", data=error_data)
            return

        if prompt_name == "summarize_document_abstract":
            document_uri = prompt_args.get("document_uri")
            if not document_uri:
                error_data = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Missing document_uri argument for summarize_document_abstract"}
                self.broadcast_sse_message(event_name="prompt_error", data=error_data)
                return
            
            resource = self.resources.get(document_uri)
            if not resource:
                error_data = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": f"Resource not found: {document_uri}"}
                self.broadcast_sse_message(event_name="prompt_error", data=error_data)
                return
            
            abstract = resource.get("content", {}).get("abstract")
            if not abstract:
                error_data = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": f"Abstract not found in resource: {document_uri}"}
                self.broadcast_sse_message(event_name="prompt_error", data=error_data)
                return
            
            summary = f"Summary of abstract for '{resource.get('name', document_uri)}': {abstract[:100]}..." if abstract else "Abstract was empty."
            result_data = {"summary": summary, "source_uri": document_uri}
            response_data = {"mcp_protocol_version": "1.0", "status": "success", "prompt_name": prompt_name, "result": result_data}
            self.broadcast_sse_message(event_name="prompt_result", data=response_data)
        else:
            logger.warning(f"Execution for prompt '{prompt_name}' is not implemented yet.")
            error_data = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Prompt execution not implemented yet"}
            self.broadcast_sse_message(event_name="prompt_error", data=error_data)


    def start(self, transport_type: str, **kwargs) -> None:
        logger.info(f"启动MCP服务器 (传输类型: {transport_type})")
        self.running = True

        if transport_type == 'stdio':
            logger.info("Starting McpServer in STDIO mode.")
            try:
                while self.running:
                    line = sys.stdin.readline()
                    line = line.strip()
                    if not line or line == "quit":
                        logger.info("Received quit signal or empty line, stopping STDIO listener.")
                        break
                    
                    if line == "discover":
                        logger.info("Received capabilities discovery request.")
                        capabilities = {
                            "mcp_protocol_version": "1.0", "server_name": self.name, "server_version": self.version,
                            "tools": [{"name": t_name, "description": t_info.get("description"), "schema": t_info.get("schema")} for t_name, t_info in self.tools.items()],
                            "resources": [{k: v for k, v in res_info.items() if k != 'content'} for res_info in self.resources.values()],
                            "prompts": [prompt_info for prompt_info in self.prompts.values()]
                        }
                        print(json.dumps(capabilities))
                        sys.stdout.flush()
                    else:
                        try:
                            request_data = json.loads(line)
                            logger.debug(f"Received MCP JSON message: {request_data}")
                            response = {}
                            command = request_data.get("command")

                            if command == "execute_tool":
                                logger.info("Received execute_tool request.")
                                tool_name = request_data.get("tool_name")
                                tool_params = request_data.get("tool_params", {})
                                if tool_name in self.tools:
                                    callback = self.tools[tool_name].get('callback')
                                    if callable(callback):
                                        try:
                                            result = callback(tool_params)
                                            response = {"mcp_protocol_version": "1.0", "status": "success", "tool_name": tool_name, "result": result}
                                        except Exception as e:
                                            logger.exception(f"Error executing tool '{tool_name}': {e}")
                                            response = {"mcp_protocol_version": "1.0", "status": "error", "tool_name": tool_name, "error": str(e)}
                                    else:
                                        response = {"mcp_protocol_version": "1.0", "status": "error", "tool_name": tool_name, "error": "Tool has no callback"}
                                else:
                                    response = {"mcp_protocol_version": "1.0", "status": "error", "error": f"Tool '{tool_name}' not found"}
                            
                            elif command == "get_resource":
                                logger.info("Received get_resource request.")
                                resource_uri = request_data.get("uri")
                                if not resource_uri:
                                    response = {"mcp_protocol_version": "1.0", "status": "error", "error": "Missing URI for get_resource"}
                                else:
                                    resource_info = self.resources.get(resource_uri)
                                    if resource_info:
                                        response = {"mcp_protocol_version": "1.0", "status": "success", "uri": resource_uri, "resource_data": resource_info}
                                    else:
                                        response = {"mcp_protocol_version": "1.0", "status": "error", "uri": resource_uri, "error": "Resource not found"}
                            
                            elif command == "get_prompt_definition":
                                logger.info("Received get_prompt_definition request.")
                                prompt_name = request_data.get("name")
                                if not prompt_name:
                                    response = {"mcp_protocol_version": "1.0", "status": "error", "error": "Missing name for get_prompt_definition"}
                                else:
                                    prompt_info = self.prompts.get(prompt_name)
                                    if prompt_info:
                                        response = {"mcp_protocol_version": "1.0", "status": "success", "name": prompt_name, "prompt_definition": prompt_info}
                                    else:
                                        response = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Prompt not found"}
                            
                            elif command == "execute_prompt":
                                logger.info("Received execute_prompt request.")
                                prompt_name = request_data.get("name")
                                prompt_args = request_data.get("arguments", {})
                                if not prompt_name:
                                    response = {"mcp_protocol_version": "1.0", "status": "error", "error": "Missing prompt name"}
                                else:
                                    prompt_info = self.prompts.get(prompt_name)
                                    if not prompt_info:
                                        response = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Prompt not found"}
                                    else:
                                        if prompt_name == "summarize_document_abstract":
                                            document_uri = prompt_args.get("document_uri")
                                            if not document_uri:
                                                response = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Missing document_uri argument"}
                                            else:
                                                resource = self.resources.get(document_uri)
                                                if not resource:
                                                    response = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Resource not found"}
                                                else:
                                                    abstract = resource.get("content", {}).get("abstract")
                                                    if not abstract:
                                                        response = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Abstract not found in resource"}
                                                    else:
                                                        summary = f"Summary of abstract: {abstract}" 
                                                        response = {"mcp_protocol_version": "1.0", "status": "success", "prompt_name": prompt_name, "result": {"summary": summary}}
                                        else:
                                            response = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Prompt execution not implemented yet"}
                            else:
                                logger.warning(f"Unknown command or malformed request: {request_data}")
                                response = {"mcp_protocol_version": "1.0", "status": "error", "error": "Unknown command or malformed request"}
                            
                            print(json.dumps(response))
                            sys.stdout.flush()

                        except json.JSONDecodeError:
                            logger.warning(f"Received non-JSON message or unknown simple command: {line}")
                            print(json.dumps({"mcp_protocol_version": "1.0", "status": "error", "error": "Invalid JSON message"}))
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
        else:
            logger.error(f"Unsupported transport type: {transport_type}")
            self.running = False 
            return
        
        if transport_type == 'stdio':
            self.running = False 
    
    def stop(self) -> None:
        logger.info("McpServer stopping...") 
        self.running = False 
        if self.http_server:
            logger.info("Stopping SSE HTTP server...")
            self.http_server.shutdown() 
            self.http_server.server_close() 
            if self.http_server_thread:
                self.http_server_thread.join(timeout=5) 
            self.http_server = None
            self.http_server_thread = None
        
        for client_wfile in self.sse_clients[:]:
             try: client_wfile.close()
             except Exception as e: logger.debug(f"Error closing an SSE client stream: {e}")
        self.sse_clients.clear()
        logger.info("McpServer stopped.")

# Global level (or static method if preferred and class structure allows easily)
def _execute_document_search(params: dict) -> dict: # This is the old one, now unused.
    query = params.get("query")
    max_results_str = params.get("max_results", "3")
    try: max_results = int(max_results_str)
    except ValueError: max_results = 3; logger.warning(f"Invalid max_results '{max_results_str}', using 3.")
    if not query or not query.strip(): return {"error": "Missing or empty query parameter"} # Should be handled by schema or new logic
    results = [{"id": f"doc_{i}", "title": f"Dummy Document {i} about '{query}'", 
                "snippet": f"Snippet for doc {i} on '{query}'.", "score": round(1.0/i, 2)} 
               for i in range(1, max_results + 1)]
    return {"search_results": results, "query_received": query}

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    server = McpServer("example-server", "0.1.0")
    server_mode = "sse" 
    if server_mode == "sse":
        server.start(transport_type="sse", port=3000)
        if server.running:
            logger.info("SSE Server is running. Press Ctrl+C to stop.")
            try:
                while server.running: threading.Event().wait(1)
            except KeyboardInterrupt: logger.info("Keyboard interrupt received.")
            finally: server.stop()
        else: logger.error("Server failed to start in SSE mode.")
    else:
        server.start(transport_type="stdio")
    logger.info("McpServer example finished.")
