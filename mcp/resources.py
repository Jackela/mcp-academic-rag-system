import logging
import json # Needed if broadcast_sse_message is moved here, or for constructing data for it.
            # server_instance.broadcast_sse_message handles json.dumps itself.
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def register_resource(server_instance: Any, uri: str, name: str, description: str,
                      mime_type: Optional[str] = None, content: Any = None) -> None:
    """Registers a resource with the McpServer instance."""
    server_instance.resources[uri] = {
        'uri': uri, 'name': name, 'description': description,
        'mime_type': mime_type, 'content': content
    }
    logger.info(f"MCP Resource Registered: {name} ({uri})")

def _register_document_as_resource(server_instance: Any, document: dict) -> None:
    """
    Helper method to register a single document (from the document store) as an MCP resource.
    This function is called when new documents are added to the store.
    """
    if not document or 'id' not in document:
        logger.warning("Attempted to register a document resource without an ID or empty document. Skipping.")
        return

    doc_id = document['id']
    doc_title_str = str(document.get('title', '')).strip()
    if not doc_title_str:
        doc_title = f"Document {doc_id}"
    else:
        doc_title = doc_title_str

    uri = f"mcp://resources/documents/{doc_id}"
    content_data = document if isinstance(document, dict) else {}
    
    resource_definition = {
        'uri': uri,
        'name': f"Document: {doc_title}",
        'description': f"Access to document {doc_id} - '{doc_title}'",
        'mime_type': 'application/json',
        'content': content_data
    }
    # Uses the register_resource function from this module, but needs server_instance
    # to access server_instance.resources.
    # Or, more directly: server_instance.resources[uri] = resource_definition
    server_instance.resources[uri] = resource_definition # Directly modifies server's state
    logger.info(f"Registered document {doc_id} as MCP resource: {uri}")
    
    # If there's a need to broadcast this new resource registration:
    # capability_event_data = {k: v for k, v in resource_definition.items() if k != 'content'}
    # server_instance.broadcast_sse_message(event_name="resource_added", data=capability_event_data)
    # This should be considered as part of a broader capability update strategy.
    # For now, clients get full resource list on connection and this is an internal update.

def get_resource_command(server_instance: Any, resource_uri: str) -> None:
    """Handles the 'get_resource' command by fetching and broadcasting resource data."""
    logger.info(f"Handling get_resource command for URI: {resource_uri}")
    if not resource_uri:
        error_data = {"mcp_protocol_version": "1.0", "status": "error", "error": "Missing URI for get_resource"}
        server_instance.broadcast_sse_message(event_name="resource_error", data=error_data)
        return
    
    resource_info = server_instance.resources.get(resource_uri)
    if resource_info:
        # Ensure content is not None before sending, or handle as needed.
        # The current implementation sends the whole resource_info, including content.
        response_data = {
            "mcp_protocol_version": "1.0",
            "status": "success",
            "uri": resource_uri,
            "resource_data": resource_info # This includes the 'content'
        }
        server_instance.broadcast_sse_message(event_name="resource_data", data=response_data)
    else:
        error_data = {
            "mcp_protocol_version": "1.0",
            "status": "error",
            "uri": resource_uri,
            "error": "Resource not found"
        }
        server_instance.broadcast_sse_message(event_name="resource_error", data=error_data)

# Note: The calls in mcp/tools.py like `server_instance._register_document_as_resource(new_document)`
# will need to be updated if `_register_document_as_resource` is now in this `resources.py` module.
# For example, it would become `resources_module_ref. _register_document_as_resource(server_instance, new_document)`
# or `server_instance.resources_module_ref._register_document_as_resource(new_document)`
# if McpServer instantiates a class from resources.py.
#
# If tools.py needs to call _register_document_as_resource from this module,
# McpServer will need to provide a way for tools module to access functions in resources module,
# possibly by passing a reference to a resources manager/handler object, or by McpServer
# itself calling the resources module function.
#
# Let's assume McpServer will handle this:
# In McpServer:
# from . import tools
# from . import resources as mcp_resources # Import the module
#
# When a tool adds a document:
# 1. Tool's _execute_add_document_impl(self, params) is called (self is McpServer instance)
# 2. It prepares the new_document.
# 3. It calls self.mcp_resources._register_document_as_resource(self, new_document)
#    (assuming self.mcp_resources = mcp_resources module, or an instance of a class from it)

# For now, tools.py calls `server_instance._register_document_as_resource(...)`.
# This means that `_register_document_as_resource` must remain a method of `McpServer` class for now,
# and that method in `McpServer` can delegate to a function in `resources.py` if needed.
#
# Alternative: Define `_register_document_as_resource` here, and `McpServer` calls
# `self.resources_module._register_document_as_resource(self, document_data)`.
# And tools would call `server_instance.resources_module._register_document_as_resource(server_instance, new_document)`
# This seems more consistent.
#
# Let's assume `McpServer` will have an instance of a class or a direct module reference:
# `self.res_handler = ResourceHandler(self)` or `self.res_module = mcp_resources`.
# Then calls from `tools.py` would look like:
# `server_instance.res_handler._register_document_as_resource(new_document)`
# (if `_register_document_as_resource` in `ResourceHandler` doesn't need `server_instance` passed again)
# OR
# `server_instance.res_module._register_document_as_resource(server_instance, new_document)`
#
# The current `_register_document_as_resource` here takes `server_instance`.
# This is fine. `tools.py` will call `server_instance.mcp_resources._register_document_as_resource(server_instance, new_document)`
# This will be wired up in `McpServer` update step.
# Removed json import as it's not directly used.
pass
