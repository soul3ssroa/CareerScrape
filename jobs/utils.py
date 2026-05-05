import re
from datetime import datetime, timedelta

from django.utils import timezone


def parse_posted_date(text):
    if not text:
        return None

    today = timezone.localdate()
    clean_text = ' '.join(text.split())
    lower_text = clean_text.lower()

    if re.search(r'\bposted(?:\s+on)?\s+today\b', lower_text) or 'just posted' in lower_text:
        return today
    if re.search(r'\bposted(?:\s+on)?\s+yesterday\b', lower_text):
        return today - timedelta(days=1)

    relative_match = re.search(r'(?:posted\s+)?(\d+)\+?\s+(day|week|month)s?\s+ago', lower_text)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        days = amount
        if unit == 'week':
            days = amount * 7
        elif unit == 'month':
            days = amount * 30
        return today - timedelta(days=days)

    date_match = re.search(
        r'\b(?:posted(?:\s+on)?|date\s+posted|posting\s+date)?\s*'
        r'([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2})\b',
        clean_text,
        re.IGNORECASE,
    )
    if not date_match:
        return None

    date_text = date_match.group(1)
    for date_format in ('%B %d, %Y', '%b %d, %Y', '%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(date_text, date_format).date()
        except ValueError:
            continue

    return None
