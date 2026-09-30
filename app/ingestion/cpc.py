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
from urllib.parse import urlparse

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


@dataclass
class DiscoveryReport:
    source_url: str
    discovered_at: str
    page_title: str = ""
    page_url: str = ""
    candidates: list[EndpointCandidate] = field(default_factory=list)
    dom_tables: list[dict[str, Any]] = field(default_factory=list)
    resource_urls: list[str] = field(default_factory=list)
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


async def discover_cpc_source(
    url: str = "https://www.cpc-togo.com/",
    browser_ws_endpoint: str | None = None,
    settle_seconds: float = 6.0,
) -> DiscoveryReport:
    """Discover the page's real market-data sources through browser network traffic.

    If browser_ws_endpoint is provided, Playwright connects to that remote CDP
    browser (Browserbase/Browserless compatible). Otherwise it launches local
    Chromium. Only response metadata and small public payload samples are saved.
    """
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
    seen: set[tuple[str, str]] = set()
    pending: list[asyncio.Task[Any]] = []

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

        async def capture(response: Any) -> None:
            request = response.request
            ctype = (await response.all_headers()).get("content-type", "")
            rurl = response.url
            rhost = urlparse(rurl).netloc.lower().removeprefix("www.")
            same_family = rhost == host or rhost.endswith("." + host)
            interesting = (
                same_family
                or "json" in ctype.lower()
                or any(token in _norm(rurl) for token in ("prix", "price", "market", "marche", "api", "ajax", "data"))
            )
            if not interesting:
                return
            key = (request.method, rurl)
            if key in seen:
                return
            seen.add(key)

            body = ""
            try:
                raw = await response.body()
                if len(raw) <= 2_000_000:
                    body = raw.decode("utf-8", errors="replace")
            except Exception:
                pass

            score, reasons = _score_candidate(rurl, ctype, body)
            if score >= 4:
                post_data = request.post_data
                # Never persist obvious credentials/tokens from POST bodies.
                if post_data and re.search(r"(password|token|secret|authorization)", post_data, re.I):
                    post_data = None
                candidates.append(
                    EndpointCandidate(
                        url=rurl,
                        method=request.method,
                        content_type=ctype,
                        status=response.status,
                        score=score,
                        request_post_data=post_data,
                        sample=body[:4000],
                        reason=reasons,
                    )
                )

        def schedule_capture(response: Any) -> None:
            pending.append(asyncio.create_task(capture(response)))

        page.on("response", schedule_capture)
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        await page.wait_for_timeout(int(settle_seconds * 1000))

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        page_title = await page.title()
        page_url = page.url
        page_text = (await page.locator("body").inner_text())[:25_000]

        resource_urls = await page.evaluate(
            """() => performance.getEntriesByType('resource').map(x => x.name)"""
        )

        dom_tables = await page.evaluate(
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
                return {index: idx, headers, rows: data.slice(0, 500)};
            }).filter(Boolean)"""
        )

        unit_hint = None
        norm_text = _norm(page_text)
        if re.search(r"(fcfa|fca|cfa).{0,8}(kg|kilogram)", page_text, re.I | re.S) or "prixkg" in norm_text:
            unit_hint = "kg"

        await context.close()
        await browser.close()

    candidates.sort(key=lambda item: item.score, reverse=True)
    return DiscoveryReport(
        source_url=url,
        discovered_at=_now_iso(),
        page_title=page_title,
        page_url=page_url,
        candidates=candidates[:30],
        dom_tables=dom_tables,
        resource_urls=list(dict.fromkeys(resource_urls))[:500],
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
