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
import urllib.parse

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


            job_cards_selector = "li[data-testid='search-results-list-item-wrapper']"
            try:
                WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, job_cards_selector)))
                
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

# --- SCRAPER POUR WEB3.CAREER (RETOUR À LA STRATÉGIE SIMPLE) ---
def scrape_web3_career():
    print("\n--- Début du scraping sur Web3.career (Liste uniquement) ---")
    
    NUM_PAGES_TO_SCRAPE = 5 # Vous pouvez ajuster ce nombre
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

        for page_num in range(1, NUM_PAGES_TO_SCRAPE + 1):
            if stop_scraping_site: break

            current_url = BASE_URL.format(page_num)
            print(f"\nWeb3.career : Traitement de la page {page_num}/{NUM_PAGES_TO_SCRAPE}...")
            
            driver.get(current_url)
            try:
                WebDriverWait(driver, 1
                ).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr[data-jobid]")))
                
            except Exception:
                print(f"Web3.career : Aucune offre trouvée sur la page {page_num}. Arrêt.")
                break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_rows = soup.select("tbody > tr[data-jobid]")
            print(f"Web3.career : {len(job_rows)} offres trouvées sur la page {page_num}.")

            if not job_rows: break

            with app.app_context():
                page_new_jobs_count = 0
                for row in job_rows:
                    time_element = row.find("time")
                    published_at = None
                    if time_element and 'datetime' in time_element.attrs:
                        try:
                            published_at = datetime.fromisoformat(time_element['datetime'].replace('Z', '+00:00'))
                        except ValueError: pass
                    
                    if published_at and published_at < seven_days_ago:
                        print("Web3.career : Offres trop anciennes atteintes. Arrêt du scraping pour ce site.")
                        stop_scraping_site = True
                        break

                    link_attribute = row.get('onclick')
                    title_element = row.find("h2")
                    company_element = row.find("h3")
                    if not all([link_attribute, title_element, company_element]): continue
                    
                    link = "https://web3.career" + link_attribute.split("'")[1]
                    title = title_element.text.strip()
                    company = company_element.text.strip()
                    location_element = row.select_one("td.job-location-mobile a")
                    location = location_element.text.strip() if location_element else "Remote"
                    salary_element = row.select_one("p.text-salary")
                    salary = salary_element.text.strip().replace('\n', ' ').replace('$', '$ ') if salary_element else None
                    tag_elements = row.select("span.my-badge a")
                    tags = ", ".join([tag.text.strip() for tag in tag_elements]) if tag_elements else None

                    # On ne sauvegarde PAS la description ici
                    job_data = {"title": title, "company": company, "location": location, "link": link, "source": "Web3.career", "published_at": published_at, "salary": salary, "tags": tags}
                    if save_job_to_db(job_data):
                        page_new_jobs_count += 1
                
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
            WebDriverWait(driver, 1).until(
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
        WebDriverWait(driver, 1).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.ais-Hits-item")))
        
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
            
            WebDriverWait(driver, 1).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tbody > tr")))
            

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
        WebDriverWait(driver, 1).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.job_listing")))
        
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
         

        scroll_count = 20
        print(f"Remote3 : Début de {scroll_count} défilements fixes...")
        
        for i in range(scroll_count):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            print(f"  Défilement {i + 1}/{scroll_count} effectué.")
            
        time.sleep(3)
        print("Remote3 : Fin du défilement.")
        time.sleep(3)        
        
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


# scraper.py

def scrape_laborx():
    print("\n--- Début du scraping sur LaborX ---")
    URL = "https://laborx.com/vacancies?orderField=date&orderType=desc"
    # ... (le début est inchangé) ...

    new_jobs_count = 0
    driver = None
    try:
        # ... (configuration selenium inchangée) ...
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        driver.get(URL)
        
        card_selector = 'div.vacancy-card'
        WebDriverWait(driver, 1).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, card_selector))
        )
        

        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.select(card_selector)
        print(f"LaborX : {len(job_cards)} offres trouvées.")

        if not job_cards: return

        with app.app_context():
            for card in job_cards:
                # ... (extraction titre, compagnie, logo, salaire, date, localisation, tags... INCHANGÉ)
                name_row = card.select_one('p.name-row')
                if not name_row: continue
                all_links = name_row.select('a.name-link')
                if not all_links: continue
                title_element = all_links[0]
                title = title_element.text.strip()
                link = "https://laborx.com" + title_element['href']
                company = all_links[1].text.strip() if len(all_links) > 1 else "N/A"
                logo_element = card.select_one('div.user-name-logo img')
                logo_url = logo_element.get('src') if logo_element and logo_element.get('src') else None
                salary_element = card.select_one('div.conditions-info span.text-bold')
                salary = salary_element.text.strip() if salary_element else None
                published_at = None
                time_element = card.select_one('time[datetime]')
                if time_element:
                    try:
                        published_at = datetime.fromisoformat(time_element['datetime']).replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError): pass
                location_element = card.select_one('section[class*="vacancy-location-tooltip"] span')
                location = location_element.text.strip() if location_element else "Remote"
                tags_list = []
                info_tags = card.select('div.info-row div.info')
                tags_list.extend([tag.text.strip() for tag in info_tags])
                skill_tags = card.select('div.skills-wrapper a')
                tags_list.extend([tag.text.strip() for tag in skill_tags])
                tags = ", ".join(list(dict.fromkeys(tags_list))) if tags_list else None

                # --- AJOUT : EXTRACTION DE LA PETITE DESCRIPTION ---
                summary_element = card.select_one('div.description')
                summary_text = summary_element.text.strip() if summary_element else None
                
                job_data = {
                    "title": title, "company": company, "location": location,
                    "link": link, "source": "LaborX", "published_at": published_at,
                    "salary": salary, "tags": tags, "logo_url": logo_url,
                    "description": summary_text # On stocke le résumé ici
                }
                
                if save_job_to_db(job_data):
                    new_jobs_count += 1
            
            db.session.commit()
            
    except Exception as e:
        print(f"Erreur lors du scraping de LaborX : {e}")
    finally:
        if driver: driver.quit()
        
    print(f"LaborX : {new_jobs_count} nouvelle(s) offre(s) ajoutée(s).")



