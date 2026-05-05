from django.core.management.base import BaseCommand, CommandError

from jobs.cleanup import delete_jobs_older_than, delete_jobs_without_posted_date


class Command(BaseCommand):
    help = 'Delete jobs with missing or stale posting dates.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--missing-date',
            action='store_true',
            help='Delete jobs whose posting date is not listed.',
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

        if not missing_date and older_than_days is None:
            raise CommandError('Choose --missing-date, --older-than-days, or both.')

        if older_than_days is not None and older_than_days < 1:
            raise CommandError('--older-than-days must be at least 1.')

        total_deleted = 0

        if missing_date:
            deleted_count = delete_jobs_without_posted_date()
            total_deleted += deleted_count
            self.stdout.write(f'Deleted {deleted_count} jobs with no listed posting date.')

        if older_than_days is not None:
            deleted_count = delete_jobs_older_than(older_than_days)
            total_deleted += deleted_count
            self.stdout.write(f'Deleted {deleted_count} jobs older than {older_than_days} days.')

        self.stdout.write(self.style.SUCCESS(f'Cleanup completed. Deleted {total_deleted} jobs.'))
