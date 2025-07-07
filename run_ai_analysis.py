# run_ai_analysis.py

import time, json, os, sys
from app import app, db, Job
from ai_analyzer import analyze_job_offer
from sqlalchemy import not_, or_, func

# --- Outils de scraping de détail ---
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

JOBS_TO_PROCESS_LIMIT = 50

DETAIL_SELECTORS = {
    'Indeed': "#jobDescriptionText", 'Glassdoor': "div[class*='JobDetails_jobDescription']",
    'Welcome to the Jungle': "div[data-testid='job-section-description']", 'Web3.career': 'div.text-dark-grey-text',
    'Remote3': 'div[class^="RemoteJobs_jobDescription"]', 'Hellowork': 'div[class*="lg:tw-col-span-8"] div.tw-flex.tw-flex-col',
}

def get_full_description(job):
    """Scrape la description complète d'une offre en utilisant la configuration qui marche."""
    print(f"  [Scraping Détails] Tentative pour ID {job.id} ({job.source})...")
    wait_selector = DETAIL_SELECTORS.get(job.source)
    if not wait_selector: print(f"  -> Pas de sélecteur pour {job.source}."); return False
    
    driver = None
    try:
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1280,800")
        if job.source in ['Indeed', 'Glassdoor']:
            profile_folder = "chrome_profile_indeed" if job.source == 'Indeed' else "chrome_profile_glassdoor"
            profile_path = os.path.abspath(profile_folder)
            if not os.path.exists(profile_path): print(f"  [ERREUR] Profil '{profile_folder}' introuvable."); return False
            options.add_argument(f'--user-data-dir={profile_path}'); options.add_argument('--profile-directory=Default')
        
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=137)
        driver.get(job.link)
        
        desc_element = WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector)))
        description_html = desc_element.get_attribute('outerHTML')
        
        with app.app_context():
            job_to_update = db.session.get(Job, job.id)
            if job_to_update:
                job_to_update.description = description_html; db.session.commit()
                print("  ✅ Description sauvegardée.")
                return True
        return False
    except Exception as e:
        print(f"  ❌ Erreur scraping détail: {type(e).__name__} - {str(e)[:100]}...")
        return False
    finally:
        if driver: driver.quit()

def _process_and_analyze(jobs_to_process, qthread=None):
    """MOTEUR PRINCIPAL : Scrape la description si besoin, puis analyse."""
    if not jobs_to_process: print("✅ Aucune offre à traiter."); return
    print(f"🔍 {len(jobs_to_process)} offres à traiter trouvées.")
    
    for i, job in enumerate(jobs_to_process):
        if qthread and not qthread.is_running: print("\n--- [!] Arrêt demandé. ---"); break
        print(f"\n--- [ {i+1}/{len(jobs_to_process)} ] Traitement ID: {job.id} : '{job.title}' ---")
        with app.app_context():
            job_in_session = db.session.get(Job, job.id)
            if not job_in_session: continue
            
            if not job_in_session.description or len(job_in_session.description) < 100:
                if not get_full_description(job_in_session):
                    job_in_session.is_analyzed = True; job_in_session.ai_verdict = "Description indisponible"; db.session.commit()
                    print(f"  [Analyse] ⚠️ Offre ignorée, description non scrapable.")
                    continue
                db.session.refresh(job_in_session)

            analysis_result = analyze_job_offer(job_in_session)
            if analysis_result:
                job_in_session.is_analyzed = True; job_in_session.ai_score = int(analysis_result.get('score_pertinence', 0))
                job_in_session.ai_verdict = analysis_result.get('verdict_court'); job_in_session.ai_analysis_json = json.dumps(analysis_result, indent=2, ensure_ascii=False)
                print(f"  [Analyse] ✅ Résultats sauvegardés.")
            else:
                job_in_session.is_analyzed = True; job_in_session.ai_verdict = "Erreur d'analyse IA"
                print(f"  [Analyse] ⚠️ L'offre a échoué à l'analyse IA.")
            db.session.commit()
        time.sleep(1)

def _get_jobs_for_source(source_name):
    return Job.query.filter(Job.is_analyzed == False, Job.source == source_name).order_by(Job.id.desc()).limit(JOBS_TO_PROCESS_LIMIT).all()

def run_wttj_analysis(qthread=None):
    print("🚀 Démarrage du workflow pour Welcome to the Jungle.");
    with app.app_context(): _process_and_analyze(_get_jobs_for_source('Welcome to the Jungle'), qthread)
def run_remote3_analysis(qthread=None):
    print("🚀 Démarrage du workflow pour Remote3.");
    with app.app_context(): _process_and_analyze(_get_jobs_for_source('Remote3'), qthread)
def run_glassdoor_analysis(qthread=None):
    print("🚀 Démarrage du workflow pour Glassdoor.");
    with app.app_context(): _process_and_analyze(_get_jobs_for_source('Glassdoor'), qthread)
def run_indeed_analysis(qthread=None):
    print("🚀 Démarrage du workflow pour Indeed.");
    with app.app_context(): _process_and_analyze(_get_jobs_for_source('Indeed'), qthread)
def run_automatic_analysis(qthread=None):
    print("🚀 Démarrage du workflow 'Analyser TOUT (sauf Indeed)'.")
    with app.app_context():
        jobs = Job.query.filter(Job.is_analyzed == False, not_(Job.source.like('Indeed'))).order_by(Job.id.desc()).limit(JOBS_TO_PROCESS_LIMIT).all()
        _process_and_analyze(jobs, qthread)