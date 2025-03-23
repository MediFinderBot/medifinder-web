"""
MCP Client implementation for connecting to the MCP server.
This client uses the HTTP SSE transport for web-based applications.
"""
from mcp import ClientSession, types
from mcp.client.http import http_client
import asyncio
import os
import logging

logger = logging.getLogger(__name__)

class MCPClient:
    """Client for connecting to the MCP server using HTTP SSE transport."""
    
    def __init__(self):
        # URL for the MCP server
        self.server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:3000")
        self.session = None
        self.tools = None
        self.resources = None
        
    async def initialize(self):
        """Initialize the connection with the MCP server."""
        try:
            logger.info(f"Connecting to MCP server at {self.server_url}")
            self.read_stream, self.write_stream = await http_client(self.server_url)
            
            self.session = ClientSession(
                self.read_stream, 
                self.write_stream,
                sampling_callback=None  # We'll use an external LLM API
            )
            
            await self.session.initialize()
            logger.info("MCP session initialized successfully")
            
            # Cache available tools and resources
            await self.refresh_capabilities()
            
            return self.session
        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {e}")
            raise
        
    async def refresh_capabilities(self):
        """Refresh the list of available tools and resources."""
        if not self.session:
            await self.initialize()
            
        # Get available tools
        self.tools = await self.session.list_tools()
        logger.info(f"Found {len(self.tools)} available tools")
        
        # Get available resources
        self.resources = await self.session.list_resources()
        logger.info(f"Found {len(self.resources)} available resources")
        
    async def get_tools(self):
        """Get available tools from the MCP server."""
        if not self.tools:
            await self.refresh_capabilities()
        return self.tools
    
    async def call_tool(self, tool_name, arguments):
        """Call a tool on the MCP server with the provided arguments."""
        if not self.session:
            await self.initialize()
            
        try:
            logger.info(f"Calling tool '{tool_name}' with arguments: {arguments}")
            result = await self.session.call_tool(tool_name, arguments)
            logger.info(f"Tool '{tool_name}' call completed")
            return result
        except Exception as e:
            logger.error(f"Error calling tool '{tool_name}': {e}")
            raise
    
    async def read_resource(self, resource_uri):
        """Read a resource from the MCP server."""
        if not self.session:
            await self.initialize()
            
        try:
            logger.info(f"Reading resource '{resource_uri}'")
            content, mime_type = await self.session.read_resource(resource_uri)
            logger.info(f"Resource '{resource_uri}' read successfully")
            return content, mime_type
        except Exception as e:
            logger.error(f"Error reading resource '{resource_uri}': {e}")
            raise
    
    async def close(self):
        """Close the connection with the MCP server."""
        if self.session:
            try:
                await self.session.close()
                logger.info("MCP session closed")
            except Exception as e:
                logger.error(f"Error closing MCP session: {e}")
        self.session = None
        self.tools = None
        self.resources = None