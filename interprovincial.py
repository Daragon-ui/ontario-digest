"""
interprovincial.py — Surveillance des sources officielles des autres provinces
canadiennes pour détecter toute référence à l'Ontario.

Sources ciblées :
  - Gazettes officielles des provinces
  - Registres de lobbyistes provinciaux
  - Hansards et journaux législatifs
  - Bases de données d'appels d'offres
  - Organismes de réglementation (énergie, transport, environnement, finances)

L'objectif : repérer des mentions peu médiatisées de l'Ontario qui pourraient
signaler un conflit interprovincial, un accord en négociation, ou un scoop.
"""

import time
import re
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from typing import Optional
from fetchers import safe_get_js

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Mots-clés pour détecter les références à l'Ontario dans des documents étrangers
MOTS_CLES_ONTARIO = [
    "ontario", "ontario's", "ontarian", "ontarien", "ontarienne",
    "toronto", "ottawa", "hamilton", "london", "windsor", "brampton",
    "doug ford", "ford government", "gouvernement ford",
    "queen's park", "queen's park",
]

PATTERN_ONTARIO = re.compile(
    "|".join(re.escape(m) for m in MOTS_CLES_ONTARIO),
    re.IGNORECASE
)


def safe_get(url: str, timeout: int = 15) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"    ⚠ {url} : {e}")
        return None


def texte_pertinent(html_ou_texte: str, max_chars: int = 800) -> str:
    """Extrait les paragraphes contenant des mots-clés ontariens."""
    if "<" in html_ou_texte:
        soup = BeautifulSoup(html_ou_texte, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        blocs = soup.find_all(["p", "li", "td", "div"])
        paragraphes = [b.get_text(" ", strip=True) for b in blocs]
    else:
        paragraphes = html_ou_texte.splitlines()

    pertinents = []
    for para in paragraphes:
        if len(para) < 30:
            continue
        if PATTERN_ONTARIO.search(para):
            pertinents.append(para.strip())

    return "\n\n".join(pertinents)[:max_chars] if pertinents else ""


def formater_resultat(province: str, source: str, url: str, extrait: str) -> str:
    if not extrait.strip():
        return ""
    return (
        f"PROVINCE : {province}\n"
        f"SOURCE   : {source}\n"
        f"URL      : {url}\n"
        f"EXTRAIT  :\n{extrait}"
    )


# ---------------------------------------------------------------------------
# QUÉBEC
# ---------------------------------------------------------------------------
def fetch_quebec():
    resultats = []

    # Gazette officielle du Québec — Index des publications récentes
    r = safe_get("https://www.publicationsduquebec.gouv.qc.ca/home.php")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Québec", "Gazette officielle du Québec",
                "https://www.publicationsduquebec.gouv.qc.ca", ext))

    # Assemblée nationale — Journal des débats (flux RSS)
    feed = feedparser.parse("https://www.assnat.qc.ca/fr/travaux-parlementaires/journaux-debats/rss.xml")
    for entry in feed.entries[:5]:
        texte = entry.get("summary", "") + " " + entry.get("title", "")
        ext = texte_pertinent(texte)
        if ext:
            resultats.append(formater_resultat("Québec", "Journal des débats de l'AN",
                entry.get("link", ""), ext[:500]))
            break

    # SEAO — Appels d'offres (site ASP.NET JS-dépendant)
    r = safe_get_js("https://www.seao.ca/OpportunityPublication/rechercheOc.aspx?lang=fr")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Québec", "SEAO — Appels d'offres",
                "https://www.seao.ca", ext))

    return resultats


# ---------------------------------------------------------------------------
# COLOMBIE-BRITANNIQUE
# ---------------------------------------------------------------------------
def fetch_bc():
    resultats = []

    # BC Gazette
    r = safe_get("https://www.bclaws.gov.bc.ca/civix/document/id/bcgaz1/bcgaz1/")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Colombie-Britannique", "BC Gazette",
                "https://www.bclaws.gov.bc.ca", ext))

    # BC Legislature — Hansard (Debates)
    r = safe_get("https://www.leg.bc.ca/parliamentary-business/hansard-blues/house")
    if r:
        soup = BeautifulSoup(r.text, "html.parser")
        # Trouver le lien le plus récent
        for a in soup.find_all("a", href=True):
            if "hansard" in a["href"].lower() or "debate" in a["href"].lower():
                lien = a["href"]
                if not lien.startswith("http"):
                    lien = "https://www.leg.bc.ca" + lien
                time.sleep(1)
                r2 = safe_get(lien)
                if r2:
                    ext = texte_pertinent(r2.text)
                    if ext:
                        resultats.append(formater_resultat("Colombie-Britannique",
                            f"Hansard BC — {a.get_text(strip=True)}",
                            lien, ext))
                break

    # BC Lobbyists Registry
    r = safe_get("https://www.lobbyistsregistrar.bc.ca/app/secure/orl/lrs/do/lbrSearch")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Colombie-Britannique",
                "Registre des lobbyistes de la C.-B.", "https://www.lobbyistsregistrar.bc.ca", ext))

    # BC Utilities Commission (énergie/transport)
    r = safe_get("https://www.bcuc.com/OurWork/Applications")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Colombie-Britannique",
                "BC Utilities Commission", "https://www.bcuc.com", ext))

    return resultats


