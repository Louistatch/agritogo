/* AgriTogo — Agent Thought Stream v1.0
 * Real-time SSE visualization of agent reasoning
 * 2026 pro animation style
 */

const ThoughtStream = {
    _es: null,
    _panel: null,
    _active: false,

    // ── Icons per thought type ────────────────────────────
    icons: {
        thinking:    '◈',
        tool_call:   '⟳',
        tool_result: '◉',
        decision:    '◆',
        done:        '✓',
        connected:   '◎',
        ping:        null,
    },

    colors: {
        thinking:    '#4f8cff',
        tool_call:   '#f59e0b',
        tool_result: '#22c55e',
        decision:    '#a78bfa',
        done:        '#22d3ee',
        connected:   '#5c6078',
    },

    labels: {
        thinking:    'Thinking',
        tool_call:   'Tool Call',
        tool_result: 'Result',
        decision:    'Decision',
        done:        'Complete',
    },

    init() {
        this._panel = document.getElementById('thought-panel');
        if (!this._panel) return;
        this.connect();
    },

    connect() {
        if (this._es) this._es.close();
        this._es = new EventSource('/thoughts');

        this._es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'ping') return;
                this.render(data);
            } catch {}
        };

        this._es.onerror = () => {
            setTimeout(() => this.connect(), 3000);
        };
    },

    render(event) {
        if (!this._panel) return;
        if (event.type === 'connected') return;

        const icon = this.icons[event.type] || '·';
        const color = this.colors[event.type] || '#5c6078';
        const label = this.labels[event.type] || event.type;
        const ts = new Date(event.ts * 1000).toTimeString().slice(0, 8);

        // Show panel
        this._panel.style.display = 'block';
        this._panel.classList.add('thought-active');

        // Create thought item
        const item = document.createElement('div');
        item.className = `thought-item thought-${event.type}`;
        item.innerHTML = `
            <div class="thought-header">
                <span class="thought-icon" style="color:${color}">${icon}</span>
                <span class="thought-agent">${event.agent || 'Agent'}</span>
                <span class="thought-label" style="color:${color}">${label}</span>
                <span class="thought-ts">${ts}</span>
            </div>
            <div class="thought-content">${this._escape(event.content || '')}</div>
        `;

        // Animate in
        item.style.opacity = '0';
        item.style.transform = 'translateX(-8px)';
        this._panel.querySelector('.thought-list').appendChild(item);

        requestAnimationFrame(() => {
            item.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
            item.style.opacity = '1';
            item.style.transform = 'translateX(0)';
        });

        // Auto-scroll
        this._panel.querySelector('.thought-list').scrollTop = 99999;

        // Pulse the indicator
        const indicator = document.getElementById('thought-indicator');
        if (indicator) {
            indicator.classList.add('pulsing');
            setTimeout(() => indicator.classList.remove('pulsing'), 600);
        }

        // On done: fade out panel after 4s
        if (event.type === 'done') {
            setTimeout(() => {
                this._panel.classList.add('thought-fading');
                setTimeout(() => {
                    this._panel.classList.remove('thought-active', 'thought-fading');
                }, 800);
            }, 4000);
        }
    },

    clear() {
        if (this._panel) {
            const list = this._panel.querySelector('.thought-list');
            if (list) list.innerHTML = '';
        }
    },

    _escape(str) {
        return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    },
};

// Auto-init
document.addEventListener('DOMContentLoaded', () => ThoughtStream.init());

// Clear on new query
document.body.addEventListener('htmx:beforeRequest', (e) => {
    if (['/chat', '/engine', '/ml/interpret'].includes(e.detail.path)) {
        ThoughtStream.clear();
    }
});
