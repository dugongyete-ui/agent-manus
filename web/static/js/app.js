const API = '';
let currentSessionId = null;
let isLoading = false;
let streamAbortController = null;
let currentModel = null;
let allModels = [];
let activeCategory = null;
let stepTracker = null;
let activeToolCards = {};

const TOOL_CONFIG = {
    shell_tool: {
        icon: 'ri-terminal-box-line',
        label: 'Terminal',
        color: '#2ecc71',
    },
    file_tool: {
        icon: 'ri-file-code-line',
        label: 'File Editor',
        color: '#3498db',
    },
    search_tool: {
        icon: 'ri-search-line',
        label: 'Web Search',
        color: '#f39c12',
    },
    browser_tool: {
        icon: 'ri-global-line',
        label: 'Browser',
        color: '#9b59b6',
    },
    generate_tool: {
        icon: 'ri-image-line',
        label: 'Generator',
        color: '#e74c3c',
    },
    slides_tool: {
        icon: 'ri-slideshow-line',
        label: 'Slides',
        color: '#e67e22',
    },
    webdev_tool: {
        icon: 'ri-code-s-slash-line',
        label: 'WebDev',
        color: '#1abc9c',
    },
    schedule_tool: {
        icon: 'ri-calendar-todo-line',
        label: 'Scheduler',
        color: '#f1c40f',
    },
    message_tool: {
        icon: 'ri-message-2-line',
        label: 'Message',
        color: '#00cec9',
    },
    skill_manager: {
        icon: 'ri-lightbulb-line',
        label: 'Skill Manager',
        color: '#fd79a8',
    },
};

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
        list.innerHTML = '<div style="padding:20px;text-align:center;font-size:12px;color:var(--text-muted)">Belum ada chat</div>';
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
        if (msg.metadata && msg.metadata.tool_executions) {
            msg.metadata.tool_executions.forEach(te => {
                appendCompletedToolCard(te);
            });
        }
        appendMessage(msg.role, msg.content);
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
            <div class="welcome-tools">
                <div class="welcome-tool-card" onclick="quickSend('Cari informasi terbaru tentang ')">
                    <i class="ri-search-line"></i><span>Pencarian Web</span>
                </div>
                <div class="welcome-tool-card" onclick="quickSend('Jalankan perintah terminal: ')">
                    <i class="ri-terminal-box-line"></i><span>Terminal</span>
                </div>
                <div class="welcome-tool-card" onclick="quickSend('Buat file ')">
                    <i class="ri-file-code-line"></i><span>Buat File</span>
                </div>
                <div class="welcome-tool-card" onclick="quickSend('Buka dan analisis website ')">
                    <i class="ri-global-line"></i><span>Browser</span>
                </div>
                <div class="welcome-tool-card" onclick="quickSend('Buat gambar ')">
                    <i class="ri-image-line"></i><span>Generate</span>
                </div>
                <div class="welcome-tool-card" onclick="quickSend('Buat presentasi tentang ')">
                    <i class="ri-slideshow-line"></i><span>Slides</span>
                </div>
            </div>
        </div>`;
}

function quickSend(text) {
    const input = document.getElementById('messageInput');
    input.value = text;
    input.focus();
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
    stepTracker = createStepTracker();
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
    activeToolCards = {};
    scrollToBottom();
}

async function sendStreamingMessage(message) {
    streamAbortController = new AbortController();
    const payload = { message };
    if (currentModel) payload.model = currentModel;

    const response = await fetch(`${API}/api/sessions/${currentSessionId}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: streamAbortController.signal,
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

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

            let event;
            try { event = JSON.parse(trimmed.slice(6)); } catch { continue; }

            switch (event.type) {
                case 'status':
                    removeThinking();
                    updateStatusBar(event.content);
                    addStep(event.content, 'running');
                    showThinkingWithText(event.content);
                    break;

                case 'tool_start':
                    removeThinking();
                    updateStatusBar(`Menjalankan ${getToolLabel(event.tool)}...`);
                    addStep(`Menggunakan ${getToolLabel(event.tool)}`, 'running');
                    showLiveToolCard(event.tool, event.params);
                    break;

                case 'tool_result':
                    completeLiveToolCard(event.tool, event.result, event.duration_ms, event.status);
                    markLastStepCompleted();
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
                    finalizeStepTracker();
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
                    finalizeStepTracker();
                    appendMessage('assistant', `Error: ${event.content}`);
                    break;
            }
        }
    }
}

function getToolLabel(toolName) {
    return TOOL_CONFIG[toolName]?.label || toolName;
}

function getToolIcon(toolName) {
    return TOOL_CONFIG[toolName]?.icon || 'ri-tools-line';
}

