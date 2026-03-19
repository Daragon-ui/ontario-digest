"""
main.py — Point d'entrée du pipeline de veille politique ontarienne.

Usage :
  python main.py

Variables d'environnement requises :
  ANTHROPIC_API_KEY   — clé API Anthropic (console.anthropic.com)
  GMAIL_ADDRESS       — adresse Gmail expéditrice
  GMAIL_APP_PASSWORD  — mot de passe d'application Gmail (16 caractères)
  RECIPIENT_EMAIL     — adresse courriel destinataire

Pour tester sans envoyer de courriel :
  DRY_RUN=1 python main.py
"""

import os
import sys
from datetime import datetime

from fetchers import fetch_all
from interprovincial import fetch_interprovincial
from digest import generate_digest
from mailer import send_email
from history import get_recent_items, record_items, extract_tracked_items


def verifier_variables():
    """Vérifie que les variables d'environnement essentielles sont définies."""
    dry_run = os.environ.get("DRY_RUN", "").strip() == "1"
    requises = ["ANTHROPIC_API_KEY"]
    if not dry_run:
        requises += ["RESEND_API_KEY", "RECIPIENT_EMAIL"]

    manquantes = [v for v in requises if not os.environ.get(v)]
    if manquantes:
        print(f"❌ Variables d'environnement manquantes : {', '.join(manquantes)}")
        print("   Consultez le guide de configuration pour les définir.")
        sys.exit(1)


def main():
    print(f"\n{'='*60}")
    print(f"  DIGEST POLITIQUE ONTARIEN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    dry_run = os.environ.get("DRY_RUN", "").strip() == "1"
    if dry_run:
        print("🔧 Mode DRY_RUN activé — aucun courriel ne sera envoyé.\n")

    # 1. Vérifier la configuration
    verifier_variables()

    # 2. Récupérer les sources ontariennes
    sources = fetch_all()

    # 3. Récupérer les sources interprovinciales
    sources_interprov = fetch_interprovincial()
    sources["Ontario ailleurs au Canada (sources interprovinciales)"] = sources_interprov

    # 4. Charger l'historique des éléments déjà couverts
    seen_items = get_recent_items()
    if seen_items:
        print(f"📋 {len(seen_items)} élément(s) déjà couverts dans les 14 derniers jours — seront exclus du digest.")

    # 5. Générer le digest avec Claude
    digest = generate_digest(sources, seen_items=seen_items)

    # 5b. Sauvegarder les éléments couverts aujourd'hui dans l'historique
    nouveaux_items = extract_tracked_items(sources)
    record_items(nouveaux_items)
    if nouveaux_items:
        print(f"💾 {len(nouveaux_items)} élément(s) enregistrés dans l'historique.")

    # 6. Afficher le résultat dans la console
    print(f"\n{'='*60}")
    print("DIGEST GÉNÉRÉ :")
    print(f"{'='*60}")
    print(digest)
    print(f"{'='*60}\n")

    # 7. Envoyer par courriel (sauf en mode dry run)
    if dry_run:
        print("🔧 DRY_RUN : courriel non envoyé. Le digest est affiché ci-dessus.")
    else:
        send_email(digest)

    print("\n✅ Pipeline terminé avec succès.")


if __name__ == "__main__":
    main()
