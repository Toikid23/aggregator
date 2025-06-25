import time
import os
import locale
import re
import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth 
import undetected_chromedriver as uc

from app import db, Job, app

# --- FONCTION UTILITAIRE STABLE ---
def save_job_to_db(job_data):
    exists = Job.query.filter_by(link=job_data['link']).first()
    if not exists:
        try:
            new_job = Job(
                title=job_data['title'],
                company=job_data.get('company', 'N/A'),
                location=job_data.get('location', 'N/A'),
                link=job_data['link'],
                source=job_data['source'],
                published_at=job_data.get('published_at'),
                salary=job_data.get('salary'),
                tags=job_data.get('tags'),
                logo_url=job_data.get('logo_url'),

                description=job_data.get('description') 
            )
            db.session.add(new_job)
            return True
        except Exception as e:
            print(f"  [ERREUR DB] Impossible d'ajouter l'offre '{job_data.get('title')}'. Erreur : {e}")
            db.session.rollback()
            return False
    return False

# scraper.py (uniquement la fonction scrape_wttj)

def scrape_wttj():
    print("\n--- Début du scraping sur Welcome to the Jungle ---")
    NUM_PAGES_TO_SCRAPE = 3
    BASE_URL = "https://www.welcometothejungle.com/fr/jobs?aroundQuery=worldwide&sortBy=mostRecent&refinementList%5Bremote%5D%5B%5D=fulltime&page={}"
    driver = None
    new_jobs_count = 0
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

        for page_num in range(1, NUM_PAGES_TO_SCRAPE + 1):
            current_url = BASE_URL.format(page_num)
            print(f"\nWTTJ : Traitement de la page {page_num}/{NUM_PAGES_TO_SCRAPE}...")
            driver.get(current_url)

            if page_num == 1:
                try:
                    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#axeptio_btn_acceptAll"))).click()
                    print("WTTJ : Bouton des cookies accepté.")
                    time.sleep(2)
                except Exception:
                    print("WTTJ : Pas de bandeau de cookies.")

            job_cards_selector = "li[data-testid='search-results-list-item-wrapper']"
            try:
                WebDriverWait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, job_cards_selector)))
                time.sleep(2)
            except Exception:
                print(f"WTTJ : Aucune offre sur la page {page_num}. Arrêt.")
                break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_cards = soup.find_all("li", attrs={"data-testid": "search-results-list-item-wrapper"})
            if not job_cards: break

            with app.app_context():
                page_new_jobs_count = 0
                for card in job_cards:
                    # Logique d'extraction de la liste (titre, entreprise, lien, etc.)
                    # SANS AUCUN CLIC NI SCRAPING DE DÉTAILS
                    time_element = card.find("time")
                    if not time_element: continue
                    published_at = datetime.fromisoformat(time_element['datetime'].replace('Z', '+00:00'))

                    if published_at < seven_days_ago: continue 

                    all_links = card.find_all("a", href=lambda href: href and "/jobs/" in href)
                    company_element = card.find("span", class_=lambda x: x and x.startswith('sc-'))
                    if not all([all_links, company_element]): continue

                    title_link_element = all_links[1] if len(all_links) > 1 else all_links[0]
                    title = title_link_element.text.strip()
                    link = "https://www.welcometothejungle.com" + title_link_element['href']
                    company = company_element.text.strip()
                    location_icon = card.find("i", attrs={"name": "location"})
                    location = location_icon.find_next_sibling("p").text.strip() if location_icon and location_icon.find_next_sibling("p") else "N/A"
                    salary_icon = card.find("i", attrs={"name": "salary"})
                    salary = salary_icon.find_next_sibling("span").text.strip().replace('\xa0', ' ') if salary_icon and salary_icon.find_next_sibling("span") else None
                    tags_list = []
                    contract_icon = card.find("i", attrs={"name": "contract"})
                    if contract_icon and contract_icon.find_next_sibling("span"): tags_list.append(contract_icon.find_next_sibling("span").text.strip())
                    remote_icon = card.find("i", attrs={"name": "remote"})
                    if remote_icon and remote_icon.find_next_sibling("span"): tags_list.append(remote_icon.find_next_sibling("span").text.strip())
                    tags = ", ".join(tags_list) if tags_list else None
                    logo_url = None
                    all_images = card.select("img")
                    if len(all_images) > 1 and all_images[1].get('src'): logo_url = all_images[1]['src']

                    job_data = {"title": title, "company": company, "location": location, "link": link, "source": "Welcome to the Jungle", "published_at": published_at, "salary": salary, "tags": tags, "logo_url": logo_url}
                    if save_job_to_db(job_data): page_new_jobs_count += 1
                
                if page_new_jobs_count > 0: db.session.commit()
                new_jobs_count += page_new_jobs_count

    except Exception as e: print(f"Erreur lors du scraping de WTTJ : {e}")
    finally:
        if driver: driver.quit()
    print(f"WTTJ : {new_jobs_count} nouvelle(s) offre(s) récente(s) ajoutée(s).")

