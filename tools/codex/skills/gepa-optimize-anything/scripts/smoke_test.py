#!/usr/bin/env python3
"""Offline installation check; synthetic scores are NOT editorial quality evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch


def blocked_connect(*args, **kwargs):
    raise RuntimeError('Network access is disabled in the offline wiring check')


def main():
    # A callable proposer prevents provider use; block connections as a backstop.
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
    with patch.object(socket.socket, 'connect', blocked_connect):
        from gepa.optimize_anything import OptimizeAnythingConfig, optimize_anything
        calls = []
        def propose(prompt):
            calls.append('proposal')
            return '```\nwiring-ok\n```'
        def evaluate(candidate, example):
            calls.append('evaluation')
            return float(candidate == 'wiring-ok'), {'feedback': 'For this synthetic check use wiring-ok.'}
        with tempfile.TemporaryDirectory(prefix='gepa-codex-smoke-') as folder:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = optimize_anything(
                    seed_candidate='seed', evaluator=evaluate,
                    dataset=[{'id':'train'}], valset=[{'id':'validation'}],
                    test_set=[{'id':'held-out'}], objective='Offline integration check only.',
                    config=OptimizeAnythingConfig(
                        engine='gepa', max_evals=8, stop_at_score=1.0,
                        max_concurrency=1, run_dir=str(Path(folder)/'run'),
                        output_dir=str(Path(folder)/'outputs'),
                        engine_config={
                            'reflection': {'reflection_lm':propose, 'reflection_minibatch_size':1},
                            'engine': {'max_workers':1, 'seed':0, 'raise_on_exception':True},
                        },
                    ),
                )
            assert result.best_candidate == 'wiring-ok', repr(result.best_candidate)
            assert calls.count('proposal') >= 1
            assert result.metadata.get('test_score') == 1.0
            assert result.metadata.get('baseline_test_score') == 0.0
            print(json.dumps({'status':'pass','scope':'offline wiring only; not a quality benchmark',
                              'proposal_calls':calls.count('proposal'),
                              'evaluation_calls':calls.count('evaluation'), 'paid_api_calls':0}))


if __name__ == '__main__':
    main()
