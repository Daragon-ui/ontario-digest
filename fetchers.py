"""
fetchers.py — Récupération des sources politiques ontariennes.
Chaque fonction retourne du texte brut prêt à être analysé par Claude.
"""

import re
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

    # Essayer plusieurs variantes RSS (le chemin exact varie selon la version du CMS)
    rss = try_rss([
        "https://news.ontario.ca/en/rss",
        "https://news.ontario.ca/en/rss/all",
        "https://news.ontario.ca/en/feed",
        "https://news.ontario.ca/feed/",
        "https://news.ontario.ca/en/releases.rss",
        "https://news.ontario.ca/rss",
    ])
    if rss:
        return rss

    # Scraping HTML — Playwright en priorité (site JS-lourd), HTTP en fallback
    for url in ["https://news.ontario.ca/en/releases", "https://news.ontario.ca/en"]:
        # Tenter HTTP d'abord ; si la page semble vide/partielle, forcer Playwright
        r = safe_get(url)
        if not r or len(r.text) < 3000:
            r = safe_get_js(url) or r
        if not r:
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        items = []
        seen = set()

        # Chercher d'abord les liens vers des communiqués individuels
        for a in soup.find_all("a", href=True):
            href = a["href"]
            titre = a.get_text(strip=True)
            if len(titre) < 20 or titre in seen:
                continue
            if re.search(r"/release[s]?/", href):
                if not href.startswith("http"):
                    href = "https://news.ontario.ca" + href
                seen.add(titre)
                items.append(f"{titre}\n{href}")
                if len(items) >= 8:
                    break

        # Chercher aussi dans les balises <article> ou <h2>/<h3> si aucun lien trouvé
        if not items:
            for container in soup.find_all(["article", "li"], class_=re.compile(r"release|news|story|item", re.I)):
                titre_tag = container.find(["h2", "h3", "h4", "a"])
                lien_tag = container.find("a", href=True)
                if not titre_tag or not lien_tag:
                    continue
                titre = titre_tag.get_text(strip=True)
                href = lien_tag["href"]
                if len(titre) < 20 or titre in seen:
                    continue
                if not href.startswith("http"):
                    href = "https://news.ontario.ca" + href
                seen.add(titre)
                items.append(f"{titre}\n{href}")
                if len(items) >= 8:
                    break

        if items:
            return "Communiqués récents (news.ontario.ca) :\n\n" + "\n\n".join(items)

        # Dernier recours : texte brut de la page si suffisamment substantiel
        text = soup_text(r, max_chars=3000)
        if len(text) > 300:
            return "Ontario Newsroom — contenu brut :\n\n" + text

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
# 6. Décrets du Conseil
# ---------------------------------------------------------------------------

# Correspond à "order-in-council" ET "orders-in-council" (singulier ET pluriel)
_OIC_HREF_RE = re.compile(r"order[s]?-in-council", re.IGNORECASE)


def _oic_links_from_html(html: str, base: str = "https://www.ontario.ca") -> list:
    """Extrait les liens vers des décrets individuels depuis du HTML (singulier ou pluriel)."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href or href.startswith("#") or "javascript:" in href:
            continue
        full = href if href.startswith("http") else base + href
        if _OIC_HREF_RE.search(href) and "/search/" not in href and full not in seen:
            seen.add(full)
            texte = a.get_text(strip=True) or full.rstrip("/").split("/")[-1]
            links.append((texte, full))
    return links


def _oic_playwright_search(url: str) -> tuple:
    """
    Charge une URL de recherche OIC via Playwright.
    - Attend les résultats dynamiques via plusieurs sélecteurs CSS
    - Intercepte les réponses JSON de l'API
    - Retourne (captured_json, rendered_html, all_hrefs)
    all_hrefs = liste brute de tous les href (pour débogage en cas d'échec)
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], None, []

    captured_json = []
    rendered_html = None
    all_hrefs = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                extra_http_headers={"Accept-Language": "en-CA,en;q=0.9"}
            )
            page = context.new_page()

            def on_response(response):
                ct = response.headers.get("content-type", "")
                if response.status == 200 and "json" in ct:
                    try:
                        data = response.json()
                        captured_json.append((response.url, data))
                        print(f"    ✓ JSON intercepté : {response.url[:80]}")
                    except Exception:
                        pass

            page.on("response", on_response)
            page.goto(url, wait_until="networkidle", timeout=45_000)

            # Attendre qu'au moins un sélecteur de résultat soit présent
            for sel in [
                "table tbody tr a",
                "[class*='result'] a",
                "[class*='Result'] a",
                "main ul li a",
                "main ol li a",
                "article a",
                "main a[href*='order']",
                "main a[href*='council']",
                ".search-results a",
            ]:
                try:
                    page.wait_for_selector(sel, timeout=4_000)
                    print(f"    ✓ Sélecteur résultat détecté : {sel}")
                    break
                except Exception:
                    pass

            # Scroll pour déclencher le chargement paresseux
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2_000)

            # Collecter TOUS les href de la page (débogage)
            all_hrefs = page.evaluate(
                "() => Array.from(document.querySelectorAll('a[href]'))"
                ".map(a => a.getAttribute('href'))"
            )

            oic_count = sum(
                1 for h in all_hrefs
                if h and _OIC_HREF_RE.search(h) and "/search/" not in h
            )
            print(f"    ℹ {len(all_hrefs)} liens sur la page, "
                  f"{oic_count} correspondent au pattern OIC")

            if oic_count == 0:
                sample = [h for h in all_hrefs if h and h.startswith("/") and len(h) > 5][:15]
                print(f"    ℹ Échantillon des liens trouvés : {sample}")

            rendered_html = page.content()
            browser.close()

    except Exception as e:
        print(f"  ⚠ Playwright OIC {url} : {e}")

    return captured_json, rendered_html, all_hrefs


