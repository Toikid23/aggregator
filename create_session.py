# create_session.py
import undetected_chromedriver as uc
import shutil
import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
PROFILE_FOLDER_NAME = "chrome_profile_indeed"
# On force la version de Chrome qui est stable sur votre système.
CHROME_VERSION = 137

# --- SCRIPT ---
print("--- Script de Création de Session Chrome (Version Fiable) ---")

profile_path = os.path.abspath(PROFILE_FOLDER_NAME)

# Étape 1 : Nettoyer l'ancien profil pour repartir de zéro
if os.path.exists(profile_path):
    print(f"Suppression de l'ancien profil : {profile_path}")
    shutil.rmtree(profile_path)
    print("Ancien profil supprimé.")

print(f"Création d'un nouveau dossier de profil à : {profile_path}")
os.makedirs(profile_path)

driver = None
try:
    # --- On utilise EXACTEMENT les mêmes options que dans le scraper qui fonctionnait ---
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f'--user-data-dir={profile_path}')
    options.add_argument('--profile-directory=Default')
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized") # Ouvre la fenêtre en grand
    
    print(f"\nLancement de Chrome avec le pilote version {CHROME_VERSION}...")
    driver = uc.Chrome(options=options, use_subprocess=True, version_main=CHROME_VERSION)
    
    # On ajoute cette ligne qui peut aider à masquer l'automatisation
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # --- LOGIQUE DE CONNEXION MANUELLE ASSISTÉE ---
    print("\n" + "="*60)
    print("!!! ACTION REQUISE - FENÊTRE CHROME OUVERTE !!!")
    print("="*60)
    print("1. La fenêtre du navigateur est ouverte. Allez sur la page de connexion Indeed.")
    print("2. Connectez-vous : entrez email, mot de passe.")
    print("3. PASSEZ la vérification 'Verify you are human'. Elle devrait fonctionner maintenant.")
    print("4. Entrez le code de vérification reçu par e-mail.")
    print("5. Assurez-vous d'être bien connecté et sur la page d'accueil d'Indeed.")
    print("\nLe script est en pause. Appuyez sur [ENTRÉE] dans ce terminal UNIQUEMENT QUAND vous aurez terminé.")

    LOGIN_URL = "https://secure.indeed.com/auth"
    driver.get(LOGIN_URL)
    
    # Le script se met en pause et vous laisse faire.
    input()
    
    print("[INFO] Reprise du script. Vérification de la connexion...")
    # On vérifie que la connexion a bien été établie en cherchant l'icône de profil.
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'button[aria-label="Navigation du profil"]'))
    )
    print("[SUCCÈS] Connexion réussie et vérifiée !")
    
except Exception as e:
    print(f"\n[ERREUR] Une erreur est survenue : {e}")
finally:
    if driver:
        print("Fermeture du navigateur. La session est sauvegardée.")
        driver.quit()

print(f"\nLe profil a été créé/mis à jour dans le dossier '{PROFILE_FOLDER_NAME}'.")
print("Vos autres scripts peuvent maintenant l'utiliser.")