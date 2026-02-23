"""
mailer.py — Envoi du digest par courriel via Resend (resend.com).

Resend est un service d'envoi de courriels gratuit (100/jour sur le plan gratuit).
Aucune configuration Gmail complexe n'est requise — juste une clé API.

Variables d'environnement requises :
  RESEND_API_KEY   — clé API Resend (re_...)
  SENDER_EMAIL     — adresse expéditrice vérifiée sur Resend
                     (sur le plan gratuit : utilisez onboarding@resend.dev)
  RECIPIENT_EMAIL  — adresse de destination
"""

import os
import resend
from datetime import datetime


def markdown_to_html(texte: str) -> str:
    """Conversion minimale de Markdown → HTML sans dépendance externe."""
    lignes = texte.split("\n")
    html_lignes = []
    in_list = False

    for ligne in lignes:
        if ligne.startswith("## "):
            if in_list:
                html_lignes.append("</ul>")
                in_list = False
            contenu = ligne[3:].strip()
            html_lignes.append(
                f'<h2 style="color:#1a3a5c;border-bottom:2px solid #c8102e;'
                f'padding-bottom:6px;margin-top:30px;">{contenu}</h2>'
            )
        elif ligne.startswith("# "):
            contenu = ligne[2:].strip()
            html_lignes.append(f'<h1 style="color:#1a3a5c;">{contenu}</h1>')
        elif ligne.startswith("- ") or ligne.startswith("* "):
            if not in_list:
                html_lignes.append("<ul>")
                in_list = True
            html_lignes.append(f"<li>{ligne[2:].strip()}</li>")
        elif ligne.startswith("**") and ligne.endswith("**") and len(ligne) > 4:
            if in_list:
                html_lignes.append("</ul>")
                in_list = False
            contenu = ligne[2:-2]
            html_lignes.append(f"<p><strong>{contenu}</strong></p>")
        elif ligne.strip().startswith("*") and ligne.strip().endswith("*") and len(ligne.strip()) > 2:
            if in_list:
                html_lignes.append("</ul>")
                in_list = False
            contenu = ligne.strip()[1:-1]
            html_lignes.append(
                f'<p style="color:#888;font-style:italic;font-size:13px;">{contenu}</p>'
            )
        elif ligne.strip() == "---":
            if in_list:
                html_lignes.append("</ul>")
                in_list = False
            html_lignes.append("<hr>")
        elif ligne.strip() == "":
            if in_list:
                html_lignes.append("</ul>")
                in_list = False
            html_lignes.append("")
        else:
            processed = ligne.strip()
            while "**" in processed:
                start = processed.find("**")
                end = processed.find("**", start + 2)
                if end == -1:
                    break
                processed = (
                    processed[:start]
                    + "<strong>"
                    + processed[start + 2:end]
                    + "</strong>"
                    + processed[end + 2:]
                )
            if processed:
                if in_list:
                    html_lignes.append("</ul>")
                    in_list = False
                html_lignes.append(f"<p>{processed}</p>")

    if in_list:
        html_lignes.append("</ul>")

    return "\n".join(html_lignes)


def construire_html(digest_texte: str, date_str: str) -> str:
    corps = markdown_to_html(digest_texte)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Digest politique ontarien — {date_str}</title>
</head>
<body style="font-family: Georgia, 'Times New Roman', serif; max-width: 680px; margin: 0 auto;
             padding: 24px; color: #2c2c2c; background: #ffffff; line-height: 1.7;">

  <div style="background: #1a3a5c; color: white; padding: 20px 24px; border-radius: 6px 6px 0 0;">
    <h1 style="margin: 0; font-size: 22px;">🏛️ Digest politique ontarien</h1>
    <p style="margin: 6px 0 0 0; opacity: 0.85; font-size: 14px;">{date_str}</p>
  </div>

  <div style="border: 1px solid #ddd; border-top: none; padding: 24px; border-radius: 0 0 6px 6px;">
    {corps}
  </div>

  <div style="margin-top: 24px; font-size: 12px; color: #999; border-top: 1px solid #eee; padding-top: 12px;">
    <p>
      Ce digest a été généré automatiquement à partir de sources officielles :<br>
      Hansard OLA · news.ontario.ca · Gazette de l'Ontario ·
      Registre des lobbyistes · Registre de la réglementation · Décrets du Conseil
    </p>
    <p>Pipeline propulsé par l'API Claude (Anthropic) · <a href="https://www.anthropic.com" style="color:#1a3a5c;">anthropic.com</a></p>
  </div>
</body>
</html>"""


def send_email(digest_texte: str) -> None:
    """Envoie le digest via l'API Resend (resend.com)."""
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    expediteur = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip()
    destinataire = os.environ.get("RECIPIENT_EMAIL", "").strip()

    if not api_key:
        raise EnvironmentError("Variable RESEND_API_KEY manquante.")
    if not destinataire:
        raise EnvironmentError("Variable RECIPIENT_EMAIL manquante.")

    resend.api_key = api_key

    date_str = datetime.now().strftime("%A %d %B %Y")
    sujet = f"🏛️ Digest politique ontarien — {date_str}"
    html = construire_html(digest_texte, date_str)

    print(f"📧 Envoi du digest à {destinataire} via Resend...")
    result = resend.Emails.send({
        "from": f"Digest Ontario <{expediteur}>",
        "to": [destinataire],
        "subject": sujet,
        "html": html,
        "text": digest_texte,
    })
    print(f"✅ Courriel envoyé avec succès. ID : {result.get('id', 'n/a')}")
