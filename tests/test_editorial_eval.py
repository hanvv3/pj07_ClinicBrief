"""Evaluation integrity: these tests do not grade the quality of generated prose."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/evaluate_editorial.py'


class EditorialEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('editorial_eval', SCRIPT)
        cls.e = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.e)

    def test_reversed_labels_map_to_same_candidate_and_unstable_is_not_win(self):
        self.assertEqual(self.e.preference('B', ['baseline','candidate']), 'candidate')
        self.assertEqual(self.e.preference('A', ['candidate','baseline']), 'candidate')
        self.assertEqual(self.e.resolve_preference('candidate','baseline'), 'unstable')
        self.assertEqual(self.e.resolve_preference('TIE','TIE'), 'tie')
        self.assertEqual(self.e.resolve_preference('NEITHER','NEITHER'), 'neither')
        self.assertEqual(self.e.resolve_preference('INSUFFICIENT_EVIDENCE','INSUFFICIENT_EVIDENCE'), 'unassessable')

    def test_factual_fail_or_generation_rejection_cannot_count_as_improvement(self):
        generation={'baseline':{'status':'accepted'},'candidate':{'status':'accepted'}}
        facts={'A':{'status':'pass'},'B':{'status':'needs_revision'}}
        answer={'winner':'B'}; reverse={'winner':'A'}
        self.assertEqual(self.e.case_outcome(generation,facts,answer,reverse,['baseline','candidate'])['outcome'],'factual_failure')
        facts['B']['status']='pass';generation['candidate']['status']='rejected'
        self.assertEqual(self.e.case_outcome(generation,facts,answer,reverse,['baseline','candidate'])['outcome'],'generation_failure')

    def test_blind_payload_omits_version_metadata_and_private_representative_notes(self):
        case={'id':'case-x','kind':'news','audience':'director','task':'소식을 전하세요',
              'topic':{'title':'seed','sources':[{'id':'S1','context':'source facts','url':'https://example.org'}]},
              'provenance':{'model':'SECRET_MODEL_LABEL'}}
        material={'brochure':{'title':'글','intro':'본문','sections':[],
                    'example':{'heading':'','body':''},'limitations':[]},
                  'notes':{'explanation':'PRIVATE-NOTE'},'quality_notes':['VERSION-HINT']}
        rubric='fixed\n## Initial product acceptance proposal\nat least 8 changed-output wins'
        payload=self.e.judge_payload(case,{'baseline':material,'candidate':material},['baseline','candidate'],rubric)
        encoded=json.dumps(payload,ensure_ascii=False)
        for hidden in ['baseline','candidate','PRIVATE-NOTE','VERSION-HINT','SECRET_MODEL_LABEL','case-x']:
            self.assertNotIn(hidden,encoded)
        self.assertIn('source facts',encoded)
        self.assertEqual(payload['outputs']['A']['title'],'글')
        self.assertEqual(payload['rubric'],'fixed')

    def test_call_budget_persists_and_reused_attempt_does_not_spend_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=self.e.Ledger(Path(tmp),2)
            ledger.reserve('first')
            with self.assertRaises(self.e.AttemptExists):ledger.reserve('first')
            ledger.reserve('second')
            with self.assertRaises(self.e.BudgetExceeded):self.e.Ledger(Path(tmp),2).reserve('third')
            self.assertEqual(len(list((Path(tmp)/'calls').glob('*.json'))),2)

    def test_resume_rejects_changed_evidence_or_rubric_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';baseline=root/'baseline';current=root/'current'
            for p in [baseline,current]:
                (p/'brochure').mkdir(parents=True);(p/'brochure/__init__.py').write_text('')
            case={'id':'x','kind':'news','audience':'director','task':'read','topic':{'sources':[]}}
            self.e.prepare_run(run,[case],'rubric','model',baseline,current,8)
            changed={**case,'task':'changed'}
            with self.assertRaises(ValueError):self.e.prepare_run(run,[changed],'rubric','model',baseline,current,8)
            with self.assertRaises(ValueError):self.e.prepare_run(run,[case],'changed','model',baseline,current,8)

    def test_resume_checks_frozen_files_actually_used_by_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';baseline=root/'baseline';current=root/'current'
            for p in [baseline,current]:
                (p/'brochure').mkdir(parents=True);(p/'brochure/__init__.py').write_text('')
            case={'id':'x','kind':'news','audience':'director','task':'read','topic':{'sources':[]}}
            arguments=(run,[case],'rubric','model',baseline,current,8)
            original=self.e.prepare_run(*arguments)
            self.assertEqual(self.e.prepare_run(*arguments),original)
            for relative,changed in [('cases.json','{"cases": []}'),('rubric.md','changed'),
                                     ('runtime/baseline/brochure/__init__.py','# changed'),
                                     ('runtime/candidate/brochure/__init__.py','# changed')]:
                with self.subTest(relative=relative):
                    target=run/relative;before=target.read_text();target.write_text(changed)
                    with self.assertRaises(ValueError):self.e.prepare_run(*arguments)
                    target.write_text(before)

    def test_production_audit_rejection_keeps_raw_draft_usage_without_credentials(self):
        from brochure.catalog import load_topics
        from brochure import provider
        topic=load_topics()[0]
        draft={key:topic[key] for key in ('brochure','notes')}
        draft['quality_notes']=[]
        audit={'factual_support':False,'non_promotional':True,'non_clinical':True,
               'injection_safe':True,'consistent':True,'quality_notes':['근거 확인이 필요합니다.']}
        def response(value):
            return {'status':'completed','model':'returned-model','output':[
                {'type':'message','status':'completed','role':'assistant','content':[
                    {'type':'output_text','text':json.dumps(value),'annotations':[]}]}],
                'usage':{'input_tokens':40,'output_tokens':20,'total_tokens':60}}
        pending=[response(draft),response(audit)]
        def transport(request,timeout):return io.BytesIO(json.dumps(pending.pop(0)).encode())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact=root/'generation.json'
            spec={'run':str(root),'max_calls':2,'source_root':str(SCRIPT.parents[1]),
                  'workspace':str(root),'model':'requested-model','key':'test.baseline',
                  'mode':'generate','artifact':str(artifact),'evidence':topic['sources'],
                  'case':{'topic':topic,'audience':'의원 직원','kind':'practical','task':'안내문을 작성하세요'}}
            secret='sk-never-persist-this-test-key-0000000'
            with patch.dict(os.environ,{'OPENAI_API_KEY':secret}),patch.object(provider,'urlopen',transport),patch.object(sys,'path',list(sys.path)):
                self.e.worker(spec)
            result=self.e.read_json(artifact)
            self.assertEqual(result['status'],'rejected')
            self.assertEqual(result['proposed_material'],draft)
            self.assertFalse(result['production_audit']['factual_support'])
            calls=[self.e.read_json(p) for p in (root/'calls').glob('*.json')]
            self.assertEqual(len(calls),2)
            self.assertTrue(all(c['returned_model']=='returned-model' and c['usage']['total_tokens']==60 for c in calls))
            self.assertTrue(all(c['request']['tools']==[] for c in calls))
            self.assertNotIn(secret,'\n'.join(p.read_text() for p in root.rglob('*.json')))

    def test_all_cases_stay_in_denominator_including_missing_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.e.write_json(root/'manifest.json',{'case_ids':['a','b'],'model':'m','max_calls':14})
            self.e.write_json(root/'cases/a/outcome.json',{'outcome':'candidate','scores':{}})
            report=self.e.summarize(root)
            self.assertEqual(report['total_cases'],2)
            self.assertEqual(report['outcomes'],{'candidate':1,'pending':1})
            self.assertEqual(report['candidate_win_rate'],0.5)

if __name__=='__main__':unittest.main()
