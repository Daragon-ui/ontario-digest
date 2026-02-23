"""
main.py — Point d'entrée du pipeline de veille politique ontarienne.
"""

import os
import sys
from datetime import datetime

from fetchers import fetch_all
from interprovincial import fetch_interprovincial
from digest import generate_digest
from mailer import send_email


def verifier_variables():
    dry_run = os.environ.get("DRY_RUN", "").strip() == "1"
    requises = ["ANTHROPIC_API_KEY"]
    if not dry_run:
        requises += ["RESEND_API_KEY", "RECIPIENT_EMAIL"]

    manquantes = [v for v in requises if not os.environ.get(v)]
    if manquantes:
        print(f"❌ Variables d'environnement manquantes : {', '.join(manquantes)}")
        sys.exit(1)


def main():
    print(f"\n{'='*60}")
    print(f"  DIGEST POLITIQUE ONTARIEN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    dry_run = os.environ.get("DRY_RUN", "").strip() == "1"
    if dry_run:
        print("🔧 Mode DRY_RUN activé — aucun courriel ne sera envoyé.\n")

    verifier_variables()

    sources = fetch_all()

    sources_interprov = fetch_interprovincial()
    sources["Ontario ailleurs au Canada (sources interprovinciales)"] = sources_interprov

    digest = generate_digest(sources)

    print(f"\n{'='*60}")
    print("DIGEST GÉNÉRÉ :")
    print(f"{'='*60}")
    print(digest)
    print(f"{'='*60}\n")

    if dry_run:
        print("🔧 DRY_RUN : courriel non envoyé.")
    else:
        send_email(digest)

    print("\n✅ Pipeline terminé avec succès.")


if __name__ == "__main__":
    main()
