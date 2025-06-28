#!/bin/bash

# Se déplace dans le répertoire où se trouve le script
cd "$(dirname "$0")"

echo "--- Lancement de l'application Job Aggregator ---"

# Active l'environnement virtuel
echo "Activation de l'environnement virtuel..."
source venv/bin/activate

# Lance le serveur Flask
echo "Démarrage du serveur Flask sur http://127.0.0.1:5000"
echo "Faites CTRL+C dans ce terminal pour arrêter le serveur."
python3 app.py

# Cette partie ne sera atteinte qu'après avoir fait CTRL+C
deactivate
echo "--- Application arrêtée ---"