function getToolSubtitle(toolName, params) {
    if (!params) return '';
    switch (toolName) {
        case 'shell_tool':
            if (params.command) return `$ ${params.command}`;
            if (params.action === 'run_code') return `Menjalankan kode ${params.runtime || 'script'}`;
            return '';
        case 'file_tool':
            const op = params.operation || 'file';
            const path = params.path || params.directory || '';
            return `${op} ${path}`.trim();
        case 'search_tool':
            if (params.query) return `Mencari: "${params.query}"`;
            if (params.action === 'fetch') return `Fetching: ${params.url}`;
            return '';
        case 'browser_tool':
            const action = params.action || 'navigate';
            if (params.url) return `${action}: ${params.url}`;
            if (params.selector) return `${action}: ${params.selector}`;
            return action;
        case 'generate_tool':
            const mediaType = params.type || 'media';
            return `Membuat ${mediaType}: ${(params.prompt || '').substring(0, 60)}`;
        case 'slides_tool':
            const slideAction = params.action || 'create';
            return `${slideAction}: ${params.title || 'Presentasi'}`;
        case 'webdev_tool':
            const wdAction = params.action || 'init';
            return `${wdAction}: ${params.framework || params.name || 'project'}`;
        case 'schedule_tool':
            const schAction = params.action || 'create';
            return `${schAction}: ${params.name || 'task'}`;
        case 'message_tool':
            const msgType = params.type || 'info';
            return `[${msgType}] ${(params.content || '').substring(0, 50)}`;
        case 'skill_manager':
            const skAction = params.action || 'list';
            return `${skAction}: ${params.name || params.query || 'skills'}`;
        default:
            return JSON.stringify(params).substring(0, 60);
    }
}

function buildPreviewHTML(toolName, params) {
    switch (toolName) {
        case 'shell_tool': return buildTerminalPreview(params);
        case 'file_tool': return buildEditorPreview(params);
        case 'search_tool': return buildSearchPreview(params);
        case 'browser_tool': return buildBrowserPreview(params);
        case 'generate_tool': return buildGeneratePreview(params);
        case 'slides_tool': return buildSlidesPreview(params);
        case 'webdev_tool': return buildWebdevPreview(params);
        case 'schedule_tool': return buildSchedulePreview(params);
        case 'message_tool': return buildMessagePreview(params);
        case 'skill_manager': return buildSkillPreview(params);
        default: return `<div class="preview-generic">${escapeHtml(JSON.stringify(params, null, 2))}</div>`;
    }
}

function buildTerminalPreview(params) {
    const cmd = params.command || '';
    const code = params.code || '';
    const runtime = params.runtime || 'bash';

    if (code) {
        return `<div class="preview-terminal">
            <span class="prompt">${escapeHtml(runtime)} &gt; </span>
            <div class="output" id="termOutput">${escapeHtml(code)}</div>
            <div class="output term-live-output"></div>
        </div>`;
    }

    return `<div class="preview-terminal">
        <span class="prompt">$ </span>${escapeHtml(cmd)}
        <div class="output term-live-output" style="margin-top:4px;color:#6a737d">Menjalankan...</div>
    </div>`;
}

function buildEditorPreview(params) {
    const op = params.operation || 'read';
    const path = params.path || 'file';
    const content = params.content || params.old_text || '';
    const fileName = path.split('/').pop() || path;
    const ext = fileName.split('.').pop() || '';

    const fileIcons = {
        py: 'ri-python-line', js: 'ri-javascript-line', ts: 'ri-javascript-line',
        html: 'ri-html5-line', css: 'ri-css3-line', json: 'ri-braces-line',
        md: 'ri-markdown-line', txt: 'ri-file-text-line',
    };
    const fileIcon = fileIcons[ext] || 'ri-file-code-line';

    let editorContent = '';
    if (content && (op === 'write' || op === 'edit' || op === 'append')) {
        const lines = content.split('\n').slice(0, 15);
        editorContent = lines.map((line, i) => {
            const num = (params.start_line || 1) + i;
            const isHighlight = op === 'edit' || op === 'write';
            return `<div class="preview-editor-line ${isHighlight && i < 3 ? 'highlight' : ''}">
                <span class="line-num">${num}</span>
                <span class="line-code">${escapeHtml(line)}</span>
            </div>`;
        }).join('');
    } else {
        editorContent = `<div class="preview-editor-line">
            <span class="line-num">-</span>
            <span class="line-code" style="color:#6a737d">${op === 'read' ? 'Membaca file...' : op === 'delete' ? 'Menghapus...' : op === 'list' ? 'Memuat daftar...' : 'Memproses...'}</span>
        </div>`;
    }

    return `<div class="preview-editor">
        <div class="preview-editor-tabs">
            <div class="preview-editor-tab active"><i class="${fileIcon}" style="margin-right:4px;font-size:11px"></i>${escapeHtml(fileName)}</div>
        </div>
        <div class="preview-editor-content">${editorContent}</div>
    </div>`;
}

