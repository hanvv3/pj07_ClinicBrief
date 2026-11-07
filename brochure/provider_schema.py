"""Bounded JSON schemas shared by Responses requests and local validation."""
from copy import deepcopy


def obj(**properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def string(limit=2000, minimum=1):
    return {'type': 'string', 'minLength': minimum, 'maxLength': limit}


def array(items, maximum=8, minimum=1):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': maximum}


IDENTIFIER = {'type': 'string', 'pattern': r'^[A-Za-z0-9_-]{1,80}$', 'maxLength': 80}
SOURCE_IDS = array(IDENTIFIER, 5)
DATE = {'type': ['string', 'null'], 'maxLength': 10,
        'pattern': r'^\d{4}-\d{2}(-\d{2})?$'}
SOURCE = obj(id=IDENTIFIER, title=string(300), publisher=string(200), url=string(1500),
             published_at=DATE, updated_at=DATE, context=string(2000, 30))
CLAIM = obj(id=IDENTIFIER, text=string(1000), source_ids=SOURCE_IDS)
TOPIC = obj(id=IDENTIFIER, title=string(100), summary=string(400), director_value=string(500),
            takeaway=string(500), reading_minutes={'type': 'integer', 'minimum': 1, 'maximum': 10},
            evidence_notice=string(1500), sources=array(SOURCE, 5), claims=array(CLAIM, 8))
DISCOVERY = obj(topics=array(TOPIC, 3))
COVERAGE_AREAS = ('medical', 'ai', 'operations', 'economy', 'life')
BROCHURE = obj(
    title=string(100), intro=string(700),
    sections=array(obj(heading=string(120), body=string(1500), source_ids=SOURCE_IDS), 5),
    example=obj(heading=string(120), body=string(1600)), limitations=array(string(600), 6),
    sender=obj(name={'type': 'string', 'enum': ['']}, contact={'type': 'string', 'enum': ['']}),
)
NOTES = obj(opening_staff=string(600), opening_director=string(600), explanation=string(2000),
            qa=array(obj(question=string(300), answer=string(1000)), 6),
            cannot_claim=array(string(600), 8),
            claim_map=array(obj(claim=string(1200), source_ids=SOURCE_IDS), 10))
COMPOSITION = obj(brochure=BROCHURE, notes=NOTES, quality_notes=array(string(600), 8, 0))
AUDIT_FLAGS = ('factual_support', 'non_promotional', 'non_clinical', 'injection_safe', 'consistent')
AUDIT = obj(**{name: {'type': 'boolean'} for name in AUDIT_FLAGS},
            quality_notes=array(string(600), 8, 0))


def discovery_schema(verified_sources, *, briefing=False):
    """Only the server's body-accessed-and-cited URL/ID set may enter extraction."""
    schema = deepcopy(DISCOVERY)
    topic_schema = schema['properties']['topics']['items']
    topic = topic_schema['properties']
    if briefing:
        topic.update(coverage_area={'type': 'string', 'enum': list(COVERAGE_AREAS)},
                     why_now=string(400))
        topic_schema['required'].extend(('coverage_area', 'why_now'))
    source = topic['sources']['items']['properties']
    ids = list(verified_sources)
    source['id'] = {'type': 'string', 'enum': ids}
    source['url'] = {'type': 'string', 'enum': list(verified_sources.values())}
    topic['claims']['items']['properties']['source_ids']['items'] = {'type': 'string', 'enum': ids}
    return schema


def composition_schema(source_ids):
    """Prevent the model from using claim IDs, URLs, or invented source IDs."""
    schema = deepcopy(COMPOSITION)
    fields = schema['properties']
    for field, items in (('brochure', 'sections'), ('notes', 'claim_map')):
        fields[field]['properties'][items]['items']['properties']['source_ids']['items'] = {
            'type': 'string', 'enum': sorted(source_ids)}
    return schema
