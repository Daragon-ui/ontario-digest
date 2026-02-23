"""
mailer.py — Envoi du digest par courriel via Resend (resend.com).
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime


def markdown_to_html(texte: str) -> str:
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
  <title>Digest politique ontarien — {date_str}</title>
</head>
<body style="font-family: Georgia, serif; max-width: 680px; margin: 0 auto;
             padding: 24px; color: #2c2c2c; background: #ffffff; line-height: 1.7;">

  <div style="background: #1a3a5c; color: white; padding: 20px 24px; border-radius: 6px 6px 0 0;">
    <h1 style="margin: 0; font-size: 22px;">🏛️ Digest politique ontarien</h1>
    <p style="margin: 6px 0 0 0; opacity: 0.85; font-size: 14px;">{date_str}</p>
  </div>

  <div style="border: 1px solid #ddd; border-top: none; padding: 24px; border-radius: 0 0 6px 6px;">
    {corps}
  </div>

  <div style="margin-top: 24px; font-size: 12px; color: #999; border-top: 1px solid #eee; padding-top: 12px;">
    <p>Pipeline propulsé par l'API Claude (Anthropic)</p>
  </div>
</body>
</html>"""


def send_email(digest_texte: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    expediteur = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip()
    destinataire = os.environ.get("RECIPIENT_EMAIL", "").strip()

    if not api_key:
        raise EnvironmentError("Variable RESEND_API_KEY manquante.")
    if not destinataire:
        raise EnvironmentError("Variable RECIPIENT_EMAIL manquante.")

    date_str = datetime.now().strftime("%A %d %B %Y")
    sujet = f"🏛️ Digest politique ontarien — {date_str}"
    html = construire_html(digest_texte, date_str)

    payload = json.dumps({
        "from": f"Digest Ontario <{expediteur}>",
        "to": [destinataire],
        "subject": sujet,
        "html": html,
        "text": digest_texte,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    print(f"📧 Envoi du digest à {destinataire} via Resend...")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"✅ Courriel envoyé. ID : {result.get('id', 'n/a')}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Erreur Resend ({e.code}): {body}") from e
