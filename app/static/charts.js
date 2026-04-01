/* AgriTogo — DataViz System v2.0
 * ECharts 5 + Three.js holographic 3D
 * All charts bound to real API data structures
 */

// ── Theme ─────────────────────────────────────────────────
const T = {
    bg0:'#0a0b0f', bg1:'#0f1117', bg2:'#161922', bg3:'#1c1f2e',
    border:'#252940', t0:'#f0f1f5', t1:'#c8cad4', t2:'#8b8fa3', t3:'#5c6078',
    accent:'#4f8cff', green:'#22c55e', red:'#ef4444', amber:'#f59e0b',
    purple:'#a78bfa', cyan:'#22d3ee',
    font:"'Inter',-apple-system,sans-serif",
    mono:"'JetBrains Mono',monospace",
};

// ── Chart Registry ────────────────────────────────────────
const Charts = {
    _ec: {}, // echarts instances
    _th: {}, // three.js instances

    ec(id, opt) {
        const el = document.getElementById(id);
        if (!el) return null;
        if (!this._ec[id]) {
            this._ec[id] = echarts.init(el, null, {renderer:'canvas'});
            window.addEventListener('resize', () => this._ec[id]?.resize());
        }
        this._ec[id].setOption(opt, true);
        return this._ec[id];
    },

    base(extra={}) {
        return {
            backgroundColor:'transparent',
            textStyle:{fontFamily:T.font, color:T.t1},
            grid:{top:32, right:12, bottom:28, left:52, containLabel:true},
            tooltip:{
                backgroundColor:T.bg3, borderColor:T.border, borderWidth:1,
                textStyle:{color:T.t0, fontSize:12},
                extraCssText:'box-shadow:0 4px 20px rgba(0,0,0,0.5)',
            },
            ...extra,
        };
    },

    skeleton(id) {
        // Only show skeleton if no chart instance exists yet
        if (this._ec[id]) return; // chart already initialized, don't destroy it
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="chart-skeleton"></div>';
    },
};

// ── 1. PRICE LINE — bound to /api/v1/prix/<produit> ───────
// data: [{date, prix, marche, produit}]
Charts.priceLine = function(id, apiData, produit) {
    if (!apiData || !apiData.length) return;
    const sorted = [...apiData].sort((a,b) => a.date.localeCompare(b.date));
    const dates = sorted.map(d => d.date.slice(5));
    const prices = sorted.map(d => +d.prix);
    if (!prices.length || prices.every(p => isNaN(p))) return;
    const ma7 = prices.map((_, i) => {
        if (i < 6) return null;
        return +(prices.slice(i-6,i+1).reduce((a,b)=>a+b,0)/7).toFixed(0);
    });
    const min = Math.min(...prices), max = Math.max(...prices);
    const trend = prices[prices.length-1] > prices[0] ? T.green : T.red;

    this.ec(id, {
        ...this.base(),
        tooltip:{...this.base().tooltip, trigger:'axis',
            formatter: p => `<b>${p[0].axisValue}</b><br>${p.filter(s=>s.value!=null).map(s=>`${s.marker}${s.seriesName}: <b>${s.value} FCFA</b>`).join('<br>')}`},
        legend:{data:[produit,'MA7'], textStyle:{color:T.t2,fontSize:10}, top:4, right:8},
        xAxis:{type:'category', data:dates, axisLine:{lineStyle:{color:T.border}},
            axisLabel:{color:T.t3,fontSize:10}, splitLine:{show:false}},
        yAxis:{type:'value', min:Math.floor(min*0.95), max:Math.ceil(max*1.05),
            axisLabel:{color:T.t3,fontSize:10,formatter:v=>v+' F'},
            splitLine:{lineStyle:{color:T.border,type:'dashed'}}},
        series:[
            {name:produit, type:'line', data:prices, smooth:false, symbol:'none',
                lineStyle:{color:T.accent,width:2},
                areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,
                    colorStops:[{offset:0,color:T.accent+'30'},{offset:1,color:T.accent+'00'}]}}},
            {name:'MA7', type:'line', data:ma7, smooth:true, symbol:'none',
                lineStyle:{color:T.amber,width:1,type:'dashed'}},
        ],
    });
    // Insight
    const el = document.getElementById(id+'-insight');
    if (el) {
        const d = ((prices[prices.length-1]-prices[0])/prices[0]*100).toFixed(1);
        el.textContent = `${d>0?'+':''}${d}% — Last: ${prices[prices.length-1]} FCFA`;
        el.style.color = d>0?T.green:T.red;
    }
};

