# app.py (version avec API pour Crypto Jobs List SEULEMENT)

import os
import pytz
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options 
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, nullslast, or_

# Imports nécessaires pour le scraping à la demande
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# --- Configuration et Modèles ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'jobs.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    link = db.Column(db.String(300), unique=True, nullable=False)
    source = db.Column(db.String(50), nullable=False)
    date_added = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    published_at = db.Column(db.DateTime, nullable=True)
    salary = db.Column(db.String(100), nullable=True)
    tags = db.Column(db.Text, nullable=True)
    logo_url = db.Column(db.String(300), nullable=True)
    description = db.Column(db.Text, nullable=True) # On a besoin de la colonne description

# --- Filtres de template (inchangés) ---
@app.template_filter('time_ago')
def time_ago(dt):
    if dt is None: return ""
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    else: dt = dt.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = diff.total_seconds()
    days = diff.days
    if days > 1: return f"il y a {days} jours"
    if days == 1: return "hier"
    if seconds < 60: return "à l'instant"
    if seconds < 3600: return f"il y a {int(seconds / 60)} minutes"
    if seconds < 86400: return f"il y a {int(seconds / 3600)} heures"

@app.template_filter('to_paris_time')
def to_paris_time(utc_dt):
    if utc_dt is None: return None
    paris_tz = pytz.timezone('Europe/Paris')
    if utc_dt.tzinfo is None: utc_dt = utc_dt.replace(tzinfo=pytz.utc)
    return utc_dt.astimezone(paris_tz)

# --- Route principale (inchangée) ---
@app.route('/')
def index():
    sources_filter = request.args.getlist('source')
    search_query = request.args.get('q', None)
    query = Job.query
    if sources_filter: query = query.filter(Job.source.in_(sources_filter))
    if search_query:
        search_term = f"%{search_query.strip()}%"
        query = query.filter(or_(Job.title.ilike(search_term), Job.company.ilike(search_term), Job.tags.ilike(search_term)))
    jobs = query.order_by(nullslast(desc(Job.published_at)), desc(Job.id)).all()
    all_sources_tuples = db.session.query(Job.source).distinct().all()
    all_sources = sorted([s[0] for s in all_sources_tuples])
    return render_template('index.html', jobs=jobs, all_sources=all_sources, selected_sources=sources_filter, search_query=search_query)

# app.py

@app.route('/job/<int:job_id>/details')
def get_job_details(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    MIN_FULL_DESCRIPTION_LENGTH = 500
    if job.description and len(job.description) > MIN_FULL_DESCRIPTION_LENGTH:
        return jsonify({'description': job.description})
    
    source = job.source
    wait_selector = None
    description_selector = None # Sélecteur pour l'extraction

    if source == 'Indeed':
        wait_selector = '#jobDescriptionText, #mosaic-vjJobDetails'
        description_selector = wait_selector
    elif source == 'Glassdoor':
        # On attend l'en-tête de la description
        wait_selector = "header[data-test='job-details-header']"
        # On extrait le conteneur de la description
        description_selector = "div[class*='JobDetails_jobDescription']"
    # ... autres sites ...
    
    if not wait_selector:
        return jsonify({'description': '<p>Scraper non défini pour cette source.</p>'})

    driver = None
    description = "<p>Détails non trouvés lors du scraping.</p>"
    try:
        if source in ['Indeed', 'Glassdoor']:
            profile_folder = "chrome_profile_indeed" if source == 'Indeed' else "chrome_profile_glassdoor"
            options = uc.ChromeOptions()
            profile_path = os.path.abspath(profile_folder)
            options.add_argument(f'--user-data-dir={profile_path}')
            options.add_argument('--profile-directory=Default')
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=800,600")
            driver = uc.Chrome(options=options, use_subprocess=True, version_main=137)
        else:
            std_options = Options()
            std_options.add_argument("--headless")
            std_options.add_argument("--no-sandbox")
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=std_options)
        
        driver.get(job.link)
        
        print(f"API: Attente de la visibilité de '{wait_selector}'...")
        WebDriverWait(driver, 1).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, wait_selector))
        )
        print("API: Élément d'attente trouvé !")

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        description_element = soup.select_one(description_selector)

        if description_element:
            for tag in description_element.find_all(True):
                if 'class' in tag.attrs: del tag.attrs['class']
                if 'style' in tag.attrs: del tag.attrs['style']
            description = str(description_element)
            job.description = description
            db.session.commit()
            print(f"API: Description pour l'offre {job_id} ({source}) sauvegardée.")
        else:
            print(f"API: Élément de description ('{description_selector}') introuvable après l'attente.")
        
    except Exception as e:
        print(f"API: Erreur scraping détails pour l'offre {job_id} ({source}): {e}")
        description = f"<p>Une erreur est survenue.</p>"
    finally:
        if driver:
            driver.quit()
    
    return jsonify({'description': description})

# --- Lancement de l'application ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)



    # if source == 'Crypto Jobs List':
    #     wait_selector = "div[class*='JobView_description']"
    
    # elif source == 'Welcome to the Jungle':
    #     wait_selector = "div[data-testid='job-section-description']"
    
    # elif source == 'Web3.career':
    #     wait_selector = 'div.text-dark-grey-text'

    # elif source == 'Crypto Careers':
    #     wait_selector = 'div.job-body'

    # elif source == 'Cryptocurrency Jobs':
    #     wait_selector = 'div.prose'

    # elif source == 'Remote3':
    #     wait_selector = 'div[class^="RemoteJobs_jobDescription"]'

    # # --- SÉLECTEUR CORRIGÉ POUR LABORX ---
    # elif source == 'LaborX':
    #     # On utilise le sélecteur que vous avez confirmé être le bon.
    #     wait_selector = 'section.section-description'

    # elif source == 'Hellowork':
    #     wait_selector = 'div[class*="lg:tw-col-span-8"] div.tw-flex.tw-flex-col'