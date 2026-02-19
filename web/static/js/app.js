const API = '';
let currentSessionId = null;
let isLoading = false;
let streamAbortController = null;

async function api(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    return res.json();
}

async function loadSessions() {
    const data = await api('/api/sessions');
    const list = document.getElementById('sessionList');
    if (!data.sessions || data.sessions.length === 0) {
        list.innerHTML = '<div style="padding:20px;text-align:center;font-size:12px;color:var(--text-muted)">No chats yet</div>';
        return;
    }
    list.innerHTML = data.sessions.map(s => `
        <div class="session-item ${s.id === currentSessionId ? 'active' : ''}" onclick="selectSession('${s.id}')">
            <i class="ri-chat-3-line"></i>
            <span class="session-name">${escapeHtml(s.title)}</span>
            <button class="btn-icon btn-sm session-delete" onclick="event.stopPropagation(); deleteSession('${s.id}')" title="Delete">
                <i class="ri-delete-bin-line"></i>
            </button>
        </div>
    `).join('');
}

async function createNewSession() {
    const data = await api('/api/sessions', {
        method: 'POST',
        body: JSON.stringify({ title: 'New Chat' })
    });
    currentSessionId = data.session.id;
    await loadSessions();
    document.getElementById('sessionTitle').textContent = 'New Chat';
    document.getElementById('messagesContainer').innerHTML = '';
    showWelcome();
    document.getElementById('messageInput').focus();
}

async function selectSession(sessionId) {
    currentSessionId = sessionId;
    await loadSessions();
    const data = await api(`/api/sessions/${sessionId}/messages`);

    const session = (await api('/api/sessions')).sessions.find(s => s.id === sessionId);
    document.getElementById('sessionTitle').textContent = session ? session.title : 'Chat';

    const container = document.getElementById('messagesContainer');
    if (!data.messages || data.messages.length === 0) {
        showWelcome();
        return;
    }

    container.innerHTML = '';
    data.messages.forEach(msg => {
        if (msg.role === 'system') return;
        appendMessage(msg.role, msg.content, msg.metadata);
    });
    scrollToBottom();
}

async function deleteSession(sessionId) {
    await api(`/api/sessions/${sessionId}`, { method: 'DELETE' });
    if (currentSessionId === sessionId) {
        currentSessionId = null;
        document.getElementById('messagesContainer').innerHTML = '';
        showWelcome();
        document.getElementById('sessionTitle').textContent = 'New Chat';
    }
    await loadSessions();
}

function showWelcome() {
    const container = document.getElementById('messagesContainer');
    container.innerHTML = `
        <div class="welcome-screen" id="welcomeScreen">
            <h2>Apa yang bisa saya bantu?</h2>
        </div>`;
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    if (!message || isLoading) return;

    if (!currentSessionId) {
        await createNewSession();
    }

    const welcomeEl = document.getElementById('welcomeScreen');
    if (welcomeEl) welcomeEl.remove();

    appendMessage('user', message);
    input.value = '';
    input.style.height = 'auto';
    scrollToBottom();

    isLoading = true;
    document.getElementById('sendBtn').disabled = true;
    updateStatusBar('Thinking...');

    showThinking();

    try {
        await sendStreamingMessage(message);
    } catch (err) {
        removeThinking();
        removeStreamingBubble();
        appendMessage('assistant', `Error: ${err.message}`);
    }

    isLoading = false;
    document.getElementById('sendBtn').disabled = false;
    updateStatusBar('Agent Ready');
    scrollToBottom();
}

