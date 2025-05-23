import logging
import os
import base64
import binascii
from typing import Any, Dict, Callable

# Import resources to call _register_document_as_resource
from . import resources as mcp_resources
# DocumentManager will be accessed via server_instance.document_manager

logger = logging.getLogger(__name__)

def register_tool(server_instance: Any, name: str, description: str, schema: Dict[str, Any], callback: Callable) -> None:
    server_instance.tools[name] = {'name': name, 'description': description, 'schema': schema, 'callback': callback}
    logger.info(f"MCP Tool Registered: {name}")

def _execute_document_search_impl(server_instance: Any, params: dict) -> dict:
    query_str = params.get("query", "").lower()
    try:
        max_results = int(params.get("max_results", 3))
    except ValueError:
        logger.warning(f"Invalid max_results value '{params.get('max_results')}', defaulting to 3.")
        max_results = 3

    if not query_str: # DocumentManager.search_documents also handles empty query
        return {"search_results": [], "query_received": params.get("query", "")}

    # Delegate search to DocumentManager instance on the server
    # Assumes server_instance has a 'document_manager' attribute
    if not hasattr(server_instance, 'document_manager'):
        logger.error("McpServer instance does not have 'document_manager'. Document search cannot proceed.")
        return {"error": "Document manager not available.", "query_received": params.get("query")}

    results_to_return = server_instance.document_manager.search_documents(query_str, max_results)
    
    return {"search_results": results_to_return, "query_received": params.get("query")}

def _execute_add_document_to_store_impl(server_instance: Any, params: dict) -> dict:
    document_text = params.get("document_text")
    keywords_str = params.get("keywords", "")

    if not document_text or not document_text.strip():
        return {"error": "Missing required parameter: document_text cannot be empty."}

    # Assumes server_instance has a 'document_manager' attribute
    if not hasattr(server_instance, 'document_manager'):
        logger.error("McpServer instance does not have 'document_manager'. Cannot add document.")
        return {"error": "Document manager not available."}

    stripped_text = document_text.strip()
    lines = stripped_text.split('\n', 1)
    derived_title = lines[0][:100].strip()
    
    if not derived_title:
         derived_title = f"Untitled Document (ID will be generated)"

    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
    
    # Generate ID using DocumentManager
    new_doc_id = server_instance.document_manager.generate_next_doc_id()
    
    new_document = {
        "id": new_doc_id,
        "title": derived_title if derived_title != "Untitled Document (ID will be generated)" else f"Untitled Document {new_doc_id}",
        "abstract": document_text, 
        "keywords": keywords
    }
    
    # Add document using DocumentManager (which also handles saving)
    server_instance.document_manager.add_document(new_document)
    logger.info(f"Added new document from text: {new_doc_id} - {new_document['title']}")
    
    # Call _register_document_as_resource from the mcp_resources module
    # This part remains the same, assuming mcp_resources can handle it.
    mcp_resources._register_document_as_resource(server_instance, new_document)
    
    return {
        "message": "Document added successfully from text.",
        "document_id": new_doc_id,
        "derived_title": new_document['title']
    }

def _execute_add_document_from_file_impl(server_instance: Any, params: dict) -> dict:
    file_content_base64 = params.get("file_content_base64")
    filename_param = params.get("filename")
    keywords_str = params.get("keywords", "")

    # Assumes server_instance has a 'document_manager' attribute
    if not hasattr(server_instance, 'document_manager'):
        logger.error("McpServer instance does not have 'document_manager'. Cannot add document from file.")
        return {"error": "Document manager not available."}

    filename = ""
    if filename_param:
        filename = str(filename_param).replace('\x00', '')

    if file_content_base64 is None or not filename.strip():
        return {"error": "Missing required parameter: file_content_base64 must be provided (can be an empty string), and filename must be a non-empty string."}

    try:
        decoded_bytes = base64.b64decode(file_content_base64)
        decoded_text = decoded_bytes.decode('utf-8')
    except (binascii.Error, UnicodeDecodeError) as e:
        logger.warning(f"Failed to decode Base64 content for file {filename}: {e}")
        return {"error": "Invalid Base64 content or UTF-8 decoding error."}
    except Exception as e:
        logger.error(f"Unexpected error decoding file {filename}: {e}", exc_info=True)
        return {"error": "An unexpected error occurred during file decoding."}

    stripped_decoded_text = decoded_text.strip()
    
    temp_title_from_fn = os.path.splitext(filename)[0]
    default_title_from_filename = temp_title_from_fn.encode('ascii', 'ignore').decode('ascii')
    
    if not default_title_from_filename:
        default_title_from_filename = "Untitled Document from File"

    if not stripped_decoded_text:
        derived_title = default_title_from_filename
    else:
        lines = stripped_decoded_text.split('\n', 1)
        first_line = lines[0].strip()
        if not first_line:
            derived_title = default_title_from_filename
        else:
            cleaned_first_line = first_line.encode('ascii', 'ignore').decode('ascii')
            derived_title = cleaned_first_line[:100] if cleaned_first_line else default_title_from_filename

    # Generate ID using DocumentManager
    new_doc_id = server_instance.document_manager.generate_next_doc_id()
    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

    derived_title_sanitized = "".join(c for c in derived_title if c.isprintable()).strip()
    if not derived_title_sanitized:
        fallback_title = default_title_from_filename
        if not fallback_title.strip():
             fallback_title = "Untitled Document"
        derived_title_sanitized = fallback_title
    
    abstract_sanitized = "".join(c for c in decoded_text if c.isprintable() or c in ('\n', '\r', '\t'))
    
    new_document = {
        "id": new_doc_id,
        "title": derived_title_sanitized,
        "abstract": abstract_sanitized,
        "keywords": keywords
    }
    
    # Add document using DocumentManager (which also handles saving)
    server_instance.document_manager.add_document(new_document)
    logger.info(f"Added new document from file {filename}: {new_doc_id} - {derived_title_sanitized}")

    # Call _register_document_as_resource from the mcp_resources module
    mcp_resources._register_document_as_resource(server_instance, new_document)
    
    return {
        "message": "Document added successfully from file.",
        "document_id": new_doc_id,
        "derived_title": derived_title_sanitized,
        "original_filename": filename
    }

def execute_tool_command(server_instance: Any, tool_name: str, tool_params: dict) -> None:
    logger.info(f"Executing tool command: {tool_name} with params: {tool_params}")
    if tool_name in server_instance.tools:
        tool_definition = server_instance.tools[tool_name]
        callback = tool_definition.get('callback')
        if callable(callback):
            try:
                result = callback(tool_params)
                response_data = {"mcp_protocol_version": "1.0", "status": "success", "tool_name": tool_name, "result": result}
                server_instance.broadcast_sse_message(event_name="tool_result", data=response_data)
            except Exception as e:
                logger.exception(f"Error executing tool '{tool_name}': {e}")
                error_data = {"mcp_protocol_version": "1.0", "status": "error", "tool_name": tool_name, "error": str(e)}
                server_instance.broadcast_sse_message(event_name="tool_error", data=error_data)
        else:
            error_data = {"mcp_protocol_version": "1.0", "status": "error", "tool_name": tool_name, "error": "Tool has no callback"}
            server_instance.broadcast_sse_message(event_name="tool_error", data=error_data)
    else:
        error_data = {"mcp_protocol_version": "1.0", "status": "error", "tool_name": tool_name, "error": f"Tool '{tool_name}' not found"}
        server_instance.broadcast_sse_message(event_name="tool_error", data=error_data)
pass
