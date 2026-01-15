/**
 * Progressive Markdown Renderer
 *
 * Token-by-token markdown rendering with progress tracking for OPMP integration.
 * Adapted from OPMP for DocAI Skill-Based system.
 *
 * Features:
 * - Real-time token-by-token rendering
 * - Progress bar with phase-specific colors
 * - Red checkmark completion animation
 * - Error handling and recovery
 *
 * Author: Claude (SuperClaude)
 * Date: 2025-12-06
 * Based on: OPMP progressive rendering patterns
 */

class ProgressiveMarkdownRenderer {
    constructor(containerSelector, progressSelector) {
        this.container = document.querySelector(containerSelector);
        this.progressBar = document.querySelector(progressSelector);
        this.markdownBuffer = "";
        this.currentPhase = 0;
        this.isComplete = false;
        this.sessionId = null;  // Session ID for acknowledgment protocol
        this.phaseStartTime = null;  // Track phase start time for minimum 2s animation

        if (!this.container) {
            console.error(`Container not found: ${containerSelector}`);
        }

        if (!this.progressBar) {
            console.error(`Progress bar not found: ${progressSelector}`);
        }
    }

    /**
     * Reset renderer state for new query
     */
    reset() {
        this.markdownBuffer = "";
        this.currentPhase = 0;
        this.isComplete = false;
        this.sessionId = null;  // Reset session ID
        this.phaseStartTime = Date.now();  // Initialize phase start time

        if (this.container) {
            // Preserve think indicator if it exists
            const thinkIndicator = this.container.querySelector('.think-indicator');
            this.container.innerHTML = "";
            if (thinkIndicator) {
                this.container.appendChild(thinkIndicator);
            }
        }

        if (this.progressBar) {
            // Disable progress bar - hide it completely
            this.progressBar.style.display = "none";
            const progressContainer = this.progressBar.closest('.progress-container');
            if (progressContainer) {
                progressContainer.style.display = "none";
            }
        }
    }

    /**
     * Set session ID from backend session_init event
     * @param {string} sessionId - Unique session identifier
     */
    setSessionId(sessionId) {
        this.sessionId = sessionId;
        console.log(`Session ID set: ${sessionId}`);
    }

