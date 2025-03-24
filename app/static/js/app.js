/**
 * MediFinder Chat Interface
 * Handles chat interactions, message streaming, and UI updates
 */
document.addEventListener('DOMContentLoaded', function() {
    // DOM elements
    setupMarkedOptions();
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
    
        // Use our enhanced rendering function
        messageContent.innerHTML = renderMarkdown(message);
        
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
     * @param {string} id - Tool ID
     * @param {Object} result - Tool result
     */
    function addToolResult(id, result) {
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-result';
        
        // Format and display the tool results
        toolDiv.innerHTML = `
            <strong>📊 Resultado de herramienta (ID: ${id})</strong>
            <pre>${typeof result === 'string' ? result : JSON.stringify(result, null, 2)}</pre>
        `;
        
        thinkingContent.appendChild(toolDiv);
        thinkingContent.scrollTop = thinkingContent.scrollHeight;
    }

    /**
     * Add a tool error to the thinking area
     * @param {string} id - Tool ID
     * @param {string} error - Error message
     */
    function addToolError(id, error) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'tool-error';
        
        errorDiv.innerHTML = `
            <strong>❌ Error en herramienta (ID: ${id})</strong>
            <div>${error}</div>
        `;
        
        thinkingContent.appendChild(errorDiv);
        thinkingContent.scrollTop = thinkingContent.scrollHeight;
    }

    /**
     * Configure marked options for better handling of responsive content
     */
    function setupMarkedOptions() {
        // Configure Marked options
        marked.setOptions({
            breaks: true,               // Allow line breaks without needing two spaces
            gfm: true,                  // Enable GitHub Flavored Markdown
            headerIds: false,           // Avoid adding IDs to headers
            mangle: false,              // Avoid mangling links
            sanitize: false,            // Don't sanitize here - we use DOMPurify for that
            smartLists: true,           // Use smarter lists
            smartypants: true,          // Use typographic smartypants
            xhtml: false,               // Don't use XHTML
            
            // Customize code block rendering to make them responsive
            renderer: new marked.Renderer()
        });
        
        // Customize table rendering
        const renderer = new marked.Renderer();
        
        // Make tables responsive
        renderer.table = function(header, body) {
            return `<div class="table-responsive"><table class="table table-bordered">
                <thead>${header}</thead>
                <tbody>${body}</tbody>
            </table></div>`;
        };
        
        // Customize code block rendering
        renderer.code = function(code, language) {
            return `<pre class="code-block"><code class="${language ? `language-${language}` : ''}">${code}</code></pre>`;
        };
        
        // Apply the custom renderer
        marked.setOptions({ renderer });
    }

    /**
     * Preprocess markdown text before rendering
     * @param {string} markdown - The markdown text to process
     */
    function preprocessMarkdown(markdown) {
        if (!markdown) return '';
        
        // Add classes to make tables responsive if there are tables in the content
        let processed = markdown;
        
        // Add classes to code blocks
        processed = processed.replace(/```(\w+)?\n([\s\S]*?)```/g, function(match, language, code) {
            return `\`\`\`${language || ''}\n${code}\`\`\``;
        });
        
        // Handle long URLs to avoid overflow
        processed = processed.replace(/(\b(https?|ftp|file):\/\/[-A-Z0-9+&@#\/%?=~_|!:,.;]*[-A-Z0-9+&@#\/%=~_|])/ig, 
            '<span class="break-word">$1</span>');
        
        return processed;
    }

    /**
     * Render markdown to HTML safely
     * @param {string} markdown - The markdown text to render
     * @returns {string} - Sanitized HTML
     */
    function renderMarkdown(markdown) {
        // Preprocess markdown
        const processed = preprocessMarkdown(markdown);
        
        // Convert markdown to HTML
        const html = marked.parse(processed);
        
        // Sanitize resulting HTML to prevent XSS
        return DOMPurify.sanitize(html, {
            ADD_ATTR: ['target'],
            ADD_TAGS: ['iframe'],
            FORBID_TAGS: ['style'],
            FORBID_ATTR: ['style'],
        });
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
            eventSource = null;
        }

        try {
            // First send the message to server via POST
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message }),
            });
            
            if (!response.ok) {
                // If the response is not ok, parse the error message if possible
                let errorMessage = 'Error al enviar mensaje';
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.error || errorMessage;
                } catch (parseError) {
                    errorMessage = `Error (${response.status}): ${response.statusText}`;
                }
                throw new Error(errorMessage);
            }
            
            // Start reading the streaming response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            let fullResponse = '';
            let responseElement = null;
            
            while (true) {
                const { done, value } = await reader.read();
                
                if (done) {
                    console.log('Stream completed');
                    break;
                }
                
                // Append new data to buffer
                buffer += decoder.decode(value, { stream: true });
                
                // Process all complete SSE messages in buffer
                let lines = buffer.split('\n\n');
                buffer = lines.pop() || ''; // Keep last incomplete message in buffer
                
                for (const line of lines) {
                    if (line.trim() === '' || !line.startsWith('data:')) continue;
                    
                    try {
                        // Extract and parse JSON data
                        const jsonString = line.replace(/^data:\s*/, '');
                        const data = JSON.parse(jsonString);
                        
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
                                
                            case 'tool_use':
                                // Tool usage notification
                                addThinkingContent(`\n📦 Usando herramienta: ${data.name}\nArgumentos: ${JSON.stringify(data.arguments, null, 2)}\n`);
                                break;
                                
                            case 'tool_result':
                                // Tool result
                                addToolResult(data.id || 'unknown', data.result);
                                break;
                                
                            case 'follow_up':
                                // Follow-up response after tool usage
                                if (responseElement) {
                                    // Update existing response element
                                    const messageContent = responseElement.querySelector('.message-content');
                                    fullResponse += "\n" + data.content;
                                    messageContent.innerHTML = DOMPurify.sanitize(marked.parse(fullResponse));
                                }
                                break;
                                
                            case 'tool_error':
                                // Tool error
                                addToolError(data.id || 'unknown', data.error);
                                break;
                                
                            case 'error':
                                // Error in processing
                                console.error('Error:', data.message);
                                removeTypingIndicator();
                                addMessage('❌ Lo siento, ha ocurrido un error: ' + data.message);
                                break;
                                
                            case 'end':
                                // End of streaming
                                console.log('Streaming ended');
                                
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
                        console.error('Error parsing event data:', error, line);
                    }
                }
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
            console.error('Error resetting conversation:', error);
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