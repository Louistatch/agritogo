"""
Database layer — Supabase (PostgreSQL) backend.

Replaces the original SQLite backend. All function signatures are preserved
so the rest of the codebase (tools, server, admin, ML) works unchanged.

Env vars required:
  SUPABASE_URL        — e.g. https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY — service_role key (reads + writes)
"""

import os
from datetime import datetime
from functools import lru_cache

from supabase import create_client, Client


@lru_cache(maxsize=1)
def _get_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set. "
            "Get them from your Supabase project settings."
        )
    return create_client(url, key)


def get_db():
    """Compatibility shim — returns the Supabase client."""
    return _get_client()


def init_db():
    """No-op: Supabase schema is managed via migrations."""
    pass


# ─── READ: Products (cultures) ─────────────────────────────────────

def get_produits() -> list[dict]:
    """List all agricultural products.

    Returns the same shape as the old SQLite version:
        [{"id": ..., "nom": ..., "unite": "kg", "categorie": ...}, ...]
    """
    sb = _get_client()
    res = sb.table("cultures").select("id, name, category").order("name").execute()
    return [
        {"id": str(r["id"]), "nom": r["name"], "unite": "kg", "categorie": r.get("category", "culture")}
        for r in (res.data or [])
    ]


# ─── READ: Historical prices ───────────────────────────────────────