# --- SCRAPER POUR WEB3.CAREER ---
def scrape_web3_career():
    print("\n--- Début du scraping sur Web3.career ---")
    
    # NOUVEAU : Constantes pour la pagination
    NUM_PAGES_TO_SCRAPE = 25 # Vous pouvez ajuster ce nombre
    BASE_URL = "https://web3.career/remote-jobs?page={}"

    driver = None
    new_jobs_count = 0
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        stop_scraping_site = False

        # NOUVEAU : Boucle pour parcourir les pages
        for page_num in range(1, NUM_PAGES_TO_SCRAPE + 1):
            if stop_scraping_site:
                break

            current_url = BASE_URL.format(page_num)
            print(f"\nWeb3.career : Traitement de la page {page_num}/{NUM_PAGES_TO_SCRAPE}...")
            
            driver.get(current_url)
            try:
                # Ajout d'un try/except pour gérer les pages qui n'ont plus d'offres
                WebDriverWait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr[data-jobid]")))
                time.sleep(2)
            except Exception:
                print(f"Web3.career : Aucune offre trouvée sur la page {page_num} ou la page n'a pas chargé. Arrêt.")
                break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            tbody = soup.find("tbody")
            job_rows = tbody.find_all("tr", attrs={"data-jobid": True}) if tbody else []
            print(f"Web3.career : {len(job_rows)} offres trouvées sur la page {page_num}.")

            if not job_rows:
                break

            with app.app_context():
                page_new_jobs_count = 0
                for row in job_rows:
                    published_at = None
                    time_element = row.find("time")
                    if time_element and 'datetime' in time_element.attrs:
                        try:
                            # La date est déjà au bon format, on la convertit
                            published_at = datetime.fromisoformat(time_element['datetime'].replace('Z', '+00:00'))
                        except ValueError: pass
                    
                    # NOUVEAU : Logique d'arrêt optimisée
                    # Si une offre est trop vieille, on arrête tout pour ce site.
                    if published_at and published_at < seven_days_ago:
                        print("Web3.career : Offres trop anciennes atteintes. Arrêt du scraping pour ce site.")
                        stop_scraping_site = True
                        break # Arrête de traiter les offres de cette page

                    link_element = row.get('onclick')
                    title_element = row.find("h2")
                    company_element = row.find("h3")
                    if not all([link_element, title_element, company_element]): continue
                    
                    link = "https://web3.career" + link_element.split("'")[1]
                    title = title_element.text.strip()
                    company = company_element.text.strip()
                    location_element = row.select_one("td.job-location-mobile a")
                    location = location_element.text.strip() if location_element else "Remote"
                    salary_element = row.select_one("p.text-salary")
                    salary = salary_element.text.strip().replace('\n', ' ').replace('$', '$ ') if salary_element else None
                    tag_elements = row.select("span.my-badge a")
                    tags = ", ".join([tag.text.strip() for tag in tag_elements]) if tag_elements else None

                    job_data = {"title": title, "company": company, "location": location, "link": link, "source": "Web3.career", "published_at": published_at, "salary": salary, "tags": tags}
                    if save_job_to_db(job_data):
                        page_new_jobs_count += 1
                
                # NOUVEAU : Commit après chaque page
                if page_new_jobs_count > 0:
                    db.session.commit()
                new_jobs_count += page_new_jobs_count

    except Exception as e: print(f"Erreur lors du scraping de Web3.career : {e}")
    finally:
        if driver: driver.quit()
    print(f"Web3.career : {new_jobs_count} nouvelle(s) offre(s) récente(s) ajoutée(s) au total.")



