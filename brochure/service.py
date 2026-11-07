"""Revision-aware local workflow. No AI or search call is disguised as a fixture."""
import copy
import hashlib
import json
import re
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .catalog import load_topics
from .storage import DraftStore, LEGACY_OWNER


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')


def sender_values(body):
    result = {}
    for field, limit, label in [('name', 40, '보내는 분'), ('contact', 100, '연락처')]:
        value = body.get('sender_' + field, '')
        if not isinstance(value, str) or len(value) > limit:
            raise AppError(f'{label}는 {limit}자 이내의 텍스트로 입력해 주세요.')
        if any(ord(c) < 32 or 0x7F <= ord(c) <= 0x9F or 0xD800 <= ord(c) <= 0xDFFF or ord(c) in (0xFFFE, 0xFFFF)
               for c in value):
            raise AppError(f'{label}에 사용할 수 없는 문자가 있습니다.')
        result[field] = value.strip()
    return result


def empty_exports():
    return {fmt: {'status': 'pending', 'url': None, 'error': None} for fmt in ('docx', 'pdf')}


class BrochureService:
    def __init__(self, data_dir: Path, renderers=None):
        self.data_dir = Path(data_dir)
        self.store = DraftStore(self.data_dir / 'drafts.sqlite3')
        self.artifacts = self.data_dir / 'artifacts'
        self.topics = load_topics()
        self.lock = threading.RLock()
        if renderers is None:
            from .rendering import render_docx, render_pdf
            renderers = (render_docx, render_pdf)
        self.render_docx, self.render_pdf = renderers

    def list(self, owner=LEGACY_OWNER):
        return self.store.all(owner)

    def get(self, identifier, owner=LEGACY_OWNER):
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise AppError('저장된 작업을 찾을 수 없습니다.', 404)
        draft = self.store.get(identifier, owner)
        if draft is None:
            raise AppError('저장된 작업을 찾을 수 없습니다.', 404)
        return draft

    def create(self, body, owner=LEGACY_OWNER):
        sender = sender_values(body)
        request_id = body.get('request_id')
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', request_id):
            raise AppError('요청 식별자가 올바르지 않습니다. 화면을 새로 열어 주세요.')
        topic_id = body.get('topic_id')
        topic = next((t for t in self.topics if t['id'] == topic_id), None)
        if topic is None:
            raise AppError('목록에서 주제를 선택해 주세요.')
        signature = hashlib.sha256(json.dumps([topic_id, sender], sort_keys=True).encode()).hexdigest()
        with self.lock:
            existing = self.store.by_request(request_id, owner)
            if existing:
                if existing[0] != signature:
                    raise AppError('같은 요청으로 다른 내용을 만들 수 없습니다. 다시 선택해 주세요.', 409)
                return existing[1]
            brochure = copy.deepcopy(topic['brochure'])
            brochure['sender'] = sender
            draft = dict(id=uuid.uuid4().hex, topic_id=topic_id, revision=1,
                         created_at=now(), updated_at=now(), status='draft', brochure=brochure,
                         notes=copy.deepcopy(topic['notes']), sources=copy.deepcopy(topic['sources']),
                         research_date=topic['research_date'], evidence_notice=topic['evidence_notice'],
                         exports=empty_exports(), origin='example', selected_topic=copy.deepcopy(topic), company_text='', quality_notes=[])
            self.store.insert(request_id, signature, draft, owner)
            return draft

    def check_revision(self, draft, revision):
        if type(revision) is not int or revision != draft['revision']:
            raise AppError('작업 버전이 변경되었습니다. 저장된 작업을 다시 열어 주세요.', 409)

    def save_composition(self, owner, topic, result, sender, company_text, request_id):
        from .provider import validate_composition
        validate_composition(result, topic)
        with self.lock:
            brochure = copy.deepcopy(result['brochure'])
            brochure['sender'] = sender
            draft = dict(id=uuid.uuid4().hex, topic_id=topic['id'], revision=1,
                         created_at=now(), updated_at=now(), status='draft', brochure=brochure,
                         notes=copy.deepcopy(result['notes']), sources=copy.deepcopy(topic['sources']),
                         research_date=topic['research_date'], evidence_notice=topic['evidence_notice'],
                         exports=empty_exports(), origin='company' if company_text else 'ai',
                         selected_topic=copy.deepcopy(topic), company_text=company_text,
                         input_notice='선택한 근거와 입력 자료를 외부 AI로 처리했습니다. 원문과 함께 검토해 주세요.',
                         quality_notes=result.get('quality_notes', []))
            signature = hashlib.sha256(json.dumps([topic['id'],company_text,sender],sort_keys=True).encode()).hexdigest()
            existing = self.store.by_request(request_id, owner)
            if existing:
                if existing[0] != signature or existing[1].get('origin') != draft['origin']:
                    raise AppError('같은 요청으로 다른 내용을 만들 수 없습니다. 다시 선택해 주세요.', 409)
                return existing[1]
            self.store.insert(request_id, signature, draft, owner)
            return draft

    def replace_composition(self, owner, identifier, revision, result):
        from .provider import validate_composition
        with self.lock:
            draft = self.get(identifier, owner)
            self.check_revision(draft, revision)
            topic = draft['selected_topic']
            validate_composition(result, topic)
            brochure = copy.deepcopy(result['brochure'])
            brochure['sender'] = draft['brochure']['sender']
            draft.update(brochure=brochure, notes=copy.deepcopy(result['notes']),
                         quality_notes=result.get('quality_notes', []), revision=revision+1,
                         status='draft', updated_at=now(), exports=empty_exports())
            self.store.save(draft, owner)
            shutil.rmtree(self.artifacts / identifier, ignore_errors=True)
            return draft

    def update(self, identifier, body, owner=LEGACY_OWNER):
        sender = sender_values(body)
        with self.lock:
            draft = self.get(identifier, owner)
            self.check_revision(draft, body.get('revision'))
            if draft['brochure']['sender'] == sender:
                return draft
            draft['brochure']['sender'] = sender
            draft['revision'] += 1
            draft['status'] = 'draft'
            draft['updated_at'] = now()
            draft['exports'] = empty_exports()
            self.store.save(draft, owner)
            shutil.rmtree(self.artifacts / identifier, ignore_errors=True)
            return draft

    def review(self, identifier, revision, owner=LEGACY_OWNER):
        with self.lock:
            draft = self.get(identifier, owner)
            self.check_revision(draft, revision)
            if draft['status'] == 'draft':
                draft['status'] = 'reviewed'
                draft['updated_at'] = now()
                self.store.save(draft, owner)
            return draft

    def _path(self, draft, fmt):
        return self.artifacts / draft['id'] / f"r{draft['revision']}" / f'brochure.{fmt}'

    def export(self, identifier, revision, owner=LEGACY_OWNER):
        # One bounded rendering operation at a time; callers retry explicitly, never indefinitely.
        if not self.lock.acquire(blocking=False):
            raise AppError('다른 작업을 처리 중입니다. 잠시 후 다시 시도해 주세요.', 409)
        try:
            draft = self.get(identifier, owner)
            self.check_revision(draft, revision)
            if draft['status'] == 'draft':
                raise AppError('브로셔와 담당자 설명을 확인한 뒤 검토를 완료해 주세요.', 409)
            for fmt in ('docx', 'pdf'):
                path = self._path(draft, fmt)
                if draft['exports'][fmt]['status'] == 'ready' and path.exists() and path.stat().st_size:
                    continue
                draft['status'] = 'reviewed'
                result = draft['exports'][fmt]
                result.update(status='pending', url=None, error=None)
                self.store.save(draft, owner)
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if fmt == 'docx':
                        self.render_docx(draft, path)
                    else:
                        self.render_pdf(self._path(draft, 'docx'), path)
                    if not path.is_file() or path.stat().st_size == 0:
                        raise RuntimeError('Renderer produced no file')
                    result.update(status='ready', error=None,
                                  url=f'/api/drafts/{identifier}/download/{fmt}?revision={revision}')
                except Exception:
                    path.unlink(missing_ok=True)
                    result.update(status='failed', url=None, error=(
                        'DOCX 생성에 실패했습니다. 입력과 설치 상태를 확인한 뒤 다시 시도해 주세요.'
                        if fmt == 'docx' else
                        'PDF 변환에 실패했습니다. LibreOffice 설치 상태를 확인한 뒤 다시 시도해 주세요. DOCX는 보존됩니다.'))
                    self.store.save(draft, owner)
                    break
                self.store.save(draft, owner)
            if all(item['status'] == 'ready' for item in draft['exports'].values()):
                draft['status'] = 'exported'
            draft['updated_at'] = now()
            self.store.save(draft, owner)
            return draft
        finally:
            self.lock.release()

    def download(self, identifier, fmt, revision, owner=LEGACY_OWNER):
        draft = self.get(identifier, owner)
        self.check_revision(draft, revision)
        if fmt not in ('pdf', 'docx'):
            raise AppError('지원하지 않는 파일 형식입니다.', 404)
        path = self._path(draft, fmt)
        if (draft['status'] == 'draft' or draft['exports'][fmt]['status'] != 'ready'
                or not path.is_file()):
            raise AppError('파일이 준비되지 않았습니다. 내보내기를 다시 실행해 주세요.', 409)
        return path

    def delete(self, identifier, owner=LEGACY_OWNER):
        with self.lock:
            self.get(identifier, owner)
            directory = self.artifacts / identifier
            if directory.exists():
                shutil.rmtree(directory)
            self.store.delete(identifier, owner)