# scraper.py (uniquement la fonction scrape_hellowork optimisée)

def scrape_hellowork():
    print("\n--- Début du scraping sur Hellowork (Version optimisée avec Selenium) ---")
    
    NUM_PAGES_TO_SCRAPE = 10 
    BASE_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html?k=&st=date&c=CDI&d=w&t=Complet&p={}"
    MAX_JOB_AGE_DAYS = 7
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=MAX_JOB_AGE_DAYS)

    driver = None
    new_jobs_count = 0
    stop_scraping_site = False

    try:
        # NOTE : Pour une performance maximale, on passe à Selenium standard.
        # AVERTISSEMENT : Si Hellowork met en place une protection anti-bot plus agressive,
        # il faudra peut-être revenir à 'undetected_chromedriver'.
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)

        # Flag pour ne gérer les cookies qu'une seule fois
        cookies_handled = False

        for page_num in range(1, NUM_PAGES_TO_SCRAPE + 1):
            if stop_scraping_site: 
                break
            
            current_url = BASE_URL.format(page_num)
            print(f"\nHellowork : Traitement de la page {page_num}/{NUM_PAGES_TO_SCRAPE}...")
            driver.get(current_url)
            
            # --- GESTION OPTIMISÉE DES COOKIES ---
            # On ne tente de cliquer que sur la première page.
            if not cookies_handled:
                try:
                    # Temps d'attente pour les cookies réduit à 5 secondes.
                    print("  [INFO] Tentative de gestion du bandeau de cookies (attente max 5s)...")
                    cookie_button = WebDriverWait(driver, 1).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "#hw-cc-notice-accept-btn"))
                    )
                    cookie_button.click()
                    print("  [OK] Cookies acceptés.")
                except Exception:
                    print("  [INFO] Pas de bandeau de cookies trouvé ou cliquable dans le temps imparti.")
                finally:
                    # On ne réessaiera plus, même en cas d'échec.
                    cookies_handled = True
            
            card_selector = "li[data-id-storage-target='item']"
            try:
                WebDriverWait(driver, 1).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, card_selector)))
            except Exception:
                print(f"Hellowork : Aucune offre sur la page {page_num}. Arrêt.")
                break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_cards = soup.select(card_selector)
            if not job_cards: break

            print(f"  [INFO] {len(job_cards)} offres trouvées sur la page {page_num}.")
            
            page_new_jobs_count = 0
            with app.app_context():
                # La logique d'extraction des offres reste identique
                for card in job_cards:
                    title_link = card.select_one('a[data-cy="offerTitle"]')
                    if not title_link: continue
                    
                    title_element = title_link.select_one("h3 p")
                    company_element = title_link.select_one("h3 p.tw-typo-s")
                    location_element = card.select_one('div[data-cy="localisationCard"]')
                    if not all([title_element, company_element, location_element]): continue

                    raw_link = title_link['href']
                    link = urllib.parse.urljoin(current_url, raw_link).split('?')[0]

                    # On peut garder cette vérification pour éviter de traiter des offres déjà en DB
                    if Job.query.filter_by(link=link).first():
                        continue

                    published_at = None
                    date_element = card.select_one("div.tw-justify-between > div.tw-text-grey")
                    if date_element:
                        date_text = date_element.text.strip().lower()
                        now = datetime.now(timezone.utc)
                        try:
                            if "instant" in date_text or "aujourd'hui" in date_text: published_at = now
                            elif "moins d'une heure" in date_text or "minute" in date_text: published_at = now
                            elif "heure" in date_text: published_at = now - timedelta(hours=int(re.search(r'\d+', date_text).group()))
                            elif "hier" in date_text: published_at = now - timedelta(days=1)
                            elif "jour" in date_text: published_at = now - timedelta(days=int(re.search(r'\d+', date_text).group()))
                        except (ValueError, AttributeError, TypeError):
                             pass
                    
                    if published_at and published_at < seven_days_ago:
                        print(f"Hellowork : Offre trop ancienne trouvée ('{date_text}'). Arrêt du scraping.")
                        stop_scraping_site = True
                        break
                    
                    title = title_element.text.strip()
                    company = company_element.text.strip()
                    location = location_element.text.strip()
                    
                    logo_element = card.select_one("header img")
                    logo_url = logo_element.get('src') if logo_element and 'http' in logo_element.get('src', '') else None
                    salary_element = card.select_one('div[data-cy="contractCard"] + div')
                    salary = salary_element.text.strip().replace("\xa0", " ") if salary_element and salary_element.text else None
                    tags_list = []
                    contract_card = card.select_one('div[data-cy="contractCard"]')
                    if contract_card: tags_list.append(contract_card.text.strip())
                    contract_tag = card.select_one('div[data-cy="contractTag"]')
                    if contract_tag: tags_list.append(contract_tag.text.strip())
                    tags = ", ".join(tags_list) if tags_list else None

                    job_data = { "title": title, "company": company, "location": location, "link": link, "source": "Hellowork", "published_at": published_at, "salary": salary, "tags": tags, "logo_url": logo_url }

                    if save_job_to_db(job_data):
                        page_new_jobs_count += 1
                
                if page_new_jobs_count > 0:
                    db.session.commit()
                    print(f"  [DB] {page_new_jobs_count} nouvelle(s) offre(s) de cette page ajoutée(s).")
                
                new_jobs_count += page_new_jobs_count

    except Exception as e:
        print(f"Erreur lors du scraping de Hellowork : {e}")
    finally:
        if driver: driver.quit()
    print(f"\nHellowork : {new_jobs_count} nouvelle(s) offre(s) récente(s) ajoutée(s) au total.")



