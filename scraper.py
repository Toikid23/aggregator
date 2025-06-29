import time
import os
import re
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
import undetected_chromedriver as uc
import urllib.parse

from app import db, Job, app

# --- FONCTION UTILITAIRE STABLE ---
def save_job_to_db(job_data):
    # On compare les liens sans les paramètres de tracking pour éviter les faux doublons
    link_to_check = job_data['link'].split('?')[0]



    if "indeed.com" in link_to_check:
        match = re.search(r'jk=([a-f0-9]+)', link_to_check)
        if match:
            # On cherche n'importe quelle offre ayant ce même 'jk'
            job_key = match.group(1)
            exists = Job.query.filter(Job.link.like(f"%jk={job_key}%")).first()
        else:
            # Si pas de 'jk', on fait une recherche normale
            exists = Job.query.filter_by(link=link_to_check).first()
    else:
        # Pour les autres sites, on garde la méthode simple
        exists = Job.query.filter_by(link=link_to_check).first()
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

# --- Welcome to the Jungle (avec arrêt intelligent) ---
def scrape_wttj():
    print("\n--- Début du scraping sur Welcome to the Jungle ---")
    NUM_PAGES_TO_SCRAPE = 10
    DUPLICATE_THRESHOLD = 10
    BASE_URL = "https://www.welcometothejungle.com/fr/jobs?aroundQuery=worldwide&sortBy=mostRecent&refinementList%5Bremote%5D%5B%5D=fulltime&page={}"
    
    driver = None
    all_jobs_data = []
    stop_scraping_site = False

    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        with app.app_context():
            processed_links = {job.link for job in Job.query.filter_by(source='Welcome to the Jungle').with_entities(Job.link).all()}

        for page_num in range(1, NUM_PAGES_TO_SCRAPE + 1):
            if stop_scraping_site:
                print("  [INFO] Seuil de doublons atteint. Arrêt pour WTTJ.")
                break

            current_url = BASE_URL.format(page_num)
            print(f"WTTJ : Traitement de la page {page_num}/{NUM_PAGES_TO_SCRAPE}...")
            driver.get(current_url)

            job_cards_selector = "li[data-testid='search-results-list-item-wrapper']"
            try:
                WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, job_cards_selector)))
            except Exception:
                print(f"WTTJ : Aucune offre sur la page {page_num}. Arrêt.")
                break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_cards = soup.select(job_cards_selector)
            if not job_cards: break

            consecutive_duplicates = 0
            for card in job_cards:
                all_links = card.select("a[href*='/jobs/']")
                if not all_links: continue
                title_link_element = all_links[1] if len(all_links) > 1 else all_links[0]
                link = "https://www.welcometothejungle.com" + title_link_element['href']

                if link in processed_links:
                    consecutive_duplicates += 1
                    if consecutive_duplicates >= DUPLICATE_THRESHOLD:
                        stop_scraping_site = True
                        break
                    continue
                
                consecutive_duplicates = 0
                
                title = title_link_element.text.strip()
                company_element = card.find("span", class_=lambda x: x and x.startswith('sc-'))
                company = company_element.text.strip() if company_element else "N/A"
                time_element = card.find("time")
                published_at = datetime.fromisoformat(time_element['datetime'].replace('Z', '+00:00')) if time_element else None
                location = card.select_one("i[name='location'] + p").text.strip() if card.select_one("i[name='location'] + p") else "N/A"
                salary_element = card.select_one("i[name='salary'] + span")
                salary = salary_element.text.strip().replace('\xa0', ' ') if salary_element else None
                tags_list = [span.text.strip() for span in card.select("i[name='contract'] + span, i[name='remote'] + span")]
                tags = ", ".join(tags_list) if tags_list else None
                all_images = card.select("img")
                logo_url = all_images[1]['src'] if len(all_images) > 1 and all_images[1].get('src') else None

                job_data = {"title": title, "company": company, "location": location, "link": link, "source": "Welcome to the Jungle", "published_at": published_at, "salary": salary, "tags": tags, "logo_url": logo_url}
                all_jobs_data.append(job_data)
                processed_links.add(link)

    except Exception as e: print(f"Erreur lors du scraping de WTTJ : {e}")
    finally:
        if driver: driver.quit()
        
    if all_jobs_data:
        all_jobs_data.reverse()
        with app.app_context():
            new_jobs_count = 0
            for job_data in all_jobs_data:
                if save_job_to_db(job_data): new_jobs_count += 1
            db.session.commit()
        print(f"WTTJ : {new_jobs_count} nouvelle(s) offre(s) ajoutée(s).")


