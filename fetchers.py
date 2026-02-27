"""
fetchers.py — Récupération des sources politiques ontariennes.
Chaque fonction retourne du texte brut prêt à être analysé par Claude.
"""

import time
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# Use a persistent session so cookies and keep-alive work across requests.
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9,fr-CA;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
})


def safe_get_js(url, timeout=30):
    """Charge une page via Playwright pour les sites qui nécessitent JavaScript."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  ⚠ Playwright non installé — fallback HTTP pour {url[:60]}")
        return safe_get(url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"Accept-Language": "en-CA,en;q=0.9,fr-CA;q=0.8"})
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            content = page.content()
            browser.close()
        print(f"    ✓ JS {url[:80]} ({len(content):,} chars)")

        class _R:
            text = content
            status_code = 200

        return _R()
    except Exception as e:
        print(f"  ⚠ JS {url[:80]} : {e}")
        return None


def safe_get(url, timeout=20, params=None):
    """Fait une requête HTTP sécurisée avec sortie de débogage."""
    try:
        r = SESSION.get(url, timeout=timeout, params=params, allow_redirects=True)
        r.raise_for_status()
        print(f"    ✓ {url[:80]} [{r.status_code}] ({len(r.text):,} chars)")
        return r
    except Exception as e:
        print(f"  ⚠ {url[:80]} : {e}")
        return None


def soup_text(r, max_chars=5000, main_only=False):
    """Extrait le texte propre d'une réponse HTTP."""
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    if main_only:
        main = (
            soup.find("main")
            or soup.find(id="content")
            or soup.find(class_="content")
            or soup.find(attrs={"role": "main"})
        )
        if main:
            soup = main
    lines = [
        l.strip()
        for l in soup.get_text(separator="\n").splitlines()
        if len(l.strip()) > 25
    ]
    return "\n".join(lines[:200])[:max_chars]


