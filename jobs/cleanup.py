from datetime import timedelta

from django.utils import timezone

from .models import Job


def delete_jobs_without_posted_date():
    deleted_count, _ = Job.objects.filter(posted_date__isnull=True).delete()
    return deleted_count


def delete_jobs_older_than(days=14):
    cutoff_date = timezone.localdate() - timedelta(days=days)
    deleted_count, _ = Job.objects.filter(posted_date__lt=cutoff_date).delete()
    return deleted_count
