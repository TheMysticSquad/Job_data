import requests
from bs4 import BeautifulSoup
import re
import spacy
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import pandas as pd
import sqlalchemy
from sqlalchemy import create_engine, text
import pymysql
from webdriver_manager.chrome import ChromeDriverManager

# Ensure the spaCy model is installed
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    from spacy.cli import download
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

def get_career_page_url(company_name):
    search_url = f"https://www.google.com/search?q={company_name}+careers"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    response = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract the first search result link
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and 'url?q=' in href and 'webcache' not in href:
            return href.split('url?q=')[1].split('&')[0]
    return None

def scrape_career_page(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    return soup.get_text()

def extract_emails(text):
    # Use regex to find email addresses
    email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    emails = email_pattern.findall(text)
    
    # Filter emails containing 'career' or 'jobs'
    career_emails = [email for email in emails if 'career' in email or 'jobs' in email]
    
    return career_emails

# URL for the LinkedIn job search
url1 = 'https://www.linkedin.com/jobs/search/?currentJobId=3888758940&distance=25.0&geoId=105556991&keywords=data%20analyst%20intern&origin=HISTORY'

# Setting up Chrome options for headless mode
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Initialize the WebDriver with headless options using WebDriverManager
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)

# Open the URL
driver.get(url1)

try:
    # Wait until the job count element is visible
    job_count_element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, 'results-context-header__job-count'))
    )
    job_count_text = job_count_element.text.replace(',', '')
    job_count = int(re.search(r'\d+', job_count_text).group())

    # Extract company names
    companyname = driver.execute_script("""
        const elements = document.querySelectorAll('.base-search-card__subtitle');
        const companynames = [];
        for (const element of elements) {
            companynames.push(element.textContent.trim());
        }
        return companynames;
    """)

    # Extract job titles
    titlename = driver.execute_script("""
        const elements = document.querySelectorAll('.base-search-card__title');
        const titlenames = [];
        for (const element of elements) {
            titlenames.push(element.textContent.trim());
        }
        return titlenames;
    """)

    # Extract job locations
    locationname = driver.execute_script("""
        const elements = document.querySelectorAll('.job-search-card__location');
        const locationnames = [];
        for (const element of elements) {
            locationnames.push(element.textContent.trim());
        }
        return locationnames;
    """)

    # Extract career emails
    career_emails = []
    for company in companyname:
        career_url = get_career_page_url(company)
        if career_url:
            page_text = scrape_career_page(career_url)
            emails = extract_emails(page_text)
            career_emails.append(', '.join(emails) if emails else None)
        else:
            career_emails.append(None)

    # Create DataFrame
    df = pd.DataFrame({'company': companyname, 'title': titlename, 'location': locationname, 'career_email': career_emails})
    print(df)

finally:
    driver.quit()

# Database connection details
db_url = 'mysql+pymysql://avnadmin:AVNS_skZtmn9k8mHNYHMTSxf@mysql-26219722-abhinandanroy165-e599.l.aivencloud.com:20585/defaultdb'
engine = create_engine(db_url)

# Create a connection object
with engine.connect() as connection:
    # Check if the "Location" and "CareerEmail" columns exist in the "jobs" table
    result = connection.execute(text("SHOW COLUMNS FROM jobs LIKE 'Location'"))
    if result.fetchone() is None:
        # Create the column "Location" in the table "jobs"
        connection.execute(text("""
            ALTER TABLE jobs
            ADD COLUMN Location VARCHAR(255)
        """))
    
    result = connection.execute(text("SHOW COLUMNS FROM jobs LIKE 'CareerEmail'"))
    if result.fetchone() is None:
        # Create the column "CareerEmail" in the table "jobs"
        connection.execute(text("""
            ALTER TABLE jobs
            ADD COLUMN CareerEmail VARCHAR(255)
        """))

    # Insert new data only if it doesn't already exist
    for index, row in df.iterrows():
        # Check if the job entry already exists
        existing_job = connection.execute(text("""
            SELECT * FROM jobs WHERE title = :title AND company = :company
        """), {'title': row['title'], 'company': row['company']}).fetchone()

        if existing_job is None:
            # Insert the new job entry
            connection.execute(text("""
                INSERT INTO jobs (title, company, location, CareerEmail)
                VALUES (:title, :company, :location, :CareerEmail)
            """), {'title': row['title'], 'company': row['company'], 'location': row['location'], 'CareerEmail': row['career_email']})

    print("New data inserted successfully")

    # Read the data back to verify
    df_2 = pd.read_sql('jobs', connection)
    print(df_2)
