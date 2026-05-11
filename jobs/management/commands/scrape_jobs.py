import time

from django.core.management.base import BaseCommand

from jobs.scraper import scrape_all_sites


class Command(BaseCommand):
    help = 'Scrape configured Workday sites and persist jobs to the database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Run forever, scraping again after each interval.',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=3600,
            help='Seconds to wait between continuous scrape runs. Defaults to 3600.',
        )
        parser.add_argument(
            '--location',
            default=None,
            help='Only save jobs whose location contains this text, case-insensitive.',
        )
        parser.add_argument(
            '--source',
            default=None,
            choices=['workday', 'jobvite', 'greenhouse'],
            help='Only scrape from this platform. Omit to scrape all.',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        location = options['location']
        source = options['source']
        if interval < 60:
            raise ValueError('The scrape interval must be at least 60 seconds.')

        while True:
            started_at = time.strftime('%Y-%m-%d %H:%M:%S')
            self.stdout.write(f'Starting job scrape at {started_at}.')
            scrape_all_sites(location_filter=location, source=source)
            self.stdout.write(self.style.SUCCESS('Job scrape completed.'))

            if not options['continuous']:
                break

            self.stdout.write(f'Waiting {interval} seconds before the next scrape.')
            time.sleep(interval)
