"""Tests for CPC market-data normalization."""

from app.ingestion.cpc import (
    _extract_script_endpoint_hints,
    _same_site,
    normalize_records,
)


def test_normalize_long_market_records() -> None:
    records = [
        {
            "Marché": "Kara",
            "Produit": "Maïs",
            "Prix": "245",
            "Date": "30/09/2026",
            "Unité": "kg",
        },
    ]

    rows = normalize_records(
        records,
        "https://www.cpc-togo.com/",
    )

    assert len(rows) == 1
    assert rows[0].market_raw == "Kara"
    assert rows[0].product_raw == "Maïs"
    assert rows[0].price == 245
    assert rows[0].observed_at == "2026-09-30"
    assert rows[0].unit == "kg"
    assert rows[0].quality_status == "accepted"


def test_normalize_wide_market_records() -> None:
    records = [
        {
            "Marché": "Sokodé",
            "Maïs": "250",
            "Riz": "450",
            "Soja": "-",
            "Date": "29/09/2026",
        },
    ]

    rows = normalize_records(
        records,
        "https://www.cpc-togo.com/",
        unit_hint="kg",
    )

    assert len(rows) == 2
    products = {row.product_raw: row.price for row in rows}
    assert products == {"Maïs": 250, "Riz": 450}
    assert all(row.market_raw == "Sokodé" for row in rows)
    assert all(row.observed_at == "2026-09-29" for row in rows)


def test_record_hash_is_idempotent() -> None:
    record = {
        "Marché": "Kara",
        "Produit": "Maïs",
        "Prix": 245,
        "Date": "2026-09-30",
    }

    first = normalize_records(
        [record],
        "https://www.cpc-togo.com/",
        unit_hint="kg",
    )
    second = normalize_records(
        [record],
        "https://www.cpc-togo.com/",
        unit_hint="kg",
    )

    assert first[0].record_hash == second[0].record_hash


def test_wide_parser_ignores_numeric_locality_labels() -> None:
    records = [
        {
            "Region": "Centre",
            "Department": "MFOUNDI",
            "Borough": "YAOUNDE 2EME",
            "Locality": "Yaoundé",
            "Walk": "Marché 8ème",
            "Rice Paddy": "600",
            "Steamed Local Rice": "900",
            "Date": "04/08/2026",
        },
    ]

    rows = normalize_records(
        records,
        "https://simro-cmr.com/",
        unit_hint="kg",
    )

    products = {row.product_raw for row in rows}
    assert products == {"Rice Paddy", "Steamed Local Rice"}
    assert all(row.market_raw == "Marché 8ème" for row in rows)


def test_extract_script_endpoint_hints() -> None:
    script = """
    fetch('/api/prix?market=kara');
    axios.get("/ajax/marches");
    const ignored = "https://example.com/not-market";
    """

    hints = _extract_script_endpoint_hints(
        script,
        "https://www.cpc-togo.com/sim",
    )

    assert "https://www.cpc-togo.com/api/prix?market=kara" in hints
    assert "https://www.cpc-togo.com/ajax/marches" in hints


def test_same_site_accepts_subdomain() -> None:
    assert _same_site(
        "https://api.cpc-togo.com/prix",
        "cpc-togo.com",
    )
    assert not _same_site(
        "https://example.com/prix",
        "cpc-togo.com",
    )


def test_normalize_html_php_table_fragment() -> None:
    html = """
    <table>
      <tr>
        <th>Marché</th><th>Maïs</th><th>Soja</th><th>Date</th>
      </tr>
      <tr>
        <td>Marché de Kara</td><td>245</td><td>310</td>
        <td>30/09/2026</td>
      </tr>
    </table>
    """

    rows = normalize_payload(
        html,
        "text/html; charset=utf-8",
        "https://example.org/php_files/tableau_prix.php",
        unit_hint="kg",
    )

    assert len(rows) == 2
    assert {row.product_raw for row in rows} == {"Maïs", "Soja"}
    assert all(row.market_raw == "Marché de Kara" for row in rows)
    assert all(row.observed_at == "2026-09-30" for row in rows)
