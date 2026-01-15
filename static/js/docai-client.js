// static/js/docai-client.js
/**
 * DocAI Client - OPMP Implementation
 *
 * Features:
 * - SSE (Server-Sent Events) streaming client
 * - OPMP (Optimistic Progressive Markdown Parsing)
 * - Five-phase progress indicators
 * - File upload with real-time status
 * - Session management
 */

class DocAIClient {
    constructor() {
        this.sessionId = this.generateSessionId();
        this.userId = this.getUserId(); // Get or generate UUID for multi-user support
        this.uploadedFiles = new Map(); // fileId → {filename, status}
        this.currentEventSource = null;
        this.useStreaming = true; // if false: Non-streaming mode by default (recommended for stability)

        // Streaming optimization: RAF throttling for token batching
        this.tokenBuffer = '';
        this.rafScheduled = false;

        // DOM elements (will be initialized in init())
        this.chatDisplayArea = null;
        this.userInput = null;
        this.sendBtn = null;
        this.sourceList = null;
    }

    /**
     * Initialize DocAI Client
     */
    init() {
        // Get DOM elements
        this.chatDisplayArea = document.querySelector('.chat-display-area');
        this.userInput = document.querySelector('.user-input-region textarea');
        this.sendBtn = document.querySelector('.user-input-region button');
        this.sourceList = document.getElementById('sourceList');

        // Bind event listeners
        if (this.sendBtn) {
            this.sendBtn.addEventListener('click', () => this.sendMessage());
        }

        if (this.userInput) {
            this.userInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        // Clear static demo content
        if (this.chatDisplayArea) {
            this.chatDisplayArea.innerHTML = `
                <div class="chat-bubble ai">
                    歡迎使用 DocAI 系統，這裡可以上傳您的文件並進行智慧問答
                </div>
            `;
        }

        // Auto-load user's existing files on startup
        this.loadUserFiles();

        console.log('DocAI Client initialized', { sessionId: this.sessionId });
    }

    /**
     * Load user's existing files from backend and display in sidebar
     * Called on page load to populate the file list for the default user
     */
    async loadUserFiles() {
        try {
            console.log('[DocAI] Loading user files...');

            const response = await fetch('/api/v1/files', {
                method: 'GET',
                headers: {
                    'X-User-ID': this.userId
                }
            });

            if (!response.ok) {
                console.warn('[DocAI] Failed to load user files:', response.status);
                return;
            }

            const result = await response.json();
            const files = result.files || [];

            console.log('[DocAI] Loaded files:', files.length);

            // Clear existing file list (remove demo items if any)
            if (this.sourceList) {
                this.sourceList.innerHTML = '';
            }

            // Add each file to the sidebar
            for (const file of files) {
                this.renderFileInSidebar(file);
            }

            console.log('[DocAI] User files loaded successfully');

        } catch (error) {
            console.error('[DocAI] Error loading user files:', error);
        }
    }

    /**
     * Render a file item in the sidebar with checkbox
     * @param {Object} file - File object from API {file_id, filename, upload_time, chunk_count, embedding_status}
     */
    renderFileInSidebar(file) {
        const item = document.createElement('li');
        item.className = 'source-item';

        // Create checkbox (unchecked by default for existing files on page load)
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = false;
        checkbox.dataset.fileId = file.file_id;

        // Create file icon
        const icon = document.createElement('i');
        icon.className = 'fa-solid fa-file-pdf file-icon';
        icon.style.color = '#e63946';

        // Create filename span
        const filename = document.createElement('span');
        filename.className = 'file-name';
        filename.textContent = file.filename;
        filename.title = `Chunks: ${file.chunk_count || 'N/A'} | Uploaded: ${file.upload_time || 'N/A'}`;

        // Assemble item
        item.appendChild(checkbox);
        item.appendChild(icon);
        item.appendChild(filename);

        // Add to list
        this.sourceList.appendChild(item);

        // Track in uploadedFiles map
        this.uploadedFiles.set(file.file_id, {
            filename: file.filename,
            status: file.embedding_status || 'completed',
            chunkCount: file.chunk_count
        });

        console.log('[DocAI] Added file to sidebar:', file.file_id, file.filename);
    }

    /**
     * Generate unique session ID
     */
    generateSessionId() {
        return `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    }

    /**
     * Get or generate user UUID (UUID v4) for multi-user support
     * Persists in localStorage for consistent user identification
     * @returns {string} - UUID v4 string
     */
    getUserId() {
        // Check if UUID already exists in localStorage
        let userId = localStorage.getItem('docai_user_id');

        if (!userId) {
            // Generate UUID v4 using crypto.randomUUID() (modern browsers)
            if (typeof crypto !== 'undefined' && crypto.randomUUID) {
                userId = crypto.randomUUID();
            } else {
                // Fallback for older browsers: manual UUID v4 generation
                userId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                    const r = Math.random() * 16 | 0;
                    const v = c === 'x' ? r : (r & 0x3 | 0x8);
                    return v.toString(16);
                });
            }

            // Store in localStorage for persistence
            localStorage.setItem('docai_user_id', userId);
            console.log('[DocAI] Generated new user_id:', userId);
        } else {
            console.log('[DocAI] Using existing user_id:', userId);
        }

        return userId;
    }

    /**
     * Upload file to backend
     * @param {File} file - File object from input
     * @returns {Promise<Object>} - Upload response with file_id
     */
    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/v1/upload', {
                method: 'POST',
                headers: {
                    'X-User-ID': this.userId  // Multi-user support: Send user UUID
                },
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                // Backend returns detail as object: {error, message, details}
                const errorMsg = error.detail?.message || error.detail || 'Upload failed';
                throw new Error(errorMsg);
            }

            const result = await response.json();

            // Store uploaded file info
            this.uploadedFiles.set(result.file_id, {
                filename: result.filename,
                status: 'completed',
                chunkCount: result.chunk_count
            });

            console.log('File uploaded successfully', result);
            return result;

        } catch (error) {
            console.error('Upload error:', error);
            throw error;
        }
    }

    /**
     * Add file to UI with upload status
     * @param {string} filename - File name
     * @returns {HTMLElement} - Created list item
     */
    addFileToUI(filename) {
        const newItem = document.createElement('li');
        newItem.className = 'source-item';
        newItem.innerHTML = `
            <i class="fa-solid fa-file-pdf file-icon" style="color: #e63946;"></i>
            <span class="file-name">${filename}</span>
            <div class="spinner"></div>
        `;

        this.sourceList.prepend(newItem);
        return newItem;
    }

    /**
     * Update file status in UI
     * @param {HTMLElement} item - List item element
     * @param {string} status - Status ('completed', 'error')
     * @param {string} fileId - File ID (for checkbox data attribute)
     */
    updateFileStatus(item, status, fileId = null) {
        const spinner = item.querySelector('.spinner');

        console.log('[DocAI] updateFileStatus called:', { status, fileId, hasSpinner: !!spinner });

        if (status === 'completed' && spinner) {
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = true;
            if (fileId) {
                checkbox.dataset.fileId = fileId;
                console.log('[DocAI] Checkbox created with file_id:', fileId);
            } else {
                console.error('[DocAI] ERROR: No file_id provided to updateFileStatus!');
            }
            // FIX: Insert checkbox at the BEGINNING of the item, then remove spinner
            // This ensures correct order: checkbox → icon → filename
            spinner.remove();
            item.insertBefore(checkbox, item.firstChild);
        } else if (status === 'error' && spinner) {
            spinner.innerHTML = '<i class="fa-solid fa-exclamation-circle" style="color: #e63946;"></i>';
        }
    }

    /**
     * Get selected file IDs from checkboxes
     * @returns {Array<string>} - Array of selected file IDs
     */
    getSelectedFileIds() {
        const checkboxes = this.sourceList.querySelectorAll('input[type="checkbox"]:checked');
        const fileIds = Array.from(checkboxes)
            .map(cb => cb.dataset.fileId)
            .filter(id => id); // Filter out undefined

        // Debug logging
        console.log('[DocAI] Checked checkboxes:', checkboxes.length);
        console.log('[DocAI] Selected file IDs:', fileIds);

        if (checkboxes.length > 0 && fileIds.length === 0) {
            console.warn('[DocAI] Warning: Checkboxes are checked but no file IDs found!');
            console.warn('[DocAI] First checkbox data:', checkboxes[0]?.dataset);
        }

        return fileIds;
    }

    /**
     * Send chat message with SSE streaming
     */
    async sendMessage() {
        const query = this.userInput.value.trim();

        if (!query) {
            return;
        }

        // Get selected files
        const selectedFileIds = this.getSelectedFileIds();

        if (selectedFileIds.length === 0) {
            this.showError('請先選擇資料來源');
            return;
        }

        // Debug Mode: Show popup with selected files info
        const debugModeCheckbox = document.getElementById('debugModeCheckbox');
        if (debugModeCheckbox && debugModeCheckbox.checked) {
            this.showDebugPopup(selectedFileIds);
        }

        // Clear input
        this.userInput.value = '';

        // Add user message bubble
        this.addMessageBubble('user', query);

        // Create AI message bubble (will be filled progressively)
        const aiBubble = this.addMessageBubble('ai', '');
        const progressIndicator = this.createProgressIndicator();
        aiBubble.appendChild(progressIndicator);

        // Prepare SSE request
        const requestPayload = {
            query: query,
            session_id: this.sessionId,
            file_ids: selectedFileIds,
            language: 'zh',
            top_k: 5,
            enable_expansion: true
        };

        try {
            if (this.useStreaming) {
                await this.streamChat(requestPayload, aiBubble, progressIndicator);
            } else {
                await this.simpleChat(requestPayload, aiBubble, progressIndicator);
            }
        } catch (error) {
            console.error('Chat error:', error);
            this.showError('發生錯誤：' + error.message);
            aiBubble.innerHTML = '<span style="color: #e63946;">處理失敗，請稍後再試</span>';
        }
    }

    /**
     * Stream chat response with SSE
     * @param {Object} payload - Request payload
     * @param {HTMLElement} aiBubble - AI message bubble element
     * @param {HTMLElement} progressIndicator - Progress indicator element
     */
    async streamChat(payload, aiBubble, progressIndicator) {
        console.log('[DocAI] Starting SSE stream...');

        // Update progress to show potential LLM loading wait time
        progressIndicator.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px; padding: 8px;">
                <div class="spinner" style="
                    border: 3px solid #f3f3f3;
                    border-top: 3px solid #007aff;
                    border-radius: 50%;
                    width: 20px;
                    height: 20px;
                    animation: spin 1s linear infinite;
                "></div>
                <span style="color: #666;">Waiting for LLM response (may take 45-90s on first request)...</span>
            </div>
        `;

        // Extended timeout: 5 minutes for LLM cold start (was default ~60s)
        const controller = new AbortController();
        const timeoutId = setTimeout(() => {
            console.warn('[DocAI] Stream timeout after 5 minutes');
            controller.abort();
        }, 300000); // 5 minutes = 300000ms

        try {
            const response = await fetch('/api/v1/chat/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-User-ID': this.userId  // Add user ID for consistency
                },
                body: JSON.stringify(payload),
                signal: controller.signal  // Abort signal for timeout control
            });

            console.log('[DocAI] Response received:', response.status, response.statusText);

            if (!response.ok) {
                clearTimeout(timeoutId);  // Clear timeout on error
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let markdownBuffer = '';

            // SSE parsing state
            let currentEvent = null;
            let currentData = null;
            let eventCount = 0;

            try {
                while (true) {
                    const { done, value } = await reader.read();

                    if (done) {
                        console.log('[DocAI] Stream completed, total events:', eventCount);
                        clearTimeout(timeoutId);  // Clear timeout on completion
                        break;
                    }

                    // Decode chunk
                    const chunk = decoder.decode(value, { stream: true });
                    buffer += chunk;

                    console.log('[DocAI] Received chunk:', chunk.substring(0, 100) + (chunk.length > 100 ? '...' : ''));

                    // Process SSE events line by line
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // Keep incomplete line in buffer

                    for (const line of lines) {
                        // Parse SSE event line
                        if (line.startsWith('event: ')) {
                            currentEvent = line.substring(7).trim();
                            console.log('[DocAI] Event type:', currentEvent);
                        }
                        // Parse SSE data line
                        else if (line.startsWith('data: ')) {
                            const dataStr = line.substring(6).trim();

                            if (!dataStr || dataStr === '[DONE]') continue;

                            try {
                                currentData = JSON.parse(dataStr);
                                console.log('[DocAI] Event data:', currentEvent, currentData);
                            } catch (parseError) {
                                console.warn('[DocAI] Failed to parse SSE data:', parseError, dataStr);
                                currentData = null;
                            }
                        }
                        // Empty line indicates end of SSE event
                        // FIX: Use trim() to handle \r\n line endings from SSE
                        else if (line.trim() === '' && currentEvent && currentData) {
                            eventCount++;

                            // Construct complete SSE event object
                            const sseEvent = {
                                event: currentEvent,
                                data: currentData
                            };

                            // Handle the complete event with error handling
                            try {
                                this.handleSSEEvent(sseEvent, aiBubble, progressIndicator);
                            } catch (handleError) {
                                console.error('[DocAI] Error handling SSE event:', handleError, sseEvent);
                            }

                            // Reset state for next event
                            currentEvent = null;
                            currentData = null;
                        }
                    }
                }
            } catch (streamError) {
                console.error('[DocAI] Stream reading error:', streamError);
                clearTimeout(timeoutId);  // Clear timeout on error
                throw streamError;
            }
        } catch (fetchError) {
            clearTimeout(timeoutId);  // Clear timeout on fetch error
            if (fetchError.name === 'AbortError') {
                throw new Error('Request timeout after 5 minutes - LLM may be loading model');
            }
            throw fetchError;
        }
    }

