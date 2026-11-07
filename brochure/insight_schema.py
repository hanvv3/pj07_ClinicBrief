"""Strict, bounded schemas for observed problems and complete public assets."""
from copy import deepcopy

from .provider_schema import COVERAGE_AREAS, IDENTIFIER, array, discovery_schema, obj, string

SCORES = obj(**{key: {'type': 'integer', 'minimum': 0, 'maximum': 3}
                for key in ('specificity', 'usability', 'novelty', 'evidence')})
ASSET_FORMATS = ('prompt', 'message', 'checklist', 'comparison', 'brief')
READY_TO_USE = obj(title=string(120), format={'type': 'string', 'enum': list(ASSET_FORMATS)},
                   body=string(3000), adaptation_note=string(500, 0))
AUDIT_FLAGS = ('factual_support', 'asset_complete', 'novelty_supported', 'scope_safe', 'provenance_correct')


def selection_schema(verified_sources):
    reference = {'type': 'string', 'enum': list(verified_sources)}
    selection = obj(
        audience={'type': 'string', 'enum': ['director', 'staff', 'both']},
        problem=string(400), problem_key=string(80), reason=string(600),
        novelty={'type': 'string', 'enum': ['new', 'update']},
        previous_topic_id={'type': ['string', 'null'], 'maxLength': 80}, change=string(400, 0),
        signals=array(obj(source_id=reference, observation=string(500)), 5), scores=SCORES,
    )
    candidate = obj(id=IDENTIFIER, title=string(150),
                    coverage_area={'type': 'string', 'enum': list(COVERAGE_AREAS)},
                    why_now=string(400), selection=selection, answer_question=string(600),
                    asset_format={'type': 'string', 'enum': list(ASSET_FORMATS)},
                    change_source_ids=array(reference, 5, 0))
    return obj(candidates=array(candidate, 6, 0))


def final_schema(verified_sources, candidate_ids):
    schema = discovery_schema(verified_sources, briefing=True)
    topics = schema['properties']['topics']
    topics['minItems'] = 0
    topic = topics['items']
    topic['properties']['id'] = {'type': 'string', 'enum': list(candidate_ids)}
    topic['properties']['ready_to_use'] = deepcopy(READY_TO_USE)
    topic['required'].append('ready_to_use')
    return schema


def edit_schema(topic_ids):
    topic = obj(id={'type': 'string', 'enum': list(topic_ids)}, title=string(100),
                summary=string(400), director_value=string(500), takeaway=string(500),
                why_now=string(400), ready_to_use=obj(title=string(120), body=string(3000)))
    return obj(topics=array(topic, len(topic_ids), len(topic_ids)))


def audit_schema(candidate_ids):
    decision = obj(id={'type': 'string', 'enum': list(candidate_ids)},
                   **{flag: {'type': 'boolean'} for flag in AUDIT_FLAGS}, reason=string(400, 0))
    return obj(decisions=array(decision, 3, 0))