# --- SCRAPER POUR CRYPTO CAREERS (STRATÉGIE "FERMER ET ROUVRIR") ---
def scrape_crypto_careers():
    print("\n--- Début du scraping sur Crypto Careers (Stratégie 'Fermer et Rouvrir') ---")
    
    NUM_PAGES_TO_SCRAPE = 15
    BASE_URL = "https://www.crypto-careers.com/jobs/search?page={}&sort=published_at"
    
    # Le compteur total est en dehors de la boucle
    new_jobs_count = 0
    
    # La boucle principale itère sur les pages
    for page_num in range(1, NUM_PAGES_TO_SCRAPE + 1):
        
        driver = None # On réinitialise le driver à chaque itération
        print(f"\nCrypto Careers : Traitement de la page {page_num}/{NUM_PAGES_TO_SCRAPE}...")

        try:
            # 1. OUVRIR une nouvelle session de navigateur pour chaque page
            print(f"  [SESSION] Ouverture d'un nouveau navigateur pour la page {page_num}...")
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
            
            # 2. VISITER une seule URL avec cette nouvelle session
            current_url = BASE_URL.format(page_num)
            driver.get(current_url)

            # 3. SCRAPER la page
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.job-listing"))
            )
            
            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_cards = soup.select("li.job-listing")
            print(f"  [INFO] {len(job_cards)} offres trouvées sur la page.")

            if not job_cards:
                print("  [INFO] La page est vide, arrêt de ce scraper.")
                break # On quitte la boucle for si une page est vide
            
            # La logique de parsing des offres reste la même
            seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
            month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
            
            with app.app_context():
                page_new_jobs_count = 0
                for card in job_cards:
                    date_element = card.select_one(".jobList-date")
                    if not date_element: continue
                    published_at = None
                    try:
                        date_text = date_element.text.strip()
                        parts = date_text.split()
                        if len(parts) == 2:
                            month_str, day_str = parts
                            month = month_map[month_str]
                            day = int(day_str)
                            year = datetime.now().year
                            if month == 12 and datetime.now().month == 1: year -= 1
                            published_at = datetime(year, month, day, tzinfo=timezone.utc)
                    except: pass
                    if published_at and published_at < seven_days_ago: continue
                    title_element = card.select_one(".jobList-title strong")
                    link_element = card.select_one(".jobList-title")
                    if not title_element or not link_element: continue
                    title = title_element.text.strip()
                    link = "https://www.crypto-careers.com" + link_element['href']
                    company_icon = card.select_one("i.fa-building")
                    company = company_icon.next_sibling.strip() if company_icon and company_icon.next_sibling else "N/A"
                    location_icon = card.select_one("i.fa-map-marker-alt")
                    location = location_icon.next_sibling.strip() if location_icon and location_icon.next_sibling else "N/A"
                    tags_list = []
                    work_type_icon = card.select_one("i.fa-business-time, i.fa-wifi")
                    if work_type_icon and work_type_icon.find_next_sibling('span'): tags_list.append(work_type_icon.find_next_sibling('span').text.strip())
                    tags = ", ".join(tags_list) if tags_list else None
                    logo_img = card.select_one("div.jobList-media img")
                    logo_url = logo_img['src'] if logo_img and logo_img.get('src') else None

                    job_data = {"title": title, "company": company, "location": location, "link": link, "source": "Crypto Careers", "published_at": published_at, "tags": tags, "logo_url": logo_url}
                    if save_job_to_db(job_data):
                        page_new_jobs_count += 1
                
                if page_new_jobs_count > 0:
                    db.session.commit()
                new_jobs_count += page_new_jobs_count
        
        except Exception as e:
            print(f"  [ERREUR] Une erreur est survenue sur la page {page_num}: {e}")
            break
        
        finally:
            # 4. FERMER le navigateur, quoi qu'il arrive, pour la prochaine itération
            if driver:
                print(f"  [SESSION] Fermeture du navigateur pour la page {page_num}.")
                driver.quit()

    print(f"\nCrypto Careers : {new_jobs_count} nouvelle(s) offre(s) récente(s) ajoutée(s) au total.")



