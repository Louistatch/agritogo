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