function buildSearchPreview(params) {
    const query = params.query || '';
    const url = params.url || '';

    if (url) {
        return `<div class="preview-search">
            <div class="preview-search-query">
                <i class="ri-link"></i>
                <span>Fetching: ${escapeHtml(url)}</span>
            </div>
            <div class="preview-search-results search-live-results">
                <div style="color:#6a737d;font-size:11px;padding:6px">Mengambil konten halaman...</div>
            </div>
        </div>`;
    }

    return `<div class="preview-search">
        <div class="preview-search-query">
            <i class="ri-search-line"></i>
            <span>${escapeHtml(query)}</span>
        </div>
        <div class="preview-search-results search-live-results">
            <div style="color:#6a737d;font-size:11px;padding:6px">Mencari di web...</div>
        </div>
    </div>`;
}

function buildBrowserPreview(params) {
    const action = params.action || 'navigate';
    const url = params.url || '';
    const selector = params.selector || '';

    let contentHTML = '';
    switch (action) {
        case 'navigate':
            contentHTML = `<div style="color:#6a737d;text-align:center;padding:20px">
                <i class="ri-loader-4-line" style="font-size:20px;display:block;margin-bottom:6px;animation:spin 1s linear infinite"></i>
                Memuat halaman...
            </div>`;
            break;
        case 'screenshot':
            contentHTML = `<div style="color:#6a737d;text-align:center;padding:20px">
                <i class="ri-camera-line" style="font-size:20px;display:block;margin-bottom:6px"></i>
                Mengambil screenshot...
            </div>`;
            break;
        case 'click':
            contentHTML = `<div style="color:#6a737d;padding:12px">
                <i class="ri-cursor-line"></i> Click: <code style="color:#58a6ff">${escapeHtml(selector)}</code>
            </div>`;
            break;
        case 'fill': case 'type':
            contentHTML = `<div style="color:#6a737d;padding:12px">
                <i class="ri-input-cursor-move"></i> ${action}: <code style="color:#58a6ff">${escapeHtml(selector)}</code>
                ${params.value ? `<br>Value: "${escapeHtml(params.value)}"` : ''}
            </div>`;
            break;
        case 'extract_text':
            contentHTML = `<div style="color:#6a737d;padding:12px">
                <i class="ri-file-text-line"></i> Mengekstrak teks halaman...
            </div>`;
            break;
        case 'extract_links':
            contentHTML = `<div style="color:#6a737d;padding:12px">
                <i class="ri-links-line"></i> Mengekstrak links...
            </div>`;
            break;
        case 'execute_js':
            contentHTML = `<div style="color:#6a737d;padding:12px;font-family:'JetBrains Mono',monospace;font-size:11px">
                <i class="ri-javascript-line"></i> ${escapeHtml((params.script || '').substring(0, 100))}
            </div>`;
            break;
        case 'scroll':
            contentHTML = `<div style="color:#6a737d;padding:12px">
                <i class="ri-arrow-${params.direction === 'up' ? 'up' : 'down'}-line"></i> Scroll ${params.direction || 'down'}
            </div>`;
            break;
        default:
            contentHTML = `<div style="color:#6a737d;padding:12px">${action}...</div>`;
    }

    return `<div class="preview-browser">
        <div class="preview-browser-bar">
            <div class="preview-browser-dots"><span></span><span></span><span></span></div>
            <div class="preview-browser-url">
                <i class="ri-lock-line"></i>
                <span>${escapeHtml(url || 'about:blank')}</span>
            </div>
        </div>
        <div class="preview-browser-content browser-live-content">${contentHTML}</div>
    </div>`;
}

function buildGeneratePreview(params) {
    const mediaType = params.type || 'media';
    const prompt = params.prompt || '';
    const style = params.style || '';

    const typeIcons = {
        image: 'ri-image-line', svg: 'ri-shapes-line', chart: 'ri-bar-chart-2-line',
        audio: 'ri-music-line', video: 'ri-video-line', document: 'ri-file-text-line',
    };
    const typeIcon = typeIcons[mediaType] || 'ri-magic-line';

    let details = '';
    if (params.width && params.height) details += `${params.width}x${params.height} `;
    if (style) details += `Style: ${style} `;
    if (params.format) details += `Format: ${params.format} `;
    if (params.chart_type) details += `Chart: ${params.chart_type} `;
    if (params.duration) details += `Duration: ${params.duration}s `;

    return `<div class="preview-generate">
        <div class="preview-generate-type">
            <i class="${typeIcon}"></i>
            <span>${escapeHtml(mediaType.toUpperCase())}</span>
        </div>
        <div class="preview-generate-prompt">"${escapeHtml(prompt)}"</div>
        ${details ? `<div style="font-size:10px;color:#6a737d;margin-top:6px">${escapeHtml(details)}</div>` : ''}
        <div class="preview-generate-output generate-live-output">
            <i class="ri-loader-4-line" style="animation:spin 1s linear infinite;margin-right:4px"></i>
            Generating...
        </div>
    </div>`;
}

