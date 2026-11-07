import copy
import json
import tempfile
import unittest
from pathlib import Path

from brochure.insight_store import (InsightStore, build_history, normalize_problem_key,
                                    project_insight_fields, public_selection_report)


def selected_topic():
    return {'id': 'feed-first', 'title': '예약 변경 안내문', 'coverage_area': 'operations',
            'sources': [{'id': 'S1'}],
            'selection': {'audience': 'staff', 'problem': '예약 변경 문의에 답할 문장이 필요합니다.',
                'problem_key': 'appointment-change-message', 'reason': '공개 문의와 지침을 연결한 안내 문구입니다.',
                'novelty': 'new', 'previous_topic_id': None, 'change': '',
                'signals': [{'source_id': 'S1', 'observation': '공개 안내에 예약 변경 문의 경로가 제시되어 있습니다.'}],
                'scores': {'specificity': 3, 'usability': 3, 'novelty': 2, 'evidence': 2}, 'total': 10},
            'ready_to_use': {'title': '예약 변경 문의 답장', 'format': 'message',
                'body': '예약 변경을 원하시면 예약하신 기관의 공식 연락처로 문의해 주세요. 변경 가능 여부를 확인한 뒤 안내해 드리겠습니다.',
                'adaptation_note': '기관이 공개한 연락 경로만 추가하세요.'}}


class InsightStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'insights.sqlite3'
        self.store = InsightStore(self.path)

    def test_votes_upsert_per_owner_topic_and_survive_reopen(self):
        self.store.set_feedback('alice', 'feed-one', 'appointment-change', 'useful', shared=True)
        self.store.set_feedback('alice', 'feed-one', 'appointment-change', 'seen', shared=True)
        self.store.set_feedback('bob', 'feed-one', 'appointment-change', 'not_useful', shared=True)
        reopened = InsightStore(self.path)
        self.assertEqual(reopened.feedback_for('alice', ['feed-one', 'missing']), {'feed-one': 'seen'})
        self.assertEqual(reopened.feedback_for('bob', ['feed-one']), {'feed-one': 'not_useful'})
        self.assertEqual(reopened.feedback_for('other', ['feed-one']), {})
        self.assertEqual(reopened.feedback_for('alice', []), {})
        self.assertCountEqual(reopened.history_feedback(shared=True), [
            {'problem_key': 'appointment-change', 'verdict': 'seen', 'count': 1},
            {'problem_key': 'appointment-change', 'verdict': 'not_useful', 'count': 1}])

    def test_shared_aggregation_excludes_private_research_and_owner_history_is_private(self):
        self.store.set_feedback('alice', 'feed-one', 'shared-task', 'useful', shared=True)
        self.store.set_feedback('bob', 'feed-one', 'shared-task', 'useful', shared=True)
        self.store.set_feedback('alice', 'research-alice', 'private-alice-task', 'seen')
        self.store.set_feedback('bob', 'research-bob', 'private-bob-task', 'not_useful')
        self.assertEqual(self.store.history_feedback(shared=True), [
            {'problem_key': 'shared-task', 'verdict': 'useful', 'count': 2}])
        alice = self.store.history_feedback(owner='alice')
        self.assertCountEqual(alice, [{'problem_key': 'shared-task', 'verdict': 'useful', 'count': 1},
                                     {'problem_key': 'private-alice-task', 'verdict': 'seen', 'count': 1}])
        self.assertNotIn('bob', str(alice))
        self.assertEqual(self.store.history_feedback(), [])
        self.assertEqual(self.store.feedback_for('alice', ['research-bob']), {})

    def test_invalid_feedback_is_rejected_without_persistence(self):
        for changes in [{'owner': ''}, {'topic_id': 'invalid\x00'}, {'problem_key': '...'},
                        {'verdict': 'freeform secret'}, {'shared': 1}]:
            args = dict(owner='alice', topic_id='feed-one', problem_key='a-task', verdict='useful')
            args.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.set_feedback(**args)
        self.assertEqual(self.store.history_feedback(owner='alice'), [])

    def test_feedback_and_history_are_bounded_and_strip_private_fields(self):
        topics, feedback = [], []
        for index in range(35):
            item = selected_topic()
            item['id'] = f'feed-{index}'
            item['selection']['problem_key'] = f'task-{index}'
            item.update(company_text='PRIVATE', notes={'PRIVATE': 'PRIVATE'})
            topics.append(item)
            feedback.append({'problem_key': f'task-{index}', 'verdict': 'useful', 'count': 1,
                             'owner': 'PRIVATE-OWNER', 'freeform': 'PRIVATE'})
            self.store.set_feedback('alice', f'feed-{index}', f'task-{index}', 'useful', shared=True)
        history = build_history(topics, feedback)
        self.assertEqual(len(history['recent_topics']), 30)
        self.assertEqual(len(history['feedback']), 30)
        self.assertEqual(len(self.store.history_feedback(shared=True)), 30)
        self.assertEqual(set(history['recent_topics'][0]), {'id', 'title', 'problem', 'problem_key',
                                                          'coverage_area', 'summary', 'change'})
        self.assertEqual(set(history['feedback'][0]), {'problem_key', 'verdict', 'count'})
        self.assertNotIn('PRIVATE', str(history))
        self.assertEqual(build_history(history['recent_topics'], history['feedback']), history)

    def test_history_distinguishes_prior_coverage_and_preserves_only_public_summary_and_change(self):
        phone = selected_topic()
        phone['summary'] = '예약 변경은 전화 문의 경로만 다뤘습니다.'
        online = copy.deepcopy(phone)
        online['summary'] = '전화와 새 온라인 예약 변경 경로를 함께 다뤘습니다.'
        online['selection']['change'] = '온라인 예약 변경 경로가 추가됐습니다.'
        online.update(company_text='PRIVATE', brochure={'body': 'PRIVATE'}, owner='PRIVATE')
        online['selection']['notes'] = 'PRIVATE'
        first = build_history([phone], [])
        second = build_history([online], [])
        self.assertNotEqual(first, second)
        self.assertEqual(second['recent_topics'][0]['summary'], online['summary'])
        self.assertEqual(second['recent_topics'][0]['change'], online['selection']['change'])
        self.assertNotIn('PRIVATE', str(second))
        self.assertNotIn('ready_to_use', str(second))
        self.assertEqual(build_history(second['recent_topics'], []), second)

    def test_history_byte_budget_retains_whole_newest_records_without_truncating_coverage(self):
        topics = []
        for index in range(30):
            item = selected_topic()
            item.update(id=f'feed-{index}', title='제' * 300, summary='요' * 400)
            item['selection'].update(problem='문' * 400, change='변' * 400)
            topics.append(item)
        history = build_history(topics, [{'problem_key': 'task', 'verdict': 'seen', 'count': 1}])
        self.assertLessEqual(len(json.dumps(history, ensure_ascii=False).encode()), 24000)
        self.assertGreater(len(history['recent_topics']), 0)
        self.assertLess(len(history['recent_topics']), 30)
        self.assertEqual(history['recent_topics'][0]['id'], 'feed-0')
        self.assertEqual(history['recent_topics'][0]['summary'], '요' * 400)
        self.assertEqual(history['recent_topics'][0]['change'], '변' * 400)
        self.assertEqual(history['feedback'], [{'problem_key': 'task', 'verdict': 'seen', 'count': 1}])

    def test_normalized_problem_keys_are_consistent_and_legacy_titles_remain_usable(self):
        self.assertEqual(normalize_problem_key(' Appointment__Change Message '), 'appointment-change-message')
        self.store.set_feedback('alice', 'feed-one', 'Appointment Change', 'useful', shared=True)
        self.assertEqual(self.store.history_feedback(shared=True)[0]['problem_key'], 'appointment-change')
        history = build_history([{'id': 'old-one', 'title': '오래된 공개 제목', 'company_text': 'PRIVATE'}], [])
        self.assertEqual(history['recent_topics'][0]['problem'], '오래된 공개 제목')
        self.assertEqual(history['recent_topics'][0]['coverage_area'], '')
        self.assertEqual(build_history([None, {'company_text': 'PRIVATE'}], [None, {'owner': 'PRIVATE'}]),
                         {'recent_topics': [], 'feedback': []})

    def test_projection_validates_source_links_and_returns_independent_public_objects(self):
        topic = selected_topic()
        topic['selection']['private_context'] = 'PRIVATE'
        topic['selection']['signals'][0]['private_context'] = 'PRIVATE'
        topic['ready_to_use']['company_text'] = 'PRIVATE'
        public = project_insight_fields(topic)
        self.assertEqual(set(public), {'selection', 'ready_to_use'})
        self.assertNotIn('PRIVATE', str(public))
        public['selection']['signals'][0]['observation'] = 'changed'
        self.assertNotEqual(topic['selection']['signals'][0]['observation'], 'changed')
        self.assertEqual(project_insight_fields({'title': 'legacy'}), {})
        for mutate in [lambda item: item['selection']['signals'][0].update(source_id='invented'),
                       lambda item: item['selection']['signals'][0].update(source_id=[]),
                       lambda item: item['selection']['scores'].update(evidence=True),
                       lambda item: item['selection'].update(total=11),
                       lambda item: item['selection'].update(audience='anyone'),
                       lambda item: item['selection'].update(novelty='update', previous_topic_id=None),
                       lambda item: item['ready_to_use'].update(body=' '),
                       lambda item: item.pop('ready_to_use')]:
            invalid = selected_topic()
            mutate(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                project_insight_fields(invalid)

    def test_selection_report_is_allowlisted_and_empty_legacy_is_supported(self):
        report = {'sources_read': 9, 'candidates_considered': 2, 'selected_count': 1,
                  'rejected': [{'title': '탈락 후보', 'reason': '완성된 결과물이 부족합니다.', 'prompt': 'PRIVATE'}],
                  'prompt': 'PRIVATE'}
        safe = public_selection_report(report)
        self.assertNotIn('PRIVATE', str(safe))
        self.assertEqual(set(safe), {'sources_read', 'candidates_considered', 'selected_count', 'rejected'})
        self.assertEqual(public_selection_report(None), {})
        self.assertEqual(public_selection_report({}), {})
        for changes in [{'selected_count': 3}, {'sources_read': True}, {'rejected': 'PRIVATE'},
                        {'candidates_considered': 7}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                public_selection_report({**report, **changes})


if __name__ == '__main__':
    unittest.main()