# ---------------------------------------------------------------------------
# ALBERTA
# ---------------------------------------------------------------------------
def fetch_alberta():
    resultats = []

    # Alberta Gazette
    r = safe_get("https://open.alberta.ca/publications?subject=alberta-gazette")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Alberta", "Alberta Gazette",
                "https://open.alberta.ca", ext))

    # Alberta Legislature — Hansard
    r = safe_get("https://www.assembly.ab.ca/assembly-business/hansard")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Alberta", "Hansard de l'Assemblée de l'Alberta",
                "https://www.assembly.ab.ca", ext))

    # Alberta Lobbyists Registry
    r = safe_get("https://www.lobbyists.alberta.ca/public/registrant-search")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Alberta", "Registre des lobbyistes de l'Alberta",
                "https://www.lobbyists.alberta.ca", ext))

    # Alberta Utilities Commission
    r = safe_get("https://www.auc.ab.ca/regulatory-documents")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Alberta", "Alberta Utilities Commission",
                "https://www.auc.ab.ca", ext))

    return resultats


# ---------------------------------------------------------------------------
# MANITOBA
# ---------------------------------------------------------------------------
def fetch_manitoba():
    resultats = []

    # Manitoba Gazette
    r = safe_get("https://web2.gov.mb.ca/laws/gazette/index_gazette.php")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Manitoba", "Gazette du Manitoba",
                "https://web2.gov.mb.ca", ext))

    # Manitoba Legislature — Debates
    r = safe_get("https://www.gov.mb.ca/legislature/hansard/index.html")
    if r:
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            if "hansard" in a["href"].lower() or ".html" in a["href"]:
                lien = a["href"]
                if not lien.startswith("http"):
                    lien = "https://www.gov.mb.ca/legislature/hansard/" + lien
                time.sleep(1)
                r2 = safe_get(lien)
                if r2:
                    ext = texte_pertinent(r2.text)
                    if ext:
                        resultats.append(formater_resultat("Manitoba",
                            f"Hansard Manitoba — {a.get_text(strip=True)}",
                            lien, ext))
                break

    return resultats


# ---------------------------------------------------------------------------
# SASKATCHEWAN
# ---------------------------------------------------------------------------
def fetch_saskatchewan():
    resultats = []

    # Saskatchewan Gazette — SPA avec routage côté client, nécessite JavaScript
    r = safe_get_js("https://publications.saskatchewan.ca/#/products?pageSize=20&keyword=gazette")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Saskatchewan", "Gazette de la Saskatchewan",
                "https://publications.saskatchewan.ca", ext))

    # Saskatchewan Legislature — Hansard
    r = safe_get("https://www.legassembly.sk.ca/legislative-business/hansard/")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Saskatchewan",
                "Hansard de la Saskatchewan", "https://www.legassembly.sk.ca", ext))

    return resultats


# ---------------------------------------------------------------------------
# NOUVELLES-ÉCOSSE
# ---------------------------------------------------------------------------
def fetch_nova_scotia():
    resultats = []

    # NS Legislature — Hansard
    r = safe_get("https://nslegislature.ca/legislative-business/hansard")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Nouvelle-Écosse",
                "Hansard de la Nouvelle-Écosse", "https://nslegislature.ca", ext))

    # NS Utility and Review Board
    r = safe_get("https://nsuarb.novascotia.ca/hearings")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Nouvelle-Écosse",
                "NS Utility and Review Board", "https://nsuarb.novascotia.ca", ext))

    return resultats


