#!/bin/sh
set -e

python manage.py scrape_jobs --interval 43200 "$@"
python manage.py cleanup_jobs --duplicates "$@"
python manage.py cleanup_jobs --older-than-days 40 "$@"
