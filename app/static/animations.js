/* AgriTogo — Animations & Dynamic Effects */

// Animated counter for metric values
function animateCounters() {
    document.querySelectorAll('.metric-card .value, .metric-card-sm .metric-value').forEach(function(el) {
        var text = el.textContent.trim();
        var match = text.match(/^([\-]?[\d,]+\.?\d*)/);
        if (!match) return;
        if (el.dataset.animated) return;
        el.dataset.animated = '1';

        var target = parseFloat(match[1].replace(/,/g, ''));
        var suffix = text.replace(match[1], '');
        var duration = 800;
        var start = performance.now();
        var startVal = 0;

        function step(now) {
            var progress = Math.min((now - start) / duration, 1);
            var ease = 1 - Math.pow(1 - progress, 3); // easeOutCubic
            var current = startVal + (target - startVal) * ease;

            if (Number.isInteger(target) && Math.abs(target) > 10) {
                el.textContent = Math.round(current).toLocaleString() + suffix;
            } else {
                el.textContent = current.toFixed(target % 1 === 0 ? 0 : Math.min(4, (target.toString().split('.')[1] || '').length)) + suffix;
            }

            if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    });
}

// Animate bars width on load
function animateBars() {
    document.querySelectorAll('.bar').forEach(function(bar) {
        if (bar.dataset.animated) return;
        bar.dataset.animated = '1';
        var targetWidth = bar.style.width;
        bar.style.width = '0px';
        bar.style.transition = 'width 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
        requestAnimationFrame(function() {
            bar.style.width = targetWidth;
        });
    });
}

// Stagger animation for table rows
function animateTableRows() {
    document.querySelectorAll('tbody').forEach(function(tbody) {
        if (tbody.dataset.animated) return;
        tbody.dataset.animated = '1';
        var rows = tbody.querySelectorAll('tr');
        rows.forEach(function(row, i) {
            row.style.opacity = '0';
            row.style.transform = 'translateY(4px)';
            setTimeout(function() {
                row.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
                row.style.opacity = '1';
                row.style.transform = 'translateY(0)';
            }, i * 40);
        });
    });
}

// Typing effect for agent responses
function typewriterEffect(el) {
    if (!el || el.dataset.typed) return;
    el.dataset.typed = '1';
    var text = el.innerHTML;
    el.innerHTML = '';
    el.style.visibility = 'visible';
    var i = 0;
    var speed = 8; // ms per character
    function type() {
        if (i < text.length) {
            // Handle HTML tags - add them instantly
            if (text[i] === '<') {
                var end = text.indexOf('>', i);
                el.innerHTML += text.substring(i, end + 1);
                i = end + 1;
            } else {
                el.innerHTML += text[i];
                i++;
            }
            setTimeout(type, speed);
        }
    }
    type();
}

// Smooth tab transitions
function showTab(name) {
    document.querySelectorAll('.tab-content').forEach(function(t) {
        if (t.classList.contains('active')) {
            t.style.opacity = '0';
            t.style.transform = 'translateY(4px)';
            setTimeout(function() {
                t.classList.remove('active');
                t.style.opacity = '';
                t.style.transform = '';
                var target = document.getElementById('tab-' + name);
                if (target) {
                    target.classList.add('active');
                    // Re-trigger animations in new tab
                    setTimeout(function() {
                        animateCounters();
                        animateBars();
                        animateTableRows();
                    }, 50);
                }
            }, 150);
        }
    });
    document.querySelectorAll('.topnav-links a').forEach(function(a) { a.classList.remove('active'); });
    if (event && event.target) event.target.classList.add('active');
}

// Run animations on HTMX content swap
document.body.addEventListener('htmx:afterSwap', function(e) {
    setTimeout(function() {
        animateCounters();
        animateBars();
        animateTableRows();
    }, 50);

    // Typewriter on agent interpretation
    var interp = e.detail.target.querySelector('.response-body');
    if (interp && e.detail.target.closest('.agent-interpretation')) {
        typewriterEffect(interp);
    }

    // Auto-scroll chat
    if (e.detail.target.id === 'chat-messages') {
        e.detail.target.scrollTop = e.detail.target.scrollHeight;
        var form = document.querySelector('.chat-form');
        if (form) form.reset();
    }
});

// Initial page load animations
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(animateCounters, 200);
    setTimeout(animateBars, 300);
    setTimeout(animateTableRows, 400);
});


// Analyst sub-panel navigation
function showAnalystPanel(name) {
    document.querySelectorAll('.analyst-panel').forEach(function(p) {
        p.classList.remove('active');
    });
    document.querySelectorAll('.analyst-tab').forEach(function(t) {
        t.classList.remove('active');
    });
    var panel = document.getElementById('analyst-' + name);
    if (panel) panel.classList.add('active');
    if (event && event.target) event.target.classList.add('active');
}


