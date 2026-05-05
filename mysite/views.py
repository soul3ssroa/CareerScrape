import re
from urllib.parse import unquote

from django.shortcuts import render, redirect
from django.db.models import Q

from jobs.models import Job
from jobs.utils import parse_posted_date


LOCATION_FILTERS = [
    ('', 'All locations'),
    ('united_states', 'United States'),
    ('china', 'China'),
    ('germany', 'Germany'),
    ('japan', 'Japan'),
    ('united_kingdom', 'United Kingdom'),
    ('india', 'India'),
    ('france', 'France'),
    ('russia', 'Russia'),
    ('italy', 'Italy'),
    ('canada', 'Canada'),
    ('brazil', 'Brazil'),
    ('spain', 'Spain'),
    ('south_korea', 'South Korea'),
    ('australia', 'Australia'),
    ('mexico', 'Mexico'),
    ('turkey', 'Turkey'),
    ('indonesia', 'Indonesia'),
    ('netherlands', 'Netherlands'),
    ('saudi_arabia', 'Saudi Arabia'),
    ('switzerland', 'Switzerland'),
    ('poland', 'Poland'),
    ('taiwan', 'Taiwan'),
    ('belgium', 'Belgium'),
    ('ireland', 'Ireland'),
    ('argentina', 'Argentina'),
]

LOCATION_ALIASES = {
    'united_states': {
        'phrases': [
            'United States', 'United States of America', 'USA', 'U.S.', 'U.S.A.',
            'America', 'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California',
            'Colorado', 'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii',
            'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky',
            'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
            'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska',
            'Nevada', 'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
            'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
            'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
            'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
            'West Virginia', 'Wisconsin', 'Wyoming', 'District of Columbia',
            'New York City', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix',
            'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'Austin',
            'Jacksonville', 'San Jose', 'Fort Worth', 'Columbus', 'Charlotte',
            'Indianapolis', 'San Francisco', 'Seattle', 'Denver', 'Boston',
            'Detroit', 'Minneapolis', 'Atlanta', 'Miami', 'Nashville',
        ],
        'codes': [
            'US', 'USA', 'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL',
            'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
            'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM',
            'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN',
            'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
        ],
    },
    'canada': {
        'phrases': [
            'Canada', 'Ontario', 'Quebec', 'British Columbia', 'Alberta',
            'Manitoba', 'Saskatchewan', 'Nova Scotia', 'New Brunswick',
            'Newfoundland and Labrador', 'Prince Edward Island',
            'Northwest Territories', 'Yukon', 'Nunavut', 'Toronto',
            'Montreal', 'Vancouver', 'Calgary', 'Edmonton', 'Ottawa',
            'Winnipeg', 'Quebec City', 'Hamilton', 'Kitchener', 'Waterloo',
        ],
        'codes': ['CAN', 'ON', 'QC', 'BC', 'AB', 'MB', 'SK', 'NS', 'NB', 'NL', 'PE', 'NT', 'YT', 'NU'],
    },
    'china': {'phrases': ['China', 'Mainland China', 'Beijing', 'Shanghai', 'Shenzhen', 'Guangzhou'], 'codes': ['CN', 'CHN']},
    'germany': {'phrases': ['Germany', 'Deutschland', 'Berlin', 'Munich', 'Hamburg', 'Frankfurt'], 'codes': ['DE', 'DEU']},
    'japan': {'phrases': ['Japan', 'Tokyo', 'Osaka', 'Kyoto', 'Yokohama'], 'codes': ['JP', 'JPN']},
    'united_kingdom': {'phrases': ['United Kingdom', 'Great Britain', 'England', 'Scotland', 'Wales', 'Northern Ireland', 'London', 'Manchester', 'Birmingham'], 'codes': ['UK', 'GB', 'GBR']},
    'india': {'phrases': ['India', 'Bengaluru', 'Bangalore', 'Mumbai', 'Delhi', 'Hyderabad', 'Chennai', 'Pune'], 'codes': ['IN', 'IND']},
    'france': {'phrases': ['France', 'Paris', 'Lyon', 'Marseille', 'Toulouse'], 'codes': ['FR', 'FRA']},
    'russia': {'phrases': ['Russia', 'Russian Federation', 'Moscow', 'Saint Petersburg'], 'codes': ['RU', 'RUS']},
    'italy': {'phrases': ['Italy', 'Italia', 'Rome', 'Milan', 'Turin'], 'codes': ['IT', 'ITA']},
    'brazil': {'phrases': ['Brazil', 'Brasil', 'Sao Paulo', 'Rio de Janeiro', 'Brasilia'], 'codes': ['BR', 'BRA']},
    'spain': {'phrases': ['Spain', 'Espana', 'Madrid', 'Barcelona', 'Valencia'], 'codes': ['ES', 'ESP']},
    'south_korea': {'phrases': ['South Korea', 'Korea, Republic of', 'Republic of Korea', 'Seoul', 'Busan'], 'codes': ['KR', 'KOR']},
    'australia': {'phrases': ['Australia', 'Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide'], 'codes': ['AU', 'AUS']},
    'mexico': {'phrases': ['Mexico', 'Mexico City', 'Ciudad de Mexico', 'Monterrey', 'Guadalajara'], 'codes': ['MX', 'MEX']},
    'turkey': {'phrases': ['Turkey', 'Turkiye', 'Istanbul', 'Ankara'], 'codes': ['TR', 'TUR']},
    'indonesia': {'phrases': ['Indonesia', 'Jakarta', 'Surabaya'], 'codes': ['ID', 'IDN']},
    'netherlands': {'phrases': ['Netherlands', 'Holland', 'Amsterdam', 'Rotterdam'], 'codes': ['NL', 'NLD']},
    'saudi_arabia': {'phrases': ['Saudi Arabia', 'Riyadh', 'Jeddah'], 'codes': ['SA', 'SAU', 'KSA']},
    'switzerland': {'phrases': ['Switzerland', 'Zurich', 'Geneva', 'Basel'], 'codes': ['CH', 'CHE']},
    'poland': {'phrases': ['Poland', 'Warsaw', 'Krakow', 'Wroclaw'], 'codes': ['PL', 'POL']},
    'taiwan': {'phrases': ['Taiwan', 'Taipei', 'Kaohsiung'], 'codes': ['TW', 'TWN']},
    'belgium': {'phrases': ['Belgium', 'Brussels', 'Antwerp'], 'codes': ['BE', 'BEL']},
    'ireland': {'phrases': ['Ireland', 'Dublin', 'Cork'], 'codes': ['IE', 'IRL']},
    'argentina': {'phrases': ['Argentina', 'Buenos Aires', 'Cordoba'], 'codes': ['AR', 'ARG']},
}


