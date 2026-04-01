/* AgriTogo — Agent OS v1.0
 * Object-driven UI. Charts react to agents, not users.
 * 20 dynamic effects. Bloomberg-grade.
 */

// ── Agent OS Core ─────────────────────────────────────────
const AgentOS = {
    _state: {
        prices: {},        // {produit: [{date,prix}]}
        risk: null,
        kpi: null,
        seg: null,
        forecast: {},
        anomalies: [],
        userProfile: { audience: 'analyst', bandwidth: 'high' },
        activeCharts: new Set(),
        lastUpdate: null,
    },
    _hooks: {},   // event → [callbacks]
    _cache: {},

    // ── Event Bus ─────────────────────────────────────────
    on(event, cb) {
        if (!this._hooks[event]) this._hooks[event] = [];
        this._hooks[event].push(cb);
    },
    emit(event, data) {
        (this._hooks[event] || []).forEach(cb => cb(data));
    },

    // ── RAG: top-k + anomaly + recent ─────────────────────
    rag(data, k=10) {
        if (!Array.isArray(data) || !data.length) return data;
        const sorted = [...data].sort((a,b) => b.prix - a.prix);
        const topK = sorted.slice(0, k);
        const anomalies = this._detectAnomalies(data);
        const recent = data.slice(-5);
        const merged = [...new Map([...topK,...anomalies,...recent].map(d=>[d.date,d])).values()];
        return merged.sort((a,b) => a.date.localeCompare(b.date));
    },

    _detectAnomalies(data) {
        if (data.length < 5) return [];
        const prices = data.map(d => d.prix);
        const mean = prices.reduce((a,b)=>a+b,0)/prices.length;
        const std = Math.sqrt(prices.map(p=>(p-mean)**2).reduce((a,b)=>a+b,0)/prices.length);
        return data.filter(d => Math.abs(d.prix - mean) > 2 * std);
    },

    // ── Effect 1: Predictive Rendering ────────────────────
    predictiveRender(chartId, historicalData) {
        if (!historicalData?.length) return;
        const prices = historicalData.map(d => d.prix);
        const n = prices.length;
        // Simple linear extrapolation + noise
        const slope = (prices[n-1] - prices[Math.max(0,n-7)]) / 7;
        const predicted = Array.from({length:7}, (_,i) => ({
            date: 'P+'+(i+1),
            prix: Math.round(prices[n-1] + slope*(i+1) + (Math.random()-0.5)*slope*2),
            predicted: true,
        }));
        this.emit('predictive:ready', {chartId, predicted, historical: historicalData});
    },

    // ── Effect 2: Anomaly Highlight ───────────────────────
    highlightAnomalies(chartId, data) {
        const anomalies = this._detectAnomalies(data);
        if (anomalies.length) {
            this.emit('anomaly:detected', {chartId, anomalies, count: anomalies.length});
        }
        return anomalies;
    },

    // ── Effect 3: Self-updating charts (HTMX push) ────────
    startAutoRefresh(chartId, endpoint, intervalMs=30000) {
        const key = `refresh_${chartId}`;
        if (this._cache[key]) clearInterval(this._cache[key]);
        this._cache[key] = setInterval(async () => {
            const data = await ATData.get(endpoint, 0); // bypass cache
            if (data) this.emit('data:refresh', {chartId, data, endpoint});
        }, intervalMs);
    },

    // ── Effect 4: Agent-triggered UI updates ──────────────
    bindAgentHook(agentType, chartId, transform) {
        this.on(`agent:${agentType}`, (data) => {
            const transformed = transform ? transform(data) : data;
            this.emit('chart:update', {chartId, data: transformed});
        });
    },

    // ── Effect 5: Adaptive charts (user profile) ──────────
    adaptToProfile(chartConfig) {
        const p = this._state.userProfile;
        if (p.bandwidth === 'low') {
            chartConfig.animation = false;
            chartConfig.progressive = 200;
        }
        if (p.audience === 'farmer') {
            // Simplify labels
            if (chartConfig.xAxis) chartConfig.xAxis.axisLabel = {interval: 3, fontSize: 10};
        }
        return chartConfig;
    },

    // ── Effect 6: Drill-down via intent ───────────────────
    registerIntent(chartId, intentMap) {
        // intentMap: {keyword: action}
        this.on('user:query', ({query}) => {
            const q = query.toLowerCase();
            Object.entries(intentMap).forEach(([kw, action]) => {
                if (q.includes(kw)) {
                    this.emit('drilldown:trigger', {chartId, action, query});
                }
            });
        });
    },

    // ── Effect 7: Semantic zoom ───────────────────────────
    semanticZoom(chartId, data, zoomLevel) {
        // zoomLevel: 'day'|'week'|'month'|'year'
        const buckets = {day:1, week:7, month:30, year:365};
        const step = buckets[zoomLevel] || 1;
        const sampled = data.filter((_,i) => i % step === 0);
        this.emit('chart:zoom', {chartId, data: sampled, level: zoomLevel});
    },

    // ── Effect 9: Decision overlay ────────────────────────
    addDecisionOverlay(chartId, decision) {
        this.emit('overlay:decision', {chartId, decision});
    },

    // ── Effect 10: Volatility animation (pulse) ───────────
    pulseVolatility(chartId, volatility) {
        const intensity = Math.min(volatility * 10, 1);
        this.emit('volatility:pulse', {chartId, intensity});
        const el = document.getElementById(chartId);
        if (el) {
            el.style.boxShadow = `0 0 ${Math.round(intensity*20)}px rgba(245,158,11,${intensity*0.4})`;
            setTimeout(() => el.style.boxShadow = '', 2000);
        }
    },

    // ── Effect 11: Risk heat propagation ─────────────────
    propagateRisk(riskByRegion) {
        Object.entries(riskByRegion).forEach(([region, data]) => {
            const el = document.querySelector(`[data-region="${region}"]`);
            if (el) {
                const h = data.high_pct / 100;
                el.style.borderColor = `rgba(239,68,68,${h})`;
                el.style.background = `rgba(239,68,68,${h*0.1})`;
            }
        });
        this.emit('risk:propagated', riskByRegion);
    },

    // ── Effect 12: Cross-chart linking ────────────────────
    linkCharts(sourceId, targetId, transform) {
        const sourceChart = Charts._ec[sourceId];
        if (!sourceChart) return;
        sourceChart.on('click', (params) => {
            const transformed = transform ? transform(params) : params;
            this.emit('chart:linked', {source: sourceId, target: targetId, data: transformed});
        });
    },

    // ── Effect 13: Temporal replay ────────────────────────
    async temporalReplay(chartId, produit, speedMs=200) {
        const data = await ATData.get(`/prix/${encodeURIComponent(produit)}`);
        if (!data?.length) return;
        const sorted = [...data].sort((a,b) => a.date.localeCompare(b.date));
        let i = 7;
        const interval = setInterval(() => {
            if (i >= sorted.length) { clearInterval(interval); return; }
            Charts.priceLine(chartId, sorted.slice(0, i), produit);
            i += 2;
        }, speedMs);
        return interval;
    },

    // ── Effect 14: Scenario simulation (what-if) ─────────
    simulateScenario(chartId, baseData, scenario) {
        // scenario: {rainfall: +20%, temp: +2, pesticides: -10%}
        const simulated = baseData.map(d => ({
            ...d,
            prix: d.prix * (1 + (scenario.priceShock || 0)),
            simulated: true,
        }));
        this.emit('scenario:ready', {chartId, simulated, scenario});
    },

    // ── Effect 15: Confidence shading ────────────────────
    addConfidenceShading(chartId, forecast) {
        if (!forecast?.forecast_30d) return;
        const bands = forecast.forecast_30d.map(f => [f.price_lower, f.price_upper]);
        this.emit('confidence:shade', {chartId, bands});
    },

    // ── Effect 16: Agent disagreement visualization ───────
    showDisagreement(chartId, geminiVal, qwenVal) {
        const diff = Math.abs(geminiVal - qwenVal) / Math.max(geminiVal, qwenVal);
        const color = diff > 0.2 ? '#ef4444' : diff > 0.1 ? '#f59e0b' : '#22c55e';
        this.emit('disagreement:show', {chartId, diff, color, geminiVal, qwenVal});
    },

    // ── Effect 17: Micro-pattern detection ───────────────
    detectPatterns(data) {
        if (data.length < 10) return [];
        const prices = data.map(d => d.prix);
        const patterns = [];
        // Head & shoulders detection (simplified)
        for (let i = 2; i < prices.length - 2; i++) {
            if (prices[i] > prices[i-1] && prices[i] > prices[i+1] &&
                prices[i-1] > prices[i-2] && prices[i+1] > prices[i+2]) {
                patterns.push({type: 'peak', index: i, value: prices[i], date: data[i].date});
            }
        }
        if (patterns.length) this.emit('pattern:detected', patterns);
        return patterns;
    },

    // ── Effect 18: KPI morphing ───────────────────────────
    morphKPI(elementId, fromVal, toVal, duration=800) {
        const el = document.getElementById(elementId);
        if (!el) return;
        const start = performance.now();
        const animate = (now) => {
            const p = Math.min((now - start) / duration, 1);
            const ease = 1 - Math.pow(1-p, 3);
            const current = fromVal + (toVal - fromVal) * ease;
            el.textContent = Number.isInteger(toVal) ? Math.round(current).toLocaleString() : current.toFixed(2);
            if (p < 1) requestAnimationFrame(animate);
        };
        requestAnimationFrame(animate);
    },

    // ── Effect 19: Low-bandwidth fallback ────────────────
    checkBandwidth() {
        const conn = navigator.connection;
        if (conn && (conn.effectiveType === '2g' || conn.saveData)) {
            this._state.userProfile.bandwidth = 'low';
            this.emit('bandwidth:low', {type: conn.effectiveType});
            // Disable animations
            document.documentElement.style.setProperty('--animation-duration', '0s');
        }
    },

    // ── Effect 20: Edge caching visualization state ───────
    cacheState(key, state) {
        try {
            sessionStorage.setItem(`agritogo_${key}`, JSON.stringify({
                state, ts: Date.now()
            }));
        } catch {}
    },
    restoreState(key, maxAge=300000) {
        try {
            const raw = sessionStorage.getItem(`agritogo_${key}`);
            if (!raw) return null;
            const {state, ts} = JSON.parse(raw);
            if (Date.now() - ts > maxAge) return null;
            return state;
        } catch { return null; }
    },
};