function buildSlidesPreview(params) {
    const action = params.action || 'create';
    const title = params.title || 'Untitled';
    const slides = params.slides || [];

    let slidesHTML = '';
    if (slides.length > 0) {
        slidesHTML = slides.slice(0, 4).map((s, i) => `
            <div class="preview-slide-mini">
                <span class="preview-slide-mini-num">#${i + 1}</span>
                <h4>${escapeHtml(s.title || 'Slide ' + (i + 1))}</h4>
                <p>${escapeHtml((s.content || '').substring(0, 80))}</p>
            </div>
        `).join('');
    } else {
        slidesHTML = `<div style="color:#6a737d;font-size:11px;padding:6px;text-align:center">
            ${action === 'create' ? 'Membuat presentasi...' : action === 'export' ? 'Mengexport...' : 'Memproses...'}
        </div>`;
    }

    return `<div class="preview-slides">
        <div style="font-size:13px;font-weight:600;color:var(--text-primary);margin-bottom:8px">
            <i class="ri-slideshow-line" style="color:var(--tool-slides);margin-right:4px"></i>
            ${escapeHtml(title)}
        </div>
        <div class="slides-live-content">${slidesHTML}</div>
    </div>`;
}

function buildWebdevPreview(params) {
    const action = params.action || 'init';
    const framework = params.framework || '';
    const name = params.name || 'project';
    const packages = params.packages || [];

    const frameworkIcons = {
        react: 'ri-reactjs-line', vue: 'ri-vuejs-line', flask: 'ri-flask-line',
        express: 'ri-nodejs-line', nextjs: 'ri-nextjs-line', fastapi: 'ri-speed-line',
    };
    const fwIcon = frameworkIcons[framework] || 'ri-code-s-slash-line';

    let content = '';
    if (action === 'init') {
        content = `<div class="preview-webdev-files">
            <div class="preview-webdev-file"><i class="ri-folder-line"></i> ${escapeHtml(name)}/</div>
            <div class="preview-webdev-file"><i class="ri-file-line"></i> package.json</div>
            <div class="preview-webdev-file"><i class="ri-folder-open-line"></i> src/</div>
            <div style="color:#6a737d;font-size:10px;margin-top:4px">Scaffolding project...</div>
        </div>`;
    } else if (action === 'install_deps' || action === 'add_dep') {
        content = `<div class="preview-webdev-files">
            ${packages.map(p => `<div class="preview-webdev-file"><i class="ri-download-line"></i> ${escapeHtml(p)}</div>`).join('')}
            <div style="color:#6a737d;font-size:10px;margin-top:4px">Installing dependencies...</div>
        </div>`;
    } else if (action === 'build') {
        content = `<div style="color:#6a737d;font-size:11px">
            <i class="ri-hammer-line"></i> Building project...
        </div>`;
    } else {
        content = `<div style="color:#6a737d;font-size:11px">${action}...</div>`;
    }

    return `<div class="preview-webdev">
        ${framework ? `<div class="preview-webdev-framework"><i class="${fwIcon}"></i><span>${escapeHtml(framework)}</span></div>` : ''}
        ${content}
    </div>`;
}

function buildSchedulePreview(params) {
    const action = params.action || 'create';
    const name = params.name || '';

    const rows = [];
    if (name) rows.push(['Nama', name]);
    if (params.interval) rows.push(['Interval', `${params.interval}s`]);
    if (params.cron_expression) rows.push(['Cron', params.cron_expression]);
    if (params.delay_seconds) rows.push(['Delay', `${params.delay_seconds}s`]);
    if (params.callback) rows.push(['Callback', params.callback]);
    if (params.task_id) rows.push(['Task ID', params.task_id]);

    if (rows.length === 0) {
        rows.push(['Action', action]);
    }

    return `<div class="preview-schedule">
        <div class="preview-schedule-info">
            ${rows.map(([label, value]) => `
                <div class="preview-schedule-row">
                    <span class="label">${escapeHtml(label)}</span>
                    <span class="value">${escapeHtml(value)}</span>
                </div>
            `).join('')}
        </div>
    </div>`;
}

function buildMessagePreview(params) {
    const content = params.content || '';
    const msgType = params.type || 'info';

    return `<div class="preview-message">
        <div class="preview-message-bubble">
            <div class="preview-message-type ${msgType}">${escapeHtml(msgType.toUpperCase())}</div>
            <div>${escapeHtml(content)}</div>
        </div>
    </div>`;
}

