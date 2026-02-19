const API = '';
let currentSessionId = null;
let isLoading = false;
let rightPanelVisible = true;
let currentFilePath = '.';
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
        list.innerHTML = '<div class="empty-state" style="padding:20px"><p style="font-size:12px;color:var(--text-muted)">No chats yet</p></div>';
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
    showChatView();
    document.getElementById('sessionTitle').textContent = 'New Chat';
    document.getElementById('messagesContainer').innerHTML = '';
    showWelcome();
    document.getElementById('messageInput').focus();
}

async function selectSession(sessionId) {
    currentSessionId = sessionId;
    await loadSessions();
    const data = await api(`/api/sessions/${sessionId}/messages`);
    showChatView();

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
    loadToolExecutions(sessionId);
}

async function deleteSession(sessionId) {
    await api(`/api/sessions/${sessionId}`, { method: 'DELETE' });
    if (currentSessionId === sessionId) {
        currentSessionId = null;
        document.getElementById('messagesContainer').innerHTML = '';
        showWelcome();
        document.getElementById('sessionTitle').textContent = 'Select or create a chat';
    }
    await loadSessions();
}

function showChatView() {
    document.getElementById('welcomeScreen')?.remove();
}

function showWelcome() {
    const container = document.getElementById('messagesContainer');
    container.innerHTML = `
        <div class="welcome-screen" id="welcomeScreen">
            <div class="welcome-icon"><i class="ri-robot-2-fill"></i></div>
            <h2>Manus Agent</h2>
            <p>AI Agent otonom dengan kemampuan tools lengkap</p>
            <div class="capability-grid">
                <div class="capability-card" onclick="quickAction('Tolong buatkan file Python hello world')">
                    <i class="ri-code-s-slash-line"></i><span>Code Execution</span>
                </div>
                <div class="capability-card" onclick="quickAction('Cari informasi terbaru tentang AI')">
                    <i class="ri-search-line"></i><span>Web Search</span>
                </div>
                <div class="capability-card" onclick="quickAction('List semua file di direktori saat ini')">
                    <i class="ri-folder-open-line"></i><span>File Operations</span>
                </div>
                <div class="capability-card" onclick="quickAction('Jalankan perintah uname -a di terminal')">
                    <i class="ri-terminal-box-line"></i><span>Shell Commands</span>
                </div>
            </div>
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
    updateStatusBar('Menghubungkan...');

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
                    updateStatusBar(`Menjalankan ${event.tool}...`);
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
                    addActivityItem({
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
                    loadToolExecutions(currentSessionId);
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

function showToolRunning(toolName, params) {
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
    };
    const icon = toolIcons[toolName] || 'ri-tools-line';

    el.innerHTML = `
        <div class="message-avatar"><i class="ri-robot-2-fill"></i></div>
        <div class="tool-running">
            <div class="tool-running-header">
                <i class="${icon} tool-spin"></i>
                <span>Menjalankan <strong>${escapeHtml(toolName)}</strong>...</span>
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

function quickAction(text) {
    document.getElementById('messageInput').value = text;
    sendMessage();
}

function appendMessage(role, content, metadata) {
    const container = document.getElementById('messagesContainer');
    const avatarIcon = role === 'user' ? 'ri-user-3-fill' : 'ri-robot-2-fill';
    const row = document.createElement('div');
    row.className = `message-row ${role}`;
    row.innerHTML = `
        <div class="message-avatar"><i class="${avatarIcon}"></i></div>
        <div class="message-bubble">${formatContent(content)}</div>
    `;
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
            <span>Agent sedang berpikir...</span>
        </div>
    `;
    container.appendChild(el);
    scrollToBottom();
}

function removeThinking() {
    document.getElementById('thinkingIndicator')?.remove();
}

function addActivityItem(toolExec) {
    const list = document.getElementById('activityList');
    if (list.querySelector('.empty-state')) list.innerHTML = '';

    const item = document.createElement('div');
    item.className = 'activity-item';
    const statusClass = toolExec.status === 'success' ? 'success' : 'tool';
    item.innerHTML = `
        <div class="activity-icon ${statusClass}"><i class="ri-tools-line"></i></div>
        <div class="activity-info">
            <div class="activity-title">${toolExec.tool}</div>
            <div class="activity-detail">${escapeHtml((toolExec.result || '').substring(0, 80))}</div>
        </div>
        <div class="activity-time">${toolExec.duration_ms || 0}ms</div>
    `;
    list.prepend(item);
}

async function loadToolExecutions(sessionId) {
    try {
        const data = await api(`/api/sessions/${sessionId}/tools`);
        const list = document.getElementById('activityList');
        if (!data.executions || data.executions.length === 0) return;
        list.innerHTML = '';
        data.executions.forEach(te => {
            const item = document.createElement('div');
            item.className = 'activity-item';
            item.innerHTML = `
                <div class="activity-icon tool"><i class="ri-tools-line"></i></div>
                <div class="activity-info">
                    <div class="activity-title">${te.tool_name}</div>
                    <div class="activity-detail">${escapeHtml((te.result || '').substring(0, 80))}</div>
                </div>
                <div class="activity-time">${te.duration_ms || 0}ms</div>
            `;
            list.appendChild(item);
        });
    } catch (e) {}
}

async function loadFiles(path) {
    currentFilePath = path || '.';
    document.getElementById('currentPath').textContent = currentFilePath;
    try {
        const data = await api(`/api/files?path=${encodeURIComponent(currentFilePath)}`);
        const list = document.getElementById('fileList');
        if (!data.entries || data.entries.length === 0) {
            list.innerHTML = '<div class="empty-state"><p>Empty directory</p></div>';
            return;
        }
        list.innerHTML = data.entries.map(e => {
            const isDir = e.type === 'directory';
            const icon = isDir ? 'ri-folder-fill folder' : 'ri-file-text-line file';
            const size = isDir ? '' : formatFileSize(e.size);
            const clickAction = isDir
                ? `navigateFiles('${currentFilePath}/${e.name}')`
                : `openFile('${currentFilePath}/${e.name}')`;
            return `
                <div class="file-item" onclick="${clickAction}">
                    <i class="${icon}"></i>
                    <span class="file-name">${escapeHtml(e.name)}</span>
                    <span class="file-size">${size}</span>
                </div>
            `;
        }).join('');
    } catch (e) {
        document.getElementById('fileList').innerHTML = `<div class="empty-state"><p>Error loading files</p></div>`;
    }
}

function navigateFiles(path) {
    loadFiles(path);
}

async function openFile(path) {
    try {
        const data = await api(`/api/files/read?path=${encodeURIComponent(path)}`);
        document.getElementById('codeFileName').textContent = path;
        document.getElementById('codeContent').textContent = data.content || '';
        document.getElementById('codeModal').classList.remove('hidden');
    } catch (e) {
        alert('Cannot open file: ' + e.message);
    }
}

function closeCodeViewer() {
    document.getElementById('codeModal').classList.add('hidden');
}

async function loadTools() {
    try {
        const data = await api('/api/agent/tools');
        const list = document.getElementById('toolsList');
        const toolIcons = {
            ShellTool: 'ri-terminal-box-line',
            FileTool: 'ri-file-code-line',
            SearchTool: 'ri-search-line',
            BrowserTool: 'ri-global-line',
            WebDevTool: 'ri-code-s-slash-line',
            GenerateTool: 'ri-image-line',
            SlidesTool: 'ri-slideshow-line',
            ScheduleTool: 'ri-calendar-line',
            MessageTool: 'ri-message-2-line',
            SkillManager: 'ri-lightbulb-line',
        };
        list.innerHTML = data.tools.map(t => `
            <div class="tool-list-item">
                <div class="tool-list-icon"><i class="${toolIcons[t.type] || 'ri-tools-line'}"></i></div>
                <div class="tool-list-info">
                    <div class="tool-list-name">${t.name}</div>
                    <div class="tool-list-type">${t.type}</div>
                </div>
            </div>
        `).join('');
    } catch (e) {}
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('collapsed');
}

function toggleActivityPanel() {
    const panel = document.getElementById('rightPanel');
    panel.classList.toggle('hidden');
    rightPanelVisible = !panel.classList.contains('hidden');
    if (rightPanelVisible) switchTab('activity');
}

function toggleFileExplorer() {
    const panel = document.getElementById('rightPanel');
    if (panel.classList.contains('hidden')) {
        panel.classList.remove('hidden');
        rightPanelVisible = true;
    }
    switchTab('files');
    loadFiles(currentFilePath);
}

function switchTab(tab) {
    document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel-content').forEach(c => c.classList.add('hidden'));
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
    document.getElementById(`${tab}Tab`).classList.remove('hidden');

    if (tab === 'files') loadFiles(currentFilePath);
    if (tab === 'tools') loadTools();
    if (tab === 'schedule') loadScheduleTasks();
    if (tab === 'skills') loadSkills();
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

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

async function loadScheduleTasks() {
    try {
        const data = await api('/api/schedule/tasks');
        const list = document.getElementById('scheduleList');
        const statsEl = document.getElementById('scheduleStats');

        const statsData = await api('/api/schedule/stats');
        if (statsEl) {
            statsEl.innerHTML = `
                <div style="display:flex;gap:12px;padding:8px 0;font-size:11px;color:var(--text-muted)">
                    <span>Total: <strong style="color:var(--text-primary)">${statsData.total_tasks || 0}</strong></span>
                    <span>Active: <strong style="color:var(--accent)">${statsData.active || 0}</strong></span>
                    <span>Runs: <strong style="color:var(--text-primary)">${statsData.total_runs || 0}</strong></span>
                </div>
            `;
        }

        if (!data.tasks || data.tasks.length === 0) {
            list.innerHTML = '<div class="empty-state"><i class="ri-calendar-line"></i><p>No scheduled tasks</p></div>';
            return;
        }

        list.innerHTML = data.tasks.map(t => {
            const typeIcon = t.type === 'cron' ? 'ri-time-line' : t.type === 'once' ? 'ri-timer-line' : 'ri-repeat-line';
            const statusClass = t.status === 'active' ? 'success' : t.status === 'paused' ? 'warning' : 'muted';
            const nextRun = t.next_run ? new Date(t.next_run * 1000).toLocaleTimeString() : '-';
            return `
                <div class="schedule-item">
                    <div class="schedule-item-header">
                        <i class="${typeIcon}" style="color:var(--accent)"></i>
                        <span class="schedule-name">${escapeHtml(t.name)}</span>
                        <span class="schedule-status ${statusClass}">${t.status}</span>
                    </div>
                    <div class="schedule-item-detail">
                        <span>${t.type}${t.interval ? ' (' + t.interval + 's)' : ''}${t.cron_expression ? ' (' + t.cron_expression + ')' : ''}</span>
                        <span>Runs: ${t.run_count} | Next: ${nextRun}</span>
                    </div>
                    <div class="schedule-item-actions">
                        ${t.status === 'active' ? `<button class="btn-xs" onclick="pauseTask('${t.task_id}')"><i class="ri-pause-line"></i></button>` : ''}
                        ${t.status === 'paused' ? `<button class="btn-xs" onclick="resumeTask('${t.task_id}')"><i class="ri-play-line"></i></button>` : ''}
                        <button class="btn-xs btn-danger" onclick="cancelTask('${t.task_id}')"><i class="ri-delete-bin-line"></i></button>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load schedule tasks:', e);
    }
}