// ── Chart Object Binding ──────────────────────────────────
// Each chart becomes an intelligent object reacting to agents

const ChartObjects = {
    // Price chart — reacts to market agent + anomalies + predictions
    bindPriceChart(chartId, produit) {
        AgentOS.on('data:refresh', ({chartId: cid, data}) => {
            if (cid !== chartId) return;
            const rag = AgentOS.rag(data);
            Charts.priceLine(chartId, rag, produit);
            AgentOS.highlightAnomalies(chartId, rag);
            AgentOS.predictiveRender(chartId, rag);
        });

        AgentOS.on('predictive:ready', ({chartId: cid, predicted, historical}) => {
            if (cid !== chartId) return;
            const all = [...historical, ...predicted];
            const dates = all.map(d => d.date.slice(5));
            const prices = all.map(d => d.prix);
            const isPred = all.map(d => d.predicted || false);
            // Render with dashed predicted section
            const chart = Charts._ec[chartId];
            if (!chart) return;
            chart.setOption({
                series: [{
                    name: produit, type: 'line', data: prices,
                    lineStyle: {color: '#4f8cff', width: 2},
                    markArea: {
                        silent: true,
                        data: [[{xAxis: historical.length - 1}, {xAxis: all.length - 1}]],
                        itemStyle: {color: 'rgba(79,140,255,0.05)'},
                    },
                }],
            }, false);
        });

        AgentOS.on('anomaly:detected', ({chartId: cid, anomalies}) => {
            if (cid !== chartId) return;
            const chart = Charts._ec[chartId];
            if (!chart) return;
            chart.setOption({
                series: [{
                    markPoint: {
                        data: anomalies.map(a => ({
                            coord: [a.date.slice(5), a.prix],
                            symbol: 'pin', symbolSize: 20,
                            itemStyle: {color: '#ef4444'},
                            label: {show: false},
                        })),
                    },
                }],
            }, false);
        });

        AgentOS.on('overlay:decision', ({chartId: cid, decision}) => {
            if (cid !== chartId) return;
            const chart = Charts._ec[chartId];
            if (!chart) return;
            chart.setOption({
                graphic: [{
                    type: 'text',
                    right: 12, top: 36,
                    style: {
                        text: decision,
                        fill: '#22c55e',
                        fontSize: 11,
                        fontWeight: 600,
                        fontFamily: "'Inter',sans-serif",
                    },
                }],
            }, false);
        });

        // Cross-link: clicking price chart triggers forecast update
        AgentOS.linkCharts(chartId, 'chart-forecast', (params) => ({
            date: params.name, value: params.value
        }));

        AgentOS.on('chart:linked', ({source, target, data}) => {
            if (source !== chartId) return;
            // Trigger forecast for clicked date context
            ATData.loadForecastChart(target);
        });
    },

    // Risk chart — propagates to region cards
    bindRiskChart(chartId) {
        AgentOS.on('risk:propagated', (riskData) => {
            // Update gauge
            Charts.riskGauge('chart-risk-gauge', {risk_distribution: riskData});
        });
    },
};