def try_rss(urls, cutoff_hours=36, max_items=8):
    """
    Essaie plusieurs URLs RSS dans l'ordre.
    Retourne un texte formaté si des entrées sont trouvées, sinon None.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cutoff_hours)
    for url in urls:
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                print(f"    ⚠ RSS vide ou inaccessible : {url}")
                continue
            print(f"    ✓ RSS OK : {url} ({len(feed.entries)} entrées)")
            items = []
            for entry in feed.entries[:20]:
                try:
                    pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pub = datetime.now(timezone.utc)
                if pub >= cutoff or len(items) < 3:
                    titre = entry.get("title", "(sans titre)")
                    resume = entry.get("summary", "")[:400]
                    lien = entry.get("link", "")
                    items.append(
                        f"[{pub.strftime('%Y-%m-%d')}] {titre}\n{resume}\n{lien}"
                    )
            if items:
                return "\n\n".join(items[:max_items])
        except Exception as e:
            print(f"    ⚠ Erreur RSS {url} : {e}")
    return None


# ---------------------------------------------------------------------------
# 1. Communiqués du gouvernement — news.ontario.ca
# ---------------------------------------------------------------------------
def fetch_news_ontario():
    print("  → news.ontario.ca...")

    rss = try_rss([
        "https://news.ontario.ca/en/rss",
        "https://news.ontario.ca/en/rss/all",
        "https://news.ontario.ca/en/releases.rss",
    ])
    if rss:
        return rss

    # HTML fallback: scrape the releases page (essaie d'abord sans JS, puis avec)
    for url in ["https://news.ontario.ca/en/releases", "https://news.ontario.ca/en"]:
        r = safe_get(url) or safe_get_js(url)
        if not r:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        items = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            titre = a.get_text(strip=True)
            if len(titre) < 20 or titre in seen:
                continue
            if "/release/" in href or "/releases/" in href:
                if not href.startswith("http"):
                    href = "https://news.ontario.ca" + href
                seen.add(titre)
                items.append(f"{titre}\n{href}")
                if len(items) >= 8:
                    break
        if items:
            return "Communiqués récents (news.ontario.ca):\n\n" + "\n\n".join(items)
        # last resort: raw text
        return soup_text(r, max_chars=3000)

    return "Communiqués du gouvernement non disponibles."


# ---------------------------------------------------------------------------
# 2. Hansard — Assemblée législative de l'Ontario (ola.org)
# ---------------------------------------------------------------------------
def fetch_hansard():
    print("  → Hansard (ola.org)...")

    # L'Assemblée est en recès jusqu'au 23 mars 2026 — aucun suivi avant cette date.
    if datetime.now() < datetime(2026, 3, 23):
        print("  → Hansard suspendu (recès jusqu'au 23 mars 2026).")
        return "Hansard non suivi jusqu'au 23 mars 2026 (Assemblée en recès)."

    year = datetime.now().year

    index_urls = [
        "https://www.ola.org/en/legislative-business/house-documents/parliament-43/session-1/hansard",
        "https://www.ola.org/en/legislative-business/house-documents/parliament-43",
        "https://www.ola.org/en/legislative-business/house-documents",
        "https://www.ola.org/en/legislative-business",
    ]

    soup = None
    for url in index_urls:
        r = safe_get(url)
        if r and len(r.text) > 1000:
            soup = BeautifulSoup(r.text, "html.parser")
            if soup.find_all("a", href=True):
                break

    if not soup:
        return "Hansard non disponible (site OLA inaccessible)."

    # Collect links that look like individual Hansard documents
    hansard_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        texte = a.get_text(strip=True)
        if not texte or len(texte) < 5:
            continue
        if "hansard" in href.lower() or str(year) in href:
            if not href.startswith("http"):
                href = "https://www.ola.org" + href
            hansard_links.append((texte, href))

    if not hansard_links:
        return "Index OLA accessible, mais aucun Hansard récent identifié."

    titre, lien = hansard_links[0]
    time.sleep(1)
    r2 = safe_get(lien)
    if not r2:
        return f"Hansard récent : {titre}\n{lien}\n(Contenu non accessible)"

    texte = soup_text(r2, max_chars=5000)
    return f"Hansard : {titre}\nLien : {lien}\n\n{texte}"


# ---------------------------------------------------------------------------
# 3. Gazette de l'Ontario
# ---------------------------------------------------------------------------
def fetch_gazette():
    print("  → Gazette de l'Ontario...")
    for url in [
        "https://www.ontario.ca/page/ontario-gazette",
        "https://ontariogazette.ca/",
    ]:
        r = safe_get(url)
        if r and len(r.text) > 500:
            return soup_text(r, max_chars=3000)
    return "Gazette de l'Ontario non disponible."


# ---------------------------------------------------------------------------
# 4. Registre des lobbyistes — lobbyist.ontario.ca
# ---------------------------------------------------------------------------
def fetch_lobbyist_registry():
    print("  → Registre des lobbyistes...")
    # ontario.ca/page : simple HTML
    r = safe_get("https://www.ontario.ca/page/lobbyist-registry")
    if r and len(r.text) > 500:
        text = soup_text(r, max_chars=3000)
        if len(text) > 100:
            return text
    # Portail JSF — nécessite JavaScript
    r = safe_get_js(
        "https://lobbyist.ontario.ca/lobbyistregistry/faces/publicregistration/searchRegistrations.xhtml"
    )
    if r and len(r.text) > 500:
        text = soup_text(r, max_chars=3000)
        if len(text) > 100:
            return text
    return "Registre des lobbyistes non disponible aujourd'hui."


# ---------------------------------------------------------------------------
# 5. Registre de la réglementation — ontariocanada.com
# ---------------------------------------------------------------------------
def fetch_regulatory_registry():
    print("  → Registre de la réglementation...")
    for url in [
        "https://www.ontariocanada.com/registry/view.do?language=en&status=Posted",
        "https://www.ontario.ca/page/ontario-regulatory-registry",
    ]:
        r = safe_get(url)
        if r and len(r.text) > 500:
            text = soup_text(r, max_chars=3000)
            if len(text) > 100:
                return text
    return "Registre de la réglementation non disponible aujourd'hui."


# ---------------------------------------------------------------------------
# 6. Décrets du Conseil — exploration de chaque décret individuel
# ---------------------------------------------------------------------------
def fetch_orders_in_council():
    print("  → Décrets du Conseil...")

    today = datetime.now()
    base = "https://www.ontario.ca"
    search_url = f"{base}/search/orders-in-council"

    # Try current month, then previous month, to find recent orders
    all_order_links = []
    for delta in [0, 1]:
        month = today.month - delta
        year = today.year
        if month <= 0:
            month += 12
            year -= 1

        url_mois = f"{search_url}?year={year}&month={month}"
        r = safe_get(url_mois) or safe_get_js(url_mois)
        if not r:
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            texte = a.get_text(strip=True)
            # Individual order pages have paths like /orders-in-council/YYYY/NNNN
            if (
                "orders-in-council" in href
                and "/search/" not in href
                and href.count("/") >= 3
            ):
                full = href if href.startswith("http") else base + href
                entry = (texte or href.rstrip("/").split("/")[-1], full)
                if entry not in all_order_links:
                    all_order_links.append(entry)

        if all_order_links:
            break  # Found orders — no need to check previous month

    # If date-filtered search found nothing, try without filters
    if not all_order_links:
        r = safe_get(search_url) or safe_get_js(search_url)
        if r:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                texte = a.get_text(strip=True)
                if (
                    "orders-in-council" in href
                    and "/search/" not in href
                    and href.count("/") >= 3
                ):
                    full = href if href.startswith("http") else base + href
                    all_order_links.append((texte or href.rstrip("/").split("/")[-1], full))

    if not all_order_links:
        r = safe_get(search_url) or safe_get_js(search_url)
        if r:
            return (
                "Décrets du Conseil (index seulement — "
                "liens individuels non détectés):\n"
                + soup_text(r, max_chars=3000)
            )
        return "Page des Décrets du Conseil non disponible."

    # Fetch the content of each individual order (up to 5 most recent)
    resultats = []
    for titre, lien in all_order_links[:5]:
        time.sleep(1)
        r_order = safe_get(lien) or safe_get_js(lien)
        if not r_order:
            resultats.append(f"Décret : {titre}\nLien : {lien}\n(Contenu non accessible)")
            continue
        texte = soup_text(r_order, max_chars=2000, main_only=True)
        if texte:
            resultats.append(f"Décret : {titre}\nLien : {lien}\n\n{texte}")
            print(f"    ✓ Contenu du décret récupéré : {titre[:60]}")
        else:
            resultats.append(
                f"Décret : {titre}\nLien : {lien}\n(Contenu vide ou non lisible)"
            )

    header = f"Décrets du Conseil ({len(resultats)} décret(s) récupéré(s)) :"
    return header + "\n\n" + "\n\n---\n\n".join(resultats)


# ---------------------------------------------------------------------------
# Orchestrateur principal
# ---------------------------------------------------------------------------
def fetch_all() -> dict:
    """
    Récupère toutes les sources et retourne un dictionnaire
    { nom_source: contenu_texte }.
    """
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
