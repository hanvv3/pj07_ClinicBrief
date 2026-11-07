#!/usr/bin/env python3
"""Verify an existing LangSmith run through read-only SmithDB APIs."""
import argparse
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langsmith import APIError
from langsmith.utils import LangSmithError

from brochure.langsmith_reads import create_reader, resolve_project_id
from brochure.tracing import _langsmith_client, _langsmith_config


def verify(config, run_id, project_id=None, start_time=None):
    """Read identifiers, link and child counts; never create a trace or job."""
    run_id = str(UUID(run_id))
    with create_reader(config) as reader:
        if project_id is None:
            with closing(_langsmith_client(config)) as client:
                project_id = resolve_project_id(config, reader, client)
        project_id = str(UUID(str(project_id)))
        options = {'start_time': start_time} if start_time is not None else {}
        saved = reader.runs.retrieve_v2(run_id, project_id=project_id,
            selects=['ID', 'PROJECT_ID', 'TRACE_ID', 'START_TIME'], **options)
        if str(saved.id) != run_id or str(saved.project_id) != project_id or not saved.trace_id:
            raise ValueError('Run identity was not confirmed')
        trace_id = str(UUID(str(saved.trace_id)))
        timestamp = saved.start_time
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        url_options = {'start_time': timestamp} if timestamp is not None else {}
        url = reader.runs.get_url(run_id, project_id=project_id,
                                 trace_id=trace_id, **url_options).url
        if not isinstance(url, str) or not url.startswith('https://'):
            raise ValueError('A verified HTTPS link was not returned')
        trace = reader.traces.list_runs(trace_id, project_id=project_id,
                                        selects=['ID', 'PARENT_RUN_IDS'])
        if trace.items is None:
            raise ValueError('Trace run list was not returned')
        parents = [[str(parent) for parent in (item.parent_run_ids or [])]
                   for item in trace.items]
        return {'status': 'verified', 'run_id': run_id, 'project_id': project_id,
                'trace_id': trace_id, 'url': url,
                'direct_child_count': sum(bool(chain) and chain[-1] == run_id for chain in parents),
                'descendant_count': sum(run_id in chain for chain in parents)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True, help='Existing LangSmith run UUID')
    parser.add_argument('--project-id', help='Project UUID; otherwise resolve configured destination')
    parser.add_argument('--start-time', help='Optional RFC3339 run start time')
    parser.add_argument('--workspace', type=Path, default=ROOT,
                        help='Workspace containing .env.local; defaults to this project')
    args = parser.parse_args(argv)
    config = _langsmith_config(args.workspace)
    if not config['configured']:
        print('LangSmith 키와 목적지 설정을 확인해 주세요.', file=sys.stderr)
        return 2
    try:
        report = verify(config, args.run_id, args.project_id, args.start_time)
    except (APIError, LangSmithError, ValueError) as error:
        # Provider bodies and credential-bearing configuration stay private.
        print(f'LangSmith 기존 기록 조회에 실패했습니다: {type(error).__name__}', file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
