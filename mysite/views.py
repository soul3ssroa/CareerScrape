from django.shortcuts import render, redirect
from django.db.models import Q

from jobs.models import Job
from jobs.utils import get_location_from_workday_url, location_matches_filter, parse_posted_date


def get_job_location_posting(job):
    return job.location or get_location_from_workday_url(job.url)


def job_matches_location_filter(job, location_filter):
    return (
        location_matches_filter(job.location, location_filter)
        or location_matches_filter(get_location_from_workday_url(job.url), location_filter)
    )


def add_job_display_fields(jobs):
    for job in jobs:
        job.location_posting = get_job_location_posting(job)
        job.posting_date_display = job.posted_date or parse_posted_date(job.description)
    return jobs


def home(request):
    return render(request, 'index.html')


def search_jobs(request):
    if request.method == 'POST':
        query = request.POST.get('query', '').strip()
        location_filter = request.POST.get('location', '').strip()

        if not query:
            return render(request, 'index.html', {
                'error': 'Please enter a job title.',
                'location_filter': location_filter,
            })

        words = query.split()
        q_filter = Q()
        for word in words:
            q_filter &= (Q(title__icontains=word) | Q(description__icontains=word))

        jobs = Job.objects.filter(q_filter).order_by('-posted_date', '-last_seen')

        if location_filter:
            jobs = [
                job for job in jobs.iterator()
                if job_matches_location_filter(job, location_filter)
            ][:100]
        else:
            jobs = list(jobs[:100])

        jobs = add_job_display_fields(jobs)

        return render(request, 'results.html', {
            'jobs': jobs,
            'query': query,
            'location_filter': location_filter,
        })
    return redirect('home')
