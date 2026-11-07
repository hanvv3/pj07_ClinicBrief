"""Reviewed examples, separate from future live research providers."""
import json
from pathlib import Path
from urllib.parse import urlsplit

CATALOG_PATH = Path(__file__).parent / 'data' / 'topics.json'


def validate_topic(topic: dict) -> None:
    for key in ('id', 'title', 'director_value', 'takeaway', 'research_date',
                'evidence_notice', 'brochure', 'notes', 'claims', 'sources'):
        if not topic.get(key):
            raise ValueError(f'Missing topic field: {key}')
    sources = topic['sources']
    ids = {source['id'] for source in sources}
    if len(ids) != len(sources):
        raise ValueError('Duplicate source ID')
    for source in sources:
        url = urlsplit(source['url'])
        if url.scheme != 'https' or not url.hostname:
            raise ValueError('Sources must use direct HTTPS URLs')
        if not all(source.get(k) for k in ('title', 'publisher', 'checked_at', 'context')):
            raise ValueError('Source context missing')
    for claim in topic['claims'] + topic['notes']['claim_map']:
        if not claim.get('source_ids') or not set(claim['source_ids']) <= ids:
            raise ValueError('Unsupported factual claim')
    for section in topic['brochure']['sections']:
        if not set(section.get('source_ids', [])) <= ids:
            raise ValueError('Unknown section citation')
    for key in ('title', 'intro', 'sections', 'example', 'limitations'):
        if not topic['brochure'].get(key):
            raise ValueError(f'Missing brochure field: {key}')
    for key in ('opening_staff', 'opening_director', 'explanation', 'qa', 'cannot_claim'):
        if not topic['notes'].get(key):
            raise ValueError(f'Missing representative notes: {key}')


def load_topics() -> list[dict]:
    topics = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    seen = set()
    for topic in topics:
        validate_topic(topic)
        if topic['id'] in seen:
            raise ValueError('Duplicate topic ID')
        seen.add(topic['id'])
    return topics
