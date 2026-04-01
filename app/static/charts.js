/* AgriTogo — ECharts DataViz System v1.0 */
/* Bloomberg-grade, HTMX-compatible, lazy-loaded */

const AT = {
    // ── Theme ──────────────────────────────────────────────
    theme: {
        bg: '#0a0b0f', bg2: '#161922', bg3: '#1c1f2e',
        border: '#252940', text0: '#f0f1f5', text1: '#c8cad4',
        text2: '#8b8fa3', text3: '#5c6078',
        accent: '#4f8cff', green: '#22c55e', red: '#ef4444',
        amber: '#f59e0b', purple: '#a78bfa',
        font: "'Inter', -apple-system, sans-serif",
        mono: "'JetBrains Mono', monospace",
    },

    // ── Chart registry (reuse instances) ──────────────────
    _charts: {},

    init(id, option) {
        if (this._charts[id]) {
            this._charts[id].setOption(option, true);
            return this._charts[id];
        }
        const el = document.getElementById(id);
        if (!el) return null;
        const chart = echarts.init(el, null, { renderer: 'canvas' });
        chart.setOption(option);
        this._charts[id] = chart;
        window.addEventListener('resize', () => chart.resize());
        return chart;
    },

    destroy(id) {
        if (this._charts[id]) {
            this._charts[id].dispose();
            delete this._charts[id];
        }
    },

    // ── Base option (shared) ──────────────────────────────
    base(extra = {}) {
        return {
            backgroundColor: 'transparent',
            textStyle: { fontFamily: this.theme.font, color: this.theme.text1 },
            grid: { top: 28, right: 12, bottom: 28, left: 48, containLabel: true },
            tooltip: {
                backgroundColor: this.theme.bg3,
                borderColor: this.theme.border,
                borderWidth: 1,
                textStyle: { color: this.theme.text0, fontSize: 12 },
                extraCssText: 'box-shadow:0 4px 16px rgba(0,0,0,0.4)',
            },
            ...extra,
        };
    },

    // ── Skeleton loader ───────────────────────────────────
    skeleton(id) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="chart-skeleton"></div>';
    },

    // ── 1. SPARKLINE (inline trend) ───────────────────────
    sparkline(id, data, color = '#4f8cff') {
        return this.init(id, {
            ...this.base(),
            grid: { top: 2, right: 2, bottom: 2, left: 2 },
            xAxis: { type: 'category', show: false, data: data.map((_, i) => i) },
            yAxis: { type: 'value', show: false },
            series: [{
                type: 'line', data, smooth: true, symbol: 'none',
                lineStyle: { color, width: 1.5 },
                areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                    colorStops: [{ offset: 0, color: color + '30' }, { offset: 1, color: color + '00' }] } },
            }],
        });
    },

    // ── 2. PRICE LINE (trend + volatility band) ───────────
    priceLine(id, dates, prices, label = 'Price') {
        const t = this.theme;
        const ma = this._ma(prices, 7);
        return this.init(id, {
            ...this.base(),
            tooltip: { ...this.base().tooltip, trigger: 'axis',
                formatter: p => `<b>${p[0].axisValue}</b><br>${p.map(s => `${s.marker}${s.seriesName}: <b>${s.value} FCFA</b>`).join('<br>')}` },
            legend: { data: [label, 'MA7'], textStyle: { color: t.text2, fontSize: 11 }, top: 4, right: 8 },
            xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: t.border } },
                axisLabel: { color: t.text3, fontSize: 10 }, splitLine: { show: false } },
            yAxis: { type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: t.border, type: 'dashed' } },
                axisLabel: { color: t.text3, fontSize: 10, formatter: v => v + ' F' } },
            series: [
                { name: label, type: 'line', data: prices, smooth: false, symbol: 'none',
                    lineStyle: { color: t.accent, width: 2 },
                    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [{ offset: 0, color: t.accent + '25' }, { offset: 1, color: t.accent + '00' }] } } },
                { name: 'MA7', type: 'line', data: ma, smooth: true, symbol: 'none',
                    lineStyle: { color: t.amber, width: 1, type: 'dashed' } },
            ],
        });
    },

    // ── 3. CANDLESTICK ────────────────────────────────────
    candlestick(id, dates, ohlc) {
        const t = this.theme;
        return this.init(id, {
            ...this.base(),
            tooltip: { ...this.base().tooltip, trigger: 'axis', axisPointer: { type: 'cross' } },
            xAxis: { type: 'category', data: dates, axisLabel: { color: t.text3, fontSize: 10 },
                axisLine: { lineStyle: { color: t.border } }, splitLine: { show: false } },
            yAxis: { type: 'value', splitLine: { lineStyle: { color: t.border, type: 'dashed' } },
                axisLabel: { color: t.text3, fontSize: 10 } },
            series: [{
                type: 'candlestick', data: ohlc,
                itemStyle: { color: t.green, color0: t.red, borderColor: t.green, borderColor0: t.red },
            }],
        });
    },

    // ── 4. HEATMAP (regions × metric) ────────────────────
    heatmap(id, regions, metrics, data, title = '') {
        const t = this.theme;
        const flat = data.flat();
        const min = Math.min(...flat), max = Math.max(...flat);
        return this.init(id, {
            ...this.base({ grid: { top: 40, right: 16, bottom: 40, left: 80 } }),
            title: title ? { text: title, textStyle: { color: t.text2, fontSize: 11, fontWeight: 500 }, top: 4 } : undefined,
            tooltip: { ...this.base().tooltip, formatter: p => `${p.name}<br><b>${p.value[2]}</b>` },
            xAxis: { type: 'category', data: metrics, axisLabel: { color: t.text3, fontSize: 10 }, splitArea: { show: true, areaStyle: { color: ['transparent', t.bg2 + '40'] } } },
            yAxis: { type: 'category', data: regions, axisLabel: { color: t.text2, fontSize: 11 } },
            visualMap: { min, max, calculable: false, show: false,
                inRange: { color: [t.bg3, t.accent + '60', t.accent] } },
            series: [{ type: 'heatmap', data: data.flatMap((row, ri) => row.map((v, ci) => [ci, ri, v])),
                label: { show: true, color: t.text0, fontSize: 10, formatter: p => p.value[2] } }],
        });
    },

    // ── 5. SCATTER / PCA CLUSTERS ─────────────────────────
    scatter(id, clusters) {
        const t = this.theme;
        const colors = [t.accent, t.green, t.amber, t.purple, t.red];
        const names = ['Subsistence', 'Emerging', 'Intensive', 'Large'];
        return this.init(id, {
            ...this.base(),
            tooltip: { ...this.base().tooltip, trigger: 'item',
                formatter: p => `<b>${names[p.seriesIndex] || 'Cluster ' + p.seriesIndex}</b><br>PC1: ${p.value[0].toFixed(2)}<br>PC2: ${p.value[1].toFixed(2)}` },
            legend: { data: names.slice(0, clusters.length), textStyle: { color: t.text2, fontSize: 10 }, top: 4 },
            xAxis: { name: 'PC1', nameTextStyle: { color: t.text3, fontSize: 10 }, axisLabel: { color: t.text3, fontSize: 9 },
                splitLine: { lineStyle: { color: t.border, type: 'dashed' } } },
            yAxis: { name: 'PC2', nameTextStyle: { color: t.text3, fontSize: 10 }, axisLabel: { color: t.text3, fontSize: 9 },
                splitLine: { lineStyle: { color: t.border, type: 'dashed' } } },
            series: clusters.map((pts, i) => ({
                name: names[i] || 'Cluster ' + i, type: 'scatter',
                data: pts, symbolSize: 5,
                itemStyle: { color: colors[i % colors.length], opacity: 0.7 },
            })),
        });
    },

    // ── 6. BUBBLE (risk-return) ───────────────────────────
    bubble(id, items) {
        // items: [{name, x: return, y: risk, z: size}]
        const t = this.theme;
        return this.init(id, {
            ...this.base(),
            tooltip: { ...this.base().tooltip, trigger: 'item',
                formatter: p => `<b>${p.data[3]}</b><br>ROI: ${p.data[0]}%<br>Risk: ${p.data[1]}%<br>Volume: ${p.data[2]}` },
            xAxis: { name: 'ROI (%)', nameTextStyle: { color: t.text3, fontSize: 10 },
                axisLabel: { color: t.text3, fontSize: 10 }, splitLine: { lineStyle: { color: t.border, type: 'dashed' } } },
            yAxis: { name: 'Risk (%)', nameTextStyle: { color: t.text3, fontSize: 10 },
                axisLabel: { color: t.text3, fontSize: 10 }, splitLine: { lineStyle: { color: t.border, type: 'dashed' } } },
            series: [{
                type: 'scatter', data: items.map(d => [d.x, d.y, d.z, d.name]),
                symbolSize: d => Math.sqrt(d[2]) * 3 + 8,
                itemStyle: { color: p => p.data[1] > 60 ? t.red : p.data[1] > 30 ? t.amber : t.green, opacity: 0.8 },
                label: { show: true, formatter: p => p.data[3], position: 'top', color: t.text2, fontSize: 10 },
            }],
        });
    },

    // ── 7. RADAR (crop comparison) ────────────────────────
    radar(id, crops, indicators, data) {
        const t = this.theme;
        const colors = [t.accent, t.green, t.amber, t.purple];
        return this.init(id, {
            ...this.base({ grid: undefined }),
            tooltip: { ...this.base().tooltip },
            legend: { data: crops, textStyle: { color: t.text2, fontSize: 10 }, bottom: 0 },
            radar: {
                indicator: indicators.map(i => ({ name: i.name, max: i.max })),
                shape: 'polygon', splitNumber: 4,
                axisName: { color: t.text2, fontSize: 10 },
                splitLine: { lineStyle: { color: t.border } },
                splitArea: { areaStyle: { color: ['transparent', t.bg2 + '30'] } },
                axisLine: { lineStyle: { color: t.border } },
            },
            series: [{ type: 'radar', data: crops.map((name, i) => ({
                name, value: data[i],
                lineStyle: { color: colors[i % colors.length], width: 1.5 },
                areaStyle: { color: colors[i % colors.length] + '20' },
                itemStyle: { color: colors[i % colors.length] },
            })) }],
        });
    },

    // ── 8. GAUGE (risk score) ─────────────────────────────
    gauge(id, value, label = 'Risk Score') {
        const t = this.theme;
        const color = value > 66 ? t.red : value > 33 ? t.amber : t.green;
        return this.init(id, {
            ...this.base({ grid: undefined }),
            series: [{
                type: 'gauge', startAngle: 200, endAngle: -20, min: 0, max: 100,
                radius: '85%', center: ['50%', '60%'],
                progress: { show: true, width: 10, itemStyle: { color } },
                axisLine: { lineStyle: { width: 10, color: [[1, t.bg3]] } },
                axisTick: { show: false }, splitLine: { show: false },
                axisLabel: { show: false }, pointer: { show: false },
                detail: { valueAnimation: true, fontSize: 22, fontWeight: 700,
                    fontFamily: t.mono, color: t.text0, offsetCenter: [0, '10%'],
                    formatter: v => v.toFixed(0) + '%' },
                title: { offsetCenter: [0, '35%'], fontSize: 11, color: t.text3 },
                data: [{ value, name: label }],
            }],
        });
    },

    // ── 9. BAR (feature importance / distribution) ────────
    bar(id, categories, values, color = '#4f8cff', horizontal = true) {
        const t = this.theme;
        const axis = { type: 'category', data: categories, axisLabel: { color: t.text2, fontSize: 11 },
            axisLine: { lineStyle: { color: t.border } }, splitLine: { show: false } };
        const val = { type: 'value', axisLabel: { color: t.text3, fontSize: 10 },
            splitLine: { lineStyle: { color: t.border, type: 'dashed' } } };
        return this.init(id, {
            ...this.base(),
            tooltip: { ...this.base().tooltip, trigger: 'axis' },
            xAxis: horizontal ? val : axis,
            yAxis: horizontal ? axis : val,
            series: [{ type: 'bar', data: values, barMaxWidth: 20,
                itemStyle: { color, borderRadius: [0, 3, 3, 0] },
                label: { show: true, position: horizontal ? 'right' : 'top',
                    color: t.text2, fontSize: 10, formatter: p => p.value.toFixed ? p.value.toFixed(3) : p.value } }],
        });
    },

    // ── Helpers ───────────────────────────────────────────
    _ma(data, period) {
        return data.map((_, i) => {
            if (i < period - 1) return null;
            const slice = data.slice(i - period + 1, i + 1);
            return +(slice.reduce((a, b) => a + b, 0) / period).toFixed(1);
        });
    },
};

