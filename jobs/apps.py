import threading
import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class JobsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jobs'

    def ready(self):
        import os
        # Only run in the main process, not the reloader child process
        if os.environ.get('RUN_MAIN') != 'true':
            return

        from django.core.management import call_command

        def worker():
            try:
                call_command('run_worker')
            except Exception as exc:
                logger.exception(f'Background worker crashed: {exc}')

        thread = threading.Thread(target=worker, daemon=True, name='job-worker')
        thread.start()
        logger.info('Background job worker thread started.')