# Dans scraper.py

def scrape_indeed():
    print("\n--- Début du scraping sur Indeed (avec Tags et Inversion) ---")

    RUN_HEADLESS = False
    profile_path = os.path.abspath("chrome_profile_indeed")
    print(f"[INFO] Utilisation du profil Chrome (déjà connecté) : {profile_path}")

    TARGET_URL = "https://fr.indeed.com/jobs?q=&l=Télétravail&sort=date&fromage=7"
    NUM_PAGES_TO_SCRAPE = 5
    
    driver = None
    all_jobs_data = []

    try:
        # ... (la configuration du driver reste la même) ...
        options = uc.ChromeOptions()
        if RUN_HEADLESS:
            options.add_argument("--headless")
        
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f'--user-data-dir={profile_path}')
        options.add_argument('--profile-directory=Default')
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--start-maximized")
        
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=137)
        
        with app.app_context():
            processed_links = {job.link for job in Job.query.filter_by(source='Indeed').with_entities(Job.link).all()}

        for page_num in range(NUM_PAGES_TO_SCRAPE):
            print(f"\nIndeed : Collecte sur la page {page_num + 1}/{NUM_PAGES_TO_SCRAPE}...")
            # ... (la navigation et la gestion des pop-ups restent les mêmes) ...
            if page_num == 0: current_url = TARGET_URL
            else: current_url = f"{TARGET_URL}&start={page_num * 10}"
            
            driver.get(current_url)

            try:
                close_button_selector = "button[aria-label='close'], button.icl-CloseButton"
                close_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, close_button_selector)))
                close_button.click()
                print("  [INFO] Pop-up fermé.")
            except Exception:
                print("  [INFO] Pas de pop-up trouvé ou déjà fermé.")
            card_selector = "div.job_seen_beacon"
            try:
                WebDriverWait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, card_selector)))
            except Exception:
                print(f"  [AVERTISSEMENT] Aucune offre trouvée sur la page {page_num + 1}.")
                driver.save_screenshot(f"indeed_debug_page_{page_num + 1}.png")
                break
            
            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_cards = soup.select(card_selector)
            if not job_cards: break
            
            print(f"  [INFO] {len(job_cards)} offres trouvées sur la page.")
            
            for card in job_cards:
                title_element = card.select_one('h2.jobTitle span')
                company_element = card.select_one('span[data-testid="company-name"]')
                location_element = card.select_one('div[data-testid="text-location"]')
                link_element = card.select_one('a.jcs-JobTitle')

                if not all([title_element, company_element, location_element, link_element]): continue
                
                relative_link = link_element['href']
                link_key_match = re.search(r'jk=([a-f0-9]+)', relative_link)
                if not link_key_match: continue
                link = f"https://fr.indeed.com/viewjob?jk={link_key_match.group(1)}"
                
                if link in processed_links: continue
                
                title = title_element.text.strip()
                company = company_element.text.strip()
                location = location_element.text.strip()
                
                # --- NOUVELLE LOGIQUE D'EXTRACTION DES TAGS ---
                tags_list = []
                # Sélecteur 1 : pour les div contenant du texte de tag
                tag_divs = card.select("div[data-testid='attribute_snippet_testid']")
                for div in tag_divs:
                    tag_text = " ".join(div.stripped_strings).strip()
                    if tag_text:
                        tags_list.append(tag_text)
                # Sélecteur 2 : pour les li étant directement des tags
                tag_lis = card.select("li.css-5ooe72")
                for li in tag_lis:
                    tag_text = li.text.strip()
                    if tag_text:
                        tags_list.append(tag_text)
                # On nettoie la liste des doublons et des éléments non pertinents
                final_tags = [t for t in list(dict.fromkeys(tags_list)) if t]
                tags = ", ".join(final_tags) if final_tags else None
                # --------------------------------------------------

                date_element = card.select_one('span.date')
                date_text = date_element.text.strip().lower() if date_element else ""

                published_at = None
                now = datetime.now(timezone.utc)
                try:
                    if "aujourd'hui" in date_text or "instant" in date_text: published_at = now
                    elif "hier" in date_text: published_at = now - timedelta(days=1)
                    elif "jour" in date_text:
                        days_ago = int(re.search(r'\d+', date_text).group())
                        if days_ago <= 7: published_at = now - timedelta(days=days_ago)
                        else: continue
                except (ValueError, AttributeError, TypeError): pass
                
                salary_element = card.select_one('div.salary-snippet-container')
                salary = salary_element.text.strip().replace('\xa0', ' ') if salary_element else None
                snippet_element = card.select_one('div.job-snippet')
                description = snippet_element.text.strip().replace('\n', ' ') if snippet_element else None

                job_data = {
                    "title": title, "company": company, "location": location,
                    "link": link, "source": "Indeed", "published_at": published_at,
                    "salary": salary, "tags": tags, "logo_url": None,
                    "description": description 
                }
                
                all_jobs_data.append(job_data)

    except Exception as e:
        print(f"Erreur majeure lors du scraping de Indeed : {e}")
    finally:
        if driver:
            driver.quit()

    if all_jobs_data:
        print(f"\n[INFO] {len(all_jobs_data)} offres collectées. Inversion et enregistrement...")
        all_jobs_data.reverse()
        
        with app.app_context():
            new_jobs_count = 0
            for job_data in all_jobs_data:
                if save_job_to_db(job_data):
                    new_jobs_count += 1
            db.session.commit()
            
    print(f"\nIndeed : {new_jobs_count} nouvelle(s) offre(s) récente(s) ajoutée(s).")


