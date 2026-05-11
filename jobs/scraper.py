import re
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

from bs4 import BeautifulSoup

from .models import Job
from .utils import get_location_from_workday_url, location_matches_filter, parse_posted_date


DEFAULT_JOBS_PER_SITE = 40
FILTERED_JOBS_PER_SITE = 40
MAX_LISTING_LOAD_ATTEMPTS = 30
API_PAGE_SIZE = 20
API_MAX_PAGES = 500


def _job_matches_location(location, location_filter):
    return location_matches_filter(location, location_filter)


def _site_api_parts(site_url):
    parsed = urlparse(site_url)
    if not parsed.netloc:
        return None

    tenant = parsed.netloc.split('.')[0]
    path_parts = [part for part in parsed.path.split('/') if part]
    if path_parts and re.fullmatch(r'[a-z]{2}-[A-Z]{2}', path_parts[0]):
        path_parts = path_parts[1:]
    if not path_parts:
        return None

    return parsed.scheme, parsed.netloc, tenant, path_parts[0]


def _api_json(url, payload=None):
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0',
    }
    data = None
    method = 'GET'
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        method = 'POST'

    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode('utf-8'))


def _first_value(data, keys):
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if value not in (None, '', []):
                return value
        for value in data.values():
            found = _first_value(value, keys)
            if found not in (None, '', []):
                return found
    elif isinstance(data, list):
        for item in data:
            found = _first_value(item, keys)
            if found not in (None, '', []):
                return found
    return None


def _text_value(value):
    if value in (None, '', []):
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_text_value(item) for item in value]
        return ', '.join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ('descriptor', 'displayName', 'name', 'label', 'text', 'value'):
            text = _text_value(value.get(key))
            if text:
                return text
        parts = [_text_value(item) for item in value.values()]
        return ', '.join(part for part in parts if part)
    return str(value).strip()


def _posted_date_from_api(data):
    value = _first_value(data, ('postedOn', 'postedDate', 'jobPostingDate', 'startDate'))
    return parse_posted_date(_text_value(value))


def _location_from_api(data):
    value = _first_value(data, (
        'locationsText',
        'location',
        'locations',
        'primaryLocation',
        'jobLocation',
        'country',
    ))
    return _text_value(value)


def _description_from_api(data):
    value = _first_value(data, ('jobDescription', 'description', 'jobDescriptionText'))
    return _text_value(value)[:100000]


def _title_from_api(data):
    return _text_value(_first_value(data, ('title', 'jobTitle', 'postingTitle'))) or 'Unknown Title'


def _external_path_from_api(data):
    return _text_value(_first_value(data, ('externalPath', 'path')))


def _detail_api_url(api_base, external_path):
    path = external_path.strip()
    if not path:
        return ''
    if path.startswith('/'):
        path = path[1:]
    if not path.startswith('job/'):
        path = f'job/{path}'
    return f'{api_base}/{path}'


def _public_job_url(site_url, external_path):
    if not external_path:
        return site_url
    return urljoin(site_url.rstrip('/') + '/', external_path.lstrip('/'))


def _save_job(job_data):
    existing_job = Job.objects.filter(url=job_data['url']).first()
    posted_date = job_data['posted_date']
    if not posted_date and existing_job:
        posted_date = existing_job.posted_date

    job, created = Job.objects.update_or_create(
        url=job_data['url'],
        defaults={
            'title': job_data['title'],
            'company': job_data['company'],
            'location': job_data['location'],
            'posted_date': posted_date,
            'description': job_data['description'],
            'source': 'workday',
        },
    )
    print(f"Saved job: {job.title} ({job.company})")
    return job.url


