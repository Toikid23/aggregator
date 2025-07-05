# run_ai_analysis.py

import time, json, os
from app import app, db, Job
from ai_analyzer import analyze_job_offer
from sqlalchemy import not_

# --- Outils de scraping de détail ---
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Nombre maximum d'offres à traiter par exécution
JOBS_TO_PROCESS_LIMIT = 100

# --- Dictionnaire des sélecteurs pour le scraping de détail ---
DETAIL_SELECTORS = {
    'Indeed': "#jobDescriptionText", 'Glassdoor': "div[class*='JobDetails_jobDescription']",
    'Crypto Careers': 'div.job-body', 'Crypto Jobs List': "div[class*='JobView_description']",
    'Welcome to the Jungle': "div[data-testid='job-section-description']", 'Web3.career': 'div.text-dark-grey-text',
    'Cryptocurrency Jobs': 'div.prose', 'Remote3': 'div[class^="RemoteJobs_jobDescription"]',
    'LaborX': 'section.section-description', 'Hellowork': 'div[class*="lg:tw-col-span-8"] div.tw-flex.tw-flex-col',
    'OnchainJobs': 'div.job_description'
}

def get_full_description(job):
    """Scrape la description complète d'une offre et la sauvegarde en DB."""
    print(f"  [Scraping Détails] Tentative pour l'offre ID {job.id} de '{job.source}'...")
    wait_selector = DETAIL_SELECTORS.get(job.source)
    if not wait_selector:
        print(f"  [Scraping Détails] ❌ Pas de sélecteur défini pour '{job.source}'.")
        return False

    driver = None
    try:
        # Configuration du driver (uc pour les sites protégés)
        if job.source in ['Indeed', 'Glassdoor']:
            options = uc.ChromeOptions(); profile_folder = "chrome_profile_indeed" if job.source == 'Indeed' else "chrome_profile_glassdoor"
            if not os.path.exists(os.path.abspath(profile_folder)):
                 print(f"  [Scraping Détails] ❌ Profil {profile_folder} introuvable.")
                 return False
            options.add_argument(f'--user-data-dir={os.path.abspath(profile_folder)}'); options.add_argument('--profile-directory=Default')
            options.add_argument("--headless=new"); options.add_argument("--no-sandbox")
            driver = uc.Chrome(options=options, use_subprocess=True)
        else:
            std_options = ChromeOptions(); std_options.add_argument("--headless=new"); std_options.add_argument("--no-sandbox")
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=std_options)
        
        driver.get(job.link)
        description_webelement = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector)))
        
        if description_webelement:
            description_html = description_webelement.get_attribute('outerHTML')
            with app.app_context():
                job_to_update = db.session.get(Job, job.id)
                if job_to_update:
                    job_to_update.description = description_html
                    db.session.commit()
            print(f"  [Scraping Détails] ✅ Description sauvegardée.")
            return True
        return False
    except Exception as e:
        print(f"  [Scraping Détails] ❌ Erreur : {str(e)[:150]}...") # Affiche le début de l'erreur
        return False
    finally:
        if driver: driver.quit()

def _process_and_analyze(jobs_to_process, qthread=None):
    """
    Fonction interne qui prend une liste de jobs, scrape la description si besoin, puis analyse.
    """
    if not jobs_to_process:
        print("✅ Aucune nouvelle offre à traiter pour cette sélection.")
        return

    print(f"🔍 {len(jobs_to_process)} offres à traiter trouvées.")
    
    for i, job in enumerate(jobs_to_process):
        if qthread and not qthread.is_running:
            print("\n--- [!] Arrêt de la tâche demandé par l'utilisateur. ---")
            break

        print(f"\n--- [ {i+1}/{len(jobs_to_process)} ] Traitement de l'offre ID: {job.id} : '{job.title}' ---")
        
        with app.app_context():
            # Il faut recharger l'objet job dans la session actuelle pour avoir les dernières données
            job_in_session = db.session.get(Job, job.id)
            if not job_in_session: continue

            # Étape 1 : S'assurer qu'on a une description
            if not job_in_session.description or len(job_in_session.description) < 100:
                if not get_full_description(job_in_session):
                    job_in_session.is_analyzed = True; job_in_session.ai_verdict = "Description indisponible"
                    db.session.commit()
                    print(f"  [Analyse] ⚠️ Offre ignorée car la description n'a pas pu être scrapée.")
                    continue
                # Recharger l'objet pour que la description soit disponible pour l'analyse
                db.session.refresh(job_in_session)

            # Étape 2 : Lancer l'analyse IA
            analysis_result = analyze_job_offer(job_in_session)
            
            if analysis_result:
                job_in_session.is_analyzed = True
                job_in_session.ai_score = int(analysis_result.get('score_pertinence', 0))
                job_in_session.ai_verdict = analysis_result.get('verdict_court')
                job_in_session.ai_analysis_json = json.dumps(analysis_result, indent=2, ensure_ascii=False)
                print(f"  [Analyse] ✅ Résultats sauvegardés.")
            else:
                job_in_session.is_analyzed = True; job_in_session.ai_verdict = "Erreur d'analyse IA"
                print(f"  [Analyse] ⚠️ L'offre a échoué à l'analyse IA et sera ignorée.")
            
            db.session.commit()
        time.sleep(1)

def run_automatic_analysis(qthread=None):
    """Analyse toutes les offres (sauf Indeed) en scrapant d'abord leur description si nécessaire."""
    print("🚀 Démarrage de l'analyse 'Juste à Temps' (tout sauf Indeed).")
    with app.app_context():
        jobs = Job.query.filter(
            Job.is_analyzed == False,
            not_(Job.source.like('Indeed'))
        ).order_by(Job.id.desc()).limit(JOBS_TO_PROCESS_LIMIT).all()
        _process_and_analyze(jobs, qthread)

def run_indeed_analysis(qthread=None):
    """Analyse les offres Indeed en scrapant d'abord leur description si nécessaire."""
    print("🚀 Démarrage de l'analyse 'Juste à Temps' pour Indeed.")
    with app.app_context():
        jobs = Job.query.filter(
            Job.is_analyzed == False,
            Job.source.like('Indeed')
        ).order_by(Job.id.desc()).limit(JOBS_TO_PROCESS_LIMIT).all()
        _process_and_analyze(jobs, qthread)

if __name__ == '__main__':
    print("Ce script est conçu pour être appelé par le lanceur.")