def get_prix_historiques(produit_nom: str, marche: str = None, limit: int = 60) -> list[dict]:
    """Get historical prices for a product, optionally filtered by market.

    Returns: [{"date": "YYYY-MM-DD", "marche": str, "prix": float, "produit": str}, ...]
    """
    sb = _get_client()

    # Resolve culture_id from name (case-insensitive fuzzy)
    cultures = sb.table("cultures").select("id, name").execute().data or []
    culture_id = None
    produit_clean = produit_nom.lower().replace("ï", "i").replace("é", "e").replace("è", "e").strip()
    for c in cultures:
        c_clean = c["name"].lower().replace("ï", "i").replace("é", "e").replace("è", "e")
        if c_clean == produit_clean or produit_clean in c_clean:
            culture_id = c["id"]
            produit_nom = c["name"]
            break

    if not culture_id:
        return []

    query = (
        sb.table("market_prices")
        .select("market_name, price, created_at")
        .eq("culture_id", culture_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if marche:
        query = query.ilike("market_name", f"%{marche}%")

    res = query.execute()
    return [
        {
            "date": r["created_at"][:10],
            "marche": r["market_name"],
            "prix": float(r["price"]),
            "produit": produit_nom,
        }
        for r in (res.data or [])
    ]


def get_marches() -> list[str]:
    """List all distinct market names."""
    sb = _get_client()
    res = sb.table("market_prices").select("market_name").execute()
    return sorted(set(r["market_name"] for r in (res.data or []) if r.get("market_name")))


def get_latest_prices() -> list[dict]:
    """Get the most recent price per product across all markets.

    Returns dicts with: nom, prix, marche, date, delta (% change vs previous).
    """
    sb = _get_client()
    res = (
        sb.table("market_prices")
        .select("market_name, price, created_at, culture:cultures(name)")
        .order("created_at", desc=True)
        .limit(400)
        .execute()
    )
    # Group by product: collect all prices sorted by date desc
    from collections import defaultdict
    by_product: dict[str, list[dict]] = defaultdict(list)
    for r in (res.data or []):
        culture_name = r.get("culture", {})
        if isinstance(culture_name, list):
            culture_name = culture_name[0] if culture_name else {}
        name = culture_name.get("name", "?") if isinstance(culture_name, dict) else "?"
        by_product[name].append({
            "marche": r["market_name"],
            "prix": float(r["price"]),
            "date": r["created_at"][:10],
        })

    out = []
    for name, prices in by_product.items():
        latest = prices[0]
        # Compute delta: % change between latest and previous price
        delta = 0.0
        if len(prices) >= 2:
            prev = prices[1]["prix"]
            if prev > 0:
                delta = round(((latest["prix"] - prev) / prev) * 100, 1)
        out.append({
            "nom": name,
            "prix": int(latest["prix"]),
            "marche": latest["marche"],
            "date": latest["date"],
            "delta": delta,
        })
    return sorted(out, key=lambda x: x["nom"])


# ─── WRITE: Forecasts ──────────────────────────────────────────────

def save_prevision(produit_nom: str, marche: str, prix_prevu: float,
                   date_cible: str, confiance: float = 0.7):
    """Save a price forecast (stored as a market_price with metadata)."""
    sb = _get_client()
    cultures = sb.table("cultures").select("id, name").execute().data or []
    culture_id = None
    for c in cultures:
        if c["name"].lower() == produit_nom.lower():
            culture_id = c["id"]
            break
    if not culture_id:
        return

    # Find region for the market
    res = (
        sb.table("market_prices")
        .select("region_id")
        .ilike("market_name", f"%{marche}%")
        .limit(1)
        .execute()
    )
    region_id = res.data[0]["region_id"] if res.data else None
    if not region_id:
        return

    sb.table("market_prices").insert({
        "culture_id": culture_id,
        "region_id": region_id,
        "market_name": marche,
        "price": int(prix_prevu),
        "unit": "kg",
        "currency": "FCFA",
        "verified": False,
    }).execute()


# ─── Conversations (AI chat history) ──────────────────────────────

def save_conversation(role: str, contenu: str, card_number: str = "SYSTEM"):
    """Save a conversation message."""
    sb = _get_client()
    sb.table("ai_conversations").insert({
        "card_number": card_number,
        "role": role,
        "content": contenu,
    }).execute()


def get_conversations(limit: int = 50, card_number: str = None) -> list[dict]:
    """Get conversation history."""
    sb = _get_client()
    query = sb.table("ai_conversations").select("role, content, created_at").order("created_at", desc=True).limit(limit)
    if card_number:
        query = query.eq("card_number", card_number)
    res = query.execute()
    return [
        {"role": r["role"], "contenu": r["content"], "timestamp": r["created_at"]}
        for r in reversed(res.data or [])
    ]


def clear_conversations(card_number: str = None):
    """Delete conversation history."""
    sb = _get_client()
    if card_number:
        sb.table("ai_conversations").delete().eq("card_number", card_number).execute()
    else:
        sb.table("ai_conversations").delete().neq("card_number", "__never__").execute()


# ─── Admin: CRUD ──────────────────────────────────────────────────

def add_produit(nom: str, unite: str = "kg", categorie: str = "culture"):
    sb = _get_client()
    sb.table("cultures").insert({"name": nom, "category": categorie}).execute()
    return True


def delete_produit(produit_id: str):
    sb = _get_client()
    sb.table("cultures").delete().eq("id", produit_id).execute()


def add_prix_from_csv(csv_content: str) -> dict:
    """Import prices from CSV (produit,marche,prix,date)."""
    import csv, io
    reader = csv.DictReader(io.StringIO(csv_content))
    inserted, errors = 0, 0
    cultures_cache = {c["nom"].lower(): c["id"] for c in get_produits()}
    for row in reader:
        try:
            nom = row.get("produit", "").strip()
            cid = cultures_cache.get(nom.lower())
            if not cid:
                errors += 1
                continue
            # Find region for market
            marche = row.get("marche", "").strip()
            sb = _get_client()
            rres = sb.table("market_prices").select("region_id").ilike("market_name", f"%{marche}%").limit(1).execute()
            rid = rres.data[0]["region_id"] if rres.data else None
            if not rid:
                errors += 1
                continue
            sb.table("market_prices").insert({
                "culture_id": cid, "region_id": rid, "market_name": marche,
                "price": int(float(row.get("prix", 0))), "unit": "kg", "currency": "FCFA",
                "created_at": row.get("date", datetime.now().isoformat()),
            }).execute()
            inserted += 1
        except Exception:
            errors += 1
    return {"inserted": inserted, "errors": errors}


def add_produit_from_csv(csv_content: str) -> dict:
    import csv, io
    reader = csv.DictReader(io.StringIO(csv_content))
    inserted, errors = 0, 0
    for row in reader:
        try:
            add_produit(row.get("nom", "").strip(), row.get("unite", "kg"), row.get("categorie", "culture"))
            inserted += 1
        except Exception:
            errors += 1
    return {"inserted": inserted, "errors": errors}


def get_all_prix(page: int = 1, per_page: int = 50) -> dict:
    sb = _get_client()
    offset = (page - 1) * per_page
    res = (
        sb.table("market_prices")
        .select("id, market_name, price, created_at, culture:cultures(name)", count="exact")
        .order("created_at", desc=True)
        .range(offset, offset + per_page - 1)
        .execute()
    )
    rows = []
    for r in (res.data or []):
        cn = r.get("culture", {})
        if isinstance(cn, list):
            cn = cn[0] if cn else {}
        rows.append({
            "id": r["id"], "produit": cn.get("name", "?") if isinstance(cn, dict) else "?",
            "marche": r["market_name"], "prix": r["price"], "date": r["created_at"][:10],
        })
    return {"data": rows, "total": res.count or 0, "page": page, "per_page": per_page}


def delete_prix(prix_id: str):
    sb = _get_client()
    sb.table("market_prices").delete().eq("id", prix_id).execute()


def get_db_stats() -> dict:
    sb = _get_client()
    cultures = sb.table("cultures").select("id", count="exact").execute()
    prices = sb.table("market_prices").select("id", count="exact").execute()
    convos = sb.table("ai_conversations").select("id", count="exact").execute()
    members = sb.table("members").select("id", count="exact").execute()
    cards = sb.table("member_cards").select("id", count="exact").execute()
    return {
        "cultures": cultures.count or 0,
        "prix": prices.count or 0,
        "conversations": convos.count or 0,
        "members": members.count or 0,
        "cards": cards.count or 0,
        "marches": len(get_marches()),
        "backend": "supabase",
    }


def export_prix_csv() -> str:
    """Export all prices as CSV string."""
    import csv, io
    all_prices = get_all_prix(page=1, per_page=10000)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["produit", "marche", "prix", "date"])
    writer.writeheader()
    for r in all_prices["data"]:
        writer.writerow(r)
    return output.getvalue()
