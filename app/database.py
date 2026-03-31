"""Base de données SQLite pour les prix agricoles au Togo."""

import sqlite3
import os
from datetime import datetime, timedelta
import random

DB_PATH = os.path.join(os.path.dirname(__file__), "agritogo.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialise la base avec les tables et données de démo."""
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS produits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT UNIQUE NOT NULL,
            unite TEXT NOT NULL DEFAULT 'kg',
            categorie TEXT NOT NULL DEFAULT 'céréale'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS prix (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produit_id INTEGER NOT NULL,
            marche TEXT NOT NULL,
            prix REAL NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (produit_id) REFERENCES produits(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS previsions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produit_id INTEGER NOT NULL,
            marche TEXT NOT NULL,
            prix_prevu REAL NOT NULL,
            date_prevision TEXT NOT NULL,
            date_cible TEXT NOT NULL,
            confiance REAL DEFAULT 0.0,
            methode TEXT DEFAULT 'agent_ia',
            FOREIGN KEY (produit_id) REFERENCES produits(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            contenu TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    # Données de démo si la table est vide
    c.execute("SELECT COUNT(*) FROM produits")
    if c.fetchone()[0] == 0:
        _seed_data(c)

    conn.commit()
    conn.close()


def _seed_data(c):
    """Insère des données réalistes de prix agricoles au Togo."""
    produits = [
        ("Maïs", "kg", "céréale"),
        ("Riz local", "kg", "céréale"),
        ("Sorgho", "kg", "céréale"),
        ("Mil", "kg", "céréale"),
        ("Haricot", "kg", "légumineuse"),
        ("Soja", "kg", "légumineuse"),
        ("Arachide", "kg", "légumineuse"),
        ("Igname", "kg", "tubercule"),
        ("Manioc", "kg", "tubercule"),
        ("Tomate", "kg", "maraîcher"),
        ("Piment", "kg", "maraîcher"),
        ("Oignon", "kg", "maraîcher"),
    ]

    for nom, unite, cat in produits:
        c.execute(
            "INSERT INTO produits (nom, unite, categorie) VALUES (?, ?, ?)",
            (nom, unite, cat),
        )

    marches = ["Lomé-Adawlato", "Kara", "Sokodé", "Atakpamé", "Dapaong"]

    # Prix de base par produit (FCFA/kg) - réalistes pour le Togo
    prix_base = {
        "Maïs": 220, "Riz local": 450, "Sorgho": 200,
        "Mil": 250, "Haricot": 500, "Soja": 350,
        "Arachide": 400, "Igname": 300, "Manioc": 150,
        "Tomate": 600, "Piment": 800, "Oignon": 350,
    }

    # Générer 12 mois de données historiques
    today = datetime.now()
    for i, (nom, unite, cat) in enumerate(produits, 1):
        base = prix_base[nom]
        for marche in marches:
            for month_offset in range(12, 0, -1):
                date = today - timedelta(days=month_offset * 30)
                # Variation saisonnière + bruit
                saison = 1.0 + 0.15 * (
                    (month_offset % 6) / 6.0 - 0.5
                )
                bruit = random.uniform(0.92, 1.08)
                prix = round(base * saison * bruit, 0)
                c.execute(
                    "INSERT INTO prix (produit_id, marche, prix, date) "
                    "VALUES (?, ?, ?, ?)",
                    (i, marche, prix, date.strftime("%Y-%m-%d")),
                )


def get_produits():
    conn = get_db()
    rows = conn.execute("SELECT * FROM produits ORDER BY nom").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prix_historiques(produit_nom, marche=None, limit=60):
    conn = get_db()
    query = """
        SELECT p.prix, p.date, p.marche, pr.nom as produit
        FROM prix p JOIN produits pr ON p.produit_id = pr.id
        WHERE pr.nom = ?
    """
    params = [produit_nom]
    if marche:
        query += " AND p.marche = ?"
        params.append(marche)
    query += " ORDER BY p.date DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_marches():
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT marche FROM prix ORDER BY marche"
    ).fetchall()
    conn.close()
    return [r["marche"] for r in rows]


def save_prevision(produit_nom, marche, prix_prevu, date_cible, confiance):
    conn = get_db()
    produit = conn.execute(
        "SELECT id FROM produits WHERE nom = ?", (produit_nom,)
    ).fetchone()
    if produit:
        conn.execute(
            "INSERT INTO previsions "
            "(produit_id, marche, prix_prevu, date_prevision, "
            "date_cible, confiance) VALUES (?, ?, ?, ?, ?, ?)",
            (produit["id"], marche, prix_prevu,
             datetime.now().strftime("%Y-%m-%d"), date_cible, confiance),
        )
        conn.commit()
    conn.close()


def save_conversation(role, contenu):
    conn = get_db()
    conn.execute(
        "INSERT INTO conversations (role, contenu, timestamp) "
        "VALUES (?, ?, ?)",
        (role, contenu, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def get_conversations(limit=50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM conversations ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


# ── Admin database functions ──────────────────────────────────────────

import csv
import io


def add_produit(nom, unite="kg", categorie="céréale"):
    """Insert a new product. Return True on success, False on failure."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO produits (nom, unite, categorie) VALUES (?, ?, ?)",
            (nom, unite, categorie),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_produit(produit_id):
    """Delete a product by ID."""
    conn = get_db()
    conn.execute("DELETE FROM produits WHERE id = ?", (produit_id,))
    conn.commit()
    conn.close()


def add_prix_from_csv(csv_content):
    """Parse CSV string (date,produit,marche,prix) and insert rows.
    Returns the count of inserted rows."""
    conn = get_db()
    reader = csv.DictReader(io.StringIO(csv_content))
    count = 0
    for row in reader:
        produit = conn.execute(
            "SELECT id FROM produits WHERE nom = ?", (row["produit"].strip(),)
        ).fetchone()
        if produit:
            conn.execute(
                "INSERT INTO prix (produit_id, marche, prix, date) "
                "VALUES (?, ?, ?, ?)",
                (produit["id"], row["marche"].strip(),
                 float(row["prix"]), row["date"].strip()),
            )
            count += 1
    conn.commit()
    conn.close()
    return count


def add_produit_from_csv(csv_content):
    """Parse CSV string (nom,unite,categorie) and insert products.
    Returns the count of inserted rows."""
    conn = get_db()
    reader = csv.DictReader(io.StringIO(csv_content))
    count = 0
    for row in reader:
        try:
            conn.execute(
                "INSERT INTO produits (nom, unite, categorie) VALUES (?, ?, ?)",
                (row["nom"].strip(), row["unite"].strip(),
                 row["categorie"].strip()),
            )
            count += 1
        except sqlite3.IntegrityError:
            continue
    conn.commit()
    conn.close()
    return count


def get_all_prix(page=1, per_page=50):
    """Paginated prix with product name and market.
    Returns dict with items, total, pages."""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM prix").fetchone()[0]
    pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page
    rows = conn.execute(
        """
        SELECT p.id, p.prix, p.date, p.marche, pr.nom as produit
        FROM prix p JOIN produits pr ON p.produit_id = pr.id
        ORDER BY p.date DESC
        LIMIT ? OFFSET ?
        """,
        (per_page, offset),
    ).fetchall()
    conn.close()
    return {"items": [dict(r) for r in rows], "total": total, "pages": pages}


def delete_prix(prix_id):
    """Delete a price entry by ID."""
    conn = get_db()
    conn.execute("DELETE FROM prix WHERE id = ?", (prix_id,))
    conn.commit()
    conn.close()


def get_db_stats():
    """Return dict with database counts."""
    conn = get_db()
    stats = {
        "total_produits": conn.execute(
            "SELECT COUNT(*) FROM produits"
        ).fetchone()[0],
        "total_prix": conn.execute(
            "SELECT COUNT(*) FROM prix"
        ).fetchone()[0],
        "total_previsions": conn.execute(
            "SELECT COUNT(*) FROM previsions"
        ).fetchone()[0],
        "total_conversations": conn.execute(
            "SELECT COUNT(*) FROM conversations"
        ).fetchone()[0],
        "marches_count": conn.execute(
            "SELECT COUNT(DISTINCT marche) FROM prix"
        ).fetchone()[0],
    }
    conn.close()
    return stats


def export_prix_csv():
    """Return CSV string of all prix data with headers."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT p.date, pr.nom as produit, p.marche, p.prix
        FROM prix p JOIN produits pr ON p.produit_id = pr.id
        ORDER BY p.date DESC
        """
    ).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "produit", "marche", "prix"])
    for r in rows:
        writer.writerow([r["date"], r["produit"], r["marche"], r["prix"]])
    return output.getvalue()


def get_latest_prices():
    """Get the most recent price for each product with trend."""
    conn = get_db()
    rows = conn.execute("""
        SELECT pr.nom, p.prix, p.date, p.marche,
            (SELECT p2.prix FROM prix p2
             WHERE p2.produit_id = pr.id
             ORDER BY p2.date DESC LIMIT 1 OFFSET 5) as prev_prix
        FROM prix p
        JOIN produits pr ON p.produit_id = pr.id
        WHERE p.id IN (
            SELECT MAX(p3.id) FROM prix p3 GROUP BY p3.produit_id
        )
        ORDER BY pr.nom
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        current = r["prix"]
        prev = r["prev_prix"]
        if prev and prev > 0:
            delta = round((current - prev) / prev * 100, 1)
        else:
            delta = 0.0
        result.append({
            "nom": r["nom"],
            "prix": round(current),
            "date": r["date"],
            "marche": r["marche"],
            "delta": delta,
        })
    return result