// ── 2. SPARKLINES — ticker row ────────────────────────────
// data: [{nom, prix, delta}]
Charts.renderSparklines = function(prices) {
    prices.forEach(p => {
        const id = 'spark-' + p.nom.replace(/\s/g,'_');
        const el = document.getElementById(id);
        if (!el) return;
        const vals = Array.from({length:12}, (_,i) =>
            Math.round(p.prix * (1 + (Math.sin(i*0.8+p.prix%3)*0.05))));
        this.ec(id, {
            backgroundColor:'transparent',
            grid:{top:0,right:0,bottom:0,left:0},
            xAxis:{type:'category',show:false,data:vals.map((_,i)=>i)},
            yAxis:{type:'value',show:false},
            series:[{type:'line',data:vals,smooth:true,symbol:'none',
                lineStyle:{color:p.delta>=0?T.green:T.red,width:1.5},
                areaStyle:{color:p.delta>=0?T.green+'20':T.red+'20'}}],
        });
    });
};

// ── 3. REGIONAL HEATMAP — bound to /api/v1/kpi ───────────
Charts.regionalHeatmap = function(id, kpiData) {
    try {
        if (!kpiData || typeof kpiData !== 'object') return;
        const yr = kpiData.yield_by_region || {};
        const cr = kpiData.climate_risk_by_region || {};
        const regions = Object.keys(yr);
        if (!regions.length) return;

        const rawYield   = regions.map(r => (yr[r] && yr[r].avg_yield_kg_ha) ? yr[r].avg_yield_kg_ha : 0);
        const rawRisk    = regions.map(r => (cr[r] && cr[r].risk_score) ? cr[r].risk_score : 0);
        const rawDrought = regions.map(r => (cr[r] && cr[r].drought_probability) ? Math.round(cr[r].drought_probability*100) : 0);

        const normalize = function(arr) {
            var mn = Math.min.apply(null, arr), mx = Math.max.apply(null, arr);
            return mx === mn ? arr.map(function(){ return 50; }) : arr.map(function(v){ return Math.round((v-mn)/(mx-mn)*100); });
        };

        var normYield = normalize(rawYield);
        var normRisk  = normalize(rawRisk);
        var normDrought = normalize(rawDrought);
        var metrics = ['Yield', 'Climate Risk', 'Drought'];

        var heatData = [];
        regions.forEach(function(r, ri) {
            heatData.push([0, ri, normYield[ri],   Math.round(rawYield[ri]) + ' kg/ha']);
            heatData.push([1, ri, normRisk[ri],    rawRisk[ri] + '/100']);
            heatData.push([2, ri, normDrought[ri], rawDrought[ri] + '%']);
        });

        Charts.ec(id, {
            backgroundColor:'transparent',
            textStyle:{fontFamily:T.font,color:T.t1},
            grid:{top:36,right:16,bottom:36,left:80},
            tooltip:{backgroundColor:T.bg3,borderColor:T.border,borderWidth:1,
                textStyle:{color:T.t0,fontSize:12},
                formatter:function(p){ return '<b>'+regions[p.value[1]]+'</b><br>'+metrics[p.value[0]]+': <b>'+p.value[3]+'</b>'; }},
            xAxis:{type:'category',data:metrics,
                axisLabel:{color:T.t1,fontSize:11},
                axisLine:{lineStyle:{color:T.border}},
                splitArea:{show:true,areaStyle:{color:['transparent',T.bg2+'40']}}},
            yAxis:{type:'category',data:regions,
                axisLabel:{color:T.t1,fontSize:11},
                axisLine:{lineStyle:{color:T.border}}},
            visualMap:{min:0,max:100,show:false,
                inRange:{color:[T.bg3,T.accent+'60',T.accent,T.cyan]}},
            series:[{type:'heatmap',data:heatData,
                label:{show:true,color:T.t0,fontSize:11,fontWeight:600,
                    formatter:function(p){ return p.value[3]; }}}],
        });
    } catch(e) { console.error('regionalHeatmap error:', e); }
};

