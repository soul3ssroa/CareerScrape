import re
from datetime import datetime, timedelta
from urllib.parse import unquote

from django.utils import timezone


COUNTRY_CHOICES = [
    'United States',
    'Canada',
    'United Kingdom',
    'Australia',
    'Germany',
    'France',
    'Netherlands',
    'Ireland',
    'India',
    'Japan',
    'China',
    'South Korea',
    'Brazil',
    'Mexico',
    'Spain',
    'Italy',
    'Poland',
    'Switzerland',
    'Sweden',
    'Belgium',
    'Argentina',
    'Russia',
    'Turkey',
    'Saudi Arabia',
    'Indonesia',
    'Taiwan',
    'Remote',
]

US_STATE_CHOICES = [
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine',
    'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi',
    'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire', 'New Jersey',
    'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
    'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina',
    'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia',
    'Washington', 'West Virginia', 'Wisconsin', 'Wyoming',
]


# Maps each country key to the set of tokens/phrases that identify it.
# Short entries (<=3 chars) are matched as whole uppercase tokens.
# Longer entries are matched as substrings in the normalized location text.
COUNTRY_INDICATORS = {
    'united states': {
        'tokens': {'US', 'USA'},
        'phrases': {
            'united states', 'united states of america',
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
    'sweden': {'tokens': {'SE', 'SWE'}, 'phrases': {'sweden'}, 'state_codes': set()},
}


# Job boards do not always provide a state or country with a city.  These are
# common US city names that are unambiguous enough to classify on their own.
# State names/codes above continue to cover every city whose listing includes
# the usual ", ST" or ", State" suffix.
US_CITY_INDICATORS = {
    'albuquerque', 'anaheim', 'arlington', 'atlanta', 'austin', 'baltimore',
    'boston', 'charlotte', 'chicago', 'cleveland', 'colorado springs',
    'columbus', 'dallas', 'denver', 'detroit', 'el paso', 'fort worth',
    'fresno', 'grand rapids', 'honolulu', 'houston', 'indianapolis',
    'jacksonville', 'kansas city', 'las vegas', 'long beach', 'los angeles',
    'louisville', 'memphis', 'mesa', 'miami', 'milwaukee', 'minneapolis',
    'nashville', 'new orleans', 'new york city', 'oakland', 'oklahoma city',
    'omaha', 'orlando', 'philadelphia', 'phoenix', 'portland', 'raleigh',
    'sacramento', 'san antonio', 'san diego', 'san francisco', 'san fransisco',
    'san jose',
    'seattle', 'tampa', 'tucson', 'tulsa', 'virginia beach', 'washington dc',
}


def normalize_location_text(location):
    return re.sub(r'[^a-z0-9]+', ' ', (location or '').lower()).strip()


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

    # Explicit country codes take precedence over US state codes.  This keeps
    # "Remote - DE" (Germany) from being mistaken for Delaware, while
    # "Austin, TX" still resolves through the state-code pass below.
    matched = {
        country
        for country, indicators in COUNTRY_INDICATORS.items()
        if upper_tokens & indicators['tokens']
    }
    if matched:
        return matched

    for country, indicators in COUNTRY_INDICATORS.items():
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


US_STATE_NAMES = {
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
}

# Maps every alias (normalised lowercase) -> canonical country key
_COUNTRY_ALIASES: dict[str, str] = {}
for _key, _ind in COUNTRY_INDICATORS.items():
    _COUNTRY_ALIASES[normalize_location_text(_key)] = _key
    for _tok in _ind['tokens']:
        _COUNTRY_ALIASES[_tok.lower()] = _key
    for _phrase in _ind['phrases']:
        _COUNTRY_ALIASES[normalize_location_text(_phrase)] = _key


def _resolve_filter(location_filter: str):
    """
    Return (kind, value) where kind is:
      'country'  -> value is a canonical country key (e.g. 'united states')
      'state'    -> value is a normalised US state name (e.g. 'michigan')
      'state_code' -> value is an uppercase US state abbreviation (e.g. 'MI')
      'raw'      -> value is the normalised filter string for substring fallback
    """
    nf = normalize_location_text(location_filter)
    upper = location_filter.strip().upper()
    us_state_codes = COUNTRY_INDICATORS['united states']['state_codes']

    # US state name takes priority over country alias (michigan is in US phrases but
    # should filter to that state specifically, not all of the US)
    if nf in US_STATE_NAMES:
        return ('state', nf)
    # US state abbreviation typed alone (e.g. 'MI', 'TX')
    if upper in us_state_codes:
        return ('state_code', upper)
    # Direct alias lookup covers 'us', 'usa', 'united states', 'uk', 'gb', 'germany', etc.
    if nf in _COUNTRY_ALIASES:
        return ('country', _COUNTRY_ALIASES[nf])
    if upper in _COUNTRY_ALIASES:
        return ('country', _COUNTRY_ALIASES[upper])
    return ('raw', nf)


def _location_contains_any_us_indicator(location):
    normalized = normalize_location_text(location)
    padded = f' {normalized} '
    upper_tokens = {t.upper() for t in re.findall(r'[A-Za-z0-9]+', location or '')}
    us_ind = COUNTRY_INDICATORS['united states']
    if upper_tokens & (us_ind['tokens'] | us_ind['state_codes']):
        return True
    for phrase in us_ind['phrases']:
        if f' {phrase} ' in padded:
            return True
    for city in US_CITY_INDICATORS:
        if f' {city} ' in padded:
            return True
    return False


def _is_us_broad_filter(normalized_filter):
    return _COUNTRY_ALIASES.get(normalized_filter) == 'united states'


def _is_us_state_filter(normalized_filter):
    return normalized_filter in US_STATE_NAMES


def location_matches_filter(location, location_filter):
    if not location_filter:
        return True
    if not location:
        return False

    if location_filter.strip().casefold() == 'remote':
        return is_remote(location)

    kind, value = _resolve_filter(location_filter)

    if kind == 'country':
        if value == 'united states':
            return _location_contains_any_us_indicator(location)
        return value in _get_country_keys(location)

    if kind == 'state':
        padded = f' {normalize_location_text(location)} '
        return f' {value} ' in padded

    if kind == 'state_code':
        # Match the abbreviation as a non-leading token in the location string
        tokens = [t.upper() for t in re.findall(r'[A-Za-z0-9]+', location)]
        return value in tokens[1:] if len(tokens) > 1 else False

    # 'raw' fallback: check country keys first, then substring
    filter_keys = _get_country_keys(location_filter)
    location_keys = _get_country_keys(location)
    if filter_keys and location_keys:
        return bool(filter_keys & location_keys)
    return f' {value} ' in f' {normalize_location_text(location)} '


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


def is_remote(location):
    if not location:
        return False
    loc = location.lower()
    return bool(re.search(r'\bremote\b', loc))


def resolve_country(location):
    """Return the canonical country name for a location string, or None."""
    if not location:
        return None
    keys = _get_country_keys(location)
    if keys:
        # A remote posting with a country qualifier (for example, "Remote - US")
        # belongs in that country, while an unqualified remote posting remains
        # available through the Remote option.
        for choice in COUNTRY_CHOICES:
            if choice.lower() in keys:
                return choice
        return next(iter(keys)).title()
    if is_remote(location):
        return 'Remote'
    if _location_contains_any_us_indicator(location):
        return 'United States'
    return None


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