def scrape_cryptocurrency_jobs():
    print("\n--- Début du scraping sur Cryptocurrency Jobs ---")
    URL = "https://cryptocurrencyjobs.co/"
    driver = None
    new_jobs_count = 0
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        driver.get(URL)
        WebDriverWait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.ais-Hits-item")))
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.select("li.ais-Hits-item")
        print(f"Cryptocurrency Jobs : {len(job_cards)} offres trouvées.")
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        if not job_cards: return

        with app.app_context():
            for card in job_cards:
                time_element = card.select_one("time")
                published_at = None
                if time_element and 'datetime' in time_element.attrs and time_element['datetime']:
                    try:
                        published_at = datetime.fromisoformat(time_element['datetime'].replace('Z', '+00:00'))
                        # --- CORRECTIF ---
                        # Si la date est naïve (malgré le replace), on la rend consciente
                        if published_at.tzinfo is None:
                            published_at = published_at.replace(tzinfo=timezone.utc)
                    except ValueError: pass
                
                if published_at and published_at < seven_days_ago: continue
                
                # ... le reste de la fonction ne change pas ...
                title_link_element = card.select_one("h2 a")
                company_element = card.select_one("h3 a")
                if not all([title_link_element, company_element]): continue
                title = title_link_element.text.strip()
                link = "https://cryptocurrencyjobs.co" + title_link_element['href']
                company = company_element.text.strip()
                logo_element = card.select_one("img.rounded-full")
                logo_url = "https://cryptocurrencyjobs.co" + logo_element['src'] if logo_element and logo_element.get('src') else None
                tags_list = []; location = "N/A"
                main_tags = card.select("h4 a")
                for tag in main_tags:
                    if any(c in tag.get('href','') for c in ['/london/','/remote/','/new-york/']): location = tag.text.strip()
                    else: tags_list.append(tag.text.strip())
                tech_tags = card.select("ul.flex-wrap a")
                tags_list.extend([tag.text.strip() for tag in tech_tags])
                tags = ", ".join(tags_list) if tags_list else None
                salary_div = card.find("div", string=lambda t: t and "$" in t)
                salary = salary_div.text.strip() if salary_div else None

                job_data = {"title": title, "company": company, "location": location, "link": link, "source": "Cryptocurrency Jobs", "published_at": published_at, "tags": tags, "salary": salary, "logo_url": logo_url}
                if save_job_to_db(job_data): new_jobs_count += 1
            db.session.commit()
    except Exception as e: print(f"Erreur lors du scraping de Cryptocurrency Jobs : {e}")
    finally:
        if driver: driver.quit()
    print(f"Cryptocurrency Jobs : {new_jobs_count} nouvelle(s) offre(s) récente(s) ajoutée(s).")

# scraper.py (uniquement la fonction scrape_cryptojobslist)