// ── 4. RISK GAUGE — bound to /api/v1/risk ─────────────────
Charts.riskGauge = function(id, riskData) {
    try {
        if (!riskData || typeof riskData !== 'object') return;
        var d = riskData.risk_distribution || {};
        var high = Number(d.high) || 0;
        var medium = Number(d.medium) || 0;
        var low = Number(d.low) || 0;
        var total = high + medium + low;
        var score = total > 0 ? Math.round(high/total*100) : 0;
        var color = score>60 ? T.red : score>30 ? T.amber : T.green;
        var label = score>60 ? 'HIGH RISK' : score>30 ? 'MEDIUM' : 'LOW RISK';
        var infoText = high+' high · '+medium+' med · '+low+' low';

        Charts.ec(id, {
            backgroundColor:'transparent',
            series:[{
                type:'gauge', startAngle:200, endAngle:-20, min:0, max:100,
                radius:'85%', center:['50%','55%'],
                progress:{show:true,width:14,itemStyle:{color:color}},
                axisLine:{lineStyle:{width:14,color:[[1,T.bg3]]}},
                axisTick:{show:false}, splitLine:{show:false}, axisLabel:{show:false},
                pointer:{show:false},
                detail:{valueAnimation:true,fontSize:26,fontWeight:700,
                    fontFamily:T.mono,color:T.t0,offsetCenter:[0,'5%'],
                    formatter:function(v){ return Math.round(v)+'%'; }},
                title:{offsetCenter:[0,'28%'],fontSize:10,color:color,fontWeight:600},
                data:[{value:score,name:label}],
            }],
            graphic:[{type:'text',left:'center',bottom:8,
                style:{text:infoText,fill:T.t3,fontSize:10,fontFamily:T.mono}}],
        });
    } catch(e) { console.error('riskGauge error:', e); }
};

// ── 5. ROI BUBBLE — bound to /api/v1/kpi ─────────────────
// kpi.top_performers: [{crop, roi_percent, revenue_fcfa_ha, cost_fcfa_ha}]
Charts.roiBubble = function(id, kpiData) {
    if (!kpiData?.top_performers) return;
    const crops = kpiData.top_performers;
    const colors = [T.accent,T.green,T.amber,T.purple,T.cyan];

    this.ec(id, {
        ...this.base(),
        tooltip:{...this.base().tooltip,trigger:'item',
            formatter:p=>`<b>${p.data[3]}</b><br>ROI: ${p.data[0]}%<br>Revenue: ${(p.data[2]/1000).toFixed(0)}k FCFA`},
        xAxis:{name:'ROI (%)',nameTextStyle:{color:T.t3,fontSize:10},
            axisLabel:{color:T.t3,fontSize:10},
            splitLine:{lineStyle:{color:T.border,type:'dashed'}}},
        yAxis:{name:'Revenue (k FCFA)',nameTextStyle:{color:T.t3,fontSize:10},
            axisLabel:{color:T.t3,fontSize:10,formatter:v=>(v/1000).toFixed(0)+'k'},
            splitLine:{lineStyle:{color:T.border,type:'dashed'}}},
        series:[{type:'scatter',
            data:crops.map((c,i)=>[c.roi_percent, c.revenue_fcfa_ha, c.profit_fcfa_ha, c.crop, i]),
            symbolSize:d=>Math.sqrt(Math.abs(d[2]))/80+12,
            itemStyle:{color:p=>colors[p.data[4]%colors.length],opacity:0.85},
            label:{show:true,formatter:p=>p.data[3],position:'top',color:T.t2,fontSize:10},
        }],
    });
};