def normalize_location(location):
    return re.sub(r'[^a-z0-9]+', ' ', location.lower()).strip()


def location_matches_filter(location, selected_location):
    if not location:
        return False

    matcher = LOCATION_ALIASES.get(selected_location)
    if not matcher:
        selected_location_name = dict(LOCATION_FILTERS).get(selected_location, '')
        matcher = {'phrases': [selected_location_name], 'codes': []}

    normalized_location = normalize_location(location)
    location_tokens = set(normalized_location.split())
    location_text = f' {normalized_location} '
    upper_location_tokens = {
        token.upper()
        for token in re.findall(r'[A-Za-z0-9]+', location)
    }

    for phrase in matcher.get('phrases', []):
        normalized_phrase = normalize_location(phrase)
        if normalized_phrase and f' {normalized_phrase} ' in location_text:
            return True

    for code in matcher.get('codes', []):
        normalized_code = normalize_location(code)
        if len(normalized_code) <= 2 and code.upper() in upper_location_tokens:
            return True
        if len(normalized_code) > 2 and normalized_code in location_tokens:
            return True

    return False


def get_location_from_workday_url(url):
    match = re.search(r'/job/([^/]+)/', url or '')
    if not match:
        return ''

    location_slug = unquote(match.group(1))
    if not re.search(r'[A-Za-z]', location_slug):
        return ''

    return location_slug.replace('-', ', ')


def get_job_location_posting(job):
    return job.location or get_location_from_workday_url(job.url)


def job_matches_location_filter(job, selected_location):
    return (
        location_matches_filter(job.location, selected_location)
        or location_matches_filter(get_location_from_workday_url(job.url), selected_location)
    )


def add_job_display_fields(jobs):
    for job in jobs:
        job.location_posting = get_job_location_posting(job)
        job.posting_date_display = job.posted_date or parse_posted_date(job.description)
    return jobs


def get_location_filter_context(selected_location=''):
    selected_location_label = dict(LOCATION_FILTERS).get(selected_location, '')
    return {
        'location_options': LOCATION_FILTERS,
        'selected_location': selected_location,
        'selected_location_label': selected_location_label,
    }


def home(request):
    return render(request, 'index.html', get_location_filter_context())


def search_jobs(request):
    if request.method == 'POST':
        query = request.POST.get('query', '').strip()
        query_slug = re.sub(r'\s+', '-', query)
        selected_location = request.POST.get('location', '').strip()
        if selected_location not in dict(LOCATION_FILTERS):
            selected_location = ''

        if not query:
            context = {
                'error': 'Please enter a job title.',
                **get_location_filter_context(selected_location),
            }
            return render(request, 'index.html', context)

        jobs = Job.objects.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(company__icontains=query)
            | Q(location__icontains=query)
            | Q(url__icontains=query)
            | Q(url__icontains=query_slug)
        )

        jobs = jobs.order_by('-posted_date', '-last_seen')

        if selected_location:
            jobs = [
                job for job in jobs
                if job_matches_location_filter(job, selected_location)
            ][:100]
        else:
            jobs = list(jobs[:100])

        jobs = add_job_display_fields(jobs)

        context = {
            'jobs': jobs,
            'query': query,
            **get_location_filter_context(selected_location),
        }
        return render(request, 'results.html', context)
    return redirect('home')
