import re
import time

from django.conf import settings
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

from .models import Job
from .utils import parse_posted_date


def find_posted_date(driver):
    selectors = [
        '[data-automation-id="postedOn"]',
        '[data-automation-id="postedDate"]',
        '[data-automation-id="jobPostingDate"]',
        '[data-automation-id*="posted"]',
        '[data-automation-id*="date"]',
    ]
    for selector in selectors:
        for elem in driver.find_elements(By.CSS_SELECTOR, selector):
            posted_date = parse_posted_date(elem.text or elem.get_attribute('textContent'))
            if posted_date:
                return posted_date

    body_text = driver.find_element(By.TAG_NAME, 'body').text
    posted_date = parse_posted_date(body_text)
    if posted_date:
        return posted_date

    for line in body_text.splitlines():
        if 'posted' in line.lower() or 'date' in line.lower():
            posted_date = parse_posted_date(line)
            if posted_date:
                return posted_date

    return None


def _build_chrome_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    return driver


def _find_job_link_elements(driver):
    selectors = [
        'a[data-automation-id="jobTitle"]',
        'a[data-automation-id*="jobTitle"]',
        'a[data-automation-id*="job"]',
        'a[href*="/job/"]',
        'a[href*="/jobs/"]',
    ]
    seen_urls = set()
    elements = []
    for selector in selectors:
        for elem in driver.find_elements(By.CSS_SELECTOR, selector):
            href = elem.get_attribute('href')
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            elements.append(elem)
    return elements


def scrape_all_sites():
    sites = getattr(settings, 'WORKDAY_SITES', [])
    if not sites:
        print('No WORKDAY_SITES configured in settings.')
        return

    driver = _build_chrome_driver()
    try:
        seen_urls = []
        failed_sites = []
        for site in sites:
            site_urls = scrape_workday_site(driver, site)
            if site_urls:
                seen_urls.extend(site_urls)
            else:
                failed_sites.append(site.get('company', 'Workday'))

        if failed_sites:
            print(f"Skipping stale job cleanup because these sites had no results: {', '.join(failed_sites)}")
        elif seen_urls:
            Job.objects.filter(source='workday').exclude(url__in=seen_urls).delete()
    finally:
        driver.quit()


def scrape_workday_site(driver, site):
    company = site.get('company', 'Workday')
    url = site.get('url')
    if not url:
        print(f'Missing URL for site: {site}')
        return []

    print(f'Scraping Workday site: {company} ({url})')
    driver.get(url)
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')

    wait = WebDriverWait(driver, 25)
    try:
        wait.until(lambda d: len(_find_job_link_elements(d)) > 0)
    except TimeoutException:
        print(f'Timeout waiting for jobs on {company}')
        return []

    job_elements = _find_job_link_elements(driver)
    print(f'Found {len(job_elements)} job links on {company}')

    jobs_to_process = []
    for elem in job_elements[:40]:
        title = elem.text.strip()
        job_url = elem.get_attribute('href')
        location = ''
        try:
            parent = elem.find_element(By.XPATH, '..')
            loc_elem = parent.find_element(By.CSS_SELECTOR, '[data-automation-id="location"]')
            location = loc_elem.text.strip()
        except Exception:
            pass
        if job_url:
            jobs_to_process.append({
                'title': title,
                'url': job_url,
                'location': location,
                'company': company,
            })

    saved_urls = []
    for job_data in jobs_to_process:
        description = ''
        posted_date = None
        try:
            driver.get(job_data['url'])
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
            WebDriverWait(driver, 15).until(
                lambda d: len(d.find_element(By.TAG_NAME, 'body').text) > 100
            )
            description = driver.find_element(By.TAG_NAME, 'body').text[:2000]
            posted_date = find_posted_date(driver)
        except Exception as exc:
            print(f"Failed to load job page {job_data['url']}: {exc}")

        if not job_data['title']:
            job_data['title'] = job_data.get('url', 'Unknown Title')

        existing_job = Job.objects.filter(url=job_data['url']).first()
        if not posted_date and existing_job:
            posted_date = existing_job.posted_date

        job, created = Job.objects.update_or_create(
            url=job_data['url'],
            defaults={
                'title': job_data['title'],
                'company': job_data['company'],
                'location': job_data['location'],
                'posted_date': posted_date,
                'description': description,
                'source': 'workday',
            },
        )
        saved_urls.append(job.url)
        print(f"Saved job: {job.title} ({job.company})")
        time.sleep(1)

    return saved_urls
