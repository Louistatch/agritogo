"""CPC-Togo market data acquisition and normalization.

This module implements a layered ingestion strategy:
1. Discover the browser/XHR data source with Playwright.
2. Reuse the discovered endpoint directly when possible.
3. Fall back to DOM table extraction when the endpoint is opaque.
4. Normalize both long and wide market-price tables into one observation model.

No undocumented endpoint is hard-coded. The discovery report is treated as runtime
metadata because CPC may change its front-end implementation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import requests


PRICE_WORDS = {"prix", "price", "montant", "valeur", "value", "cout", "coût"}
MARKET_WORDS = {
    "marche",
    "marché",
    "market",
    "walk",
    "pointvente",
    "point_vente",
}
PRODUCT_WORDS = {"produit", "product", "culture", "denree", "denrée", "speculation"}
DATE_WORDS = {"date", "jour", "observedat", "observed_at", "createdat", "created_at"}
UNIT_WORDS = {"unite", "unité", "unit", "conditionnement"}
CURRENCY_WORDS = {"devise", "currency", "monnaie"}
PRICE_TYPE_WORDS = {"typeprix", "type_prix", "pricetype", "price_type", "niveau", "vente"}
META_HEADERS = {
    "region", "région", "prefecture", "préfecture", "departement", "département",
    "commune", "arrondissement", "localite", "localité", "village",
    "zone", "source", "observations", "observation", "rang",
    "department", "departement", "département", "borough",
    "arrondissement", "district", "walk", "marche", "marché", "market",
}


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: Any) -> float | None:
    """Parse a price cell without turning locality labels into numbers.

    A naive parser would incorrectly read values such as "YAOUNDE 2EME" or
    "Marché 8ème" as prices. After removing known currency/unit tokens, the
    remaining value must be strictly numeric.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text or text in {"-", "—", "–", "n/a", "N/A", "null", "None"}:
        return None

    cleaned = text.replace("\u00a0", " ")
    cleaned = re.sub(
        r"(?i)\b(?:f\s*cfa|fcfa|cfa)\b",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)(?:/\s*)?(?:kg|kilogrammes?|kilos?)\b",
        "",
        cleaned,
    )
    cleaned = cleaned.replace(" ", "")

    if re.search(r"[A-Za-zÀ-ÿ]", cleaned):
        return None

    if cleaned.count(",") == 1 and cleaned.count(".") == 0:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(",") > 1 and cleaned.count(".") == 0:
        cleaned = cleaned.replace(",", "")

    if not re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