# --- Web3.career (avec arrêt intelligent) ---
def scrape_web3_career():
    print("\n--- Début du scraping sur Web3.career ---")
    
    NUM_PAGES_TO_SCRAPE = 10
    DUPLICATE_THRESHOLD = 10
    BASE_URL = "https://web3.career/remote-jobs?page={}"

    driver = None
    all_jobs_data = []
    stop_scraping_site = False

    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        with app.app_context():
            processed_links = {job.link for job in Job.query.filter_by(source='Web3.career').with_entities(Job.link).all()}

        for page_num in range(1, NUM_PAGES_TO_SCRAPE + 1):
            if stop_scraping_site:
                print("  [INFO] Seuil de doublons atteint. Arrêt pour Web3.career.")
                break

            current_url = BASE_URL.format(page_num)
            print(f"Web3.career : Traitement de la page {page_num}/{NUM_PAGES_TO_SCRAPE}...")
            driver.get(current_url)
            
            try:
                WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr[data-jobid]")))
            except Exception:
                print(f"Web3.career : Aucune offre sur la page {page_num}. Arrêt.")
                break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_rows = soup.select("tbody > tr[data-jobid]")
            if not job_rows: break

            consecutive_duplicates = 0
            for row in job_rows:
                link_attribute = row.get('onclick')
                if not link_attribute: continue
                link = "https://web3.career" + link_attribute.split("'")[1]

                if link in processed_links:
                    consecutive_duplicates += 1
                    if consecutive_duplicates >= DUPLICATE_THRESHOLD:
                        stop_scraping_site = True
                        break
                    continue
                
                consecutive_duplicates = 0
                
                title_element = row.find("h2")
                company_element = row.find("h3")
                if not title_element or not company_element: continue

                title = title_element.text.strip()
                company = company_element.text.strip()
                time_element = row.find("time")
                published_at = datetime.fromisoformat(time_element['datetime'].replace('Z', '+00:00')) if time_element and 'datetime' in time_element.attrs else None
                location_element = row.select_one("td.job-location-mobile a")
                location = location_element.text.strip() if location_element else "Remote"
                salary_element = row.select_one("p.text-salary")
                salary = salary_element.text.strip().replace('\n', ' ').replace('$', '$ ') if salary_element else None
                tag_elements = row.select("span.my-badge a")
                tags = ", ".join([tag.text.strip() for tag in tag_elements]) if tag_elements else None

                job_data = {"title": title, "company": company, "location": location, "link": link, "source": "Web3.career", "published_at": published_at, "salary": salary, "tags": tags}
                all_jobs_data.append(job_data)
                processed_links.add(link)

    except Exception as e: print(f"Erreur lors du scraping de Web3.career : {e}")
    finally:
        if driver: driver.quit()
        
    if all_jobs_data:
        all_jobs_data.reverse()
        with app.app_context():
            new_jobs_count = 0
            for job_data in all_jobs_data:
                if save_job_to_db(job_data): new_jobs_count += 1
            db.session.commit()
        print(f"Web3.career : {new_jobs_count} nouvelle(s) offre(s) ajoutée(s).")


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
                    
                    tag_elements = row.select(".job-tags span.category")
                    tags_list = [tag.text.strip() for tag in tag_elements]
                    tags = ", ".join(tags_list) if tags_list else None
                    
                    location_element = row.select_one("td > span.text-sm")
                    location = location_element.text.strip() if location_element else "N/A"
                    
                    if 'Remote' in tags_list and location == 'N/A':
                        location = 'Remote'

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



