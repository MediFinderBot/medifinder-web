"""
LLM Client for Anthropic Claude API with MCP tool integration.
"""
import anthropic
import os
import json
import logging
from typing import List, Dict, Any, AsyncGenerator

logger = logging.getLogger(__name__)

class LLMClient:
    """Client for interacting with the Anthropic Claude API."""
    
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY environment variable not set")
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
        
    async def generate_response(self, 
                              conversation_history: List[Dict[str, str]], 
                              mcp_tools: List = None) -> AsyncGenerator:
        """
        Generate a response using the Anthropic Claude API with MCP tools.
        
        Args:
            conversation_history: List of conversation messages
            mcp_tools: List of MCP tools available for the model
            
        Yields:
            Chunks of the response as they are generated
        """
        messages = []
        for msg in conversation_history:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
        
        system_prompt = """
        Eres un asistente especializado en información sobre disponibilidad de medicamentos en centros de salud del noroeste peruano.
        
        Cuando te pregunten sobre medicamentos o inventario médico, utiliza las herramientas disponibles para proporcionar información precisa.
        NO pidas permiso para utilizar herramientas, úsalas directamente cuando sea necesario.
        
        Sigue estos pasos al responder consultas sobre medicamentos:
        1. Analiza la consulta del usuario para identificar qué información necesita
        2. Selecciona la herramienta más adecuada para obtener esa información
        3. Interpreta los resultados obtenidos, extrayendo los datos más relevantes
        4. Presenta la información de manera clara y útil, incluyendo:
           - Disponibilidad del medicamento
           - Ubicaciones donde está disponible
           - Información sobre stock
           - Cualquier otra información relevante
        
        Si el usuario hace una pregunta no relacionada con medicamentos o inventario médico, responde amablemente que estás especializado en información sobre medicamentos y no puedes ayudar con otros temas.
        
        Herramientas disponibles:
        - search_medicines: Buscar medicamentos por nombre o ubicación
        - get_medicine_locations: Encontrar lugares donde un medicamento está disponible
        - get_medicine_stock: Obtener información de stock para un medicamento específico
        - get_regional_statistics: Obtener estadísticas de medicamentos por región
        - get_medicine_status: Obtener estadísticas generales de medicamentos
        
        Asegúrate de proporcionar respuestas completas y útiles basadas en los datos obtenidos.
        """
        
        # Convert MCP tools to Anthropic tool format
        anthropic_tools = []
        if mcp_tools:
            for tool in mcp_tools:
                # Parse the JSON schema if it's a string
                schema_json = {}
                if hasattr(tool, 'parameters_schema') and tool.parameters_schema:
                    try:
                        if isinstance(tool.parameters_schema, str):
                            schema_json = json.loads(tool.parameters_schema)
                        else:
                            schema_json = tool.parameters_schema
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse schema for tool {tool.name}")
                
                tool_def = {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": schema_json
                }
                anthropic_tools.append(tool_def)
        
        try:
            logger.info(f"Generating response with model {self.model}")
            
            # Set up message parameters
            params = {
                "model": self.model,
                "max_tokens": 2000,
                "temperature": 0.7,
                "system": system_prompt,
                "messages": messages,
                "stream": True
            }
            
            # Add tools if available
            if anthropic_tools:
                params["tools"] = anthropic_tools
            
            # Stream the response
            full_response = ""
            tool_calls = []
            
            logger.info("Starting response streaming")
            
            response_stream = await self.client.messages.create(**params)
            
            async for chunk in response_stream:
                # Process text content
                if chunk.type == "content_block_delta" and chunk.delta.type == "text_delta":
                    text = chunk.delta.text
                    full_response += text
                    yield {"type": "chunk", "content": text}
                
                # Process tool use
                elif chunk.type == "tool_use":
                    tool_use = {
                        "name": chunk.tool_use.name,
                        "arguments": chunk.tool_use.input
                    }
                    tool_calls.append(tool_use)
                    yield {"type": "tool_use", "tool": tool_use}
                
                # Process content blocks
                elif chunk.type == "content_block_start" and chunk.content_block.type == "tool_use":
                    tool_use = {
                        "name": chunk.content_block.tool_use.name,
                        "arguments": chunk.content_block.tool_use.input
                    }
                    tool_calls.append(tool_use)
                    yield {"type": "tool_use", "tool": tool_use}
            
            # Final response object with all accumulated data
            yield {"type": "complete", "content": full_response, "tool_calls": tool_calls}
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            yield {"type": "error", "error": str(e)}