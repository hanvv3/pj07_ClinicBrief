"""Authenticated Phase 2 local integration server; no public deployment yet."""
import argparse
import json
import mimetypes
import os
import re
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .service import AppError, BrochureService
from .auth import AuthStore, AuthError
from .jobs import JobRunner, JobError
from .provider import OpenAIProvider, ProviderError
from .workflows import Workflows
from .briefing import BriefingService
from .insight_store import InsightStore

ROOT = Path(__file__).resolve().parent.parent
STATIC = {'/': 'index.html', '/index.html': 'index.html',
          '/app.js': 'app.js', '/style.css': 'style.css'}
MAX_BODY = 32768


def make_server(service, port=8765, provider=None, auth=None, jobs=None, briefing=None,
                auto_briefing=True, insights=None):
    provider = provider or OpenAIProvider(ROOT)
    auth = auth or AuthStore(service.data_dir / 'auth.sqlite3')
    jobs = jobs or JobRunner(service.data_dir / 'jobs.sqlite3')
    insights = insights or InsightStore(service.data_dir / 'insights.sqlite3')
    briefing = briefing or BriefingService(service.data_dir / 'briefing.sqlite3',
                                           provider, jobs, enabled=auto_briefing, insights=insights)
    workflows = Workflows(service, provider, jobs, briefing, insights=insights)

    class Handler(BaseHTTPRequestHandler):
        server_version = 'ClinicBrief/0.2'

        def setup(self):
            super().setup()
            self.connection.settimeout(60)

        def log_message(self, *args):
            # Never log sender details, content, URLs or arbitrary provider errors.
            pass

        def send_data(self, status, content, mime='application/json; charset=utf-8', filename=None, cookie=None):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, status, data, cookie=None):
            self.send_data(status, json.dumps(data, ensure_ascii=False).encode('utf-8'), cookie=cookie)

        def token(self):
            try:
                cookie = SimpleCookie(self.headers.get('Cookie',''))
                return cookie['clinic_session'].value if 'clinic_session' in cookie else ''
            except Exception:
                return ''

        def session_data(self, session):
            return {'user':session['user'] if session else None,
                    'csrf_token':session['csrf_token'] if session else None,
                    'provider':{'configured':provider.configured,'model':provider.model},
                    'limits':{'company_chars':6000,'revision_chars':1000},'phase':2}

        def check_local(self):
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            host = self.headers.get('Host', '')
            if host not in allowed:
                raise AppError('이 검증 앱은 로컬 주소에서만 사용할 수 있습니다.', 403)
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + host:
                raise AppError('다른 사이트에서 보낸 요청은 허용하지 않습니다.', 403)
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise AppError('다른 사이트에서 보낸 요청은 허용하지 않습니다.', 403)

        def json_body(self):
            if self.headers.get('Transfer-Encoding'):
                raise AppError('지원하지 않는 요청 형식입니다.')
            if self.headers.get_content_type() != 'application/json':
                raise AppError('JSON 형식으로 요청해 주세요.')
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                raise AppError('요청 크기가 올바르지 않습니다.')
            if length > MAX_BODY:
                raise AppError('입력 크기가 제한을 초과했습니다.', 413)
            if length <= 0:
                raise AppError('요청 내용이 비어 있습니다.')
            try:
                body = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError):
                raise AppError('요청 내용을 읽을 수 없습니다.')
            if not isinstance(body, dict):
                raise AppError('JSON 객체가 필요합니다.')
            return body

        def handle_request(self):
            try:
                self.check_local()
                url = urlsplit(self.path)
                path = url.path
                method = self.command
                if method == 'GET' and path in STATIC:
                    file = ROOT / 'web' / STATIC[path]
                    if not file.is_file():
                        raise AppError('화면 파일이 준비되지 않았습니다.', 404)
                    mime = mimetypes.guess_type(file)[0] or 'application/octet-stream'
                    return self.send_data(200, file.read_bytes(), mime + '; charset=utf-8')
                session = auth.session(self.token())
                if method == 'GET' and path == '/api/session':
                    return self.send_json(200,self.session_data(session))
                if method == 'POST' and path in ('/api/auth/register','/api/auth/login'):
                    body = self.json_body()
                    operation = auth.register if path.endswith('register') else auth.login
                    user = operation(body.get('email'),body.get('password'))
                    auth.logout(self.token())
                    created = auth.new_session(user['id'])
                    cookie = f"clinic_session={created['token']}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200"
                    return self.send_json(200,self.session_data(created),cookie=cookie)
                if not path.startswith('/api/'):
                    raise AppError('요청한 경로를 찾을 수 없습니다.',404)
                if session is None:
                    raise AppError('로그인한 뒤 이용해 주세요.',401)
                owner = session['user']['id']
                if method in ('POST','PATCH','DELETE'):
                    if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf_token']):
                        raise AppError('보안 확인이 만료되었습니다. 화면을 새로고침해 주세요.',403)
                if method == 'POST' and path == '/api/auth/logout':
                    auth.logout(self.token())
                    return self.send_json(200,{'ok':True},cookie='clinic_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
                if method == 'GET' and path == '/api/topics':
                    return self.send_json(200, {'topics': service.topics})
                if method == 'GET' and path == '/api/briefing':
                    feed = briefing.snapshot()
                    feed['feedback'] = insights.feedback_for(owner, [topic['id'] for topic in feed['items']])
                    return self.send_json(200, feed)
                if method == 'POST' and path == '/api/topic-feedback':
                    body = self.json_body()
                    if set(body) != {'topic_id', 'source', 'verdict'}:
                        raise AppError('주제와 평가 항목만 보낼 수 있습니다.')
                    if body['source'] not in ('briefing', 'research') or not isinstance(body['topic_id'], str):
                        raise AppError('평가할 주제를 목록에서 선택해 주세요.')
                    shared = body['source'] == 'briefing'
                    topic = (briefing.get_topic(body['topic_id']) if shared else
                             service.store.topic(owner, body['topic_id']))
                    if topic is None:
                        raise AppError('평가할 주제를 찾을 수 없습니다.', 404)
                    problem_key = (topic.get('selection') or {}).get('problem_key')
                    if not problem_key:
                        raise AppError('새 선별 방식으로 찾은 주제에 평가를 남길 수 있습니다.')
                    try:
                        insights.set_feedback(owner, body['topic_id'], problem_key, body['verdict'], shared=shared)
                    except ValueError:
                        raise AppError('지원하는 평가 항목을 선택해 주세요.') from None
                    return self.send_json(200, {'topic_id': body['topic_id'], 'verdict': body['verdict']})
                if method == 'POST' and path == '/api/briefing/refresh':
                    body = self.json_body()
                    if set(body) != {'request_id'}:
                        raise AppError('새 소식 수집에는 요청 번호만 보낼 수 있습니다.')
                    if isinstance(body['request_id'], str) and body['request_id'].startswith('scheduled-'):
                        raise AppError('예약 수집용 요청 번호는 사용할 수 없습니다.')
                    return self.send_json(202, {'job': briefing.refresh(body['request_id'])})
                if path == '/api/research':
                    if method == 'GET':
                        topics = workflows.research_topics(owner)
                        return self.send_json(200, {'topics': topics,
                            'feedback': insights.feedback_for(owner, [topic['id'] for topic in topics])})
                    if method == 'POST':
                        return self.send_json(202,workflows.research(owner,self.json_body()))
                    if method == 'DELETE':
                        workflows.delete_research(owner)
                        return self.send_json(200,{'deleted':True})
                if method == 'POST' and path == '/api/compose':
                    return self.send_json(202,workflows.compose(owner,self.json_body()))
                if method == 'GET' and path == '/api/jobs':
                    return self.send_json(200,{'jobs':jobs.list(owner)})
                job_match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})',path)
                if job_match:
                    if method == 'GET':
                        return self.send_json(200,jobs.get(owner,job_match.group(1)))
                    if method == 'DELETE':
                        jobs.delete(owner,job_match.group(1))
                        return self.send_json(200,{'deleted':True})
                if path == '/api/drafts':
                    if method == 'GET':
                        return self.send_json(200, {'drafts': service.list(owner)})
                    if method == 'POST':
                        return self.send_json(201, service.create(self.json_body(),owner))
                match = re.fullmatch(r'/api/drafts/([a-f0-9]{32})(?:/(review|exports|revise|download/(?:pdf|docx)))?', path)
                if match:
                    identifier, action = match.groups()
                    if action is None:
                        if method == 'GET':
                            return self.send_json(200, service.get(identifier,owner))
                        if method == 'PATCH':
                            return self.send_json(200, service.update(identifier, self.json_body(),owner))
                        if method == 'DELETE':
                            workflows.delete_draft(owner,identifier)
                            return self.send_json(200, {'deleted': True})
                    if method == 'POST' and action == 'revise':
                        return self.send_json(202,workflows.revise(owner,identifier,self.json_body()))
                    if method == 'POST' and action in ('review', 'exports'):
                        body = self.json_body()
                        fn = service.review if action == 'review' else service.export
                        return self.send_json(200, fn(identifier, body.get('revision'),owner))
                    if method == 'GET' and action and action.startswith('download/'):
                        fmt = action.split('/')[1]
                        try:
                            revision = int(parse_qs(url.query).get('revision', [''])[0])
                        except ValueError:
                            raise AppError('다운로드 버전을 확인해 주세요.')
                        with service.lock:
                            data = service.download(identifier, fmt, revision,owner).read_bytes()
                        mime = ('application/pdf' if fmt == 'pdf' else
                                'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                        return self.send_data(200, data, mime, f'clinic-brief-r{revision}.{fmt}')
                raise AppError('요청한 경로를 찾을 수 없습니다.', 404)
            except (AppError,AuthError,JobError) as exc:
                self.send_json(exc.status, {'error': str(exc)})
            except ProviderError:
                self.send_json(502,{'error':'AI 연결을 완료하지 못했습니다. 설정과 작업 상태를 확인해 주세요.'})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send_json(500, {'error': '처리 중 오류가 발생했습니다. 저장된 작업을 다시 열어 시도해 주세요.'})

        do_GET = handle_request
        do_POST = handle_request
        do_PATCH = handle_request
        do_DELETE = handle_request

    class LocalServer(ThreadingHTTPServer):
        def server_close(self):
            super().server_close()
            briefing.shutdown()
            jobs.shutdown()

    server = LocalServer(('127.0.0.1', port), Handler)
    server.jobs, server.auth, server.workflows = jobs,auth,workflows
    server.briefing = briefing
    server.insights = insights
    return server


def main():
    parser = argparse.ArgumentParser(description='Clinic Brief Phase 2 local workflow')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=ROOT / '.local-data')
    parser.add_argument('--no-auto-briefing', action='store_true',
                        help='Disable scheduled public news collection; manual refresh remains available')
    args = parser.parse_args()
    os.umask(0o077)
    server = make_server(BrochureService(args.data_dir), args.port,
                         auto_briefing=not args.no_auto_briefing)
    server.briefing.start()
    print(f'Clinic Brief: http://127.0.0.1:{server.server_port}', flush=True)
    print('Phase 2 local validation. Sign in to access your saved work.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
