import unittest
import json
import io
import sys
import os

# Adjust path to import McpServer from the parent directory
# This assumes 'tests' is a subdirectory of the project root where 'mcp' also resides.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from mcp.server import McpServer

class TestMcpServer(unittest.TestCase):

    def setUp(self):
        self.original_stdin = sys.stdin
        self.original_stdout = sys.stdout
        sys.stdout = self.mock_stdout = io.StringIO()
        # For most tests, stdin will be set specifically
        self.server = McpServer(name="Test Server", version="0.0.1")

    def tearDown(self):
        sys.stdin = self.original_stdin
        sys.stdout = self.original_stdout
        # Ensure server is stopped if a test started it and didn't stop it
        if hasattr(self.server, 'running') and self.server.running:
            self.server.stop()

    def _run_server_for_input(self, input_str):
        """Helper to run the server loop for a single input (or a sequence ending in quit)."""
        sys.stdin = io.StringIO(input_str)
        # We need to ensure the server stops after processing the input.
        # The current server loop breaks on "quit" or empty line.
        # If input_str doesn't naturally end the loop, this might hang.
        # For single commands, we can often just call a more direct method if available,
        # but here we test 'start' more directly.
        try:
            self.server.start(transport_type='stdio')
        except Exception as e:
            # Catch exceptions during server start/run for debugging tests
            print(f"Server run caused an exception: {e}", file=sys.stderr)


    def test_server_instantiation_and_echo_tool_registration(self):
        self.assertEqual(self.server.name, "Test Server")
        self.assertEqual(self.server.version, "0.0.1")
        self.assertIn("echo", self.server.tools)
        echo_tool = self.server.tools["echo"]
        self.assertEqual(echo_tool["description"], "Echo the input")
        self.assertEqual(echo_tool["schema"], {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"]
        })
        self.assertTrue(callable(echo_tool["callback"]))

    def test_discover_command(self):
        # The server's main loop in start() will exit after one command if stdin closes.
        # 'discover' is a single line command.
        self._run_server_for_input("discover\nquit\n") # Add quit to ensure loop termination
        
        output = self.mock_stdout.getvalue()
        # The output will contain logs as well, so we find the JSON part.
        # We expect the JSON to be on its own line.
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{") and line.strip().endswith("}"):
                try:
                    json.loads(line) # check if it's valid json
                    json_output_line = line
                    break
                except json.JSONDecodeError:
                    continue
        
        self.assertTrue(json_output_line, "No JSON output found for discover command.")

        response = json.loads(json_output_line)
        self.assertEqual(response["mcp_protocol_version"], "1.0")
        self.assertEqual(response["server_name"], "Test Server")
        self.assertEqual(response["server_version"], "0.0.1")
        self.assertIsInstance(response["tools"], list)
        self.assertTrue(any(tool["name"] == "echo" for tool in response["tools"]))
        echo_tool_info = next(tool for tool in response["tools"] if tool["name"] == "echo")
        self.assertNotIn("callback", echo_tool_info) # Callback should not be exposed

    def test_echo_tool_execution(self):
        command = '{"command": "execute_tool", "tool_name": "echo", "tool_params": {"message": "Hello MCP"}}\nquit\n'
        self._run_server_for_input(command)
        
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
             # Assuming JSON response is the first line starting with {
            if line.strip().startswith("{"):
                try:
                    # Validate if it's the actual response, not some other JSON in logs
                    parsed_line = json.loads(line)
                    if parsed_line.get("status") == "success":
                         json_output_line = line
                         break
                except json.JSONDecodeError:
                    continue
        
        self.assertTrue(json_output_line, "No success JSON output found for echo tool.")
        response = json.loads(json_output_line)

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["tool_name"], "echo")
        self.assertIn("result", response)
        self.assertEqual(response["result"]["echo_response"], "Hello MCP")

    def test_unknown_tool(self):
        command = '{"command": "execute_tool", "tool_name": "nonexistent_tool", "tool_params": {}}\nquit\n'
        self._run_server_for_input(command)
        
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed_line = json.loads(line)
                    if parsed_line.get("status") == "error" and "Tool 'nonexistent_tool' not found" in parsed_line.get("error",""):
                         json_output_line = line
                         break
                except json.JSONDecodeError:
                    continue
        
        self.assertTrue(json_output_line, "No error JSON output for unknown tool.")
        response = json.loads(json_output_line)
        
        self.assertEqual(response["status"], "error")
        self.assertIn("Tool 'nonexistent_tool' not found", response["error"])

    def test_invalid_json_message(self):
        self._run_server_for_input("this is not json\nquit\n")
        
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed_line = json.loads(line)
                    if parsed_line.get("status") == "error" and "Invalid JSON message" in parsed_line.get("error",""):
                         json_output_line = line
                         break
                except json.JSONDecodeError:
                    continue

        self.assertTrue(json_output_line, "No error JSON output for invalid JSON.")
        response = json.loads(json_output_line)

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "Invalid JSON message")

    def test_unknown_command(self):
        command = '{"command": "non_existent_command", "data": "test"}\nquit\n'
        self._run_server_for_input(command)
        
        output = self.mock_stdout.getvalue()
        json_output_line = ""
        for line in output.splitlines():
            if line.strip().startswith("{"):
                try:
                    parsed_line = json.loads(line)
                    if parsed_line.get("status") == "error" and "Unknown command" in parsed_line.get("error",""):
                         json_output_line = line
                         break
                except json.JSONDecodeError:
                    continue
        
        self.assertTrue(json_output_line, "No error JSON output for unknown command.")
        response = json.loads(json_output_line)

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "Unknown command or malformed request")

    def test_quit_command(self):
        self.assertFalse(self.server.running, "Server should not be running before start")
        
        # McpServer logs to a logger named '__main__' when run as a script,
        # or 'mcp.server' if imported. Let's check which one it is or capture from root logger.
        # The logger in mcp/server.py is `logger = logging.getLogger(__name__)`
        # When tests run it via `from mcp.server import McpServer`, __name__ will be 'mcp.server'.
        with self.assertLogs('mcp.server', level='INFO') as cm:
            self._run_server_for_input("quit\n")
        
        self.assertFalse(self.server.running, "Server should be stopped after 'quit' command")
        
        # Check captured log messages
        self.assertTrue(any("Received quit signal or empty line, stopping STDIO listener." in message for message in cm.output))


if __name__ == '__main__':
    unittest.main()

# Create dummy mcp/__init__.py if it doesn't exist, so 'from mcp.server' works
# This is more of a project setup thing, but helpful for the test runner here.
if not os.path.exists(os.path.join(project_root, 'mcp', '__init__.py')):
    with open(os.path.join(project_root, 'mcp', '__init__.py'), 'w') as f:
        pass # Create empty __init__.py

# Create dummy tests/__init__.py if it doesn't exist for test discovery
if not os.path.exists(os.path.join(project_root, 'tests', '__init__.py')):
    with open(os.path.join(project_root, 'tests', '__init__.py'), 'w') as f:
        pass # Create empty __init__.py
