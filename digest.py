"""
digest.py — Génération du digest quotidien avec l'API Claude.
"""

import anthropic
from datetime import datetime


SYSTEM_PROMPT = """Tu es un analyste politique senior spécialisé dans la politique provinciale ontarienne.
Tu travailles pour un service de veille destiné à des journalistes, des décideurs et des citoyens engagés.
Ton style est précis, factuel, en français québécois/canadien. Tu cites des noms, des ministères,
des numéros de projets de loi quand c'est disponible. Tu ne spécules jamais — tu te bases
strictement sur les faits présents dans les sources fournies."""


def generate_digest(sources: dict) -> str:
    client = anthropic.Anthropic()

    today = datetime.now().strftime("%A %d %B %Y")

    bloc_sources = ""
    for nom, contenu in sources.items():
        separateur = "=" * 60
        bloc_sources += f"\n\n{separateur}\nSOURCE : {nom}\n{separateur}\n{contenu}"

    user_prompt = f"""Voici les contenus bruts récupérés ce matin ({today}) depuis les sources officielles
de la politique provinciale ontarienne et des autres provinces canadiennes :
{bloc_sources}

---

Génère le digest quotidien structuré en EXACTEMENT 6 sections avec ce format :

## 🗣️ Ce qui s'est dit
[Débats parlementaires, déclarations d'élus, prises de position. Cite des noms et des partis.]

## ✅ Ce qui s'est passé
[Faits accomplis : décrets adoptés, lois promulguées, annonces officielles, nominations gouvernementales.]

## 🔍 Ce qui se trame
[Inscriptions au registre des lobbyistes, consultations réglementaires ouvertes, projets en préparation.]

## ⚡ Ce qui fait réagir
[Sujets controversés, débats vifs, enjeux qui divisent selon les sources disponibles.]

## 📅 Ce qui s'en vient
[Consultations à venir, échéances, projets annoncés pour les prochains jours ou semaines.]

## 🍁 Ontario ailleurs au Canada
Pour chaque référence à l'Ontario trouvée dans les sources officielles des autres provinces
et territoires, présente un paragraphe structuré ainsi :

**[Province]** — [Source exacte] : [Résumé de 2-3 phrases.] **Potentiel journalistique : [faible / moyen / élevé]** — [Justification en une phrase.]

Si aucune référence n'a été détectée, indique-le brièvement.

---

RÈGLES STRICTES :
- Chaque section doit avoir au moins 2-3 phrases substantielles.
- Si une section manque de matière, explique pourquoi (ex : « L'Assemblée ne siégeait pas »).
- Sois factuel. Ne fabrique aucune information absente des sources.
- Utilise le français canadien (ex : « courriel », « gouvernement », « première ministre »).
- Termine le digest par : *Digest généré automatiquement le {today} à partir de sources officielles.*"""

    print("🤖 Génération du digest avec Claude (claude-opus-4-6)...")

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        final = stream.get_final_message()

    texte = ""
    for bloc in final.content:
        if bloc.type == "text":
            texte += bloc.text

    if not texte.strip():
        return "Erreur : Claude n'a pas pu générer de digest. Vérifiez votre clé API."

    print("✅ Digest généré avec succès.")
    return texte