function buildSkillPreview(params) {
    const action = params.action || 'list';
    const name = params.name || '';

    let content = '';
    switch (action) {
        case 'list':
            content = '<div style="color:#6a737d;font-size:11px">Memuat daftar skills...</div>';
            break;
        case 'info':
            content = `<div style="color:#6a737d;font-size:11px">Info skill: ${escapeHtml(name)}</div>`;
            break;
        case 'create':
            content = `<div style="color:#6a737d;font-size:11px">Membuat skill: ${escapeHtml(name)}</div>
                ${params.description ? `<div style="font-size:10px;color:#484f58;margin-top:4px">${escapeHtml(params.description)}</div>` : ''}
                ${params.capabilities ? `<div style="font-size:10px;color:#484f58;margin-top:2px">Capabilities: ${escapeHtml(params.capabilities.join(', '))}</div>` : ''}`;
            break;
        case 'run_script':
            content = `<div style="color:#6a737d;font-size:11px">Menjalankan script: ${escapeHtml(params.script || name)}</div>`;
            break;
        case 'search':
            content = `<div style="color:#6a737d;font-size:11px">Mencari: "${escapeHtml(params.query || '')}"</div>`;
            break;
        default:
            content = `<div style="color:#6a737d;font-size:11px">${escapeHtml(action)}: ${escapeHtml(name)}</div>`;
    }

    return `<div class="preview-skill">
        ${name ? `<div class="preview-skill-name"><i class="ri-lightbulb-line"></i><span>${escapeHtml(name)}</span></div>` : ''}
        <div class="preview-skill-action">${content}</div>
    </div>`;
}

function showLiveToolCard(toolName, params) {
    removeThinking();
    const container = document.getElementById('messagesContainer');
    const config = TOOL_CONFIG[toolName] || { icon: 'ri-tools-line', label: toolName, color: 'var(--accent)' };

    const cardId = 'liveCard_' + Date.now();
    const row = document.createElement('div');
    row.className = 'message-row assistant';
    row.id = cardId;

    const subtitle = getToolSubtitle(toolName, params);
    const previewHTML = buildPreviewHTML(toolName, params);

    row.innerHTML = `
        <div class="message-avatar"><i class="ri-robot-2-fill"></i></div>
        <div class="live-tool-card running" data-tool="${toolName}">
            <div class="live-tool-header" onclick="toggleToolPreview(this)">
                <div class="live-tool-icon ${toolName}">
                    <i class="${config.icon}"></i>
                </div>
                <div class="live-tool-info">
                    <div class="live-tool-title">${escapeHtml(config.label)}</div>
                    <div class="live-tool-subtitle">${escapeHtml(subtitle)}</div>
                </div>
                <div class="live-tool-status">
                    <div class="live-tool-status-dot running"></div>
                    <span class="live-tool-status-text">Running</span>
                </div>
            </div>
            <div class="live-tool-progress">
                <div class="live-tool-progress-bar running"></div>
            </div>
            <div class="live-tool-preview">
                ${previewHTML}
            </div>
            <div class="live-tool-footer">
                <div class="live-tool-footer-left">
                    <span class="live-tool-duration">0ms</span>
                </div>
                <button class="live-tool-toggle" onclick="event.stopPropagation();toggleToolPreview(this.closest('.live-tool-card').querySelector('.live-tool-header'))">
                    <i class="ri-arrow-up-s-line"></i>
                </button>
            </div>
        </div>
    `;

    container.appendChild(row);
    activeToolCards[toolName] = cardId;
    scrollToBottom();

    const startTime = Date.now();
    const durationEl = row.querySelector('.live-tool-duration');
    const timer = setInterval(() => {
        const elapsed = Date.now() - startTime;
        if (durationEl) durationEl.textContent = formatDuration(elapsed);
        if (!document.getElementById(cardId)) clearInterval(timer);
    }, 100);
    row._timer = timer;
}

function completeLiveToolCard(toolName, result, durationMs, status) {
    const cardId = activeToolCards[toolName];
    if (!cardId) {
        appendCompletedToolCard({ tool: toolName, result, duration_ms: durationMs, status });
        return;
    }

    const row = document.getElementById(cardId);
    if (!row) return;

    if (row._timer) clearInterval(row._timer);

    const card = row.querySelector('.live-tool-card');
    if (card) {
        card.classList.remove('running');
        card.classList.add('completed');
    }

    const dot = row.querySelector('.live-tool-status-dot');
    if (dot) {
        dot.classList.remove('running');
        dot.classList.add(status === 'success' ? 'success' : 'error');
    }

    const statusText = row.querySelector('.live-tool-status-text');
    if (statusText) statusText.textContent = status === 'success' ? 'Done' : 'Error';

    const progressBar = row.querySelector('.live-tool-progress-bar');
    if (progressBar) {
        progressBar.classList.remove('running');
        progressBar.style.width = '100%';
        progressBar.style.background = status === 'success' ? 'var(--success)' : 'var(--error)';
    }

    const durationEl = row.querySelector('.live-tool-duration');
    if (durationEl) durationEl.textContent = formatDuration(durationMs);

    updatePreviewWithResult(row, toolName, result);

    delete activeToolCards[toolName];
    scrollToBottom();
}

