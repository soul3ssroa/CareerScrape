import time
import logging

from django.core.management.base import BaseCommand

from jobs.scraper import scrape_all_sites
from jobs.cleanup import delete_duplicate_jobs, delete_jobs_older_than

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 86400  # 24 hours


class Command(BaseCommand):
    help = 'Continuously scrape jobs and remove duplicates on a loop.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=DEFAULT_INTERVAL,
            help=f'Seconds between each scrape cycle. Defaults to {DEFAULT_INTERVAL}.',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        if interval < 60:
            raise ValueError('Interval must be at least 60 seconds.')

        self.stdout.write(f'Background worker started. Interval: {interval}s.')

        while True:
            try:
                self.stdout.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] Scraping jobs...')
                scrape_all_sites()
                self.stdout.write('Scrape complete.')

                count = delete_duplicate_jobs()
                self.stdout.write(f'Removed {count} duplicate jobs.')

                count = delete_jobs_older_than(days=24)
                self.stdout.write(f'Removed {count} jobs older than 24 days.')
            except Exception as exc:
                logger.exception(f'Worker cycle failed: {exc}')

            self.stdout.write(f'Sleeping {interval}s...')
            time.sleep(interval)
