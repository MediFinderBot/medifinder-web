"""
LLM Client for Anthropic Claude API with MCP tool integration.
"""
import anthropic
import os
import json
import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class LLMClient:
    """Client for interacting with the Anthropic Claude API."""
    
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY environment variable not set")
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
        
    def generate_response(self, 
                      conversation_history: List[Dict[str, str]], 
                      mcp_client, 
                      system_prompt: Optional[str] = None):
        """
        Generate a response using the Anthropic Claude API with MCP tools.
        
        Args:
            conversation_history: List of conversation messages
            mcp_client: MCP client object for tool calling
            system_prompt: Optional system prompt to override default
            
        Yields:
            Chunks of the response as they are generated
        """
        # Convert conversation history to the format expected by Claude
        messages = []
        for msg in conversation_history:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
        
        default_system_prompt = """
        Eres un asistente especializado en información sobre disponibilidad de medicamentos en centros de salud del noroeste peruano.
        Este es un sistema REAL, no una simulación. Las herramientas mencionadas están realmente disponibles y funcionando.

        Cuando te pregunten sobre medicamentos o inventario médico, DEBES utilizar las herramientas disponibles para proporcionar información precisa.
        No solo menciones lo que harías, EJECUTA las herramientas directamente.

        Para usar una herramienta, escribe exactamente en este formato:
        "Uso la herramienta [NOMBRE_HERRAMIENTA] con argumentos: [ARGUMENTOS_JSON]"

        Por ejemplo:
        "Uso la herramienta search_medicines con argumentos: {\"query\": \"paracetamol\", \"search_type\": \"name\"}"
        "Uso la herramienta get_medicine_locations con argumentos: {\"medicine_name\": \"ibuprofeno\"}"

        REGLA MUY IMPORTANTE: NUNCA incluyas mensajes de error, fallas o problemas de conexión en tu respuesta inicial. Asume que las herramientas funcionarán correctamente. Si realmente hubiera un problema, el sistema lo manejará automáticamente.

        Las herramientas disponibles son:
        - search_medicines: Buscar medicamentos por nombre o ubicación
        Argumentos: {"query": "nombre_medicamento", "search_type": "name", "location": "ubicación"}
        
        - get_medicine_locations: Encontrar lugares donde un medicamento está disponible
        Argumentos: {"medicine_name": "nombre_medicamento", "min_stock": 1}
        
        - get_medicine_stock: Obtener información de stock para un medicamento específico
        Argumentos: {"medicine_id": id_numérico_del_medicamento}
        
        - get_regional_statistics: Obtener estadísticas de medicamentos por región
        Argumentos: {}
        
        - get_medicine_status: Obtener estadísticas generales de medicamentos
        Argumentos: {}

        Sigue estos pasos al responder consultas sobre medicamentos:
        1. Analiza la consulta del usuario para identificar qué información necesita
        2. Selecciona la herramienta más adecuada según la consulta
        3. EJECUTA la herramienta con los argumentos apropiados usando el formato indicado
        4. Interpreta los resultados obtenidos y preséntaselos al usuario de manera clara

        Si el usuario hace una pregunta no relacionada con medicamentos o inventario médico, responde amablemente que estás especializado en información sobre medicamentos y no puedes ayudar con otros temas.
        """
        
        final_system_prompt = system_prompt if system_prompt else default_system_prompt
        
        try:
            # Start the response
            yield {"type": "start"}
            
            # Generate initial response (not using stream here)
            response = self.client.messages.create(
                model=self.model,
                system=final_system_prompt,
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            
            # Extract the response text
            response_content = ""
            for content_block in response.content:
                if content_block.type == "text":
                    response_content += content_block.text
            
            # Detect tool mentions
            tools_to_call = []
            try:
                tools_to_call = self._extract_tool_calls(response_content)
                logger.info(f"Tools detected: {len(tools_to_call)}")
            except Exception as e:
                logger.error(f"Error extracting tools: {e}", exc_info=True)
                
            # If there are tools to execute, filter the text to show only up to the last tool mention
            filtered_response = response_content
            if tools_to_call:
                # Look for patterns like "Uso la herramienta X con argumentos: {...}"
                tool_mentions = []
                
                # Main pattern to detect tool calls
                main_pattern = r'Uso la herramienta (\w+) con argumentos: ({.*?})'
                
                # Alternative patterns
                alternative_patterns = [
                    r'(?:Usaré|Voy a usar|Usando|Utilizaré|Utilizo) la herramienta (\w+) con argumentos: ({.*?})',
                    r'(?:Llamaré|Llamo|Invoco|Invocaré) a la herramienta (\w+) con argumentos: ({.*?})',
                    r'(?:Ejecutaré|Ejecuto) la herramienta (\w+) con argumentos: ({.*?})'
                ]
                
                # Search for all tool mentions in the text
                import re
                for pattern in [main_pattern] + alternative_patterns:
                    for match in re.finditer(pattern, response_content, re.DOTALL):
                        tool_mentions.append(match)
                
                # If we found tool mentions
                if tool_mentions:
                    # Sort mentions by position in the text
                    tool_mentions.sort(key=lambda m: m.start())
                    
                    # Find the last tool mention
                    last_mention = tool_mentions[-1]
                    
                    # Get the text up to the end of the last tool mention
                    # and add a small margin (50 characters) to include relevant following text
                    end_pos = min(last_mention.end() + 50, len(response_content))
                    
                    # Verify we're not cutting in the middle of a word or phrase
                    while end_pos < len(response_content) and response_content[end_pos] not in ['.', '!', '?', '\n']:
                        end_pos += 1
                    
                    # If we found the end of a sentence, include it
                    if end_pos < len(response_content):
                        end_pos += 1
                    
                    # Filter the text to show only up to that point
                    filtered_response = response_content[:end_pos]
                    
                    # Check if there's error/recovery text and remove it                    
                    error_patterns = [
                        r'Lo siento, parece que estoy teniendo problemas',
                        r'Lo siento, parece que hay un problema',
                        r'No puedo conectarme',
                        r'Error al acceder',
                        r'No fue posible ejecutar',
                        r'Hay un problema con',
                        r'No se pudo completar',
                        r'Parece que hay un error',
                        r'No estoy pudiendo acceder',
                        r'No consigo conectarme',
                        r'Tengo problemas para acceder',
                        r'La conexión al sistema',
                        r'El sistema no está respondiendo',
                        r'No logro obtener',
                        r'Estoy experimentando dificultades',
                        r'No puedo usar la herramienta',
                        r'La herramienta no está disponible',
                        r'No puedo obtener información',
                        r'Hay dificultades técnicas',
                        r'El servicio no está disponible',
                    ]

                    # Modify the filtering logic to be more aggressive in removing error messages
                    filtered_text_chunks = []
                    current_chunk = ""
                    sentences = re.split(r'(?<=[.!?])\s+', filtered_response)

                    for sentence in sentences:
                        # Check if the sentence contains any error pattern
                        contains_error = False
                        for pattern in error_patterns:
                            if re.search(pattern, sentence, re.IGNORECASE):
                                contains_error = True
                                break
                                
                        # Only add sentences that don't contain error patterns
                        if not contains_error:
                            if current_chunk:
                                current_chunk += " " + sentence
                            else:
                                current_chunk = sentence
                        else:
                            logger.info(f"Removing sentence with error pattern: {sentence}")
                            
                        # If the sentence ends with a tool call, finalize the current chunk
                        if "Uso la herramienta" in sentence and "con argumentos:" in sentence:
                            if current_chunk:
                                filtered_text_chunks.append(current_chunk)
                                current_chunk = ""

                    # Add the last chunk if it exists
                    if current_chunk:
                        filtered_text_chunks.append(current_chunk)

                    # Reconstruct the filtered text
                    filtered_response = " ".join(filtered_text_chunks)

                    # Make sure the text doesn't end abruptly
                    if not filtered_response.endswith(('.', '!', '?', '\n')):
                        filtered_response += '...'

                    # Variables to accumulate the response
                    full_response = filtered_response

                    # Send initial text (filtered if there are tools)
                    yield {"type": "chunk", "content": filtered_response}                        
            
            # Process tools if detected
            for tool_call in tools_to_call:
                tool_name = tool_call["name"]
                try:
                    tool_args = tool_call["args"]
                    
                    # Notify tool usage
                    yield {"type": "tool_use", "name": tool_name, "arguments": tool_args}
                    
                    # SOLUTION 2: Use subprocess to run an independent Python script
                    import subprocess
                    import os
                    import sys
                    
                    # Get path to tool_runner.py script
                    tool_runner_path = os.path.join(os.getcwd(), 'tool_runner.py')
                    
                    # Verify that the script exists
                    if not os.path.exists(tool_runner_path):
                        logger.error(f"Tool script not found: {tool_runner_path}")
                        raise Exception(f"Tool script not found: {tool_runner_path}")
                    
                    # Execute script in separate process
                    python_executable = sys.executable  # Get path to current Python executable
                    cmd = [
                        python_executable,
                        tool_runner_path,
                        tool_name,
                        json.dumps(tool_args)
                    ]
                    
                    # Prepare execution environment
                    env = os.environ.copy()
                    env["PYTHONPATH"] = os.getcwd()  # Ensure it can import app.mcp.client
                    
                    logger.info(f"Executing tool {tool_name} in separate process")
                    logger.info(f"Command: {' '.join(cmd)}")
                    
                    # Execute and capture output with 30 second timeout
                    try:
                        process = subprocess.run(
                            cmd,
                            env=env,
                            capture_output=True,
                            text=True,
                            timeout=30  # 30 second timeout
                        )
                        
                        # Verify process result
                        if process.returncode != 0:
                            logger.error(f"Error in tool process (code {process.returncode}): {process.stderr}")
                            raise Exception(f"Error executing tool: {process.stderr.strip()}")
                        
                        # Parse result
                        try:
                            output = process.stdout.strip()
                            logger.info(f"Process output: {output[:100]}...")
                            tool_result_dict = json.loads(output)
                            
                            # Extract content from result
                            if 'content' in tool_result_dict:
                                # The normalized result contains the "content" key
                                tool_result = tool_result_dict['content']
                            elif 'error' in tool_result_dict:
                                # If there's an error, throw it
                                raise Exception(tool_result_dict['error'])
                            else:
                                # If there's neither content nor error, use the whole dictionary
                                tool_result = tool_result_dict
                                
                        except json.JSONDecodeError as json_err:
                            logger.error(f"Error parsing result: {output}")
                            raise Exception(f"Error parsing JSON result: {str(json_err)}")
                            
                    except subprocess.TimeoutExpired:
                        logger.error(f"Timeout executing tool {tool_name}")
                        raise Exception(f"Timeout executing tool {tool_name} (more than 30 seconds)")
                    
                    # Format the result for readability
                    formatted_result = self._format_tool_result(tool_result)
                    
                    # Send tool result
                    yield {"type": "tool_result", "id": tool_name, "result": formatted_result}
                    
                    # Update the conversation with the tool and its result
                    tool_messages = messages.copy()
                    tool_messages.append({
                        "role": "assistant", 
                        "content": response_content
                    })
                    tool_messages.append({
                        "role": "user",
                        "content": f"Resultado de la herramienta {tool_name} con argumentos {json.dumps(tool_args)}:\n\n{formatted_result}"
                    })
                    
                    # Generate follow-up response with the result
                    follow_up_response = self.client.messages.create(
                        model=self.model,
                        system=final_system_prompt,
                        messages=tool_messages,
                        max_tokens=1000,
                        temperature=0.7
                    )
                    
                    # Extract text from follow-up response
                    follow_up_text = ""
                    for content_block in follow_up_response.content:
                        if content_block.type == "text":
                            follow_up_text += content_block.text
                    
                    # Update the complete response
                    full_response += f"\n\n**Resultado de {tool_name}**:\n```\n{formatted_result}\n```\n\n{follow_up_text}"
                    
                    # Send follow-up text
                    yield {"type": "follow_up", "content": f"\n\n**Resultado de {tool_name}**:\n```\n{formatted_result}\n```\n\n{follow_up_text}"}
                    
                except Exception as e:
                    error_msg = f"Error executing tool {tool_name}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    yield {"type": "tool_error", "error": error_msg}
            
            # Finalize
            yield {"type": "complete", "content": full_response}
            
        except Exception as e:
            logger.error(f"Error in response generation: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}
    
    def _extract_tool_calls(self, text):
        """
        Extract tool calls from text.
        """
        tool_calls = []
        
        # Main pattern to detect tool calls with format:
        # "Uso la herramienta X con argumentos: {...}"
        main_pattern = r'Uso la herramienta (\w+) con argumentos: ({.*?})'
        
        # Alternative patterns to capture other ways of mentioning tools
        alternative_patterns = [
            r'(?:Usaré|Voy a usar|Usando|Utilizaré|Utilizo) la herramienta (\w+) con argumentos: ({.*?})',
            r'(?:Llamaré|Llamo|Invoco|Invocaré) a la herramienta (\w+) con argumentos: ({.*?})',
            r'(?:Ejecutaré|Ejecuto) la herramienta (\w+) con argumentos: ({.*?})'
        ]
        
        # Search for main pattern
        matches = re.finditer(main_pattern, text, re.DOTALL)
        for match in matches:
            try:
                tool_name = match.group(1).strip()
                args_json = match.group(2).strip()
                
                # Validate that it's a known tool
                if tool_name in ["search_medicines", "get_medicine_locations", 
                                "get_medicine_stock", "get_regional_statistics", 
                                "get_medicine_status", "diagnose_database", 
                                "troubleshoot_connection", "create_database_schema"]:
                    try:
                        # Parse JSON directly
                        args = json.loads(args_json)
                        tool_calls.append({"name": tool_name, "args": args})
                        logger.info(f"Found tool: {tool_name} with JSON arguments: {args}")
                    except json.JSONDecodeError:
                        logger.error(f"Error: Could not parse JSON in arguments: {args_json}")
            except Exception as e:
                logger.error(f"Error processing tool match: {e}")
        
        # If not found with the main pattern, try with alternatives
        if not tool_calls:
            for pattern in alternative_patterns:
                matches = re.finditer(pattern, text, re.DOTALL)
                for match in matches:
                    try:
                        tool_name = match.group(1).strip()
                        args_json = match.group(2).strip()
                        
                        # Validate that it's a known tool
                        if tool_name in ["search_medicines", "get_medicine_locations", 
                                        "get_medicine_stock", "get_regional_statistics", 
                                        "get_medicine_status", "diagnose_database", 
                                        "troubleshoot_connection", "create_database_schema"]:
                            try:
                                # Parse JSON directly
                                args = json.loads(args_json)
                                tool_calls.append({"name": tool_name, "args": args})
                                logger.info(f"Found tool (alt): {tool_name} with JSON arguments: {args}")
                            except json.JSONDecodeError:
                                logger.error(f"Error: Could not parse JSON in arguments: {args_json}")
                    except Exception as e:
                        logger.error(f"Error processing alternative match: {e}")
        
        return tool_calls
    
    def _parse_args(self, args_text, tool_name):
        """
        Parse arguments from text to a dictionary.
        Tries to parse JSON directly first if available.
        """
        args = {}
        
        # Check if args_text is a complete JSON
        if args_text.strip().startswith('{') and args_text.strip().endswith('}'):
            try:
                return json.loads(args_text)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse directly as JSON: {args_text}")
                # Continue with fallback analysis
        
        # Check if arguments are in "con argumentos: {...}" format
        json_pattern = r'con argumentos:\s*({.*})'
        json_match = re.search(json_pattern, args_text, re.DOTALL)
        if json_match:
            try:
                json_str = json_match.group(1).strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                logger.warning(f"Could not parse JSON in 'con argumentos': {json_str}")
                # Continue with fallback analysis
        
        # Tool-specific analysis (as fallback)
        if "search_medicines" in tool_name:
            # Look for parameters
            query_match = re.search(r'(?:consulta|query)[:\s]+["\']*([^"\']+)["\']', args_text, re.IGNORECASE)
            location_match = re.search(r'(?:ubicación|location)[:\s]+["\']*([^"\']+)["\']', args_text, re.IGNORECASE)
            
            if query_match:
                args["query"] = query_match.group(1).strip()
            else:
                # If there's no explicit query, use all the text as query
                args["query"] = args_text.strip()
            
            if location_match:
                args["location"] = location_match.group(1).strip()
            
            args["search_type"] = "name"  # Default value
            
        elif "get_medicine_locations" in tool_name:
            # Extract medicine name
            medicine_match = re.search(r'(?:medicina|medicine|medicamento|nombre)[:\s]+["\']*([^"\']+)["\']', args_text, re.IGNORECASE)
            if medicine_match:
                args["medicine_name"] = medicine_match.group(1).strip()
            else:
                args["medicine_name"] = args_text.strip()
                
        elif "get_medicine_stock" in tool_name:
            # Extract medicine ID or name
            medicine_id_match = re.search(r'(?:id)[:\s]+["\']*(\d+)["\']', args_text, re.IGNORECASE)
            if medicine_id_match:
                args["medicine_id"] = int(medicine_id_match.group(1).strip())
            else:
                # Try to extract the first number in the text
                id_match = re.search(r'(\d+)', args_text)
                if id_match:
                    args["medicine_id"] = int(id_match.group(1))
                else:
                    args["medicine_id"] = 1  # Default value
        
        # If no specific arguments were found, try general analysis
        if not args:
            # Try to extract key-value pairs
            pairs = re.finditer(r'(\w+)[:\s]+["\']*([^"\']+)["\']', args_text)
            for pair in pairs:
                key = pair.group(1).strip()
                value = pair.group(2).strip()
                args[key] = value
                
            # If there are still no arguments and the text is not empty
            if not args and args_text.strip():
                if "search" in tool_name:
                    args["query"] = args_text.strip()
                elif "location" in tool_name:
                    args["medicine_name"] = args_text.strip()
                elif "stock" in tool_name and args_text.isdigit():
                    args["medicine_id"] = int(args_text.strip())
        
        return args
    
    def _format_tool_result(self, result):
        """Format tool result for better readability"""
        try:
            if isinstance(result, str):
                return result
            elif isinstance(result, dict):
                return json.dumps(result, indent=2, ensure_ascii=False)
            else:
                return str(result)
        except Exception:
            return str(result)