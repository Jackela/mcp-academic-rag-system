import unittest
import json
import io
import sys
import os
import time
import http.client
import threading 
import socket 

# Adjust path to import McpServer from the parent directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from mcp.server import McpServer, SSE_PATH, COMMAND_PATH

# Helper to find a free port
def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

class TestMcpServer(unittest.TestCase):
    
    def setUp(self):
        self.original_stdin = sys.stdin
        self.original_stdout = sys.stdout
        self.mock_stdout = io.StringIO() 
        sys.stdout = self.mock_stdout

        self.server = None 
        self.sse_test_port = find_free_port()
        # To suppress server logs during tests for cleaner output:
        # import logging
        # logging.getLogger('mcp.server').setLevel(logging.CRITICAL)


    def tearDown(self):
        if self.server and hasattr(self.server, 'running') and self.server.running:
            self.server.stop()
            if self.server.http_server_thread and self.server.http_server_thread.is_alive():
                 self.server.http_server_thread.join(timeout=1) 
        
        sys.stdin = self.original_stdin
        sys.stdout = self.original_stdout
        time.sleep(0.05) # Allow time for resources (e.g., ports) to be released


    def _start_stdio_server(self):
        self.server = McpServer(name="Test STDIO Server", version="0.0.1")
        return self.server

    def _run_server_for_input(self, server_instance, input_str):
        sys.stdin = io.StringIO(input_str)
        try:
            server_instance.start(transport_type='stdio')
        except Exception as e:
            print(f"STDIO Server run caused an exception: {e}", file=sys.stderr)

    def _start_sse_server(self, port=None):
        if port is None:
            port = self.sse_test_port
        
        self.server = McpServer(name="Test SSE Server", version="0.0.1")
        self.server.start(transport_type='sse', port=port)
        
        time.sleep(0.1) 
        if not self.server.running or not self.server.http_server_thread or not self.server.http_server_thread.is_alive():
            if self.server: self.server.stop()
            raise RuntimeError(f"MCP SSE server failed to start on port {port}")
        return self.server

    @staticmethod
    def _read_sse_event(response_stream, timeout=5.0):
        event_data = {'event': 'message', 'data': ''}
        start_time = time.monotonic()
        
        # Set timeout on the socket if possible
        if hasattr(response_stream, 'fp') and hasattr(response_stream.fp, 'settimeout'):
             response_stream.fp.settimeout(timeout)

        try:
            while True:
                if time.monotonic() - start_time > timeout:
                    return None 

                raw_line = response_stream.fp.readline()
                if not raw_line: 
                    return None 
                
                line = raw_line.decode('utf-8').strip()

                if not line: 
                    break 
                
                if line.startswith(':'): 
                    if line == ": keepalive":
                        event_data['event'] = 'keepalive'
                    continue

                if ':' in line:
                    field, value = line.split(':', 1)
                    value = value.strip()
                    if field == 'event':
                        event_data['event'] = value
                    elif field == 'data':
                        event_data['data'] = (event_data['data'] + "\n" + value) if event_data['data'] else value
        
        except socket.timeout:
            return None
        except Exception: # Broad exception for other read errors
            return None

        return event_data if event_data.get('data') or event_data.get('event') == 'keepalive' else None
    
    # --- STDIO Tests ---
    def test_server_instantiation_and_tool_registration(self):
        # Test with a locally created server instance, not started.
        server = McpServer(name="Test Server", version="0.0.1")
        self.assertEqual(server.name, "Test Server")
        self.assertEqual(server.version, "0.0.1")
        self.assertIn("echo", server.tools)
        self.assertIn("document_search", server.tools) # Verify new tool
        
        doc_search_tool = server.tools["document_search"]
        self.assertEqual(doc_search_tool["description"], "Searches academic documents based on a query.")
        self.assertTrue(callable(doc_search_tool["callback"]))
        self.assertIn("query", doc_search_tool["schema"]["required"])

    def test_discover_command(self):
        server = self._start_stdio_server()
        self._run_server_for_input(server, "discover\nquit\n")
        
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    json.loads(line) 
                    json_output_line = line
                    break
                except json.JSONDecodeError:
                    continue
        
        self.assertTrue(json_output_line, "No JSON output found for discover command.")
        response = json.loads(json_output_line)
        self.assertEqual(response["server_name"], "Test STDIO Server")
        
        tools_by_name = {t["name"]: t for t in response["tools"]}
        self.assertIn("echo", tools_by_name)
        self.assertIn("document_search", tools_by_name)
        doc_search_tool_info = tools_by_name["document_search"]
        self.assertEqual(doc_search_tool_info["description"], "Searches academic documents based on a query.")
        self.assertIsNotNone(doc_search_tool_info["schema"])
        self.assertIn("query", doc_search_tool_info["schema"]["properties"])

    def test_stdio_echo_tool_execution(self): # Renamed for clarity
        server = self._start_stdio_server()
        command = '{"command": "execute_tool", "tool_name": "echo", "tool_params": {"message": "Hello MCP"}}\nquit\n'
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed_line = json.loads(line)
                    if parsed_line.get("status") == "success" and parsed_line.get("tool_name") == "echo":
                         json_output_line = line
                         break
                except json.JSONDecodeError:
                    continue
        self.assertTrue(json_output_line, "No success JSON output for echo tool.")
        response = json.loads(json_output_line)
        self.assertEqual(response["result"]["echo_response"], "Hello MCP")

    def test_stdio_document_search_success(self):
        server = self._start_stdio_server()
        command = json.dumps({
            "command": "execute_tool",
            "tool_name": "document_search",
            "tool_params": {"query": "test query", "max_results": 2}
        }) + "\nquit\n"
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("tool_name") == "document_search":
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line)
        response = json.loads(json_output_line)
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["result"]["query_received"], "test query")
        self.assertEqual(len(response["result"]["search_results"]), 2)

    def test_stdio_document_search_missing_query(self):
        server = self._start_stdio_server()
        command = json.dumps({
            "command": "execute_tool",
            "tool_name": "document_search",
            "tool_params": {} 
        }) + "\nquit\n"
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try: # The callback error is nested inside a "result" field by STDIO handler
                    parsed = json.loads(line)
                    if parsed.get("tool_name") == "document_search" and parsed.get("status") == "success" and \
                       "result" in parsed and "error" in parsed["result"]:
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line)
        response = json.loads(json_output_line)
        self.assertEqual(response["status"], "success") # STDIO reports success even if callback returns error dict
        self.assertEqual(response["result"]["error"], "Missing or empty query parameter")

    def test_stdio_document_search_default_max_results(self):
        server = self._start_stdio_server()
        command = json.dumps({
            "command": "execute_tool",
            "tool_name": "document_search",
            "tool_params": {"query": "another query"}
        }) + "\nquit\n"
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("tool_name") == "document_search":
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line)
        response = json.loads(json_output_line)
        self.assertEqual(response["status"], "success")
        self.assertEqual(len(response["result"]["search_results"]), 3) # Callback default

    # --- SSE Tests ---
    def test_sse_capabilities_on_connect(self):
        self._start_sse_server()
        conn = None
        try:
            conn = http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5)
            conn.request("GET", SSE_PATH)
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            event = self._read_sse_event(response, timeout=5.0)
            self.assertIsNotNone(event)
            self.assertEqual(event['event'], 'capabilities')
            capabilities = json.loads(event['data'])
            self.assertEqual(capabilities['server_name'], 'Test SSE Server')
            tools_by_name_sse = {t["name"]: t for t in capabilities['tools']}
            self.assertIn("echo", tools_by_name_sse)
            self.assertIn("document_search", tools_by_name_sse)
            self.assertIsNotNone(tools_by_name_sse["document_search"]["schema"])
        finally:
            if conn: conn.close()

    def test_sse_echo_tool_execution(self): # Renamed for clarity
        self._start_sse_server()
        listener_conn = None
        try:
            listener_conn = http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5)
            listener_conn.request("GET", SSE_PATH)
            listener_response = listener_conn.getresponse()
            self.assertEqual(listener_response.status, 200)
            self._read_sse_event(listener_response, timeout=5.0) # Capabilities

            command_body = json.dumps({"command": "execute_tool", "tool_name": "echo", "tool_params": {"message": "Hello SSE"}})
            headers = {"Content-Type": "application/json", "Content-Length": str(len(command_body))}
            with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as cmd_conn:
                cmd_conn.request("POST", COMMAND_PATH, body=command_body, headers=headers)
                post_response = cmd_conn.getresponse()
                self.assertEqual(post_response.status, 202)
            
            tool_event = self._read_sse_event(listener_response, timeout=5.0)
            if tool_event and tool_event['event'] == 'keepalive':
                tool_event = self._read_sse_event(listener_response, timeout=5.0)
            self.assertIsNotNone(tool_event)
            self.assertEqual(tool_event['event'], 'tool_result')
            result_data = json.loads(tool_event['data'])
            self.assertEqual(result_data['tool_name'], 'echo')
            self.assertEqual(result_data['result']['echo_response'], 'Hello SSE')
        finally:
            if listener_conn: listener_conn.close()

    def test_sse_document_search_success(self):
        self._start_sse_server()
        listener_conn = None
        try:
            listener_conn = http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5)
            listener_conn.request("GET", SSE_PATH)
            listener_response = listener_conn.getresponse()
            self.assertEqual(listener_response.status, 200)
            self._read_sse_event(listener_response, timeout=2.0) # Capabilities

            command_body = json.dumps({
                "command": "execute_tool", 
                "tool_name": "document_search", 
                "tool_params": {"query": "SSE search", "max_results": 1}
            })
            headers = {"Content-Type": "application/json", "Content-Length": str(len(command_body))}
            with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as cmd_conn:
                cmd_conn.request("POST", COMMAND_PATH, body=command_body, headers=headers)
                post_response = cmd_conn.getresponse()
                self.assertEqual(post_response.status, 202)

            tool_event = self._read_sse_event(listener_response, timeout=5.0)
            if tool_event and tool_event['event'] == 'keepalive':
                 tool_event = self._read_sse_event(listener_response, timeout=5.0)
            self.assertIsNotNone(tool_event)
            self.assertEqual(tool_event['event'], 'tool_result')
            result_data = json.loads(tool_event['data'])
            self.assertEqual(result_data['status'], 'success')
            self.assertEqual(result_data['tool_name'], 'document_search')
            self.assertEqual(len(result_data['result']['search_results']), 1)
        finally:
            if listener_conn: listener_conn.close()

    def test_sse_document_search_missing_query(self):
        self._start_sse_server()
        listener_conn = None
        try:
            listener_conn = http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5)
            listener_conn.request("GET", SSE_PATH)
            listener_response = listener_conn.getresponse()
            self.assertEqual(listener_response.status, 200)
            self._read_sse_event(listener_response, timeout=2.0) # Capabilities

            command_body = json.dumps({"command": "execute_tool", "tool_name": "document_search", "tool_params": {}})
            headers = {"Content-Type": "application/json", "Content-Length": str(len(command_body))}
            with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as cmd_conn:
                cmd_conn.request("POST", COMMAND_PATH, body=command_body, headers=headers)
                post_response = cmd_conn.getresponse()
                self.assertEqual(post_response.status, 202) 

            error_event = self._read_sse_event(listener_response, timeout=5.0)
            if error_event and error_event['event'] == 'keepalive':
                 error_event = self._read_sse_event(listener_response, timeout=5.0)
            self.assertIsNotNone(error_event)
            self.assertEqual(error_event['event'], 'tool_error')
            error_data = json.loads(error_event['data'])
            self.assertEqual(error_data['status'], 'error')
            self.assertEqual(error_data['tool_name'], 'document_search')
            self.assertIn("Missing or empty query parameter", error_data['error'])
        finally:
            if listener_conn: listener_conn.close()

    # Keep other existing tests like test_unknown_tool, test_invalid_json_message etc.
    # Ensure their server setup is also updated if they relied on self.server from setUp
    def test_stdio_unknown_tool(self): # Renamed and ensure it uses new setup
        server = self._start_stdio_server()
        command = '{"command": "execute_tool", "tool_name": "nonexistent_tool", "tool_params": {}}\nquit\n'
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("status") == "error" and "not found" in parsed.get("error", ""):
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line, "No error JSON for unknown tool.")
        response = json.loads(json_output_line)
        self.assertEqual(response["status"], "error")

    def test_stdio_invalid_json_message(self): # Renamed
        server = self._start_stdio_server()
        self._run_server_for_input(server, "this is not json\nquit\n")
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("status") == "error" and "Invalid JSON message" in parsed.get("error", ""):
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line)
        response = json.loads(json_output_line)
        self.assertEqual(response["error"], "Invalid JSON message")

    def test_stdio_unknown_command(self): # Renamed
        server = self._start_stdio_server()
        command = '{"command": "non_existent_command", "data": "test"}\nquit\n'
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("status") == "error" and "Unknown command" in parsed.get("error", ""):
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line)
        response = json.loads(json_output_line)
        self.assertEqual(response["error"], "Unknown command or malformed request")

    def test_stdio_quit_command(self): # Renamed
        server = self._start_stdio_server()
        self.assertFalse(server.running)
        with self.assertLogs('mcp.server', level='INFO') as cm:
            self._run_server_for_input(server, "quit\n")
        self.assertFalse(server.running)
        self.assertTrue(any("Received quit signal" in message for message in cm.output))

    def test_sse_post_invalid_json(self):
        self._start_sse_server()
        with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as conn:
            invalid_json_body = "this is not json"
            headers = {"Content-Type": "application/json", "Content-Length": str(len(invalid_json_body))}
            conn.request("POST", COMMAND_PATH, body=invalid_json_body, headers=headers)
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            response_body = json.loads(response.read().decode('utf-8'))
            self.assertIn("Invalid JSON", response_body.get("error", ""))

    def test_sse_post_unknown_command(self):
        self._start_sse_server()
        with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as conn:
            unknown_command_body = json.dumps({"command": "make_coffee"})
            headers = {"Content-Type": "application/json", "Content-Length": str(len(unknown_command_body))}
            conn.request("POST", COMMAND_PATH, body=unknown_command_body, headers=headers)
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            response_body = json.loads(response.read().decode('utf-8'))
            self.assertIn("Unknown command", response_body.get("error", ""))

if __name__ == '__main__':
    unittest.main()

# Ensure this runs only once if tests are run multiple times in one session.
_project_root_init_done = False
if not _project_root_init_done:
    if not os.path.exists(os.path.join(project_root, 'mcp', '__init__.py')):
        with open(os.path.join(project_root, 'mcp', '__init__.py'), 'w') as f:
            pass 
    if not os.path.exists(os.path.join(project_root, 'tests', '__init__.py')):
        with open(os.path.join(project_root, 'tests', '__init__.py'), 'w') as f:
            pass
    _project_root_init_done = True
