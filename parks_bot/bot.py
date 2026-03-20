"""
Ontario Parks Reservation Bot
==============================
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
from pathlib import Path

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
LOGIN_URL = f"{BASE_URL}/create-account"
SEARCH_URL = BASE_URL  # Le moteur de recherche est sur la page d'accueil

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
    Affiche un compte à rebours toutes les 30 secondes.
    """
    ET = timezone(timedelta(hours=-5))  # EST — ajuster à -4 en été (EDT)
    now = datetime.now(ET)
    h, m = map(int, open_time_str.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)

    log.info(f"⏰  Fenêtre d'ouverture prévue : {target.strftime('%Y-%m-%d %H:%M:%S')} ET")
    while True:
        remaining = (target - datetime.now(ET)).total_seconds()
        if remaining <= 0:
            log.info("🚀  Heure d'ouverture atteinte — démarrage du bot !")
            break
        if remaining > 60:
            log.info(f"   Attente : {int(remaining // 60)}m {int(remaining % 60)}s restantes...")
            time.sleep(30)
        else:
            log.info(f"   Compte à rebours : {int(remaining)}s...")
            time.sleep(1)


# ---------------------------------------------------------------------------
# Étapes de navigation
# ---------------------------------------------------------------------------

def open_browser(pw: Playwright, cfg: dict):
    """Lance Chromium avec des paramètres discrets."""
    browser = pw.chromium.launch(
        headless=cfg["bot"]["headless"],
        args=[
            "--disable-blink-features=AutomationControlled",
        ],
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
    # Masque le flag webdriver pour éviter la détection basique
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = context.new_page()
    return browser, context, page


def navigate_to_search(page, cfg: dict) -> None:
    """Va sur la page de recherche et accepte les cookies si nécessaire."""
    log.info("📍  Navigation vers Ontario Parks Reservations...")
    page.goto(SEARCH_URL, wait_until="networkidle", timeout=30_000)
    human_delay(cfg)

    # Accepter les cookies si le bandeau apparaît
    try:
        page.click("text=Accept", timeout=3000)
        log.info("   Cookies acceptés.")
        human_delay(cfg)
    except PlaywrightTimeout:
        pass  # Pas de bandeau de cookies, c'est correct


def login(page, cfg: dict) -> bool:
    """Se connecte au compte Ontario Parks."""
    log.info("🔐  Connexion au compte Ontario Parks...")

    try:
        # Chercher le bouton de connexion (le texte peut varier)
        for btn_text in ["Sign in", "Log in", "Connexion", "Se connecter"]:
            try:
                page.click(f"text={btn_text}", timeout=3000)
                break
            except PlaywrightTimeout:
                continue
        human_delay(cfg)

        # Remplir le formulaire de connexion
        email = cfg["account"]["email"]
        password = cfg["account"]["password"]

        email_sel = "input[type='email'], input[name='email'], #email, #Email"
        pwd_sel = "input[type='password'], input[name='password'], #password, #Password"

        page.wait_for_selector(email_sel, timeout=10_000)
        human_type(page, email_sel, email, cfg)
        human_delay(cfg)
        human_type(page, pwd_sel, password, cfg)
        human_delay(cfg)

        # Soumettre
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle", timeout=15_000)
        log.info("   Connexion réussie.")
        return True

    except Exception as e:
        log.error(f"   Échec de connexion : {e}")
        return False


def search_campsite(page, cfg: dict) -> None:
    """Remplit le formulaire de recherche avec les paramètres de réservation."""
    r = cfg["reservation"]
    log.info(f"🔍  Recherche : {r['park_name']} — Site {r['site_number']} — {r['arrival_date']} ({r['num_nights']} nuits)")

    page.goto(SEARCH_URL, wait_until="networkidle", timeout=30_000)
    human_delay(cfg)

    # Sélectionner le parc
    try:
        park_input = page.wait_for_selector(
            "input[placeholder*='park'], input[placeholder*='parc'], #park-search, [data-testid='park-search']",
            timeout=10_000,
        )
        park_input.click()
        human_delay(cfg)
        park_input.type(r["park_name"])
        human_delay(cfg)
        # Choisir la première suggestion correspondante
        page.wait_for_selector(f"text={r['park_name']}", timeout=8_000)
        page.click(f"text={r['park_name']}", timeout=5_000)
        human_delay(cfg)
    except PlaywrightTimeout:
        log.warning("   Impossible de localiser le champ de recherche de parc automatiquement.")
        log.warning("   Le site a peut-être changé de structure — intervention manuelle requise.")

    # Date d'arrivée
    try:
        arrival_dt = datetime.strptime(r["arrival_date"], "%Y-%m-%d")
        date_input = page.query_selector("input[type='date'], input[name*='arrival'], input[name*='date']")
        if date_input:
            date_input.fill(r["arrival_date"])
            human_delay(cfg)
    except Exception as e:
        log.warning(f"   Champ de date non trouvé automatiquement : {e}")

    # Nombre de nuits
    try:
        nights_sel = "select[name*='night'], input[name*='night'], #nights"
        el = page.query_selector(nights_sel)
        if el:
            el.select_option(str(r["num_nights"]))
            human_delay(cfg)
    except Exception:
        pass

    # Taille du groupe
    try:
        party_sel = "select[name*='party'], input[name*='party'], select[name*='person'], #partySize"
        el = page.query_selector(party_sel)
        if el:
            el.select_option(str(r["party_size"]))
            human_delay(cfg)
    except Exception:
        pass

    # Lancer la recherche
    try:
        page.click("button[type='submit'], button:has-text('Search'), button:has-text('Rechercher')", timeout=5_000)
        page.wait_for_load_state("networkidle", timeout=20_000)
        log.info("   Recherche lancée.")
    except PlaywrightTimeout:
        log.warning("   Bouton de recherche non trouvé — vérifiez manuellement.")


def select_site(page, cfg: dict) -> bool:
    """
    Tente de sélectionner le site préféré dans les résultats.
    Retourne True si un site a été sélectionné.
    """
    site_num = cfg["reservation"].get("site_number", "")
    log.info(f"🏕️   Sélection du site {'#' + site_num if site_num else '(premier disponible)'}...")

    try:
        if site_num:
            # Chercher le site par numéro
            page.click(f"text=#{site_num}", timeout=8_000)
        else:
            # Prendre le premier résultat disponible
            page.click(".site-item:first-child, .campsite:first-child, [data-available='true']:first-child", timeout=8_000)

        human_delay(cfg)
        log.info("   Site sélectionné.")
        return True

    except PlaywrightTimeout:
        log.warning(f"   Site #{site_num} non trouvé ou non disponible.")
        # Essayer les sites de remplacement
        for fallback in cfg.get("fallback_sites", []):
            if not fallback:
                continue
            try:
                page.click(f"text=#{fallback}", timeout=5_000)
                log.info(f"   Site de remplacement #{fallback} sélectionné.")
                return True
            except PlaywrightTimeout:
                continue
        return False


def proceed_to_checkout(page, cfg: dict) -> None:
    """Clique sur 'Proceed to Checkout' ou équivalent."""
    log.info("🛒  Passage au paiement...")
    for btn_text in ["Proceed to Checkout", "Add to Cart", "Reserve", "Réserver"]:
        try:
            page.click(f"text={btn_text}", timeout=5_000)
            page.wait_for_load_state("networkidle", timeout=15_000)
            log.info(f"   Bouton '{btn_text}' cliqué.")
            return
        except PlaywrightTimeout:
            continue
    log.warning("   Bouton de paiement non trouvé — vérifiez manuellement.")


def confirm_reservation(page, cfg: dict) -> None:
    """
    SEULEMENT en mode 'live' : confirme et finalise la réservation.
    Accepte les conditions et clique sur le bouton final.
    """
    log.info("✅  Confirmation de la réservation...")

    # Accepter les conditions
    for checkbox_sel in [
        "input[type='checkbox']",
        "input[name*='agree']",
        "input[name*='terms']",
    ]:
        try:
            checkboxes = page.query_selector_all(checkbox_sel)
            for cb in checkboxes:
                if not cb.is_checked():
                    cb.check()
                    human_delay(cfg)
        except Exception:
            pass

    # Confirmer
    for btn_text in ["Confirm", "Complete Reservation", "Confirmer", "Finaliser"]:
        try:
            page.click(f"text={btn_text}", timeout=5_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
            log.info("🎉  Réservation confirmée !")
            return
        except PlaywrightTimeout:
            continue

    log.warning("   Bouton de confirmation non trouvé.")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def run(mode: str, wait: bool, config_path: str) -> None:
    cfg = load_config(config_path)
    effective_mode = mode or cfg["bot"]["mode"]

    log.info(f"🤖  Ontario Parks Bot — mode : {effective_mode.upper()}")
    log.info(f"    Parc : {cfg['reservation']['park_name']} | Site : {cfg['reservation']['site_number']}")
    log.info(f"    Arrivée : {cfg['reservation']['arrival_date']} | {cfg['reservation']['num_nights']} nuits")

    if wait:
        wait_for_opening(cfg["scheduler"]["open_time"])

    with sync_playwright() as pw:
        browser, context, page = open_browser(pw, cfg)

        try:
            if effective_mode == "explore":
                # Mode exploration : pas de connexion, vérifie juste la disponibilité
                navigate_to_search(page, cfg)
                search_campsite(page, cfg)
                log.info("🔎  Mode EXPLORE : résultats affichés dans le navigateur.")
                log.info("    Le bot ne se connecte pas. Appuyez sur Ctrl+C pour terminer.")
                input("    [Appuyez sur Entrée pour fermer le navigateur]")

            elif effective_mode == "dry_run":
                # Mode dry run : se connecte et remplit tout, mais S'ARRÊTE avant le paiement
                navigate_to_search(page, cfg)
                if not login(page, cfg):
                    log.error("Connexion échouée — arrêt.")
                    return
                search_campsite(page, cfg)
                if select_site(page, cfg):
                    proceed_to_checkout(page, cfg)
                    log.info("🛑  Mode DRY RUN : arrêt avant confirmation du paiement.")
                    log.info("    Vérifiez le navigateur — tout est prêt, rien n'a été facturé.")
                    input("    [Appuyez sur Entrée pour fermer le navigateur]")
                else:
                    log.warning("Aucun site disponible trouvé.")

            elif effective_mode == "live":
                # Mode réel : exécute tout
                navigate_to_search(page, cfg)
                if not login(page, cfg):
                    log.error("Connexion échouée — arrêt.")
                    return
                search_campsite(page, cfg)
                if select_site(page, cfg):
                    proceed_to_checkout(page, cfg)
                    confirm_reservation(page, cfg)
                    log.info("🎉  Réservation complétée ! Vérifiez votre courriel.")
                else:
                    log.warning("Aucun site disponible — réservation impossible.")

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
