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

    is_saved = db.Column(db.Boolean, default=False, nullable=False)
    is_applied = db.Column(db.Boolean, default=False, nullable=False)
    is_hidden = db.Column(db.Boolean, default=False, nullable=False)

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

# Dans app.py

@app.route('/')
def index():
    sources_filter = request.args.getlist('source')
    search_query = request.args.get('q', '').strip() # On récupère et on nettoie
    
    # On ne montre que les offres "neuves"
    query = Job.query.filter_by(
        is_hidden=False, 
        is_saved=False, 
        is_applied=False
    )
    
    if sources_filter: 
        query = query.filter(Job.source.in_(sources_filter))
    
    # --- NOUVELLE LOGIQUE DE RECHERCHE MULTI-MOTS-CLÉS ---
    if search_query:
        # 1. On sépare les mots-clés. On peut utiliser l'espace comme séparateur.
        #    On filtre les mots vides au cas où l'utilisateur mettrait plusieurs espaces.
        keywords = [keyword for keyword in search_query.split(' ') if keyword]
        
        # 2. On crée une liste de conditions de filtre (une pour chaque mot-clé)
        search_conditions = []
        for keyword in keywords:
            search_term = f"%{keyword}%"
            # Chaque condition est un "OU" entre les colonnes title, company, et tags
            condition = or_(
                Job.title.ilike(search_term),
                Job.company.ilike(search_term),
                Job.tags.ilike(search_term)
            )
            search_conditions.append(condition)
        
        # 3. On applique toutes ces conditions avec un "OU" global.
        #    L'offre doit correspondre à au moins une des recherches de mots-clés.
        if search_conditions:
            query = query.filter(or_(*search_conditions))
    # ----------------------------------------------------
    
    jobs = query.order_by(nullslast(desc(Job.published_at)), desc(Job.id)).all()
    all_sources_tuples = db.session.query(Job.source).distinct().all()
    all_sources = sorted([s[0] for s in all_sources_tuples])
    
    # On passe search_query au template pour qu'il reste dans la barre de recherche
    return render_template('index.html', jobs=jobs, all_sources=all_sources, selected_sources=sources_filter, search_query=search_query)




@app.route('/job/<int:job_id>/details')
def get_job_details(job_id):
    job = db.session.get(Job, job_id)
    if not job: 
        return jsonify({'error': 'Job not found'}), 404
    
    # --- NOUVELLE LOGIQUE : TROUVER LES OFFRES SIMILAIRES ---
    similar_jobs_data = []
    if job.company != 'N/A':
        similar_jobs_query = Job.query.filter(
            Job.company == job.company,
            Job.id != job.id,
            Job.is_hidden == False,
            Job.is_applied == False
        ).order_by(nullslast(desc(Job.published_at))).limit(5)
        
        similar_jobs = similar_jobs_query.all()
        similar_jobs_data = [{
            'id': s_job.id,
            'title': s_job.title,
            'location': s_job.location,
            'link': s_job.link
        } for s_job in similar_jobs]
    # --------------------------------------------------------

    # On vérifie si la description est déjà en cache
    MIN_FULL_DESCRIPTION_LENGTH = 500
    if job.description and len(job.description) > MIN_FULL_DESCRIPTION_LENGTH:
        print(f"API: Description pour ID {job.id} trouvée en cache.")
        return jsonify({
            'description': job.description,
            'similar_jobs': similar_jobs_data
        })
    
    source = job.source
    
    # --- CORRECTION : DÉFINITION DE SELECTORS AVANT UTILISATION ---
    SELECTORS = {
        'Indeed': "#jobDescriptionText",
        'Glassdoor': "div[class*='JobDetails_jobDescription']",
        'Crypto Careers': 'div.job-body',
        'Crypto Jobs List': "div[class*='JobView_description']",
        'Welcome to the Jungle': "div[data-testid='job-section-description']",
        'Web3.career': 'div.text-dark-grey-text',
        'Cryptocurrency Jobs': 'div.prose',
        'Remote3': 'div[class^="RemoteJobs_jobDescription"]',
        'LaborX': 'section.section-description',
        'Hellowork': 'div[class*="lg:tw-col-span-8"] div.tw-flex.tw-flex-col',
        'OnchainJobs': 'div.job_description'
    }
    
    wait_selector = SELECTORS.get(source)
    # --------------------------------------------------------------
    
    if not wait_selector:
        # On renvoie la description vide mais aussi les offres similaires trouvées
        return jsonify({
            'description': '<p>Scraper non défini pour cette source.</p>',
            'similar_jobs': similar_jobs_data
        })

    driver = None
    description = "<p>Détails non trouvés.</p>"
    try:
        print(f"API: Lancement scraper de détails pour '{source}' (offre {job_id})...")

        PROTECTED_SITES = ['Indeed', 'Glassdoor', 'Crypto Careers']
        if source in PROTECTED_SITES:
            # ... (la logique de configuration du driver reste la même)
            options = uc.ChromeOptions()
            if source in ['Indeed', 'Glassdoor']:
                profile_folder = "chrome_profile_indeed" if source == 'Indeed' else "chrome_profile_glassdoor"
                options.add_argument(f'--user-data-dir={os.path.abspath(profile_folder)}')
                options.add_argument('--profile-directory=Default')
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1024,768")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            driver = uc.Chrome(options=options, use_subprocess=True, version_main=137)
        else:
            std_options = Options()
            std_options.add_argument("--headless")
            std_options.add_argument("--no-sandbox")
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=std_options)
        
        driver.get(job.link)
        
        # --- LOGIQUE D'ATTENTE ADAPTÉE ---
        # Par défaut, on attend la visibilité
        wait_condition = EC.visibility_of_element_located((By.CSS_SELECTOR, wait_selector))
        
        # Pour les sites où l'élément peut être masqué, on attend juste sa présence
        if source in ['Crypto Careers', 'Glassdoor']:
            print(f"API ({source}): Utilisation de la condition d'attente 'presence_of_element_located'.")
            wait_condition = EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
        
        print(f"API: Attente de l'élément '{wait_selector}'...")
        description_webelement = WebDriverWait(driver, 15).until(wait_condition)
        
        if description_webelement:
            description_html = description_webelement.get_attribute('outerHTML')
            soup_for_cleaning = BeautifulSoup(description_html, 'html.parser')
            main_tag = soup_for_cleaning.find()
            if main_tag:
                for tag in main_tag.find_all(True):
                    if 'class' in tag.attrs: del tag.attrs['class']
                    if 'style' in tag.attrs: del tag.attrs['style']
                description = str(main_tag)
            else:
                description = description_html
            
            job.description = description
            db.session.commit()
            print(f"API: Description pour l'offre {job_id} ({source}) sauvegardée.")
        else:
            print(f"API: Élément de description introuvable.")
        
    except Exception as e:
        print(f"API: Erreur scraping détails pour offre {job_id} ({source}): {e}")
    finally:
        if driver:
            driver.quit()
    
    return jsonify({
        'description': description,
        'similar_jobs': similar_jobs_data
    })


