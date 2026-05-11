from django.core.management.base import BaseCommand, CommandError

from jobs.cleanup import delete_duplicate_jobs, delete_invalid_url_jobs, delete_jobs_from_company, delete_jobs_older_than, delete_jobs_without_posted_date


class Command(BaseCommand):
    help = 'Delete jobs with missing or stale posting dates.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company',
            type=str,
            default=None,
            help='Delete all jobs from a specific company (case-insensitive).',
        )
        parser.add_argument(
            '--invalid-urls',
            action='store_true',
            help='Delete jobs with invalid or unreachable URLs (e.g. community.workday.com).',
        )
        parser.add_argument(
            '--missing-date',
            action='store_true',
            help='Delete jobs whose posting date is not listed.',
        )
        parser.add_argument(
            '--duplicates',
            action='store_true',
            help='Delete duplicate jobs (same title and company, keeps first occurrence).',
        )
        parser.add_argument(
            '--older-than-days',
            type=int,
            default=None,
            help='Delete jobs posted more than this many days ago.',
        )

    def handle(self, *args, **options):
        missing_date = options['missing_date']
        older_than_days = options['older_than_days']
        duplicates = options['duplicates']
        invalid_urls = options['invalid_urls']
        company = options['company']

        if not missing_date and older_than_days is None and not duplicates and not invalid_urls and not company:
            raise CommandError('Choose at least one option.')

        if older_than_days is not None and older_than_days < 1:
            raise CommandError('--older-than-days must be at least 1.')

        total_deleted = 0

        if company:
            deleted_count = delete_jobs_from_company(company)
            total_deleted += deleted_count
            self.stdout.write(f'Deleted {deleted_count} jobs from "{company}".')

        if invalid_urls:
            deleted_count = delete_invalid_url_jobs()
            total_deleted += deleted_count
            self.stdout.write(f'Deleted {deleted_count} jobs with invalid URLs.')

        if duplicates:
            deleted_count = delete_duplicate_jobs()
            total_deleted += deleted_count
            self.stdout.write(f'Deleted {deleted_count} duplicate jobs.')

        if missing_date:
            deleted_count = delete_jobs_without_posted_date()
            total_deleted += deleted_count
            self.stdout.write(f'Deleted {deleted_count} jobs with no listed posting date.')

        if older_than_days is not None:
            deleted_count = delete_jobs_older_than(older_than_days)
            total_deleted += deleted_count
            self.stdout.write(f'Deleted {deleted_count} jobs older than {older_than_days} days.')

        self.stdout.write(self.style.SUCCESS(f'Cleanup completed. Deleted {total_deleted} jobs.'))