    /**
     * Send acknowledgment to backend that phase rendering is complete
     * MINIMUM 2-second delay per phase to ensure smooth animations
     * @param {number} phase - Phase number (1-4)
     */
    async acknowledgePhase(phase) {
        if (!this.sessionId) {
            console.warn(`Cannot ACK phase ${phase}: No session ID`);
            return;
        }

        // Calculate elapsed time since phase started
        const elapsedMs = Date.now() - this.phaseStartTime;
        const minimumDelayMs = 1500;  // 1.5 seconds minimum per phase

        // If phase completed too quickly, delay ACK to ensure smooth animation
        if (elapsedMs < minimumDelayMs) {
            const remainingDelay = minimumDelayMs - elapsedMs;
            console.log(`⏳ Phase ${phase} completed in ${elapsedMs}ms, delaying ACK by ${remainingDelay}ms for smooth animation`);
            await new Promise(resolve => setTimeout(resolve, remainingDelay));
        }

        try {
            const response = await fetch(`/api/v1/skills/acknowledge/${this.sessionId}/${phase}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            });

            if (response.ok) {
                const data = await response.json();
                console.log(`✅ Phase ${phase} acknowledged:`, data);

                // Reset phase start time for next phase
                this.phaseStartTime = Date.now();
            } else {
                console.error(`❌ Failed to ACK phase ${phase}: ${response.status}`);
            }
        } catch (error) {
            console.error(`❌ ACK error for phase ${phase}:`, error);
        }
    }

    /**
     * Add token and re-render markdown
     * @param {string} token - Markdown token to add
     */
    addToken(token) {
        this.markdownBuffer += token;

        if (this.container) {
            // Preserve think indicator if it exists
            const thinkIndicator = this.container.querySelector('.think-indicator');
            const thinkIndicatorHtml = thinkIndicator ? thinkIndicator.outerHTML : '';
            
            // Use marked.js for markdown parsing
            if (typeof marked !== 'undefined') {
                this.container.innerHTML = thinkIndicatorHtml + marked.parse(this.markdownBuffer);
            } else {
                // Fallback to plain text if marked.js not loaded
                this.container.innerHTML = thinkIndicatorHtml;
                this.container.appendChild(document.createTextNode(this.markdownBuffer));
            }

            // Auto-scroll during streaming (only if user hasn't scrolled up and stream is not complete)
            if (!this.isComplete && !window.userHasScrolled && !window.streamJustCompleted) {
                setTimeout(() => {
                    // Scroll the chat area, not the window
                    const chatArea = document.getElementById('chat-area');
                    if (chatArea && !this.isComplete && !window.streamJustCompleted) {
                        chatArea.scrollTop = chatArea.scrollHeight;
                    }
                }, 50);
            }
        }
    }

    /**
     * Update progress bar with phase information
     * 5-segment design: Phase 1→20%, Phase 2→40%, Phase 3→60%, Phase 4→80%, Phase 5→100%
     * @param {number} phase - Phase number (1-5)
     * @param {string} message - Progress message
     * @param {number} progress - Progress percentage (0-100, ignored - using phase mapping)
     */
    updateProgress(phase, message, progress) {
        // Progress bar disabled - do nothing
        return;
    }

    /**
     * Update progress bar color based on phase
     * @param {number} phase - Phase number (1-5)
     * @private
     */
    _updatePhaseColor(phase) {
        if (!this.progressBar) return;

        // Remove all phase classes
        this.progressBar.className = 'progress-bar';

        // Add phase-specific class
        switch(phase) {
            case 1:
                this.progressBar.classList.add('phase-1');
                break;
            case 2:
                this.progressBar.classList.add('phase-2');
                break;
            case 3:
                this.progressBar.classList.add('phase-3');
                break;
            case 4:
                this.progressBar.classList.add('phase-4');
                break;
            case 5:
                this.progressBar.classList.add('phase-5');
                break;
        }
    }

    /**
     * Mark rendering as complete with red checkmark
     */
    complete() {
        this.isComplete = true;
        // Progress bar disabled - hide it completely
        if (this.progressBar) {
            this.progressBar.style.display = "none";
            const progressContainer = this.progressBar.closest('.progress-container');
            if (progressContainer) {
                progressContainer.style.display = "none";
            }
        }
    }

    /**
     * Handle error state
     * @param {string} errorMessage - Error message to display
     */
    handleError(errorMessage) {
        // Progress bar disabled - hide it
        if (this.progressBar) {
            this.progressBar.style.display = "none";
            const progressContainer = this.progressBar.closest('.progress-container');
            if (progressContainer) {
                progressContainer.style.display = "none";
            }
        }

        if (this.container && this.markdownBuffer === "") {
            this.container.innerHTML = `<div class="error-message">系統發生錯誤: ${errorMessage}</div>`;
        }
    }

    /**
     * Handle user-initiated stop (abort)
     * Shows stopped state without error styling
     */
    handleStopped() {
        this.isComplete = true;

        // Progress bar disabled - hide it
        if (this.progressBar) {
            this.progressBar.style.display = "none";
            const progressContainer = this.progressBar.closest('.progress-container');
            if (progressContainer) {
                progressContainer.style.display = "none";
            }
        }

        // If there's partial content, append stopped marker
        if (this.container && this.markdownBuffer.trim()) {
            this.container.innerHTML = marked.parse(this.markdownBuffer + '\n\n---\n*[已停止生成]*');
        } else if (this.container) {
            this.container.innerHTML = '<div class="stopped-message">已停止生成</div>';
        }
    }

    /**
     * Get current markdown buffer
     * @returns {string} Current markdown content
     */
    getMarkdown() {
        return this.markdownBuffer;
    }
}

/**
 * Start progressive chat with SSE streaming
 * @param {string} query - User query
 * @param {string} endpoint - API endpoint URL
 * @param {string} containerSelector - Container element selector
 * @param {string} progressSelector - Progress bar element selector
 * @param {Array<string>} document_ids - Selected document IDs
 * @param {Function} onComplete - Optional callback when streaming completes
 * @param {AbortSignal} abortSignal - Optional AbortSignal for cancellation
 * @param {Object} memoryParams - Optional Memory parameters for multi-turn context
 */
function startProgressiveChat(query, endpoint, containerSelector, progressSelector, document_ids, onComplete, abortSignal, memoryParams = {}) {
    const renderer = new ProgressiveMarkdownRenderer(containerSelector, progressSelector);

    // Reset renderer
    renderer.reset();

    // ✅ Build request body with Memory support
    const requestBody = {
        query: query,
        document_ids: document_ids || [],
        // Memory parameters (reusing pattern from sendTraditionalQuery)
        user_id: memoryParams.user_id || null,
        include_history: memoryParams.include_history !== false,  // Default true
        history_limit: memoryParams.history_limit || 10
    };

    // Make POST request with fetch (with optional abort signal)
    fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody),
        signal: abortSignal  // ✅ Support abort signal for stop generation
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        // Get reader for streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        return readStream(reader, decoder, renderer, onComplete);
    })
    .catch(error => {
        // ✅ Handle user-initiated abort gracefully
        if (error.name === 'AbortError') {
            console.log('🛑 User stopped generation');
            renderer.handleStopped();  // Mark as stopped, not error

            if (typeof onComplete === 'function') {
                onComplete(true, renderer.getMarkdown(), true);  // success=true, aborted=true
            }
            return;
        }

        console.error('Progressive streaming error:', error);
        renderer.handleError(`請求失敗: ${error.message}`);

        // Call completion callback on error too
        if (typeof onComplete === 'function') {
            onComplete(false, '');  // Pass false to indicate error, empty markdown
        }
    });
}

/**
 * Read SSE stream and process events
 * @param {ReadableStreamDefaultReader} reader - Stream reader
 * @param {TextDecoder} decoder - Text decoder
 * @param {ProgressiveMarkdownRenderer} renderer - Renderer instance
 * @param {Function} onComplete - Completion callback
 */
async function readStream(reader, decoder, renderer, onComplete) {
    let buffer = "";
    let onCompleteInvoked = false;  // ✅ Guard to prevent duplicate onComplete calls

    // Wrapper to ensure onComplete is only called once
    const invokeOnComplete = (success, markdown) => {
        if (onCompleteInvoked) {
            console.log('⚠️ onComplete already invoked, skipping duplicate call');
            return;
        }
        onCompleteInvoked = true;
        if (typeof onComplete === 'function') {
            onComplete(success, markdown);
        }
    };

    try {
        while (true) {
            const {done, value} = await reader.read();

            if (done) {
                // Stream complete
                if (!renderer.isComplete) {
                    renderer.complete();
                }

                // ✅ Use wrapper to prevent duplicate callback
                invokeOnComplete(true, renderer.getMarkdown());
                break;
            }

            // Decode chunk and add to buffer
            buffer += decoder.decode(value, {stream: true});

            // Process complete SSE events (split by \n\n)
            const events = buffer.split('\n\n');

            // Keep incomplete event in buffer
            buffer = events.pop();

            // Process complete events
            for (const eventText of events) {
                if (eventText.trim() === "") continue;

                try {
                    // Parse SSE event (format: "data: {...}")
                    const dataMatch = eventText.match(/^data:\s*(.+)$/m);
                    if (dataMatch) {
                        const eventData = JSON.parse(dataMatch[1]);
                        // ✅ Pass wrapper function instead of raw onComplete
                        handleSSEEvent(eventData, renderer, invokeOnComplete);
                    }
                } catch (parseError) {
                    console.error('Failed to parse SSE event:', parseError, eventText);
                }
            }
        }
    } catch (streamError) {
        // ✅ 檢查是否為用戶主動停止（AbortError）
        if (streamError.name === 'AbortError') {
            console.log('🛑 User stopped generation (stream level)');
            renderer.handleStopped();
            invokeOnComplete(true, renderer.getMarkdown(), true);  // success=true, aborted=true
            return;
        }

        // 真正的串流錯誤
        console.error('Stream reading error:', streamError);
        renderer.handleError(`串流讀取失敗: ${streamError.message}`);

        // ✅ Use wrapper to prevent duplicate callback
        invokeOnComplete(false, renderer.getMarkdown() || '');
    }
}

/**
 * Handle individual SSE event
 * @param {Object} eventData - Parsed event data
 * @param {ProgressiveMarkdownRenderer} renderer - Renderer instance
 * @param {Function} invokeComplete - Wrapped completion callback (guards against duplicate calls)
 */
function handleSSEEvent(eventData, renderer, invokeComplete) {
    const type = eventData.type;
    const phase = eventData.phase || 0;

    switch(type) {
        case 'session_init':
            // Backend sending session ID for acknowledgment protocol
            const sessionId = eventData.session_id;
            renderer.setSessionId(sessionId);
            console.log(`🔗 Session initialized: ${sessionId}`);
            break;

        case 'progress':
            // Progress update
            const message = eventData.message || "處理中...";
            const progress = eventData.progress || 0;
            renderer.updateProgress(phase, message, progress);
            break;

        case 'markdown_token':
            // Token from Phase 4
            const token = eventData.token || "";
            renderer.addToken(token);
            break;

        case 'phase_result':
            // Phase completion - send acknowledgment to backend
            console.log(`Phase ${phase} complete:`, eventData.data);

            // Acknowledge phase completion to backend (phases 1-4 only)
            if (phase >= 1 && phase <= 4) {
                renderer.acknowledgePhase(phase);
            }
            break;

        case 'complete':
            // Final completion
            renderer.complete();

            // ✅ Use wrapper to prevent duplicate callback
            invokeComplete(true, renderer.getMarkdown());
            break;

        case 'error':
            // Error occurred
            const errorMsg = eventData.message || "未知錯誤";
            renderer.handleError(errorMsg);

            // ✅ Use wrapper to prevent duplicate callback
            invokeComplete(false, '');
            break;

        case 'warning':
            // Warning (non-fatal)
            console.warn(`Phase ${phase} warning:`, eventData.message);
            break;

        default:
            console.log('Unknown event type:', type, eventData);
    }
}

/**
 * Utility: Create progress bar HTML element
 * @param {string} containerId - Container element ID
 * @returns {string} HTML string
 */
function createProgressBarHTML(containerId) {
    return `
        <div class="progress-container" id="${containerId}" style="display: none;">
            <div id="${containerId}-bar" class="progress-bar"></div>
        </div>
    `;
}

/**
 * Utility: Show progress container
 * @param {string} containerId - Container element ID
 */
function showProgressBar(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.style.display = 'block';
    }
}

/**
 * Utility: Hide progress container
 * @param {string} containerId - Container element ID
 */
function hideProgressBar(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.style.display = 'none';
    }
}
