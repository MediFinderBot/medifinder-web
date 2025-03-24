"""
Main routes for the Medifinder Web application.
"""
import json
import logging
import asyncio
import traceback
from queue import Queue, Empty
from threading import Thread
from flask import Blueprint, render_template, request, jsonify, session, Response, current_app

from app.mcp.client import MCPClient
from app.llm.client import LLMClient

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
main_bp = Blueprint('main', __name__)

# Initialize clients
mcp_client = MCPClient()
llm_client = LLMClient()

# Globals for tracking state
mcp_initialized = False

@main_bp.route('/')
def index():
    """Render the main chat interface."""
    return render_template('index.html')

def check_mcp_connection():
    """Check or establish MCP connection using a separate thread and event loop."""
    global mcp_initialized  # Declare global here
    result_queue = Queue()
    
    def run_async_connection():
        global mcp_initialized  # And also here, in the nested function
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Try to connect or verify connection
            if not mcp_initialized:
                connected = loop.run_until_complete(mcp_client.connect())
                if connected:
                    mcp_initialized = True
                    result_queue.put(("success", "Conectado al servidor MCP"))
                else:
                    result_queue.put(("error", "No se pudo conectar al servidor MCP"))
            else:
                # Check if connection is still alive
                alive = loop.run_until_complete(mcp_client.keep_alive())
                if alive:
                    result_queue.put(("success", "Conexión MCP activa"))
                else:
                    result_queue.put(("error", "Conexión MCP perdida, no se pudo reconectar"))
            
            # Close the event loop
            loop.close()
        except Exception as e:
            logger.error(f"Error checking MCP connection: {str(e)}")
            result_queue.put(("error", str(e)))
    
    # Start connection check in a separate thread
    connection_thread = Thread(target=run_async_connection)
    connection_thread.daemon = True
    connection_thread.start()
    
    # Wait for connection check to complete (with timeout)
    connection_thread.join(timeout=10.0)
    
    # Check result
    try:
        return result_queue.get(block=False)
    except Empty:
        logger.error("Timeout checking MCP connection")
        return ("error", "Timeout checking MCP connection")

@main_bp.route('/api/chat', methods=['POST'])
def chat():
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
    session.modified = True
    
    # Save current conversation for reference
    current_conversation = list(session['conversation'])
    
    # Add a placeholder for the assistant's response (we'll update it in the frontend)
    assistant_placeholder = "Procesando respuesta..."
    session['conversation'].append({'role': 'assistant', 'content': assistant_placeholder})
    session.modified = True
    
    # Check MCP connection before starting streaming
    connection_status, connection_message = check_mcp_connection()
    if connection_status == "error":
        logger.error(f"MCP connection error: {connection_message}")
        return jsonify({'error': f'Error de conexión MCP: {connection_message}'}), 500
    
    # Function to generate streaming response
    def generate():
        try:
            # Local variables for tracking
            full_response = ""
            
            # Start LLM processing in a separate thread
            response_queue = Queue()
            
            def process_llm_response():
                try:
                    # DO NOT create an event loop here
                    # Simply generate response and process
                    llm_generator = llm_client.generate_response(current_conversation, mcp_client)
                    for response_chunk in llm_generator:
                        response_queue.put(response_chunk)
                        
                        # If it's the final response, save it
                        if response_chunk.get('type') == 'complete':
                            if 'content' in response_chunk:
                                response_queue.put(('final_response', response_chunk['content']))
                                
                except Exception as e:
                    logger.error(f"Error processing LLM response: {e}", exc_info=True)
                    response_queue.put({"type": "error", "error": str(e)})
                    
                # Indicate that we're done
                response_queue.put(('done', None))
            
            # Start the processing thread
            process_thread = Thread(target=process_llm_response)
            process_thread.daemon = True
            process_thread.start()
            
            # Stream the response
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            
            # Variables for tracking
            complete_response = None
            done = False
            
            # Process responses until complete
            while not done:
                try:
                    # Wait for the next chunk (with timeout)
                    chunk = response_queue.get(timeout=30.0)
                    
                    # Check if it's a special message
                    if isinstance(chunk, tuple) and chunk[0] == 'done':
                        done = True
                        continue
                    elif isinstance(chunk, tuple) and chunk[0] == 'final_response':
                        complete_response = chunk[1]
                        continue
                    
                    # Send the chunk to the client
                    yield f"data: {json.dumps(chunk)}\n\n"
                    
                    # Accumulate response text if it's a text chunk
                    if chunk.get('type') in ['chunk', 'follow_up'] and 'content' in chunk:
                        full_response += chunk['content']
                        
                except Empty:
                    # Timeout waiting for response
                    logger.error("Timeout waiting for LLM response")
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Timeout esperando respuesta'})}\n\n"
                    done = True
            
            # Update complete response variable if not set before
            if complete_response is None:
                complete_response = full_response
                
            # Signal that the response is finished
            yield f"data: {json.dumps({'type': 'end', 'complete_response': complete_response})}\n\n"
            
        except Exception as e:
            logger.error(f"Error in generate_response: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'end'})}\n\n"
    
    # Return streaming response
    return Response(
        generate(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        }
    )

@main_bp.route('/api/reset', methods=['POST'])
def reset_conversation():
    """Reset the conversation history."""
    if 'conversation' in session:
        session.pop('conversation')
    return jsonify({"status": "ok"})

@main_bp.route('/api/health', methods=['GET'])
def health_check():
    """Check the health of the application and its dependencies."""
    status = {
        "app": "ok",
        "mcp": "unknown",
        "llm": "unknown",
        "tools": []
    }
    
    # Check MCP connection
    connection_status, message = check_mcp_connection()
    status["mcp"] = connection_status
    
    if connection_status == "success":
        # Get tools list
        tool_thread = Thread(target=lambda q: q.put(get_mcp_tools()), args=(Queue(),))
        tool_thread.daemon = True
        tool_queue = Queue()
        tool_thread.start()
        tool_thread.join(timeout=5.0)
        
        try:
            tools = tool_queue.get(block=False)
            status["tools"] = tools
        except Empty:
            status["mcp"] = "error"
            status["mcp_error"] = "Timeout getting tools list"
    else:
        status["mcp_error"] = message
    
    # Check LLM API key
    if os.environ.get("ANTHROPIC_API_KEY"):
        status["llm"] = "ok"
    else:
        status["llm"] = "error"
        status["llm_error"] = "API key not set"
    
    return jsonify(status)

def get_mcp_tools():
    """Get tools from MCP server using a separate event loop."""
    try:
        # Create a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Get tools
        tools = loop.run_until_complete(mcp_client.get_tools())
        
        # Close loop
        loop.close()
        
        # Return tool names
        return [tool.get("name") for tool in tools]
    except Exception as e:
        logger.error(f"Error getting MCP tools: {e}")
        return []