function updatePreviewWithResult(row, toolName, result) {
    if (!result) return;
    const cleanResult = result.substring(0, 1500);

    switch (toolName) {
        case 'shell_tool': {
            const outputEl = row.querySelector('.term-live-output');
            if (outputEl) {
                outputEl.style.color = '#c9d1d9';
                outputEl.textContent = cleanResult;
            }
            break;
        }
        case 'file_tool': {
            const editorContent = row.querySelector('.preview-editor-content');
            if (editorContent) {
                const lines = cleanResult.split('\n').slice(0, 20);
                editorContent.innerHTML = lines.map((line, i) =>
                    `<div class="preview-editor-line">
                        <span class="line-num">${i + 1}</span>
                        <span class="line-code">${escapeHtml(line)}</span>
                    </div>`
                ).join('');
            }
            break;
        }
        case 'search_tool': {
            const resultsEl = row.querySelector('.search-live-results');
            if (resultsEl) {
                try {
                    const items = parseSearchResults(cleanResult);
                    if (items.length > 0) {
                        resultsEl.innerHTML = items.slice(0, 5).map(item =>
                            `<div class="preview-search-item">
                                <div class="preview-search-item-title">${escapeHtml(item.title)}</div>
                                <div class="preview-search-item-url">${escapeHtml(item.url)}</div>
                                <div class="preview-search-item-snippet">${escapeHtml(item.snippet)}</div>
                            </div>`
                        ).join('');
                    } else {
                        resultsEl.innerHTML = `<div style="font-size:11px;color:#8b949e;padding:4px">${escapeHtml(cleanResult.substring(0, 300))}</div>`;
                    }
                } catch {
                    resultsEl.innerHTML = `<div style="font-size:11px;color:#8b949e;padding:4px">${escapeHtml(cleanResult.substring(0, 300))}</div>`;
                }
            }
            break;
        }
        case 'browser_tool': {
            const contentEl = row.querySelector('.browser-live-content');
            if (contentEl) {
                contentEl.innerHTML = `<div style="font-size:11px;color:#8b949e;padding:6px;white-space:pre-wrap;word-break:break-all">${escapeHtml(cleanResult.substring(0, 500))}</div>`;
            }
            break;
        }
        case 'generate_tool': {
            const outputEl = row.querySelector('.generate-live-output');
            if (outputEl) {
                outputEl.innerHTML = `<i class="ri-check-line" style="color:var(--success);margin-right:4px"></i>${escapeHtml(cleanResult.substring(0, 200))}`;
            }
            break;
        }
        case 'slides_tool': {
            const contentEl = row.querySelector('.slides-live-content');
            if (contentEl) {
                contentEl.innerHTML = `<div style="font-size:11px;color:#8b949e;padding:4px">${escapeHtml(cleanResult.substring(0, 300))}</div>`;
            }
            break;
        }
        default: {
            const preview = row.querySelector('.live-tool-preview');
            if (preview) {
                const existingGeneric = preview.querySelector('.preview-generic');
                if (existingGeneric) {
                    existingGeneric.textContent = cleanResult;
                } else {
                    const liveEls = preview.querySelectorAll('[style*="color:#6a737d"]');
                    liveEls.forEach(el => {
                        el.textContent = cleanResult.substring(0, 300);
                        el.style.color = '#8b949e';
                    });
                }
            }
        }
    }
}

function parseSearchResults(text) {
    const results = [];
    const titleRegex = /(?:\d+\.\s*)?(.+?)(?:\n|$)/g;
    const urlRegex = /https?:\/\/[^\s)]+/g;
    const urls = text.match(urlRegex) || [];

    const lines = text.split('\n').filter(l => l.trim());
    let current = null;

    for (const line of lines) {
        const trimmed = line.trim();
        const urlMatch = trimmed.match(/https?:\/\/[^\s)]+/);

        if (trimmed.match(/^\d+[\.\)]\s/) || (trimmed.length > 10 && !urlMatch && !trimmed.startsWith('-'))) {
            if (current && current.title) results.push(current);
            current = { title: trimmed.replace(/^\d+[\.\)]\s*/, ''), url: '', snippet: '' };
        } else if (urlMatch && current) {
            current.url = urlMatch[0];
        } else if (current && trimmed.length > 5) {
            current.snippet += (current.snippet ? ' ' : '') + trimmed;
        }
    }
    if (current && current.title) results.push(current);

    return results;
}