def _oic_json_to_links(captured_json: list, base: str = "https://www.ontario.ca") -> list:
    """Extrait les URLs de décrets depuis les données JSON interceptées."""
    links = []
    seen = set()

    def walk(obj, depth=0):
        if depth > 8:
            return
        if isinstance(obj, list):
            for item in obj:
                walk(item, depth + 1)
        elif isinstance(obj, dict):
            kl = {k.lower(): v for k, v in obj.items()}
            url_val = str(kl.get("url") or kl.get("link") or kl.get("href") or "")
            titre_val = str(kl.get("title") or kl.get("name") or kl.get("label") or "")
            if url_val and _OIC_HREF_RE.search(url_val) and "/search/" not in url_val:
                full = url_val if url_val.startswith("http") else base + url_val
                if full not in seen:
                    seen.add(full)
                    links.append((titre_val or full.rstrip("/").split("/")[-1], full))
            for v in obj.values():
                walk(v, depth + 1)

    for _url, data in captured_json:
        walk(data)

    return links


def _oic_extract_bold_names(html: str) -> list:
    """
    Extrait les noms écrits en gras (<strong> ou <b>) dans un document de décret.
    Les décrets ontariens indiquent toujours le nom de la personne nommée en gras.
    Retourne une liste dédupliquée de chaînes (noms ou courtes expressions en gras).
    """
    soup = BeautifulSoup(html, "html.parser")
    names = []
    seen = set()
    for tag in soup.find_all(["strong", "b"]):
        name = tag.get_text(strip=True)
        # Garder seulement des textes ressemblant à un nom propre (1-6 mots, pas trop long)
        if not name or name in seen or len(name) > 100:
            continue
        words = name.split()
        if len(words) < 1 or len(words) > 6:
            continue
        # Ignorer les chaînes entièrement en majuscules (titres de section) ou trop courtes
        if name.isupper() or len(name) < 3:
            continue
        seen.add(name)
        names.append(name)
    return names


def _oic_soup_text_with_names(r, max_chars=2000) -> str:
    """
    Variante de soup_text pour les décrets : extrait le texte ET préfixe
    la liste des noms en gras trouvés dans le document.
    """
    soup = BeautifulSoup(r.text, "html.parser")

    bold_names = _oic_extract_bold_names(r.text)

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    main = (
        soup.find("main")
        or soup.find(id="content")
        or soup.find(class_="content")
        or soup.find(attrs={"role": "main"})
        or soup
    )
    lines = [
        l.strip()
        for l in main.get_text(separator="\n").splitlines()
        if len(l.strip()) > 10
    ]
    texte = "\n".join(lines[:200])[:max_chars]

    if bold_names:
        prefix = "PERSONNES/ENTITÉS EN GRAS DANS LE DÉCRET : " + " | ".join(bold_names) + "\n\n"
        return prefix + texte
    return texte