    /**
     * Simple non-streaming chat (fallback mode)
     * @param {Object} payload - Request payload
     * @param {HTMLElement} aiBubble - AI message bubble element
     * @param {HTMLElement} progressIndicator - Progress indicator element
     */
    async simpleChat(payload, aiBubble, progressIndicator) {
        console.log('[DocAI] Starting non-streaming chat...');

        // Update progress indicator to show processing state
        progressIndicator.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px; padding: 8px;">
                <div class="spinner" style="
                    border: 3px solid #f3f3f3;
                    border-top: 3px solid #007aff;
                    border-radius: 50%;
                    width: 20px;
                    height: 20px;
                    animation: spin 1s linear infinite;
                "></div>
                <span style="color: #666;">Processing your request...</span>
            </div>
        `;

        try {
            // Call non-streaming endpoint
            const response = await fetch('/api/v1/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-User-ID': this.userId
                },
                body: JSON.stringify(payload)
            });

            console.log('[DocAI] Response received:', response.status, response.statusText);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            console.log('[DocAI] Complete response received:', result);

            // Remove progress indicator
            if (progressIndicator && progressIndicator.parentNode) {
                progressIndicator.remove();
            }

            // Render the complete answer using marked
            const answer = result.answer || '無回應內容';

            // Check if marked library is available
            if (typeof marked !== 'undefined' && marked.parse) {
                const htmlContent = marked.parse(answer);
                aiBubble.innerHTML = `<div class="markdown-content">${htmlContent}</div>`;
            } else {
                // Fallback to plain text
                console.warn('[DocAI] marked library not loaded, using plain text');
                aiBubble.innerHTML = `<div class="markdown-content">${answer}</div>`;
            }

            // Auto-scroll to bottom
            this.chatDisplayArea.scrollTop = this.chatDisplayArea.scrollHeight;

            console.log('[DocAI] Chat completed successfully');

        } catch (error) {
            console.error('[DocAI] Error in simpleChat:', error);
            throw error;  // Re-throw to be caught in sendMessage
        }
    }

    /**
     * Handle SSE event
     * @param {Object} event - SSE event object with {event: string, data: object}
     * @param {HTMLElement} aiBubble - AI message bubble
     * @param {HTMLElement} progressIndicator - Progress indicator
     */
    handleSSEEvent(event, aiBubble, progressIndicator) {
        const eventType = event.event;
        const eventData = event.data; // Already parsed in streamChat

        console.log('[DocAI SSE] Handling event:', eventType, eventData);

        try {
            switch (eventType) {
                case 'progress':
                    this.updateProgressIndicator(progressIndicator, eventData);
                    break;

                case 'markdown_token':
                    // OPMP Core: Progressive Markdown rendering with RAF throttling
                    const token = eventData.token || '';

                    if (!token) {
                        console.warn('[DocAI] Empty token received');
                        break;
                    }

                    // FIX: Remove "Waiting..." indicator on first token
                    if (this.tokenBuffer === '' && progressIndicator && progressIndicator.parentNode) {
                        progressIndicator.remove();
                        console.log('[DocAI] Removed waiting indicator on first token');
                    }

                    // Accumulate token in buffer
                    this.tokenBuffer += token;

                    // Schedule RAF update if not already scheduled (throttling)
                    if (!this.rafScheduled) {
                        this.rafScheduled = true;
                        requestAnimationFrame(() => {
                            this.rafScheduled = false;
                            this.flushTokenBuffer(aiBubble);
                        });
                    }
                    break;

                case 'complete':
                    // Remove progress indicator
                    if (progressIndicator && progressIndicator.parentNode) {
                        progressIndicator.remove();
                    }
                    console.log('[DocAI] Chat completed successfully', eventData);
                    break;

                case 'error':
                    // Show error
                    if (progressIndicator && progressIndicator.parentNode) {
                        progressIndicator.remove();
                    }
                    const errorMsg = eventData.message || eventData.error || '發生未知錯誤';
                    aiBubble.innerHTML = `<span style="color: #e63946;">錯誤：${errorMsg}</span>`;
                    console.error('[DocAI] Chat error:', eventData);
                    break;

                default:
                    console.warn('[DocAI] Unknown SSE event type:', eventType, eventData);
            }
        } catch (handleError) {
            console.error('[DocAI] Error in handleSSEEvent:', handleError, 'Event:', event);
            throw handleError;  // Re-throw to be caught in streamChat
        }
    }

    /**
     * Create progress indicator UI
     * @returns {HTMLElement} - Progress indicator element
     */
    createProgressIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'progress-indicator';
        indicator.style.cssText = `
            font-size: 0.875rem;
            color: var(--color-text-secondary);
            padding: 0.5rem 0;
            border-top: 1px solid var(--color-border);
            margin-top: 0.5rem;
        `;
        indicator.innerHTML = `
            <div class="progress-phases" style="display: flex; gap: 0.5rem; margin-bottom: 0.5rem;">
                <span class="phase phase-1">①</span>
                <span class="phase phase-2">②</span>
                <span class="phase phase-3">③</span>
                <span class="phase phase-4">④</span>
                <span class="phase phase-5">⑤</span>
            </div>
            <div class="progress-message">Initializing...</div>
        `;
        return indicator;
    }

    /**
     * Update progress indicator
     * @param {HTMLElement} indicator - Progress indicator element
     * @param {Object} progressData - Progress data {phase, progress, message}
     */
    updateProgressIndicator(indicator, progressData) {
        const { phase, progress, message } = progressData;

        // Update phase indicators
        const phases = indicator.querySelectorAll('.phase');
        phases.forEach((phaseEl, index) => {
            const phaseNum = index + 1;
            if (phaseNum < phase) {
                phaseEl.style.color = '#34c759'; // Completed - green
            } else if (phaseNum === phase) {
                phaseEl.style.color = '#007aff'; // Current - blue
                phaseEl.style.fontWeight = 'bold';
            } else {
                phaseEl.style.color = '#c7c7cc'; // Pending - gray
            }
        });

        // Update message
        const messageEl = indicator.querySelector('.progress-message');
        if (messageEl) {
            messageEl.textContent = message || `Phase ${phase} - ${progress}%`;
        }
    }

    /**
     * Flush accumulated tokens to DOM (RAF-throttled)
     * Reduces DOM updates from ~500 to ~150 for typical responses
     * @param {HTMLElement} aiBubble - AI message bubble
     */
    flushTokenBuffer(aiBubble) {
        if (!this.tokenBuffer) return;

        // Update accumulated markdown
        const currentMarkdown = aiBubble.dataset.markdown || '';
        const newMarkdown = currentMarkdown + this.tokenBuffer;
        aiBubble.dataset.markdown = newMarkdown;

        // Clear buffer
        this.tokenBuffer = '';

        // Check if marked library is available
        if (typeof marked === 'undefined' || !marked.parse) {
            console.error('[DocAI] marked library not loaded!');
            let contentDiv = aiBubble.querySelector('.markdown-content');
            if (!contentDiv) {
                contentDiv = document.createElement('div');
                contentDiv.className = 'markdown-content';
                aiBubble.appendChild(contentDiv);
            }
            contentDiv.textContent = newMarkdown;
            return;
        }

        // Parse markdown and update DOM
        const htmlContent = marked.parse(newMarkdown);
        let contentDiv = aiBubble.querySelector('.markdown-content');
        if (!contentDiv) {
            contentDiv = document.createElement('div');
            contentDiv.className = 'markdown-content';
            aiBubble.appendChild(contentDiv);
        }
        contentDiv.innerHTML = htmlContent;

        // Auto-scroll to bottom
        this.chatDisplayArea.scrollTop = this.chatDisplayArea.scrollHeight;
    }

    /**
     * Add message bubble to chat
     * @param {string} role - 'user' or 'ai'
     * @param {string} content - Message content
     * @returns {HTMLElement} - Created bubble element
     */
    addMessageBubble(role, content) {
        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${role}`;

        if (content) {
            if (role === 'ai') {
                bubble.innerHTML = marked.parse(content);
            } else {
                bubble.textContent = content;
            }
        }

        this.chatDisplayArea.appendChild(bubble);
        this.chatDisplayArea.scrollTop = this.chatDisplayArea.scrollHeight;

        return bubble;
    }