function appendCompletedToolCard(toolExec) {
    const container = document.getElementById('messagesContainer');
    const config = TOOL_CONFIG[toolExec.tool] || { icon: 'ri-tools-line', label: toolExec.tool, color: 'var(--accent)' };

    const row = document.createElement('div');
    row.className = 'message-row assistant';

    const subtitle = getToolSubtitle(toolExec.tool, toolExec.params || {});
    const result = toolExec.result || '';

    row.innerHTML = `
        <div class="message-avatar"><i class="ri-robot-2-fill"></i></div>
        <div class="live-tool-card completed" data-tool="${toolExec.tool}">
            <div class="live-tool-header" onclick="toggleToolPreview(this)">
                <div class="live-tool-icon ${toolExec.tool}">
                    <i class="${config.icon}"></i>
                </div>
                <div class="live-tool-info">
                    <div class="live-tool-title">${escapeHtml(config.label)}</div>
                    <div class="live-tool-subtitle">${escapeHtml(subtitle)}</div>
                </div>
                <div class="live-tool-status">
                    <div class="live-tool-status-dot ${toolExec.status === 'success' ? 'success' : 'error'}"></div>
                    <span class="live-tool-status-text">${toolExec.status === 'success' ? 'Done' : 'Error'}</span>
                </div>
            </div>
            <div class="live-tool-preview collapsed">
                <div class="preview-generic">${escapeHtml(result.substring(0, 1000))}</div>
            </div>
            <div class="live-tool-footer">
                <div class="live-tool-footer-left">
                    <span class="live-tool-duration">${formatDuration(toolExec.duration_ms || 0)}</span>
                </div>
                <button class="live-tool-toggle" onclick="event.stopPropagation();toggleToolPreview(this.closest('.live-tool-card').querySelector('.live-tool-header'))">
                    <i class="ri-arrow-down-s-line"></i>
                </button>
            </div>
        </div>
    `;

    container.appendChild(row);
}

function toggleToolPreview(headerEl) {
    const card = headerEl.closest('.live-tool-card');
    const preview = card.querySelector('.live-tool-preview');
    const toggleIcon = card.querySelector('.live-tool-toggle i');

    if (preview.classList.contains('collapsed')) {
        preview.classList.remove('collapsed');
        preview.classList.add('expanded');
        if (toggleIcon) toggleIcon.className = 'ri-arrow-up-s-line';
    } else if (preview.classList.contains('expanded')) {
        preview.classList.remove('expanded');
        preview.classList.add('collapsed');
        if (toggleIcon) toggleIcon.className = 'ri-arrow-down-s-line';
    } else {
        preview.classList.add('collapsed');
        if (toggleIcon) toggleIcon.className = 'ri-arrow-down-s-line';
    }
}

function createStepTracker() {
    const container = document.getElementById('messagesContainer');
    const existing = document.getElementById('stepTracker');
    if (existing) existing.remove();

    const tracker = document.createElement('div');
    tracker.className = 'step-tracker';
    tracker.id = 'stepTracker';
    tracker.innerHTML = `
        <div class="step-tracker-title" onclick="toggleStepList()">
            <i class="ri-list-check-2"></i>
            <span>Langkah-langkah</span>
            <span class="step-count" id="stepCount">0 langkah</span>
        </div>
        <div class="step-list" id="stepList"></div>
    `;
    container.appendChild(tracker);
    return tracker;
}

function addStep(text, status = 'pending') {
    const list = document.getElementById('stepList');
    if (!list) return;

    const existingRunning = list.querySelectorAll('.step-item.running');
    existingRunning.forEach(el => {
        el.classList.remove('running');
        el.classList.add('completed');
        const icon = el.querySelector('.step-item-icon');
        if (icon) {
            icon.classList.remove('running');
            icon.classList.add('completed');
            icon.innerHTML = '<i class="ri-check-line"></i>';
        }
        const time = el.querySelector('.step-item-time');
        if (time && !time.textContent) {
            time.textContent = 'done';
        }
    });

    const step = document.createElement('div');
    step.className = `step-item ${status}`;

    const iconClass = status === 'completed' ? 'completed' : status === 'running' ? 'running' : 'pending';
    const iconHTML = status === 'completed' ? '<i class="ri-check-line"></i>' :
                     status === 'running' ? '<i class="ri-loader-4-line"></i>' :
                     '<i class="ri-circle-line"></i>';

    step.innerHTML = `
        <div class="step-item-icon ${iconClass}">${iconHTML}</div>
        <span class="step-item-text">${escapeHtml(text)}</span>
        <span class="step-item-time"></span>
    `;

    list.appendChild(step);
    updateStepCount();
    scrollToBottom();
}

function markLastStepCompleted() {
    const list = document.getElementById('stepList');
    if (!list) return;

    const runningSteps = list.querySelectorAll('.step-item.running');
    runningSteps.forEach(step => {
        step.classList.remove('running');
        step.classList.add('completed');
        const icon = step.querySelector('.step-item-icon');
        if (icon) {
            icon.classList.remove('running');
            icon.classList.add('completed');
            icon.innerHTML = '<i class="ri-check-line"></i>';
        }
    });
    updateStepCount();
}

