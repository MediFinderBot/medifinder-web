#!/usr/bin/env python
"""
Helper script to run MCP tools in separate processes.
Run as a separate process to avoid issues with event loops.
"""

import asyncio
import json
import sys
import os
import logging
import inspect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("tool_runner")

# Helper function to convert the result to a serializable dictionary
def result_to_dict(result):
    """Converts complex objects to a JSON-serializable format"""
    try:
        # If it's a primitive type that JSON can handle directly
        if result is None or isinstance(result, (str, int, float, bool)):
            return {"content": result}
            
        # If it's a list or dictionary, verify if its contents are serializable
        if isinstance(result, (list, dict)):
            # Try to serialize directly to see if it works
            try:
                json.dumps(result)
                return {"content": result}
            except TypeError:
                # If it fails, we need to process the content
                pass
                
        # Check if it has a 'content' attribute or method to access it
        content = None
        
        # Attempt 1: If it's an object with a 'content' attribute
        if hasattr(result, 'content'):
            content = result.content
            logger.info(f"Extracting content via attribute: {type(content)}")
            
        # Attempt 2: If it's an object that can be used as a dictionary
        elif hasattr(result, '__getitem__') and 'content' in result:
            content = result['content']
            logger.info(f"Extracting content via __getitem__: {type(content)}")
            
        # If we got content, process it recursively if necessary
        if content is not None:
            # If the content is still not serializable, process it
            try:
                json.dumps(content)
                return {"content": content}
            except TypeError:
                # If the content is of type TextContent or similar
                if hasattr(content, 'text'):
                    logger.info(f"Extracting text from content: {type(content)}")
                    return {"content": content.text}
                # For other complex types, try to convert to string
                return {"content": str(content)}
        
        # Attempt 3: If it has to_dict or to_json method
        if hasattr(result, 'to_dict'):
            return {"content": result.to_dict()}
        elif hasattr(result, 'to_json'):
            return {"content": result.to_json()}
        
        # Attempt 4: If it has special attributes for TextContent
        if hasattr(result, 'text'):
            logger.info(f"Object has 'text' attribute: {type(result)}")
            return {"content": result.text}
            
        # Attempt 5: If it has __dict__ attribute
        if hasattr(result, '__dict__'):
            # Get attributes but exclude methods and private attributes
            attrs = {k: v for k, v in result.__dict__.items() 
                    if not k.startswith('_') and not inspect.ismethod(v)}
            
            # Check if there are useful attributes
            if attrs:
                try:
                    json.dumps(attrs)  # Test if it's serializable
                    return {"content": attrs}
                except TypeError:
                    pass
                    
        # Last resort: convert to string
        return {"content": str(result)}
    
    except Exception as e:
        logger.error(f"Error converting result to dictionary: {e}", exc_info=True)
        return {"error": f"Error processing result: {str(e)}"}

async def main():
    try:
        # Verify arguments
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Arguments required: tool_name and tool_args_json"}))
            return 1
            
        # Get arguments
        tool_name = sys.argv[1]
        tool_args = json.loads(sys.argv[2])
        
        logger.info(f"Executing tool: {tool_name} with arguments: {tool_args}")
        
        # Import dynamically to avoid circular import problems
        from app.mcp.client import MCPClient
        
        # Create MCP client
        mcp = MCPClient()
        
        # Connect to server
        connected = await mcp.connect()
        if not connected:
            print(json.dumps({"error": "Could not connect to MCP server"}))
            return 1
        
        # Call the tool
        logger.info(f"Connection established, calling the tool...")
        result = await mcp.call_tool(tool_name, tool_args)
        logger.info(f"Tool executed successfully: {type(result)}")
        
        # Close connection
        await mcp.close()
        
        # Convert the result to a serializable format
        serializable_result = result_to_dict(result)
        logger.info(f"Result converted to serializable format: {type(serializable_result)}")
        
        # Verify if it's serializable
        try:
            json_result = json.dumps(serializable_result)
            # Print result as JSON
            print(json_result)
            return 0
        except TypeError as e:
            logger.error(f"The result is still not serializable: {e}")
            # Try a simpler conversion
            print(json.dumps({"content": str(result)}))
            return 0
            
    except Exception as e:
        import traceback
        logger.error(f"Error in tool_runner: {e}")
        logger.error(traceback.format_exc())
        print(json.dumps({"error": str(e)}))
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        print(json.dumps({"error": f"Error in asyncio.run: {str(e)}"}))
        sys.exit(1)