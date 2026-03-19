"""
digest.py — Génération du digest quotidien avec l'API Claude.
"""

import anthropic
from datetime import datetime


SYSTEM_PROMPT = """Tu es un analyste politique senior spécialisé dans la politique provinciale ontarienne.
Tu travailles pour un service de veille destiné à des journalistes, des décideurs et des citoyens engagés.
Ton style est précis, factuel, en français québécois/canadien. Tu cites des noms, des ministères,
des numéros de projets de loi quand c'est disponible. Tu ne spécules jamais — tu te bases
strictement sur les faits présents dans les sources fournies.

PÉRIMÈTRE GÉOGRAPHIQUE STRICT : Les sections 1 à 5 du digest couvrent exclusivement la politique
ontarienne. N'y mentionne jamais d'événements survenus dans d'autres provinces ou territoires
canadiens, sauf s'ils affectent directement l'Ontario ou font l'objet d'une action du gouvernement
ontarien. La section 6 (Ontario ailleurs au Canada) est la seule destinée au contenu interprovincial."""


def generate_digest(sources: dict) -> str:
    """
    Prend un dictionnaire {nom_source: contenu} et retourne
    le digest quotidien en 5 sections, en français.
    """
    client = anthropic.Anthropic()  # Lit ANTHROPIC_API_KEY automatiquement

    today = datetime.now().strftime("%A %d %B %Y")

    # Assembler le contenu de toutes les sources
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
[Faits accomplis : décrets adoptés, lois promulguées, annonces officielles, nominations gouvernementales.
Pour chaque décret du Conseil contenant une ligne « PERSONNES/ENTITÉS EN GRAS DANS LE DÉCRET »,
nomme explicitement la personne ou l'entité concernée. Évalue ensuite le potentiel journalistique
de cette nomination : qui est cette personne (si identifiable), quel organisme, quel ministère,
et pourquoi cela pourrait intéresser un journaliste. Ne passe sous silence aucun nom fourni.]

## 🔍 Ce qui se trame
[Inscriptions au registre des lobbyistes, consultations réglementaires ouvertes, projets en préparation.]

## ⚡ Ce qui fait réagir
[Sujets controversés, débats vifs, enjeux qui divisent selon les sources disponibles.]

## 📅 Ce qui s'en vient
[Consultations à venir, échéances, projets annoncés pour les prochains jours ou semaines.]

## 🍁 Ontario ailleurs au Canada
N'inclus ici QUE les références où l'Ontario (ou un de ses acteurs) est nommé ou directement
concerné dans une source officielle d'une autre province ou d'un territoire. Ignore tout contenu
qui ne mentionne pas explicitement l'Ontario ou qui concerne exclusivement une autre province.

Pour chaque référence retenue, présente un paragraphe structuré ainsi :

**[Province]** — [Source exacte] : [Résumé de 2-3 phrases expliquant le contexte et ce qui
est dit sur l'Ontario.] **Potentiel journalistique : [faible / moyen / élevé]** — [Justification
en une phrase : pourquoi ce passage pourrait intéresser un journaliste ou signaler un enjeu
interprovincial, un conflit latent, un accord en négociation, ou une décision qui touche
l'Ontario à l'insu du public ontarien.]

Si aucune référence pertinente n'a été détectée, écris uniquement : « Aucune référence à l'Ontario n'a été détectée dans les sources interprovinciales aujourd'hui. » Ne mentionne pas les provinces consultées ni les sujets qui en ont été exclus.

---

RÈGLES STRICTES :
- Chaque section doit avoir au moins 2-3 phrases substantielles.
- Si une section manque de matière, explique pourquoi (ex : « L'Assemblée ne siégeait pas »).
- Sois factuel. Ne fabrique aucune information absente des sources.
- Dans la section « Ontario ailleurs au Canada », n'invente rien : utilise uniquement les
  extraits fournis. Si un extrait est ambigu, dis-le explicitement.
- Sections 1 à 5 : contenu ontarien uniquement. Tout événement survenu dans une autre province
  sans lien direct avec l'Ontario doit être ignoré ou réservé à la section 6.
- Pour les Décrets du Conseil : si la source indique « PERSONNES/ENTITÉS EN GRAS DANS LE DÉCRET »,
  nomme chaque personne dans le digest. Pour les communiqués d'Ontario Newsroom, résume chaque
  communiqué pertinent en 2 phrases maximum.
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

    # Extraire uniquement le texte (ignorer les blocs de réflexion)
    texte = ""
    for bloc in final.content:
        if bloc.type == "text":
            texte += bloc.text

    if not texte.strip():
        return "Erreur : Claude n'a pas pu générer de digest. Vérifiez votre clé API."

    print("✅ Digest généré avec succès.")
    return texte