def scrape_workday_site_api(site, location_filter=None):
    company = site.get('company', 'Workday')
    site_url = site.get('url')
    api_parts = _site_api_parts(site_url)
    if not api_parts:
        return None

    scheme, netloc, tenant, site_name = api_parts
    api_base = f'{scheme}://{netloc}/wday/cxs/{tenant}/{site_name}'
    target_job_count = FILTERED_JOBS_PER_SITE if location_filter else DEFAULT_JOBS_PER_SITE
    saved_urls = []
    seen_urls = set()
    scanned_count = 0
    skipped_count = 0

    print(f'Scraping Workday API: {company} ({api_base})')
    for page in range(API_MAX_PAGES):
        offset = page * API_PAGE_SIZE
        try:
            search_data = _api_json(
                f'{api_base}/jobs',
                {
                    'appliedFacets': {},
                    'limit': API_PAGE_SIZE,
                    'offset': offset,
                    'searchText': '',
                },
            )
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f'Workday API failed for {company}: {exc}')
            return None

        postings = search_data.get('jobPostings') or search_data.get('jobs') or []
        if not postings:
            break

        for posting in postings:
            scanned_count += 1
            external_path = _external_path_from_api(posting)
            job_url = _public_job_url(site_url, external_path)
            if not job_url or job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            detail_data = {}
            detail_api_url = _detail_api_url(api_base, external_path)
            if detail_api_url:
                try:
                    detail_data = _api_json(detail_api_url)
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                    print(f'Could not load Workday detail API for {job_url}: {exc}')

            location = _location_from_api(detail_data) or _location_from_api(posting)
            if not location:
                location = get_location_from_workday_url(job_url)

            posted_date = _posted_date_from_api(detail_data) or _posted_date_from_api(posting)
            description = _description_from_api(detail_data) or _description_from_api(posting)
            title = _title_from_api(detail_data) or _title_from_api(posting)

            if not _job_matches_location(location, location_filter):
                skipped_count += 1
                print(
                    f"Skipped job outside location filter '{location_filter}': "
                    f"{title} ({location or 'No location listed'})"
                )
                continue

            saved_urls.append(_save_job({
                'title': title,
                'url': job_url,
                'location': location,
                'posted_date': posted_date,
                'description': description,
                'company': company,
            }))

            if len(saved_urls) >= target_job_count:
                print(
                    f'{company} summary: scanned {scanned_count}, '
                    f'saved {len(saved_urls)}, skipped {skipped_count}.'
                )
                return saved_urls

        if len(postings) < API_PAGE_SIZE:
            break

    print(
        f'{company} summary: scanned {scanned_count}, '
        f'saved {len(saved_urls)}, skipped {skipped_count}.'
    )
    return saved_urls


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


def find_posted_date_near_listing(elem):
    selectors = [
        '[data-automation-id="postedOn"]',
        '[data-automation-id="postedDate"]',
        '[data-automation-id="jobPostingDate"]',
        '[data-automation-id*="posted"]',
        '[data-automation-id*="date"]',
    ]
    containers = [elem]
    for xpath in ('..', '../..', '../../..'):
        try:
            containers.append(elem.find_element(By.XPATH, xpath))
        except Exception:
            pass

    for container in containers:
        for selector in selectors:
            for date_elem in container.find_elements(By.CSS_SELECTOR, selector):
                posted_date = parse_posted_date(date_elem.text or date_elem.get_attribute('textContent'))
                if posted_date:
                    return posted_date

        posted_date = parse_posted_date(container.text or container.get_attribute('textContent'))
        if posted_date:
            return posted_date

    return None


def _nearby_containers(elem):
    containers = [elem]
    for xpath in ('..', '../..', '../../..', '../../../..'):
        try:
            containers.append(elem.find_element(By.XPATH, xpath))
        except Exception:
            pass
    return containers


def find_location_near_listing(elem):
    selectors = [
        '[data-automation-id="location"]',
        '[data-automation-id="locations"]',
        '[data-automation-id="jobLocation"]',
        '[data-automation-id="primaryLocation"]',
        '[data-automation-id*="location"]',
    ]
    for container in _nearby_containers(elem):
        for selector in selectors:
            for loc_elem in container.find_elements(By.CSS_SELECTOR, selector):
                location = (loc_elem.text or loc_elem.get_attribute('textContent') or '').strip()
                if location:
                    return location
    return ''


def find_location_on_detail_page(driver):
    selectors = [
        '[data-automation-id="locations"]',
        '[data-automation-id="location"]',
        '[data-automation-id="jobLocation"]',
        '[data-automation-id="primaryLocation"]',
        '[data-automation-id*="location"]',
    ]
    for selector in selectors:
        for elem in driver.find_elements(By.CSS_SELECTOR, selector):
            location = (elem.text or elem.get_attribute('textContent') or '').strip()
            if location:
                return location
    return ''


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


def _load_more_job_links(driver, current_count):
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
    time.sleep(1)
    if len(_find_job_link_elements(driver)) > current_count:
        return True

    button_xpaths = [
        '//button[@data-automation-id="loadMoreJobs"]',
        '//button[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "more")]',
        '//button[contains(translate(@aria-label, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "more")]',
    ]
    for xpath in button_xpaths:
        buttons = driver.find_elements(By.XPATH, xpath)
        for button in buttons:
            if not button.is_displayed() or not button.is_enabled():
                continue
            try:
                driver.execute_script('arguments[0].scrollIntoView({block: "center"});', button)
                button.click()
                WebDriverWait(driver, 10).until(
                    lambda d: len(_find_job_link_elements(d)) > current_count
                )
                return True
            except Exception:
                continue

    return len(_find_job_link_elements(driver)) > current_count


