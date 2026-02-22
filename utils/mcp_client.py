"""
╔══════════════════════════════════════════════════════════╗
║      TARS — MCP Client (Model Context Protocol)         ║
╠══════════════════════════════════════════════════════════╣
║  Connects to external MCP servers and exposes their      ║
║  tools to TARS. Supports stdio transport.                ║
║                                                          ║
║  Config (config.yaml):                                   ║
║    mcp:                                                  ║
║      servers:                                            ║
║        - name: "filesystem"                              ║
║          command: "npx"                                  ║
║          args: ["-y", "@modelcontextprotocol/server-fs"] ║
║        - name: "github"                                  ║
║          command: "npx"                                  ║
║          args: ["-y", "@modelcontextprotocol/server-gh"] ║
║          env:                                            ║
║            GITHUB_TOKEN: "ghp_..."                       ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import json
import subprocess
import threading
import logging
import time

logger = logging.getLogger("tars.mcp")


class MCPServer:
    """Represents a single MCP server connection (stdio transport)."""

    def __init__(self, name, command, args=None, env=None, cwd=None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd
        self._process = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._tools = []  # Discovered tools
        self._connected = False

    def connect(self):
        """Start the MCP server process and initialize the connection."""
        try:
            # Build environment
            env = os.environ.copy()
            env.update(self.env)

            # Start the server process
            cmd = [self.command] + self.args
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=self.cwd,
            )

            # Send initialize request (JSON-RPC 2.0)
            init_response = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "tars", "version": "5.0"},
            })

            if init_response and not init_response.get("error"):
                # Send initialized notification
                self._send_notification("notifications/initialized", {})
                self._connected = True

                # Discover tools
                tools_response = self._send_request("tools/list", {})
                if tools_response and "result" in tools_response:
                    self._tools = tools_response["result"].get("tools", [])
                    logger.info(f"  🔌 MCP '{self.name}': {len(self._tools)} tools available")
                else:
                    self._tools = []
                    logger.info(f"  🔌 MCP '{self.name}': connected (no tools listed)")
            else:
                error = init_response.get("error", {}).get("message", "Unknown error") if init_response else "No response"
                logger.warning(f"  🔌 MCP '{self.name}' init failed: {error}")
                self._connected = False

        except FileNotFoundError:
            logger.warning(f"  🔌 MCP '{self.name}': command not found: {self.command}")
            self._connected = False
        except Exception as e:
            logger.warning(f"  🔌 MCP '{self.name}' connect error: {e}")
            self._connected = False

    def disconnect(self):
        """Stop the MCP server process."""
        if self._process:
            try:
                self._process.stdin.close()
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            self._connected = False

    def call_tool(self, tool_name, arguments=None):
        """Call a tool on this MCP server.
        
        Returns standard TARS tool result dict.
        """
        if not self._connected or not self._process:
            return {"success": False, "error": True, "content": f"MCP server '{self.name}' not connected."}

        try:
            response = self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments or {},
            })

            if not response:
                return {"success": False, "error": True, "content": f"MCP '{self.name}': no response for tool '{tool_name}'."}

            if response.get("error"):
                error_msg = response["error"].get("message", str(response["error"]))
                return {"success": False, "error": True, "content": f"MCP '{self.name}' error: {error_msg}"}

            result = response.get("result", {})
            content_parts = result.get("content", [])

            # Extract text content from MCP response
            text_parts = []
            for part in content_parts:
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif part.get("type") == "image":
                    text_parts.append(f"[Image: {part.get('mimeType', 'image')}]")
                elif part.get("type") == "resource":
                    text_parts.append(f"[Resource: {part.get('uri', '')}]")

            content = "\n".join(text_parts) if text_parts else json.dumps(result, indent=2)

            is_error = result.get("isError", False)
            return {
                "success": not is_error,
                "error": is_error,
                "content": content[:5000],
            }

        except Exception as e:
            return {"success": False, "error": True, "content": f"MCP tool call error: {e}"}

    def get_tools(self):
        """Return the list of tools discovered from this server."""
        return self._tools

    def _send_request(self, method, params):
        """Send a JSON-RPC 2.0 request and wait for response."""
        with self._lock:
            if not self._process or self._process.poll() is not None:
                return None

            self._request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params,
            }

            try:
                msg = json.dumps(request) + "\n"
                self._process.stdin.write(msg.encode("utf-8"))
                self._process.stdin.flush()

                # Read response with timeout to prevent blocking forever
                import select
                ready, _, _ = select.select([self._process.stdout], [], [], 30)
                if not ready:
                    logger.warning(f"  🔌 MCP '{self.name}' read timeout (30s) for {method}")
                    return None

                line = self._process.stdout.readline()
                if not line:
                    return None

                return json.loads(line.decode("utf-8"))
            except Exception as e:
                logger.debug(f"  🔌 MCP '{self.name}' request error: {e}")
                return None

    def _send_notification(self, method, params):
        """Send a JSON-RPC 2.0 notification (no response expected)."""
        if not self._process or self._process.poll() is not None:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            msg = json.dumps(notification) + "\n"
            self._process.stdin.write(msg.encode("utf-8"))
            self._process.stdin.flush()
        except Exception:
            pass


class MCPClient:
    """Manages multiple MCP server connections and routes tool calls.
    
    Usage:
        client = MCPClient(config)
        client.connect_all()
        result = client.call_tool("mcp_filesystem__read_file", {"path": "/tmp/test.txt"})
        client.disconnect_all()
    """

    def __init__(self, config):
        self.config = config
        self.servers = {}  # name → MCPServer
        self._available = False

        # Parse server configs
        mcp_config = config.get("mcp", {})
        server_configs = mcp_config.get("servers", [])

        for sc in server_configs:
            name = sc.get("name", "")
            command = sc.get("command", "")
            if name and command:
                self.servers[name] = MCPServer(
                    name=name,
                    command=command,
                    args=sc.get("args", []),
                    env=sc.get("env", {}),
                    cwd=sc.get("cwd"),
                )

    def connect_all(self):
        """Connect to all configured MCP servers."""
        if not self.servers:
            logger.info("  🔌 No MCP servers configured")
            return

        connected = 0
        for name, server in self.servers.items():
            server.connect()
            if server._connected:
                connected += 1

        self._available = connected > 0
        if connected:
            logger.info(f"  🔌 MCP client: {connected}/{len(self.servers)} servers connected")
        else:
            logger.info(f"  🔌 MCP client: no servers connected")

    def disconnect_all(self):
        """Disconnect from all MCP servers."""
        for server in self.servers.values():
            server.disconnect()
        self._available = False

    @property
    def available(self):
        return self._available

    def list_tools(self):
        """List all available tools across all connected MCP servers.
        
        Returns standard tool result dict.
        """
        if not self._available:
            return {"success": False, "error": True, "content": "No MCP servers connected."}

        lines = ["## Available MCP Tools\n"]
        total = 0

        for name, server in self.servers.items():
            if not server._connected:
                continue
            tools = server.get_tools()
            if tools:
                lines.append(f"### {name} ({len(tools)} tools)")
                for t in tools:
                    desc = t.get("description", "No description")[:100]
                    lines.append(f"  - `mcp_{name}__{t['name']}` — {desc}")
                total += len(tools)
                lines.append("")

        if total == 0:
            return {"success": True, "content": "MCP servers connected but no tools available."}

        return {"success": True, "content": "\n".join(lines)}

    def call_tool(self, tool_ref, arguments=None):
        """Call an MCP tool by its qualified name (mcp_<server>__<tool>).
        
        Args:
            tool_ref: "mcp_<server_name>__<tool_name>" format
            arguments: dict of arguments for the tool
        
        Returns standard tool result dict.
        """
        if not self._available:
            return {"success": False, "error": True, "content": "No MCP servers connected."}

        # Parse tool reference: mcp_servername__toolname
        if not tool_ref.startswith("mcp_"):
            return {"success": False, "error": True, "content": f"Invalid MCP tool reference: {tool_ref}. Must start with 'mcp_'."}

        parts = tool_ref[4:].split("__", 1)  # Remove "mcp_" prefix, split on "__"
        if len(parts) != 2:
            return {"success": False, "error": True, "content": f"Invalid MCP tool format: {tool_ref}. Expected: mcp_<server>__<tool>."}

        server_name, tool_name = parts

        if server_name not in self.servers:
            return {"success": False, "error": True, "content": f"MCP server '{server_name}' not found. Available: {list(self.servers.keys())}"}

        server = self.servers[server_name]
        if not server._connected:
            return {"success": False, "error": True, "content": f"MCP server '{server_name}' is not connected."}

        return server.call_tool(tool_name, arguments)

    def get_tool_schemas(self):
        """Get tool schemas in TARS format for all MCP tools.
        
        Returns a list of tool schema dicts compatible with brain/tools.py format.
        """
        schemas = []

        for server_name, server in self.servers.items():
            if not server._connected:
                continue

            for tool in server.get_tools():
                tars_name = f"mcp_{server_name}__{tool['name']}"
                schema = {
                    "name": tars_name,
                    "description": f"[MCP: {server_name}] {tool.get('description', 'No description')}",
                    "input_schema": tool.get("inputSchema", {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    }),
                }
                schemas.append(schema)

        return schemas

    def get_stats(self):
        """Get MCP client statistics."""
        stats = {
            "configured": len(self.servers),
            "connected": sum(1 for s in self.servers.values() if s._connected),
            "total_tools": sum(len(s.get_tools()) for s in self.servers.values() if s._connected),
            "servers": {},
        }
        for name, server in self.servers.items():
            stats["servers"][name] = {
                "connected": server._connected,
                "tools": len(server.get_tools()),
            }
        return stats