# --- Hellowork (avec arrêt intelligent) ---
def scrape_hellowork():
    print("\n--- Début du scraping sur Hellowork ---")
    NUM_PAGES_TO_SCRAPE = 10 
    DUPLICATE_THRESHOLD = 8
    BASE_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html?k=&st=date&c=CDI&d=w&t=Complet&p={}"
    driver = None
    all_jobs_data = []
    stop_scraping_site = False

    try:
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=137)

        with app.app_context():
            processed_links = {job.link.split('?')[0] for job in Job.query.filter_by(source='Hellowork').with_entities(Job.link).all()}

        for page_num in range(1, NUM_PAGES_TO_SCRAPE + 1):
            if stop_scraping_site:
                print("  [INFO] Seuil de doublons atteint. Arrêt pour Hellowork.")
                break
            
            current_url = BASE_URL.format(page_num)
            print(f"Hellowork : Traitement de la page {page_num}/{NUM_PAGES_TO_SCRAPE}...")
            driver.get(current_url)
            
            try: WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "hw-cc-notice-accept-btn"))).click()
            except: pass

            try: WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[data-id-storage-target='item']")))
            except Exception: print(f"Hellowork : Aucune offre sur la page {page_num}. Arrêt."); break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_cards = soup.select("li[data-id-storage-target='item']")
            if not job_cards: break
            
            consecutive_duplicates = 0
            for card in job_cards:
                title_link = card.select_one('a[data-cy="offerTitle"]')
                if not title_link: continue
                link = urllib.parse.urljoin(current_url, title_link['href']).split('?')[0]
                
                if link in processed_links:
                    consecutive_duplicates += 1
                    if consecutive_duplicates >= DUPLICATE_THRESHOLD:
                        stop_scraping_site = True; break
                    continue
                consecutive_duplicates = 0
                
                title = card.select_one("h3 p:first-of-type").text.strip()
                company = card.select_one("h3 p.tw-typo-s").text.strip()
                location = card.select_one('div[data-cy="localisationCard"]').text.strip()
                logo_url = card.select_one("header img")['src'] if card.select_one("header img") and 'http' in card.select_one("header img").get('src', '') else None
                salary = card.select_one('div[data-cy="contractCard"] + div').text.strip().replace("\xa0", " ") if card.select_one('div[data-cy="contractCard"] + div') else None
                tags = ", ".join([tag.text.strip() for tag in card.select('div[data-cy="contractCard"], div[data-cy="contractTag"]')])
                published_at = None
                date_element = card.select_one("div.tw-justify-between > div.tw-text-grey")
                if date_element:
                    date_text = date_element.text.strip().lower()
                    now = datetime.now(timezone.utc)
                    try:
                        if "instant" in date_text or "aujourd'hui" in date_text: published_at = now
                        elif "heure" in date_text: published_at = now - timedelta(hours=int(re.search(r'\d+', date_text).group()))
                        elif "hier" in date_text: published_at = now - timedelta(days=1)
                        elif "jour" in date_text: published_at = now - timedelta(days=int(re.search(r'\d+', date_text).group()))
                    except: pass
                
                job_data = { "title": title, "company": company, "location": location, "link": link, "source": "Hellowork", "published_at": published_at, "salary": salary, "tags": tags, "logo_url": logo_url }
                all_jobs_data.append(job_data)
                processed_links.add(link)
                
    except Exception as e: print(f"Erreur lors du scraping de Hellowork : {e}")
    finally:
        if driver: driver.quit()

    if all_jobs_data:
        all_jobs_data.reverse()
        with app.app_context():
            new_jobs_count = 0
            for job_data in all_jobs_data:
                if save_job_to_db(job_data): new_jobs_count += 1
            db.session.commit()
        print(f"Hellowork : {new_jobs_count} nouvelle(s) offre(s) ajoutée(s).")


# Dans scraper.py

