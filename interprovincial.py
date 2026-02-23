"""
interprovincial.py — Surveillance des sources officielles des autres provinces
canadiennes pour détecter toute référence à l'Ontario.
"""

import time
import re
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from typing import Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

MOTS_CLES_ONTARIO = [
    "ontario", "ontario's", "ontarian", "ontarien", "ontarienne",
    "toronto", "ottawa", "hamilton", "london", "windsor", "brampton",
    "doug ford", "ford government", "gouvernement ford",
    "queen's park",
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


def fetch_quebec():
    resultats = []
    r = safe_get("https://www.publicationsduquebec.gouv.qc.ca/home.php")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Québec", "Gazette officielle du Québec",
                "https://www.publicationsduquebec.gouv.qc.ca", ext))

    feed = feedparser.parse("https://www.assnat.qc.ca/fr/travaux-parlementaires/journaux-debats/rss.xml")
    for entry in feed.entries[:5]:
        texte = entry.get("summary", "") + " " + entry.get("title", "")
        ext = texte_pertinent(texte)
        if ext:
            resultats.append(formater_resultat("Québec", "Journal des débats de l'AN",
                entry.get("link", ""), ext[:500]))
            break

    r = safe_get("https://www.seao.ca/OpportunityPublication/rechercheOc.aspx?lang=fr")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Québec", "SEAO — Appels d'offres",
                "https://www.seao.ca", ext))
    return resultats


def fetch_bc():
    resultats = []
    r = safe_get("https://www.bclaws.gov.bc.ca/civix/document/id/bcgaz1/bcgaz1/")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Colombie-Britannique", "BC Gazette",
                "https://www.bclaws.gov.bc.ca", ext))

    r = safe_get("https://www.leg.bc.ca/parliamentary-business/hansard-blues/house")
    if r:
        soup = BeautifulSoup(r.text, "html.parser")
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
                            f"Hansard BC — {a.get_text(strip=True)}", lien, ext))
                break

    r = safe_get("https://www.lobbyistsregistrar.bc.ca/app/secure/orl/lrs/do/lbrSearch")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Colombie-Britannique",
                "Registre des lobbyistes de la C.-B.", "https://www.lobbyistsregistrar.bc.ca", ext))
    return resultats


def fetch_alberta():
    resultats = []
    r = safe_get("https://open.alberta.ca/publications?subject=alberta-gazette")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Alberta", "Alberta Gazette",
                "https://open.alberta.ca", ext))

    r = safe_get("https://www.assembly.ab.ca/assembly-business/hansard")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Alberta", "Hansard de l'Assemblée de l'Alberta",
                "https://www.assembly.ab.ca", ext))

    r = safe_get("https://www.lobbyists.alberta.ca/public/registrant-search")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Alberta", "Registre des lobbyistes de l'Alberta",
                "https://www.lobbyists.alberta.ca", ext))
    return resultats


def fetch_manitoba():
    resultats = []
    r = safe_get("https://web2.gov.mb.ca/laws/gazette/index_gazette.php")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Manitoba", "Gazette du Manitoba",
                "https://web2.gov.mb.ca", ext))

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
                            f"Hansard Manitoba — {a.get_text(strip=True)}", lien, ext))
                break
    return resultats


def fetch_saskatchewan():
    resultats = []
    r = safe_get("https://publications.saskatchewan.ca/#/products?pageSize=20&keyword=gazette")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Saskatchewan", "Gazette de la Saskatchewan",
                "https://publications.saskatchewan.ca", ext))

    r = safe_get("https://www.legassembly.sk.ca/legislative-business/hansard/")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Saskatchewan",
                "Hansard de la Saskatchewan", "https://www.legassembly.sk.ca", ext))
    return resultats


def fetch_nova_scotia():
    resultats = []
    r = safe_get("https://nslegislature.ca/legislative-business/hansard")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Nouvelle-Écosse",
                "Hansard de la Nouvelle-Écosse", "https://nslegislature.ca", ext))
    return resultats


def fetch_new_brunswick():
    resultats = []
    r = safe_get("https://www.gnb.ca/legis/hansard/index-f.asp")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Nouveau-Brunswick",
                "Hansard du N.-B.", "https://www.gnb.ca/legis/hansard/", ext))

    r = safe_get("https://www.gnb.ca/gazette/index-f.asp")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Nouveau-Brunswick",
                "Gazette royale du N.-B.", "https://www.gnb.ca/gazette/", ext))
    return resultats


def fetch_pei():
    resultats = []
    r = safe_get("https://www.assembly.pe.ca/hansard")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Île-du-Prince-Édouard",
                "Hansard de l'ÎPÉ", "https://www.assembly.pe.ca", ext))
    return resultats


def fetch_newfoundland():
    resultats = []
    r = safe_get("https://www.assembly.nl.ca/HouseBusiness/Hansard")
    if r:
        ext = texte_pertinent(r.text)
        if ext:
            resultats.append(formater_resultat("Terre-Neuve-et-Labrador",
                "Hansard de T.-N.-L.", "https://www.assembly.nl.ca", ext))
    return resultats


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


def fetch_interprovincial() -> str:
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
                print(f"    ✓ {nom_province} : {len(resultats)} référence(s) trouvée(s)")
                tous_resultats.extend(resultats)
            time.sleep(0.5)
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
