(function () {
    const state = { product: "", market: "", overview: null };

    function el(id) { return document.getElementById(id); }
    function money(value) {
        const n = Number(value);
        return Number.isFinite(n) ? new Intl.NumberFormat("fr-FR").format(Math.round(n)) : "—";
    }
    function dateLabel(value) {
        if (!value) return "Date non disponible";
        try { return new Intl.DateTimeFormat("fr-FR", {day:"2-digit", month:"short", year:"numeric"}).format(new Date(value+"T00:00:00")); }
        catch (_) { return value; }
    }
    function deltaClass(v) { return v > 0 ? "up" : v < 0 ? "down" : "flat"; }
    function deltaText(v) {
        const n = Number(v || 0);
        return (n > 0 ? "+" : "") + n.toFixed(1) + " % / 30 j";
    }

    async function getJSON(url) {
        const r = await fetch(url, {headers: {"Accept":"application/json"}});
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        if (data && data.error) throw new Error(data.error);
        return data;
    }

    function chosenMarket(markets) {
        if (!markets || !markets.length) return null;
        const select = el("market-place");
        const wanted = select ? select.value : "";
        if (wanted) {
            const exact = markets.find(m => m.marche === wanted);
            if (exact) return exact;
            const fuzzy = markets.find(m => String(m.marche).toLowerCase().includes(wanted.toLowerCase()));
            if (fuzzy) return fuzzy;
        }
        return markets[0];
    }

    function renderSnapshot(row) {
        if (!row) {
            el("market-price-value").innerHTML = "— <small>FCFA/kg</small>";
            el("market-price-delta").textContent = "Aucune observation";
            el("market-price-source").textContent = "Source indisponible";
            return;
        }
        el("market-price-value").innerHTML = money(row.prix) + ' <small>' + (row.devise || "FCFA") + "/" + (row.unite || "kg") + "</small>";
        const delta = el("market-price-delta");
        delta.textContent = deltaText(row.variation_30j);
        delta.className = "market-delta " + deltaClass(Number(row.variation_30j || 0));
        el("market-price-market").textContent = row.marche || "Marché";
        el("market-price-date").textContent = dateLabel(row.date);
        el("market-price-min").textContent = money(row.prix_min) + " FCFA";
        el("market-price-max").textContent = money(row.prix_max) + " FCFA";
        el("market-price-source").textContent = row.source || "AgriTogo";
        el("market-observation-count").textContent = (row.observations || 0) + " observations";
        state.market = row.marche || "";
    }

    function renderRanking(markets) {
        const host = el("market-ranking");
        if (!host) return;
        if (!markets || !markets.length) {
            host.innerHTML = '<div class="market-rank-empty">Aucune observation disponible pour ce produit.</div>';
            return;
        }
        host.innerHTML = markets.map((m, index) => {
            const sign = Number(m.variation_30j || 0);
            return '<div class="market-row" data-market="' + String(m.marche).replace(/"/g, "&quot;") + '">' +
                '<div><div class="name">' + (index + 1) + '. ' + m.marche + '</div><div class="market-kicker">' + (m.source || "AgriTogo") + '</div></div>' +
                '<div class="price">' + money(m.prix) + ' F</div>' +
                '<div class="market-delta ' + deltaClass(sign) + '">' + (sign > 0 ? "+" : "") + sign.toFixed(1) + '%</div>' +
                '<div class="date">' + dateLabel(m.date) + '</div></div>';
        }).join("");
        host.querySelectorAll(".market-row").forEach(row => {
            row.addEventListener("click", () => {
                const name = row.getAttribute("data-market");
                const select = el("market-place");
                if (select) {
                    const option = Array.from(select.options).find(o => o.value === name || name.includes(o.value));
                    if (option) select.value = option.value;
                }
                const selected = markets.find(m => m.marche === name);
                renderSnapshot(selected);
                renderChart();
            });
        });
    }

    async function renderChart() {
        const product = state.product || (el("market-product") ? el("market-product").value : "");
        const market = state.market || (el("market-place") ? el("market-place").value : "");
        if (!product || !window.Charts) return;
        try {
            const q = market ? "?marche=" + encodeURIComponent(market) : "";
            const data = await getJSON("/api/v1/prix/" + encodeURIComponent(product) + q);
            if (Array.isArray(data) && data.length) {
                Charts.priceLine("market-price-chart", data, product);
                setTimeout(function(){ if (Charts._ec && Charts._ec["market-price-chart"]) Charts._ec["market-price-chart"].resize(); }, 120);
            } else {
                const chart = el("market-price-chart");
                if (chart) chart.innerHTML = '<div class="market-rank-empty">Pas assez de données historiques pour tracer une évolution.</div>';
            }
        } catch (err) {
            const chart = el("market-price-chart");
            if (chart) chart.innerHTML = '<div class="market-rank-empty">Historique indisponible.</div>';
        }
    }

    async function load() {
        const product = el("market-product") ? el("market-product").value : "";
        if (!product) return;
        state.product = product;
        const host = el("market-ranking");
        if (host) host.innerHTML = '<div class="market-rank-empty">Chargement des observations…</div>';
        try {
            const overview = await getJSON("/api/v1/market-intelligence/" + encodeURIComponent(product));
            state.overview = overview;
            const markets = overview.markets || [];
            const selected = chosenMarket(markets);
            renderSnapshot(selected);
            renderRanking(markets);
            await renderChart();
        } catch (err) {
            if (host) host.innerHTML = '<div class="market-rank-empty">Impossible de charger les données de marché.</div>';
            console.error("AgriMarket:", err);
        }
    }

    function quickAsk(kind) {
        const product = state.product || (el("market-product") ? el("market-product").value : "ce produit");
        const market = state.market || (el("market-place") ? el("market-place").value : "");
        const context = market ? " à " + market : " au Togo";
        const prompts = {
            sell: "Analyse les observations disponibles pour " + product + context + ". Dois-je vendre maintenant ou attendre ? Sépare clairement données observées, calculs et prévisions. Cite la date et la source des prix utilisés.",
            where: "Pour " + product + ", compare les marchés disponibles et indique les écarts de prix observés. Ne recommande pas seulement le prix brut : explique aussi les coûts de transport à vérifier avant décision.",
            store: "Pour " + product + context + ", compare vendre maintenant et stocker. Utilise les prix observés comme base, indique ce qui est prévision ou hypothèse et les principaux risques de stockage."
        };
        const message = prompts[kind] || prompts.sell;
        if (typeof window.showTab === "function") window.showTab("analyst");
        setTimeout(function(){
            if (typeof window.engineAsk === "function") window.engineAsk(message);
        }, 80);
    }

    window.AgriMarket = { load, quickAsk, state };

    document.addEventListener("DOMContentLoaded", function(){
        const product = el("market-product");
        const place = el("market-place");
        if (product) product.addEventListener("change", load);
        if (place) place.addEventListener("change", function(){
            if (state.overview) {
                const row = chosenMarket(state.overview.markets || []);
                renderSnapshot(row);
                renderChart();
            } else load();
        });
        document.querySelectorAll('[onclick*="showTab(\'markets\')"]').forEach(function(link){
            link.addEventListener("click", function(){ setTimeout(load, 120); });
        });
    });
})();