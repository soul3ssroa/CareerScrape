from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Job


INVALID_URL_PATTERNS = [
    'community.workday.com',
    '/invalid',
    'error',
]


def delete_invalid_url_jobs():
    q = Q()
    for pattern in INVALID_URL_PATTERNS:
        q |= Q(url__icontains=pattern)
    deleted_count, _ = Job.objects.filter(q).delete()
    return deleted_count


def delete_duplicate_jobs():
    seen = set()
    duplicate_ids = []
    for job in Job.objects.order_by('title', 'company', 'id').values('id', 'title', 'company'):
        key = (job['title'].strip().lower(), job['company'].strip().lower())
        if key in seen:
            duplicate_ids.append(job['id'])
        else:
            seen.add(key)
    deleted_count, _ = Job.objects.filter(id__in=duplicate_ids).delete()
    return deleted_count


def delete_jobs_without_posted_date():
    deleted_count, _ = Job.objects.filter(posted_date__isnull=True).delete()
    return deleted_count


def delete_jobs_older_than(days=14):
    cutoff_date = timezone.localdate() - timedelta(days=days)
    deleted_count, _ = Job.objects.filter(posted_date__lt=cutoff_date).delete()
    return deleted_count


def delete_jobs_from_company(company):
    deleted_count, _ = Job.objects.filter(company__iexact=company).delete()
    return deleted_count
