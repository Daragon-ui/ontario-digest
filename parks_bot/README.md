# Ontario Parks Reservation Bot

Bot d'automatisation pour faire des réservations sur le site [Ontario Parks](https://reservations.ontarioparks.ca) au moment précis où la fenêtre de réservation s'ouvre.

## Installation

```bash
pip install playwright pyyaml
playwright install chromium
```

## Configuration

Éditez `parks_bot/config.yaml` :

```yaml
account:
  email: "votre@courriel.com"
  password: "votre_mot_de_passe"

reservation:
  park_name: "Balsam Lake"
  site_number: "153"
  arrival_date: "2026-08-20"
  num_nights: 3
  party_size: 3
  equipment_type: "tent"
```

**⚠️ Ne partagez jamais `config.yaml` — il contient vos identifiants.**

## Utilisation

### 1. Mode exploration (sans connexion — 100% sécuritaire)
```bash
python parks_bot/bot.py --mode explore
```
Navigue sur le site comme un humain, affiche les disponibilités, ne se connecte pas.

### 2. Mode dry run (connexion + remplissage — s'arrête avant paiement)
```bash
python parks_bot/bot.py --mode dry_run
```
Se connecte, remplit tout le formulaire, **s'arrête avant de confirmer**. Idéal pour tester.

### 3. Mode réel (la veille au soir pour une ouverture à 7h00 AM)
```bash
python parks_bot/bot.py --mode live --wait
```
Se met en attente et démarre automatiquement à 7h00 AM heure de l'Est.

## Quand lancer le bot ?

Ontario Parks ouvre les réservations **5 mois à l'avance, à 7h00 AM heure de l'Est**.

Pour une arrivée le **20 août 2026**, lancer le script le soir du **19 mars 2026** :
```bash
python parks_bot/bot.py --mode live --wait
```

## Avertissement

L'automatisation est techniquement contraire aux CGU d'Ontario Parks. Ce bot est conçu pour un usage personnel (une seule réservation pour vous-même). Utilisez à votre discrétion.
