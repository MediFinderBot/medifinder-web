"""
MCP Client implementation for connecting to the MCP server.
This client uses the StdIO transport for process-based communication.
"""
import os
import asyncio
import logging
from typing import Optional, Dict, Any, List
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

class MCPClient:
    """Client for connecting to the MCP server using StdIO transport."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Implement Singleton pattern to maintain a single instance."""
        if cls._instance is None:
            cls._instance = super(MCPClient, cls).__new__(cls)
            # Initialize attributes
            cls._instance.session = None
            cls._instance.exit_stack = AsyncExitStack()
            cls._instance.tools = None
            cls._instance.connected = False
            cls._instance.server_process = None
        return cls._instance
    
    async def connect(self):
        """Connect to the MCP server."""
        try:
            # If there's an existing connection, close it to start fresh
            if self.connected and self.session:
                logger.info("Closing existing connection before reconnecting")
                await self.close()
            
            # Get server path from environment variable
            server_script_path = os.environ.get("MCP_SERVER_PATH", "main.py")
            
            # Get Python interpreter path (optional)
            python_interpreter = os.environ.get("MCP_PYTHON_INTERPRETER", "python")
            
            # Determine if it's a Python or JS server (assuming Python by default)
            is_python = server_script_path.endswith('.py')
            is_js = server_script_path.endswith('.js')
            if not (is_python or is_js):
                logger.warning(f"Server script {server_script_path} has an unexpected extension, assuming Python")
                is_python = True
                
            # Set command based on script type
            command = python_interpreter if is_python else "node"
            
            # Prepare environment variables dictionary
            env = {
                # Pass necessary environment variables to the MCP server
                "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
                "DB_HOST": os.environ.get("DB_HOST", "localhost"),
                "DB_PORT": os.environ.get("DB_PORT", "5432"),
                "DB_NAME": os.environ.get("DB_NAME", "medifinderbot"),
                "DB_USER": os.environ.get("DB_USER", "postgres"),
                "DB_PASSWORD": os.environ.get("DB_PASSWORD", ""),
                "ENV": os.environ.get("ENV", "development"),
                "DEBUG": os.environ.get("DEBUG", "True"),
            }
            
            # Create server parameters with environment variables
            server_params = StdioServerParameters(
                command=command,
                args=[server_script_path],
                env=env
            )
            
            logger.info(f"Connecting to MCP server: {command} {server_script_path}")
            
            # Create new exit stack
            self.exit_stack = AsyncExitStack()
            
            # Establish the StdIO connection
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            read_stream, write_stream = stdio_transport
            
            # Create and initialize the client session
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            
            # Initialize the session
            await self.session.initialize()
            logger.info("MCP session initialized successfully")
            
            # Cache available tools
            await self.refresh_capabilities()
            self.connected = True
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {e}", exc_info=True)
            await self.close()
            return False
        
    async def refresh_capabilities(self):
        """Refresh the list of available tools and resources."""
        if not self.session:
            logger.error("Cannot refresh capabilities: Session not initialized")
            return
            
        # Get available tools
        try:
            tools_response = await self.session.list_tools()
            self.tools = tools_response.tools
            logger.info(f"Found {len(self.tools)} available tools")
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            self.tools = []
        
    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get formatted available tools for Anthropic API."""
        if not self.tools:
            await self.refresh_capabilities()
            
        if not self.tools:
            return []
            
        # Format tools for Anthropic
        anthropic_tools = []
        for tool in self.tools:
            try:
                tool_schema = tool.inputSchema
                tool_def = {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool_schema
                }
                anthropic_tools.append(tool_def)
            except Exception as e:
                logger.error(f"Error formatting tool {tool.name}: {e}")
                
        return anthropic_tools
    
    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server with the provided arguments."""
        if not self.session:
            logger.error("Cannot call tool: Session not initialized")
            raise RuntimeError("MCP session not initialized")
            
        try:
            logger.info(f"Calling tool '{tool_name}' with arguments: {tool_args}")
            result = await self.session.call_tool(tool_name, tool_args)
            logger.info(f"Tool '{tool_name}' call completed")
            return result
        except Exception as e:
            logger.error(f"Error calling tool '{tool_name}': {e}")
            raise
    
    async def close(self):
        """Close the connection with the MCP server."""
        try:
            logger.info("Closing MCP client")
            if hasattr(self, 'exit_stack') and self.exit_stack:
                try:
                    await self.exit_stack.aclose()
                except Exception as close_error:
                    logger.error(f"Error closing exit stack: {close_error}")
                self.exit_stack = AsyncExitStack()
            self.session = None
            self.tools = None
            self.connected = False
            logger.info("MCP client closed")
        except Exception as e:
            logger.error(f"Error closing MCP client: {e}")
            
    async def keep_alive(self):
        """Keep the connection alive by performing a simple operation."""
        if not self.connected or not self.session:
            return await self.connect()
        
        try:
            # Perform a simple operation to verify the connection is still active
            await self.session.list_tools()
            return True
        except Exception as e:
            logger.warning(f"The MCP connection appears to be down, attempting to reconnect: {e}")
            return await self.connect()