// ── Confidence Shading on Forecast Chart ─────────────────
AgentOS.on('confidence:shade', ({chartId, bands}) => {
    const chart = Charts._ec[chartId];
    if (!chart) return;
    chart.setOption({
        series: [{
            name: 'Confidence',
            type: 'line',
            data: bands.map(b => b[1]),
            lineStyle: {opacity: 0},
            areaStyle: {color: 'rgba(79,140,255,0.08)'},
            stack: 'conf',
        }, {
            name: 'ConfLow',
            type: 'line',
            data: bands.map(b => b[0]),
            lineStyle: {opacity: 0},
            areaStyle: {color: 'rgba(79,140,255,0.08)'},
            stack: 'conf',
        }],
    }, false);
});

// ── Disagreement Visualization ────────────────────────────
AgentOS.on('disagreement:show', ({chartId, diff, color, geminiVal, qwenVal}) => {
    const el = document.getElementById(chartId + '-disagreement');
    if (el) {
        el.innerHTML = `<span style="color:${color};font-size:10px;font-family:var(--mono)">Δ${(diff*100).toFixed(1)}% disagreement</span>`;
    }
});

// ── Pattern Detection Overlay ─────────────────────────────
AgentOS.on('pattern:detected', (patterns) => {
    patterns.forEach(p => {
        const el = document.getElementById('pattern-alert');
        if (el) {
            el.textContent = `Pattern: ${p.type} at ${p.date} (${p.value} FCFA)`;
            el.style.display = 'block';
            setTimeout(() => el.style.display = 'none', 5000);
        }
    });
});

