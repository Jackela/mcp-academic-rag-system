import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

def register_prompt(server_instance: Any, name: str, description: str,
                    arguments: Optional[List[Dict[str, Any]]] = None) -> None:
    """Registers a prompt template with the McpServer instance."""
    server_instance.prompts[name] = {'name': name, 'description': description, 'arguments': arguments or []}
    logger.info(f"MCP Prompt Registered: {name}")

def get_prompt_definition_command(server_instance: Any, prompt_name: str) -> None:
    """Handles the 'get_prompt_definition' command."""
    logger.info(f"Handling get_prompt_definition command for: {prompt_name}")
    if not prompt_name:
        error_data = {"mcp_protocol_version": "1.0", "status": "error", "error": "Missing name for get_prompt_definition"}
        server_instance.broadcast_sse_message(event_name="prompt_definition_error", data=error_data)
        return
    
    prompt_info = server_instance.prompts.get(prompt_name)
    if prompt_info:
        response_data = {
            "mcp_protocol_version": "1.0",
            "status": "success",
            "name": prompt_name,
            "prompt_definition": prompt_info
        }
        server_instance.broadcast_sse_message(event_name="prompt_definition_data", data=response_data)
    else:
        error_data = {
            "mcp_protocol_version": "1.0",
            "status": "error",
            "name": prompt_name,
            "error": "Prompt not found"
        }
        server_instance.broadcast_sse_message(event_name="prompt_definition_error", data=error_data)

def execute_prompt_command(server_instance: Any, prompt_name: str, prompt_args: dict) -> None:
    """Handles the 'execute_prompt' command."""
    logger.info(f"Executing prompt command: {prompt_name} with args: {prompt_args}")
    
    if not prompt_name:
        error_data = {"mcp_protocol_version": "1.0", "status": "error", "error": "Missing prompt name for execute_prompt"}
        server_instance.broadcast_sse_message(event_name="prompt_error", data=error_data)
        return

    prompt_info = server_instance.prompts.get(prompt_name)
    if not prompt_info:
        error_data = {"mcp_protocol_version": "1.0", "status": "error", "name": prompt_name, "error": "Prompt not found"}
        server_instance.broadcast_sse_message(event_name="prompt_error", data=error_data)
        return

    # Actual prompt execution logic
    # This is where the specific logic for each prompt_name would go.
    # For this refactoring, we'll replicate the existing simple 'summarize_document_abstract' example.
    if prompt_name == "summarize_document_abstract":
        document_uri = prompt_args.get("document_uri")
        if not document_uri:
            error_data = {
                "mcp_protocol_version": "1.0", "status": "error", "name": prompt_name,
                "error": "Missing document_uri argument for summarize_document_abstract"
            }
            server_instance.broadcast_sse_message(event_name="prompt_error", data=error_data)
            return
        
        resource = server_instance.resources.get(document_uri) # Accesses server_instance.resources
        if not resource:
            error_data = {
                "mcp_protocol_version": "1.0", "status": "error", "name": prompt_name,
                "error": f"Resource not found: {document_uri}"
            }
            server_instance.broadcast_sse_message(event_name="prompt_error", data=error_data)
            return
        
        abstract = resource.get("content", {}).get("abstract")
        if not abstract: # Also handles if content or abstract key is missing
            error_data = {
                "mcp_protocol_version": "1.0", "status": "error", "name": prompt_name,
                "error": f"Abstract not found in resource: {document_uri}"
            }
            server_instance.broadcast_sse_message(event_name="prompt_error", data=error_data)
            return
        
        # Simple summary logic from original file
        summary = f"Summary of abstract for '{resource.get('name', document_uri)}': {abstract[:100]}..." if abstract else "Abstract was empty."
        result_data = {"summary": summary, "source_uri": document_uri}
        response_data = {
            "mcp_protocol_version": "1.0",
            "status": "success",
            "prompt_name": prompt_name,
            "result": result_data
        }
        server_instance.broadcast_sse_message(event_name="prompt_result", data=response_data)
    else:
        logger.warning(f"Execution for prompt '{prompt_name}' is not implemented yet.")
        error_data = {
            "mcp_protocol_version": "1.0",
            "status": "error",
            "name": prompt_name,
            "error": "Prompt execution not implemented yet"
        }
        server_instance.broadcast_sse_message(event_name="prompt_error", data=error_data)
pass
