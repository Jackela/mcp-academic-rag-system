document.addEventListener('DOMContentLoaded', function() {
    const eventSource = new EventSource('/mcp_sse');
    const statusMessageDiv = document.getElementById('status-message');
    const toolsListDiv = document.getElementById('tools-list');
    const resourcesListDiv = document.getElementById('resources-list');
    const promptsListDiv = document.getElementById('prompts-list');

    console.log("Attempting to connect to MCP Server via SSE...");

    eventSource.onopen = function() {
        statusMessageDiv.textContent = 'Connected to MCP Server. Waiting for capabilities...';
        statusMessageDiv.className = 'container status-connected';
        console.log("SSE connection opened.");
    };

    eventSource.onerror = function(error) {
        statusMessageDiv.textContent = 'Error connecting to MCP Server. Make sure it is running and accessible. Retrying...';
        statusMessageDiv.className = 'container status-error';
        console.error('EventSource failed:', error);
    };

    eventSource.addEventListener('capabilities', function(event) {
        console.log('Capabilities event received:', event.data);
        try {
            const capabilities = JSON.parse(event.data);
            statusMessageDiv.textContent = `Capabilities received. Server: ${capabilities.server_name || 'N/A'} v${capabilities.server_version || 'N/A'}`;
            statusMessageDiv.className = 'container status-connected';

            renderTools(capabilities.tools);
            renderResources(capabilities.resources);
            renderPrompts(capabilities.prompts);
        } catch (e) {
            console.error('Error parsing capabilities JSON:', e);
            statusMessageDiv.textContent = 'Error processing capabilities from server.';
            statusMessageDiv.className = 'container status-error';
        }
    });
    
    eventSource.addEventListener('keepalive', function(event) {
        console.log('Keepalive event received');
    });

    eventSource.addEventListener('tool_result', function(event) {
        console.log('Tool Result event received:', event.data);
        try {
            const parsedData = JSON.parse(event.data);
            let displayDiv;
            if (parsedData.tool_name === "echo") {
                displayDiv = document.getElementById('echo-result-display');
                if (displayDiv) {
                    displayDiv.textContent = `Success:\n${JSON.stringify(parsedData.result, null, 2)}`;
                }
            } else if (parsedData.tool_name === "document_search") {
                displayDiv = document.getElementById('search-result-display');
                if (displayDiv) {
                    if (parsedData.result && parsedData.result.search_results && parsedData.result.search_results.length > 0) {
                        let resultsHtml = `<strong>Query:</strong> ${parsedData.result.query_received}<br><br>`;
                        parsedData.result.search_results.forEach(doc => {
                            resultsHtml += `
                                <div class="item">
                                    <div class="item-name">ID: ${doc.id}</div>
                                    <div><strong>Title:</strong> ${doc.title || 'N/A'}</div>
                                    <div><strong>Abstract:</strong> ${doc.abstract || 'N/A'}</div>
                                    <div><strong>Keywords:</strong> ${(doc.keywords || []).join(', ')}</div>
                                </div>
                            `;
                        });
                        displayDiv.innerHTML = resultsHtml;
                    } else if (parsedData.result && parsedData.result.query_received) {
                         displayDiv.textContent = `No documents found for your query: "${parsedData.result.query_received}"`;
                    } else if (parsedData.result && parsedData.result.error) { 
                        displayDiv.textContent = `Error: ${parsedData.result.error}`;
                    } else {
                        displayDiv.textContent = 'No results or malformed result data.';
                    }
                }
            } else if (parsedData.tool_name === "add_document_to_store") {
                displayDiv = document.getElementById('add-doc-result-display');
                if (displayDiv) {
                    if (parsedData.result && parsedData.result.message) {
                        displayDiv.textContent = `Success: ${parsedData.result.message} (ID: ${parsedData.result.document_id}, Title: '${parsedData.result.derived_title}')`;
                        // Clear input fields on success
                        document.getElementById('add-doc-text-input').value = ''; // Updated ID
                        document.getElementById('add-doc-keywords-input').value = '';
                    } else if (parsedData.result && parsedData.result.error) {
                        displayDiv.textContent = `Error: ${parsedData.result.error}`;
                    } else {
                        displayDiv.textContent = 'Document addition status unknown or malformed result data.';
                    }
                }
            } else if (parsedData.tool_name === "add_document_from_file") {
                displayDiv = document.getElementById('fileUploadResult');
                if (displayDiv) {
                    if (parsedData.result && parsedData.result.message) {
                        displayDiv.textContent = `Success: ${parsedData.result.message} (ID: ${parsedData.result.document_id}, Title: '${parsedData.result.derived_title}', Original File: '${parsedData.result.original_filename}')`;
                        // Clear input fields on success
                        const fileInput = document.getElementById('fileInput');
                        if (fileInput) fileInput.value = '';
                        const fileKeywordsInput = document.getElementById('fileKeywords');
                        if (fileKeywordsInput) fileKeywordsInput.value = '';
                    } else if (parsedData.result && parsedData.result.error) {
                        displayDiv.textContent = `Error: ${parsedData.result.error}`;
                    } else {
                        displayDiv.textContent = 'File upload status unknown or malformed result data.';
                    }
                }
            }
        } catch (e) {
            console.error('Error parsing tool_result JSON:', e);
        }
    });

    eventSource.addEventListener('tool_error', function(event) {
        console.log('Tool Error event received:', event.data);
        try {
            const parsedData = JSON.parse(event.data);
            let displayDivId = '';
            if (parsedData.tool_name === "echo") { 
                displayDivId = 'echo-result-display';
            } else if (parsedData.tool_name === "document_search") {
                displayDivId = 'search-result-display';
            } else if (parsedData.tool_name === "add_document_to_store") {
                displayDivId = 'add-doc-result-display';
            } else if (parsedData.tool_name === "add_document_from_file") {
                displayDivId = 'fileUploadResult';
            }

            if (displayDivId) {
                const displayDiv = document.getElementById(displayDivId);
                if (displayDiv) {
                    displayDiv.textContent = `Error for tool ${parsedData.tool_name}:\n${JSON.stringify(parsedData.error, null, 2)}`;
                }
            }
        } catch (e) {
            console.error('Error parsing tool_error JSON:', e);
        }
    });

    eventSource.addEventListener('prompt_result', function(event) {
        console.log('Prompt Result event received:', event.data);
        try {
            const parsedData = JSON.parse(event.data);
            if (parsedData.prompt_name === "summarize_document_abstract") {
                const displayDiv = document.getElementById('summarize-result-display');
                if (displayDiv) {
                    displayDiv.textContent = `Success:\n${JSON.stringify(parsedData.result, null, 2)}`;
                }
            }
        } catch (e) {
            console.error('Error parsing prompt_result JSON:', e);
        }
    });

    eventSource.addEventListener('prompt_error', function(event) {
        console.log('Prompt Error event received:', event.data);
        try {
            const parsedData = JSON.parse(event.data);
             if (parsedData.prompt_name === "summarize_document_abstract") { 
                const displayDiv = document.getElementById('summarize-result-display');
                if (displayDiv) {
                    displayDiv.textContent = `Error:\n${JSON.stringify(parsedData.error, null, 2)}`;
                }
            }
        } catch (e) {
            console.error('Error parsing prompt_error JSON:', e);
        }
    });


    function renderTools(toolsData) {
        toolsListDiv.innerHTML = ''; 
        if (!toolsData || !Array.isArray(toolsData) || toolsData.length === 0) {
            toolsListDiv.innerHTML = '<p>No tools available.</p>';
            return;
        }
        toolsData.forEach(tool => {
            const toolDiv = document.createElement('div');
            toolDiv.className = 'item';
            let toolHtml = `
                <div class="item-name">${tool.name}</div>
                <div class="item-meta">${tool.description || 'No description provided.'}</div>
                <pre>Schema: ${JSON.stringify(tool.schema || {}, null, 2)}</pre>
            `;
            
            if (tool.name === "echo") {
                toolHtml += `
                <div class="tool-interaction">
                    <input type="text" id="echo-message-input" placeholder="Enter message for echo">
                    <button onclick="runEchoTool()">Run Echo</button>
                    <div id="echo-result-display" class="result-display"></div>
                </div>
                `;
            } else if (tool.name === "document_search") {
                toolHtml += `
                <div class="tool-interaction">
                    <div>
                        <label for="search-query-input">Query:</label>
                        <input type="text" id="search-query-input" placeholder="Enter search query">
                    </div>
                    <div style="margin-top: 5px;">
                        <label for="search-max-results-input">Max Results:</label>
                        <input type="number" id="search-max-results-input" value="3" min="1" style="width: 60px;">
                    </div>
                    <button onclick="runDocumentSearch()" style="margin-top: 10px;">Run Search</button>
                    <div id="search-result-display" class="result-display"></div>
                </div>
                `;
            } else if (tool.name === "add_document_to_store") {
                toolHtml += `
                <div class="tool-interaction">
                    <div>
                        <label for="add-doc-text-input">Document Text:</label>
                        <textarea id="add-doc-text-input" placeholder="Enter full document text here. First line will be used as title." rows="5" style="width: 98%;"></textarea>
                    </div>
                    <div style="margin-top: 5px;">
                        <label for="add-doc-keywords-input">Keywords (comma-separated, optional):</label>
                        <input type="text" id="add-doc-keywords-input" placeholder="e.g., ai, healthcare, data" style="width: 98%;">
                    </div>
                    <button onclick="runAddDocumentTool()" style="margin-top: 10px;">Add Document from Text</button>
                    <div id="add-doc-result-display" class="result-display"></div>
                </div>
                `;
            }
            toolDiv.innerHTML = toolHtml;
            toolsListDiv.appendChild(toolDiv);
        });
    }

    function renderResources(resourcesData) {
        resourcesListDiv.innerHTML = ''; 
        if (!resourcesData || !Array.isArray(resourcesData) || resourcesData.length === 0) {
            resourcesListDiv.innerHTML = '<p>No resources available.</p>';
            return;
        }
        resourcesData.forEach(resource => {
            const resourceDiv = document.createElement('div');
            resourceDiv.className = 'item';
            resourceDiv.innerHTML = `
                <div class.item-name">${resource.uri}</div>
                <div class="item-meta"><b>Name:</b> ${resource.name || 'N/A'}</div>
                <div class="item-meta"><b>Description:</b> ${resource.description || 'No description provided.'}</div>
                <div class="item-meta"><b>MIME Type:</b> ${resource.mime_type || 'N/A'}</div>
            `;
            resourcesListDiv.appendChild(resourceDiv);
        });
    }

    function renderPrompts(promptsData) {
        promptsListDiv.innerHTML = ''; 
        if (!promptsData || !Array.isArray(promptsData) || promptsData.length === 0) {
            promptsListDiv.innerHTML = '<p>No prompts available.</p>';
            return;
        }
        promptsData.forEach(prompt => {
            const promptDiv = document.createElement('div');
            promptDiv.className = 'item';
            const argsHtml = (prompt.arguments && prompt.arguments.length > 0)
                ? prompt.arguments.map(arg => `
                    <div><b>${arg.name || 'N/A'}</b> (${arg.type || 'N/A'}, ${arg.required ? 'required' : 'optional'}): ${arg.description || 'No description.'}</div>
                `).join('')
                : 'No arguments defined.';
            
            let promptHtml = `
                <div class="item-name">${prompt.name}</div>
                <div class="item-meta">${prompt.description || 'No description provided.'}</div>
                <div>Arguments:</div>
                <div class="item-args">
                    ${argsHtml}
                </div>
            `;

            if (prompt.name === "summarize_document_abstract") {
                promptHtml += `
                <div class="prompt-interaction tool-interaction">
                    <input type="text" id="summarize-uri-input" placeholder="Enter document URI (e.g., mcp://resources/literature/doc123)">
                    <button onclick="runSummarizePrompt()">Run Summarize Abstract</button>
                    <div id="summarize-result-display" class="result-display"></div>
                </div>
                `;
            }
            promptDiv.innerHTML = promptHtml;
            promptsListDiv.appendChild(promptDiv);
        });
    }
});