// ── API Data Binding ──────────────────────────────────────
const ATData = {
    _cache: {},

    async fetch(endpoint, ttl = 60000) {
        const now = Date.now();
        if (this._cache[endpoint] && now - this._cache[endpoint].ts < ttl)
            return this._cache[endpoint].data;
        const r = await fetch('/api/v1' + endpoint);
        const data = await r.json();
        this._cache[endpoint] = { data, ts: now };
        return data;
    },

    // Load price chart for a product
    async loadPriceChart(chartId, produit, marche = '') {
        AT.skeleton(chartId);
        const qs = marche ? `?marche=${encodeURIComponent(marche)}` : '';
        const data = await this.fetch(`/prix/${encodeURIComponent(produit)}${qs}`);
        if (!data.length) return;
        const sorted = data.sort((a, b) => a.date.localeCompare(b.date));
        const dates = sorted.map(d => d.date.slice(5)); // MM-DD
        const prices = sorted.map(d => d.prix);
        AT.priceLine(chartId, dates, prices, produit);
        this._addInsight(chartId, prices);
    },

    // Load GARCH forecast chart
    async loadForecastChart(chartId, produit = 'Mais') {
        AT.skeleton(chartId);
        const data = await this.fetch('/forecast', 0); // no cache for POST
        // Use last known price + forecast band
        if (!data.forecast_30d) return;
        const dates = data.forecast_30d.map(d => d.date.slice(5));
        const lower = data.forecast_30d.map(d => d.price_lower);
        const upper = data.forecast_30d.map(d => d.price_upper);
        const mid = data.forecast_30d.map(d => (d.price_lower + d.price_upper) / 2);
        AT.init(chartId, {
            ...AT.base(),
            tooltip: { ...AT.base().tooltip, trigger: 'axis' },
            legend: { data: ['Forecast', 'Range'], textStyle: { color: AT.theme.text2, fontSize: 10 }, top: 4 },
            xAxis: { type: 'category', data: dates, axisLabel: { color: AT.theme.text3, fontSize: 10 }, splitLine: { show: false } },
            yAxis: { type: 'value', axisLabel: { color: AT.theme.text3, fontSize: 10 }, splitLine: { lineStyle: { color: AT.theme.border, type: 'dashed' } } },
            series: [
                { name: 'Forecast', type: 'line', data: mid, smooth: true, symbol: 'none', lineStyle: { color: AT.theme.accent, width: 2 } },
                { name: 'Range', type: 'line', data: upper, smooth: true, symbol: 'none', lineStyle: { color: AT.theme.amber, width: 1, type: 'dashed' }, stack: 'band', areaStyle: { color: AT.theme.amber + '15' } },
                { name: 'Lower', type: 'line', data: lower, smooth: true, symbol: 'none', lineStyle: { color: AT.theme.amber, width: 1, type: 'dashed' }, stack: 'band' },
            ],
        });
    },

    // Load KPI heatmap
    async loadKPIHeatmap(chartId) {
        AT.skeleton(chartId);
        const data = await this.fetch('/kpi');
        const regions = Object.keys(data.yield_by_region || {});
        if (!regions.length) return;
        const yields = regions.map(r => data.yield_by_region[r].avg_yield_kg_ha);
        const risks = regions.map(r => (data.climate_risk_by_region[r] || {}).risk_score || 0);
        AT.heatmap(chartId, regions, ['Yield (kg/ha)', 'Climate Risk'],
            [yields.map(v => Math.round(v)), risks.map(v => Math.round(v))]);
    },

    // Load risk gauge
    async loadRiskGauge(chartId) {
        AT.skeleton(chartId);
        const data = await this.fetch('/risk', 0);
        const high = data.risk_distribution?.high || 0;
        const total = Object.values(data.risk_distribution || {}).reduce((a, b) => a + b, 0);
        const score = total ? Math.round(high / total * 100) : 0;
        AT.gauge(chartId, score, 'Portfolio Risk');
    },

    // 1-line AI insight on chart interaction
    _addInsight(chartId, prices) {
        const chart = AT._charts[chartId];
        if (!chart) return;
        const last = prices[prices.length - 1];
        const prev = prices[prices.length - 8] || prices[0];
        const delta = ((last - prev) / prev * 100).toFixed(1);
        const trend = delta > 2 ? 'Upward trend' : delta < -2 ? 'Downward trend' : 'Stable';
        const el = document.getElementById(chartId + '-insight');
        if (el) el.textContent = `${trend} ${delta > 0 ? '+' : ''}${delta}% (7d) — Last: ${last} FCFA`;
    },
};