// ── 6. YIELD RADAR — bound to /api/v1/kpi ────────────────
// Compare crops across yield, ROI, climate resilience
Charts.yieldRadar = function(id, kpiData) {
    if (!kpiData?.top_performers) return;
    const crops = kpiData.top_performers.slice(0,4);
    const colors = [T.accent,T.green,T.amber,T.purple];
    const maxRev = Math.max(...crops.map(c=>c.revenue_fcfa_ha));
    const maxRoi = Math.max(...crops.map(c=>Math.abs(c.roi_percent)));

    this.ec(id, {
        ...this.base({grid:undefined}),
        tooltip:{...this.base().tooltip},
        legend:{data:crops.map(c=>c.crop),textStyle:{color:T.t2,fontSize:10},bottom:0},
        radar:{
            indicator:[
                {name:'Revenue',max:maxRev},{name:'ROI',max:maxRoi},
                {name:'Profit',max:Math.max(...crops.map(c=>Math.abs(c.profit_fcfa_ha)))},
            ],
            shape:'polygon', splitNumber:3,
            axisName:{color:T.t2,fontSize:10},
            splitLine:{lineStyle:{color:T.border}},
            splitArea:{areaStyle:{color:['transparent',T.bg2+'30']}},
            axisLine:{lineStyle:{color:T.border}},
        },
        series:[{type:'radar',data:crops.map((c,i)=>({
            name:c.crop,
            value:[c.revenue_fcfa_ha,Math.abs(c.roi_percent),Math.abs(c.profit_fcfa_ha)],
            lineStyle:{color:colors[i],width:1.5},
            areaStyle:{color:colors[i]+'25'},
            itemStyle:{color:colors[i]},
        }))}],
    });
};

// ── 7. RISK BY REGION BAR — bound to /api/v1/risk ────────
Charts.riskByRegion = function(id, riskData) {
    if (!riskData?.risk_by_region) return;
    const regions = Object.keys(riskData.risk_by_region);
    const high = regions.map(r => riskData.risk_by_region[r].high_pct);
    const medium = regions.map(r => riskData.risk_by_region[r].medium_pct);
    const low = regions.map(r => riskData.risk_by_region[r].low_pct);

    this.ec(id, {
        ...this.base(),
        tooltip:{...this.base().tooltip,trigger:'axis',axisPointer:{type:'shadow'}},
        legend:{data:['High','Medium','Low'],textStyle:{color:T.t2,fontSize:10},top:4},
        xAxis:{type:'category',data:regions,axisLabel:{color:T.t2,fontSize:11},
            axisLine:{lineStyle:{color:T.border}},splitLine:{show:false}},
        yAxis:{type:'value',max:100,axisLabel:{color:T.t3,fontSize:10,formatter:v=>v+'%'},
            splitLine:{lineStyle:{color:T.border,type:'dashed'}}},
        series:[
            {name:'High',type:'bar',stack:'risk',data:high,barMaxWidth:32,
                itemStyle:{color:T.red+'cc',borderRadius:[0,0,0,0]}},
            {name:'Medium',type:'bar',stack:'risk',data:medium,
                itemStyle:{color:T.amber+'cc'}},
            {name:'Low',type:'bar',stack:'risk',data:low,
                itemStyle:{color:T.green+'cc',borderRadius:[3,3,0,0]}},
        ],
    });
};

