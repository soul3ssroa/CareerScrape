#!/bin/sh
set -e

python manage.py cleanup_jobs --invalid "$@"
python manage.py scrape_jobs --interval 21600 "$@"
python manage.py cleanup_jobs --duplicates "$@"
python manage.py cleanup_jobs --older-than-days 40 "$@"
