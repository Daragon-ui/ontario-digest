"""
fetchers.py — Récupération des sources politiques ontariennes.
"""

import time
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def safe_get(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  ⚠ Impossible de récupérer {url} : {e}")
        return None


def soup_text(r, max_chars=5000):
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if len(l.strip()) > 25]
    return "\n".join(lines[:200])[:max_chars]


def fetch_news_ontario():
    print("  → news.ontario.ca...")
    feed = feedparser.parse("https://news.ontario.ca/en/rss")
    if not feed.entries:
        return "Aucun communiqué disponible (flux RSS inaccessible)."

    cutoff = datetime.now(timezone.utc) - timedelta(hours=36)
    items = []
    for entry in feed.entries[:20]:
        try:
            pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pub = datetime.now(timezone.utc)

        if pub >= cutoff or len(items) < 3:
            titre = entry.get("title", "(sans titre)")
            resume = entry.get("summary", "")[:500]
            lien = entry.get("link", "")
            items.append(f"[{pub.strftime('%Y-%m-%d')}] {titre}\n{resume}\n{lien}")

    return "\n\n".join(items[:8]) if items else "Aucun communiqué récent."


def fetch_hansard():
    print("  → Hansard (ola.org)...")
    index_urls = [
        "https://www.ola.org/en/legislative-business/house-documents/parliament-43/session-1/hansard",
        "https://www.ola.org/en/legislative-business/house-documents/parliament-43",
        "https://www.ola.org/en/legislative-business/house-documents",
    ]

    soup = None
    for url in index_urls:
        r = safe_get(url)
        if r:
            soup = BeautifulSoup(r.text, "html.parser")
            break

    if not soup:
        return "Hansard non disponible (site OLA inaccessible)."

    hansard_link = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        texte = a.get_text(strip=True)
        if texte and any(k in href.lower() for k in ["hansard", "2025", "2026"]):
            if not href.startswith("http"):
                href = "https://www.ola.org" + href
            hansard_link = (texte, href)
            break

    if not hansard_link:
        text = soup_text(r if r else requests.Response(), max_chars=3000)
        return f"Index OLA récupéré (pas de Hansard identifié ce jour):\n{text}"

    titre, lien = hansard_link
    time.sleep(1)
    r2 = safe_get(lien)
    if not r2:
        return f"Hansard le plus récent trouvé : {titre}\nLien : {lien}\n(Contenu non accessible)"

    texte = soup_text(r2, max_chars=5000)
    return f"Hansard : {titre}\nLien : {lien}\n\n{texte}"


def fetch_gazette():
    print("  → Gazette de l'Ontario...")
    r = safe_get("https://www.ontario.ca/page/ontario-gazette")
    if not r:
        return "Gazette de l'Ontario non disponible."
    return soup_text(r, max_chars=3000)


def fetch_lobbyist_registry():
    print("  → Registre des lobbyistes...")
    urls = [
        "https://www.ontario.ca/page/lobbyist-registry",
        "https://lobbyist.ontario.ca/lobbyistregistry/faces/publicregistration/searchRegistrations.xhtml",
    ]
    for url in urls:
        r = safe_get(url)
        if r:
            return soup_text(r, max_chars=3000)
    return "Registre des lobbyistes non disponible aujourd'hui."


def fetch_regulatory_registry():
    print("  → Registre de la réglementation...")
    urls = [
        "https://www.ontariocanada.com/registry/view.do?language=en&status=Posted",
        "https://www.ontario.ca/page/ontario-regulatory-registry",
    ]
    for url in urls:
        r = safe_get(url)
        if r:
            return soup_text(r, max_chars=3000)
    return "Registre de la réglementation non disponible aujourd'hui."


def fetch_orders_in_council():
    print("  → Décrets du Conseil...")
    r = safe_get("https://www.ontario.ca/search/orders-in-council")
    if not r:
        return "Page des Décrets du Conseil non disponible."
    return soup_text(r, max_chars=3000)


def fetch_all() -> dict:
    print("📡 Récupération des sources politiques ontariennes...")
    sources = {
        "Communiqués du gouvernement (news.ontario.ca)": fetch_news_ontario(),
        "Hansard — Assemblée législative de l'Ontario": fetch_hansard(),
        "Gazette de l'Ontario": fetch_gazette(),
        "Registre des lobbyistes": fetch_lobbyist_registry(),
        "Registre de la réglementation de l'Ontario": fetch_regulatory_registry(),
        "Décrets du Conseil": fetch_orders_in_council(),
    }
    print("✅ Sources récupérées.")
    return sources