# --- SCRAPER POUR CRYPTOJOBSLIST (CORRECTION FINALE DE LA LOCALISATION) ---
def scrape_cryptojobslist():
    print("\n--- Début du scraping sur Crypto Jobs List (rapide) ---")
    
    NUM_PAGES_TO_SCRAPE = 3
    BASE_URL = "https://cryptojobslist.com/?sort=recent&page={}"

    driver = None
    new_jobs_count = 0
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        for page_num in range(1, NUM_PAGES_TO_SCRAPE + 1):
            current_url = BASE_URL.format(page_num)
            print(f"\nCrypto Jobs List : Traitement de la page {page_num}/{NUM_PAGES_TO_SCRAPE}...")
            driver.get(current_url)
            
            WebDriverWait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tbody > tr")))
            time.sleep(3)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_rows = soup.select("tbody > tr")
            print(f"Crypto Jobs List : {len(job_rows)} offres trouvées sur la page {page_num}.")
            if not job_rows: break

            with app.app_context():
                page_new_jobs_count = 0
                for row in job_rows:
                    title_link_element = row.select_one("a.job-title-text")
                    if not title_link_element: continue
                    link = "https://cryptojobslist.com" + title_link_element['href']

                    if Job.query.filter_by(link=link).first():
                        continue

                    title = title_link_element.text.strip()
                    company_link_element = row.select_one("a.job-company-name-text")
                    company = company_link_element.text.strip() if company_link_element else "N/A"
                    logo_img = row.select_one(".job-company-logo img")
                    logo_url = logo_img.get('src') if logo_img and logo_img.get('src') else None
                    salary_element = row.select_one("svg[stroke='currentColor'] + span")
                    salary = salary_element.text.strip() if salary_element else None

                    # --- LOGIQUE DE LOCALISATION ET TAGS CORRIGÉE ---
                    
                    # 1. On récupère les tags "normaux"
                    tag_elements = row.select(".job-tags span.category")
                    tags_list = [tag.text.strip() for tag in tag_elements]
                    tags = ", ".join(tags_list) if tags_list else None
                    
                    # 2. On récupère la localisation depuis sa cellule spécifique
                    # Le sélecteur cible le span avec le point rose (le premier enfant de la td)
                    location_element = row.select_one("td > span.text-sm")
                    location = location_element.text.strip() if location_element else "N/A"
                    
                    # 3. On vérifie si "Remote" est dans les tags pour être sûr
                    if 'Remote' in tags_list and location == 'N/A':
                        location = 'Remote'

                    # ----------------------------------------------------

                    # La logique de date reste la même
                    published_at = None
                    date_element = row.select_one("td.job-time-since-creation")
                    if date_element:
                        date_text = date_element.text.strip().lower()
                        now = datetime.now(timezone.utc)
                        try:
                            if "today" in date_text: published_at = now
                            elif "yesterday" in date_text: published_at = now - timedelta(days=1)
                            elif 'w' in date_text: published_at = now - timedelta(weeks=int(re.search(r'\d+', date_text).group()))
                            elif 'd' in date_text: published_at = now - timedelta(days=int(re.search(r'\d+', date_text).group()))
                            elif 'h' in date_text: published_at = now - timedelta(hours=int(re.search(r'\d+', date_text).group()))
                            elif 'm' in date_text: published_at = now - timedelta(minutes=int(re.search(r'\d+', date_text).group()))
                        except (ValueError, AttributeError, TypeError): pass
                    
                    job_data = {
                        "title": title, "company": company, "location": location,
                        "link": link, "source": "Crypto Jobs List", "published_at": published_at,
                        "salary": salary, "tags": tags, "logo_url": logo_url,
                    }
                    if save_job_to_db(job_data):
                        page_new_jobs_count += 1
                
                if page_new_jobs_count > 0:
                    db.session.commit()
                new_jobs_count += page_new_jobs_count

    except Exception as e: print(f"Erreur lors du scraping de Crypto Jobs List : {e}")
    finally:
        if driver: driver.quit()
    print(f"Crypto Jobs List : {new_jobs_count} nouvelle(s) offre(s) récente(s) ajoutée(s).")

# Dans scraper.py
def scrape_onchainjobs():
    print("\n--- Début du scraping sur OnchainJobs ---")
    URL = "https://www.onchainjobs.io/jobs-emplois-carriere/"
    driver = None
    new_jobs_count = 0
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        driver.get(URL)
        WebDriverWait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.job_listing")))
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.select("li.job_listing")
        print(f"OnchainJobs : {len(job_cards)} offres trouvées sur la page.")
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        if not job_cards: return

        with app.app_context():
            for card in job_cards:
                published_at = None
                date_element = card.select_one("li.date time")
                if date_element and date_element.get('datetime'):
                    try:
                        published_at = datetime.fromisoformat(date_element['datetime'])
                        # --- CORRECTIF ---
                        # Si la date est naïve, on la considère comme UTC
                        if published_at.tzinfo is None:
                            published_at = published_at.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass

                if published_at and published_at < seven_days_ago: continue

                # ... le reste de la fonction ne change pas ...
                title_link_element = card.select_one("div.position h3")
                link_element = card.select_one("a")
                if not title_link_element or not link_element: continue
                title = title_link_element.text.strip()
                link = link_element['href']
                company_element = card.select_one("div.company strong")
                company = company_element.text.strip() if company_element else "N/A"
                location_element = card.select_one("div.location")
                location = location_element.text.strip() if location_element else "N/A"
                logo_element = card.select_one("img.company_logo")
                logo_url = logo_element['src'] if logo_element and logo_element.get('src') else None
                job_type_element = card.select_one("li.job-type")
                tags = job_type_element.text.strip() if job_type_element else None
                
                job_data = {"title": title, "company": company, "location": location, "link": link, "source": "OnchainJobs", "published_at": published_at, "tags": tags, "logo_url": logo_url, "salary": None}
                if save_job_to_db(job_data): new_jobs_count += 1
            db.session.commit()
    except Exception as e: print(f"Erreur lors du scraping de OnchainJobs : {e}")
    finally:
        if driver: driver.quit()
    print(f"OnchainJobs : {new_jobs_count} nouvelle(s) offre(s) récente(s) ajoutée(s).")