def _fetch_html(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8', errors='replace')


def _save_job_source(job_data, source):
    existing = Job.objects.filter(url=job_data['url']).first()
    posted_date = job_data['posted_date']
    if not posted_date and existing:
        posted_date = existing.posted_date
    job, _ = Job.objects.update_or_create(
        url=job_data['url'],
        defaults={
            'title': job_data['title'],
            'company': job_data['company'],
            'location': job_data['location'],
            'posted_date': posted_date,
            'description': job_data['description'],
            'source': source,
        },
    )
    print(f"Saved job: {job.title} ({job.company})")
    return job.url


def _jobvite_base_url(site_url):
    """Return the base jobs listing URL, normalising /job/ paths to /jobs."""
    parsed = urlparse(site_url)
    # e.g. /tylertech/job  ->  /tylertech/jobs
    path = re.sub(r'/job(/.*)?$', '/jobs', parsed.path)
    return f'{parsed.scheme}://{parsed.netloc}{path}'


def scrape_jobvite_site(site, location_filter=None):
    company = site.get('company', 'Jobvite')
    site_url = site.get('url')
    listing_url = _jobvite_base_url(site_url)
    parsed = urlparse(listing_url)
    url_base = f'{parsed.scheme}://{parsed.netloc}'

    print(f'Scraping Jobvite: {company} ({listing_url})')
    try:
        html = _fetch_html(listing_url)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f'Jobvite fetch failed for {company}: {exc}')
        return []

    soup = BeautifulSoup(html, 'html.parser')
    saved_urls = []

    # Each job is a <tr> inside a <table class="jv-job-list">
    for row in soup.select('table.jv-job-list tr'):
        title_el = row.select_one('td.jv-job-list-name a')
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get('href', '')
        job_url = href if href.startswith('http') else url_base + href

        loc_el = row.select_one('td.jv-job-list-location')
        location = ' '.join(loc_el.get_text().split()) if loc_el else ''

        # Fetch detail page for description (and richer location if listing says "N Locations")
        description = ''
        posted_date = None
        try:
            detail_html = _fetch_html(job_url)
            detail_soup = BeautifulSoup(detail_html, 'html.parser')
            # Extract datePosted from JSON-LD if present
            ld_tag = detail_soup.find('script', type='application/ld+json')
            if ld_tag:
                try:
                    ld = json.loads(ld_tag.string or '')
                    posted_date = parse_posted_date(ld.get('datePosted', ''))
                except (json.JSONDecodeError, AttributeError):
                    pass
            meta_el = detail_soup.select_one('p.jv-job-detail-meta')
            if meta_el and (not location or 'location' in location.lower()):
                for br in meta_el.find_all('br'):
                    br.decompose()
                location = ' '.join(meta_el.get_text().split()).split('Salary:')[0].strip()
            desc_el = detail_soup.select_one('div.jv-job-detail-description')
            description = desc_el.get_text(' ', strip=True)[:100000] if desc_el else ''
        except Exception as exc:
            print(f'Jobvite detail fetch failed for {job_url}: {exc}')

        if not _job_matches_location(location, location_filter):
            print(f"Skipped '{location_filter}' filter: {title} ({location or 'No location'})")
            continue

        saved_urls.append(_save_job_source({
            'title': title or 'Unknown Title',
            'url': job_url,
            'location': location,
            'posted_date': posted_date,
            'description': description,
            'company': company,
        }, 'jobvite'))

    print(f'{company}: saved {len(saved_urls)} jobs.')
    return saved_urls


def scrape_greenhouse_site(site, location_filter=None):
    company = site.get('company', 'Greenhouse')
    site_url = site.get('url')
    # Greenhouse exposes a JSON API at the same path
    parsed = urlparse(site_url)
    board_token = parsed.path.strip('/').split('/')[-1]
    api_url = f'https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true'
    print(f'Scraping Greenhouse: {company} ({api_url})')
    try:
        data = _api_json(api_url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f'Greenhouse API failed for {company}: {exc}')
        return []

    saved_urls = []
    for job in data.get('jobs', []):
        title = job.get('title', 'Unknown Title')
        job_url = job.get('absolute_url', '')
        if not job_url:
            continue

        location = (job.get('location') or {}).get('name', '')
        posted_date = parse_posted_date(job.get('first_published', '') or job.get('updated_at', ''))

        content = job.get('content', '')
        description = re.sub(r'<[^>]+>', ' ', content).strip()[:100000] if content else ''

        if not _job_matches_location(location, location_filter):
            print(f"Skipped '{location_filter}' filter: {title} ({location or 'No location'})")
            continue

        saved_urls.append(_save_job_source({
            'title': title,
            'url': job_url,
            'location': location,
            'posted_date': posted_date,
            'description': description,
            'company': company,
        }, 'greenhouse'))

    print(f'{company}: saved {len(saved_urls)} jobs.')
    return saved_urls