// ── Bandwidth check on load ───────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    AgentOS.checkBandwidth();

    // Restore cached state
    const cached = AgentOS.restoreState('dashboard');
    if (cached?.produit) {
        ATData.loadPriceChart('chart-price', cached.produit);
    }

    // Bind chart objects
    ChartObjects.bindPriceChart('chart-price', 'Mais');
    ChartObjects.bindRiskChart('chart-risk-gauge');

    // Auto-refresh price chart every 60s
    AgentOS.startAutoRefresh('chart-price', '/prix/Mais', 60000);

    // Register intents for drill-down
    AgentOS.registerIntent('chart-price', {
        'mais': () => ATData.loadPriceChart('chart-price', 'Mais'),
        'riz': () => ATData.loadPriceChart('chart-price', 'Riz'),
        'kara': () => ATData.loadPriceChart('chart-price', 'Mais', 'Kara'),
        'risque': () => ATData.loadRiskCharts(),
        'prevision': () => ATData.loadForecastChart('chart-forecast'),
    });

    // Save state on produit change
    const produitSel = document.getElementById('dash-produit');
    if (produitSel) {
        produitSel.addEventListener('change', () => {
            AgentOS.cacheState('dashboard', {produit: produitSel.value});
        });
    }
});

// ── Thought stream → agent hooks ─────────────────────────
// When agent emits a decision, update the price chart overlay
if (typeof ThoughtStream !== 'undefined') {
    const origRender = ThoughtStream.render.bind(ThoughtStream);
    ThoughtStream.render = function(event) {
        origRender(event);
        if (event.type === 'decision' && event.content) {
            const short = event.content.slice(0, 40);
            AgentOS.addDecisionOverlay('chart-price', short);
        }
        if (event.type === 'tool_result') {
            AgentOS.emit('agent:market', event);
        }
    };
}