function updateStepCount() {
    const list = document.getElementById('stepList');
    const countEl = document.getElementById('stepCount');
    if (!list || !countEl) return;

    const total = list.children.length;
    const completed = list.querySelectorAll('.step-item.completed').length;
    countEl.textContent = `${completed}/${total} selesai`;
}

function finalizeStepTracker() {
    markLastStepCompleted();
    const tracker = document.getElementById('stepTracker');
    if (tracker) {
        tracker.removeAttribute('id');
    }
}

function toggleStepList() {
    const list = document.getElementById('stepList');
    if (list) list.style.display = list.style.display === 'none' ? '' : 'none';
}

function formatDuration(ms) {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
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
    if (bubble) bubble.innerHTML = formatContent(content) + '<span class="cursor-blink">|</span>';
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

function removeThinking() {
    document.getElementById('thinkingIndicator')?.remove();
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
        row.innerHTML = `<div class="message-bubble">${formatContent(content)}</div>`;
    }

    container.appendChild(row);
    scrollToBottom();
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
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) =>
        `<div class="tool-card"><div class="tool-card-header"><i class="ri-code-line"></i><span>${lang || 'code'}</span></div><div class="tool-card-result">${code}</div></div>`
    );
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

async function loadModels(category = null) {
    try {
        const url = category ? `/api/models?category=${category}` : '/api/models';
        const data = await api(url);
        allModels = data.models || [];
        currentModel = data.current ? data.current.model : null;

        const nameEl = document.getElementById('currentModelName');
        if (nameEl && data.current) nameEl.textContent = data.current.name || data.current.model;

        renderCategoryTabs(data.categories || {}, category);
        renderModelList(allModels, data.current ? data.current.model : null);
        renderModelStats(data);
    } catch (err) {
        console.error('Failed to load models:', err);
    }
}

function renderCategoryTabs(categories, active) {
    const container = document.getElementById('modelCategoryTabs');
    if (!container) return;
    const allTab = `<button class="model-cat-tab ${!active ? 'active' : ''}" onclick="filterModels(null)">Semua</button>`;
    const tabs = Object.entries(categories).map(([key, desc]) =>
        `<button class="model-cat-tab ${active === key ? 'active' : ''}" onclick="filterModels('${key}')" title="${escapeHtml(desc)}">${key}</button>`
    ).join('');
    container.innerHTML = allTab + tabs;
}

function renderModelList(models, activeModel) {
    const container = document.getElementById('modelList');
    if (!container) return;

    const categoryIcons = {
        thinking: 'ri-brain-line', reasoning: 'ri-lightbulb-flash-line',
        general: 'ri-sparkling-line', research: 'ri-search-eye-line', labs: 'ri-flask-line',
    };

    container.innerHTML = models.map(m => `
        <div class="model-item ${m.id === activeModel ? 'active' : ''}" onclick="switchModel('${m.id}')">
            <div class="model-item-icon ${m.category}">
                <i class="${categoryIcons[m.category] || 'ri-cpu-line'}"></i>
            </div>
            <div class="model-item-info">
                <div class="model-item-name">${escapeHtml(m.name)}</div>
                <div class="model-item-desc">${escapeHtml(m.description)}</div>
            </div>
            <span class="model-item-badge">${m.id === activeModel ? 'Active' : m.category}</span>
        </div>
    `).join('');
}

function renderModelStats(data) {
    const container = document.getElementById('modelStats');
    if (!container) return;
    container.textContent = `${(data.models || []).length} model tersedia`;
}

function toggleModelDropdown() {
    const dropdown = document.getElementById('modelDropdown');
    if (!dropdown) return;
    if (dropdown.classList.contains('hidden')) {
        dropdown.classList.remove('hidden');
        loadModels(activeCategory);
    } else {
        dropdown.classList.add('hidden');
    }
}

function filterModels(category) {
    activeCategory = category;
    loadModels(category);
}

async function switchModel(modelId) {
    try {
        const data = await api('/api/models/switch', {
            method: 'POST',
            body: JSON.stringify({ model: modelId }),
        });
        if (data.ok && data.current) {
            currentModel = data.current.model;
            const nameEl = document.getElementById('currentModelName');
            if (nameEl) nameEl.textContent = data.current.name || data.current.model;
            document.getElementById('modelDropdown')?.classList.add('hidden');
            updateStatusBar(`Model: ${data.current.name}`);
            loadModels(activeCategory);
        }
    } catch (err) {
        console.error('Failed to switch model:', err);
    }
}

document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('modelDropdown');
    const btn = document.getElementById('modelSelectorBtn');
    if (dropdown && btn && !dropdown.contains(e.target) && !btn.contains(e.target)) {
        dropdown.classList.add('hidden');
    }
});

document.addEventListener('DOMContentLoaded', () => {
    loadSessions();
    loadModels();
    document.getElementById('messageInput').focus();
});