// Generic function to send MCP commands
function sendMcpCommand(commandPayload, resultDisplayId) {
    const resultDisplay = document.getElementById(resultDisplayId);
    if (!resultDisplay) {
        console.error(`Result display area with ID '${resultDisplayId}' not found.`);
        return;
    }
    resultDisplay.textContent = 'Sending command...';

    fetch('/mcp_command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(commandPayload)
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errData => {
                throw new Error(`HTTP error! status: ${response.status}, message: ${errData.error || 'Unknown server error'}`);
            }).catch(() => { 
                throw new Error(`HTTP error! status: ${response.status}, statusText: ${response.statusText}`);
            });
        }
        return response.json(); 
    })
    .then(data => {
        console.log('Command accepted by server:', data);
        resultDisplay.textContent = `Command sent (${data.message || '202 Accepted'}), waiting for SSE result...`;
    })
    .catch(error => {
        console.error('Error sending command:', error);
        resultDisplay.textContent = `Error sending command: ${error.message}`;
    });
}

function runEchoTool() {
    const messageInput = document.getElementById('echo-message-input');
    const message = messageInput ? messageInput.value : '';
    const command = { 
        command: "execute_tool", 
        tool_name: "echo", 
        tool_params: { message: message } 
    };
    sendMcpCommand(command, 'echo-result-display');
}