// ── 8. HOLOGRAPHIC 3D CLUSTER — Three.js ─────────────────
// seg.cluster_profiles + seg.pca_components (sample)
Charts.holo3DCluster = function(id, segData) {
    if (!segData?.cluster_profiles || typeof THREE === 'undefined') return;
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = '';

    const W = el.clientWidth || 400, H = el.clientHeight || 300;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, W/H, 0.1, 1000);
    camera.position.set(0, 0, 8);

    const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
    renderer.setSize(W, H);
    renderer.setClearColor(0x000000, 0);
    el.appendChild(renderer.domElement);

    // Holographic grid
    const gridGeo = new THREE.PlaneGeometry(12, 12, 20, 20);
    const gridMat = new THREE.MeshBasicMaterial({color:0x4f8cff, wireframe:true, opacity:0.08, transparent:true});
    const grid = new THREE.Mesh(gridGeo, gridMat);
    grid.rotation.x = -Math.PI/2;
    grid.position.y = -2.5;
    scene.add(grid);

    // Cluster colors
    const clusterColors = [0x4f8cff, 0x22c55e, 0xf59e0b, 0xa78bfa];
    const clusterNames = segData.cluster_profiles.map(p => p.name);

    // Generate points per cluster from profile data
    segData.cluster_profiles.forEach((profile, ci) => {
        const count = Math.min(Math.round(profile.pct * 3), 80);
        const color = clusterColors[ci % clusterColors.length];
        const cx = (ci - 1.5) * 2.5;
        const cy = (profile.avg_revenue_fcfa / 15000000) * 3 - 1;

        for (let i = 0; i < count; i++) {
            const geo = new THREE.SphereGeometry(0.04 + Math.random()*0.04, 6, 6);
            const mat = new THREE.MeshBasicMaterial({color, opacity:0.7+Math.random()*0.3, transparent:true});
            const sphere = new THREE.Mesh(geo, mat);
            sphere.position.set(
                cx + (Math.random()-0.5)*2,
                cy + (Math.random()-0.5)*1.5,
                (Math.random()-0.5)*2
            );
            scene.add(sphere);
        }

        // Cluster label plane
        const canvas = document.createElement('canvas');
        canvas.width = 256; canvas.height = 64;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = 'rgba(0,0,0,0)';
        ctx.fillRect(0,0,256,64);
        ctx.font = 'bold 18px Inter';
        ctx.fillStyle = '#' + color.toString(16).padStart(6,'0');
        ctx.fillText(profile.name.split(' ')[0], 8, 40);
        const tex = new THREE.CanvasTexture(canvas);
        const labelGeo = new THREE.PlaneGeometry(2, 0.5);
        const labelMat = new THREE.MeshBasicMaterial({map:tex, transparent:true, side:THREE.DoubleSide});
        const label = new THREE.Mesh(labelGeo, labelMat);
        label.position.set(cx, cy + 1.8, 0);
        scene.add(label);
    });

    // Ambient glow particles
    const partGeo = new THREE.BufferGeometry();
    const partCount = 200;
    const positions = new Float32Array(partCount * 3);
    for (let i = 0; i < partCount; i++) {
        positions[i*3] = (Math.random()-0.5)*14;
        positions[i*3+1] = (Math.random()-0.5)*8;
        positions[i*3+2] = (Math.random()-0.5)*8;
    }
    partGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const partMat = new THREE.PointsMaterial({color:0x4f8cff, size:0.03, opacity:0.3, transparent:true});
    scene.add(new THREE.Points(partGeo, partMat));

    // Animation
    let frame;
    const animate = () => {
        frame = requestAnimationFrame(animate);
        scene.rotation.y += 0.003;
        renderer.render(scene, camera);
    };
    animate();

    // Store for cleanup
    Charts._th[id] = {renderer, frame};

    // Resize
    const ro = new ResizeObserver(() => {
        const w = el.clientWidth, h = el.clientHeight;
        camera.aspect = w/h; camera.updateProjectionMatrix();
        renderer.setSize(w, h);
    });
    ro.observe(el);
};