async function sendStreamingMessage(message) {
    streamAbortController = new AbortController();

    const response = await fetch(`${API}/api/sessions/${currentSessionId}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
        signal: streamAbortController.signal,
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let streamBubbleCreated = false;
    let streamContent = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith('data: ')) continue;

            const jsonStr = trimmed.slice(6);
            let event;
            try {
                event = JSON.parse(jsonStr);
            } catch { continue; }

            switch (event.type) {
                case 'status':
                    removeThinking();
                    updateStatusBar(event.content);
                    showThinkingWithText(event.content);
                    break;

                case 'tool_start':
                    removeThinking();
                    updateStatusBar(`Running ${event.tool}...`);
                    showToolRunning(event.tool, event.params);
                    break;

                case 'tool_result':
                    removeToolRunning();
                    appendToolCard({
                        tool: event.tool,
                        result: event.result,
                        duration_ms: event.duration_ms,
                        status: event.status,
                    });
                    showThinking();
                    break;

                case 'chunk':
                    removeThinking();
                    if (!streamBubbleCreated) {
                        createStreamingBubble();
                        streamBubbleCreated = true;
                    }
                    streamContent += event.content;
                    updateStreamingBubble(streamContent);
                    scrollToBottom();
                    break;

                case 'done':
                    removeThinking();
                    if (streamBubbleCreated) {
                        finalizeStreamingBubble(streamContent);
                    } else if (event.content) {
                        appendMessage('assistant', event.content);
                    }
                    await loadSessions();
                    break;

                case 'error':
                    removeThinking();
                    removeStreamingBubble();
                    appendMessage('assistant', `Error: ${event.content}`);
                    break;
            }
        }
    }
}

function createStreamingBubble() {
    const container = document.getElementById('messagesContainer');
    const row = document.createElement('div');
    row.className = 'message-row assistant';
    row.id = 'streamingMessage';
    row.innerHTML = `
        <div class="message-avatar"><i class="ri-robot-2-fill"></i></div>
        <div class="message-bubble streaming-bubble"><span class="cursor-blink">|</span></div>
    `;
    container.appendChild(row);
    scrollToBottom();
}

function updateStreamingBubble(content) {
    const bubble = document.querySelector('#streamingMessage .message-bubble');
    if (bubble) {
        bubble.innerHTML = formatContent(content) + '<span class="cursor-blink">|</span>';
    }
}

function finalizeStreamingBubble(content) {
    const bubble = document.querySelector('#streamingMessage .message-bubble');
    if (bubble) {
        bubble.innerHTML = formatContent(content);
        bubble.classList.remove('streaming-bubble');
    }
    const el = document.getElementById('streamingMessage');
    if (el) el.removeAttribute('id');
}

function removeStreamingBubble() {
    document.getElementById('streamingMessage')?.remove();
}

function showThinkingWithText(text) {
    removeThinking();
    const container = document.getElementById('messagesContainer');
    const el = document.createElement('div');
    el.id = 'thinkingIndicator';
    el.className = 'message-row assistant';
    el.innerHTML = `
        <div class="message-avatar"><i class="ri-robot-2-fill"></i></div>
        <div class="thinking-indicator">
            <div class="thinking-dots"><span></span><span></span><span></span></div>
            <span>${escapeHtml(text)}</span>
        </div>
    `;
    container.appendChild(el);
    scrollToBottom();
}

function showToolRunning(toolName) {
    removeThinking();
    removeToolRunning();
    const container = document.getElementById('messagesContainer');
    const el = document.createElement('div');
    el.id = 'toolRunningIndicator';
    el.className = 'message-row assistant';

    const toolIcons = {
        shell_tool: 'ri-terminal-box-line',
        file_tool: 'ri-file-code-line',
        search_tool: 'ri-search-line',
        browser_tool: 'ri-global-line',
        webdev_tool: 'ri-code-s-slash-line',
        generate_tool: 'ri-image-line',
        slides_tool: 'ri-slideshow-line',
        schedule_tool: 'ri-calendar-line',
        message_tool: 'ri-message-2-line',
        skill_manager: 'ri-lightbulb-line',
    };
    const icon = toolIcons[toolName] || 'ri-tools-line';

    el.innerHTML = `
        <div class="message-avatar"><i class="ri-robot-2-fill"></i></div>
        <div class="tool-running">
            <div class="tool-running-header">
                <i class="${icon} tool-spin"></i>
                <span>Running <strong>${escapeHtml(toolName)}</strong>...</span>
            </div>
        </div>
    `;
    container.appendChild(el);
    scrollToBottom();
}

function removeToolRunning() {
    document.getElementById('toolRunningIndicator')?.remove();
}

function updateStatusBar(text) {
    const el = document.getElementById('statusText');
    if (el) el.textContent = text;
}

function appendMessage(role, content) {
    const container = document.getElementById('messagesContainer');
    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    if (role === 'assistant') {
        row.innerHTML = `
            <div class="message-avatar"><i class="ri-robot-2-fill"></i></div>
            <div class="message-bubble">${formatContent(content)}</div>
        `;
    } else {
        row.innerHTML = `
            <div class="message-bubble">${formatContent(content)}</div>
        `;
    }

    container.appendChild(row);
    scrollToBottom();
}

function appendToolCard(toolExec) {
    const container = document.getElementById('messagesContainer');
    const card = document.createElement('div');
    card.className = 'message-row assistant';

    const toolIcons = {
        shell_tool: 'ri-terminal-box-line',
        file_tool: 'ri-file-code-line',
        search_tool: 'ri-search-line',
        browser_tool: 'ri-global-line',
        webdev_tool: 'ri-code-s-slash-line',
        generate_tool: 'ri-image-line',
        slides_tool: 'ri-slideshow-line',
        schedule_tool: 'ri-calendar-line',
        message_tool: 'ri-message-2-line',
        skill_manager: 'ri-lightbulb-line',
    };
    const icon = toolIcons[toolExec.tool] || 'ri-tools-line';

    card.innerHTML = `
        <div class="message-avatar"><i class="ri-robot-2-fill"></i></div>
        <div class="tool-card">
            <div class="tool-card-header">
                <i class="${icon}"></i>
                <span>${toolExec.tool}</span>
            </div>
            <div class="tool-card-result">${escapeHtml(toolExec.result || '').substring(0, 1000)}</div>
            <div class="tool-card-meta">
                <span>${toolExec.duration_ms || 0}ms</span>
                <span>${toolExec.status || 'done'}</span>
            </div>
        </div>
    `;
    container.appendChild(card);
}

function showThinking() {
    removeThinking();
    const container = document.getElementById('messagesContainer');
    const el = document.createElement('div');
    el.id = 'thinkingIndicator';
    el.className = 'message-row assistant';
    el.innerHTML = `
        <div class="message-avatar"><i class="ri-robot-2-fill"></i></div>
        <div class="thinking-indicator">
            <div class="thinking-dots"><span></span><span></span><span></span></div>
            <span>Thinking...</span>
        </div>
    `;
    container.appendChild(el);
    scrollToBottom();
}

function removeThinking() {
    document.getElementById('thinkingIndicator')?.remove();
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('collapsed');
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
    autoResize(e.target);
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    requestAnimationFrame(() => container.scrollTop = container.scrollHeight);
}

function formatContent(text) {
    if (!text) return '';
    text = escapeHtml(text);
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) => {
        return `<div class="tool-card"><div class="tool-card-header"><i class="ri-code-line"></i><span>${lang || 'code'}</span></div><div class="tool-card-result">${code}</div></div>`;
    });
    text = text.replace(/`([^`]+)`/g, '<code style="background:var(--bg-tertiary);padding:2px 6px;border-radius:4px;font-family:JetBrains Mono,monospace;font-size:12px">$1</code>');
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\n/g, '<br>');
    return text;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function closeCodeViewer() {
    document.getElementById('codeModal').classList.add('hidden');
}

document.addEventListener('DOMContentLoaded', () => {
    loadSessions();
    document.getElementById('messageInput').focus();
});