def scrape_all_sites(location_filter=None, source=None):
    workday_sites = getattr(settings, 'WORKDAY_SITES', []) if source in (None, 'workday') else []
    jobvite_sites = getattr(settings, 'JOBVITE_SITES', []) if source in (None, 'jobvite') else []
    greenhouse_sites = getattr(settings, 'GREENHOUSE_SITES', []) if source in (None, 'greenhouse') else []

    seen_urls = []
    failed_sites = []
    selenium_driver = None

    try:
        for site in workday_sites:
            site_urls = scrape_workday_site_api(site, location_filter=location_filter)
            if site_urls is None:
                if selenium_driver is None:
                    selenium_driver = _build_chrome_driver()
                site_urls = scrape_workday_site(selenium_driver, site, location_filter=location_filter)
            if site_urls:
                seen_urls.extend(site_urls)
            else:
                failed_sites.append(site.get('company', 'Workday'))
    finally:
        if selenium_driver is not None:
            selenium_driver.quit()

    for site in jobvite_sites:
        site_urls = scrape_jobvite_site(site, location_filter=location_filter)
        seen_urls.extend(site_urls or [])

    for site in greenhouse_sites:
        site_urls = scrape_greenhouse_site(site, location_filter=location_filter)
        seen_urls.extend(site_urls or [])

    if location_filter:
        print('Skipping stale job cleanup because a location filter was used.')
    elif failed_sites:
        print(f"Skipping stale job cleanup because these sites had no results: {', '.join(failed_sites)}")
    elif seen_urls:
        Job.objects.exclude(url__in=seen_urls).delete()


def scrape_workday_site(driver, site, location_filter=None):
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

    target_job_count = FILTERED_JOBS_PER_SITE if location_filter else DEFAULT_JOBS_PER_SITE
    jobs_to_process = []
    scanned_urls = set()
    load_attempts = 0

    while len(jobs_to_process) < target_job_count:
        job_elements = _find_job_link_elements(driver)

        for elem in job_elements:
            if len(jobs_to_process) >= target_job_count:
                break

            title = elem.text.strip()
            job_url = elem.get_attribute('href')
            if not job_url or job_url in scanned_urls:
                continue

            scanned_urls.add(job_url)
            location = find_location_near_listing(elem)
            posted_date = find_posted_date_near_listing(elem)
            if not location:
                location = get_location_from_workday_url(job_url)

            jobs_to_process.append({
                'title': title,
                'url': job_url,
                'location': location,
                'posted_date': posted_date,
                'company': company,
            })

        if len(jobs_to_process) >= target_job_count:
            break
        if not location_filter:
            break
        if load_attempts >= MAX_LISTING_LOAD_ATTEMPTS:
            print(f'Stopped looking for more {location_filter} jobs after {load_attempts} load attempts.')
            break

        current_count = len(job_elements)
        if not _load_more_job_links(driver, current_count):
            print(f'No more job listings loaded for {company}.')
            break

        load_attempts += 1
        print(
            f'Loaded more listings for {company}; '
            f'{len(jobs_to_process)} matching jobs queued so far.'
        )

    if location_filter:
        print(f'Queued {len(jobs_to_process)} {location_filter} jobs for {company}.')

    saved_urls = []
    for job_data in jobs_to_process:
        description = ''
        posted_date = job_data['posted_date']
        try:
            driver.get(job_data['url'])
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
            WebDriverWait(driver, 15).until(
                lambda d: len(d.find_element(By.TAG_NAME, 'body').text) > 100
            )
            description = driver.find_element(By.TAG_NAME, 'body').text[:20000]
            if not posted_date:
                posted_date = find_posted_date(driver)
            if not job_data['location']:
                job_data['location'] = find_location_on_detail_page(driver)
            if not job_data['location']:
                job_data['location'] = get_location_from_workday_url(job_data['url'])
        except Exception as exc:
            print(f"Failed to load job page {job_data['url']}: {exc}")

        if not _job_matches_location(job_data['location'], location_filter):
            print(
                f"Skipped job outside location filter '{location_filter}': "
                f"{job_data['title']} ({job_data['location'] or 'No location listed'})"
            )
            continue

        if not job_data['title']:
            job_data['title'] = job_data.get('url', 'Unknown Title')

        saved_urls.append(_save_job({
            'title': job_data['title'],
            'url': job_data['url'],
            'location': job_data['location'],
            'posted_date': posted_date,
            'description': description,
            'company': job_data['company'],
        }))
        time.sleep(1)

    return saved_urls