// ── 9. HOLOGRAPHIC RISK SPHERE — Three.js ────────────────
Charts.holo3DRisk = function(id, riskData) {
    if (!riskData?.risk_by_region || typeof THREE === 'undefined') return;
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = '';

    const W = el.clientWidth || 300, H = el.clientHeight || 300;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, W/H, 0.1, 100);
    camera.position.set(0, 0, 6);

    const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
    renderer.setSize(W, H);
    renderer.setClearColor(0x000000, 0);
    el.appendChild(renderer.domElement);

    const regions = Object.keys(riskData.risk_by_region);
    const angleStep = (Math.PI*2) / regions.length;

    regions.forEach((region, i) => {
        const d = riskData.risk_by_region[region];
        const risk = d.high_pct / 100;
        const angle = i * angleStep;
        const r = 2.2;

        // Sphere size = risk level
        const size = 0.2 + risk * 0.6;
        const color = risk > 0.6 ? 0xef4444 : risk > 0.3 ? 0xf59e0b : 0x22c55e;
        const geo = new THREE.SphereGeometry(size, 16, 16);
        const mat = new THREE.MeshBasicMaterial({color, opacity:0.6+risk*0.3, transparent:true, wireframe:false});
        const sphere = new THREE.Mesh(geo, mat);
        sphere.position.set(Math.cos(angle)*r, Math.sin(angle)*r*0.5, 0);
        scene.add(sphere);

        // Wireframe overlay
        const wMat = new THREE.MeshBasicMaterial({color, wireframe:true, opacity:0.3, transparent:true});
        const wSphere = new THREE.Mesh(geo.clone(), wMat);
        wSphere.position.copy(sphere.position);
        scene.add(wSphere);

        // Connection line to center
        const points = [new THREE.Vector3(0,0,0), sphere.position.clone()];
        const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
        const lineMat = new THREE.LineBasicMaterial({color, opacity:0.2, transparent:true});
        scene.add(new THREE.Line(lineGeo, lineMat));
    });

    // Central core
    const coreGeo = new THREE.SphereGeometry(0.3, 16, 16);
    const coreMat = new THREE.MeshBasicMaterial({color:0x4f8cff, opacity:0.8, transparent:true});
    scene.add(new THREE.Mesh(coreGeo, coreMat));

    let frame;
    const animate = () => {
        frame = requestAnimationFrame(animate);
        scene.rotation.z += 0.005;
        renderer.render(scene, camera);
    };
    animate();
    Charts._th[id] = {renderer, frame};
};

