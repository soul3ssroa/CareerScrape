from django.shortcuts import render, redirect
from django.db.models import Q
from django.conf import settings
from datetime import date, timedelta

from jobs.models import Job
from jobs.utils import get_location_from_workday_url, location_matches_filter, parse_posted_date


def get_job_location_posting(job):
    return job.location or get_location_from_workday_url(job.url)


def job_matches_location_filter(job, location_filter):
    return (
        location_matches_filter(job.location, location_filter)
        or location_matches_filter(get_location_from_workday_url(job.url), location_filter)
    )


def job_matches_date_filter(job, date_posted, today):
    if not date_posted:
        return True
    d = job.posted_date or parse_posted_date(job.description)
    if date_posted == 'not listed':
        return d is None
    if d is None:
        return False
    if date_posted == 'today':
        return d >= today
    if date_posted == 'week':
        return d >= today - timedelta(days=7)
    if date_posted == 'month':
        return d >= today - timedelta(days=30)
    return True


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


def home(request):
    return render(request, 'index.html', {'companies': _all_companies()})


def search_jobs(request):
    if request.method == 'POST':
        query = request.POST.get('query', '').strip()
        location_filter = request.POST.get('location', '').strip()
        company_filter = request.POST.get('company', '').strip()
        date_posted = request.POST.get('date_posted', '').strip()

        if not query:
            return render(request, 'index.html', {
                'error': 'Please enter a job title.',
                'location_filter': location_filter,
                'company_filter': company_filter,
                'date_posted': date_posted,
                'companies': _all_companies(),
            })

        words = query.split()
        q_filter = Q(title__icontains=query) | Q(description__icontains=query)
        for word in words:
            q_filter &= (Q(title__icontains=word) | Q(description__icontains=word))
        if company_filter:
            q_filter &= Q(company__iexact=company_filter)

        jobs = Job.objects.filter(q_filter).order_by('-posted_date', '-last_seen')

        needs_python_filter = bool(location_filter or date_posted)
        if needs_python_filter:
            today = date.today()
            jobs = [
                job for job in jobs.iterator()
                if job_matches_location_filter(job, location_filter)
                and job_matches_date_filter(job, date_posted, today)
            ][:100]
        else:
            jobs = list(jobs[:100])

        jobs = add_job_display_fields(jobs)

        return render(request, 'results.html', {
            'jobs': jobs,
            'query': query,
            'location_filter': location_filter,
            'company_filter': company_filter,
            'date_posted': date_posted,
            'companies': _all_companies(),
        })
    return redirect('home')