    /**
     * Reset session and clear chat history
     * Call this when user clicks "新增來源" to start fresh conversation
     */
    resetSession() {
        // Generate new session ID
        this.sessionId = this.generateSessionId();

        // Clear chat display area
        if (this.chatDisplayArea) {
            this.chatDisplayArea.innerHTML = `
                <div class="chat-bubble ai">
                    歡迎使用 DocAI 系統，這裡可以上傳您的文件並進行智慧問答
                </div>
            `;
        }

        console.log('[DocAI] Session reset:', { sessionId: this.sessionId });
    }

    /**
     * Show error notification
     * @param {string} message - Error message
     */
    showError(message) {
        // Simple alert for now (can be enhanced with toast notifications)
        alert(message);
    }

    /**
     * Show debug popup with selected files info
     * @param {Array<string>} fileIds - Array of selected file IDs
     */
    showDebugPopup(fileIds) {
        // Build file info list: [file_id, filename]
        const fileInfoList = fileIds.map(fileId => {
            const fileInfo = this.uploadedFiles.get(fileId);
            const filename = fileInfo ? fileInfo.filename : 'Unknown';
            return `[${fileId}, ${filename}]`;
        });

        // Format message
        const message = `📋 Debug Mode - Selected Files:\n\n${fileInfoList.join('\n')}`;

        // Show popup
        alert(message);
    }
}

// Initialize client on DOM ready
let docaiClient;

document.addEventListener('DOMContentLoaded', () => {
    docaiClient = new DocAIClient();
    docaiClient.init();

    // Expose to global scope for debugging
    window.docaiClient = docaiClient;
});
