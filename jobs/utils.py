import re
from datetime import datetime, timedelta
from urllib.parse import unquote

from django.utils import timezone


# Maps each country key to the set of tokens/phrases that identify it.
# Short entries (<=3 chars) are matched as whole uppercase tokens.
# Longer entries are matched as substrings in the normalized location text.
COUNTRY_INDICATORS = {
    'united states': {
        'tokens': {'US', 'USA'},
        'phrases': {
            'united states', 'united states of america', 'america',
            # state names
            'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
            'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
            'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
            'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota',
            'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
            'new hampshire', 'new jersey', 'new mexico', 'new york',
            'north carolina', 'north dakota', 'ohio', 'oklahoma', 'oregon',
            'pennsylvania', 'rhode island', 'south carolina', 'south dakota',
            'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington',
            'west virginia', 'wisconsin', 'wyoming', 'district of columbia',
        },
        # State codes matched as whole tokens but only when NOT the leading token
        # (leading token is typically a country code, e.g. "IN, Pune" = India)
        'state_codes': {
            'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI',
            'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI',
            'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC',
            'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT',
            'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
        },
    },
    'canada': {
        'tokens': {'CA', 'CAN'},
        'phrases': {
            'canada', 'ontario', 'quebec', 'british columbia', 'alberta',
            'manitoba', 'saskatchewan', 'nova scotia', 'new brunswick',
            'newfoundland', 'prince edward island', 'northwest territories',
            'yukon', 'nunavut',
        },
        'state_codes': set(),
    },
    'china': {'tokens': {'CN', 'CHN'}, 'phrases': {'china', 'mainland china'}, 'state_codes': set()},
    'germany': {'tokens': {'DE', 'DEU'}, 'phrases': {'germany', 'deutschland'}, 'state_codes': set()},
    'japan': {'tokens': {'JP', 'JPN'}, 'phrases': {'japan'}, 'state_codes': set()},
    'united kingdom': {'tokens': {'UK', 'GB', 'GBR'}, 'phrases': {'united kingdom', 'great britain', 'england', 'scotland', 'wales'}, 'state_codes': set()},
    'india': {'tokens': {'IN', 'IND'}, 'phrases': {'india'}, 'state_codes': set()},
    'france': {'tokens': {'FR', 'FRA'}, 'phrases': {'france'}, 'state_codes': set()},
    'italy': {'tokens': {'IT', 'ITA'}, 'phrases': {'italy', 'italia'}, 'state_codes': set()},
    'brazil': {'tokens': {'BR', 'BRA'}, 'phrases': {'brazil', 'brasil'}, 'state_codes': set()},
    'spain': {'tokens': {'ES', 'ESP'}, 'phrases': {'spain'}, 'state_codes': set()},
    'south korea': {'tokens': {'KR', 'KOR'}, 'phrases': {'south korea', 'republic of korea'}, 'state_codes': set()},
    'australia': {'tokens': {'AU', 'AUS'}, 'phrases': {'australia'}, 'state_codes': set()},
    'mexico': {'tokens': {'MX', 'MEX'}, 'phrases': {'mexico'}, 'state_codes': set()},
    'russia': {'tokens': {'RU', 'RUS'}, 'phrases': {'russia', 'russian federation'}, 'state_codes': set()},
    'turkey': {'tokens': {'TR', 'TUR'}, 'phrases': {'turkey', 'turkiye'}, 'state_codes': set()},
    'netherlands': {'tokens': {'NL', 'NLD'}, 'phrases': {'netherlands', 'holland'}, 'state_codes': set()},
    'switzerland': {'tokens': {'CH', 'CHE'}, 'phrases': {'switzerland'}, 'state_codes': set()},
    'poland': {'tokens': {'PL', 'POL'}, 'phrases': {'poland'}, 'state_codes': set()},
    'saudi arabia': {'tokens': {'SA', 'SAU'}, 'phrases': {'saudi arabia'}, 'state_codes': set()},
    'indonesia': {'tokens': {'ID', 'IDN'}, 'phrases': {'indonesia'}, 'state_codes': set()},
    'taiwan': {'tokens': {'TW', 'TWN'}, 'phrases': {'taiwan'}, 'state_codes': set()},
    'belgium': {'tokens': {'BE', 'BEL'}, 'phrases': {'belgium'}, 'state_codes': set()},
    'ireland': {'tokens': {'IE', 'IRL'}, 'phrases': {'ireland'}, 'state_codes': set()},
    'argentina': {'tokens': {'AR', 'ARG'}, 'phrases': {'argentina'}, 'state_codes': set()},
}


def normalize_location_text(location):
    return re.sub(r'[^a-z0-9]+', ' ', location or '').lower().strip()


def _get_country_keys(location):
    """Return the set of country keys that this location string matches."""
    if not location:
        return set()

    normalized = normalize_location_text(location)
    padded = f' {normalized} '
    all_tokens = re.findall(r'[A-Za-z0-9]+', location)
    upper_tokens = {t.upper() for t in all_tokens}
    # Tokens after the first — a leading token like 'IN' or 'DE' is a country code,
    # but the same code appearing later (e.g. 'Austin, TX') is a US state.
    trailing_upper = {t.upper() for t in all_tokens[1:]} if len(all_tokens) > 1 else set()

    matched = set()
    for country, indicators in COUNTRY_INDICATORS.items():
        # Check short tokens (US/USA, country ISO codes)
        if upper_tokens & indicators['tokens']:
            matched.add(country)
            continue
        # Check state codes only in non-leading position
        if indicators['state_codes'] and trailing_upper & indicators['state_codes']:
            matched.add(country)
            continue
        # Check full phrases
        for phrase in indicators['phrases']:
            if f' {phrase} ' in padded:
                matched.add(country)
                break

    return matched


def location_matches_filter(location, location_filter):
    if not location_filter:
        return True
    if not location:
        return False

    filter_keys = _get_country_keys(location_filter)
    location_keys = _get_country_keys(location)

    if filter_keys and location_keys:
        return bool(filter_keys & location_keys)

    # Fallback: plain substring match
    normalized_location = normalize_location_text(location)
    normalized_filter = normalize_location_text(location_filter)
    return f' {normalized_filter} ' in f' {normalized_location} '


def get_location_from_workday_url(url):
    match = re.search(r'/job/([^/]+)/', url or '')
    if not match:
        return ''

    location_slug = unquote(match.group(1))
    if not re.search(r'[A-Za-z]', location_slug):
        return ''

    if '---' in location_slug:
        parts = [part for part in location_slug.split('---') if part]
    else:
        parts = [location_slug]

    cleaned_parts = []
    for part in parts:
        cleaned = re.sub(r'-+', ' ', part).strip()
        if cleaned:
            cleaned_parts.append(cleaned)

    return ', '.join(cleaned_parts)


def parse_posted_date(text):
    if not text:
        return None

    today = timezone.localdate()
    clean_text = ' '.join(text.split())
    lower_text = clean_text.lower()

    if re.search(r'\b(?:posted(?:\s+on)?\s+)?today\b', lower_text) or 'just posted' in lower_text:
        return today
    if re.search(r'\b(?:posted(?:\s+on)?\s+)?yesterday\b', lower_text):
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
        r'([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2})\b',
        clean_text,
        re.IGNORECASE,
    )
    if not date_match:
        return None

    date_text = date_match.group(1)
    for date_format in ('%B %d, %Y', '%b %d, %Y', '%B %d %Y', '%b %d %Y', '%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(date_text, date_format).date()
        except ValueError:
            continue

    return None