function runSummarizePrompt() {
    const uriInput = document.getElementById('summarize-uri-input');
    const document_uri = uriInput ? uriInput.value : '';
    const resultDisplay = document.getElementById('summarize-result-display'); 

    if (!document_uri) { 
        if(resultDisplay) resultDisplay.textContent = 'Error: Document URI is required.'; 
        return; 
    }

    const command = {
        command: "execute_prompt",
        name: "summarize_document_abstract",
        arguments: { document_uri: document_uri }
    };
    sendMcpCommand(command, 'summarize-result-display');
}

function runDocumentSearch() {
    const queryInput = document.getElementById('search-query-input');
    const maxResultsInput = document.getElementById('search-max-results-input');
    
    const query = queryInput ? queryInput.value : '';
    const maxResults = maxResultsInput ? parseInt(maxResultsInput.value, 10) : 3;

    if (!query.trim()) {
        const resultDisplay = document.getElementById('search-result-display');
        if(resultDisplay) resultDisplay.textContent = 'Error: Search query cannot be empty.';
        return;
    }

    const command = {
        command: "execute_tool",
        tool_name: "document_search",
        tool_params: {
            query: query,
            max_results: isNaN(maxResults) || maxResults <= 0 ? 3 : maxResults 
        }
    };
    sendMcpCommand(command, 'search-result-display');
}