def _oic_fetch_content_playwright(lien: str) -> str:
    """Récupère le contenu d'un décret via Playwright (fallback JS)."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(lien, wait_until="networkidle", timeout=30_000)
            for sel in ["main", "article", "[role='main']", "#content"]:
                try:
                    page.wait_for_selector(sel, timeout=3_000)
                    break
                except Exception:
                    pass
            html = page.content()
            browser.close()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)[:2000]
    except Exception as e:
        print(f"    ⚠ Playwright contenu décret : {e}")
        return ""


def fetch_orders_in_council():
    print("  → Décrets du Conseil...")

    today = datetime.now()
    base = "https://www.ontario.ca"
    search_url = f"{base}/search/orders-in-council"

    order_links = []

    # --- Étape 1 : Playwright avec interception JSON + HTML rendu (mois courant puis précédent) ---
    for delta in [0, 1]:
        month = today.month - delta
        year = today.year
        if month <= 0:
            month += 12
            year -= 1

        url_mois = f"{search_url}?year={year}&month={month}"
        captured_json, rendered_html, all_hrefs = _oic_playwright_search(url_mois)

        # Priorité 1 : liens extraits du JSON intercepté
        if captured_json:
            order_links = _oic_json_to_links(captured_json, base)
            if order_links:
                print(f"    ✓ {len(order_links)} décret(s) via API JSON")
                break

        # Priorité 2 : liens extraits du HTML rendu
        if rendered_html:
            order_links = _oic_links_from_html(rendered_html, base)
            if order_links:
                print(f"    ✓ {len(order_links)} lien(s) dans le HTML rendu")
                break

        # Priorité 3 : fallback sur les hrefs bruts avec pattern d'année
        if all_hrefs and not order_links:
            year_re = re.compile(rf"\b{year}\b|\b{year - 1}\b")
            seen = set()
            for href in all_hrefs:
                if not href:
                    continue
                if year_re.search(href) and "/search/" not in href:
                    full = href if href.startswith("http") else base + href
                    if full not in seen:
                        seen.add(full)
                        order_links.append((href.rstrip("/").split("/")[-1], full))
            if order_links:
                print(f"    ✓ {len(order_links)} lien(s) via pattern année")
                break

    # --- Étape 2 : fallback HTTP simple sans filtre de date ---
    if not order_links:
        for url in [search_url, f"{search_url}?year={today.year}"]:
            r = safe_get(url)
            if r:
                order_links = _oic_links_from_html(r.text, base)
                if order_links:
                    print(f"    ✓ {len(order_links)} lien(s) via HTTP fallback")
                    break

    # --- Étape 3 : Playwright sans filtre de date ---
    if not order_links:
        _, rendered_html, _ = _oic_playwright_search(search_url)
        if rendered_html:
            order_links = _oic_links_from_html(rendered_html, base)

    # Aucun lien trouvé
    if not order_links:
        r = safe_get(search_url)
        if r and len(r.text) > 500:
            return (
                "Décrets du Conseil — page accessible mais aucun lien individuel détecté.\n"
                "Texte brut de la page :\n\n"
                + soup_text(r, max_chars=3000)
            )
        return "Page des Décrets du Conseil non disponible."

    # --- Récupérer le contenu de chaque décret (max 5) ---
    resultats = []
    for titre, lien in order_links[:5]:
        time.sleep(1)
        contenu = ""
        r_order = safe_get(lien)
        if r_order:
            # Utiliser la version enrichie qui extrait les noms en gras
            contenu = _oic_soup_text_with_names(r_order, max_chars=2000)
        if not contenu:
            # Fallback Playwright : extraire aussi les noms en gras du HTML rendu
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(lien, wait_until="networkidle", timeout=30_000)
                    html = page.content()
                    browser.close()

                class _FakeR:
                    text = html

                contenu = _oic_soup_text_with_names(_FakeR(), max_chars=2000)
            except Exception as e:
                print(f"    ⚠ Playwright fallback décret : {e}")
                contenu = _oic_fetch_content_playwright(lien)
        if contenu:
            resultats.append(f"Décret : {titre}\nLien : {lien}\n\n{contenu}")
            print(f"    ✓ Décret récupéré : {titre[:60]}")
        else:
            resultats.append(f"Décret : {titre}\nLien : {lien}\n(Contenu non accessible)")

    return (
        f"Décrets du Conseil ({len(resultats)} décret(s)) :\n\n"
        + "\n\n---\n\n".join(resultats)
    )


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
