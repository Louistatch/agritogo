/* AgriTogo — Chart Debug Tool
 * Run in browser console: DebugCharts.runAll()
 */
const DebugCharts = {
    async runAll() {
        console.group('AgriTogo Chart Debug');

        // 1. Check ECharts loaded
        console.log('ECharts:', typeof echarts !== 'undefined' ? 'OK' : 'MISSING');
        console.log('Three.js:', typeof THREE !== 'undefined' ? 'OK' : 'MISSING');
        console.log('ATData:', typeof ATData !== 'undefined' ? 'OK' : 'MISSING');
        console.log('Charts:', typeof Charts !== 'undefined' ? 'OK' : 'MISSING');

        // 2. Check chart containers exist
        const ids = ['chart-price','chart-forecast','chart-heatmap','chart-gauge',
                     'chart-roi-bubble','chart-yield-radar','chart-risk-gauge',
                     'chart-risk-region','chart-risk-3d','chart-seg-3d'];
        ids.forEach(id => {
            const el = document.getElementById(id);
            console.log(`#${id}:`, el ? `EXISTS (${el.offsetWidth}x${el.offsetHeight})` : 'MISSING');
        });

        // 3. Test API endpoints
        console.group('API Tests');
        try {
            const kpi = await ATData.get('/kpi');
            console.log('/kpi:', kpi ? `OK — regions: ${Object.keys(kpi.yield_by_region||{}).join(',')}` : 'FAILED');
        } catch(e) { console.error('/kpi:', e); }

        try {
            const risk = await ATData.post('/risk');
            console.log('/risk:', risk ? `OK — F1: ${risk.metrics?.f1}` : 'FAILED');
        } catch(e) { console.error('/risk:', e); }

        try {
            const prix = await ATData.get('/prix/Ma%C3%AFs');
            console.log('/prix/Maïs:', prix ? `OK — ${prix.length} rows` : 'FAILED/EMPTY');
        } catch(e) { console.error('/prix:', e); }

        try {
            const forecast = await ATData.post('/forecast', {produit:'Ma\u00EFs', periods:10});
            console.log('/forecast:', forecast ? `OK — ${forecast.forecast_30d?.length} days` : 'FAILED');
        } catch(e) { console.error('/forecast:', e); }
        console.groupEnd();

        // 4. Force render all charts
        console.group('Force Render');
        await this.forceRenderAll();
        console.groupEnd();

        console.groupEnd();
    },

    async forceRenderAll() {
        // Price
        const produit = document.getElementById('dash-produit')?.value || 'Ma\u00EFs';
        await ATData.loadPriceChart('chart-price', produit);
        console.log('chart-price: rendered');

        // KPI
        const kpi = await ATData.get('/kpi');
        if (kpi) {
            if (document.getElementById('chart-heatmap')) {
                Charts.regionalHeatmap('chart-heatmap', kpi);
                console.log('chart-heatmap: rendered');
            }
            if (document.getElementById('chart-roi-bubble')) {
                Charts.roiBubble('chart-roi-bubble', kpi);
                console.log('chart-roi-bubble: rendered');
            }
            if (document.getElementById('chart-yield-radar')) {
                Charts.yieldRadar('chart-yield-radar', kpi);
                console.log('chart-yield-radar: rendered');
            }
        }

        // Risk gauge
        const risk = await ATData.post('/risk');
        if (risk) {
            if (document.getElementById('chart-gauge')) {
                Charts.riskGauge('chart-gauge', risk);
                console.log('chart-gauge: rendered');
            }
        }

        // Forecast
        const fc = await ATData.post('/forecast', {produit, periods:30});
        if (fc?.forecast_30d && document.getElementById('chart-forecast')) {
            ATData.loadForecastChart('chart-forecast', produit);
            console.log('chart-forecast: rendered');
        }
    },
};

// Auto-expose
window.DebugCharts = DebugCharts;