// ── Advanced Chatbot Functions ──

// Copy bubble content to clipboard
function copyBubble(btn) {
    var bubble = btn.closest('.chat-bubble');
    var content = bubble.querySelector('.bubble-content');
    if (content) {
        navigator.clipboard.writeText(content.textContent).then(function() {
            btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
            setTimeout(function() {
                btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>';
            }, 1500);
        });
    }
}

// Export chat as text file
function exportChat() {
    var messages = document.getElementById('chat-messages');
    if (!messages) return;
    var bubbles = messages.querySelectorAll('.chat-bubble');
    var text = 'AgriTogo Chat Export\n' + '='.repeat(40) + '\n\n';
    bubbles.forEach(function(b) {
        var sender = b.querySelector('.bubble-sender');
        var time = b.querySelector('.bubble-time');
        var content = b.querySelector('.bubble-content');
        text += (sender ? sender.textContent : '') + (time ? ' [' + time.textContent + ']' : '') + ':\n';
        text += (content ? content.textContent : '') + '\n\n';
    });
    var blob = new Blob([text], {type: 'text/plain'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'agritogo_chat_' + new Date().toISOString().slice(0,10) + '.txt';
    a.click();
}

// Auto-scroll and reset on new messages
document.body.addEventListener('htmx:afterSwap', function(e) {
    if (e.detail.target.id === 'chat-messages') {
        e.detail.target.scrollTop = e.detail.target.scrollHeight;
        var form = document.getElementById('chat-form');
        if (form) form.reset();
        var input = document.getElementById('chat-input');
        if (input) input.focus();
    }
    // Re-run animations on any swap
    setTimeout(function() {
        animateCounters();
        animateBars();
    }, 50);
});

// Enter to send, Shift+Enter for newline
document.addEventListener('keydown', function(e) {
    var input = document.getElementById('chat-input');
    if (e.key === 'Enter' && !e.shiftKey && document.activeElement === input) {
        e.preventDefault();
        var form = document.getElementById('chat-form');
        if (form && input.value.trim()) {
            // Check if Puter mode
            var model = document.querySelector('input[name="model"]:checked');
            if (model && model.value === 'puter') {
                handlePuterChat(input.value.trim());
                input.value = '';
            } else {
                form.requestSubmit();
            }
        }
    }
});

// Puter.js Claude handler
function handlePuterChat(msg) {
    var cd = document.getElementById('chat-messages');
    if (!cd) return;
    var now = new Date().toTimeString().slice(0,5);

    cd.innerHTML += '<div class="chat-bubble bubble-user"><div class="bubble-meta"><span class="bubble-sender">You</span><span class="bubble-time">' + now + '</span></div><div class="bubble-content">' + escapeHtml(msg) + '</div></div>';

    var typingId = 'puter-' + Date.now();
    cd.innerHTML += '<div class="chat-bubble bubble-agent" id="' + typingId + '"><div class="bubble-meta"><span class="bubble-sender">AgriTogo [Claude]</span><span class="bubble-time">' + now + '</span></div><div class="bubble-content"><span class="typing-dots"><span></span><span></span><span></span></span></div></div>';
    cd.scrollTop = cd.scrollHeight;

    var SP = document.getElementById('puter-system-prompt').value;
    puter.ai.chat([{role:'system',content:SP},{role:'user',content:msg}],{model:'claude-sonnet-4-6'}).then(function(r) {
        var text = r.message.content[0].text;
        var el = document.getElementById(typingId);
        if (el) {
            el.querySelector('.bubble-content').innerHTML = text.replace(/\n/g,'<br>');
            el.innerHTML += '<div class="bubble-actions"><button class="btn-icon-sm" onclick="copyBubble(this)" title="Copy"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg></button></div>';
        }
        cd.scrollTop = cd.scrollHeight;
    }).catch(function(err) {
        var el = document.getElementById(typingId);
        if (el) el.querySelector('.bubble-content').textContent = 'Error: ' + err;
    });
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// Intercept HTMX chat for Puter mode
document.addEventListener('htmx:configRequest', function(e) {
    if (e.detail.path === '/chat') {
        var model = document.querySelector('input[name="model"]:checked');
        if (model && model.value === 'puter') {
            e.preventDefault();
            var input = document.getElementById('chat-input');
            if (input && input.value.trim()) {
                handlePuterChat(input.value.trim());
                input.value = '';
            }
        }
    }
});