async function pauseTask(taskId) {
    await api(`/api/schedule/tasks/${taskId}/pause`, { method: 'POST' });
    loadScheduleTasks();
}

async function resumeTask(taskId) {
    await api(`/api/schedule/tasks/${taskId}/resume`, { method: 'POST' });
    loadScheduleTasks();
}

async function cancelTask(taskId) {
    await api(`/api/schedule/tasks/${taskId}`, { method: 'DELETE' });
    loadScheduleTasks();
}

async function loadSkills() {
    try {
        const data = await api('/api/skills');
        const list = document.getElementById('skillsList');

        if (!data.skills || data.skills.length === 0) {
            list.innerHTML = '<div class="empty-state"><i class="ri-lightbulb-line"></i><p>No skills loaded</p></div>';
            return;
        }

        list.innerHTML = data.skills.map(s => {
            const caps = (s.capabilities || []).slice(0, 3).map(c => `<span class="skill-cap">${escapeHtml(c)}</span>`).join('');
            const scripts = (s.scripts || []).map(sc => `<span class="skill-script">${escapeHtml(sc)}</span>`).join('');
            return `
                <div class="skill-item">
                    <div class="skill-item-header">
                        <i class="ri-lightbulb-line" style="color:var(--accent)"></i>
                        <span class="skill-name">${escapeHtml(s.name)}</span>
                        <span class="skill-version">v${s.version || '1.0.0'}</span>
                    </div>
                    <div class="skill-desc">${escapeHtml(s.description || '').substring(0, 120)}</div>
                    ${caps ? `<div class="skill-caps">${caps}</div>` : ''}
                    ${scripts ? `<div class="skill-scripts"><i class="ri-code-line"></i> ${scripts}</div>` : ''}
                    <div class="skill-meta">
                        <span>Used: ${s.use_count || 0}x</span>
                        ${s.author ? `<span>By: ${escapeHtml(s.author)}</span>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load skills:', e);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadSessions();
    loadTools();
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeCodeViewer();
});