# Dans scraper.py

def scrape_glassdoor():
    print("\n--- Début du scraping sur Glassdoor ---")
    
    NUM_CLICKS = 6 # Nombre de fois où on clique sur "Voir plus"
    profile_path = os.path.abspath("chrome_profile_glassdoor")
    if not os.path.exists(profile_path):
        print("[ERREUR] Profil Glassdoor non trouvé. Veuillez lancer 'create_session_glassdoor.py' d'abord.")
        return

    TARGET_URL = "https://www.glassdoor.fr/Emploi/télétravail-france-emplois-SRCH_IL.0,18_IS11049.htm?sortBy=date_desc&fromAge=7&remoteWorkType=1"
    
    driver = None
    all_jobs_data = []

    try:
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f'--user-data-dir={profile_path}')
        options.add_argument('--profile-directory=Default')
        options.add_argument("--window-size=1280,800")
        
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=137)
        
        driver.get(TARGET_URL)

        try:
            driver.find_element(By.ID, "onetrust-accept-btn-handler").click()
            print("  [INFO] Bannière de cookies fermée.")
        except Exception:
            pass # Pas de bannière, on continue
        
        WebDriverWait(driver, 1).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[data-jobid]")))
        print("  [INFO] Offres initiales chargées.")

        load_more_button_selector = "button[data-test='load-more']"
        close_popup_selector = "button[data-test='job-alert-modal-close']"
        
        for i in range(NUM_CLICKS):
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                load_more_button = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR, load_more_button_selector)))
                load_more_button.click()
                print(f"  [INFO] Clic n°{i + 1}/{NUM_CLICKS} sur 'Voir plus'.")
                time.sleep(1.5)
                try:
                    driver.find_element(By.CSS_SELECTOR, close_popup_selector).click()
                    print("    [+] Pop-up 'Job Alert' fermé.")
                except Exception: pass
            except Exception:
                print("  [INFO] Le bouton 'Voir plus' n'est plus disponible.")
                break
        
        print("\n  [INFO] Scraping de l'ensemble de la page...")
        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.select("li[data-jobid]")
            
        print(f"  [INFO] {len(job_cards)} offres trouvées au total.")

        with app.app_context():
            processed_links = {job.link for job in Job.query.filter_by(source='Glassdoor').with_entities(Job.link).all()}
            
            for card in job_cards:
                title_link_element = card.select_one("a[data-test='job-title']")
                company_element = card.select_one("div[class*='EmployerProfile_employerNameContainer']")

                # Condition de garde
                if not title_link_element or not title_link_element.has_attr('href') or not company_element:
                    continue

                # --- LOGIQUE DE LIEN SIMPLIFIÉE ET CORRIGÉE ---
                # D'après l'image, le href est TOUJOURS une URL complète.
                # On la prend telle quelle et on nettoie juste les paramètres.
                # NOUVEAU CODE
                # On prend l'URL complète du href, sans la modifier.
                link = title_link_element['href']
                # ---------------------------------------------

                if link in processed_links: 
                    continue
                    
                title = title_link_element.text.strip()
                company = company_element.text.strip()
                location_element = card.select_one("div[data-test='emp-location']")
                location = location_element.text.strip() if location_element else "N/A"
                salary_element = card.select_one("div[data-test='detailSalary']")
                salary = salary_element.text.strip().replace('\xa0', ' ') if salary_element else None
                logo_element = card.select_one("div[id*='job-employer'] img")
                logo_url = logo_element.get('src') if logo_element else None
                # NOUVEAU CODE CORRIGÉ
                date_element = card.select_one("div[data-test='job-age']")
                published_at = None
                if date_element:
                    date_text = date_element.text.strip().lower()
                    now = datetime.now(timezone.utc)
                    
                    try:
                        # re.search(r'\d+', ...) trouve la première séquence de chiffres dans le texte.
                        number_match = re.search(r'(\d+)', date_text)
                        if number_match:
                            value = int(number_match.group(1))
                            
                            if 'h' in date_text:
                                # Cas: "24h"
                                published_at = now - timedelta(hours=value)
                            elif 'j' in date_text:
                                # Cas: "2j", "3j", etc.
                                published_at = now - timedelta(days=value)
                            # On peut ajouter 'd' comme alias pour 'jour' si le site change
                            elif 'd' in date_text and '30' not in date_text: 
                                published_at = now - timedelta(days=value)

                        # Cas spécial pour "30j+"
                        elif '30' in date_text and '+' in date_text:
                            published_at = now - timedelta(days=30)

                    except (AttributeError, ValueError):
                        # Cette erreur se produit si re.search ne trouve rien ou si la conversion échoue
                        # On ne fait rien, published_at restera None.
                        pass
                
                job_data = { "title": title, "company": company, "location": location, "link": link, "source": "Glassdoor", "published_at": published_at, "salary": salary, "tags": None, "logo_url": logo_url, "description": None }
                all_jobs_data.append(job_data)
        
        if all_jobs_data:
            print(f"  [INFO] {len(all_jobs_data)} offres valides prêtes pour la BDD.")
            all_jobs_data.reverse()
            with app.app_context():
                new_jobs_count = 0
                for job_data in all_jobs_data:
                    if save_job_to_db(job_data):
                        new_jobs_count += 1
                db.session.commit()
            print(f"Glassdoor : {new_jobs_count} nouvelle(s) offre(s) ajoutée(s).")
        else:
            print("[AVERTISSEMENT] Aucune nouvelle offre à ajouter.")

    except Exception as e:
        print(f"Erreur majeure lors du scraping de Glassdoor : {e}")
        if driver: driver.save_screenshot("glassdoor_fatal_error.png")
    finally:
        if driver:
            driver.quit()



# --- SCRIPT PRINCIPAL ---
if __name__ == '__main__':
    if os.path.exists("jobs.db"):
        os.remove("jobs.db")
    
    with app.app_context():
        db.create_all()
    
    scrape_wttj()
    scrape_web3_career()
    scrape_crypto_careers()
    scrape_cryptocurrency_jobs()
    scrape_cryptojobslist()
    scrape_onchainjobs()
    scrape_remote3()
    scrape_laborx()
    scrape_hellowork()
    scrape_indeed()
    scrape_glassdoor()

    
    print("\nScraping de tous les sites terminé !")