# ---------------------------------------------------------------------------
# NOUVEAU-BRUNSWICK
# ---------------------------------------------------------------------------
def fetch_new_brunswick():
    resultats = []

    # NB Legislature — Hansard
    r = safe_get("https://www.gnb.ca/legis/hansard/index-f.asp")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Nouveau-Brunswick",
                "Hansard du N.-B.", "https://www.gnb.ca/legis/hansard/", ext))

    # Gazette royale du Nouveau-Brunswick
    r = safe_get("https://www.gnb.ca/gazette/index-f.asp")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Nouveau-Brunswick",
                "Gazette royale du N.-B.", "https://www.gnb.ca/gazette/", ext))

    return resultats


# ---------------------------------------------------------------------------
# ÎLE-DU-PRINCE-ÉDOUARD
# ---------------------------------------------------------------------------
def fetch_pei():
    resultats = []

    r = safe_get("https://www.assembly.pe.ca/hansard")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Île-du-Prince-Édouard",
                "Hansard de l'ÎPÉ", "https://www.assembly.pe.ca", ext))
    return resultats


# ---------------------------------------------------------------------------
# TERRE-NEUVE-ET-LABRADOR
# ---------------------------------------------------------------------------
def fetch_newfoundland():
    resultats = []

    r = safe_get("https://www.assembly.nl.ca/HouseBusiness/Hansard")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Terre-Neuve-et-Labrador",
                "Hansard de T.-N.-L.", "https://www.assembly.nl.ca", ext))

    # NL Public Utilities Board
    r = safe_get("https://pub.nl.ca/applications/")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Terre-Neuve-et-Labrador",
                "NL Public Utilities Board", "https://pub.nl.ca", ext))

    return resultats


# ---------------------------------------------------------------------------
# TERRITOIRES (couverture légère)
# ---------------------------------------------------------------------------
def fetch_territories():
    resultats = []
    sources = [
        ("Yukon", "Assemblée législative du Yukon",
         "https://yukonassembly.ca/house-business/hansard", "https://yukonassembly.ca"),
        ("T.N.-O.", "Assemblée législative des T.N.-O.",
         "https://www.ntassembly.ca/content/hansard", "https://www.ntassembly.ca"),
        ("Nunavut", "Assemblée législative du Nunavut",
         "https://www.assembly.nu.ca/hansard", "https://www.assembly.nu.ca"),
    ]
    for territoire, nom, url, base in sources:
        r = safe_get(url)
        if r:
            ext = texte_pertinent(r.text, max_chars=400)
            if ext:
                resultats.append(formater_resultat(territoire, nom, url, ext))
    return resultats


# ---------------------------------------------------------------------------
# Orchestrateur principal
# ---------------------------------------------------------------------------
def fetch_interprovincial() -> str:
    """
    Lance la surveillance de toutes les sources interprovinciales.
    Retourne un bloc de texte formaté pour Claude.
    """
    print("  → Surveillance interprovinciale...")

    fetchers = [
        ("Québec", fetch_quebec),
        ("Colombie-Britannique", fetch_bc),
        ("Alberta", fetch_alberta),
        ("Manitoba", fetch_manitoba),
        ("Saskatchewan", fetch_saskatchewan),
        ("Nouvelle-Écosse", fetch_nova_scotia),
        ("Nouveau-Brunswick", fetch_new_brunswick),
        ("Île-du-Prince-Édouard", fetch_pei),
        ("Terre-Neuve-et-Labrador", fetch_newfoundland),
        ("Territoires", fetch_territories),
    ]

    tous_resultats = []
    for nom_province, fn in fetchers:
        try:
            resultats = fn()
            if resultats:
                print(f"    ✓ {nom_province} : {len(resultats)} référence(s) à l'Ontario trouvée(s)")
                tous_resultats.extend(resultats)
            time.sleep(0.5)  # Politesse entre provinces
        except Exception as e:
            print(f"    ⚠ Erreur pour {nom_province} : {e}")

    if not tous_resultats:
        return (
            "Aucune référence directe à l'Ontario détectée aujourd'hui dans "
            "les sources officielles des autres provinces et territoires canadiens."
        )

    separateur = "\n" + "-" * 50 + "\n"
    bloc = separateur.join(r for r in tous_resultats if r)

    return (
        f"[{len(tous_resultats)} référence(s) à l'Ontario détectée(s) hors Ontario]\n\n"
        f"INSTRUCTIONS POUR CLAUDE : Pour chaque extrait ci-dessous, évalue le potentiel "
        f"journalistique (faible / moyen / élevé) et explique pourquoi.\n\n"
        f"{bloc}"
    )