# Dans app.py

@app.route('/job/<int:job_id>/toggle_save', methods=['POST'])
def toggle_save_job(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404
    
    # On stocke l'état ACTUEL avant de le changer
    was_saved = job.is_saved
    
    # On inverse la valeur
    job.is_saved = not job.is_saved
    
    # Si on dés-enregistre une offre, elle ne peut plus être considérée comme postulée
    if not job.is_saved:
        job.is_applied = False
        
    db.session.commit()
    
    # On retourne le nouvel état, et une information sur ce qui s'est passé
    return jsonify({
        'success': True, 
        'is_saved': job.is_saved,
        'is_applied': job.is_applied,
        'is_saved_toggled_off': was_saved and not job.is_saved # ex: True and not False -> True
    })

@app.route('/job/<int:job_id>/toggle_apply', methods=['POST'])
def toggle_apply_job(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404
    
    job.is_applied = not job.is_applied
    
    # Si on marque une offre comme "postulée", elle doit aussi être "enregistrée"
    if job.is_applied:
        job.is_saved = True
        
    db.session.commit()
    return jsonify({
        'success': True,
        'is_saved': job.is_saved,
        'is_applied': job.is_applied,
        'is_applied_toggled': True
    })


# Dans app.py

# --- NOUVELLE ROUTE API POUR IGNORER ---
@app.route('/job/<int:job_id>/toggle_hide', methods=['POST'])
def toggle_hide_job(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404
    
    job.is_hidden = not job.is_hidden
    db.session.commit()
    return jsonify({
        'success': True, 
        'is_hidden': job.is_hidden,
        'is_hidden_toggled': True # On signale que le statut "ignoré" a changé
    })


# --- NOUVELLE PAGE POUR LES OFFRES IGNORÉES ---
@app.route('/hidden')
def hidden_jobs():
    jobs = Job.query.filter_by(is_hidden=True).order_by(desc(Job.id)).all()
    return render_template('index.html', jobs=jobs, page_title="Offres Ignorées")



# --- MODIFIER LA ROUTE DES OFFRES ENREGISTRÉES ---
@app.route('/saved')
def saved_jobs():
    # On affiche les offres enregistrées QUI NE SONT PAS POSTULÉES et QUI NE SONT PAS IGNORÉES
    jobs = Job.query.filter_by(is_saved=True, is_applied=False, is_hidden=False).order_by(nullslast(desc(Job.published_at)), desc(Job.id)).all()
    return render_template('index.html', jobs=jobs, page_title="Offres Enregistrées")


# --- MODIFIER LA ROUTE DES OFFRES POSTULÉES ---
@app.route('/applied')
def applied_jobs():
    # On affiche les offres postulées QUI NE SONT PAS IGNORÉES
    jobs = Job.query.filter_by(is_applied=True, is_hidden=False).order_by(nullslast(desc(Job.published_at)), desc(Job.id)).all()
    return render_template('index.html', jobs=jobs, page_title="Offres Postulées")

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