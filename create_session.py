# create_session.py
import undetected_chromedriver as uc
import shutil
import os
import time

# --- CONFIGURATION ---
PROFILE_FOLDER_NAME = "chrome_profile_indeed"
# On force la version de Chrome qui est stable sur votre système.
CHROME_VERSION = 137

# --- SCRIPT ---
print("--- Script de Création de Session Chrome pour Indeed ---")

# Chemin absolu vers le dossier du profil
profile_path = os.path.abspath(PROFILE_FOLDER_NAME)

# --- ÉTAPE 1 : Nettoyer l'ancien profil et en créer un nouveau ---
if os.path.exists(profile_path):
    print(f"Suppression de l'ancien profil : {profile_path}")
    try:
        shutil.rmtree(profile_path)
        print("Ancien profil supprimé avec succès.")
    except Exception as e:
        print(f"Erreur lors de la suppression du profil : {e}")
        print("Veuillez le supprimer manuellement et relancer le script.")
        exit()

print(f"Création d'un nouveau dossier de profil à : {profile_path}")
os.makedirs(profile_path)
# ------------------------------------------------------------------

driver = None
try:
    # On utilise les options fiables que nous avons identifiées
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f'--user-data-dir={profile_path}')
    options.add_argument('--profile-directory=Default')
    options.add_argument("--window-size=1280,960")
    
    print(f"\nLancement de Chrome avec le pilote version {CHROME_VERSION}...")
    driver = uc.Chrome(options=options, use_subprocess=True, version_main=CHROME_VERSION)
    
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # --- LOGIQUE DE CONNEXION MANUELLE ---
    print("\n" + "="*60)
    print("!!! ACTION REQUISE - FENÊTRE CHROME OUVERTE !!!")
    print("="*60)
    print("1. Une fenêtre de navigateur vient de s'ouvrir.")
    print("2. Connectez-vous à Indeed (email, mot de passe, CAPTCHA, code 2FA).")
    print("3. Cochez 'Se souvenir de moi' pour que la session persiste.")
    print("\nIMPORTANT : Une fois connecté, fermez simplement la fenêtre du navigateur.")
    print("Le script attendra que vous fermiez la fenêtre pour se terminer.")
    
    LOGIN_URL = "https://secure.indeed.com/auth"
    driver.get(LOGIN_URL)
    
    # --- NOUVELLE LOGIQUE D'ATTENTE ---
    # Le script reste en vie tant que le navigateur est ouvert.
    while True:
        try:
            # On vérifie si le driver est toujours actif en accédant à une de ses propriétés
            _ = driver.title 
            time.sleep(1) # On vérifie toutes les secondes
        except Exception:
            # Si on a une erreur, c'est que la fenêtre a été fermée.
            break
    # ---------------------------------
    
    print("\n[SUCCÈS] Fenêtre du navigateur fermée par l'utilisateur.")
    
except Exception as e:
    print(f"\n[ERREUR] Une erreur est survenue lors du lancement de Chrome : {e}")
finally:
    # Sécurité pour s'assurer que le processus du driver est bien terminé
    if driver:
        driver.quit()

print(f"\nLa session a été créée et sauvegardée dans le dossier '{PROFILE_FOLDER_NAME}'.")
print("Vos autres scripts peuvent maintenant l'utiliser.")