(() => {
  'use strict';

  const main = document.getElementById('main-content');
  const live = document.getElementById('live-status');
  const breadcrumb = document.getElementById('breadcrumb');
  const navTopics = document.getElementById('nav-topics');
  const navSaved = document.getElementById('nav-saved');
  const state = {
    page: 'topics', topics: [], drafts: [], active: null, tab: 'brochure',
    sender: { name: '', contact: '' }, visited: new Set(), busy: false,
    loadedTopics: false, error: null, notice: '', requestIds: new Map(),
    session: null, sessionLoaded: false, authMode: 'login', auth: { email: '', password: '' },
    discovery: 'briefing', research: [], category: 'briefing', jobs: [], pollTimer: null, epoch: 0,
    briefing: { items: [], status: null }, briefingLoaded: false, briefingLoading: false,
    briefingError: '', briefingTimer: null, briefingPollDelay: null,
    feedback: { briefing: {}, research: {} }, feedbackVersion: { briefing: 0, research: 0 },
    feedbackPending: new Set(), feedbackErrors: {}, copyMessages: {},
    selected: null, compose: { mode: 'ai', companyText: '', confirmed: false, name: '', contact: '' },
    revision: { instructions: '', confirmed: false }, appliedJobs: new Set(), pendingRequests: {},
    researchResult: null, destinationFocus: null,

  };
  const statusLabels = { draft: '검토 전', reviewed: '검토 완료', exported: '파일 준비 완료' };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function append(parent, ...children) {
    parent.append(...children.filter(Boolean));
    return parent;
  }
  function button(label, className, action, disabled = false) {
    const node = el('button', className, label);
    node.type = 'button';
    node.disabled = disabled || state.busy;
    node.addEventListener('click', action);
    return node;
  }
  function tag(text, tone = '') { return el('span', `tag ${tone}`, text); }
  function date(value) {
    if (!value) return '날짜 미표기';
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
    return match ? `${match[1]}.${match[2]}.${match[3]}` : String(value);
  }
  function koreanTime(value) {
    if (!value) return '';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '';
    return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(parsed);
  }
  function announce(message) { live.textContent = message; }
  function focusMain() { main.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'auto' }); }
  function safeSourceUrl(value) {
    try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; }
    catch { return null; }
  }
  function sourceLink(source, label) {
    const url = safeSourceUrl(source.url);
    if (!url) return el('span', '', label || source.title);
    const link = el('a', 'source-link', label || source.title);
    link.setAttribute('href', url);
    link.setAttribute('target', '_blank');
    link.setAttribute('rel', 'noopener noreferrer');
    link.setAttribute('aria-label', `${label || source.title} (새 창)`);
    return link;
  }
  function hasSenderChanges() {
    const sender = state.active?.brochure?.sender || {};
    return !!state.active && (state.sender.name !== (sender.name || '') || state.sender.contact !== (sender.contact || ''));
  }
  function approveDiscard() {
    return !hasSenderChanges() || window.confirm('저장하지 않은 전달자 정보가 있습니다. 이 수정을 버리고 다른 작업을 여시겠어요?');
  }
  function visitedKey(tab) { return `${state.active.id}:${state.active.revision}:${tab}`; }
  function reviewedBoth() { return ['brochure', 'notes'].every(tab => state.visited.has(visitedKey(tab))); }
  function acceptDraft(draft, resetTab = false) {
    state.active = draft;
    state.revision = { instructions: '', confirmed: false };
    state.sender = { name: draft.brochure.sender?.name || '', contact: draft.brochure.sender?.contact || '' };
    if (resetTab) state.tab = 'brochure';
    const index = state.drafts.findIndex(item => item.id === draft.id);
    if (index >= 0) state.drafts[index] = draft;
  }
  function topicKey(source, topic) { return `${source}-${topic.id}`; }
  function acceptFeedback(source, feedback, version) {
    if (version !== state.feedbackVersion[source] || [...state.feedbackPending].some(key => key.startsWith(`${source}-`))) return;
    state.feedback[source] = Object.fromEntries(Object.entries(feedback || {}).filter(([, verdict]) => ['useful', 'not_useful', 'seen'].includes(verdict)));
  }
  async function setTopicFeedback(topic, source, verdict) {
    if (!state.session?.user || !['briefing', 'research'].includes(source) || !['useful', 'not_useful', 'seen'].includes(verdict)) return;
    const key = topicKey(source, topic);
    if (state.feedbackPending.has(key) || state.feedback[source][topic.id] === verdict) return;
    const epoch = state.epoch;
    state.feedbackVersion[source] += 1; state.feedbackPending.add(key); delete state.feedbackErrors[key]; render();
    try {
      const result = await api('/api/topic-feedback', 'POST', { topic_id: topic.id, source, verdict });
      if (epoch !== state.epoch) return;
      state.feedback[source][result.topic_id] = result.verdict;
      announce('의견을 저장했습니다.');
    } catch (error) {
      if (epoch === state.epoch) state.feedbackErrors[key] = '의견을 저장하지 못했습니다. 이전 선택은 유지됩니다. 다시 눌러 저장해주세요.';
    } finally {
      if (epoch === state.epoch) { state.feedbackVersion[source] += 1; state.feedbackPending.delete(key); render(); }
    }
  }
  function copyThroughSelection(text) {
    if (typeof document.execCommand !== 'function') return false;
    const focused = document.activeElement;
    const selection = window.getSelection?.();
    const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index).cloneRange()) : [];
    const temporary = el('textarea', 'sr-only');
    temporary.value = text; temporary.readOnly = true; temporary.tabIndex = -1;
    temporary.setAttribute('aria-label', '복사할 자료 본문');
    try {
      document.body.append(temporary);
      temporary.focus({ preventScroll: true }); temporary.select();
      temporary.setSelectionRange(0, temporary.value.length);
      return document.execCommand('copy') === true;
    } catch {
      return false;
    } finally {
      temporary.remove(); focused?.focus({ preventScroll: true });
      if (selection) { selection.removeAllRanges(); ranges.forEach(range => selection.addRange(range)); }
    }
  }
  async function copyReady(topic, source) {
    const epoch = state.epoch;
    const key = topicKey(source, topic);
    const focused = document.activeElement;
    try {
      // Keep native copy in the click gesture; some embedded browsers silently drop async writes.
      if (!copyThroughSelection(topic.ready_to_use.body)) {
        if (!window.navigator?.clipboard?.writeText) throw new Error('Clipboard unavailable');
        await window.navigator.clipboard.writeText(topic.ready_to_use.body);
      }
      if (epoch !== state.epoch) return;
      state.copyMessages[key] = { text: '붙여넣어 확인하세요. 안 되면 본문 선택 후 직접 복사해주세요.', error: false };
    } catch (error) {
      if (epoch !== state.epoch) return;
      state.copyMessages[key] = { text: '자동 복사를 사용할 수 없습니다. 본문 선택 후 Ctrl+C 또는 ⌘C로 복사해주세요.', error: true };
    }
    const restoreFocus = document.activeElement === focused;
    announce(state.copyMessages[key].text); render();
    if (restoreFocus && focused?.id) document.getElementById(focused.id)?.focus({ preventScroll: true });
  }

  async function api(path, method = 'GET', body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const response = await fetch(path, {
        method, signal: controller.signal, credentials: 'same-origin',
        headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
          ...(method !== 'GET' && state.session?.csrf_token ? { 'X-CSRF-Token': state.session.csrf_token } : {}), },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      let data;
      try { data = await response.json(); }
      catch { throw new Error('서버 응답을 읽지 못했습니다. 로컬 앱이 실행 중인지 확인한 뒤 다시 시도해주세요.'); }
      if (!response.ok) {
        const error = new Error(data.error || '요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.');
        error.status = response.status;
        if (response.status === 401 && !path.startsWith('/api/auth/')) { clearSession(); render(); }
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('서버 응답을 확인하지 못했습니다. 내 작업에서 진행 상태를 먼저 확인하세요. 같은 입력의 재전송은 기존 요청 번호를 사용합니다.');
      if (error instanceof TypeError || error.name === 'TypeError') throw new Error('로컬 앱에 연결하지 못했습니다. 서버에서 작업이 시작되었을 수 있습니다. 진행 상태를 먼저 확인하세요. 같은 입력은 기존 요청 번호로 재전송됩니다.');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  async function act(label, action) {
    if (state.busy) return;
    state.busy = true;
    state.error = null;
    state.notice = label;
    announce(label);
    render();
    try { await action(); }
    catch (error) {
      state.error = { message: error.message, stale: error.status === 409 };
      state.notice = '';
      announce(error.message);
    } finally { state.busy = false; render(); }
  }
  async function loadTopics() {
    await act('조사된 예제를 불러오고 있습니다.', async () => {
      const data = await api('/api/topics');
      state.topics = data.topics;
      state.loadedTopics = true;
      state.notice = '';
    });
  }
  async function showSaved() {
    if (!state.session?.user || !approveDiscard()) return;
    state.page = 'saved';
    await act('저장된 작업을 불러오고 있습니다.', async () => {
      await loadOwned();
      state.notice = '';
    });
    focusMain();
  }
  async function createDraft(topic) {
    if (!approveDiscard()) return;
    if (!state.requestIds.has(topic.id)) state.requestIds.set(topic.id, crypto.randomUUID());
    await act('선택한 예제로 자료를 구성하고 있습니다.', async () => {
      const draft = await api('/api/drafts', 'POST', {
        topic_id: topic.id, sender_name: '', sender_contact: '', request_id: state.requestIds.get(topic.id),
      });
      state.requestIds.delete(topic.id);
      acceptDraft(draft, true);
      state.page = 'workspace';
      state.notice = '예제 자료가 저장되었습니다. 두 화면을 확인한 뒤 검토를 완료해주세요.';
      announce(state.notice);
    });
    if (state.page === 'workspace') focusMain();
  }
  async function openDraft(id) {
    if (!approveDiscard()) return;
    await act('저장된 작업을 열고 있습니다.', async () => {
      acceptDraft(await api(`/api/drafts/${encodeURIComponent(id)}`), true);
      state.page = 'workspace';
      state.notice = '저장된 내용으로 작업을 열었습니다.';
      announce(state.notice);
    });
    if (state.page === 'workspace') focusMain();
  }
  async function saveSender() {
    if (!hasSenderChanges()) return;
    const { name, contact } = state.sender;
    if (name.length > 40 || contact.length > 100 || /[\u0000-\u001f\u007f-\u009f]/.test(name + contact)) {
      state.error = { message: '이름은 40자, 연락처는 100자 이내로 입력하고 줄바꿈·제어 문자를 제외해주세요.' };
      render();
      return;
    }
    await act('전달자 정보를 저장하고 있습니다.', async () => {
      acceptDraft(await api(`/api/drafts/${encodeURIComponent(state.active.id)}`, 'PATCH', {
        revision: state.active.revision, sender_name: name, sender_contact: contact,
      }), true);
      state.notice = '전달자 정보를 저장했습니다. 바뀐 버전의 두 화면을 확인하고 다시 검토해주세요.';
      announce(state.notice);
    });
  }
  async function reviewDraft() {
    if (hasSenderChanges() || !reviewedBoth()) return;
    await act('현재 버전의 검토를 기록하고 있습니다.', async () => {
      acceptDraft(await api(`/api/drafts/${encodeURIComponent(state.active.id)}/review`, 'POST', { revision: state.active.revision }));
      state.notice = '검토를 완료했습니다. 이제 PDF와 DOCX 파일을 만들 수 있습니다.';
      announce(state.notice);
    });
  }
  async function exportDraft() {
    if (hasSenderChanges() || !['reviewed', 'exported'].includes(state.active.status)) return;
    await act('PDF와 DOCX 파일을 만들고 있습니다. PDF 변환에는 잠시 시간이 걸릴 수 있습니다.', async () => {
      acceptDraft(await api(`/api/drafts/${encodeURIComponent(state.active.id)}/exports`, 'POST', { revision: state.active.revision }));
      const failed = Object.values(state.active.exports).some(item => item.status === 'failed');
      state.notice = failed ? '일부 파일을 만들지 못했습니다. 준비된 파일은 내려받을 수 있으며, 실패한 변환은 다시 시도할 수 있습니다.' : '파일이 준비되었습니다. 아래에서 각각 내려받으세요.';
      announce(state.notice);
    });
  }
  async function deleteDraft(draft) {
    if (!window.confirm(`“${draft.brochure.title}” 작업을 삭제할까요? 저장된 내용과 이 작업의 다운로드 파일이 함께 삭제됩니다. 이 작업은 되돌릴 수 없습니다.`)) return;
    await act('작업을 삭제하고 있습니다.', async () => {
      await api(`/api/drafts/${encodeURIComponent(draft.id)}`, 'DELETE');
      state.drafts = state.drafts.filter(item => item.id !== draft.id);
      removeJobSnapshots(job => job.result?.draft?.id === draft.id);
      if (state.active?.id === draft.id) { state.active = null; state.sender = { name: '', contact: '' }; }
      state.notice = '작업을 삭제했습니다.';
      announce(state.notice);
    });
  }

  function messages() {
    const wrapper = el('div', 'messages');
    if (state.error) {
      const box = el('div', 'notice error');
      box.setAttribute('role', 'alert');
      append(box, el('p', '', state.error.message));
      if (state.error.stale && state.active) append(box, button('저장된 버전 다시 열기', 'text-button', () => openDraft(state.active.id)));
      append(wrapper, box);
    }
    if (state.notice) append(wrapper, append(el('div', `notice ${state.busy ? 'working' : ''}`), state.busy ? el('span', 'loading-dot') : null, el('p', '', state.notice)));
    return wrapper;
  }
  const jobLabels = { research: '공개 출처 조사', compose: '두 자료 구성', revise: '두 자료 수정' };
  const jobStatusLabels = { queued: '대기 중', running: '진행 중', succeeded: '완료', failed: '실패', interrupted: '중단됨' };
  function activeJob() { return state.jobs.some(job => ['queued', 'running'].includes(job.status)); }
  function stopPolling() { clearTimeout(state.pollTimer); state.pollTimer = null; }
  function briefingVisible() { return !!state.session?.user && state.page === 'topics' && state.discovery === 'briefing' && !document.hidden; }
  function briefingRunning() { return ['queued', 'running'].includes(state.briefing.status?.last_attempt?.status); }
  function stopBriefingPolling() { clearTimeout(state.briefingTimer); state.briefingTimer = null; state.briefingPollDelay = null; }
  function scheduleBriefingPolling() {
    if (!briefingVisible() || state.briefingLoading) { stopBriefingPolling(); return; }
    const delay = briefingRunning() ? 2000 : 60000;
    if (state.briefingTimer && state.briefingPollDelay === delay) return;
    stopBriefingPolling(); state.briefingPollDelay = delay;
    state.briefingTimer = setTimeout(loadBriefing, delay);
  }
  async function loadBriefing() {
    if (!state.session?.user || state.briefingLoading) return;
    stopBriefingPolling();
    const epoch = state.epoch;
    const feedbackVersion = state.feedbackVersion.briefing;
    state.briefingLoading = true;
    try {
      const data = await api('/api/briefing');
      if (epoch !== state.epoch || !state.session?.user) return;
      state.briefing = data; state.briefingLoaded = true; state.briefingError = '';
      acceptFeedback('briefing', data.feedback, feedbackVersion);
      const request = state.pendingRequests['briefing-refresh'];
      const attempt = data.status?.last_attempt;
      if (request && attempt && !['queued', 'running'].includes(attempt.status) && (request.job === attempt.id || request.id === attempt.request_id)) {
        delete state.pendingRequests['briefing-refresh']; saveRequests();
      }
    } catch (error) {
      if (epoch !== state.epoch) return;
      state.briefingError = '새 소식 목록을 확인하지 못했습니다. 저장된 글은 그대로 두었습니다. 수집 상태 확인을 눌러 다시 불러오세요.';
    } finally {
      if (epoch === state.epoch) {
        state.briefingLoading = false;
        if (briefingVisible()) render();
        scheduleBriefingPolling();
      }
    }
  }
  async function refreshBriefing() {
    const status = state.briefing.status;
    if (!status?.configured || briefingRunning() || state.briefingLoading || status.remaining_runs <= 0) return;
    await act('새 읽을거리를 모으도록 요청하고 있습니다.', async () => {
      const epoch = state.epoch;
      const request = state.pendingRequests['briefing-refresh'] || { id: crypto.randomUUID() };
      state.pendingRequests['briefing-refresh'] = request; saveRequests();
      try {
        const { job } = await api('/api/briefing/refresh', 'POST', { request_id: request.id });
        if (epoch !== state.epoch) return;
        const terminal = !['queued', 'running'].includes(job.status);
        // The shared last_attempt can belong to a newer user's run. This acknowledgement is authoritative for our request.
        if (terminal) delete state.pendingRequests['briefing-refresh'];
        else request.job = job.id;
        saveRequests();
        state.briefing.status = { ...status, last_attempt: job };
        state.notice = terminal ? '이 수집 요청은 종료되었습니다. 현재 목록과 수집 상태를 확인해주세요.' : '수집 요청을 확인했습니다. 모아 둔 글을 읽으면서 기다리셔도 됩니다.';
        await loadBriefing();
      } catch (error) {
        if (epoch !== state.epoch) return;
        if (error.status && error.status < 500) { delete state.pendingRequests['briefing-refresh']; saveRequests(); }
        await loadBriefing();
        if (epoch !== state.epoch) return;
        state.notice = '';
        state.briefingError = error.status ? error.message : '수집 요청의 접수 여부를 확인하지 못했습니다. 먼저 수집 상태를 확인하세요. 다시 눌러도 같은 요청으로 확인하며, 자동으로 재실행하지 않습니다.';
      }
    });
  }
  function clearSession() {
    stopPolling(); stopBriefingPolling(); state.epoch += 1;
    state.session = null; state.active = null; state.drafts = []; state.research = []; state.jobs = [];
    state.researchResult = null; state.destinationFocus = null;
    state.sender = { name: '', contact: '' }; state.visited.clear(); state.appliedJobs.clear(); state.requestIds.clear();
    state.pendingRequests = {}; state.selected = null; state.compose = { mode: 'ai', companyText: '', confirmed: false, name: '', contact: '' };
    state.revision = { instructions: '', confirmed: false }; state.auth.password = ''; state.page = 'topics';
    state.discovery = 'briefing'; state.briefing = { items: [], status: null }; state.briefingLoaded = false; state.briefingLoading = false; state.briefingError = '';
    state.feedback = { briefing: {}, research: {} }; state.feedbackVersion = { briefing: 0, research: 0 }; state.feedbackPending.clear(); state.feedbackErrors = {}; state.copyMessages = {};
  }
  function requestStorageKey() { return `clinic-brief.requests.${state.session?.user?.id}`; }
  function saveRequests() {
    try { window.sessionStorage.setItem(requestStorageKey(), JSON.stringify(state.pendingRequests)); } catch { /* Current-tab memory still preserves request identity. */ }
  }
  function acceptSession(session) {
    if (state.session?.user && state.session.user.id !== session.user?.id) clearSession();
    state.session = session; state.sessionLoaded = true;
    try { state.pendingRequests = JSON.parse(window.sessionStorage.getItem(requestStorageKey()) || '{}'); } catch { state.pendingRequests = {}; }
  }
  function reconcileRequests() {
    const terminal = new Set(state.jobs.filter(job => !['queued', 'running'].includes(job.status)).map(job => job.id));
    for (const [key, request] of Object.entries(state.pendingRequests)) if (terminal.has(request.job)) delete state.pendingRequests[key];
    saveRequests();
  }
  async function loadOwned() {
    const epoch = state.epoch;
    const feedbackVersion = state.feedbackVersion.research;
    const [research, drafts, jobs] = await Promise.all([api('/api/research'), api('/api/drafts'), api('/api/jobs')]);
    if (epoch !== state.epoch || !state.session?.user) return;
    state.research = research.topics; state.drafts = drafts.drafts; state.jobs = jobs.jobs;
    acceptFeedback('research', research.feedback, feedbackVersion);
    reconcileRequests(); schedulePolling();
  }
  async function bootstrap() {
    await act('로컬 계정과 AI 연결 상태를 확인하고 있습니다.', async () => {
      acceptSession(await api('/api/session'));
      if (state.session.user) await Promise.all([loadOwned(), loadBriefing()]);
      state.notice = '';
    });
  }
  async function authenticate() {
    const { email, password } = state.auth;
    if (!email.trim() || password.length < 12 || password.length > 128) {
      state.error = { message: '이메일과 12–128자의 비밀번호를 입력해주세요.' }; render(); return;
    }
    await act(state.authMode === 'register' ? '로컬 계정을 만들고 있습니다.' : '로그인하고 있습니다.', async () => {
      acceptSession(await api(`/api/auth/${state.authMode}`, 'POST', { email: email.trim(), password }));
      state.auth.password = ''; await Promise.all([loadOwned(), loadBriefing()]); state.notice = '';
    });
  }
  async function logout() {
    if (!approveDiscard()) return;
    await act('로그아웃하고 있습니다.', async () => {
      await api('/api/auth/logout', 'POST', {}); clearSession(); state.notice = '로그아웃했습니다. 진행 중인 서버 작업은 계정에 저장됩니다.';
    });
  }
  function schedulePolling() {
    stopPolling();
    if (state.session?.user && activeJob()) state.pollTimer = setTimeout(pollJobs, 1500);
  }
  function shouldOpenCompletedJob(job) {
    if (state.page === 'compose' && job.kind === 'research') return false;
    return state.page !== 'workspace' || !state.active || (job.result?.draft?.id === state.active.id && !hasSenderChanges());
  }
  async function applyCompletedJob(job, open = false) {
    if (job.status !== 'succeeded') return;
    const shouldOpen = () => typeof open === 'function' ? open() : open;
    if (job.kind === 'research' && Array.isArray(job.result?.topics)) {
      if (open === true && !approveDiscard()) return;
      // Saved candidates are authoritative; old job results cannot resurrect deleted research.
      const epoch = state.epoch;
      const feedbackVersion = state.feedbackVersion.research;
      const research = await api('/api/research');
      if (epoch !== state.epoch || !state.session?.user || !state.jobs.some(item => item.id === job.id)) return;
      state.research = research.topics;
      acceptFeedback('research', research.feedback, feedbackVersion);
      if (shouldOpen()) {
        state.researchResult = job; state.discovery = 'research'; state.page = 'research-result';
        state.destinationFocus = 'research-result-title';
      }
    } else if (job.result?.draft && shouldOpen()) {
      if (open === true && !approveDiscard()) return;
      // Fetch the latest version: a historical job may refer to an older revision.
      const epoch = state.epoch;
      const draft = await api(`/api/drafts/${encodeURIComponent(job.result.draft.id)}`);
      if (epoch !== state.epoch || !state.session?.user || !state.jobs.some(item => item.id === job.id) || !shouldOpen()) return;
      acceptDraft(draft, true); state.page = 'workspace'; state.destinationFocus = 'main-content';
    }
  }
  async function pollJobs() {
    stopPolling();
    if (!state.session?.user) return;
    if (state.busy) { schedulePolling(); return; }
    const epoch = state.epoch;
    try {
      const active = state.jobs.filter(job => ['queued', 'running'].includes(job.status));
      const updates = await Promise.all(active.map(job => api(`/api/jobs/${encodeURIComponent(job.id)}`)));
      if (epoch !== state.epoch || !state.session?.user) return;
      let changed = false;
      for (const update of updates) {
        const index = state.jobs.findIndex(job => job.id === update.id);
        // Deletion can finish while this poll is in flight; never reapply its old result.
        if (index < 0) continue;
        if (JSON.stringify(state.jobs[index]) !== JSON.stringify(update)) changed = true;
        state.jobs[index] = update;
        if (!['queued', 'running'].includes(update.status) && !state.appliedJobs.has(update.id)) {
          state.appliedJobs.add(update.id);
          for (const [key, request] of Object.entries(state.pendingRequests)) if (request.job === update.id) delete state.pendingRequests[key];
          saveRequests();
          if (update.status === 'succeeded') {
            // Do not overwrite another open draft while a background task finishes.
            await applyCompletedJob(update, () => shouldOpenCompletedJob(update));
            if (epoch !== state.epoch) return;
            state.notice = update.kind === 'research' && update.result?.selection_report?.selected_count === 0 ? '이번에는 새로 제안할 만한 주제를 찾지 못했습니다. 저장된 조사는 유지됩니다.' : `${jobLabels[update.kind]} 작업이 완료되었습니다. 근거와 내용을 직접 확인해주세요.`;
          } else state.error = { message: update.error || '작업이 중단되었습니다. 내용은 다시 제출할 때만 처리됩니다.' };
          announce(state.notice || state.error?.message);
        }
      }
      if (changed) render();
      schedulePolling();
    } catch (error) {
      if (epoch !== state.epoch) return;
      state.error = { message: `작업 상태를 확인하지 못했습니다. ${error.message} ‘진행 상태 확인’을 눌러 다시 확인하세요.` }; render();
    }
  }
  async function refreshJobs() {
    await act('진행 상태를 확인하고 있습니다.', async () => {
      const before = new Set(state.jobs.filter(job => ['queued', 'running'].includes(job.status)).map(job => job.id));
      state.jobs = (await api('/api/jobs')).jobs;
      reconcileRequests();
      for (const job of state.jobs) if (before.has(job.id) && job.status === 'succeeded') await applyCompletedJob(job, () => shouldOpenCompletedJob(job));
      schedulePolling(); state.notice = '서버의 진행 상태를 확인했습니다.';
    });
  }
  async function submitJob(path, body, label) {
    if (!state.session?.provider?.configured || activeJob()) return;
    await act(label, async () => {
      // Persist only an input digest and opaque request ID, never private input or credentials.
      const bytes = new TextEncoder().encode(JSON.stringify({ path, body }));
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
      const request = state.pendingRequests[hash] || { id: crypto.randomUUID() };
      state.pendingRequests[hash] = request; saveRequests();
      let job;
      try { job = await api(path, 'POST', { ...body, request_id: request.id }); }
      catch (error) {
        // A definitive rejection allows an explicit new submission. Unknown outcomes retain identity.
        if (error.status && error.status < 500) { delete state.pendingRequests[hash]; saveRequests(); }
        throw error;
      }
      request.job = job.id; saveRequests();
      state.jobs = [job, ...state.jobs.filter(item => item.id !== job.id)];
      state.notice = '작업을 접수했습니다. 다른 화면으로 이동하거나 새로고침해도 내 작업에서 이어서 확인할 수 있습니다.';
      if (!['queued', 'running'].includes(job.status)) {
        delete state.pendingRequests[hash]; saveRequests();
        if (job.status === 'succeeded') await applyCompletedJob(job, true);
        else throw new Error(job.error || '작업이 완료되지 않았습니다. 다시 실행하려면 직접 제출해주세요.');
      }
      schedulePolling();
    });
  }
  function removeJobSnapshots(matches) {
    const removed = new Set(state.jobs.filter(matches).map(job => job.id));
    state.jobs = state.jobs.filter(job => !removed.has(job.id));
    if (removed.has(state.researchResult?.id)) {
      state.researchResult = null;
      if (state.page === 'research-result') { state.page = 'topics'; state.discovery = 'research'; state.destinationFocus = 'main-content'; }
    }
    for (const id of removed) state.appliedJobs.delete(id);
    for (const [key, request] of Object.entries(state.pendingRequests)) if (removed.has(request.job)) delete state.pendingRequests[key];
    saveRequests();
  }
  async function clearResearch() {
    if (!window.confirm('저장된 조사 후보를 모두 삭제할까요? 이미 만든 자료는 유지됩니다.')) return;
    await act('저장된 조사를 삭제하고 있습니다.', async () => { await api('/api/research', 'DELETE'); state.research = []; removeJobSnapshots(job => job.kind === 'research');
      state.feedback.research = {}; state.feedbackVersion.research += 1;
      if (state.selected?.source === 'research') { state.selected = null; state.compose = { mode: 'ai', companyText: '', confirmed: false, name: '', contact: '' }; }
      state.notice = '저장된 조사 후보를 삭제했습니다.'; });
  }
  async function deleteJob(job) {
    if (!window.confirm('이 작업 기록과 기록에 저장된 결과를 삭제할까요? 별도로 저장된 자료는 유지됩니다.')) return;
    await act('작업 기록을 삭제하고 있습니다.', async () => {
      await api(`/api/jobs/${encodeURIComponent(job.id)}`, 'DELETE'); removeJobSnapshots(item => item.id === job.id); state.notice = '작업 기록을 삭제했습니다.';
    });
  }
  function field(id, label, value, max, onInput, options = {}) {
    const labelNode = el('label', '', label); labelNode.setAttribute('for', id);
    const input = el(options.multiline ? 'textarea' : 'input'); input.setAttribute('id', id); input.value = value; input.maxLength = max; input.disabled = state.busy;
    if (options.multiline) { input.rows = options.rows || 6; input.placeholder = options.placeholder || ''; }
    else { input.type = options.type || 'text'; input.autocomplete = options.autocomplete || 'off'; }
    if (options.required) input.required = true;
    if (options.type === 'password') input.minLength = 12;
    const counter = el('span', 'input-counter', options.type === 'password' ? '12–128자' : `${value.length}/${max}`);
    counter.setAttribute('id', `${id}-count`); input.setAttribute('aria-describedby', `${id}-count`);
    input.addEventListener('input', event => { onInput(event.target.value); if (options.type !== 'password') counter.textContent = `${event.target.value.length}/${max}`; updateComposeButtons(); });
    return append(el('div', 'field'), append(el('div', 'field-label'), labelNode, counter), input);
  }
  function consent(id, checked, action, wording) {
    const input = el('input'); input.type = 'checkbox'; input.setAttribute('id', id); input.checked = checked; input.disabled = state.busy;
    input.addEventListener('change', event => { action(event.target.checked); updateComposeButtons(); });
    const label = el('label', '', wording); label.setAttribute('for', id);
    return append(el('div', 'consent-field'), input, label);
  }
  function authPage() {
    const page = el('div', 'page auth-page');
    append(page, append(el('section', 'auth-intro'), el('p', 'eyebrow', 'YOUR LOCAL WORKSPACE'), el('h1', '', '준비한 이야기를,\n내 작업 공간에.'), el('p', 'muted', '계정별로 조사와 자료를 보관하고, 원장님께 드릴 안내자료와 담당자 메모를 함께 준비하세요.'), tag('2단계 로컬 검증 · SaaS 출시 전')));
    const panel = el('section', 'auth-card'); append(panel, el('h2', '', state.authMode === 'login' ? '로그인' : '로컬 계정 만들기'), el('p', 'muted small', '이 컴퓨터의 계정입니다. 이메일은 식별자로만 사용하며 인증 메일을 보내지 않습니다. 비밀번호 재설정은 지원하지 않습니다.'), messages());
    const form = el('form', 'auth-form');
    form.addEventListener('submit', event => { event.preventDefault(); authenticate(); });
    append(form, field('auth-email', '이메일', state.auth.email, 254, value => { state.auth.email = value; }, { type: 'email', autocomplete: 'username', required: true }), field('auth-password', '비밀번호', state.auth.password, 128, value => { state.auth.password = value; }, { type: 'password', autocomplete: state.authMode === 'login' ? 'current-password' : 'new-password', required: true }), button(state.authMode === 'login' ? '로그인하기' : '계정 만들기', 'button primary full-width', authenticate));
    append(panel, form, button(state.authMode === 'login' ? '처음이신가요? 로컬 계정 만들기' : '기존 계정으로 로그인', 'text-button auth-switch', () => { state.authMode = state.authMode === 'login' ? 'register' : 'login'; state.error = null; state.auth.password = ''; render(); }));
    append(page, panel); return page;
  }
  function providerPanel() {
    const provider = state.session?.provider;
    const panel = el('div', `provider-panel ${provider?.configured ? 'configured' : ''}`);
    append(panel, append(el('div'), el('strong', '', provider?.configured ? `AI 연결 준비됨 · ${provider.model}` : '실시간 조사와 AI 구성은 연결 설정이 필요합니다'), el('p', '', provider?.configured ? '실행 시 외부 OpenAI API를 사용하며 사용료가 발생할 수 있습니다. 조사 범주만 공개 검색에 사용합니다.' : '서버 환경 또는 .env.local에 기존 OPENAI_API_KEY를 직접 설정한 뒤 서버를 재시작하세요. 키는 브라우저에 입력하지 않습니다. 준비된 예제는 지금 사용할 수 있습니다.')), button('연결 상태 확인', 'text-button', async () => { await act('AI 연결 상태를 확인하고 있습니다.', async () => { acceptSession(await api('/api/session')); if (state.discovery === 'briefing') await loadBriefing(); state.notice = '연결 상태를 확인했습니다.'; }); }));
    return panel;
  }
  function discoveryPanel() {
    const panel = el('section', 'discovery-panel');
    const modes = el('div', 'mode-tabs'); modes.setAttribute('aria-label', '자료 시작 방식');
    for (const [mode, label] of [['briefing', '새 소식'], ['research', '직접 조사'], ['examples', '준비된 예제']]) {
      const choice = button(label, state.discovery === mode ? 'mode-button selected' : 'mode-button', async () => { state.discovery = mode; state.error = null; state.notice = ''; render(); if (mode === 'briefing') await loadBriefing(); else if (mode === 'examples' && !state.loadedTopics) await loadTopics(); });
      choice.setAttribute('aria-pressed', String(state.discovery === mode)); append(modes, choice);
    }
    append(panel, modes);
    if (state.discovery === 'examples') append(panel, el('p', 'discovery-help', '미리 준비한 예제입니다. 실시간 조사 결과와 구분됩니다. “예제 그대로 만들기”는 AI 호출 없이 저장합니다.'));
    else if (state.discovery === 'research') {
      const controls = el('div', 'research-controls');
      const label = el('label', '', '조사 범주'); label.setAttribute('for', 'research-category');
      const select = el('select'); select.setAttribute('id', 'research-category'); select.disabled = state.busy || activeJob();
      for (const [value, text] of [['briefing', '전체 분야에서 찾기'], ['communication', '진료 설명·직원 소통·환자 안내'], ['operations', '예약·장비·행정·의원 운영'], ['ai-literacy', 'AI 설정·문서 작업·업무 활용']]) { const option = el('option', '', text); option.value = value; option.selected = state.category === value; append(select, option); }
      select.value = state.category; select.addEventListener('change', event => { state.category = event.target.value; });
      append(controls, append(el('div', 'category-field'), label, select), button('실시간 조사 시작', 'button primary', () => submitJob('/api/research', { category: state.category }, '공개 출처 조사를 요청하고 있습니다.'), !state.session?.provider?.configured || activeJob()));
      append(panel, controls, el('p', 'discovery-help', '공개된 의원의 질문·업무 사례와 도구·제도 자료를 살펴보고, 바로 쓸 자료를 만들 수 있는 주제를 최대 3개 고릅니다. 충분한 근거와 활용 가치가 없으면 새 주제를 추가하지 않습니다.'));
    }
    return panel;
  }
  function jobsPanel(history = false) {
    const active = state.jobs.filter(job => ['queued', 'running'].includes(job.status));
    // API history is newest first. Keep old failures in history instead of showing them as current.
    const jobs = history ? state.jobs : active.length ? active : state.jobs.slice(0, 1);
    const panel = el('section', 'jobs-panel');
    append(panel, append(el('div', 'jobs-heading'), el('h2', '', history ? '작업 기록' : '작업 진행 상태'), button('진행 상태 확인', 'text-button', refreshJobs)));
    if (!jobs.length) append(panel, el('p', 'muted small', history ? '아직 실행한 AI 작업이 없습니다.' : '진행 중인 AI 작업이 없습니다. 계정당 한 번에 하나씩 실행합니다.'));
    for (const job of jobs) {
      const card = el('article', 'job-card');
      const researchDone = job.kind === 'research' && job.status === 'succeeded' && Array.isArray(job.result?.topics);
      const count = researchDone ? job.result.topics.length : null;
      const status = researchDone ? count ? `주제 ${count}개 선정` : '선정 주제 없음' : jobStatusLabels[job.status] || job.status;
      const content = append(el('div', 'job-content'), append(el('div', 'job-meta'), tag(status, job.status === 'succeeded' && count !== 0 ? 'green' : ''), el('strong', '', jobLabels[job.kind] || 'AI 작업')), el('p', 'small', job.stage || '상태 확인 중'), job.error ? el('p', 'job-error', job.error) : null);
      if (researchDone) {
        const report = job.result.selection_report;
        if (report) append(content, el('p', 'small', `원문 ${report.sources_read}개 확인 · 후보 ${report.candidates_considered}개 검토`));
        if (count === 0) append(content, el('p', 'selection-empty', '조사를 마쳤지만 선정한 주제가 없습니다. 후보별 이유를 확인해 보세요.'));
      }
      append(card, content);
      const controls = el('div', 'job-actions');
      const label = researchDone ? count ? `선정한 주제 ${count}개 보기` : '선정하지 못한 이유 보기' : '작성 자료 열기';
      if (job.status === 'succeeded' && (researchDone || job.result?.draft)) append(controls, button(label, 'button secondary small-button', () => act('작업 결과를 열고 있습니다.', async () => { await applyCompletedJob(job, true); state.notice = ''; })));
      if (!['queued', 'running'].includes(job.status) && history) append(controls, button('기록 삭제', 'text-button delete-button', () => deleteJob(job)));
      append(card, controls); append(panel, card);
    }
    if (jobs.some(job => ['failed', 'interrupted'].includes(job.status))) append(panel, el('p', 'form-hint', '실패·중단된 작업은 자동으로 재실행하지 않습니다. 내용을 확인한 뒤 직접 다시 제출하면 새 요청으로 실행합니다.'));
    return panel;
  }
  function selectTopic(topic) {
    if (!approveDiscard()) return;
    state.selected = { topic, source: state.discovery === 'examples' ? 'example' : state.discovery };
    state.compose = { mode: 'ai', companyText: '', confirmed: false, name: '', contact: '' }; state.page = 'compose'; state.error = null; state.notice = ''; render(); focusMain();
  }
  function validCompose() {
    const form = state.compose;
    return !!state.session?.provider?.configured && !!state.selected && form.confirmed && form.companyText.length <= 6000 && (form.mode !== 'company' || !!form.companyText.trim()) && form.name.length <= 40 && form.contact.length <= 100 && !activeJob();
  }
  function validRevision() { return state.session?.provider?.configured && state.revision.confirmed && state.revision.instructions.trim().length > 0 && state.revision.instructions.length <= 1000 && !hasSenderChanges() && !activeJob(); }
  function updateComposeButtons() {
    const compose = document.getElementById('submit-compose'); if (compose) compose.disabled = state.busy || !validCompose();
    const revise = document.getElementById('submit-revision'); if (revise) revise.disabled = state.busy || !validRevision();
  }
  async function composeDraft() {
    if (!validCompose()) return;
    const form = state.compose;
    await submitJob('/api/compose', { topic_id: state.selected.topic.id, source: state.selected.source, mode: form.mode, company_text: form.mode === 'company' ? form.companyText : '', input_confirmed: true, sender_name: form.name, sender_contact: form.contact }, '두 자료 구성을 요청하고 있습니다.');
  }
  function composePage() {
    const page = el('div', 'page compose-page');
    append(page, button('← 주제로 돌아가기', 'back-button', showTopics), append(el('div', 'page-heading'), el('p', 'eyebrow', 'ONE TOPIC, TWO AUDIENCES'), el('h1', '', '두 자료를 함께 준비하세요.'), el('p', 'muted', '원장용 안내자료와 담당자 메모가 같은 근거로 구성됩니다.')), messages(), jobsPanel());
    const grid = el('div', 'compose-grid');
    const selected = append(el('aside', 'selected-topic'), tag(state.selected.source === 'example' ? '준비된 예제' : state.selected.source === 'briefing' ? '새 소식에서 고른 주제' : '실시간 조사 후보'), el('h2', '', state.selected.topic.title), el('p', '', state.selected.topic.summary), el('p', 'evidence-notice', state.selected.topic.evidence_notice), sourceDetails(state.selected.topic.sources));
    const form = el('section', 'composition-card'); append(form, el('h2', '', '구성 방법'));
    const modes = el('div', 'mode-tabs');
    for (const [mode, label] of [['ai', 'AI가 근거로 구성'], ['company', '회사 자료 함께 사용']]) {
      const choice = button(label, state.compose.mode === mode ? 'mode-button selected' : 'mode-button', () => { state.compose.mode = mode; state.compose.confirmed = false; render(); }); choice.setAttribute('aria-pressed', String(state.compose.mode === mode)); append(modes, choice);
    }
    append(form, modes, el('p', 'muted small', '선택한 근거 안에서 구성합니다. 회사 입력은 공개 검색에 사용하지 않으며, 구성과 내용 점검을 위해 외부 AI에 전달됩니다.'));
    if (state.compose.mode === 'company') append(form, field('company-text', '회사 자료 · 텍스트 붙여넣기만 지원', state.compose.companyText, 6000, value => { state.compose.companyText = value; }, { multiline: true, rows: 10, placeholder: '사용 권한이 있는 비민감 설명을 붙여넣으세요. 환자 기록, 개인 식별 정보, 임상 조언을 넣지 마세요.' }));
    append(form, append(el('div', 'sender-grid'), field('compose-name', '전달자 이름 · 선택', state.compose.name, 40, value => { state.compose.name = value; }), field('compose-contact', '연락처 · 선택', state.compose.contact, 100, value => { state.compose.contact = value; })), consent('compose-confirmed', state.compose.confirmed, checked => { state.compose.confirmed = checked; }, '입력 내용의 사용 권한이 있고 환자 기록이 없음을 확인합니다. 선택한 근거와 입력이 외부 OpenAI API로 전송되어 구성·점검되는 데 동의합니다.'), el('p', 'form-hint', 'AI 점검은 사실의 보증이 아닙니다. 과장·홍보성 내용은 제외되거나 반려될 수 있으며, 완성된 두 자료를 직접 검토해야 합니다.'));
    const submit = button('AI로 두 자료 만들기', 'button primary full-width', composeDraft, !validCompose()); submit.setAttribute('id', 'submit-compose'); append(form, submit);
    if (!state.session?.provider?.configured) append(form, providerPanel());
    append(grid, selected, form); append(page, grid); return page;
  }
  function revisionPanel() {
    const panel = el('section', 'revision-panel');
    append(panel, el('p', 'eyebrow', 'REFINE BOTH TOGETHER'), el('h2', '', '두 자료를 함께 수정'), el('p', 'muted small', '선택한 근거를 유지하며 원장용 자료와 담당자 메모를 함께 고칩니다. 수정 후에는 새 버전의 검토와 파일 만들기가 필요합니다.'), field('revision-instructions', '수정할 내용', state.revision.instructions, 1000, value => { state.revision.instructions = value; }, { multiline: true, rows: 4, placeholder: '예: 두 자료의 설명을 더 쉬운 말로 정리해주세요.' }), consent('revision-confirmed', state.revision.confirmed, checked => { state.revision.confirmed = checked; }, '수정 지시에 환자 기록이 없으며, 현재 자료·회사 입력·수정 지시를 외부 OpenAI API로 보내는 데 동의합니다.'));
    const submit = button('두 자료 함께 수정', 'button primary', async () => {
      if (!validRevision()) return;
      await submitJob(`/api/drafts/${encodeURIComponent(state.active.id)}/revise`, { revision: state.active.revision, instructions: state.revision.instructions, input_confirmed: true }, '두 자료 수정을 요청하고 있습니다.');
    }, !validRevision()); submit.setAttribute('id', 'submit-revision'); append(panel, submit);
    if (!state.session?.provider?.configured) append(panel, el('p', 'form-hint', 'AI 연결 설정이 필요합니다. 주제 화면에서 연결 상태와 설정 방법을 확인하세요.'));
    return panel;
  }

  function sourceDetails(sources, compact = false) {
    const list = el('ol', `source-list ${compact ? 'compact' : ''}`);
    for (const [index, source] of (sources || []).entries()) {
      const item = el('li', 'source-item');
      append(item, el('span', 'source-index', String(index + 1).padStart(2, '0')));
      const content = el('div', 'source-content');
      append(content, sourceLink(source), el('p', 'source-meta', `${source.publisher || '발행 기관 미표기'} · ${source.published_at ? `출처 표시일 ${date(source.published_at)}` : '출처 표시일 미표기'}${source.updated_at ? ` · 수정 ${date(source.updated_at)}` : ''} · 확인 ${date(source.checked_at)}`));
      if (source.context) append(content, el('p', 'source-context', source.context));
      append(item, content); append(list, item);
    }
    return list;
  }
  function citations(ids) {
    if (!ids?.length) return null;
    const row = el('div', 'citations');
    append(row, el('span', '', '근거'));
    for (const id of ids) {
      const index = state.active.sources.findIndex(source => source.id === id);
      if (index >= 0) append(row, sourceLink(state.active.sources[index], `[${index + 1}] ${state.active.sources[index].publisher || state.active.sources[index].title}`));
    }
    return row;
  }
  function insightContext(topic, source) {
    const selection = topic.selection;
    if (!selection) return null;
    const context = el('div', 'insight-context');
    const audiences = { director: '원장님', staff: '직원', both: '원장님과 직원' };
    append(context, append(el('div', 'insight-audience'), tag(`활용 대상 · ${audiences[selection.audience] || '대상 확인 필요'}`), selection.novelty === 'update' ? tag('업데이트') : null), append(el('div', 'insight-problem'), el('span', 'mini-label', '해결하려는 문제'), el('p', '', selection.problem)));
    const evidence = el('details', 'insight-signals'); evidence.setAttribute('id', `insight-signals-${topicKey(source, topic)}`);
    append(evidence, el('summary', '', '선정 근거와 관찰한 내용'));
    if (topic.summary) append(evidence, append(el('div', 'insight-context-note'), el('span', 'mini-label', '자료 요약'), el('p', '', topic.summary)));
    append(evidence, append(el('div', 'insight-context-note'), el('span', 'mini-label', '이 주제를 고른 이유'), el('p', '', selection.reason)), el('p', 'insight-scope', '문제와 활용 대상은 자료를 바탕으로 제안했습니다. 아래 관찰 내용만으로 현장 전체의 수요나 효과를 단정할 수는 없습니다.'));
    const signals = el('ul', 'insight-signal-list');
    for (const signal of selection.signals || []) {
      const reference = topic.sources?.find(item => item.id === signal.source_id);
      append(signals, append(el('li'), el('p', '', signal.observation), reference ? sourceLink(reference, `${reference.publisher || reference.title} 원문 ↗`) : el('span', 'muted small', '연결된 출처 확인 필요')));
    }
    append(evidence, signals);
    if (topic.why_now) append(evidence, append(el('div', 'insight-context-note'), el('span', 'mini-label', '지금 살펴볼 이유'), el('p', '', topic.why_now)));
    if (selection.change) append(evidence, append(el('div', 'insight-context-note'), el('span', 'mini-label', '이전 주제와 달라진 점'), el('p', '', selection.change)));
    append(context, evidence); return context;
  }
  function readyMaterial(topic, source) {
    const ready = topic.ready_to_use;
    if (!ready?.body) return null;
    const key = topicKey(source, topic);
    const details = el('details', 'ready-material'); details.setAttribute('id', `ready-material-${key}`);
    append(details, el('summary', '', '바로 쓸 자료 보기'));
    const content = el('div', 'ready-content');
    const formats = { prompt: 'AI 질문문', message: '안내문', checklist: '체크리스트', comparison: '비교 자료', brief: '요약 자료' };
    const body = el('textarea', 'ready-body', ready.body);
    body.value = ready.body; body.readOnly = true; body.rows = 14;
    body.setAttribute('id', `ready-body-${key}`); body.setAttribute('aria-label', '복사할 자료 본문');
    const select = button('본문 선택', 'button secondary small-button', () => {
      body.focus({ preventScroll: true }); body.select(); body.setSelectionRange(0, body.value.length);
      announce('본문을 선택했습니다. Ctrl+C 또는 ⌘C로 복사해주세요.');
    });
    const copy = button('본문 복사', 'button secondary small-button', () => copyReady(topic, source)); copy.setAttribute('id', `copy-ready-${key}`);
    append(content, append(el('div', 'ready-heading'), append(el('div'), el('span', 'mini-label', formats[ready.format] || '활용 자료'), el('h4', '', ready.title)), append(el('div', 'ready-actions'), select, copy)));
    append(content, el('p', 'ready-help', '본문 선택 후 Ctrl+C(Windows) 또는 ⌘C(Mac)를 누르세요. 추가 AI 실행 없이 사용할 수 있습니다.'));
    const copied = state.copyMessages[key];
    if (copied) { const message = el('p', copied.error ? 'copy-status error' : 'copy-status', copied.text); message.setAttribute('role', copied.error ? 'alert' : 'status'); append(content, message); }
    append(content, body);
    if (ready.adaptation_note) append(content, append(el('div', 'ready-adaptation'), el('span', 'mini-label', '사용 전에 맞춰볼 부분'), el('p', '', ready.adaptation_note)));
    append(details, content); return details;
  }
  function feedbackPanel(topic, source) {
    if (!['briefing', 'research'].includes(source) || typeof topic.selection?.problem_key !== 'string' || !topic.selection.problem_key.trim()) return null;
    const key = topicKey(source, topic);
    const panel = el('div', 'topic-feedback');
    const choices = el('div', 'feedback-choices'); choices.setAttribute('role', 'group'); choices.setAttribute('aria-label', `${topic.title} 유용성 평가`);
    append(panel, el('p', 'mini-label', '이 주제가 도움이 되었나요?'));
    for (const [verdict, label] of [['useful', '유용해요'], ['not_useful', '지금은 필요 없어요'], ['seen', '읽었어요']]) {
      const chosen = state.feedback[source][topic.id] === verdict;
      const choice = button(label, `feedback-choice${chosen ? ' selected' : ''}`, () => setTopicFeedback(topic, source, verdict), state.feedbackPending.has(key));
      choice.setAttribute('aria-pressed', String(chosen)); append(choices, choice);
    }
    append(panel, choices);
    if (state.feedbackPending.has(key)) append(panel, el('p', 'feedback-status', '의견을 저장하고 있습니다.'));
    else if (state.feedbackErrors[key]) { const error = el('p', 'feedback-status error', state.feedbackErrors[key]); error.setAttribute('role', 'alert'); append(panel, error); }
    else if (state.feedback[source][topic.id]) append(panel, el('p', 'feedback-status', '내 선택이 저장되어 있습니다.'));
    return panel;
  }
  function selectionReport(report, id) {
    if (!report) return null;
    const details = el('details', 'selection-report'); details.setAttribute('id', `selection-report-${id}`);
    append(details, el('summary', '', `선정 과정 · 원문 ${report.sources_read}개 확인 · 후보 ${report.candidates_considered}개 검토 · ${report.selected_count}개 선정`));
    if (report.rejected?.length) {
      const rejected = el('ul');
      for (const candidate of report.rejected) append(rejected, append(el('li'), el('strong', '', candidate.title), el('p', '', candidate.reason)));
      append(details, rejected);
    } else append(details, el('p', '', '별도로 남긴 제외 사유가 없습니다.'));
    return details;
  }
  function briefingContent() {
    const section = el('section', 'briefing-content');
    const status = state.briefing.status;
    const attempt = status?.last_attempt;
    const running = briefingRunning();
    const schedule = el('section', 'briefing-schedule');
    const summary = el('div', 'briefing-schedule-copy');
    append(summary, el('p', 'eyebrow', '새로운 읽을거리'), el('h2', '', `매일 오전 ${status?.schedule_hour || 9}시 · 한국 시간`), el('p', 'briefing-schedule-note', status?.auto_enabled ? '의료·AI·운영·경제·생활에서 읽어볼 자료를 모읍니다. 이 컴퓨터의 로컬 서버가 켜져 있을 때 자동 수집됩니다.' : status ? '자동 수집은 꺼져 있습니다. 필요할 때 아래 버튼으로 새 자료를 모을 수 있습니다.' : '저장된 소식과 수집 상태를 확인하고 있습니다.'));
    const times = el('div', 'briefing-times');
    if (status?.last_success_at) append(times, el('span', '', `마지막 수집 ${koreanTime(status.last_success_at)}`));
    if (status?.auto_enabled && status.next_run_at) append(times, el('span', '', `다음 수집 ${koreanTime(status.next_run_at)}`));
    append(summary, times);
    const actions = el('div', 'briefing-refresh-actions');
    const refresh = button('새 소식 모으기', 'button primary', refreshBriefing, !status?.configured || running || state.briefingLoading || !(status?.remaining_runs > 0));
    refresh.setAttribute('id', 'refresh-briefing'); refresh.setAttribute('aria-describedby', 'briefing-refresh-help');
    append(actions, refresh, button('수집 상태 확인', 'text-button', loadBriefing, state.briefingLoading));
    append(schedule, summary, actions);
    const help = el('p', 'briefing-quota'); help.setAttribute('id', 'briefing-refresh-help');
    help.textContent = status ? `최근 24시간에 ${status.daily_limit}회까지 · 남은 수집 ${status.remaining_runs}회. 실패한 시도도 횟수에 포함되며, 수집할 때 AI 사용료가 발생할 수 있습니다.` : '화면을 열면 저장된 글만 읽습니다. 수동 수집은 버튼을 눌렀을 때 시작됩니다.';
    append(schedule, help);
    if (status && !status.configured) append(schedule, el('p', 'briefing-setup', 'AI 연결 설정이 필요합니다. 위의 연결 안내를 확인해주세요. 저장된 글은 계속 읽을 수 있습니다.'));
    else if (status?.remaining_runs === 0 && !running) append(schedule, el('p', 'briefing-setup', '수집 횟수를 모두 사용했습니다. 다시 수집할 수 있을 때까지 모아 둔 글을 살펴보세요.'));
    if (attempt) {
      const progress = el('div', `briefing-progress ${running ? 'running' : attempt.status === 'failed' || attempt.status === 'interrupted' ? 'failed' : ''}`);
      progress.setAttribute('role', running ? 'status' : 'note');
      const noNewTopic = attempt.status === 'succeeded' && attempt.result?.selection_report?.selected_count === 0;
      append(progress, tag(running ? '새 소식 수집 중' : jobStatusLabels[attempt.status] || '수집 기록', attempt.status === 'succeeded' ? 'green' : ''), el('p', '', running ? '공개 원문을 확인하고 있습니다. 먼저 모아 둔 글은 계속 읽을 수 있습니다.' : noNewTopic ? '이번에는 새로 제안할 만한 주제를 찾지 못했습니다. 이전에 모은 글은 그대로 남아 있습니다.' : attempt.status === 'succeeded' ? '마지막 수집을 마쳤습니다. 각 글의 출처 날짜를 따로 확인하세요.' : attempt.error || '이번 수집을 마치지 못했습니다. 이전에 모은 글은 그대로 남아 있습니다.'));
      if (attempt.status === 'failed' || attempt.status === 'interrupted') append(progress, el('p', 'briefing-preserved', '이전에 모은 글은 유지됩니다. 실패한 수집은 자동으로 다시 실행하지 않습니다.'));
      append(schedule, progress);
      append(schedule, selectionReport(attempt.result?.selection_report, `briefing-${attempt.id}`));
    }
    if (state.briefingError) { const error = el('p', 'briefing-error', state.briefingError); error.setAttribute('role', 'alert'); append(schedule, error); }
    append(section, schedule);
    const items = state.briefing.items;
    append(section, append(el('div', 'section-title'), append(el('div'), el('p', 'eyebrow', '읽고 싶은 주제부터'), el('h2', '', '어떤 이야기가 눈에 들어오세요?')), el('span', 'muted small', `${items.length}개 읽을거리`)));
    if (!items.length) append(section, emptyState(state.briefingLoaded ? '아직 모아 둔 소식이 없습니다.' : state.briefingError ? '새 소식을 불러오지 못했습니다.' : '새 소식을 불러오고 있습니다.', state.briefingLoaded ? '예약된 수집을 기다리거나 직접 새 소식을 모아보세요. 직접 조사와 준비된 예제도 사용할 수 있습니다.' : '수집 상태 확인으로 저장된 목록을 다시 확인할 수 있습니다. 목록 확인은 새 수집을 시작하지 않습니다.'));
    const areas = { medical: '의료·제도', ai: 'AI', operations: '운영', economy: '경제', life: '생활' };
    const cards = el('div', 'briefing-grid');
    for (const topic of items) {
      const freshness = topic.freshness || {};
      const kind = freshness.date ? freshness.kind : 'undated';
      const label = kind === 'recent' ? '최근 자료' : kind === 'older' ? '읽을거리' : '날짜 미상';
      const card = el('article', 'topic-card briefing-card');
      const heading = el('h3', '', topic.title); heading.setAttribute('id', `briefing-title-${topic.id}`); card.setAttribute('aria-labelledby', heading.id);
      append(card, append(el('div', 'card-top'), tag(areas[topic.coverage_area] || topic.category || '읽을거리'), tag(label, kind === 'recent' ? 'green' : '')), heading, !topic.selection ? el('p', 'topic-summary', topic.summary) : null);
      const primary = topic.sources?.[0];
      append(card, el('p', 'briefing-source-date', `${primary?.publisher || '출처 기관 미표기'} · ${freshness.date ? `출처 날짜 ${date(freshness.date)}` : '발행·수정일 미상'}`));
      append(card, insightContext(topic, 'briefing'), readyMaterial(topic, 'briefing'));
      if (!topic.selection && topic.why_now) append(card, append(el('div', 'value-block'), el('span', 'mini-label', '지금 살펴볼 이유'), el('p', '', topic.why_now)));
      if (!topic.ready_to_use?.body && (topic.director_value || topic.takeaway)) {
        const usage = el('details', 'briefing-usage'); usage.setAttribute('id', `briefing-usage-${topic.id}`);
        const content = el('div', 'briefing-usage-content');
        if (topic.director_value) append(content, append(el('div'), el('span', 'mini-label', '어떻게 활용할까요?'), el('p', '', topic.director_value)));
        if (topic.takeaway) append(content, append(el('div'), el('span', 'mini-label', '바로 활용할 예시'), el('p', '', topic.takeaway)));
        append(usage, el('summary', '', '활용 방법과 예시'), content); append(card, usage);
      }
      const sources = el('details', 'topic-evidence'); sources.setAttribute('id', `briefing-evidence-${topic.id}`);
      append(sources, el('summary', '', `출처와 적용 범위 ${topic.sources?.length || 0}개`), el('p', 'evidence-notice', topic.evidence_notice), sourceDetails(topic.sources, true));
      append(card, sources, append(el('div', 'briefing-collected'), el('span', '', `모은 날 ${date(topic.collected_at)}`), primary ? sourceLink(primary, '원문 읽기 ↗') : null), append(el('div', 'card-bottom'), el('span', 'muted small', `약 ${topic.reading_minutes || 3}분 읽기`), button('이 주제로 구성하기', 'button primary small-button', () => selectTopic(topic))));
      append(card, feedbackPanel(topic, 'briefing'));
      append(cards, card);
    }
    append(section, cards);
    return section;
  }
  function researchTopicCard(topic, index, source) {
    const card = el('article', 'topic-card');
    append(card, append(el('div', 'card-top'), tag(topic.category || '운영 안내'), el('span', 'topic-number', String(index + 1).padStart(2, '0'))), el('h3', '', topic.title), !topic.selection ? el('p', 'topic-summary', topic.summary) : null);
    append(card, insightContext(topic, source), readyMaterial(topic, source));
    if (!topic.ready_to_use?.body) append(card, append(el('div', 'value-block'), el('span', 'mini-label', '원장님께 어떤 도움이 되나요?'), el('p', '', topic.director_value)), append(el('div', 'takeaway-block'), el('span', 'takeaway-icon', '↳'), el('p', '', topic.takeaway)));
    const sourceBox = el('details', 'topic-evidence');
    append(sourceBox, el('summary', '', `근거 ${topic.sources?.length || 0}개 · 조사 ${date(topic.research_date)}`), el('p', 'evidence-notice', topic.evidence_notice), sourceDetails(topic.sources, true));
    append(card, sourceBox, append(el('div', 'card-bottom'), el('span', 'muted small', `약 ${topic.reading_minutes || 3}분 읽기`), button('이 주제로 구성하기', 'button primary small-button', () => selectTopic(topic)), source === 'examples' ? button('예제 그대로 만들기', 'text-button template-button', () => createDraft(topic)) : null));
    append(card, feedbackPanel(topic, source));
    return card;
  }
  function researchResultPage() {
    const job = state.researchResult;
    const selected = job.result.topics;
    const saved = new Map(state.research.map(topic => [topic.id, topic]));
    const topics = selected.map(topic => saved.get(topic.id)).filter(Boolean);
    const page = el('div', 'page research-result-page');
    const title = el('h1', 'research-result-title', '조사 결과');
    title.setAttribute('id', 'research-result-title'); title.setAttribute('tabindex', '-1');
    const completed = koreanTime(job.updated_at || job.created_at);
    append(page, button('← 저장된 조사 전체 보기', 'back-button', showTopics), append(el('header', 'page-heading research-result-heading'), el('p', 'eyebrow', 'RESEARCH RESULT'), title,
      append(el('div', 'research-result-meta'), tag(selected.length ? `주제 ${selected.length}개 선정` : '선정 주제 없음', selected.length ? 'green' : ''), completed ? el('p', 'muted small', `${completed} 조사 완료`) : null)), messages());
    if (selected.length === 0) {
      append(page, append(el('section', 'research-outcome empty-outcome'), el('h2', '', '이번 조사에서는 주제를 선정하지 못했습니다.'), el('p', '', '아래에서 살펴본 후보와 선정하지 못한 이유를 확인하세요. 이전에 저장한 조사는 그대로 남아 있습니다.')));
    } else if (!topics.length) {
      append(page, append(el('section', 'research-outcome'), el('h2', '', '선정했던 주제가 현재 저장 목록에 없습니다.'), el('p', '', `이 조사에서는 ${selected.length}개를 선정했지만 현재 열 수 있는 주제는 없습니다. 다른 주제는 저장된 조사 전체 보기에서 확인할 수 있습니다.`)));
    } else {
      append(page, el('p', 'research-result-help', '이 조사에서 선정한 주제입니다. 내용을 읽고 바로 쓸 자료를 복사하거나, 전달할 자료로 구성해 보세요.'));
      if (topics.length < selected.length) append(page, el('p', 'research-result-missing', `선정한 ${selected.length}개 중 ${selected.length - topics.length}개가 현재 저장 목록에 없어, 남아 있는 ${topics.length}개를 표시합니다.`));
      const cards = el('div', 'topic-grid insight-grid');
      topics.forEach((topic, index) => append(cards, researchTopicCard(topic, index, 'research')));
      append(page, cards);
    }
    const report = selectionReport(job.result.selection_report, job.id);
    if (report) { report.open = true; append(page, append(el('section', 'research-result-report'), el('h2', '', '주제를 검토한 내용'), report)); }
    else if (!selected.length) append(page, el('p', 'muted', '이전 조사 기록에는 후보별 선정 이유가 저장되어 있지 않습니다.'));
    return page;
  }
  function topicsPage() {
    const page = el('div', 'page topics-page');
    const hero = el('section', state.discovery === 'briefing' ? 'hero briefing-hero' : 'hero');
    const intro = el('div', 'hero-copy');
    append(intro, el('p', 'eyebrow', 'A CLEARER CONVERSATION'), el('h1', '', state.discovery === 'briefing' ? '새로운 이야기를,\n한눈에 살펴보세요.' : '좋은 대화는,\n잘 정리된 한 장에서.'), el('p', 'hero-description', state.discovery === 'briefing' ? '의료와 AI부터 운영, 경제와 생활까지.\n원문을 읽고 대화에 쓸 주제를 골라보세요.' : '원장님께 전달할 주제를 고르세요.\n근거가 담긴 안내자료와 나만의 대화 메모를 함께 준비합니다.'));
    const illustration = el('div', 'hero-illustration');
    illustration.setAttribute('aria-hidden', 'true');
    append(illustration, append(el('div', 'illustration-note'), el('span', '', '나의 대화 메모'), el('i', 'illus-line'), el('i', 'illus-line short'), el('i', 'illus-line')), append(el('div', 'illustration-paper'), el('span', 'illus-logo', 'cb.'), el('span', 'illus-heading', '근거로 준비하는\n더 명확한 대화'), el('i', 'illus-line'), el('i', 'illus-line short'), el('i', 'illus-line'), el('span', 'illus-foot', 'CLINIC BRIEF')));
    append(hero, intro, illustration);
    const introNote = append(el('div', 'scope-note'), el('span', 'scope-icon', 'i'), el('p', '', '2단계 로컬 검증입니다. 공개 출처를 조사하고 두 대상의 자료를 함께 준비합니다. SaaS 출시 전이며, 출처 날짜만으로 최신성이나 정확성을 보장하지 않습니다.'));
    append(page, hero, introNote, messages(), state.discovery !== 'briefing' || !state.session?.provider?.configured ? providerPanel() : null, state.discovery !== 'briefing' || activeJob() ? jobsPanel() : null, discoveryPanel());
    if (state.discovery === 'briefing') { append(page, briefingContent()); return page; }
    const shownTopics = state.discovery === 'examples' ? state.topics : state.research;
    const title = append(el('div', 'section-title'), append(el('div'), el('p', 'eyebrow', state.discovery === 'examples' ? 'PREPARED EXAMPLES' : 'YOUR RESEARCH'), el('h2', '', '어떤 이야기를 준비할까요?')), el('span', 'muted small', `${state.discovery === 'examples' ? '준비된 예제' : '저장된 조사'} ${shownTopics.length}개`));
    append(page, title);
    if (state.discovery === 'examples' && !state.loadedTopics && !state.busy) append(page, button('예제 다시 불러오기', 'button primary', loadTopics));
    if (state.discovery === 'examples' && state.loadedTopics && !state.topics.length) append(page, emptyState('아직 준비된 예제가 없습니다.', '예제 데이터가 준비되면 이곳에서 주제를 선택할 수 있습니다.'));
    if (state.discovery === 'research' && !shownTopics.length) append(page, emptyState('공개 근거부터 살펴보세요.', '위에서 넓은 조사 범주를 선택하세요. 실시간 조사는 외부 AI를 사용하며, 저장된 후보가 여기에 모입니다.'));
    const cards = el('div', state.discovery === 'research' ? 'topic-grid insight-grid' : 'topic-grid');
    shownTopics.forEach((topic, index) => append(cards, researchTopicCard(topic, index, state.discovery)));
    append(page, cards, append(el('section', 'how-it-works'), el('p', 'eyebrow', 'FROM TOPIC TO HANDOUT'), ...[['01', '주제와 근거 확인', '원문과 적용 범위를 살펴보세요.'], ['02', '두 화면 나눠 검토', '전달할 자료와 개인 메모를 구분하세요.'], ['03', 'PDF · DOCX로 전달', '검토한 버전의 실제 파일을 내려받으세요.']].map(([number, heading, text]) => append(el('div', 'how-step'), el('span', 'step-number', number), append(el('div'), el('h3', '', heading), el('p', '', text))))));
    return page;
  }
  function emptyState(title, description) {
    return append(el('div', 'empty-state'), el('span', 'empty-icon', '▱'), el('h2', '', title), el('p', 'muted', description));
  }
  function savedPage() {
    const page = el('div', 'page saved-page');
    append(page, append(el('div', 'page-heading'), el('p', 'eyebrow', 'YOUR WORK'), el('h1', '', '이어갈 이야기가 있습니다.'), el('p', 'muted', '저장된 내용 그대로 다시 열고, 검토와 파일 준비를 이어가세요.')), messages());
    append(page, append(el('div', 'section-title'), el('h2', '', `저장된 작업 ${state.drafts.length}`), button('목록 새로고침', 'button secondary small-button', showSaved)));
    if (!state.drafts.length && !state.busy) append(page, emptyState('첫 자료를 준비해보세요.', '주제를 선택하면 작업이 이 컴퓨터에 자동으로 저장됩니다.'), button('주제 둘러보기', 'button primary', showTopics));
    const list = el('div', 'saved-list');
    for (const draft of state.drafts) {
      const card = el('article', 'saved-card');
      const body = el('div', 'saved-card-body');
      append(body, append(el('div', 'saved-meta'), tag(statusLabels[draft.status] || draft.status, draft.status !== 'draft' ? 'green' : ''), el('span', 'muted small', `버전 ${draft.revision} · 수정 ${date(draft.updated_at)}`)), el('h3', '', draft.brochure.title), el('p', 'muted small', `조사 ${date(draft.research_date)} · ${draft.brochure.sender?.name ? `전달자 ${draft.brochure.sender.name}` : '전달자 정보 없음'}`));
      append(card, body, append(el('div', 'saved-actions'), button('작업 열기', 'button secondary', () => openDraft(draft.id)), button('삭제', 'text-button delete-button', () => deleteDraft(draft))));
      append(list, card);
    }
    append(page, list, jobsPanel(true), append(el('section', 'cleanup-panel'), el('h2', '', '저장된 조사 관리'), el('p', 'muted small', '완료된 조사 후보를 지워도 이미 만든 자료의 근거 사본은 유지됩니다. 작업 기록은 아래 목록에서 개별 삭제할 수 있습니다.'), button('저장된 조사 삭제', 'button secondary', clearResearch, activeJob() || !state.research.length)));
    return page;
  }
  function handout() {
    const { brochure } = state.active;
    const paper = el('article', 'document-paper');
    append(paper, append(el('div', 'document-topline'), el('span', 'eyebrow', 'CLINIC BRIEF'), el('span', '', '원장님께 드리는 안내자료')), el('h2', 'document-title', brochure.title), el('p', 'document-intro', brochure.intro));
    for (const section of brochure.sections || []) append(paper, append(el('section', 'document-section'), el('h3', '', section.heading), el('p', '', section.body), citations(section.source_ids)));
    if (brochure.example) append(paper, append(el('section', 'example-box'), el('span', 'mini-label', '제안된 활용 예시 · 실제 기관 사례 아님'), el('h3', '', brochure.example.heading), el('p', '', brochure.example.body)));
    if (brochure.limitations?.length) append(paper, append(el('section', 'document-section limitations'), el('h3', '', '함께 확인할 사항'), append(el('ul'), ...brochure.limitations.map(item => el('li', '', item)))));
    const sender = brochure.sender || {};
    if (sender.name || sender.contact) append(paper, append(el('div', 'document-sender'), el('span', 'mini-label', '전달자'), sender.name ? el('p', 'sender-display-name', sender.name) : null, sender.contact ? el('p', '', sender.contact) : null));
    append(paper, append(el('div', 'document-footer'), el('p', '', `조사 기준일 ${date(state.active.research_date)}`), el('p', '', state.active.evidence_notice)));
    return paper;
  }
  function notes() {
    const content = state.active.notes;
    const panel = el('article', 'notes-panel');
    append(panel, append(el('div', 'private-banner'), el('span', 'private-icon', '▣'), append(el('div'), el('strong', '', '나만 보는 담당자 메모'), el('p', '', '이 화면은 PDF와 DOCX에 포함되지 않습니다. 대화 준비에만 사용하세요.'))));
    append(panel, el('h2', '', '대화를 준비하는 메모'));
    const openings = el('div', 'opening-grid');
    append(openings, append(el('section', 'note-card'), el('span', 'mini-label', '직원에게 대화를 시작할 때'), el('p', '', content.opening_staff)), append(el('section', 'note-card'), el('span', 'mini-label', '원장님께 설명을 시작할 때'), el('p', '', content.opening_director)));
    append(panel, openings, append(el('section', 'note-section'), el('h3', '', '핵심 설명'), el('p', '', content.explanation)));
    if (content.qa?.length) {
      const qa = el('section', 'note-section');
      append(qa, el('h3', '', '예상 질문과 답변'));
      for (const pair of content.qa) append(qa, append(el('div', 'qa-item'), el('h4', '', `Q. ${pair.question}`), el('p', '', pair.answer)));
      append(panel, qa);
    }
    if (content.cannot_claim?.length) append(panel, append(el('section', 'cannot-claim'), el('h3', '', '이렇게 단정하지 마세요'), append(el('ul'), ...content.cannot_claim.map(item => el('li', '', item)))));
    if (content.claim_map?.length) {
      const mapping = append(el('section', 'note-section'), el('h3', '', '설명과 근거 연결'));
      for (const item of content.claim_map) append(mapping, append(el('div', 'claim-item'), el('p', '', item.claim), citations(item.source_ids)));
      append(panel, mapping);
    }
    return panel;
  }
  function senderPanel() {
    const panel = el('section', 'control-card sender-panel');
    append(panel, el('span', 'control-number', '01'), el('h2', '', '전달자 정보'), el('p', 'muted small', '직접 제공한 정보만 자료에 표시합니다. 입력은 선택사항입니다.'));
    const form = el('form', 'sender-form');
    form.addEventListener('submit', event => { event.preventDefault(); saveSender(); });
    for (const [key, label, max, placeholder] of [['name', '이름 또는 표시명', 40, '예: 홍길동'], ['contact', '연락처', 100, '이메일 또는 전화번호']]) {
      const id = `sender-${key}`;
      const labelNode = el('label', '', label); labelNode.setAttribute('for', id);
      const input = el('input'); input.setAttribute('id', id); input.type = 'text'; input.maxLength = max; input.value = state.sender[key]; input.placeholder = placeholder; input.autocomplete = 'off'; input.disabled = state.busy;
      const counter = el('span', 'input-counter', `${state.sender[key].length}/${max}`);
      counter.setAttribute('id', `${id}-count`); input.setAttribute('aria-describedby', `${id}-count`);
      input.addEventListener('input', event => {
        state.sender[key] = event.target.value;
        counter.textContent = `${state.sender[key].length}/${max}`;
        refreshControls();
      });
      append(form, append(el('div', 'field'), append(el('div', 'field-label'), labelNode, counter), input));
    }
    const save = button('전달자 정보 저장', 'button secondary full-width', saveSender, !hasSenderChanges());
    save.setAttribute('id', 'save-sender');
    const hint = el('p', 'form-hint'); hint.setAttribute('id', 'sender-hint');
    append(form, save, hint); append(panel, form);
    return panel;
  }
  function exportPanel() {
    const panel = el('section', 'control-card export-panel');
    append(panel, el('span', 'control-number', '02'), el('h2', '', '검토하고 파일로 준비'), el('p', 'muted small', '원장용 자료와 담당자 메모를 모두 확인한 뒤, 현재 버전을 검토 완료하세요.'));
    const checklist = el('ul', 'review-checklist');
    for (const [tab, label] of [['brochure', '원장용 자료 확인'], ['notes', '담당자 메모 확인']]) append(checklist, el('li', state.visited.has(visitedKey(tab)) ? 'checked' : '', `${state.visited.has(visitedKey(tab)) ? '✓' : '○'} ${label}`));
    append(panel, checklist);
    const review = button(state.active.status === 'draft' ? '현재 버전 검토 완료' : '현재 버전 검토 완료됨', 'button secondary full-width', reviewDraft);
    review.setAttribute('id', 'review-draft'); append(panel, review);
    const hint = el('p', 'form-hint'); hint.setAttribute('id', 'review-hint'); append(panel, hint);
    const failed = Object.values(state.active.exports || {}).some(item => item.status === 'failed');
    const ready = ['docx', 'pdf'].every(format => state.active.exports?.[format]?.status === 'ready');
    const make = button(failed ? '실패한 파일 다시 시도' : ready ? '파일 다시 확인 · 복구' : 'PDF · DOCX 파일 만들기', 'button primary full-width', exportDraft);
    make.setAttribute('id', 'export-draft'); append(panel, make);
    const formats = el('div', 'export-formats');
    for (const [format, label, description] of [['pdf', 'PDF', '전달하기 좋은 문서'], ['docx', 'DOCX', '내용을 편집할 수 있는 문서']]) {
      const result = state.active.exports?.[format] || { status: 'pending' };
      const item = el('div', 'export-item');
      append(item, append(el('div', 'format-info'), el('strong', '', label), el('span', '', description)));
      // Only server-issued, same-origin routes for this exact revision become download links.
      const expected = `/api/drafts/${encodeURIComponent(state.active.id)}/download/${format}?revision=${state.active.revision}`;
      if (result.status === 'ready' && result.url === expected) {
        const link = el('a', 'download-link', `${label} 다운로드 ↓`); link.setAttribute('href', result.url); link.setAttribute('download', ''); link.setAttribute('data-format', format); append(item, link);
      } else append(item, el('span', `export-status ${result.status === 'failed' ? 'failed' : ''}`, hasSenderChanges() ? '수정 내용 저장 필요' : result.status === 'failed' ? '다시 시도 필요' : '아직 준비되지 않음'));
      if (result.error) append(item, el('p', 'export-error', result.error));
      append(formats, item);
    }
    formats.setAttribute('id', 'export-formats'); append(panel, formats, el('p', 'export-footnote', '담당자 메모는 내보내기에 포함되지 않습니다. 편집한 DOCX를 전달할 때는 내용을 다시 확인하세요.'));
    return panel;
  }
  function refreshControls() {
    updateComposeButtons();
    const dirty = hasSenderChanges();
    const save = document.getElementById('save-sender');
    const senderHint = document.getElementById('sender-hint');
    const review = document.getElementById('review-draft');
    const reviewHint = document.getElementById('review-hint');
    const make = document.getElementById('export-draft');
    if (save) save.disabled = state.busy || !dirty;
    if (senderHint) senderHint.textContent = dirty ? '저장하지 않은 변경이 있습니다. 저장하면 검토와 기존 파일이 초기화됩니다.' : '저장된 전달자 정보가 자료 미리보기에 표시됩니다.';
    if (review) review.disabled = state.busy || dirty || !reviewedBoth() || state.active.status !== 'draft';
    if (reviewHint) reviewHint.textContent = dirty ? '먼저 전달자 정보를 저장해주세요.' : !reviewedBoth() ? '두 탭을 모두 열어 내용을 확인해주세요.' : state.active.status === 'draft' ? '내용과 근거를 확인했다면 검토를 완료해주세요.' : `버전 ${state.active.revision}의 검토가 완료되었습니다.`;
    if (make) make.disabled = state.busy || dirty || !['reviewed', 'exported'].includes(state.active.status);
    // Keep input focus while replacing only the file controls on sender edits.
    const formats = document.getElementById('export-formats');
    if (formats) {
      for (const link of formats.querySelectorAll('a')) {
        if (dirty) { link.setAttribute('aria-disabled', 'true'); link.removeAttribute('href'); link.textContent = '수정 내용 저장 필요'; }
        else {
          const format = link.getAttribute('data-format');
          if (format) { link.setAttribute('href', state.active.exports[format].url); link.removeAttribute('aria-disabled'); link.textContent = `${format.toUpperCase()} 다운로드 ↓`; }
        }
      }
    }
  }
  function workspacePage() {
    state.visited.add(visitedKey(state.tab));
    const draft = state.active;
    const page = el('div', 'page workspace-page');
    append(page, button('← 주제 둘러보기', 'back-button', showTopics));
    append(page, append(el('div', 'workspace-heading'), append(el('div'), el('p', 'eyebrow', 'PREPARE YOUR BRIEF'), el('h1', '', draft.brochure.title)), append(el('div', 'workspace-status'), tag(statusLabels[draft.status] || draft.status, draft.status !== 'draft' ? 'green' : ''), el('span', 'muted small', `버전 ${draft.revision} · 로컬 저장됨`))), messages(), jobsPanel());
    const grid = el('div', 'workspace-grid');
    const left = el('div', 'preview-column');
    const tabs = el('div', 'audience-tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', '자료 대상');
    for (const [tab, label] of [['brochure', '원장용 자료'], ['notes', '담당자 메모']]) {
      const tabButton = button(label, state.tab === tab ? 'audience-tab selected' : 'audience-tab', () => { state.tab = tab; render(); document.getElementById(`tab-${tab}`)?.focus(); });
      tabButton.setAttribute('id', `tab-${tab}`); tabButton.setAttribute('role', 'tab'); tabButton.setAttribute('aria-selected', String(state.tab === tab)); tabButton.setAttribute('aria-controls', 'audience-panel'); tabButton.tabIndex = state.tab === tab ? 0 : -1;
      tabButton.addEventListener('keydown', event => {
        if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
          event.preventDefault(); state.tab = event.key === 'Home' ? 'brochure' : event.key === 'End' ? 'notes' : state.tab === 'brochure' ? 'notes' : 'brochure'; render(); document.getElementById(`tab-${state.tab}`)?.focus();
        }
      });
      append(tabs, tabButton);
    }
    append(tabs, el('span', 'tab-caption', state.tab === 'brochure' ? 'PDF · DOCX에 포함' : '내보내기 제외'));
    const panel = el('div', 'audience-panel'); panel.setAttribute('id', 'audience-panel'); panel.setAttribute('role', 'tabpanel'); panel.setAttribute('aria-labelledby', `tab-${state.tab}`); panel.tabIndex = 0;
    append(panel, state.tab === 'brochure' ? handout() : notes());
    append(left, tabs, panel);
    const evidence = el('details', 'workspace-evidence');
    append(evidence, el('summary', '', `출처와 적용 범위 확인 (${draft.sources.length})`), el('p', 'evidence-notice', draft.evidence_notice), sourceDetails(draft.sources));
    append(left, evidence, revisionPanel());
    if (draft.input_notice) append(left, append(el('div', 'notice input-notice'), el('p', '', draft.input_notice)));
    if (draft.quality_notes?.length) append(left, append(el('div', 'notice input-notice'), el('p', '', draft.quality_notes.join(' '))));
    append(grid, left, append(el('aside', 'workspace-controls'), senderPanel(), exportPanel(), append(el('div', 'local-note'), el('strong', '', '계정별 로컬 작업'), el('p', '', '자료는 이 컴퓨터에 저장됩니다. AI 구성 시 선택한 근거·회사 입력·수정 지시는 외부 AI로 전송됩니다. 환자 기록을 입력하지 마세요.'))));
    append(page, grid); return page;
  }
  function render() {
    const focus = document.activeElement;
    const focusId = focus?.id;
    const selection = focus && typeof focus.selectionStart === 'number' ? [focus.selectionStart, focus.selectionEnd] : null;
    const openDetails = [...main.querySelectorAll('details')].filter(node => node.open && node.id).map(node => node.id);
    const signedIn = !!state.session?.user;
    const workspace = signedIn && state.page === 'workspace' && state.active;
    const researchResult = signedIn && state.page === 'research-result' && state.researchResult;
    const topicsCurrent = state.page === 'topics' || !!researchResult;
    navTopics.disabled = state.busy || !signedIn; navSaved.disabled = state.busy || !signedIn;
    navTopics.classList.toggle('active', topicsCurrent); navSaved.classList.toggle('active', state.page === 'saved');
    for (const [nav, current] of [[navTopics, topicsCurrent], [navSaved, state.page === 'saved']]) {
      if (current) nav.setAttribute('aria-current', 'page'); else nav.removeAttribute('aria-current');
    }
    breadcrumb.textContent = !signedIn ? '계정 / 로컬 작업 공간' : workspace ? '내 작업 / 자료 준비' : researchResult ? '주제 둘러보기 / 조사 결과' : state.page === 'saved' ? '내 작업' : state.page === 'compose' ? '주제 / 두 자료 구성' : '주제 둘러보기';
    const account = document.getElementById('account-controls');
    if (account) account.replaceChildren(...(signedIn ? [el('span', 'account-email', state.session.user.email), button('로그아웃', 'text-button', logout)] : []));
    main.setAttribute('aria-busy', String(state.busy));
    main.replaceChildren(!state.sessionLoaded ? append(el('div', 'page'), messages(), !state.busy ? button('연결 다시 확인', 'button primary', bootstrap) : null) : !signedIn ? authPage() : workspace ? workspacePage() : researchResult ? researchResultPage() : state.page === 'saved' ? savedPage() : state.page === 'compose' ? composePage() : topicsPage());
    if (workspace) refreshControls();
    for (const id of openDetails) { const details = document.getElementById(id); if (details) details.open = true; }
    if (focusId) { const restored = document.getElementById(focusId); restored?.focus(); if (selection && restored?.setSelectionRange) restored.setSelectionRange(...selection); }
    if (state.destinationFocus && !state.busy) {
      const target = document.getElementById(state.destinationFocus); state.destinationFocus = null;
      if (target) {
        target.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'auto' });
        if (researchResult) announce(state.researchResult.result.topics.length ? `선정한 주제 ${state.researchResult.result.topics.length}개와 조사 결과를 열었습니다.` : '선정한 주제가 없습니다. 후보별 이유를 확인할 수 있습니다.');
        else if (workspace) announce('작성 자료를 열었습니다.');
      }
    }
    scheduleBriefingPolling();
  }
  function showTopics() {
    if (!state.session?.user || !approveDiscard()) return;
    state.researchResult = null; state.page = 'topics'; state.error = null; state.notice = ''; render(); focusMain();
    if (state.discovery === 'briefing') loadBriefing();
  }
  navTopics.addEventListener('click', showTopics);
  navSaved.addEventListener('click', showSaved);
  window.addEventListener('beforeunload', event => { if (hasSenderChanges()) { event.preventDefault(); event.returnValue = ''; } });
  document.addEventListener('visibilitychange', () => { if (briefingVisible()) return loadBriefing(); stopBriefingPolling(); });
  bootstrap();
})();