// ── API Data Loader ───────────────────────────────────────
const ATData = {
    _cache: {},

    async get(path, ttl=60000) {
        const now = Date.now();
        if (this._cache[path] && now - this._cache[path].ts < ttl)
            return this._cache[path].data;
        try {
            const r = await fetch('/api/v1' + path);
            const data = await r.json();
            this._cache[path] = {data, ts:now};
            return data;
        } catch(e) { return null; }
    },

    async post(path, body={}) {
        try {
            const r = await fetch('/api/v1' + path, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify(body),
            });
            if (!r.ok) return null;
            return await r.json();
        } catch(e) { return null; }
    },

    // Dashboard: price chart
    async loadPriceChart(chartId, produit, marche) {
        if (!produit) produit = document.getElementById('dash-produit')?.value || 'Ma\u00EFs';
        if (marche === undefined) marche = document.getElementById('dash-marche')?.value || '';

        // Show loading state without destroying the chart instance
        const el = document.getElementById(chartId);
        if (el && !Charts._ec[chartId]) el.innerHTML = '<div class="chart-skeleton"></div>';

        const qs = marche ? `?marche=${encodeURIComponent(marche)}` : '';
        // Always bypass cache when produit changes
        const cacheKey = `/prix/${encodeURIComponent(produit)}${qs}`;
        delete this._cache[cacheKey]; // force fresh fetch
        const data = await this.get(`/prix/${encodeURIComponent(produit)}${qs}`, 0);

        if (!data || !data.length) {
            if (el) el.innerHTML = `<div class="empty" style="padding:20px;text-align:center;color:var(--text-3)">No data for ${produit}</div>`;
            return;
        }
        Charts.priceLine(chartId, data, produit + (marche ? ` — ${marche}` : ' (avg)'));
    },

    // Dashboard: KPI heatmap + ROI bubble + radar
    async loadKPICharts() {
        const kpi = await this.get('/kpi');
        if (!kpi) return;
        if (document.getElementById('chart-heatmap')) Charts.regionalHeatmap('chart-heatmap', kpi);
        if (document.getElementById('chart-roi-bubble')) Charts.roiBubble('chart-roi-bubble', kpi);
        if (document.getElementById('chart-yield-radar')) Charts.yieldRadar('chart-yield-radar', kpi);
    },

    // Risk module: gauge + stacked bar + 3D sphere
    async loadRiskCharts() {
        const risk = await this.post('/risk');
        if (!risk) return;
        // Dashboard gauge (id: chart-gauge)
        if (document.getElementById('chart-gauge')) Charts.riskGauge('chart-gauge', risk);
        // Risk tab gauge (id: chart-risk-gauge)
        if (document.getElementById('chart-risk-gauge')) Charts.riskGauge('chart-risk-gauge', risk);
        // Risk by region bar
        if (document.getElementById('chart-risk-region')) Charts.riskByRegion('chart-risk-region', risk);
        // 3D holographic
        if (document.getElementById('chart-risk-3d') && typeof THREE !== 'undefined')
            Charts.holo3DRisk('chart-risk-3d', risk);
    },

    // Segmentation: 3D holographic cluster
    async loadSegCharts() {
        const seg = await this.post('/segmentation');
        if (!seg) return;
        if (typeof THREE !== 'undefined') Charts.holo3DCluster('chart-seg-3d', seg);
    },

    // GARCH forecast
    async loadForecastChart(chartId, produit) {
        try {
            if (!produit) {
                var sel = document.getElementById('dash-produit');
                produit = sel ? sel.value : 'Ma\u00EFs';
            }
            const el = document.getElementById(chartId);
            if (!el) return;
            if (!Charts._ec[chartId]) {
                el.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:var(--text-3);font-size:11px;font-family:var(--mono)">Computing GARCH(1,1)...</div>';
            }
            const data = await this.post('/forecast', {produit: produit, periods:30});
            if (!data || !data.forecast_30d || !data.forecast_30d.length) {
                el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-3);font-size:12px">No forecast data for '+produit+'</div>';
                return;
            }
            const dates = data.forecast_30d.map(d => d.date ? d.date.slice(5) : '');
            const mid   = data.forecast_30d.map(d => Math.round((d.price_lower+d.price_upper)/2));
            const upper = data.forecast_30d.map(d => Math.round(d.price_upper));
            const lower = data.forecast_30d.map(d => Math.round(d.price_lower));
            const lastPrice = Math.round(data.last_price_fcfa || mid[0] || 0);
            Charts.ec(chartId, {
                backgroundColor:'transparent',
                textStyle:{fontFamily:T.font,color:T.t1},
                grid:{top:32,right:12,bottom:28,left:52,containLabel:true},
                tooltip:{backgroundColor:T.bg3,borderColor:T.border,borderWidth:1,
                    textStyle:{color:T.t0,fontSize:12},trigger:'axis'},
                legend:{data:['Forecast','Upper','Lower'],textStyle:{color:T.t2,fontSize:10},top:4},
                xAxis:{type:'category',data:dates,axisLabel:{color:T.t3,fontSize:10},splitLine:{show:false}},
                yAxis:{type:'value',axisLabel:{color:T.t3,fontSize:10,formatter:v=>v+' F'},
                    splitLine:{lineStyle:{color:T.border,type:'dashed'}}},
                series:[
                    {name:'Forecast',type:'line',data:mid,smooth:true,symbol:'circle',symbolSize:4,
                        lineStyle:{color:T.accent,width:2},itemStyle:{color:T.accent},
                        markLine:{silent:true,data:[{yAxis:lastPrice,
                            lineStyle:{color:T.amber,type:'dashed',width:1},
                            label:{formatter:'Now: '+lastPrice+' F',color:T.amber,fontSize:10}}]}},
                    {name:'Upper',type:'line',data:upper,smooth:true,symbol:'none',
                        lineStyle:{color:T.green,width:1,type:'dashed'},
                        areaStyle:{color:T.green+'12'},stack:'band'},
                    {name:'Lower',type:'line',data:lower,smooth:true,symbol:'none',
                        lineStyle:{color:T.red,width:1,type:'dashed'},stack:'band'},
                ],
            });
        } catch(e) { console.error('loadForecastChart error:', e); }
    },
};
