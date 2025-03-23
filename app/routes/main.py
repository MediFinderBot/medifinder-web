"""
Main routes for the Medifinder Web application.
"""
import json
import logging
import asyncio
import traceback
from flask import Blueprint, render_template, request, jsonify, session, Response, stream_with_context

from app.mcp.client import MCPClient
from app.llm.client import LLMClient

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
main_bp = Blueprint('main', __name__)

# Initialize clients
mcp_client = MCPClient()
llm_client = LLMClient()

@main_bp.route('/')
def index():
    """Render the main chat interface."""
    return render_template('index.html')

@main_bp.route('/api/chat', methods=['POST'])
async def chat():
    """Process a chat message and stream the response."""
    data = request.json
    user_message = data.get('message', '')
    
    if not user_message.strip():
        return jsonify({'error': 'Empty message'}), 400
    
    # Initialize conversation history if not exists
    if 'conversation' not in session:
        session['conversation'] = []
    
    # Add user message to conversation history
    session['conversation'].append({'role': 'user', 'content': user_message})
    
    # Make session modifications persistent
    session.modified = True
    
    # Stream the response
    return Response(
        stream_with_context(generate_response(session['conversation'])),
        content_type='text/event-stream'
    )

async def generate_response(conversation):
    """Generate and stream the response from the LLM."""
    try:
        # Initialize MCP client if needed
        if not hasattr(mcp_client, 'session') or not mcp_client.session:
            await mcp_client.initialize()
        
        # Get available tools from MCP server
        tools = await mcp_client.get_tools()
        
        # Start streaming response
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        # Stream response from LLM
        full_response = ""
        async for chunk in llm_client.generate_response(conversation, tools):
            if chunk['type'] == 'chunk':
                # Text chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk['content']})}\n\n"
                full_response += chunk['content']
                
            elif chunk['type'] == 'tool_use':
                # Tool usage
                tool = chunk['tool']
                tool_name = tool['name']
                tool_args = tool['arguments']
                
                # Log tool usage
                logger.info(f"LLM is using tool: {tool_name} with args: {tool_args}")
                
                # Call the tool
                try:
                    tool_result = await mcp_client.call_tool(tool_name, tool_args)
                    # Send tool result to frontend
                    yield f"data: {json.dumps({'type': 'tool_result', 'name': tool_name, 'arguments': tool_args, 'result': tool_result})}\n\n"
                except Exception as e:
                    error_msg = f"Error calling tool {tool_name}: {str(e)}"
                    logger.error(error_msg)
                    yield f"data: {json.dumps({'type': 'tool_error', 'name': tool_name, 'error': error_msg})}\n\n"
            
            elif chunk['type'] == 'complete':
                # Add assistant response to conversation history
                if 'conversation' in session:
                    session['conversation'].append({'role': 'assistant', 'content': chunk['content']})
                    session.modified = True
            
            elif chunk['type'] == 'error':
                # Error in LLM response
                error_msg = chunk.get('error', 'Unknown error')
                logger.error(f"LLM error: {error_msg}")
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
        
        # End streaming
        yield f"data: {json.dumps({'type': 'end'})}\n\n"
        
    except Exception as e:
        logger.error(f"Error in generate_response: {str(e)}")
        logger.error(traceback.format_exc())
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

@main_bp.route('/api/reset', methods=['POST'])
def reset_conversation():
    """Reset the conversation history."""
    if 'conversation' in session:
        session.pop('conversation')
    return jsonify({"status": "ok"})

@main_bp.route('/api/health', methods=['GET'])
async def health_check():
    """Check the health of the application and its dependencies."""
    status = {
        "app": "ok",
        "mcp": "unknown",
        "tools": []
    }
    
    try:
        # Initialize MCP client if needed
        if not hasattr(mcp_client, 'session') or not mcp_client.session:
            await mcp_client.initialize()
        
        # Get available tools
        tools = await mcp_client.get_tools()
        status["mcp"] = "ok"
        status["tools"] = [t.name for t in tools]
    except Exception as e:
        status["mcp"] = "error"
        status["mcp_error"] = str(e)
    
    return jsonify(status)