def scrape_remote3():
    print("\n--- Début du scraping sur Remote3 (Méthode simplifiée) ---")
    URL = "https://www.remote3.co/remote-web3-jobs"
    
    driver = None
    new_jobs_count = 0
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
        
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        driver.get(URL)
        
        print("Remote3 : Attente du chargement initial...")
        time.sleep(5) 

        scroll_count = 4
        print(f"Remote3 : Début de {scroll_count} défilements fixes...")
        
        for i in range(scroll_count):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            print(f"  Défilement {i + 1}/{scroll_count} effectué.")
            time.sleep(3)
            
        print("Remote3 : Fin du défilement.")
        time.sleep(2)
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.select("a[href^='/remote-jobs/']")
        
        print(f"Remote3 : {len(job_cards)} offres trouvées au total.")

        if not job_cards:
            print("Aucune offre trouvée. Le site a peut-être changé ou n'a pas chargé le contenu.")
            with open("remote3_debug_page.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("Le contenu de la page a été sauvegardé dans 'remote3_debug_page.html' pour analyse.")
            return

        with app.app_context():
            for card in job_cards:
                title_element = card.find("h2")
                company_element = card.find("p")

                if not title_element or not company_element:
                    continue

                link = "https://www.remote3.co" + card.get('href', '')
                title = title_element.text.strip()
                company = company_element.text.strip()
                
                logo_element = card.find("img")
                logo_url = logo_element.get('src') if logo_element else None

                location = "Remote"
                salary = None
                tags_list = []
                
                info_elements = card.select("div[class*='JobListingItem_infoContainer']")
                for info in info_elements:
                    text = info.text.strip()
                    if '$' in text or '€' in text: salary = text
                    elif '📍' in text: location = text.replace('📍', '').strip()
                    else: tags_list.append(text)
                
                tags = ", ".join(tags_list) if tags_list else None

                published_at = None
                date_element = card.select_one("div[class*='JobListingItem_rightContainer'] p")
                if date_element:
                    date_text = date_element.text.strip().lower()
                    now = datetime.now(timezone.utc)
                    try:
                        # --- CORRECTION ICI : AJOUT DE LA GESTION DES MINUTES ---
                        if 'minute' in date_text:
                            minutes_ago = int(re.search(r'\d+', date_text).group())
                            published_at = now - timedelta(minutes=minutes_ago)
                        elif 'hour' in date_text:
                            hours_ago = int(re.search(r'\d+', date_text).group())
                            published_at = now - timedelta(hours=hours_ago)
                        elif 'day' in date_text:
                            days_ago = int(re.search(r'\d+', date_text).group())
                            published_at = now - timedelta(days=days_ago)
                        elif 'month' in date_text:
                            months_ago = int(re.search(r'\d+', date_text).group())
                            published_at = now - timedelta(days=months_ago * 30)
                    except:
                        pass
                        
                job_data = {
                    "title": title, "company": company, "location": location,
                    "link": link, "source": "Remote3", "published_at": published_at,
                    "salary": salary, "tags": tags, "logo_url": logo_url
                }
                
                if save_job_to_db(job_data):
                    new_jobs_count += 1
            db.session.commit()
            
    except Exception as e:
        print(f"Erreur lors du scraping de Remote3 : {e}")
    finally:
        if driver: driver.quit()
        
    print(f"Remote3 : {new_jobs_count} nouvelle(s) offre(s) ajoutée(s).")


# --- SCRIPT PRINCIPAL ---
if __name__ == '__main__':
    if os.path.exists("jobs.db"):
        os.remove("jobs.db")
    
    with app.app_context():
        db.create_all()
    
    scrape_wttj()
    # scrape_web3_career()
    # scrape_crypto_careers()
    # scrape_cryptocurrency_jobs()
    scrape_cryptojobslist()
    # scrape_onchainjobs()
    # scrape_remote3()

    
    print("\nScraping de tous les sites terminé !")