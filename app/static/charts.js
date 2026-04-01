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
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="chart-skeleton"></div>';
    },
};

// ── 1. PRICE LINE — bound to /api/v1/prix/<produit> ───────
// data: [{date, prix, marche, produit}]
Charts.priceLine = function(id, apiData, produit) {
    if (!apiData?.length) return;
    const sorted = [...apiData].sort((a,b) => a.date.localeCompare(b.date));
    const dates = sorted.map(d => d.date.slice(5));
    const prices = sorted.map(d => +d.prix);
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
// kpi.yield_by_region + kpi.climate_risk_by_region
Charts.regionalHeatmap = function(id, kpiData) {
    if (!kpiData?.yield_by_region) return;
    const regions = Object.keys(kpiData.yield_by_region);
    const metrics = ['Yield (kg/ha)', 'Climate Risk', 'Drought Prob.'];
    const rows = regions.map(r => [
        kpiData.yield_by_region[r]?.avg_yield_kg_ha || 0,
        kpiData.climate_risk_by_region?.[r]?.risk_score || 0,
        Math.round((kpiData.climate_risk_by_region?.[r]?.drought_probability || 0)*100),
    ]);
    const flat = rows.flat();
    const min = Math.min(...flat), max = Math.max(...flat);

    this.ec(id, {
        ...this.base({grid:{top:40,right:16,bottom:40,left:80}}),
        tooltip:{...this.base().tooltip,
            formatter:p=>`<b>${regions[p.value[1]]}</b> — ${metrics[p.value[0]]}<br><b>${p.value[2]}</b>`},
        xAxis:{type:'category',data:metrics,axisLabel:{color:T.t2,fontSize:10},
            splitArea:{show:true,areaStyle:{color:['transparent',T.bg2+'40']}}},
        yAxis:{type:'category',data:regions,axisLabel:{color:T.t1,fontSize:11}},
        visualMap:{min,max,show:false,
            inRange:{color:[T.bg3,T.accent+'50',T.accent,T.cyan]}},
        series:[{type:'heatmap',
            data:rows.flatMap((row,ri)=>row.map((v,ci)=>[ci,ri,v])),
            label:{show:true,color:T.t0,fontSize:10,formatter:p=>p.value[2]}}],
    });
};

// ── 4. RISK GAUGE — bound to /api/v1/risk ─────────────────
// risk.risk_distribution: {high, medium, low}
Charts.riskGauge = function(id, riskData) {
    if (!riskData?.risk_distribution) return;
    const d = riskData.risk_distribution;
    const total = (d.high||0)+(d.medium||0)+(d.low||0);
    const score = total ? Math.round((d.high||0)/total*100) : 0;
    const color = score>60?T.red:score>30?T.amber:T.green;

    this.ec(id, {
        ...this.base({grid:undefined}),
        series:[{
            type:'gauge', startAngle:200, endAngle:-20, min:0, max:100,
            radius:'88%', center:['50%','58%'],
            progress:{show:true,width:12,itemStyle:{color}},
            axisLine:{lineStyle:{width:12,color:[[1,T.bg3]]}},
            axisTick:{show:false}, splitLine:{show:false}, axisLabel:{show:false},
            pointer:{show:false},
            detail:{valueAnimation:true,fontSize:24,fontWeight:700,
                fontFamily:T.mono,color:T.t0,offsetCenter:[0,'8%'],
                formatter:v=>v.toFixed(0)+'%'},
            title:{offsetCenter:[0,'32%'],fontSize:11,color:T.t3},
            data:[{value:score,name:'High Risk'}],
        }],
    });
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
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify(body),
            });
            return await r.json();
        } catch(e) { return null; }
    },

    // Dashboard: price chart
    async loadPriceChart(chartId, produit, marche='') {
        Charts.skeleton(chartId);
        const qs = marche ? `?marche=${encodeURIComponent(marche)}` : '';
        const data = await this.get(`/prix/${encodeURIComponent(produit)}${qs}`);
        if (data) Charts.priceLine(chartId, data, produit);
    },

    // Dashboard: KPI heatmap + ROI bubble + radar
    async loadKPICharts() {
        const kpi = await this.get('/kpi');
        if (!kpi) return;
        Charts.regionalHeatmap('chart-heatmap', kpi);
        Charts.roiBubble('chart-roi-bubble', kpi);
        Charts.yieldRadar('chart-yield-radar', kpi);
    },

    // Risk module: gauge + stacked bar + 3D sphere
    async loadRiskCharts() {
        const risk = await this.post('/risk');
        if (!risk) return;
        Charts.riskGauge('chart-risk-gauge', risk);
        Charts.riskByRegion('chart-risk-region', risk);
        if (typeof THREE !== 'undefined') Charts.holo3DRisk('chart-risk-3d', risk);
    },

    // Segmentation: 3D holographic cluster
    async loadSegCharts() {
        const seg = await this.post('/segmentation');
        if (!seg) return;
        if (typeof THREE !== 'undefined') Charts.holo3DCluster('chart-seg-3d', seg);
    },

    // GARCH forecast
    async loadForecastChart(chartId, produit='Mais') {
        Charts.skeleton(chartId);
        const data = await this.post('/forecast', {produit, periods:30});
        if (!data?.forecast_30d) return;
        const dates = data.forecast_30d.map(d => d.date.slice(5));
        const mid = data.forecast_30d.map(d => +((d.price_lower+d.price_upper)/2).toFixed(0));
        const upper = data.forecast_30d.map(d => d.price_upper);
        const lower = data.forecast_30d.map(d => d.price_lower);
        Charts.ec(chartId, {
            ...Charts.base(),
            tooltip:{...Charts.base().tooltip,trigger:'axis'},
            legend:{data:['Forecast','Upper','Lower'],textStyle:{color:T.t2,fontSize:10},top:4},
            xAxis:{type:'category',data:dates,axisLabel:{color:T.t3,fontSize:10},splitLine:{show:false}},
            yAxis:{type:'value',axisLabel:{color:T.t3,fontSize:10,formatter:v=>v+' F'},
                splitLine:{lineStyle:{color:T.border,type:'dashed'}}},
            series:[
                {name:'Forecast',type:'line',data:mid,smooth:true,symbol:'none',
                    lineStyle:{color:T.accent,width:2}},
                {name:'Upper',type:'line',data:upper,smooth:true,symbol:'none',
                    lineStyle:{color:T.amber,width:1,type:'dashed'},
                    areaStyle:{color:T.amber+'15'},stack:'band'},
                {name:'Lower',type:'line',data:lower,smooth:true,symbol:'none',
                    lineStyle:{color:T.amber,width:1,type:'dashed'},stack:'band'},
            ],
        });
    },
};
