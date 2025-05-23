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
        self.sample_resource_uri = "mcp://resources/literature/doc123"
        self.sample_resource_name = "Sample Document 123"
        self.sample_resource_title = "Foundations of Fictional Science"
        self.sample_prompt_name = "summarize_document_abstract"
        self.sample_prompt_description = "Generates a brief summary of a document's abstract. Requires the document's resource URI."
        # import logging
        # logging.getLogger('mcp.server').setLevel(logging.CRITICAL)


    def tearDown(self):
        if self.server and hasattr(self.server, 'running') and self.server.running:
            self.server.stop()
            if self.server.http_server_thread and self.server.http_server_thread.is_alive():
                 self.server.http_server_thread.join(timeout=1) 
        
        sys.stdin = self.original_stdin
        sys.stdout = self.original_stdout
        time.sleep(0.05)


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
        
        if hasattr(response_stream, 'fp') and hasattr(response_stream.fp, 'settimeout'):
             response_stream.fp.settimeout(timeout)

        try:
            while True:
                if time.monotonic() - start_time > timeout: return None 
                raw_line = response_stream.fp.readline()
                if not raw_line: return None 
                line = raw_line.decode('utf-8').strip()
                if not line: break 
                if line.startswith(':'): 
                    if line == ": keepalive": event_data['event'] = 'keepalive'
                    continue
                if ':' in line:
                    field, value = line.split(':', 1)
                    value = value.strip()
                    if field == 'event': event_data['event'] = value
                    elif field == 'data': event_data['data'] = (event_data['data'] + "\n" + value) if event_data['data'] else value
        except socket.timeout: return None
        except Exception: return None
        return event_data if event_data.get('data') or event_data.get('event') == 'keepalive' else None
    
    # --- STDIO Tests ---
    def test_server_instantiation_and_registrations(self): # Renamed
        server = McpServer(name="Test Server", version="0.0.1") 
        self.assertEqual(server.name, "Test Server")
        self.assertIn("echo", server.tools)
        self.assertIn("document_search", server.tools) 
        self.assertIn(self.sample_resource_uri, server.resources) 
        self.assertEqual(server.resources[self.sample_resource_uri]["name"], self.sample_resource_name)
        self.assertIn(self.sample_prompt_name, server.prompts) # Verify sample prompt
        self.assertEqual(server.prompts[self.sample_prompt_name]["description"], self.sample_prompt_description)


    def test_discover_command(self):
        server = self._start_stdio_server()
        self._run_server_for_input(server, "discover\nquit\n")
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try: json.loads(line); json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line, "No JSON output for discover command.")
        response = json.loads(json_output_line)
        self.assertEqual(response["server_name"], "Test STDIO Server")
        
        # Verify resource in capabilities
        self.assertIn("resources", response)
        found_sample_resource = any(res.get("uri") == self.sample_resource_uri and "content" not in res for res in response["resources"])
        self.assertTrue(found_sample_resource, "Sample resource metadata not found or content exposed in STDIO capabilities.")

        # Verify prompt in capabilities
        self.assertIn("prompts", response)
        found_sample_prompt = False
        for p in response["prompts"]:
            if p.get("name") == self.sample_prompt_name:
                found_sample_prompt = True
                self.assertEqual(p.get("description"), self.sample_prompt_description)
                self.assertIsInstance(p.get("arguments"), list)
                self.assertEqual(p["arguments"][0]["name"], "document_uri")
                break
        self.assertTrue(found_sample_prompt, "Sample prompt not found in STDIO capabilities.")


    def test_stdio_get_prompt_definition_success(self):
        server = self._start_stdio_server()
        command = json.dumps({"command": "get_prompt_definition", "name": self.sample_prompt_name}) + "\nquit\n"
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("name") == self.sample_prompt_name: # Check for prompt name in response
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line, "No JSON output for get_prompt_definition.")
        response = json.loads(json_output_line)
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["name"], self.sample_prompt_name)
        self.assertIn("prompt_definition", response)
        self.assertEqual(response["prompt_definition"]["description"], self.sample_prompt_description)
        self.assertIsInstance(response["prompt_definition"]["arguments"], list)
        self.assertEqual(response["prompt_definition"]["arguments"][0]["name"], "document_uri")

    def test_stdio_get_prompt_definition_not_found(self):
        server = self._start_stdio_server()
        command = json.dumps({"command": "get_prompt_definition", "name": "nonexistent_prompt"}) + "\nquit\n"
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("status") == "error" and parsed.get("name") == "nonexistent_prompt":
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line)
        response = json.loads(json_output_line)
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "Prompt not found")

    def test_stdio_get_prompt_definition_missing_name(self):
        server = self._start_stdio_server()
        command = json.dumps({"command": "get_prompt_definition"}) + "\nquit\n"
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("status") == "error" and "Missing name" in parsed.get("error", ""):
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line)
        response = json.loads(json_output_line)
        self.assertEqual(response["status"], "error")
        self.assertIn("Missing name", response["error"])


    # --- SSE Tests ---
    def test_sse_capabilities_on_connect(self):
        self._start_sse_server()
        with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as conn:
            conn.request("GET", SSE_PATH)
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            event = self._read_sse_event(response, timeout=5.0)
            self.assertIsNotNone(event)
            self.assertEqual(event['event'], 'capabilities')
            capabilities = json.loads(event['data'])
            self.assertEqual(capabilities['server_name'], 'Test SSE Server')
            
            # Verify resource in capabilities
            self.assertIn("resources", capabilities)
            found_sample_resource_sse = any(res.get("uri") == self.sample_resource_uri and "content" not in res for res in capabilities["resources"])
            self.assertTrue(found_sample_resource_sse, "Sample resource metadata not found or content exposed in SSE capabilities.")

            # Verify prompt in capabilities
            self.assertIn("prompts", capabilities)
            found_sample_prompt_sse = False
            for p in capabilities["prompts"]:
                if p.get("name") == self.sample_prompt_name:
                    found_sample_prompt_sse = True
                    self.assertEqual(p.get("description"), self.sample_prompt_description)
                    self.assertIsInstance(p.get("arguments"), list)
                    self.assertEqual(p["arguments"][0]["name"], "document_uri")
                    break
            self.assertTrue(found_sample_prompt_sse, "Sample prompt not found in SSE capabilities.")

    def test_sse_get_prompt_definition_success(self):
        self._start_sse_server()
        with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as listener_conn:
            listener_conn.request("GET", SSE_PATH)
            listener_response = listener_conn.getresponse()
            self.assertEqual(listener_response.status, 200)
            self._read_sse_event(listener_response, timeout=5.0) # Consume capabilities

            command_body = json.dumps({"command": "get_prompt_definition", "name": self.sample_prompt_name})
            headers = {"Content-Type": "application/json", "Content-Length": str(len(command_body))}
            with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as cmd_conn:
                cmd_conn.request("POST", COMMAND_PATH, body=command_body, headers=headers)
                post_response = cmd_conn.getresponse()
                self.assertEqual(post_response.status, 202) # Accepted

            prompt_event = self._read_sse_event(listener_response, timeout=5.0)
            if prompt_event and prompt_event['event'] == 'keepalive':
                 prompt_event = self._read_sse_event(listener_response, timeout=5.0)
            
            self.assertIsNotNone(prompt_event, "Listener did not receive prompt_definition_data event.")
            self.assertEqual(prompt_event['event'], 'prompt_definition_data')
            data = json.loads(prompt_event['data'])
            self.assertEqual(data['status'], 'success')
            self.assertEqual(data['name'], self.sample_prompt_name)
            self.assertIn('prompt_definition', data)
            self.assertEqual(data['prompt_definition']['description'], self.sample_prompt_description)
            self.assertEqual(data['prompt_definition']['arguments'][0]['name'], "document_uri")

    def test_sse_get_prompt_definition_not_found(self):
        self._start_sse_server()
        with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as listener_conn:
            listener_conn.request("GET", SSE_PATH)
            listener_response = listener_conn.getresponse()
            self.assertEqual(listener_response.status, 200)
            self._read_sse_event(listener_response, timeout=5.0) # Capabilities

            command_body = json.dumps({"command": "get_prompt_definition", "name": "nonexistent_prompt"})
            headers = {"Content-Type": "application/json", "Content-Length": str(len(command_body))}
            with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as cmd_conn:
                cmd_conn.request("POST", COMMAND_PATH, body=command_body, headers=headers)
                post_response = cmd_conn.getresponse()
                self.assertEqual(post_response.status, 202)

            error_event = self._read_sse_event(listener_response, timeout=5.0)
            if error_event and error_event['event'] == 'keepalive':
                 error_event = self._read_sse_event(listener_response, timeout=5.0)

            self.assertIsNotNone(error_event, "Listener did not receive prompt_definition_error event.")
            self.assertEqual(error_event['event'], 'prompt_definition_error')
            data = json.loads(error_event['data'])
            self.assertEqual(data['status'], 'error')
            self.assertEqual(data['name'], "nonexistent_prompt")
            self.assertEqual(data['error'], "Prompt not found")

    def test_sse_get_prompt_definition_missing_name_in_post(self):
        self._start_sse_server()
        with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as conn:
            command_body = json.dumps({"command": "get_prompt_definition"}) # Missing name
            headers = {"Content-Type": "application/json", "Content-Length": str(len(command_body))}
            conn.request("POST", COMMAND_PATH, body=command_body, headers=headers)
            response = conn.getresponse()
            self.assertEqual(response.status, 400) # Bad Request
            response_body = json.loads(response.read().decode('utf-8'))
            self.assertIn("Missing name for get_prompt_definition command", response_body.get("error", ""))

    # --- Keep other existing tests (ensure they are not duplicated by copy-paste errors) ---
    # (STDIO tool tests)
    def test_stdio_echo_tool_execution(self):
        server = self._start_stdio_server()
        command = '{"command": "execute_tool", "tool_name": "echo", "tool_params": {"message": "Hello MCP"}}\nquit\n'
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("status") == "success" and parsed.get("tool_name") == "echo":
                        json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line)
        response = json.loads(json_output_line)
        self.assertEqual(response["result"]["echo_response"], "Hello MCP")

    def test_stdio_document_search_success(self):
        server = self._start_stdio_server()
        command = json.dumps({"command": "execute_tool", "tool_name": "document_search", "tool_params": {"query": "test", "max_results": 1}}) + "\nquit\n"
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed = json.loads(line)
                    if parsed.get("tool_name") == "document_search": json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line)
        response = json.loads(json_output_line)
        self.assertEqual(response["status"], "success")
        self.assertEqual(len(response["result"]["search_results"]), 1)

    # (STDIO resource tests)
    def test_stdio_get_resource_success(self):
        server = self._start_stdio_server()
        command = json.dumps({"command": "get_resource", "uri": self.sample_resource_uri}) + "\nquit\n"
        self._run_server_for_input(server, command)
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"): # Assuming first JSON is the one
                try: json.loads(line); json_output_line = line; break
                except: pass
        self.assertTrue(json_output_line, f"No JSON output for get_resource. Output: {output}")
        response = json.loads(json_output_line)
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["uri"], self.sample_resource_uri)
        self.assertIn("resource_data", response)
        self.assertEqual(response["resource_data"]["name"], self.sample_resource_name)
        self.assertIn("content", response["resource_data"])

    # (STDIO general error tests)
    def test_stdio_unknown_tool(self): 
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

    def test_stdio_invalid_json_message(self): 
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

    def test_stdio_unknown_command(self): 
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

    def test_stdio_quit_command(self): 
        server = self._start_stdio_server()
        self.assertFalse(server.running)
        with self.assertLogs('mcp.server', level='INFO') as cm:
            self._run_server_for_input(server, "quit\n")
        self.assertFalse(server.running)
        self.assertTrue(any("Received quit signal" in message for message in cm.output))

    # (SSE tool tests)
    def test_sse_echo_tool_execution(self):
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

            command_body = json.dumps({"command": "execute_tool", "tool_name": "document_search", "tool_params": {"query": "SSE search", "max_results": 1}})
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
            self.assertEqual(result_data['tool_name'], 'document_search')
        finally:
            if listener_conn: listener_conn.close()

    # (SSE resource tests)
    def test_sse_get_resource_success(self):
        self._start_sse_server()
        with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as listener_conn:
            listener_conn.request("GET", SSE_PATH)
            listener_response = listener_conn.getresponse()
            self.assertEqual(listener_response.status, 200)
            self._read_sse_event(listener_response, timeout=5.0) # Capabilities

            command_body = json.dumps({"command": "get_resource", "uri": self.sample_resource_uri})
            headers = {"Content-Type": "application/json", "Content-Length": str(len(command_body))}
            with http.client.HTTPConnection('localhost', self.sse_test_port, timeout=5) as cmd_conn:
                cmd_conn.request("POST", COMMAND_PATH, body=command_body, headers=headers)
                post_response = cmd_conn.getresponse()
                self.assertEqual(post_response.status, 202)

            resource_event = self._read_sse_event(listener_response, timeout=5.0)
            if resource_event and resource_event['event'] == 'keepalive':
                 resource_event = self._read_sse_event(listener_response, timeout=5.0)
            self.assertIsNotNone(resource_event)
            self.assertEqual(resource_event['event'], 'resource_data')
            data = json.loads(resource_event['data'])
            self.assertEqual(data['uri'], self.sample_resource_uri)
            self.assertIn('content', data['resource_data'])

    # (SSE general error tests)
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

_project_root_init_done = False
if not _project_root_init_done:
    if not os.path.exists(os.path.join(project_root, 'mcp', '__init__.py')):
        with open(os.path.join(project_root, 'mcp', '__init__.py'), 'w') as f: pass 
    if not os.path.exists(os.path.join(project_root, 'tests', '__init__.py')):
        with open(os.path.join(project_root, 'tests', '__init__.py'), 'w') as f: pass
    _project_root_init_done = True
