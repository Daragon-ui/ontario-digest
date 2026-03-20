"""
Ontario Parks Reservation Bot
==============================
Supporte deux types de réservations :
  - backcountry : arrière-pays en canot, itinéraire nuit par nuit
  - frontcountry : camping régulier (site numéroté)

Modes :
  explore  → navigue sans se connecter, vérifie la disponibilité
  dry_run  → se connecte, remplit tout, s'ARRÊTE avant la confirmation de paiement
  live     → exécute la réservation complète

Lancement :
  python parks_bot/bot.py --mode explore
  python parks_bot/bot.py --mode dry_run
  python parks_bot/bot.py --mode live --wait  # attend 7h00 AM ET automatiquement
"""

import argparse
import logging
import random
import time
from datetime import datetime, timezone, timedelta

import yaml
from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PlaywrightTimeout

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("parks-bot")

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
BASE_URL = "https://reservations.ontarioparks.ca"
SEARCH_URL = BASE_URL

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config(path: str = "parks_bot/config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def human_delay(cfg: dict) -> None:
    """Pause aléatoire pour simuler un comportement humain."""
    ms = random.randint(cfg["bot"]["min_delay_ms"], cfg["bot"]["max_delay_ms"])
    time.sleep(ms / 1000)


def human_type(page, selector: str, text: str, cfg: dict) -> None:
    """Tape un texte caractère par caractère avec des délais variables."""
    page.click(selector)
    if cfg["bot"]["slow_typing"]:
        for char in text:
            page.type(selector, char)
            time.sleep(random.uniform(0.05, 0.18))
    else:
        page.fill(selector, text)


def wait_for_opening(open_time_str: str) -> None:
    """
    Attend que l'heure d'ouverture soit atteinte (heure de l'Est).
    Utilise pytz si disponible, sinon calcule manuellement EDT/EST.
    """
    try:
        import zoneinfo
        ET = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.now(ET)
        h, m = map(int, open_time_str.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
    except ImportError:
        # Fallback: EDT = UTC-4 en été (mai–nov), EST = UTC-5 en hiver
        utc_offset = -4  # EDT pour août
        ET = timezone(timedelta(hours=utc_offset))
        now = datetime.now(ET)
        h, m = map(int, open_time_str.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)

    log.info(f"⏰  Fenêtre d'ouverture prévue : {target.strftime('%Y-%m-%d %H:%M:%S')} ET")
    while True:
        try:
            remaining = (target - datetime.now(ET)).total_seconds()
        except Exception:
            remaining = (target - datetime.now(timezone(timedelta(hours=-4)))).total_seconds()

        if remaining <= 0:
            log.info("🚀  Heure d'ouverture atteinte — démarrage du bot !")
            break
        elif remaining > 60:
            log.info(f"   Attente : {int(remaining // 60)}m {int(remaining % 60)}s restantes...")
            time.sleep(30)
        else:
            log.info(f"   Compte à rebours : {int(remaining)}s...")
            time.sleep(1)


# ---------------------------------------------------------------------------
# Navigateur
# ---------------------------------------------------------------------------

def open_browser(pw: Playwright, cfg: dict):
    """Lance Chromium avec des paramètres discrets."""
    browser = pw.chromium.launch(
        headless=cfg["bot"]["headless"],
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        locale="fr-CA",
        timezone_id="America/Toronto",
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = context.new_page()
    return browser, context, page


# ---------------------------------------------------------------------------
# Étapes communes
# ---------------------------------------------------------------------------

def navigate_to_search(page, cfg: dict) -> None:
    log.info("📍  Navigation vers Ontario Parks Reservations...")
    page.goto(SEARCH_URL, wait_until="networkidle", timeout=30_000)
    human_delay(cfg)
    try:
        page.click("text=Accept", timeout=3_000)
        log.info("   Cookies acceptés.")
        human_delay(cfg)
    except PlaywrightTimeout:
        pass


def login(page, cfg: dict) -> bool:
    log.info("🔐  Connexion au compte Ontario Parks...")
    try:
        for btn_text in ["Sign in", "Log in", "Connexion", "Se connecter"]:
            try:
                page.click(f"text={btn_text}", timeout=3_000)
                break
            except PlaywrightTimeout:
                continue
        human_delay(cfg)

        email_sel = "input[type='email'], input[name='email'], #email, #Email"
        pwd_sel = "input[type='password'], input[name='password'], #password, #Password"

        page.wait_for_selector(email_sel, timeout=10_000)
        human_type(page, email_sel, cfg["account"]["email"], cfg)
        human_delay(cfg)
        human_type(page, pwd_sel, cfg["account"]["password"], cfg)
        human_delay(cfg)

        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle", timeout=15_000)
        log.info("   Connexion réussie.")
        return True

    except Exception as e:
        log.error(f"   Échec de connexion : {e}")
        return False


def proceed_to_checkout(page, cfg: dict) -> bool:
    log.info("🛒  Passage au paiement...")
    for btn_text in ["Proceed to Checkout", "Add to Cart", "Reserve", "Réserver", "Continue"]:
        try:
            page.click(f"text={btn_text}", timeout=5_000)
            page.wait_for_load_state("networkidle", timeout=15_000)
            log.info(f"   Bouton '{btn_text}' cliqué.")
            return True
        except PlaywrightTimeout:
            continue
    log.warning("   Bouton de paiement non trouvé — vérifiez manuellement.")
    return False


def confirm_reservation(page, cfg: dict) -> None:
    """SEULEMENT en mode 'live' : confirme et finalise."""
    log.info("✅  Confirmation de la réservation...")

    # Accepter toutes les cases à cocher (conditions, pénalités, etc.)
    for checkbox_sel in ["input[type='checkbox']", "input[name*='agree']", "input[name*='terms']"]:
        try:
            for cb in page.query_selector_all(checkbox_sel):
                if not cb.is_checked():
                    cb.check()
                    human_delay(cfg)
        except Exception:
            pass

    for btn_text in ["Confirm", "Complete Reservation", "Place Order", "Confirmer", "Finaliser"]:
        try:
            page.click(f"text={btn_text}", timeout=5_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
            log.info("🎉  Réservation confirmée !")
            return
        except PlaywrightTimeout:
            continue

    log.warning("   Bouton de confirmation non trouvé — intervention manuelle requise.")


# ---------------------------------------------------------------------------
# Flux BACKCOUNTRY (arrière-pays en canot)
# ---------------------------------------------------------------------------

def search_backcountry(page, cfg: dict) -> bool:
    """
    Remplit le formulaire de réservation backcountry de Killarney.
    Retourne True si la recherche a été lancée avec succès.
    """
    r = cfg["reservation"]
    night1 = r["itinerary"][0]
    log.info(
        f"🔍  Backcountry — Killarney | Accès : {r['access_point']} | "
        f"Entrée : {r['entry_date']} | {r['num_nights']} nuits"
    )

    page.goto(SEARCH_URL, wait_until="networkidle", timeout=30_000)
    human_delay(cfg)

    # Étape 1 : Sélectionner le type de réservation "Backcountry" / "Arrière-pays"
    for label in ["Backcountry", "Arrière-pays", "Interior", "Canoe"]:
        try:
            page.click(f"text={label}", timeout=3_000)
            human_delay(cfg)
            log.info(f"   Type '{label}' sélectionné.")
            break
        except PlaywrightTimeout:
            continue

    # Étape 2 : Sélectionner le parc (Killarney)
    try:
        park_input = page.wait_for_selector(
            "input[placeholder*='park'], input[placeholder*='parc'], "
            "input[placeholder*='location'], #park-search",
            timeout=8_000,
        )
        park_input.click()
        human_delay(cfg)
        for char in r["park_name"]:
            park_input.type(char)
            time.sleep(random.uniform(0.07, 0.15))
        human_delay(cfg)
        # Choisir Killarney dans la liste déroulante
        page.wait_for_selector(f"text={r['park_name']}", timeout=8_000)
        page.click(f"text={r['park_name']}", timeout=5_000)
        human_delay(cfg)
        log.info(f"   Parc '{r['park_name']}' sélectionné.")
    except PlaywrightTimeout:
        log.warning("   Champ de parc non trouvé — le site a peut-être changé de structure.")

    # Étape 3 : Point d'accès (Bell Lake)
    try:
        for label in ["Access Point", "Point d'accès", "Entry Point"]:
            el = page.query_selector(f"select:near(:text('{label}'))")
            if el:
                el.select_option(label=r["access_point"])
                human_delay(cfg)
                log.info(f"   Point d'accès '{r['access_point']}' sélectionné.")
                break
    except Exception:
        log.warning(f"   Point d'accès non trouvé automatiquement.")

    # Étape 4 : Date d'entrée
    try:
        date_input = page.query_selector(
            "input[type='date'], input[name*='arrival'], input[name*='entry'], input[name*='date']"
        )
        if date_input:
            date_input.fill(r["entry_date"])
            human_delay(cfg)
            log.info(f"   Date d'entrée : {r['entry_date']}")
    except Exception as e:
        log.warning(f"   Champ de date non trouvé : {e}")

    # Étape 5 : Nombre de nuits
    try:
        el = page.query_selector("select[name*='night'], input[name*='night'], #nights, select[name*='duration']")
        if el:
            el.select_option(str(r["num_nights"]))
            human_delay(cfg)
    except Exception:
        pass

    # Étape 6 : Taille du groupe
    try:
        el = page.query_selector("select[name*='party'], input[name*='party'], select[name*='person'], #partySize")
        if el:
            el.select_option(str(r["party_size"]))
            human_delay(cfg)
    except Exception:
        pass

    # Étape 7 : Nombre de canots / embarcations
    try:
        for label in ["Canoe", "Canot", "Watercraft", "Embarcation", "Equipment"]:
            el = page.query_selector(f"select:near(:text('{label}'))")
            if el:
                el.select_option(str(r["num_canoes"]))
                human_delay(cfg)
                log.info(f"   Canots : {r['num_canoes']}")
                break
    except Exception:
        pass

    # Lancer la recherche
    try:
        page.click(
            "button[type='submit'], button:has-text('Search'), button:has-text('Rechercher'), "
            "button:has-text('Find'), button:has-text('Trouver')",
            timeout=5_000,
        )
        page.wait_for_load_state("networkidle", timeout=20_000)
        log.info("   Recherche lancée.")
        return True
    except PlaywrightTimeout:
        log.warning("   Bouton de recherche non trouvé.")
        return False


def select_backcountry_itinerary(page, cfg: dict) -> bool:
    """
    Sélectionne les sites pour chaque nuit de l'itinéraire.
    Retourne True si l'itinéraire complet a été sélectionné.
    """
    r = cfg["reservation"]
    itinerary = r["itinerary"]
    log.info(f"🗺️   Sélection de l'itinéraire ({len(itinerary)} nuits)...")

    for night_cfg in itinerary:
        night = night_cfg["night"]
        lake = night_cfg["lake"]
        site = night_cfg.get("site_number", "")
        log.info(f"   Nuit {night} : {lake} {'site #' + site if site else '(premier disponible)'}")

        # Chercher le lac dans les résultats
        try:
            page.click(f"text={lake}", timeout=8_000)
            human_delay(cfg)
        except PlaywrightTimeout:
            log.warning(f"   Lac '{lake}' non trouvé dans les résultats pour la nuit {night}.")
            return False

        # Sélectionner le site spécifique ou le premier disponible
        if site:
            try:
                page.click(f"text=#{site}", timeout=6_000)
                human_delay(cfg)
                log.info(f"   Site #{site} sélectionné.")
            except PlaywrightTimeout:
                log.warning(f"   Site #{site} non disponible — tentative avec le premier disponible.")
                # Fallback: premier site disponible sur ce lac
                fallbacks = r.get("fallback_sites_night1", []) if night == 1 else []
                selected = False
                for fb in fallbacks:
                    if not fb:
                        continue
                    try:
                        page.click(f"text=#{fb}", timeout=4_000)
                        log.info(f"   Site de remplacement #{fb} sélectionné.")
                        selected = True
                        break
                    except PlaywrightTimeout:
                        continue
                if not selected:
                    try:
                        page.click(
                            ".site-item:first-child, .campsite:first-child, [data-available='true']:first-child",
                            timeout=5_000,
                        )
                        log.info("   Premier site disponible sélectionné.")
                    except PlaywrightTimeout:
                        log.error(f"   Aucun site disponible pour la nuit {night} à {lake}.")
                        return False
        else:
            # Prendre le premier disponible
            try:
                page.click(
                    ".site-item:first-child, .campsite:first-child, [data-available='true']:first-child",
                    timeout=5_000,
                )
                log.info("   Premier site disponible sélectionné.")
                human_delay(cfg)
            except PlaywrightTimeout:
                log.error(f"   Aucun site disponible pour la nuit {night} à {lake}.")
                return False

        # Confirmer la sélection de cette nuit (bouton "Next" ou "Suivant" entre les nuits)
        if night < len(itinerary):
            for btn in ["Next Night", "Next", "Suivant", "Continue"]:
                try:
                    page.click(f"text={btn}", timeout=4_000)
                    page.wait_for_load_state("networkidle", timeout=10_000)
                    human_delay(cfg)
                    break
                except PlaywrightTimeout:
                    continue

    log.info("   Itinéraire complet sélectionné.")
    return True


# ---------------------------------------------------------------------------
# Flux FRONTCOUNTRY (camping régulier)
# ---------------------------------------------------------------------------

def search_frontcountry(page, cfg: dict) -> None:
    """Remplit le formulaire de recherche frontcountry."""
    r = cfg["reservation"]
    log.info(f"🔍  Frontcountry — {r['park_name']} | Site {r.get('site_number','')} | {r['entry_date']}")

    page.goto(SEARCH_URL, wait_until="networkidle", timeout=30_000)
    human_delay(cfg)

    try:
        park_input = page.wait_for_selector(
            "input[placeholder*='park'], input[placeholder*='parc'], #park-search",
            timeout=10_000,
        )
        park_input.click()
        human_delay(cfg)
        for char in r["park_name"]:
            park_input.type(char)
            time.sleep(random.uniform(0.07, 0.15))
        human_delay(cfg)
        page.wait_for_selector(f"text={r['park_name']}", timeout=8_000)
        page.click(f"text={r['park_name']}", timeout=5_000)
        human_delay(cfg)
    except PlaywrightTimeout:
        log.warning("   Champ parc non trouvé.")

    try:
        date_input = page.query_selector("input[type='date'], input[name*='arrival'], input[name*='date']")
        if date_input:
            date_input.fill(r["entry_date"])
            human_delay(cfg)
    except Exception:
        pass

    try:
        el = page.query_selector("select[name*='night'], input[name*='night'], #nights")
        if el:
            el.select_option(str(r["num_nights"]))
            human_delay(cfg)
    except Exception:
        pass

    try:
        el = page.query_selector("select[name*='party'], input[name*='party'], #partySize")
        if el:
            el.select_option(str(r["party_size"]))
            human_delay(cfg)
    except Exception:
        pass

    try:
        page.click("button[type='submit'], button:has-text('Search'), button:has-text('Rechercher')", timeout=5_000)
        page.wait_for_load_state("networkidle", timeout=20_000)
        log.info("   Recherche lancée.")
    except PlaywrightTimeout:
        log.warning("   Bouton de recherche non trouvé.")


def select_frontcountry_site(page, cfg: dict) -> bool:
    site_num = cfg["reservation"].get("site_number", "")
    log.info(f"🏕️   Sélection du site {'#' + site_num if site_num else '(premier disponible)'}...")

    try:
        if site_num:
            page.click(f"text=#{site_num}", timeout=8_000)
        else:
            page.click(".site-item:first-child, .campsite:first-child, [data-available='true']:first-child", timeout=8_000)
        human_delay(cfg)
        log.info("   Site sélectionné.")
        return True
    except PlaywrightTimeout:
        log.warning(f"   Site #{site_num} non trouvé ou non disponible.")
        return False


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def run(mode: str, wait: bool, config_path: str) -> None:
    cfg = load_config(config_path)
    effective_mode = mode or cfg["bot"]["mode"]
    r = cfg["reservation"]
    res_type = r.get("type", "frontcountry")

    log.info(f"🤖  Ontario Parks Bot — mode : {effective_mode.upper()} | type : {res_type}")
    if res_type == "backcountry":
        log.info(f"    Parc : {r['park_name']} | Accès : {r['access_point']} | Entrée : {r['entry_date']}")
        log.info(f"    Itinéraire : " + " → ".join(
            f"Nuit {n['night']}: {n['lake']} #{n.get('site_number','?')}" for n in r["itinerary"]
        ))
    else:
        log.info(f"    Parc : {r['park_name']} | Site : {r.get('site_number','')} | Entrée : {r['entry_date']}")

    if wait:
        wait_for_opening(cfg["scheduler"]["open_time"])

    with sync_playwright() as pw:
        browser, context, page = open_browser(pw, cfg)

        try:
            if effective_mode == "explore":
                navigate_to_search(page, cfg)
                if res_type == "backcountry":
                    search_backcountry(page, cfg)
                else:
                    search_frontcountry(page, cfg)
                log.info("🔎  Mode EXPLORE : résultats dans le navigateur. Ctrl+C pour quitter.")
                input("    [Appuyez sur Entrée pour fermer le navigateur]")

            elif effective_mode == "dry_run":
                navigate_to_search(page, cfg)
                if not login(page, cfg):
                    log.error("Connexion échouée — arrêt.")
                    return
                if res_type == "backcountry":
                    if search_backcountry(page, cfg) and select_backcountry_itinerary(page, cfg):
                        proceed_to_checkout(page, cfg)
                        log.info("🛑  DRY RUN : arrêt avant confirmation. Rien n'a été facturé.")
                        input("    [Appuyez sur Entrée pour fermer le navigateur]")
                    else:
                        log.warning("Itinéraire incomplet — vérifiez les disponibilités.")
                else:
                    search_frontcountry(page, cfg)
                    if select_frontcountry_site(page, cfg):
                        proceed_to_checkout(page, cfg)
                        log.info("🛑  DRY RUN : arrêt avant confirmation. Rien n'a été facturé.")
                        input("    [Appuyez sur Entrée pour fermer le navigateur]")

            elif effective_mode == "live":
                navigate_to_search(page, cfg)
                if not login(page, cfg):
                    log.error("Connexion échouée — arrêt.")
                    return
                if res_type == "backcountry":
                    if search_backcountry(page, cfg) and select_backcountry_itinerary(page, cfg):
                        if proceed_to_checkout(page, cfg):
                            confirm_reservation(page, cfg)
                            log.info("🎉  Réservation complétée ! Vérifiez votre courriel.")
                else:
                    search_frontcountry(page, cfg)
                    if select_frontcountry_site(page, cfg):
                        if proceed_to_checkout(page, cfg):
                            confirm_reservation(page, cfg)
                            log.info("🎉  Réservation complétée ! Vérifiez votre courriel.")

            else:
                log.error(f"Mode inconnu : {effective_mode}. Choisir : explore | dry_run | live")

        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ontario Parks Reservation Bot")
    parser.add_argument(
        "--mode",
        choices=["explore", "dry_run", "live"],
        help="Mode de fonctionnement (remplace config.yaml si spécifié)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Attendre l'heure d'ouverture définie dans config.yaml avant de démarrer",
    )
    parser.add_argument(
        "--config",
        default="parks_bot/config.yaml",
        help="Chemin vers le fichier de configuration (défaut : parks_bot/config.yaml)",
    )
    args = parser.parse_args()
    run(args.mode, args.wait, args.config)