def _first_key(record: dict[str, Any], aliases: set[str]) -> str | None:
    for key in record:
        if _norm(key) in {_norm(x) for x in aliases}:
            return key
    return None


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidates = (
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d",
        "%d/%m/%y", "%d-%m-%y", "%Y-%m-%dT%H:%M:%S",
    )
    for fmt in candidates:
        try:
            dt = datetime.strptime(text[:19], fmt)
            return dt.date().isoformat()
        except ValueError:
            pass
    # Already ISO-ish with timezone.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _hash_record(*parts: Any) -> str:
    payload = "|".join("" if p is None else str(p).strip() for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class EndpointCandidate:
    url: str
    method: str = "GET"
    content_type: str = ""
    status: int = 0
    score: int = 0
    request_post_data: str | None = None
    sample: str = ""
    reason: list[str] = field(default_factory=list)
    source_page: str | None = None
    discovered_via: str = "network"


@dataclass
class DiscoveryReport:
    source_url: str
    discovered_at: str
    page_title: str = ""
    page_url: str = ""
    candidates: list[EndpointCandidate] = field(default_factory=list)
    dom_tables: list[dict[str, Any]] = field(default_factory=list)
    resource_urls: list[str] = field(default_factory=list)
    visited_pages: list[str] = field(default_factory=list)
    script_endpoint_hints: list[str] = field(default_factory=list)
    unit_hint: str | None = None
    currency_hint: str = "FCFA"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidates"] = [asdict(c) for c in self.candidates]
        return data


@dataclass
class MarketObservation:
    source: str
    source_url: str
    market_raw: str
    product_raw: str
    observed_at: str
    price: float
    unit: str = "unknown"
    currency: str = "FCFA"
    price_type: str = "unknown"
    region_raw: str | None = None
    locality_raw: str | None = None
    raw_record: dict[str, Any] = field(default_factory=dict)
    unit_inferred: bool = False
    quality_score: float = 1.0
    quality_status: str = "accepted"
    quality_reason: str | None = None

    @property
    def record_hash(self) -> str:
        return _hash_record(
            self.source,
            self.market_raw,
            self.product_raw,
            self.observed_at,
            self.price,
            self.unit,
            self.price_type,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["record_hash"] = self.record_hash
        return data


def _score_candidate(url: str, content_type: str, text: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    normalized_url = _norm(url)
    normalized_body = _norm(text[:12000])

    for word, pts in (("prix", 4), ("price", 4), ("marche", 3), ("market", 3), ("produit", 2), ("data", 1), ("api", 2), ("ajax", 1)):
        if word in normalized_url:
            score += pts
            reasons.append(f"url:{word}")

    if "json" in content_type.lower():
        score += 6
        reasons.append("content-type:json")
    if "csv" in content_type.lower():
        score += 5
        reasons.append("content-type:csv")

    body_hits = 0
    for word in ("prix", "price", "marche", "market", "produit", "product", "date"):
        if word in normalized_body:
            body_hits += 1
    if body_hits:
        score += min(body_hits * 2, 10)
        reasons.append(f"body-keywords:{body_hits}")

    try:
        payload = json.loads(text)
        score += 3
        reasons.append("valid-json")
        if _find_record_lists(payload):
            score += 8
            reasons.append("record-list")
    except Exception:
        pass

    return score, reasons



def _same_site(candidate_url: str, root_host: str) -> bool:
    host = urlparse(candidate_url).netloc.lower().removeprefix("www.")
    return host == root_host or host.endswith("." + root_host)


def _market_relevance(text: str) -> int:
    value = _norm(text)
    score = 0
    for token, weight in (
        ("sim", 3),
        ("prix", 5),
        ("price", 5),
        ("marche", 5),
        ("market", 5),
        ("agric", 2),
        ("produit", 2),
        ("culture", 2),
        ("cours", 2),
    ):
        if token in value:
            score += weight
    return score


def _extract_script_endpoint_hints(script_text: str, base_url: str) -> list[str]:
    """Extract likely public data endpoints embedded in front-end JavaScript."""
    if not script_text:
        return []

    patterns = [
        r"""fetch\s*\(\s*["']([^"']+)["']""",
        r"""axios\.(?:get|post|request)\s*\(\s*["']([^"']+)["']""",
        r"""\$\.(?:get|getJSON|post)\s*\(\s*["']([^"']+)["']""",
        r"""url\s*:\s*["']([^"']+)["']""",
        r"""["']([^"']*(?:/api/|/ajax/|prix|price|marche|market)[^"']*)["']""",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, script_text, re.I):
            value = str(match).strip()
            if not value or value.startswith(("data:", "javascript:", "#")):
                continue
            if ("$" + "{") in value or "{{" in value:
                continue
            absolute = urljoin(base_url, value)
            parsed = urlparse(absolute)
            if parsed.scheme in {"http", "https"}:
                found.append(absolute)
    return list(dict.fromkeys(found))


async def discover_cpc_source(
    url: str = "https://www.cpc-togo.com/",
    browser_ws_endpoint: str | None = None,
    settle_seconds: float = 6.0,
) -> DiscoveryReport:
    """Discover CPC sources using network traffic, scripts and safe UI probes."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for discovery. Install requirements-ingestion.txt "
            "and run: playwright install chromium"
        ) from exc

    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    candidates: list[EndpointCandidate] = []
    candidate_keys: set[tuple[str, str]] = set()
    pending: list[asyncio.Task[Any]] = []
    dom_tables: list[dict[str, Any]] = []
    resource_urls: list[str] = []
    visited_pages: list[str] = []
    script_endpoint_hints: list[str] = []
    all_page_text: list[str] = []

    async with async_playwright() as p:
        browser = (
            await p.chromium.connect_over_cdp(browser_ws_endpoint)
            if browser_ws_endpoint
            else await p.chromium.launch(headless=True)
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124 Safari/537.36 AgriTogoData/1.0"
            ),
            locale="fr-FR",
        )
        page = await context.new_page()

        def add_candidate(candidate: EndpointCandidate) -> None:
            key = (candidate.method.upper(), candidate.url)
            if key in candidate_keys:
                for idx, current in enumerate(candidates):
                    if (
                        current.method.upper(),
                        current.url,
                    ) == key and candidate.score > current.score:
                        candidates[idx] = candidate
                        break
                return
            candidate_keys.add(key)
            candidates.append(candidate)

        async def capture(response: Any) -> None:
            request = response.request
            ctype = (await response.all_headers()).get("content-type", "")
            rurl = response.url
            same_family = _same_site(rurl, host)
            interesting = (
                same_family
                or "json" in ctype.lower()
                or "csv" in ctype.lower()
                or any(
                    token in _norm(rurl)
                    for token in (
                        "prix",
                        "price",
                        "market",
                        "marche",
                        "api",
                        "ajax",
                        "data",
                    )
                )
            )
            if not interesting:
                return

            body = ""
            try:
                raw = await response.body()
                if len(raw) <= 3_000_000:
                    body = raw.decode("utf-8", errors="replace")
            except Exception:
                pass

            score, reasons = _score_candidate(rurl, ctype, body)
            if score >= 4:
                post_data = request.post_data
                if post_data and re.search(
                    r"(password|token|secret|authorization)",
                    post_data,
                    re.I,
                ):
                    post_data = None
                add_candidate(
                    EndpointCandidate(
                        url=rurl,
                        method=request.method,
                        content_type=ctype,
                        status=response.status,
                        score=score,
                        request_post_data=post_data,
                        sample=body[:4000],
                        reason=reasons,
                        source_page=page.url,
                        discovered_via="network",
                    )
                )

            if "javascript" in ctype.lower() or rurl.lower().endswith(".js"):
                for hint in _extract_script_endpoint_hints(body, rurl):
                    if not _same_site(hint, host):
                        continue
                    if hint not in script_endpoint_hints:
                        script_endpoint_hints.append(hint)
                    hint_score = 6 + _market_relevance(hint)
                    if hint_score >= 8:
                        add_candidate(
                            EndpointCandidate(
                                url=hint,
                                method="GET",
                                content_type="application/x-endpoint-hint",
                                status=0,
                                score=hint_score,
                                sample="",
                                reason=["javascript-endpoint-hint"],
                                source_page=page.url,
                                discovered_via="javascript",
                            )
                        )

        def schedule_capture(response: Any) -> None:
            pending.append(asyncio.create_task(capture(response)))

        page.on("response", schedule_capture)

        async def collect_page_snapshot() -> None:
            current_url = page.url
            if current_url not in visited_pages:
                visited_pages.append(current_url)

            try:
                text = (await page.locator("body").inner_text())[:50_000]
            except Exception:
                text = ""
            all_page_text.append(text)

            try:
                resources = await page.evaluate(
                    "() => performance.getEntriesByType('resource').map(x => x.name)"
                )
                resource_urls.extend(resources)
            except Exception:
                pass

            try:
                tables = await page.evaluate(
                    """() => Array.from(document.querySelectorAll('table')).map((table, idx) => {
                        const rows = Array.from(table.querySelectorAll('tr'));
                        const matrix = rows.map(row => Array.from(row.querySelectorAll('th,td'))
                            .map(cell => (cell.innerText || '').trim()));
                        if (!matrix.length) return null;
                        let headers = matrix[0];
                        let data = matrix.slice(1);
                        const thead = Array.from(table.querySelectorAll('thead th'))
                            .map(x => (x.innerText || '').trim());
                        if (thead.length) {
                            headers = thead;
                            const bodyRows = Array.from(table.querySelectorAll('tbody tr'));
                            data = bodyRows.map(row => Array.from(row.querySelectorAll('td'))
                                .map(cell => (cell.innerText || '').trim()));
                        }
                        return {
                            index: idx,
                            page_url: window.location.href,
                            headers,
                            rows: data.slice(0, 1000)
                        };
                    }).filter(Boolean)"""
                )
                dom_tables.extend(tables)
            except Exception:
                pass

            try:
                inline_scripts = await page.locator(
                    "script:not([src])"
                ).all_text_contents()
                for script in inline_scripts:
                    for hint in _extract_script_endpoint_hints(
                        script,
                        current_url,
                    ):
                        if (
                            _same_site(hint, host)
                            and hint not in script_endpoint_hints
                        ):
                            script_endpoint_hints.append(hint)
                            add_candidate(
                                EndpointCandidate(
                                    url=hint,
                                    method="GET",
                                    content_type=(
                                        "application/x-endpoint-hint"
                                    ),
                                    status=0,
                                    score=7 + _market_relevance(hint),
                                    reason=[
                                        "inline-script-endpoint-hint",
                                    ],
                                    source_page=current_url,
                                    discovered_via="javascript",
                                )
                            )
            except Exception:
                pass

        async def settle() -> None:
            try:
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=20_000,
                )
            except Exception:
                pass
            await page.wait_for_timeout(int(settle_seconds * 1000))
            if pending:
                await asyncio.gather(
                    *pending,
                    return_exceptions=True,
                )

        async def safe_filter_probe() -> None:
            selects = page.locator("select")
            try:
                count = min(await selects.count(), 4)
            except Exception:
                count = 0
            for idx in range(count):
                select = selects.nth(idx)
                try:
                    options = await select.locator("option").evaluate_all(
                        """els => els.map((o, i) => ({
                            index:i, value:o.value, text:(o.innerText||'').trim(),
                            disabled:o.disabled
                        }))"""
                    )
                    usable = [
                        item
                        for item in options
                        if (
                            not item["disabled"]
                            and str(item["value"]).strip()
                            and _norm(item["text"])
                            not in {
                                "choisir",
                                "selectionner",
                                "tous",
                                "tout",
                            }
                        )
                    ]
                    if usable:
                        await select.select_option(
                            value=str(usable[0]["value"])
                        )
                        await page.wait_for_timeout(900)
                except Exception:
                    continue

            safe_pattern = re.compile(
                (
                    r"(afficher|rechercher|chercher|filtrer|actualiser|"
                    r"consulter|voir|charger)"
                ),
                re.I,
            )
            buttons = page.locator(
                "button, input[type=submit], a"
            )
            try:
                count = min(await buttons.count(), 120)
            except Exception:
                count = 0
            clicked = 0
            for idx in range(count):
                if clicked >= 4:
                    break
                node = buttons.nth(idx)
                try:
                    is_input = await node.evaluate(
                        "(el) => el.tagName === 'INPUT'"
                    )
                    text = (
                        await node.get_attribute("value")
                        if is_input
                        else await node.inner_text()
                    ) or ""
                    href = await node.get_attribute("href")
                    if href:
                        continue
                    if safe_pattern.search(text) is None:
                        continue
                    if re.search(
                        (
                            r"(supprimer|delete|envoyer|payer|"
                            r"connexion|login|inscrire)"
                        ),
                        text,
                        re.I,
                    ):
                        continue
                    if not await node.is_visible():
                        continue
                    await node.click(timeout=3000)
                    clicked += 1
                    await page.wait_for_timeout(1200)
                except Exception:
                    continue

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        await settle()
        page_title = await page.title()
        await collect_page_snapshot()

        try:
            links = await page.locator("a[href]").evaluate_all(
                """els => els.map(a => ({
                    href: a.href,
                    text: (a.innerText || a.getAttribute('aria-label') || '').trim()
                }))"""
            )
        except Exception:
            links = []

        relevant_pages: list[tuple[int, str]] = []
        for item in links:
            href = str(item.get("href") or "")
            text = str(item.get("text") or "")
            if not href or not _same_site(href, host):
                continue
            score = _market_relevance(href + " " + text)
            if score >= 3:
                relevant_pages.append((score, href))

        ordered_pages = [url]
        for _, href in sorted(
            relevant_pages,
            reverse=True,
        ):
            if href not in ordered_pages:
                ordered_pages.append(href)
        ordered_pages = ordered_pages[:8]

        for target in ordered_pages:
            if target != page.url:
                try:
                    await page.goto(
                        target,
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )
                    await settle()
                except Exception:
                    continue
            await safe_filter_probe()
            await settle()
            await collect_page_snapshot()

        if pending:
            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )

        page_url = page.url
        joined_text = "\n".join(all_page_text)
        unit_hint = None
        norm_text = _norm(joined_text)
        if (
            re.search(
                r"(fcfa|fca|cfa).{0,12}(kg|kilogram)",
                joined_text,
                re.I | re.S,
            )
            or "prixkg" in norm_text
        ):
            unit_hint = "kg"

        await context.close()
        await browser.close()

    candidates.sort(
        key=lambda item: item.score,
        reverse=True,
    )
    return DiscoveryReport(
        source_url=url,
        discovered_at=_now_iso(),
        page_title=page_title,
        page_url=page_url,
        candidates=candidates[:50],
        dom_tables=dom_tables[:100],
        resource_urls=list(
            dict.fromkeys(resource_urls)
        )[:1000],
        visited_pages=list(
            dict.fromkeys(visited_pages)
        ),
        script_endpoint_hints=script_endpoint_hints[:200],
        unit_hint=unit_hint,
        currency_hint="FCFA",
    )

def fetch_candidate(candidate: dict[str, Any], timeout: int = 30) -> tuple[str, str]:
    """Fetch a discovered public endpoint directly after browser discovery."""
    url = candidate["url"]
    method = (candidate.get("method") or "GET").upper()
    headers = {
        "User-Agent": "AgriTogoData/1.0 (+market intelligence; respectful polling)",
        "Accept": "application/json,text/csv,text/plain,text/html;q=0.8,*/*;q=0.5",
        "Referer": "https://www.cpc-togo.com/",
    }
    kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
    post_data = candidate.get("request_post_data")
    if method == "POST" and post_data:
        if post_data.lstrip().startswith(("{", "[")):
            try:
                kwargs["json"] = json.loads(post_data)
            except json.JSONDecodeError:
                kwargs["data"] = post_data
        else:
            kwargs["data"] = post_data

    response = requests.request(method, url, **kwargs)
    response.raise_for_status()
    return response.text, response.headers.get("content-type", "")


def _find_record_lists(payload: Any, depth: int = 0) -> list[list[dict[str, Any]]]:
    """Find JSON arrays that look like records without assuming one API schema."""
    if depth > 8:
        return []
    found: list[list[dict[str, Any]]] = []
    if isinstance(payload, list) and payload and all(isinstance(x, dict) for x in payload[:20]):
        found.append(payload)
    if isinstance(payload, dict):
        for value in payload.values():
            found.extend(_find_record_lists(value, depth + 1))
    elif isinstance(payload, list):
        for value in payload[:100]:
            if isinstance(value, (dict, list)):
                found.extend(_find_record_lists(value, depth + 1))
    return found


def _records_from_json(text: str) -> list[dict[str, Any]]:
    payload = json.loads(text)
    lists = _find_record_lists(payload)
    if not lists:
        return []
    # Prefer the largest record list; market feeds are usually tabular.
    return max(lists, key=len)


def _detect_field(record: dict[str, Any], aliases: set[str]) -> str | None:
    norms = {_norm(x) for x in aliases}
    for key in record:
        if _norm(key) in norms:
            return key
    return None


def _wide_product_keys(record: dict[str, Any], excluded: Iterable[str]) -> list[str]:
    excluded_norm = {_norm(x) for x in excluded}
    product_keys: list[str] = []
    for key, value in record.items():
        nk = _norm(key)
        if nk in excluded_norm or nk in {_norm(x) for x in META_HEADERS}:
            continue
        if _money(value) is not None:
            product_keys.append(key)
    return product_keys


def normalize_records(
    records: list[dict[str, Any]],
    source_url: str,
    source: str = "SIM-CPC",
    unit_hint: str | None = None,
) -> list[MarketObservation]:
    """Normalize long or wide records into one observation per product/market/date."""
    observations: list[MarketObservation] = []
    if not records:
        return observations

    sample = records[0]
    market_key = _detect_field(sample, MARKET_WORDS)
    date_key = _detect_field(sample, DATE_WORDS)
    product_key = _detect_field(sample, PRODUCT_WORDS)
    price_key = _detect_field(sample, PRICE_WORDS)
    unit_key = _detect_field(sample, UNIT_WORDS)
    currency_key = _detect_field(sample, CURRENCY_WORDS)
    price_type_key = _detect_field(sample, PRICE_TYPE_WORDS)
    region_key = next((k for k in sample if _norm(k) in {"region"}), None)
    locality_key = next(
        (k for k in sample if _norm(k) in {"localite", "commune", "ville", "village"}),
        None,
    )

    for row in records:
        market = str(row.get(market_key, "") if market_key else "").strip()
        observed = _iso_date(row.get(date_key) if date_key else None)

        # Long form: one product + one price per row.
        if product_key and price_key:
            price = _money(row.get(price_key))
            product = str(row.get(product_key, "")).strip()
            if price is not None:
                observations.append(
                    _build_observation(
                        source=source,
                        source_url=source_url,
                        market=market,
                        product=product,
                        observed=observed,
                        price=price,
                        unit=(str(row.get(unit_key, "")).strip() if unit_key else "") or unit_hint,
                        currency=(str(row.get(currency_key, "")).strip() if currency_key else "") or "FCFA",
                        price_type=(str(row.get(price_type_key, "")).strip() if price_type_key else "") or "unknown",
                        region=str(row.get(region_key, "")).strip() if region_key else None,
                        locality=str(row.get(locality_key, "")).strip() if locality_key else None,
                        raw=row,
                        unit_inferred=bool(unit_hint and not unit_key),
                    )
                )
            continue

        # Wide form: market/date columns + one numeric column per product.
        excluded = [
            key for key in (
                market_key, date_key, unit_key, currency_key, price_type_key,
                region_key, locality_key,
            ) if key
        ]
        for key in _wide_product_keys(row, excluded):
            price = _money(row.get(key))
            if price is None:
                continue
            observations.append(
                _build_observation(
                    source=source,
                    source_url=source_url,
                    market=market,
                    product=str(key).strip(),
                    observed=observed,
                    price=price,
                    unit=unit_hint,
                    currency="FCFA",
                    price_type="unknown",
                    region=str(row.get(region_key, "")).strip() if region_key else None,
                    locality=str(row.get(locality_key, "")).strip() if locality_key else None,
                    raw=row,
                    unit_inferred=bool(unit_hint),
                )
            )

    deduped: dict[str, MarketObservation] = {}
    for obs in observations:
        deduped.setdefault(obs.record_hash, obs)
    return list(deduped.values())


def normalize_dom_tables(
    tables: list[dict[str, Any]],
    source_url: str,
    source: str = "SIM-CPC",
    unit_hint: str | None = None,
) -> list[MarketObservation]:
    observations: list[MarketObservation] = []
    for table in tables:
        headers = [str(x).strip() for x in table.get("headers", [])]
        if not headers:
            continue
        records = []
        for row in table.get("rows", []):
            values = list(row) + [""] * max(0, len(headers) - len(row))
            records.append(dict(zip(headers, values[: len(headers)])))
        observations.extend(normalize_records(records, source_url, source, unit_hint))
    deduped: dict[str, MarketObservation] = {}
    for obs in observations:
        deduped.setdefault(obs.record_hash, obs)
    return list(deduped.values())


def normalize_payload(
    text: str,
    content_type: str,
    source_url: str,
    source: str = "SIM-CPC",
    unit_hint: str | None = None,
) -> list[MarketObservation]:
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        try:
            return normalize_records(_records_from_json(text), source_url, source, unit_hint)
        except Exception:
            return []
    return []


def _build_observation(
    *,
    source: str,
    source_url: str,
    market: str,
    product: str,
    observed: str | None,
    price: float,
    unit: str | None,
    currency: str,
    price_type: str,
    region: str | None,
    locality: str | None,
    raw: dict[str, Any],
    unit_inferred: bool,
) -> MarketObservation:
    quality = 1.0
    reasons: list[str] = []

    if not market:
        quality -= 0.35
        reasons.append("missing_market")
    if not product:
        quality -= 0.35
        reasons.append("missing_product")
    if not observed:
        quality -= 0.25
        reasons.append("missing_date")
    if price <= 0:
        quality -= 0.60
        reasons.append("invalid_price")
    if not unit:
        unit = "unknown"
        quality -= 0.12
        reasons.append("unknown_unit")
    if unit_inferred:
        quality -= 0.05
        reasons.append("unit_inferred")

    status = "accepted"
    if not market or not product or not observed or price <= 0:
        status = "needs_review" if price > 0 else "rejected"

    return MarketObservation(
        source=source,
        source_url=source_url,
        market_raw=market,
        product_raw=product,
        observed_at=observed or datetime.now(timezone.utc).date().isoformat(),
        price=price,
        unit=unit,
        currency=currency or "FCFA",
        price_type=price_type or "unknown",
        region_raw=region or None,
        locality_raw=locality or None,
        raw_record=raw,
        unit_inferred=unit_inferred,
        quality_score=max(0.0, round(quality, 3)),
        quality_status=status,
        quality_reason=",".join(reasons) or None,
    )


def extract_from_discovery(report: DiscoveryReport) -> tuple[list[MarketObservation], dict[str, Any]]:
    """Use the best discovered source, falling back to rendered DOM tables."""
    attempts: list[dict[str, Any]] = []

    for candidate in report.candidates:
        if candidate.score < 10:
            continue
        try:
            text, ctype = fetch_candidate(asdict(candidate))
            observations = normalize_payload(
                text,
                ctype,
                candidate.url,
                source="SIM-CPC",
                unit_hint=report.unit_hint,
            )
            attempts.append({
                "url": candidate.url,
                "score": candidate.score,
                "observations": len(observations),
                "mode": "direct_endpoint",
            })
            if observations:
                return observations, {
                    "mode": "direct_endpoint",
                    "endpoint": candidate.url,
                    "attempts": attempts,
                    "raw_text": text[:500_000],
                    "content_type": ctype,
                }
        except Exception as exc:
            attempts.append({
                "url": candidate.url,
                "score": candidate.score,
                "observations": 0,
                "mode": "direct_endpoint",
                "error": str(exc)[:300],
            })

    observations = normalize_dom_tables(
        report.dom_tables,
        report.page_url or report.source_url,
        source="SIM-CPC",
        unit_hint=report.unit_hint,
    )
    return observations, {
        "mode": "browser_dom",
        "endpoint": report.page_url or report.source_url,
        "attempts": attempts,
        "raw_text": json.dumps(report.dom_tables, ensure_ascii=False)[:500_000],
        "content_type": "application/json+dom-table",
    }