function runAddDocumentTool() {
    const textInput = document.getElementById('add-doc-text-input'); // Updated ID
    const keywordsInput = document.getElementById('add-doc-keywords-input');
    const resultDisplay = document.getElementById('add-doc-result-display');

    const document_text = textInput ? textInput.value : '';
    const keywords = keywordsInput ? keywordsInput.value : '';

    if (!document_text.trim()) { 
        if(resultDisplay) resultDisplay.textContent = 'Error: Document Text is required.';
        return;
    }

    const command = {
        command: "execute_tool",
        tool_name: "add_document_to_store",
        tool_params: {
            document_text: document_text, 
            keywords: keywords 
        }
    };
    sendMcpCommand(command, 'add-doc-result-display');
}

// Event listener and handler for Add Document from File
const addDocFromFileButton = document.getElementById('addDocumentFromFileButton');
if (addDocFromFileButton) {
    addDocFromFileButton.addEventListener('click', handleAddDocumentFromFile);
}

function handleAddDocumentFromFile() {
    const fileInput = document.getElementById('fileInput');
    const fileKeywordsInput = document.getElementById('fileKeywords');
    const fileUploadResultDiv = document.getElementById('fileUploadResult');

    if (!fileInput || !fileKeywordsInput || !fileUploadResultDiv) {
        console.error('One or more elements for file upload not found.');
        if (fileUploadResultDiv) fileUploadResultDiv.textContent = 'Error: UI elements missing.';
        return;
    }

    fileUploadResultDiv.textContent = ''; // Clear previous messages

    const file = fileInput.files[0];
    const keywords = fileKeywordsInput.value.trim();

    if (!file) {
        fileUploadResultDiv.textContent = 'Please select a .txt or .pdf file.'; // Updated message
        return;
    }

    // Updated file type check for .txt and .pdf
    const allowedTypes = ['text/plain', 'application/pdf'];
    const allowedExtensions = ['.txt', '.pdf'];
    let isValidType = allowedTypes.includes(file.type);
    let isValidExt = allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext));

    if (!isValidType && !isValidExt) { 
        fileUploadResultDiv.textContent = 'Error: Invalid file type. Please select a .txt or .pdf file.'; // Updated message
        return;
    }

    fileUploadResultDiv.textContent = 'Processing file...';

    const reader = new FileReader();

    reader.onload = function(event) {
        const fileContent = event.target.result;
        let base64Encoded;
        try {
            // For UTF-8 text to Base64:
            // 1. Encode URI components (handles multi-byte UTF-8 chars)
            // 2. Unescape to get raw byte string
            // 3. btoa to get Base64
            base64Encoded = btoa(unescape(encodeURIComponent(fileContent)));
        } catch (e) {
            console.error('Error during Base64 encoding:', e);
            fileUploadResultDiv.textContent = 'Error: Could not encode file content. Ensure it is valid UTF-8 text.';
            return;
        }

        const payload = {
            command: "execute_tool",
            tool_name: "add_document_from_file",
            tool_params: {
                filename: file.name,
                file_content_base64: base64Encoded,
                keywords: keywords
            }
        };
        
        // Use the generic sendMcpCommand function
        sendMcpCommand(payload, 'fileUploadResult');
        // The sendMcpCommand will set "Command sent..., waiting for SSE result..."
        // Actual success/error will be handled by SSE listeners updating fileUploadResultDiv
    };

    reader.onerror = function(event) {
        console.error('File reading error:', event);
        fileUploadResultDiv.textContent = 'Error reading file.';
    };

    reader.readAsText(file); // Reads as UTF-8 by default
}
