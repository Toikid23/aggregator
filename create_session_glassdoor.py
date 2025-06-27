# create_session_glassdoor.py
import undetected_chromedriver as uc
import shutil
import os
import time

# --- CONFIGURATION ---
PROFILE_FOLDER_NAME = "chrome_profile_glassdoor" # Nouveau nom de dossier !
CHROME_VERSION = 137

# --- SCRIPT ---
print("--- Script de Création de Session Chrome pour Glassdoor ---")

profile_path = os.path.abspath(PROFILE_FOLDER_NAME)

if os.path.exists(profile_path):
    print(f"Suppression de l'ancien profil : {profile_path}")
    shutil.rmtree(profile_path)

print(f"Création d'un nouveau dossier de profil à : {profile_path}")
os.makedirs(profile_path)

driver = None
try:
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f'--user-data-dir={profile_path}')
    options.add_argument('--profile-directory=Default')
    options.add_argument("--window-size=1280,960")

    print(f"\nLancement de Chrome avec le pilote version {CHROME_VERSION}...")
    driver = uc.Chrome(version_main=CHROME_VERSION, options=options)
    
    print("\n" + "="*60)
    print("!!! ACTION REQUISE - FENÊTRE CHROME OUVERTE !!!")
    print("="*60)
    print("1. Allez sur https://www.glassdoor.fr/ et connectez-vous.")
    print("2. Cochez 'Se souvenir de moi' et résolvez les CAPTCHA si nécessaire.")
    print("3. Une fois bien connecté, fermez simplement la fenêtre du navigateur.")
    print("Le script attendra que vous fermiez la fenêtre...")
    
    # On vous amène directement sur Glassdoor
    driver.get("https://www.glassdoor.fr/profile/login_input.htm")
    
    # Boucle qui maintient le script en vie tant que le navigateur est ouvert
    while True:
        try:
            _ = driver.window_handles
            time.sleep(1)
        except Exception:
            break
            
    print("\n[SUCCÈS] Fenêtre du navigateur fermée par l'utilisateur.")
    
except Exception as e:
    print(f"\n[ERREUR] Une erreur est survenue : {e}")
finally:
    if driver:
        driver.quit()

print(f"\nLa session Glassdoor a été créée dans le dossier '{PROFILE_FOLDER_NAME}'.")