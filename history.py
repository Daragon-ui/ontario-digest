"""
history.py — Mémorisation des éléments déjà couverts dans les digests précédents.

Évite la répétition d'un digest à l'autre, notamment pour les décrets
nommant des personnes à des conseils d'administration.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

HISTORY_FILE = Path(__file__).parent / "digest_history.json"
RETENTION_DAYS = 14


def _load() -> dict:
    if not HISTORY_FILE.exists():
        return {"items": []}
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"items": []}


def _save(data: dict) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_recent_items(days: int = RETENTION_DAYS) -> list:
    """Retourne les descriptions des éléments couverts dans les derniers `days` jours."""
    data = _load()
    cutoff = datetime.now() - timedelta(days=days)
    return [
        item["description"]
        for item in data.get("items", [])
        if datetime.fromisoformat(item["date"]) > cutoff
    ]


def record_items(items: list) -> None:
    """Enregistre de nouveaux éléments dans l'historique et purge les anciens."""
    if not items:
        return
    data = _load()
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    data["items"] = [
        item for item in data.get("items", [])
        if datetime.fromisoformat(item["date"]) > cutoff
    ]
    today = datetime.now().date().isoformat()
    existing = {item["description"] for item in data["items"]}
    for desc in items:
        if desc not in existing:
            data["items"].append({"date": today, "description": desc})
    _save(data)


def extract_tracked_items(sources: dict) -> list:
    """
    Extrait les identifiants traçables depuis les sources brutes,
    avant que Claude ne les traite.
    """
    items = []

    # Décrets du Conseil : noms des personnes nommées
    oic_content = sources.get("Décrets du Conseil (OIC)", "")
    for line in oic_content.splitlines():
        if line.startswith("PERSONNES/ENTITÉS EN GRAS DANS LE DÉCRET :"):
            noms = line.split(":", 1)[1].strip()
            if noms:
                items.append(f"Décret — nomination : {noms}")

    # Communiqués Ontario Newsroom : titres et URLs
    news_content = sources.get("Communiqués Ontario Newsroom", "")
    for line in news_content.splitlines():
        line = line.strip()
        if line.startswith("http"):
            items.append(f"Communiqué : {line[:150]}")
        elif len(line) > 30 and not line.startswith(("=", "[", "-")):
            items.append(f"Communiqué : {line[:150]}")

    return items
