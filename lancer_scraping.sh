#!/bin/bash

# --- CORRECTION ---
# Se déplace dans le répertoire où se trouve le script
# Cela garantit que tous les chemins relatifs (comme venv/bin/activate) fonctionneront
cd "$(dirname "$0")"

echo "--- Lancement du processus de Scraping ---"

# Active l'environnement virtuel
echo "Activation de l'environnement virtuel..."
source venv/bin/activate

# Demande de confirmation
read -p "Voulez-vous supprimer l'ancienne base de données (jobs.db) ? (o/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Oo]$ ]]
then
    echo "Suppression de jobs.db..."
    rm -f jobs.db
fi

# Lance le scraper
echo "Démarrage des scrapers..."
python3 scraper.py

# Désactive l'environnement virtuel
deactivate
echo "--- Scraping terminé ---"
# Ajout d'une pause pour que la fenêtre ne se ferme pas instantanément
read -p "Appuyez sur [ENTRÉE] pour fermer..."