def scrape_indeed():
    print("\n--- Début du scraping sur Indeed ---")
    
    NUM_PAGES_TO_SCRAPE = 10
    DUPLICATE_THRESHOLD = 10
    TARGET_URL = "https://fr.indeed.com/jobs?q=&l=Télétravail&sort=date&fromage=7&radius=25&sc=0kf%3Aattr%285QWDV%7C8YWGX%7CCF3CP%7CT9BXE%252COR%29%3B&from=searchOnDesktopSerp&vjk=f7a9d0a1dbbb59ed"
    driver = None
    all_jobs_data = []

    with app.app_context():
        try:
            profile_path = os.path.abspath("chrome_profile_indeed")
            if not os.path.exists(profile_path):
                print("[ERREUR] Profil Indeed non trouvé.")
                return
            
            options = uc.ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument(f'--user-data-dir={profile_path}')
            options.add_argument('--profile-directory=Default')
            options.add_argument("--window-size=1280,800")
            driver = uc.Chrome(options=options, use_subprocess=True, version_main=137)

            processed_jks = set()
            existing_indeed_jobs = Job.query.filter_by(source='Indeed').with_entities(Job.link).all()
            for job_tuple in existing_indeed_jobs:
                job_link = job_tuple[0]
                match = re.search(r'jk=([a-f0-9]+)', job_link)
                if match:
                    processed_jks.add(match.group(1))
            print(f"[INFO] {len(processed_jks)} 'jk' Indeed déjà en base de données.")
            
            stop_scraping_site = False
            for page_num in range(NUM_PAGES_TO_SCRAPE):
                if stop_scraping_site:
                    print("  [INFO] Seuil de doublons atteint. Arrêt pour Indeed.")
                    break
                
                current_url = f"{TARGET_URL}&start={page_num * 10}" if page_num > 0 else TARGET_URL
                print(f"Indeed : Traitement de la page {page_num + 1}/{NUM_PAGES_TO_SCRAPE}...")
                driver.get(current_url)
                
                time.sleep(2)
                try:
                    WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='close']"))).click()
                    time.sleep(1)
                except: pass
                
                try:
                    WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.job_seen_beacon")))
                except: break
                
                soup = BeautifulSoup(driver.page_source, "html.parser")
                job_cards = soup.select("div.job_seen_beacon")
                if not job_cards: break
                
                consecutive_duplicates = 0
                for card in job_cards:
                    link_element = card.select_one('a.jcs-JobTitle')
                    if not link_element or not link_element.has_attr('href'): continue
                    
                    link_key_match = re.search(r'jk=([a-f0-9]+)', link_element['href'])
                    if not link_key_match: continue
                    
                    job_key = link_key_match.group(1)
                    
                    # --- CORRECTION ICI ---
                    if job_key in processed_jks:
                        consecutive_duplicates += 1
                        if consecutive_duplicates >= DUPLICATE_THRESHOLD:
                            stop_scraping_site = True; break
                        continue
                    # --------------------
                    
                    consecutive_duplicates = 0
                    
                    link = f"https://fr.indeed.com/viewjob?jk={job_key}"
                    
                    title_element = card.select_one('h2.jobTitle span')
                    company_element = card.select_one('span[data-testid="company-name"]')
                    location_element = card.select_one('div[data-testid="text-location"]')
                    if not all([title_element, company_element, location_element]): continue
                    
                    title = title_element.text.strip()
                    company = company_element.text.strip()
                    location = location_element.text.strip()
                    
                    # --- Parsing complet (le reste est bon) ---
                    tag_divs = card.select("div[data-testid='attribute_snippet_testid']")
                    tag_lis = card.select("li.css-5ooe72")
                    tags_list = [div.text.strip() for div in tag_divs if div.text.strip()] + [li.text.strip() for li in tag_lis if li.text.strip()]
                    tags = ", ".join(list(dict.fromkeys(tags_list))) if tags_list else None
                    date_element = card.select_one('span.date')
                    published_at = None
                    if date_element:
                        date_text = date_element.text.strip().lower()
                        now = datetime.now(timezone.utc)
                        try:
                            if "aujourd'hui" in date_text or "instant" in date_text: published_at = now
                            elif "hier" in date_text: published_at = now - timedelta(days=1)
                            elif "jour" in date_text: published_at = now - timedelta(days=int(re.search(r'\d+', date_text).group()))
                        except: pass
                    salary_element = card.select_one('div.salary-snippet-container')
                    salary = salary_element.text.strip().replace('\xa0', ' ') if salary_element else None
                    snippet_element = card.select_one('div.job-snippet')
                    description = snippet_element.text.strip().replace('\n', ' ') if snippet_element else None

                    job_data = {"title": title, "company": company, "location": location, "link": link, "source": "Indeed", "published_at": published_at, "salary": salary, "tags": tags, "description": description}
                    all_jobs_data.append(job_data)
                    
                    # --- CORRECTION ICI ---
                    processed_jks.add(job_key)
                    # --------------------

        except Exception as e:
            print(f"Erreur majeure lors du scraping de Indeed : {e}")
        finally:
            if driver: driver.quit()

        if all_jobs_data:
            print(f"\n[INFO] {len(all_jobs_data)} offres collectées. Enregistrement...")
            all_jobs_data.reverse()
            new_jobs_count = 0
            for job_data in all_jobs_data:
                if save_job_to_db(job_data):
                    new_jobs_count += 1
            db.session.commit()
            print(f"Indeed : {new_jobs_count} nouvelle(s) offre(s) ajoutée(s).")
        else:
            print("\n[INFO] Aucune nouvelle offre trouvée pour Indeed.")


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
    scrape_glassdoor()
    scrape_indeed()
    
    print("\nScraping de tous les sites terminé !")