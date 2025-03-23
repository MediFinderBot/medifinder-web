/**
 * MediFinder Chat Interface
 * Handles chat interactions, message streaming, and UI updates
 */
document.addEventListener('DOMContentLoaded', function() {
    // DOM elements
    const chatMessages = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const resetButton = document.getElementById('reset-button');
    const thinkingArea = document.getElementById('thinking-area');
    const thinkingContent = document.getElementById('thinking-content');

    // Event source for streaming
    let eventSource = null;
    
    /**
     * Add a message to the chat interface
     * @param {string} message - The message text
     * @param {boolean} isUser - Whether the message is from the user
     * @returns {HTMLElement} - The message element
     */
    function addMessage(message, isUser = false) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message');
        messageDiv.classList.add(isUser ? 'user' : 'assistant');

        const messageContent = document.createElement('div');
        messageContent.classList.add('message-content');

        // Use DOMPurify to sanitize HTML and marked to render markdown
        const sanitizedHtml = DOMPurify.sanitize(marked.parse(message));
        messageContent.innerHTML = sanitizedHtml;
        
        messageDiv.appendChild(messageContent);
        chatMessages.appendChild(messageDiv);
        
        // Scroll to the bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return messageDiv;
    }

    /**
     * Show the typing indicator
     * @returns {HTMLElement} - The indicator element
     */
    function showTypingIndicator() {
        const indicatorDiv = document.createElement('div');
        indicatorDiv.classList.add('message', 'assistant', 'typing-message');
        
        const indicatorContent = document.createElement('div');
        indicatorContent.classList.add('message-content');
        
        const typingIndicator = document.createElement('div');
        typingIndicator.classList.add('typing-indicator');
        typingIndicator.innerHTML = '<span></span><span></span><span></span>';
        
        indicatorContent.appendChild(typingIndicator);
        indicatorDiv.appendChild(indicatorContent);
        chatMessages.appendChild(indicatorDiv);
        
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return indicatorDiv;
    }

    /**
     * Remove the typing indicator
     */
    function removeTypingIndicator() {
        const indicators = document.querySelectorAll('.typing-message');
        indicators.forEach(indicator => indicator.remove());
    }

    /**
     * Show the thinking area with initial content
     */
    function showThinkingArea() {
        thinkingContent.innerHTML = 'Analizando tu consulta...\n';
        thinkingArea.style.display = 'block';
    }

    /**
     * Add content to the thinking area
     * @param {string} content - Content to add
     */
    function addThinkingContent(content) {
        thinkingContent.innerHTML += content;
        thinkingContent.scrollTop = thinkingContent.scrollHeight;
    }

    /**
     * Add a tool result to the thinking area
     * @param {string} name - Tool name
     * @param {Object} args - Tool arguments
     * @param {Object} result - Tool result
     */
    function addToolResult(name, args, result) {
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-result';
        
        // Format and display the tool usage
        toolDiv.innerHTML = `
            <strong>📊 Usando herramienta: ${name}</strong>
            <div><small>Argumentos: ${JSON.stringify(args)}</small></div>
            <pre>${JSON.stringify(result, null, 2)}</pre>
        `;
        
        thinkingContent.appendChild(toolDiv);
        thinkingContent.scrollTop = thinkingContent.scrollHeight;
    }

    /**
     * Add a tool error to the thinking area
     * @param {string} name - Tool name
     * @param {string} error - Error message
     */
    function addToolError(name, error) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'tool-error';
        
        errorDiv.innerHTML = `
            <strong>❌ Error en herramienta: ${name}</strong>
            <div>${error}</div>
        `;
        
        thinkingContent.appendChild(errorDiv);
        thinkingContent.scrollTop = thinkingContent.scrollHeight;
    }

    /**
     * Handle the user's input
     */
    async function handleUserInput() {
        const message = userInput.value.trim();
        if (!message) return;

        // Clear input and disable UI
        userInput.value = '';
        userInput.disabled = true;
        sendButton.disabled = true;

        // Show user message
        addMessage(message, true);

        // Show typing indicator and thinking area
        const typingIndicator = showTypingIndicator();
        showThinkingArea();

        // Close existing EventSource if any
        if (eventSource) {
            eventSource.close();
        }

        try {
            // Create a new EventSource for streaming
            eventSource = new EventSource('/api/chat');
            
            let fullResponse = '';
            let responseElement = null;
            
            // Handle incoming events
            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    
                    switch(data.type) {
                        case 'start':
                            // Start of streaming
                            console.log('Streaming started');
                            break;
                            
                        case 'chunk':
                            // Text chunk
                            fullResponse += data.content;
                            
                            // Add to thinking content
                            addThinkingContent(data.content);
                            
                            // If this is the first chunk, create the response element
                            if (!responseElement) {
                                // Remove typing indicator and create response element
                                removeTypingIndicator();
                                responseElement = addMessage(fullResponse);
                            } else {
                                // Update existing response element
                                const messageContent = responseElement.querySelector('.message-content');
                                messageContent.innerHTML = DOMPurify.sanitize(marked.parse(fullResponse));
                            }
                            break;
                            
                        case 'tool_result':
                            // Tool result
                            addToolResult(data.name, data.arguments, data.result);
                            break;
                            
                        case 'tool_error':
                            // Tool error
                            addToolError(data.name, data.error);
                            break;
                            
                        case 'error':
                            // Error in processing
                            console.error('Error:', data.message);
                            removeTypingIndicator();
                            addMessage('❌ Lo siento, ha ocurrido un error: ' + data.message);
                            eventSource.close();
                            break;
                            
                        case 'end':
                            // End of streaming
                            console.log('Streaming ended');
                            eventSource.close();
                            
                            // Hide thinking area after a delay
                            setTimeout(() => {
                                thinkingArea.style.display = 'none';
                            }, 2000);
                            
                            // Re-enable UI
                            userInput.disabled = false;
                            sendButton.disabled = false;
                            userInput.focus();
                            break;
                    }
                } catch (error) {
                    console.error('Error parsing event data:', error);
                }
            };
            
            // Handle EventSource errors
            eventSource.onerror = function(error) {
                console.error('EventSource error:', error);
                eventSource.close();
                eventSource = null;
                
                removeTypingIndicator();
                
                if (!responseElement) {
                    addMessage('❌ Lo siento, ha ocurrido un error en la conexión. Por favor, inténtalo de nuevo.');
                }
                
                thinkingArea.style.display = 'none';
                userInput.disabled = false;
                sendButton.disabled = false;
                userInput.focus();
            };
            
            // Send message to server
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message }),
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Error al enviar mensaje');
            }
            
        } catch (error) {
            console.error('Error:', error);
            
            removeTypingIndicator();
            addMessage(`❌ Lo siento, ha ocurrido un error: ${error.message}`);
            
            thinkingArea.style.display = 'none';
            userInput.disabled = false;
            sendButton.disabled = false;
            userInput.focus();
        }
    }

    /**
     * Reset the conversation
     */
    async function resetConversation() {
        try {
            // Confirm reset
            if (!confirm('¿Estás seguro de que quieres iniciar una nueva conversación?')) {
                return;
            }
            
            // Close existing EventSource if any
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            
            // Reset UI state
            userInput.disabled = false;
            sendButton.disabled = false;
            thinkingArea.style.display = 'none';
            
            // Call reset API
            const response = await fetch('/api/reset', {
                method: 'POST',
            });
            
            if (!response.ok) {
                throw new Error('Error al resetear la conversación');
            }
            
            // Clear chat messages
            chatMessages.innerHTML = '';
            
            // Add welcome message
            addMessage(`¡Hola! Soy el asistente de MediFinder. Puedo ayudarte a encontrar información sobre medicamentos disponibles en centros de salud del noroeste peruano.

Puedes preguntarme sobre:
* Disponibilidad de medicamentos específicos
* Ubicaciones donde encontrar un medicamento
* Información sobre stock de medicamentos
* Estadísticas regionales de medicamentos

¿En qué puedo ayudarte hoy?`);
            
            // Focus input
            userInput.focus();
            
        } catch (error) {
            console.error('Error al resetear la conversación:', error);
            alert('Error al resetear la conversación. Por favor, recarga la página.');
        }
    }

    // Event listeners
    sendButton.addEventListener('click', handleUserInput);
    
    userInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleUserInput();
        }
    });
    
    resetButton.addEventListener('click', resetConversation);

    // Focus input on load
    userInput.focus();
});