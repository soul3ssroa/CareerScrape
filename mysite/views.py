import logging
from django.shortcuts import render, redirect
from django.db.models import Q
from django.conf import settings
from django.core.paginator import Paginator
from datetime import date, timedelta

from jobs.models import Job
from jobs.utils import (
    COUNTRY_CHOICES,
    US_STATE_CHOICES,
    get_location_from_workday_url,
    location_matches_filter,
    parse_posted_date,
)

logger = logging.getLogger(__name__)


def get_job_location_posting(job):
    return job.location or get_location_from_workday_url(job.url)



def add_job_display_fields(jobs):
    for job in jobs:
        job.location_posting = get_job_location_posting(job)
        job.posting_date_display = job.posted_date or parse_posted_date(job.description)
    return jobs


def _all_companies():
    sources = [
        getattr(settings, 'WORKDAY_SITES', []),
        getattr(settings, 'JOBVITE_SITES', []),
        getattr(settings, 'GREENHOUSE_SITES', []),
        getattr(settings, 'LEVER_SITES', []),
        getattr(settings, 'ASHBY_SITES', []),
    ]
    seen = set()
    companies = []
    for site_list in sources:
        for site in site_list:
            name = site.get('company', '')
            if name and name not in seen:
                seen.add(name)
                companies.append(name)
    return sorted(companies)


def _filter_options():
    return {
        'companies': _all_companies(),
        'countries': COUNTRY_CHOICES,
        'states': US_STATE_CHOICES,
    }


def home(request):
    return render(request, 'index.html', _filter_options())


def search_jobs(request):
    if request.method == 'POST':
        params = request.POST
    elif request.GET.get('query'):
        params = request.GET
    else:
        return redirect('home')

    query = params.get('query', '').strip()
    location_filter = params.get('location', '').strip()
    company_filter = params.get('company', '').strip()
    date_posted = params.get('date_posted', '').strip()
    exclude_tags = [t.strip() for t in params.get('exclude_tags', '').split(',') if t.strip()]

    if not query:
        return render(request, 'index.html', {
            'error': 'Please enter a job title.',
            'location_filter': location_filter,
            'company_filter': company_filter,
            'date_posted': date_posted,
            'exclude_tags': params.get('exclude_tags', ''),
            **_filter_options(),
        })

    words = query.split()

    def keyword_filter(word):
        return (
            Q(title__icontains=word)
            | Q(description__icontains=word)
            | Q(location__icontains=word)
            | Q(url__icontains=word)
        )

    q_filter = keyword_filter(words[0])
    for word in words[1:]:
        q_filter &= keyword_filter(word)
    if company_filter:
        q_filter &= Q(company__iexact=company_filter)

    today = date.today()
    if date_posted == 'today':
        q_filter &= Q(posted_date__gte=today)
    elif date_posted == '3days':
        q_filter &= Q(posted_date__gte=today - timedelta(days=3))
    elif date_posted == 'week':
        q_filter &= Q(posted_date__gte=today - timedelta(days=7))
    elif date_posted == '2weeks':
        q_filter &= Q(posted_date__gte=today - timedelta(days=14))
    elif date_posted == 'month':
        q_filter &= Q(posted_date__gte=today - timedelta(days=30))
    elif date_posted == 'not listed':
        q_filter &= Q(posted_date__isnull=True)
    else:
        q_filter &= Q(posted_date__isnull=False)

    if exclude_tags:
        for tag in exclude_tags:
            q_filter &= ~Q(title__icontains=tag) & ~Q(description__icontains=tag)

    try:
        jobs = Job.objects.filter(q_filter).order_by('-posted_date', '-last_seen')
        list(jobs[:1])  # test DB connection early
    except Exception as e:
        logger.exception('Database error during job search: %s', e)
        return render(request, 'index.html', {
            'error': 'A database error occurred. Please try again later.',
            **_filter_options(),
        })

    all_jobs = list(jobs.only('title', 'company', 'location', 'url', 'posted_date', 'description'))

    if location_filter:
        all_jobs = [
            job for job in all_jobs
            if location_matches_filter(
                job.location or get_location_from_workday_url(job.url), location_filter
            )
        ]

    paginator = Paginator(all_jobs, 30)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    add_job_display_fields(page_obj.object_list)

    return render(request, 'results.html', {
        'page_obj': page_obj,
        'query': query,
        'location_filter': location_filter,
        'company_filter': company_filter,
        'date_posted': date_posted,
        'exclude_tags': params.get('exclude_tags', ''),
        **_filter_options(),
    })
