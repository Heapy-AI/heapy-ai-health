/** HEAPY 웹 앱 상호작용. 작성자: 김진우 */
const elements = {
  authScreen: document.querySelector("#authScreen"),
  appShell: document.querySelector("#appShell"),
  loginForm: document.querySelector("#loginForm"),
  emailInput: document.querySelector("#emailInput"),
  passwordInput: document.querySelector("#passwordInput"),
  loginButton: document.querySelector("#loginButton"),
  loginError: document.querySelector("#loginError"),
  loginTitle: document.querySelector("#loginTitle"),
  authDescription: document.querySelector("#authDescription"),
  loginModeButton: document.querySelector("#loginModeButton"),
  signupModeButton: document.querySelector("#signupModeButton"),
  signupFields: document.querySelector("#signupFields"),
  nameInput: document.querySelector("#nameInput"),
  birthDateInput: document.querySelector("#birthDateInput"),
  sexInput: document.querySelector("#sexInput"),
  logoutButton: document.querySelector("#logoutButton"),
  userAvatar: document.querySelector("#userAvatar"),
  userName: document.querySelector("#userName"),
  userEmail: document.querySelector("#userEmail"),
  form: document.querySelector("#chatForm"),
  input: document.querySelector("#questionInput"),
  sendButton: document.querySelector("#sendButton"),
  resetButton: document.querySelector("#resetButton"),
  conversation: document.querySelector("#conversation"),
  welcome: document.querySelector("#welcome"),
  messages: document.querySelector("#messages"),
  emptyInsight: document.querySelector("#emptyInsight"),
  auditCountBadge: document.querySelector("#auditCountBadge"),
  auditCardList: document.querySelector("#auditCardList"),
  chatInsightPanel: document.querySelector("#chatInsightPanel"),
  dashboardInsightPanel: document.querySelector("#dashboardInsightPanel"),
  dashboardStatusBadge: document.querySelector("#dashboardStatusBadge"),
  dashboardPanelTitle: document.querySelector("#dashboardPanelTitle"),
  dashboardMetricLabels: [...document.querySelectorAll("[data-dashboard-metric-label]")],
  dashboardMetricValues: [...document.querySelectorAll("[data-dashboard-metric-value]")],
  dashboardLatestStatus: document.querySelector("#dashboardLatestStatus"),
  dashboardHistoryStatus: document.querySelector("#dashboardHistoryStatus"),
  dashboardAnalysisStatus: document.querySelector("#dashboardAnalysisStatus"),
  dashboardResultStatus: document.querySelector("#dashboardResultStatus"),
  dashboardReportLog: document.querySelector("#dashboardReportLog"),
  dashboardVerificationDetails: document.querySelector("#dashboardVerificationDetails"),
  environmentStatus: document.querySelector("#environmentStatus"),
  vectorBackendLabel: document.querySelector("#vectorBackendLabel"),
  embedModelLabel: document.querySelector("#embedModelLabel"),
  totalChunkCount: document.querySelector("#totalChunkCount"),
  classifierLabel: document.querySelector("#classifierLabel"),
  collectionTotalLabel: document.querySelector("#collectionTotalLabel"),
  environmentCollectionList: document.querySelector("#environmentCollectionList"),
  projectEnvironmentContent: document.querySelector("#projectEnvironmentContent"),
  projectEnvironmentHeader: document.querySelector("#projectEnvironmentHeader"),
  personalEnvironment: document.querySelector("#personalEnvironment"),
  lifestyleEnvironment: document.querySelector("#lifestyleEnvironment"),
  reportModelLabel: document.querySelector("#reportModelLabel"),
  conversationList: document.querySelector("#conversationList"),
  conversationHistory: document.querySelector("#conversationHistory"),
  newConversationButton: document.querySelector("#newConversationButton"),
  composerWrap: document.querySelector("#composerWrap"),
  chatViewTab: document.querySelector("#chatViewTab"),
  dataViewTab: document.querySelector("#dataViewTab"),
  dataView: document.querySelector("#dataView"),
  checkupTab: document.querySelector("#checkupTab"),
  lifestyleTab: document.querySelector("#lifestyleTab"),
  dataReloadButton: document.querySelector("#dataReloadButton"),
  checkupPanel: document.querySelector("#checkupPanel"),
  lifestylePanel: document.querySelector("#lifestylePanel"),
  checkupMeta: document.querySelector("#checkupMeta"),
  lifestyleMeta: document.querySelector("#lifestyleMeta"),
  checkupBody: document.querySelector("#checkupBody"),
  checkupReportButton: document.querySelector("#checkupReportButton"),
  checkupRecordSelect: document.querySelector("#checkupRecordSelect"),
  checkupReport: document.querySelector("#checkupReport"),
  lifestyleBody: document.querySelector("#lifestyleBody"),
  lifestyleStatus: document.querySelector("#lifestyleStatus"),
  lifestyleContent: document.querySelector("#lifestyleContent"),
  lifestyleToday: document.querySelector("#lifestyleToday"),
  lifestyleTodayDate: document.querySelector("#lifestyleTodayDate"),
  lifestyleReport: document.querySelector("#lifestyleReport"),
  lifestyleReportButton: document.querySelector("#lifestyleReportButton"),
  lifestyleAnalysisScope: document.querySelector("#lifestyleAnalysisScope"),
  lifestyleTrends: document.querySelector("#lifestyleTrends"),
  lifestyleTabs: [...document.querySelectorAll("[data-lifestyle-tab]")],
  lifestylePeriods: [...document.querySelectorAll("[data-lifestyle-days]")],
};

const intentNames = {
  simple_lookup: "건강정보 조회",
  comprehensive: "종합 건강 질문",
  general_chat: "일상 건강 대화",
  ignore: "상담 범위 외",
};

const recommendationPool = [
  { title: "혈당 수치 알아보기", question: "공복혈당 정상 수치는 어떻게 되나요?" },
  { title: "혈압 기준 알아보기", question: "수축기 혈압과 이완기 혈압은 무엇이 다른가요?" },
  { title: "검진 결과 이해하기", question: "건강검진에서 정상B 판정은 무슨 뜻인가요?" },
  { title: "간 기능 검사 알아보기", question: "AST와 ALT 검사는 무엇을 확인하는 검사인가요?" },
  { title: "콜레스테롤 이해하기", question: "HDL과 LDL 콜레스테롤은 어떻게 다른가요?" },
  { title: "중성지방 알아보기", question: "중성지방 수치가 높으면 일반적으로 무엇을 확인하나요?" },
  { title: "체질량지수 알아보기", question: "BMI는 어떻게 계산하고 결과를 어떻게 해석하나요?" },
  { title: "빈혈 정보 알아보기", question: "빈혈의 대표적인 원인과 증상을 알려주세요." },
  { title: "감기 정보 알아보기", question: "감기의 대표적인 원인과 증상을 알려주세요." },
  { title: "고혈압 알아보기", question: "고혈압의 대표적인 원인과 증상은 무엇인가요?" },
  { title: "당뇨병 알아보기", question: "당뇨병의 대표적인 증상과 위험 요인을 알려주세요." },
  { title: "건강 습관 알아보기", question: "고혈압 예방에 도움이 되는 생활 습관을 알려주세요." },
  { title: "혈색소 수치 알아보기", question: "혈색소 검사는 무엇을 확인하고 수치는 어떻게 해석하나요?" },
  { title: "신장 기능 알아보기", question: "신장 기능 검사에서는 일반적으로 어떤 항목을 확인하나요?" },
  { title: "간 건강 알아보기", question: "간 건강을 관리하는 데 도움이 되는 생활 습관을 알려주세요." },
  { title: "검진 전 준비하기", question: "건강검진 전에 금식이 필요한 이유를 알려주세요." },
];

const STREAM_CHARACTER_DELAY_MS = 28;
const STREAM_COMMA_DELAY_MS = 70;
const STREAM_SENTENCE_DELAY_MS = 130;
let isRequesting = false;
let conversationHistory = [];
let conversationSummary = "";
let currentSessionId = "";
let authMode = "login";
let activeView = "chat";
let activeDataTab = "checkup";
let activeLifestyleTab = "bio";
// 생활건강 탭의 기본 조회 기간. index.html에서 active로 표시한 버튼과 같아야 한다.
const LIFESTYLE_DEFAULT_DAYS = 7;
let lifestyleDays = LIFESTYLE_DEFAULT_DAYS;
let lifestylePayload = null;
let checkupRecords = [];
let selectedCheckupRecordId = "";
// 탭을 다시 열 때마다 재조회하지 않도록 조회 여부를 기억한다.
const loadedDataTabs = new Set();

function setAuthMode(mode) {
  authMode = mode;
  const isSignup = mode === "signup";
  elements.loginModeButton.classList.toggle("active", !isSignup);
  elements.signupModeButton.classList.toggle("active", isSignup);
  elements.signupFields.hidden = !isSignup;
  elements.nameInput.required = isSignup;
  elements.birthDateInput.required = isSignup;
  elements.sexInput.required = isSignup;
  elements.passwordInput.autocomplete = isSignup ? "new-password" : "current-password";
  elements.loginTitle.textContent = isSignup ? "HEAPY와 함께 시작해요" : "다시 만나서 반가워요";
  elements.authDescription.textContent = isSignup
    ? "건강 프로필과 로그인 계정을 함께 만들어요."
    : "Supabase에 등록된 계정으로 로그인해 주세요.";
  elements.loginButton.textContent = isSignup ? "회원가입" : "로그인";
  setLoginError();
}

function setLoginError(message = "") {
  elements.loginError.textContent = message;
  elements.loginError.hidden = !message;
}

function renderAuthenticatedUser(user) {
  const email = String(user.email || "");
  const displayName = String(user.display_name || email.split("@")[0] || "사용자");
  elements.userName.textContent = displayName;
  elements.userEmail.textContent = email;
  elements.userAvatar.textContent = displayName.charAt(0).toUpperCase() || "사";
  elements.authScreen.hidden = true;
  elements.appShell.hidden = false;
  // 계정이 바뀌면 이전 사용자의 개인 데이터를 다시 조회하도록 캐시를 버린다.
  loadedDataTabs.clear();
  resetCheckupRecords();
  // 세션이 끊겨 로그인 화면으로 돌아갔던 경우 열려 있던 탭을 다시 채운다.
  setActiveView(activeView);
  loadConversationSessions();
  elements.input.focus();
}

function showLoginScreen(message = "") {
  elements.appShell.hidden = true;
  elements.authScreen.hidden = false;
  setLoginError(message);
  elements.passwordInput.value = "";
  setAuthMode("login");
  elements.emailInput.focus();
}

async function refreshSession() {
  const response = await fetch("/auth/refresh", { method: "POST" });
  return response.ok;
}

async function fetchChatStream(options) {
  let response = await fetch("/chat/stream", options);
  if (response.status !== 401 || !(await refreshSession())) return response;
  response = await fetch("/chat/stream", options);
  return response;
}

async function restoreSession() {
  let response = await fetch("/auth/me", { headers: { Accept: "application/json" } });
  if (response.status === 401 && await refreshSession()) {
    response = await fetch("/auth/me", { headers: { Accept: "application/json" } });
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const message = response.status === 503
      ? String(payload.detail || "Supabase 인증 설정이 필요합니다.")
      : "";
    showLoginScreen(message);
    return;
  }
  renderAuthenticatedUser(await response.json());
}

async function requestLogin(payload) {
  return fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function requestSignup(payload) {
  return fetch("/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function login(event) {
  event.preventDefault();
  setLoginError();
  elements.loginButton.disabled = true;
  const isSignup = authMode === "signup";
  elements.loginButton.textContent = isSignup ? "가입 중..." : "로그인 중...";
  try {
    const payload = {
      email: elements.emailInput.value.trim(),
      password: elements.passwordInput.value,
    };
    if (isSignup) {
      payload.name = elements.nameInput.value.trim();
      payload.birth_date = elements.birthDateInput.value;
      payload.sex = elements.sexInput.value;
    }
    const response = isSignup
      ? await requestSignup(payload)
      : await requestLogin(payload);
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(String(result.detail || (isSignup ? "회원가입에 실패했습니다." : "로그인에 실패했습니다.")));
    }
    if (result.email_confirmation_required) {
      setAuthMode("login");
      setLoginError("가입 확인 메일을 확인한 뒤 로그인해 주세요.");
      return;
    }
    renderAuthenticatedUser(result);
  } catch (error) {
    setLoginError(error instanceof Error ? error.message : "인증 처리에 실패했습니다.");
  } finally {
    elements.loginButton.disabled = false;
    elements.loginButton.textContent = authMode === "signup" ? "회원가입" : "로그인";
  }
}

async function logout() {
  elements.logoutButton.disabled = true;
  try {
    await fetch("/auth/logout", { method: "POST" });
  } finally {
    resetConversation();
    resetPersonalData();
    elements.conversationList.replaceChildren();
    showLoginScreen();
    elements.logoutButton.disabled = false;
  }
}

async function fetchWithSession(resource, options = {}) {
  let response = await fetch(resource, options);
  if (response.status !== 401 || !(await refreshSession())) return response;
  response = await fetch(resource, options);
  return response;
}

function renderConversationSessions(sessions) {
  elements.conversationList.replaceChildren();
  if (!sessions.length) {
    const empty = document.createElement("p");
    empty.className = "conversation-list-empty";
    empty.textContent = "저장된 대화가 없습니다.";
    elements.conversationList.appendChild(empty);
    return;
  }
  sessions.forEach((session) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "conversation-item";
    button.classList.toggle("active", session.session_id === currentSessionId);
    const title = document.createElement("strong");
    title.textContent = session.title || "새 대화";
    const time = document.createElement("time");
    time.textContent = new Intl.DateTimeFormat("ko-KR", {
      month: "numeric",
      day: "numeric",
    }).format(new Date(session.updated_at));
    button.append(title, time);
    button.addEventListener("click", () => loadConversation(session.session_id));
    elements.conversationList.appendChild(button);
  });
}

async function loadConversationSessions() {
  try {
    const response = await fetchWithSession("/conversations", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return;
    renderConversationSessions(await response.json());
  } catch {
    renderConversationSessions([]);
  }
}

function appendStoredAssistantMessage(content) {
  const message = document.createElement("div");
  message.className = "message assistant";
  message.appendChild(createAssistantAvatar());
  const messageContent = document.createElement("div");
  messageContent.className = "message-content";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = renderMarkdown(sanitizeAnswerText(content));
  messageContent.appendChild(bubble);
  message.appendChild(messageContent);
  elements.messages.appendChild(message);
}

async function loadConversation(sessionId) {
  if (isRequesting) return;
  // 사이드바 대화는 '내건강' 탭에서도 눌릴 수 있으므로 챗 화면으로 돌린다.
  if (activeView !== "chat") setActiveView("chat");
  try {
    const response = await fetchWithSession(`/conversations/${encodeURIComponent(sessionId)}`, {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "대화를 불러오지 못했습니다.");
    currentSessionId = payload.session.session_id;
    conversationSummary = payload.session.summary || "";
    conversationHistory = (payload.messages || [])
      .map((message) => ({ role: message.role, content: message.content }))
      .slice(-6);
    elements.messages.replaceChildren();
    elements.welcome.hidden = true;
    elements.messages.hidden = false;
    (payload.messages || []).forEach((message) => {
      if (message.role === "user") appendUserMessage(message.content);
      if (message.role === "assistant") appendStoredAssistantMessage(message.content);
    });
    await loadConversationSessions();
    scrollToLatest();
  } catch (error) {
    appendErrorMessage(error instanceof Error ? error.message : "대화를 불러오지 못했습니다.");
  }
}

function selectRandomRecommendations(count) {
  const shuffled = [...recommendationPool];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[randomIndex]] = [shuffled[randomIndex], shuffled[index]];
  }
  return shuffled.slice(0, count);
}

function renderSuggestionCards() {
  const cards = [...document.querySelectorAll(".suggestion-card")];
  const recommendations = selectRandomRecommendations(cards.length);
  cards.forEach((card, index) => {
    const recommendation = recommendations[index];
    if (!recommendation) return;
    card.dataset.question = recommendation.question;
    card.querySelector("strong").textContent = recommendation.title;
    card.querySelector("small").textContent = recommendation.question;
  });
}

function setEnvironmentBadge(status, label) {
  elements.environmentStatus.className = `environment-badge ${status}`;
  elements.environmentStatus.replaceChildren();
  const dot = document.createElement("span");
  dot.className = "status-dot";
  elements.environmentStatus.append(dot, document.createTextNode(label));
}

function renderCollections(indexedChunks) {
  const collections = Object.entries(indexedChunks || {});
  elements.collectionTotalLabel.textContent = String(collections.length);
  elements.environmentCollectionList.replaceChildren();

  if (!collections.length) {
    const empty = document.createElement("div");
    empty.className = "environment-placeholder";
    empty.textContent = "표시할 컬렉션이 없습니다.";
    elements.environmentCollectionList.appendChild(empty);
    return;
  }

  collections.forEach(([name, count]) => {
    const item = document.createElement("div");
    item.className = "environment-collection-item";
    const collectionName = document.createElement("span");
    collectionName.className = "environment-collection-name";
    collectionName.textContent = name;
    const collectionCount = document.createElement("strong");
    collectionCount.className = "environment-collection-count";
    collectionCount.textContent = Number(count || 0).toLocaleString("ko-KR");
    item.append(collectionName, collectionCount);
    elements.environmentCollectionList.appendChild(item);
  });
}

async function loadProjectEnvironment() {
  try {
    const response = await fetch("/health", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("환경 상태를 조회하지 못했습니다.");
    const data = await response.json();
    const indexedChunks = data.indexed_chunks || {};
    const totalChunks = Object.values(indexedChunks)
      .reduce((total, count) => total + (Number(count) || 0), 0);
    const classifier = data.intent_classifier || {};
    const reportModel = data.checkup_report_model;

    setEnvironmentBadge(data.ready ? "ready" : "warning", data.ready ? "준비 완료" : "점검 필요");
    elements.vectorBackendLabel.textContent = String(data.vector_backend || "unknown").toUpperCase();
    elements.embedModelLabel.textContent = data.embed_model || "unknown";
    elements.embedModelLabel.title = data.embed_model || "unknown";
    elements.totalChunkCount.textContent = totalChunks.toLocaleString("ko-KR");
    elements.classifierLabel.textContent = classifier.ready
      ? classifier.model_version || "준비 완료"
      : "모델 없음";
    if (reportModel) elements.reportModelLabel.textContent = `Gemini · ${reportModel}`;
    renderCollections(indexedChunks);
  } catch (error) {
    setEnvironmentBadge("error", "연결 실패");
    elements.vectorBackendLabel.textContent = "확인 불가";
    elements.embedModelLabel.textContent = "확인 불가";
    elements.totalChunkCount.textContent = "—";
    elements.classifierLabel.textContent = "확인 불가";
    renderCollections({});
  }
}

function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 120)}px`;
  elements.sendButton.disabled = isRequesting || !elements.input.value.trim();
}

function createAssistantAvatar() {
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.innerHTML = '<img src="/images/heapy-doctor.png" alt="" aria-hidden="true" />';
  return avatar;
}

function appendUserMessage(question) {
  const message = document.createElement("div");
  message.className = "message user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = question;
  message.appendChild(bubble);
  elements.messages.appendChild(message);
}

function appendLoadingMessage() {
  const message = document.createElement("div");
  message.className = "message assistant";
  message.dataset.loading = "true";
  message.appendChild(createAssistantAvatar());
  const bubble = document.createElement("div");
  bubble.className = "bubble loading-bubble";
  bubble.innerHTML = "<span></span><span></span><span></span>";
  message.appendChild(bubble);
  elements.messages.appendChild(message);
  scrollToLatest();
}

function appendAssistantMessage(data) {
  let message = document.querySelector('[data-loading="true"]');
  if (!message) {
    message = document.createElement("div");
    message.className = "message assistant";
    message.appendChild(createAssistantAvatar());
    elements.messages.appendChild(message);
  }
  delete message.dataset.loading;

  let bubble = message.querySelector(".bubble");
  if (!bubble) {
    bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = renderMarkdown(
      sanitizeAnswerText(data.answer) || "답변을 생성하지 못했습니다.",
    );
  } else if (message.dataset.started !== "true") {
    bubble.classList.remove("loading-bubble");
    bubble.innerHTML = renderMarkdown(
      sanitizeAnswerText(data.answer) || "답변을 생성하지 못했습니다.",
    );
  }

  let content = message.querySelector(".message-content");
  if (!content) {
    content = document.createElement("div");
    content.className = "message-content";
    content.appendChild(bubble);
    message.appendChild(content);
  }

  const meta = document.createElement("div");
  meta.className = "answer-meta";
  const intentChip = document.createElement("span");
  intentChip.className = "answer-chip";
  intentChip.textContent = intentNames[data.intent] || data.intent || "분류 없음";
  meta.appendChild(intentChip);
  if (data.grounded === true) {
    const groundedChip = document.createElement("span");
    groundedChip.className = "answer-chip";
    groundedChip.textContent = data.evidence_status === "partial" ? "부분 근거 답변" : "검색 근거 답변";
    meta.appendChild(groundedChip);
  }
  if (data.audit_status === "failed" || data.audit_status === "error") {
    const auditChip = document.createElement("span");
    auditChip.className = "answer-chip warning";
    auditChip.textContent = "감사 확인 필요";
    meta.appendChild(auditChip);
  }
  content.querySelector(".answer-meta")?.remove();
  content.appendChild(meta);
  content.querySelector(".confirmation-actions")?.remove();
  if (data.query_confirmation && data.confirmation_id) {
    const actions = document.createElement("div");
    actions.className = "confirmation-actions";
    [
      ["예", true],
      ["아니요", false],
    ].forEach(([label, answer]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = answer ? "confirmation-button primary" : "confirmation-button";
      button.textContent = label;
      button.addEventListener("click", () => {
        actions.querySelectorAll("button").forEach((item) => { item.disabled = true; });
        submitQuestion(data.original_question || data.question, {
          confirmationId: data.confirmation_id,
          confirmationAnswer: answer,
          displayUser: false,
        });
      });
      actions.appendChild(button);
    });
    content.appendChild(actions);
  }
  scrollToLatest();
}

function appendStreamToken(text) {
  const message = document.querySelector('[data-loading="true"]');
  const bubble = message?.querySelector(".bubble");
  if (!message || !bubble) return;
  if (message.dataset.started !== "true") {
    message.dataset.started = "true";
    bubble.classList.remove("loading-bubble");
    bubble.replaceChildren();
    message.dataset.rawAnswer = "";
  }
  message.dataset.rawAnswer = `${message.dataset.rawAnswer || ""}${text}`;
  bubble.innerHTML = renderMarkdown(
    sanitizeAnswerText(message.dataset.rawAnswer, true),
  );
  scrollToLatest();
}

function createTokenPacer() {
  let queuedText = "";
  let timerId = null;
  let drainResolvers = [];
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function resolveDrain() {
    if (queuedText || timerId !== null) return;
    drainResolvers.forEach((resolve) => resolve());
    drainResolvers = [];
  }

  function getBatchSize() {
    if (reduceMotion) return Math.max(queuedText.length, 1);
    if (queuedText.length > 72) return 2;
    return 1;
  }

  function getDelay(displayedText) {
    if (reduceMotion) return 0;
    if (/[.!?。]\s*$/.test(displayedText)) return STREAM_SENTENCE_DELAY_MS;
    if (/[,，:;]\s*$/.test(displayedText)) return STREAM_COMMA_DELAY_MS;
    return STREAM_CHARACTER_DELAY_MS;
  }

  function schedule() {
    if (timerId !== null || !queuedText) {
      resolveDrain();
      return;
    }
    const batchSize = getBatchSize();
    const displayedText = queuedText.slice(0, batchSize);
    queuedText = queuedText.slice(batchSize);
    timerId = window.setTimeout(() => {
      timerId = null;
      appendStreamToken(displayedText);
      schedule();
    }, getDelay(displayedText));
  }

  return {
    push(text) {
      queuedText += text;
      schedule();
    },
    drain() {
      if (!queuedText && timerId === null) return Promise.resolve();
      return new Promise((resolve) => drainResolvers.push(resolve));
    },
    cancel() {
      if (timerId !== null) window.clearTimeout(timerId);
      timerId = null;
      queuedText = "";
      resolveDrain();
    },
  };
}

function sanitizeAnswerText(text, hidePartialLabel = false) {
  let sanitized = String(text || "").replace(/\[(?:C\d+\s*(?:,\s*C?\d+\s*)*)\]/gi, "");
  if (hidePartialLabel) sanitized = sanitized.replace(/\[(?:C\d*(?:\s*,\s*C?\d*)*)?$/i, "");
  return sanitized
    .replace(/[ \t]+\n/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .trimStart();
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(text) {
  const codeTokens = [];
  let rendered = escapeHtml(text).replace(/`([^`\n]+)`/g, (_, code) => {
    const token = `\u0000CODE${codeTokens.length}\u0000`;
    codeTokens.push(`<code>${code}</code>`);
    return token;
  });
  rendered = rendered
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_\n]+)__/g, "<strong>$1</strong>")
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");
  return rendered.replace(/\u0000CODE(\d+)\u0000/g, (_, index) => codeTokens[Number(index)]);
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replaceAll("\r\n", "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let listType = null;
  let listItems = [];
  let codeLines = [];
  let inCodeBlock = false;

  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push(`<p>${paragraph.map(renderInlineMarkdown).join("<br>")}</p>`);
    paragraph = [];
  }

  function flushList() {
    if (!listType || !listItems.length) return;
    blocks.push(
      `<${listType}>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</${listType}>`,
    );
    listType = null;
    listItems = [];
  }

  lines.forEach((line) => {
    if (/^\s*```/.test(line)) {
      flushParagraph();
      flushList();
      if (inCodeBlock) {
        blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
      }
      inCodeBlock = !inCodeBlock;
      return;
    }
    if (inCodeBlock) {
      codeLines.push(line);
      return;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      return;
    }

    const unorderedItem = line.match(/^\s*[-+*]\s+(.+)$/);
    const orderedItem = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unorderedItem || orderedItem) {
      flushParagraph();
      const nextListType = unorderedItem ? "ul" : "ol";
      if (listType && listType !== nextListType) flushList();
      listType = nextListType;
      listItems.push((unorderedItem || orderedItem)[1]);
      return;
    }

    const quote = line.match(/^\s*>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      return;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      return;
    }
    flushList();
    paragraph.push(line);
  });

  if (inCodeBlock && codeLines.length) {
    blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  flushParagraph();
  flushList();
  return blocks.join("");
}

function appendErrorMessage(error) {
  document.querySelector('[data-loading="true"]')?.remove();
  const message = document.createElement("div");
  message.className = "message assistant error";
  message.appendChild(createAssistantAvatar());
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = error;
  message.appendChild(bubble);
  elements.messages.appendChild(message);
  scrollToLatest();
}

function scrollToLatest() {
  requestAnimationFrame(() => {
    elements.conversation.scrollTop = elements.conversation.scrollHeight;
  });
}

function setConversationMode() {
  elements.welcome.hidden = true;
  elements.messages.hidden = false;
}

function setInsightPending() {
  elements.auditCountBadge.className = "quality-badge info";
  elements.auditCountBadge.textContent = "처리 중";
}

function setInsightError() {
  elements.auditCountBadge.className = "quality-badge warning";
  elements.auditCountBadge.textContent = "응답 오류";
}

function createTextElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text;
  return element;
}

function auditStatusMeta(status) {
  const statuses = {
    passed: { label: "감사 통과", className: "passed" },
    failed: { label: "추가 검토", className: "failed" },
    error: { label: "감사 오류", className: "error" },
    not_run: { label: "감사 미실행", className: "not_run" },
    not_applicable: { label: "감사 비대상", className: "not_applicable" },
  };
  return statuses[status] || statuses.not_applicable;
}

function addMonitorItem(container, label, value) {
  const item = document.createElement("div");
  item.className = "audit-monitor-item";
  item.append(
    createTextElement("span", "", label),
    createTextElement("strong", "", value || "—"),
  );
  container.appendChild(item);
}

function appendAuditSection(body, title) {
  const section = document.createElement("section");
  section.className = "audit-section";
  section.appendChild(createTextElement("h3", "", title));
  body.appendChild(section);
  return section;
}

function appendRetrievalAssessment(body, data) {
  const assessment = data.retrieval_assessment;
  const section = appendAuditSection(body, "검색 결과 기본 검사");
  if (!assessment) {
    section.appendChild(createTextElement("div", "no-source", "이 응답 경로는 검색을 사용하지 않았습니다."));
    return;
  }

  const list = document.createElement("div");
  list.className = "audit-monitor-list";
  addMonitorItem(list, "검사 결과", evidenceStatusLabel(assessment.status));
  addMonitorItem(list, "최고 유사도", assessment.max_score == null ? "—" : `${(Number(assessment.max_score) * 100).toFixed(1)}%`);
  addMonitorItem(list, "질문 대상", (assessment.query_entities || []).join(", ") || "명시 대상 없음");
  addMonitorItem(list, "일치 대상", (assessment.matched_entities || []).join(", ") || "—");
  section.appendChild(list);
  section.appendChild(createTextElement("p", "environment-placeholder", assessment.reason || "검사 사유 없음"));
}

function appendUnsupportedClaims(body, data) {
  const claims = Array.isArray(data.unsupported_claims) ? data.unsupported_claims : [];
  const unanswered = Array.isArray(data.unanswered_items) ? data.unanswered_items : [];
  const safetyViolations = Array.isArray(data.safety_violations) ? data.safety_violations : [];
  if (!claims.length && !unanswered.length && !safetyViolations.length && !(data.grounding_errors || []).length) return;
  const section = appendAuditSection(body, "감사 경고");
  const list = document.createElement("ul");
  list.className = "unsupported-list";
  [...claims, ...unanswered.map((item) => `근거 부족 항목: ${item}`), ...safetyViolations.map((item) => `안전 정책 위반: ${item}`), ...(data.grounding_errors || [])].forEach((claim) => {
    list.appendChild(createTextElement("li", "", claim));
  });
  section.appendChild(list);
}

function appendEvidenceChunks(body, data) {
  const citations = Array.isArray(data.citations) ? data.citations : [];
  const chunks = citations.length ? citations : (Array.isArray(data.chunks) ? data.chunks : []);
  const section = appendAuditSection(body, `근거 청크 ${chunks.length}개`);
  const list = document.createElement("div");
  list.className = "chunk-list";

  if (!chunks.length) {
    list.appendChild(createTextElement("div", "no-source", "이 응답은 표시할 검색 근거가 없습니다."));
  } else {
    chunks.forEach((chunk, index) => {
      const item = document.createElement("div");
      item.className = "chunk-item";
      const header = document.createElement("div");
      header.className = "chunk-header";
      header.append(
        createTextElement("strong", "", chunk.citation_id || `근거 ${index + 1}`),
        createTextElement("em", "", `유사도 ${((Number(chunk.score) || 0) * 100).toFixed(1)}%`),
      );
      const meta = createTextElement(
        "span",
        "chunk-meta",
        `${chunk.collection || "unknown"} · ${chunk.record_id || "ID 없음"}`,
      );
      const chunkText = String(chunk.text || "본문 없음");
      const chunkContent = createTextElement("div", "chunk-scroll-content", chunkText);
      const source = createTextElement(
        "span",
        "chunk-source",
        String(chunk.source || "출처 미상").split(" · ")[0],
      );
      item.append(header, meta, chunkContent, source);
      list.appendChild(item);
    });
  }
  section.appendChild(list);
}

function updateInsight(data) {
  elements.emptyInsight.hidden = true;
  elements.auditCardList.querySelectorAll("details[open]").forEach((card) => {
    card.open = false;
  });

  const status = auditStatusMeta(data.audit_status);
  const card = document.createElement("details");
  card.className = "audit-card";
  card.open = true;

  const summary = document.createElement("summary");
  summary.className = "audit-card-summary";
  const title = document.createElement("div");
  title.className = "audit-card-title";
  title.append(
    createTextElement("strong", "", data.question || "질문 내용 없음"),
    createTextElement(
      "span",
      "",
      `${intentNames[data.intent] || data.intent || "분류 없음"} · ${Math.round((Number(data.confidence) || 0) * 100)}%`,
    ),
  );
  summary.append(
    title,
    createTextElement("span", `audit-card-status ${status.className}`, status.label),
  );
  card.appendChild(summary);

  const body = document.createElement("div");
  body.className = "audit-card-body";
  const auditSummary = document.createElement("div");
  auditSummary.className = "audit-summary-box";
  auditSummary.append(
    createTextElement("strong", "", "사후 감사"),
    createTextElement("p", "", data.audit_summary || "이 응답 경로에는 별도 사후 감사 내용이 없습니다."),
  );
  body.appendChild(auditSummary);

  const metrics = document.createElement("div");
  metrics.className = "audit-metrics";
  [
    ["Intent", intentNames[data.intent] || data.intent || "—"],
    ["신뢰도", `${Math.round((Number(data.confidence) || 0) * 100)}%`],
    ["근거 상태", evidenceStatusLabel(data.evidence_status)],
    ["감사 상태", status.label],
  ].forEach(([label, value]) => {
    const metric = document.createElement("div");
    metric.className = "audit-metric";
    metric.append(
      createTextElement("span", "", label),
      createTextElement("strong", "", value),
    );
    metrics.appendChild(metric);
  });
  body.appendChild(metrics);

  const monitorSection = appendAuditSection(body, "모니터링 정보");
  const monitorList = document.createElement("div");
  monitorList.className = "audit-monitor-list";
  addMonitorItem(monitorList, "응답 경로", `${data.model_version || "Intent 모델"} · ${intentNames[data.intent] || data.intent || "—"}`);
  addMonitorItem(monitorList, "위험 수준", riskLevelLabel(data.risk_level));
  addMonitorItem(monitorList, "금지 행동", (data.restricted_actions || []).join(", ") || "없음");
  addMonitorItem(monitorList, "응답 정책", data.response_policy || "—");
  addMonitorItem(monitorList, "원문 질문", data.original_question || data.question || "—");
  addMonitorItem(monitorList, "독립형 질문", data.standalone_question || "—");
  addMonitorItem(monitorList, "후속 질문", data.is_follow_up ? "예" : "아니요");
  addMonitorItem(monitorList, "현재 주제", data.current_topic || "—");
  addMonitorItem(monitorList, "이어받은 대상", data.inherited_target || "없음");
  addMonitorItem(monitorList, "개인 검진 필요", data.personal_context_required ? "예" : "아니요");
  addMonitorItem(monitorList, "최종 검색 질문", data.resolved_query || "—");
  addMonitorItem(monitorList, "용어 정규화", data.resolution_status || "NO_MATCH");
  addMonitorItem(monitorList, "정규화 오류", data.resolution_error || "없음");
  addMonitorItem(monitorList, "검증 방식", formatVerification(data.verification_method));
  addMonitorItem(monitorList, "검증 사유", data.verification_reason);
  addMonitorItem(monitorList, "분류 검토", data.uncertain ? "필요" : "불필요");
  addMonitorItem(monitorList, "검색 컬렉션", (data.searched_collections || []).join(", ") || "검색 안 함");
  addMonitorItem(monitorList, "실패 컬렉션", (data.failed_collections || []).join(", ") || "없음");
  monitorSection.appendChild(monitorList);

  appendRetrievalAssessment(body, data);
  appendUnsupportedClaims(body, data);
  appendEvidenceChunks(body, data);

  const jsonSection = appendAuditSection(body, "응답 원본");
  const jsonDetail = document.createElement("details");
  const jsonSummary = createTextElement("summary", "audit-json-toggle", "응답 결과 JSON 보기");
  const json = createTextElement("pre", "audit-json", JSON.stringify(data, null, 2));
  jsonDetail.append(jsonSummary, json);
  jsonSection.appendChild(jsonDetail);

  card.appendChild(body);
  elements.auditCardList.prepend(card);
  elements.auditCountBadge.className = "quality-badge neutral";
  elements.auditCountBadge.textContent = `${elements.auditCardList.childElementCount}건`;
}

function formatVerification(method) {
  const names = {
    retrieval_check_post_audit: "검색 검사 + 사후 감사",
    retrieval_check_audit_warning: "검색 검사 + 감사 경고",
    retrieval_check_audit_error: "검색 검사 + 감사 오류",
    retrieval_rejected: "검색 결과 검사 거절",
    fixed_response: "고정 응답",
    not_applicable: "검증 대상 아님",
  };
  return names[method] || method || "—";
}

function evidenceStatusLabel(status) {
  const names = {
    sufficient: "근거 충분",
    partial: "부분 근거",
    insufficient: "근거 부족",
    evidence_available: "근거 청크 있음",
    no_evidence: "검색 결과 없음",
    entity_mismatch: "질문 대상 불일치",
    unknown: "감사 확인 필요",
    not_applicable: "검색 미사용",
  };
  return names[status] || status || "검색 미사용";
}

function riskLevelLabel(level) {
  const names = {
    normal: "일반 정보",
    caution: "주의 상담",
    emergency: "긴급 우선",
  };
  return names[level] || level || "일반 정보";
}

function parseError(response, payload) {
  if (response.status === 503) {
    return "챗봇 서버가 아직 준비 중이에요. 잠시 후 다시 질문해 주세요.";
  }
  if (response.status === 422) {
    return "질문 내용을 확인해 주세요.";
  }
  return payload?.detail || "답변을 불러오는 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.";
}

function parseSseBlock(block) {
  let eventName = "message";
  const dataLines = [];
  block.split("\n").forEach((line) => {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  });
  if (!dataLines.length) return null;
  return { eventName, payload: JSON.parse(dataLines.join("\n")) };
}

async function consumeChatStream(response) {
  if (!response.body) throw new Error("이 브라우저에서는 스트리밍 응답을 사용할 수 없어요.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  const tokenPacer = createTokenPacer();
  let buffer = "";
  let completePayload = null;

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      buffer = buffer.replaceAll("\r\n", "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseSseBlock(block);
        if (event?.eventName === "token") {
          tokenPacer.push(event.payload.text || "");
        }
        if (event?.eventName === "complete") {
          completePayload = event.payload;
        }
        if (event?.eventName === "error") {
          throw new Error(event.payload.message || "답변 스트리밍 중 문제가 생겼어요.");
        }
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }

    if (!completePayload) {
      throw new Error("답변 스트림이 완료되기 전에 연결이 종료됐어요.");
    }
    await tokenPacer.drain();
    appendAssistantMessage(completePayload);
    updateInsight(completePayload);
    updateConversationMemory(completePayload);
  } catch (error) {
    tokenPacer.cancel();
    throw error;
  }
}

function updateConversationMemory(data) {
  currentSessionId = data.session_id || currentSessionId;
  conversationSummary = data.conversation_summary || conversationSummary;
  const blockedStatuses = new Set([
    "CONFIRM",
    "AMBIGUOUS",
    "CONFIRMATION_EXPIRED",
    "CONFIRMATION_REJECTED",
  ]);
  if (data.query_confirmation || blockedStatuses.has(data.resolution_status)) return;
  const userQuestion = String(data.original_question || data.question || "").trim();
  const assistantAnswer = String(data.answer || "").trim();
  if (userQuestion) conversationHistory.push({ role: "user", content: userQuestion });
  if (assistantAnswer) conversationHistory.push({ role: "assistant", content: assistantAnswer });
  conversationHistory = conversationHistory.slice(-6);
  loadConversationSessions();
}

async function submitQuestion(question, options = {}) {
  const normalized = question.trim();
  if (!normalized || isRequesting) return;

  isRequesting = true;
  setConversationMode();
  setInsightPending();
  if (options.displayUser !== false) appendUserMessage(normalized);
  appendLoadingMessage();
  elements.input.value = "";
  resizeInput();

  try {
    const response = await fetchChatStream({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: normalized,
        session_id: currentSessionId,
        history: conversationHistory,
        summary: conversationSummary,
        confirmation_id: options.confirmationId || "",
        confirmation_answer: options.confirmationAnswer ?? null,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(parseError(response, payload));
    }
    await consumeChatStream(response);
  } catch (error) {
    appendErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류가 발생했어요.");
    setInsightError();
  } finally {
    isRequesting = false;
    resizeInput();
    elements.input.focus();
  }
}

/* 내건강 탭. 라벨과 단위 환산은 프롬프트 포맷(supabase_lifestyle_context)과 맞춘다. 작성자: 고수연 */
function formatDataNumber(value, digits = 0) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toLocaleString("ko-KR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatDataDate(value) {
  const text = String(value || "").trim();
  if (!text) return "—";
  // record_date는 날짜, measured_at·consumed_at은 timestamp로 내려온다.
  return text.length <= 10 ? text.slice(0, 10) : `${text.slice(0, 10)} ${text.slice(11, 16)}`;
}

function formatGraphDate(value) {
  const text = String(value || "").slice(0, 10);
  if (!text) return "";
  const parts = text.split("-");
  if (parts.length === 2) return `${Number(parts[1])}월`;
  return `${Number(parts[1])}/${Number(parts[2])}`;
}

function statusChipClass(status) {
  const text = String(status || "");
  if (!text) return "neutral";
  // 검진은 정상·경계·의심, 생활건강은 양호·주의·관리 필요로 판정이 내려온다.
  if (text.startsWith("정상") || text === "양호") return "normal";
  if (text.includes("경계") || text.includes("주의")) return "caution";
  if (text.includes("의심") || text.includes("이상") || text.includes("위험") || text.includes("관리")) return "danger";
  return "neutral";
}

function createStatusChip(status) {
  const chip = document.createElement("span");
  chip.className = `status-chip ${statusChipClass(status)}`;
  chip.textContent = String(status || "미분류");
  return chip;
}

const checkupColumns = [
  { label: "검사 항목", value: (row) => String(row.item_name || row.item_code || "—") },
  { label: "코드", value: (row) => String(row.item_code || "—") },
  {
    label: "수치",
    numeric: true,
    value: (row) => (row.value ? `${row.value}${row.unit ? ` ${row.unit}` : ""}` : "—"),
  },
  { label: "판정", value: (row) => createStatusChip(row.status) },
];

/* 생활건강 탭의 세부 항목 정의.
   단위 환산과 항목 이름은 백엔드 분석(services/lifestyle_report.py)과 같게 맞춘다. */
const bioMetric = (type, value) => ({
  source: "bio",
  dateKey: "measured_at",
  daily: "mean",
  keep: (row) => row.bio_type === type,
  value,
});

const lifestyleMetrics = {
  weight: { label: "체중", unit: "kg", digits: 1, ...bioMetric("weight", (row) => row.value) },
  // 체중과 단위가 달라 한 그래프에 겹칠 때는 오른쪽 축을 쓴다.
  bmi: { label: "BMI", unit: "", digits: 1, axis: "right", ...bioMetric("bmi", (row) => row.value) },
  // 당일 카드에서는 이완기와 묶어 '121/79'로 보여 준다. 그래프와 수치표는 그대로 둘로 나눈다.
  systolic: { label: "수축기 혈압", unit: "mmHg", digits: 0, pairedWith: "diastolic", pairedLabel: "혈압", ...bioMetric("blood_pressure", (row) => row.detail_data?.systolic) },
  diastolic: { label: "이완기 혈압", unit: "mmHg", digits: 0, ...bioMetric("blood_pressure", (row) => row.detail_data?.diastolic) },
  glucoseFasting: {
    label: "공복 혈당", unit: "mg/dL", digits: 0,
    source: "bio", dateKey: "measured_at", daily: "mean",
    keep: (row) => row.bio_type === "blood_glucose" && row.detail_data?.fasting === true,
    value: (row) => row.value,
  },
  glucoseAfter: {
    label: "식후 혈당", unit: "mg/dL", digits: 0,
    source: "bio", dateKey: "measured_at", daily: "mean",
    keep: (row) => row.bio_type === "blood_glucose" && row.detail_data?.fasting !== true,
    value: (row) => row.value,
  },
  heartRate: { label: "심박수", unit: "bpm", digits: 0, ...bioMetric("heart_rate", (row) => row.value) },

  steps: { label: "걸음 수", unit: "걸음", digits: 0, source: "activity", dateKey: "record_date", daily: "sum", value: (row) => row.steps },
  floors: { label: "계단", unit: "층", digits: 0, source: "activity", dateKey: "record_date", daily: "sum", value: (row) => row.floors_climbed },
  activeTime: { label: "활동시간", unit: "분", digits: 0, source: "activity", dateKey: "record_date", daily: "sum", value: (row) => row.active_time },
  // lifestyle_activity.distance_m은 컬럼명과 달리 km로 적재돼 환산 없이 쓴다.
  activeDistance: { label: "이동거리", unit: "km", digits: 1, source: "activity", dateKey: "record_date", daily: "sum", value: (row) => row.active_distance_km },
  activeCalories: { label: "활동칼로리", unit: "kcal", digits: 0, source: "activity", dateKey: "record_date", daily: "sum", value: (row) => row.active_calories },
  exerciseTime: {
    label: "운동시간", unit: "분", digits: 0,
    pairedWith: "exerciseCalories", pairedLabel: "운동",
    source: "exercise", dateKey: "record_date", daily: "sum",
    value: (row) => (row.duration_sec === null || row.duration_sec === undefined ? null : Number(row.duration_sec) / 60),
  },
  // lifestyle_exercise.distance_m은 미터 단위이므로 km로 환산한다.
  exerciseDistance: {
    label: "운동거리", unit: "km", digits: 1,
    source: "exercise", dateKey: "record_date", daily: "sum",
    value: (row) => (row.distance_m === null || row.distance_m === undefined ? null : Number(row.distance_m) / 1000),
  },
  exerciseCalories: { label: "운동칼로리", unit: "kcal", digits: 0, source: "exercise", dateKey: "record_date", daily: "sum", value: (row) => row.calories },
  // 운동칼로리는 활동칼로리 안에 든 값이다. 실측한 29일 모두 운동 ≤ 활동이었고
  // 중앙값이 61%였다. 둘을 그대로 쌓으면 하루 합이 실제보다 커지므로, 겹치지 않는
  // 나머지를 쌓아 막대 높이가 활동칼로리와 같아지게 한다.
  otherCalories: {
    label: "그 외 활동", unit: "kcal", digits: 0,
    derive: (payload) => {
      const exercise = new Map(metricDailySeries(payload, lifestyleMetrics.exerciseCalories)
        .map((point) => [point.date, point.value]));
      return metricDailySeries(payload, lifestyleMetrics.activeCalories)
        .map((point) => ({ date: point.date, value: Math.max(point.value - (exercise.get(point.date) || 0), 0) }));
    },
  },

  intakeCalories: { label: "섭취칼로리", unit: "kcal", digits: 0, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.calories },
  carbohydrate: { label: "탄수화물", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.carbohydrate },
  protein: { label: "단백질", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.protein },
  totalFat: { label: "지방", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.total_fat },
  sodium: { label: "나트륨", unit: "mg", digits: 0, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.sodium },
  sugar: { label: "당", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.sugar },
  dietaryFiber: { label: "식이섬유", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.dietary_fiber },
  potassium: { label: "칼륨", unit: "mg", digits: 0, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.potassium },
  calcium: { label: "칼슘", unit: "mg", digits: 0, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.calcium },
  water: { label: "수분 섭취", unit: "mL", digits: 0, source: "water", dateKey: "consumed_at", daily: "sum", value: (row) => row.water_amount },
  // 1,500mL보다 '여섯 잔'이 하루치로 가늠하기 쉽다. 그래프와 표는 mL 그대로 둔다.
  waterCups: {
    label: "수분 섭취", unit: "잔", digits: 1,
    source: "water", dateKey: "consumed_at",
    derive: (payload) => metricDailySeries(payload, lifestyleMetrics.water)
      .map((point) => ({ date: point.date, value: point.value / _WATER_CUP_ML })),
    // 잔은 어림수라 실제로 얼마나 마셨는지를 괄호로 같이 보여 준다.
    note: (rows) => {
      const total = rows.reduce((sum, row) => sum + (Number(row.water_amount) || 0), 0);
      return total ? `(${formatDataNumber(total)}mL)` : "";
    },
  },

  // 3대 영양소는 총열량 대비 비율로 봐야 뜻이 선다. 열량 환산은 Atwater 계수
  // (탄수화물·단백질 4kcal/g, 지방 9kcal/g)를 쓴다. 기록된 calories가 아니라
  // 세 영양소로 낸 열량을 분모로 삼는다. 둘이 어긋날 때 비율의 합이 100%를 벗어난다.
  carbRatio: {
    label: "탄수화물 비중", unit: "%", digits: 0,
    // 카드에는 셋을 합쳐 한 이름으로 건다. 항목 이름은 분석과 같게 둔다.
    pairedWith: ["proteinRatio", "fatRatio"], pairedLabel: "탄수화물 · 단백질 · 지방",
    // 세 숫자의 균형을 한눈에 보는 카드다. 셋을 겹쳐 그리면 선만 어지럽다.
    spark: false,
    derive: (payload) => macroRatioSeries(payload, "carbohydrate"),
  },
  proteinRatio: { label: "단백질 비중", unit: "%", digits: 0, derive: (payload) => macroRatioSeries(payload, "protein") },
  fatRatio: { label: "지방 비중", unit: "%", digits: 0, derive: (payload) => macroRatioSeries(payload, "totalFat") },
  // 포화지방은 지방의 일부라 분자만 다르다. 지방 비중과 나란히 봐야 뜻이 선다.
  saturatedRatio: {
    label: "포화지방 비중", unit: "%", digits: 0,
    derive: (payload) => macroRatioSeries(payload, "saturatedFat"),
  },
  saturatedFat: { label: "포화지방", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.saturated_fat },

  sleepHours: {
    label: "수면시간", unit: "시간", digits: 1,
    source: "sleep", dateKey: "measured_at", daily: "sum", value: (row) => row.value,
    // 몇 시간 잤는지 옆에 몇 시에 자고 일어났는지를 같이 보여 준다.
    note: (rows) => {
      const row = rows[rows.length - 1];
      const start = formatClockTime(row?.detail_data?.start_at);
      const end = formatClockTime(row?.detail_data?.end_at);
      return start && end ? `${start} - ${end}` : "";
    },
  },
  sleepScore: { label: "수면점수", unit: "점", digits: 0, source: "sleep", dateKey: "measured_at", daily: "mean", value: (row) => row.detail_data?.sleep_score },
  // 수면 단계는 lifestyle_sleep의 *_minutes 컬럼에서 온다. 같은 7시간을 자도 어떻게
  // 나뉘었는지가 수면점수의 차이를 설명하므로 셋을 함께 본다.
  deepSleep: { label: "깊은수면", unit: "분", digits: 0, source: "sleep", dateKey: "measured_at", daily: "sum", value: (row) => row.detail_data?.deep_sleep_minutes },
  lightSleep: { label: "얕은수면", unit: "분", digits: 0, source: "sleep", dateKey: "measured_at", daily: "sum", value: (row) => row.detail_data?.light_sleep_minutes },
  remSleep: { label: "REM수면", unit: "분", digits: 0, source: "sleep", dateKey: "measured_at", daily: "sum", value: (row) => row.detail_data?.rem_sleep_minutes },
  awake: { label: "뒤척임", unit: "분", digits: 0, source: "sleep", dateKey: "measured_at", daily: "sum", value: (row) => row.detail_data?.awake_minutes },
};

/* 탭마다 '세부 항목별 그래프 + 수치표' 한 묶음을 그릴 그룹 목록.
   측정값 탭은 여러 계열을 한 시간축에 겹쳐야 읽히므로 꺾은선, 합계 탭은 막대를 쓴다. */
const lifestyleTabConfigs = {
  bio: {
    chart: "line",
    groups: [
      { title: "체중과 BMI", metrics: ["weight", "bmi"] },
      { title: "혈압", metrics: ["systolic", "diastolic"] },
      { title: "혈당", metrics: ["glucoseFasting", "glucoseAfter"] },
      { title: "심박수", metrics: ["heartRate"] },
    ],
  },
  activity: {
    chart: "bar",
    // 걸음 수는 하루 활동량의 대표값, 활동칼로리는 그 결과, 운동은 따로 낸 시간이다.
    // 계단·활동시간·이동거리·운동거리는 이 셋에 딸려 움직여 카드로는 내지 않는다.
    cards: ["steps", "activeCalories", "exerciseTime"],
    groups: [
      { title: "걸음 수", metrics: ["steps"] },
      // 운동은 활동의 일부다. 쌓아 보면 하루에 태운 열량 중 얼마가 따로 낸
      // 운동에서 나왔는지 보인다. 눈금은 200kcal마다 실선, 100kcal마다 점선이다.
      {
        title: "칼로리", chart: "stack",
        axis: { unit: "kcal", step: 100, major: 200, min: 0, max: 600, palette: "calorie-parts" },
        metrics: ["exerciseCalories", "otherCalories"],
        // 표에서는 합계를 앞에 세워 두 조각과 나란히 읽게 한다.
        columns: ["activeCalories", "exerciseCalories", "otherCalories"],
      },
      // 종류별로 쌓으면 막대 높이가 그날 총 운동시간이고, 무엇을 했는지가 같이 보인다.
      // 그래서 운동시간을 따로 그리지 않는다. 표에는 총 운동시간을 앞에 세운다.
      {
        title: "운동시간 및 종류", chart: "stack",
        axis: { unit: "분", step: 15, major: 30, min: 0, max: 60, palette: "exercise-kinds" },
        deriveSeries: exerciseKindSeries,
        metrics: ["exerciseTime"],
        columns: ["exerciseTime", "exerciseDistance"],
      },
    ],
  },
  nutrition: {
    chart: "bar",
    // 나트륨·당은 그래프에서 본다. 카드에 일곱 장을 늘어놓으면 무엇을 먼저 볼지 모른다.
    // 비율 셋을 모두 적어야 한 카드로 합쳐진다. 짝은 이 목록 안에서만 찾는다.
    cards: ["intakeCalories", "carbRatio", "proteinRatio", "fatRatio", "waterCups"],
    groups: [
      { title: "섭취칼로리", metrics: ["intakeCalories"] },
      { title: "탄수화물", metrics: ["carbohydrate"] },
      { title: "단백질", metrics: ["protein"] },
      { title: "지방", metrics: ["totalFat"] },
      // 나트륨과 칼륨은 함께 봐야 뜻이 선다. 칼륨이 나트륨을 덜어 내는 쪽이다.
      { title: "나트륨과 칼륨", metrics: ["sodium", "potassium"] },
      { title: "당", metrics: ["sugar"] },
      { title: "식이섬유", metrics: ["dietaryFiber"] },
      { title: "칼슘", metrics: ["calcium"] },
      // 지방은 총량보다 그 안에 포화지방이 얼마나 되는지가 문제가 된다.
      { title: "지방과 포화지방 비중", metrics: ["fatRatio", "saturatedRatio"] },
      { title: "수분 섭취", metrics: ["water"] },
    ],
  },
  sleep: {
    chart: "line",
    groups: [
      // 단계는 서로 견줘야 뜻이 생긴다. 쌓아 보여야 하루 수면의 구성이 보인다.
      // 눈금은 3·6·9시간을 실선으로 고정하고 그 사이는 점선으로 둔다.
      // 잠이 3시간보다 짧거나 9시간보다 길면 3시간 단위로 축을 넓힌다.
      {
        title: "수면시간 및 단계", chart: "stack",
        axis: { unit: "시간", divisor: 60, step: 1, major: 3, min: 3, max: 9, palette: "sleep-stages" },
        // 막대에 쌓는 것은 단계뿐이다. 총 수면시간은 합이 아니라 견줄 값이라 쌓지 않는다.
        metrics: ["deepSleep", "lightSleep", "remSleep", "awake"],
        // 표에서는 총 수면시간을 앞에 세워 단계 합과 나란히 읽게 한다.
        columns: ["sleepHours", "deepSleep", "lightSleep", "remSleep", "awake"],
        // 단계는 서로 견줘야 뜻이 생기는 값이라 카드 한 장씩으로는 읽히지 않는다.
        // 카드에는 총 수면시간만 두고 구성은 아래 그래프와 표에서 본다.
        cards: ["sleepHours"],
      },
      { title: "수면점수", metrics: ["sleepScore"] },
    ],
  },
};

// 물 한 잔. 종이컵·머그 한 잔이 대략 이만큼이다.
const _WATER_CUP_ML = 250;
// 열량 환산 계수(kcal/g). 지방만 9인 것이 비율을 무게 비율과 다르게 만든다.
const _MACRO_KCAL = { carbohydrate: 4, protein: 4, totalFat: 9 };
// 분모에는 들어가지 않고 분자로만 쓰는 항목. 포화지방은 지방 안에 이미 들어 있다.
const _NON_MACRO_KCAL = { saturatedFat: 9 };

function macroRatioSeries(payload, target) {
  // 하루 총열량 대비 몇 %인지. 세 영양소가 모두 있는 날만 비율을 낸다.
  // 분모는 늘 세 영양소로 낸 열량이고, 분자만 고른다. 포화지방은 지방의 일부라
  // 분모에 더하지 않는다. 더하면 같은 열량을 두 번 세게 된다.
  const parts = Object.keys(_MACRO_KCAL).map((key) => ({
    key,
    days: new Map(metricDailySeries(payload, lifestyleMetrics[key])
      .map((point) => [point.date, point.value * _MACRO_KCAL[key]])),
  }));
  const numerator = _MACRO_KCAL[target]
    ? parts.find((part) => part.key === target).days
    : new Map(metricDailySeries(payload, lifestyleMetrics[target])
      .map((point) => [point.date, point.value * _NON_MACRO_KCAL[target]]));
  const series = [];
  [...parts[0].days.keys()].sort().forEach((date) => {
    if (parts.some((part) => !part.days.has(date)) || !numerator.has(date)) return;
    const total = parts.reduce((sum, part) => sum + part.days.get(date), 0);
    if (total <= 0) return;
    series.push({ date, value: numerator.get(date) / total * 100 });
  });
  return series;
}

// 운동 종류 이름. lifestyle_exercise.exercise_type은 enum이 아니라 자유 문자열이라
// 새 값이 언제든 들어온다. 아는 것만 옮기고 모르는 값은 원문을 그대로 보여 준다.
// 서비스 쪽 _EXERCISE_KIND_NAMES와 같은 목록을 쓴다.
const exerciseKindNames = {
  walking: "걷기", running: "달리기", hiking: "등산", cycling: "자전거",
  indoor_cycling: "실내 자전거", swimming: "수영", weight_machine: "웨이트",
  yoga: "요가", pilates: "필라테스", climbing: "클라이밍", badminton: "배드민턴",
  tennis: "테니스", golf: "골프", dancing: "댄스", treadmill: "러닝머신",
  elliptical: "일립티컬", stair_climbing: "계단 오르기", other_workout: "기타 운동",
};
// 색 계열이 넷뿐이라 그보다 많으면 뒤쪽이 같은 색으로 겹친다. 적게 한 종류는 묶는다.
const _MAX_EXERCISE_KIND_SERIES = 4;

function exerciseKindSeries(payload) {
  // 종류는 사용자마다 다르다. 항목을 미리 적을 수 없어 기록에서 직접 만든다.
  const rows = (payload.exercise || {}).rows || [];
  const totals = new Map();
  const byKind = new Map();
  rows.forEach((row) => {
    const date = String(row.record_date || "").slice(0, 10);
    const minutes = Number(row.duration_sec) / 60;
    const kind = String(row.exercise_type || "").trim();
    if (!date || !kind || !Number.isFinite(minutes)) return;
    totals.set(kind, (totals.get(kind) || 0) + minutes);
    if (!byKind.has(kind)) byKind.set(kind, new Map());
    const days = byKind.get(kind);
    days.set(date, (days.get(date) || 0) + minutes);
  });
  if (!totals.size) return [];
  const ranked = [...totals.keys()].sort((left, right) => totals.get(right) - totals.get(left));
  const kept = ranked.slice(0, _MAX_EXERCISE_KIND_SERIES);
  const rest = ranked.slice(_MAX_EXERCISE_KIND_SERIES);
  const toPoints = (days) => [...days.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([date, value]) => ({ date, value }));
  const series = kept.map((kind) => ({
    key: `kind:${kind}`,
    label: exerciseKindNames[kind.toLowerCase()] || kind,
    unit: "분",
    digits: 0,
    points: toPoints(byKind.get(kind)),
  }));
  if (rest.length) {
    const merged = new Map();
    rest.forEach((kind) => byKind.get(kind).forEach((value, date) => {
      merged.set(date, (merged.get(date) || 0) + value);
    }));
    series.push({ key: "kind:rest", label: `그 외 ${rest.length}가지`, unit: "분", digits: 0, points: toPoints(merged) });
  }
  return series;
}

// 당일 카드는 그래프 그룹에 쓰인 항목을 같은 순서로 보여준다.
function lifestyleTabMetricKeys(tab) {
  const config = lifestyleTabConfigs[tab] || {};
  // 탭이 cards를 두면 그것만 카드로 낸다. 그래프에 있는 항목을 모두 카드로 내면
  // 활동기록처럼 여덟 장까지 늘어 무엇을 먼저 봐야 할지 알 수 없다.
  if (config.cards) return [...new Set(config.cards)];
  // 그 다음은 그룹이 cards로 고른 것, 표 항목, 그래프 항목 순이다.
  // 수면 단계처럼 표에만 두고 카드에서는 뺄 때 쓴다.
  const keys = (config.groups || [])
    .flatMap((group) => group.cards || group.columns || group.metrics);
  return [...new Set(keys)];
}
function buildDataTable(columns, rows) {
  const scroll = document.createElement("div");
  scroll.className = "data-table-scroll";
  const table = document.createElement("table");
  table.className = "data-table";

  const headRow = document.createElement("tr");
  columns.forEach((column) => {
    const th = document.createElement("th");
    th.scope = "col";
    if (column.numeric) th.className = "numeric";
    th.textContent = column.label;
    headRow.appendChild(th);
  });
  const thead = document.createElement("thead");
  thead.appendChild(headRow);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((column) => {
      const cell = document.createElement("td");
      if (column.numeric) cell.className = "numeric";
      const value = column.value(row);
      // 개인 데이터는 항상 textContent로 넣어 마크업으로 해석되지 않게 한다.
      if (value instanceof Node) cell.appendChild(value);
      else cell.textContent = String(value);
      tr.appendChild(cell);
    });
    tbody.appendChild(tr);
  });

  table.append(thead, tbody);
  scroll.appendChild(table);
  return scroll;
}

function metricDailySeries(payload, metric) {
  // 다른 항목에서 끌어내는 항목은 저장소 행 대신 제 계산식을 쓴다.
  if (metric.derive) return metric.derive(payload);
  // 하루에 여러 건 들어오는 항목은 daily 규칙(합계·평균)으로 하루 한 점으로 줄인다.
  const rows = (payload[metric.source] || {}).rows || [];
  const buckets = new Map();
  rows.forEach((row) => {
    if (metric.keep && !metric.keep(row)) return;
    const date = String(row[metric.dateKey] || "").slice(0, 10);
    const value = Number(metric.value(row));
    if (!date || !Number.isFinite(value)) return;
    if (!buckets.has(date)) buckets.set(date, []);
    buckets.get(date).push(value);
  });
  return [...buckets.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([date, values]) => ({
      date,
      value: metric.daily === "sum"
        ? values.reduce((sum, value) => sum + value, 0)
        : values.reduce((sum, value) => sum + value, 0) / values.length,
    }));
}

// 눈금선의 세로 위치. bottom으로 잡으면 맨 위 눈금이 컨테이너 밖 1px에 그려져
// overflow에 잘린다(9시간 실선이 안 보이던 원인). 위에서부터 재면 안쪽에 들어온다.
// 숫자는 .data-chart-bars(150px, 아래 여백 22px)와 .data-chart-item(128px)에서 온다.
const _CHART_PLOT_HEIGHT = 150;
const _CHART_PLOT_BOTTOM = 22;
const _CHART_BAR_HEIGHT = 128;

function chartGuideTop(tick, max) {
  return _CHART_PLOT_HEIGHT - _CHART_PLOT_BOTTOM - (tick / max) * _CHART_BAR_HEIGHT;
}

function buildLifestyleBarChart(title, metric, points, days, gapDate) {
  if (!points.length) return null;
  const max = Math.max(...points.map((point) => point.value), 1);
  const ticks = [0, max / 2, max];
  const chart = document.createElement("div");
  chart.className = "data-chart";
  const heading = document.createElement("div");
  heading.className = "data-chart-title";
  heading.textContent = metric.unit ? `${title} (${metric.unit})` : title;
  const plot = document.createElement("div");
  plot.className = "data-chart-plot";
  const axis = document.createElement("div");
  axis.className = "data-chart-axis";
  ticks.slice().reverse().forEach((tick) => {
    const label = document.createElement("span");
    label.textContent = formatDataNumber(tick, metric.digits);
    label.style.bottom = `${(tick / max) * 100}%`;
    axis.appendChild(label);
  });
  const bars = document.createElement("div");
  bars.className = "data-chart-bars";
  ticks.forEach((tick) => {
    const guide = document.createElement("i");
    guide.className = "data-chart-guide";
    if (tick === 0) guide.classList.add("zero");
    guide.style.top = `${chartGuideTop(tick, max)}px`;
    bars.appendChild(guide);
  });
  if (gapDate) bars.appendChild(buildEmptyChartSlot(gapDate, days));
  points.forEach((point) => {
    const item = document.createElement("div");
    item.className = "data-chart-item";
    const bar = document.createElement("span");
    bar.className = isSparseBucket(metric, point) ? "data-chart-bar is-sparse" : "data-chart-bar";
    bar.style.height = `${Math.max((point.value / max) * 100, 8)}%`;
    const coverage = point.span > 1 ? ` (${bucketCoverageText(point)})` : "";
    bar.title = `${formatBucketDate(point.date, days)}: ${formatDataNumber(point.value, metric.digits)}${metric.unit ? ` ${metric.unit}` : ""}${coverage}`;
    const label = document.createElement("small");
    label.textContent = formatBucketDate(point.date, days);
    item.append(bar, label);
    bars.appendChild(item);
  });
  plot.append(axis, bars);
  chart.append(heading, plot);
  return chart;
}

function stackedAxisTicks(totals, axisSpec) {
  // 눈금은 늘 같은 자리에 있어야 날짜를 오가며 봐도 높이가 비교된다. 그래서 기본
  // 구간(수면은 3~9시간)을 고정해 두고, 값이 그 밖으로 나갈 때만 major 간격으로 넓힌다.
  const step = axisSpec.step || 1;
  const major = axisSpec.major || step;
  const scaled = totals.map((total) => total / (axisSpec.divisor || 1));
  const baseLow = axisSpec.min === undefined ? 0 : axisSpec.min;
  const baseHigh = axisSpec.max === undefined ? major : axisSpec.max;
  const low = Math.min(baseLow, Math.floor(Math.min(...scaled) / major) * major);
  const high = Math.max(baseHigh, Math.ceil(Math.max(...scaled) / major) * major);
  const ticks = [];
  for (let tick = low; tick <= high; tick += step) ticks.push(tick);
  // 막대는 0부터 쌓이므로 눈금의 위치는 축 전체(0~high) 기준으로 잡는다.
  return { ticks, major, max: high };
}

function buildStackedChart(title, series, axisSpec, days, gapDate) {
  // 날짜마다 계열을 쌓아 하루가 어떻게 나뉘었는지 보여 준다.
  const dates = [...new Set(series.flatMap((item) => item.points.map((point) => point.date)))].sort();
  if (!dates.length) return null;
  const valueAt = series.map((item) => new Map(item.points.map((point) => [point.date, point.value])));
  const totals = dates.map((date) => valueAt.reduce((sum, map) => sum + (map.get(date) || 0), 0));
  // 축은 원래 단위(분)를 읽기 쉬운 단위(시간)로 바꿔 표시한다.
  const axisSpecs = axisSpec || { unit: series[0].unit, divisor: 1, step: 1 };
  const { ticks, major, max } = stackedAxisTicks(totals, axisSpecs);

  const chart = document.createElement("div");
  chart.className = axisSpecs.palette ? `data-chart ${axisSpecs.palette}` : "data-chart";
  const heading = createTextElement("div", "data-chart-title",
    axisSpecs.unit ? `${title} (${axisSpecs.unit})` : title);
  const plot = document.createElement("div");
  plot.className = "data-chart-plot";
  const axis = document.createElement("div");
  axis.className = "data-chart-axis";
  // 눈금선은 한 시간마다 긋되 숫자는 실선(3시간 배수)에만 붙여 왼쪽이 빽빽해지지 않게 한다.
  ticks.filter((tick) => tick % major === 0).reverse().forEach((tick) => {
    const label = createTextElement("span", "", formatDataNumber(tick));
    label.style.bottom = `${(tick / max) * 100}%`;
    axis.appendChild(label);
  });
  const bars = document.createElement("div");
  bars.className = "data-chart-bars";
  ticks.forEach((tick) => {
    const guide = document.createElement("i");
    guide.className = tick % major === 0 ? "data-chart-guide solid" : "data-chart-guide";
    if (tick === 0) guide.classList.add("zero");
    guide.style.top = `${chartGuideTop(tick, max)}px`;
    bars.appendChild(guide);
  });
  if (gapDate) bars.appendChild(buildEmptyChartSlot(gapDate, days));
  dates.forEach((date, index) => {
    const item = document.createElement("div");
    item.className = "data-chart-item";
    const stack = document.createElement("span");
    // 계열 하나만 봐도 그 묶음의 기록 촘촘함은 같다. 첫 계열로 판단한다.
    const sparse = series.some((entry, order) => {
      const point = entry.points.find((item) => item.date === date);
      return point && isSparseBucket(entry, point);
    });
    stack.className = sparse ? "data-chart-bar stack is-sparse" : "data-chart-bar stack";
    const scaledTotal = totals[index] / (axisSpecs.divisor || 1);
    stack.style.height = `${Math.max((scaledTotal / max) * 100, 4)}%`;
    // 아래에서 위로 쌓이도록 계열 순서대로 넣는다. 높이는 그날 총합 대비 비율이다.
    series.forEach((entry, order) => {
      const value = valueAt[order].get(date) || 0;
      if (!value) return;
      const segment = document.createElement("i");
      segment.className = `data-chart-segment s${order % _CHART_COLOR_COUNT}`;
      segment.style.height = `${(value / (totals[index] || 1)) * 100}%`;
      const point = entry.points.find((item) => item.date === date);
      const coverage = point && point.span > 1 ? ` · ${bucketCoverageText(point)}` : "";
      segment.title = `${formatBucketDate(date, days)} ${entry.label}: ${formatDataNumber(value, entry.digits)}${entry.unit ? ` ${entry.unit}` : ""}${coverage}`;
      stack.appendChild(segment);
    });
    item.append(stack, createTextElement("small", "", formatBucketDate(date, days)));
    bars.appendChild(item);
  });
  plot.append(axis, bars);
  const legend = document.createElement("div");
  legend.className = "line-chart-legend";
  series.forEach((entry, order) => {
    const label = createTextElement("span", "", entry.label);
    label.style.setProperty("--legend-color", `var(--chart-s${order % _CHART_COLOR_COUNT})`);
    legend.appendChild(label);
  });
  chart.append(heading, plot, legend);
  return chart;
}

function weekOfMonthLabel(date) {
  // 월~일 한 주에서 목요일은 늘 그 주가 더 많이 걸친 달에 있다(ISO 주 규칙).
  // 그래서 목요일이 속한 달과 그 달에서 몇 번째 주인지로 이름을 붙인다.
  const monday = new Date(`${date}T00:00:00Z`);
  const thursday = new Date(monday.getTime() + 3 * 24 * 60 * 60 * 1000);
  const week = Math.floor((thursday.getUTCDate() - 1) / 7) + 1;
  return `${thursday.getUTCMonth() + 1}월${week}주`;
}

function formatBucketDate(date, days) {
  // 묶음 단위에 맞춰 x축을 읽는다. 주 단위는 날짜보다 '몇 월 몇 주'가 알아보기 쉽다.
  if (days >= 180) return formatGraphDate(date);
  if (days >= 90) return weekOfMonthLabel(date);
  return formatGraphDate(date);
}

function bucketCoverageText(point) {
  return `${point.span}일 중 ${point.count}일 기록`;
}

function isSparseBucket(metric, point) {
  // 하루 누적 지표만 해당한다. 체중·혈압처럼 이따금 재는 값은 며칠 비어도 정상이다.
  return metric.daily === "sum" && point.span > 1 && point.count * 2 < point.span;
}

function withTopicParticle(word) {
  // 한글은 끝 글자의 받침으로 은/는이 갈린다. BMI·REM처럼 로마자로 끝나면 '는'을 쓴다.
  const last = String(word || "").trim().slice(-1);
  const code = last.charCodeAt(0);
  const isHangul = code >= 0xac00 && code <= 0xd7a3;
  if (!isHangul) return `${word}는`;
  return `${word}${(code - 0xac00) % 28 === 0 ? "는" : "은"}`;
}

function buildEmptyChartSlot(date, days) {
  // 값은 없고 x축 이름만 있는 칸. 기록이 시작되기 직전 자리를 보여 준다.
  const item = document.createElement("div");
  item.className = "data-chart-item is-blank";
  item.title = "기록 없음";
  item.appendChild(createTextElement("small", "", formatBucketDate(date, days)));
  return item;
}

function lifestyleBucketLabel(days) {
  if (days >= 180) return "월";
  if (days >= 90) return "주 시작일";
  return "일자";
}

function buildTrendTable(series, days) {
  // 계열마다 기록된 날이 달라도 한 표에서 견줄 수 있게 날짜를 합쳐 최신순으로 세운다.
  const dates = [...new Set(series.flatMap((item) => item.points.map((point) => point.date)))]
    .sort((left, right) => right.localeCompare(left));
  const valueByDate = series.map((item) => new Map(item.points.map((point) => [point.date, point.value])));
  const columns = [
    { label: lifestyleBucketLabel(days), value: (row) => formatBucketDate(row.date, days) },
    ...series.map((item, index) => ({
      label: item.unit ? `${item.label}(${item.unit})` : item.label,
      numeric: true,
      value: (row) => formatDataNumber(valueByDate[index].get(row.date), item.digits),
    })),
  ];
  return buildDataTable(columns, dates.map((date) => ({ date })));
}
function lifestyleBucket(value, days) {
  const text = String(value || "").slice(0, 10);
  if (!text) return "";
  if (days >= 180) return text.slice(0, 7);
  if (days >= 90) {
    // 주 시작일 계산은 UTC로만 한다. 로컬 시간으로 만들면 toISOString이 날짜를 하루 당긴다.
    const current = new Date(`${text}T00:00:00Z`);
    const day = current.getUTCDay() || 7;
    current.setUTCDate(current.getUTCDate() - day + 1);
    return current.toISOString().slice(0, 10);
  }
  return text;
}

function bucketSpan(date, days) {
  // 묶음 하나가 며칠짜리인지. 기록이 얼마나 촘촘한지 재는 분모가 된다.
  if (days >= 180) return new Date(Date.UTC(Number(date.slice(0, 4)), Number(date.slice(5, 7)), 0)).getUTCDate();
  return days >= 90 ? 7 : 1;
}

function previousBucket(date, days) {
  // 묶음 단위만큼 하나 앞으로 되짚는다. 기록 시작 전에 빈칸을 한 칸 두기 위한 것이다.
  if (days >= 180) {
    const month = new Date(`${date}-01T00:00:00Z`);
    month.setUTCMonth(month.getUTCMonth() - 1);
    return month.toISOString().slice(0, 7);
  }
  const day = new Date(`${date}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() - (days >= 90 ? 7 : 1));
  return day.toISOString().slice(0, 10);
}

function windowStartBucket(latestDate, days) {
  // 고른 기간이 실제로 어디까지 거슬러 올라가는지. 기록 시작일과 견줄 기준이다.
  if (!latestDate) return "";
  const start = new Date(`${latestDate}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return lifestyleBucket(start.toISOString().slice(0, 10), days);
}

function bucketSeries(series, days) {
  // 구간이 길면 일별 점이 너무 촘촘해지므로 주·월로 묶어 일평균으로 본다.
  const buckets = new Map();
  series.forEach((point) => {
    const key = lifestyleBucket(point.date, days);
    if (!key) return;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(point.value);
  });
  return [...buckets.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([date, values]) => ({
      date,
      value: values.reduce((sum, value) => sum + value, 0) / values.length,
      // 기록이 있는 날만 평균에 들어간다. 며칠이 빠졌는지 알아야 값을 믿을지 판단할 수 있다.
      count: values.length,
      span: bucketSpan(date, days),
    }));
}

function lifestyleAggregationLabel(days) {
  if (days >= 180) return "월평균";
  if (days >= 90) return "주평균";
  return "일별";
}

function svgNode(name, attributes, text = "") {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text) node.textContent = text;
  return node;
}

function buildLineChart(title, series, days, gapDate) {
  const colors = ["#2f8f6b", "#e3924d", "#5e83c5", "#bd6c9b"];
  const plots = series.map((item) => item.points
    .map((point) => ({ x: String(point.date || ""), value: Number(point.value) }))
    .filter((point) => point.x && Number.isFinite(point.value))
    .sort((left, right) => left.x.localeCompare(right.x)));
  // 시리즈마다 x를 새로 매기면 선이 옆으로 나열되므로 측정 시점을 공통 축으로 삼아 겹쳐 그린다.
  const axis = [...new Set(plots.flat().map((point) => point.x))].sort();
  if (!axis.length) return null;
  // 기록이 시작되기 전 한 칸을 비워 두면 언제부터 값이 생겼는지 눈에 들어온다.
  if (gapDate) axis.unshift(gapDate);
  const scaleOf = (group) => {
    const values = group.flat().map((point) => point.value);
    if (!values.length) return null;
    const min = Math.min(...values);
    return { min, max: Math.max(...values, min + 1) };
  };
  // 체중과 BMI처럼 단위가 다른 짝은 축을 좌우로 나눠야 각 선의 변화가 눌리지 않는다.
  const rightScale = scaleOf(plots.filter((_, index) => series[index].axis === "right"));
  const leftScale = scaleOf(plots.filter((_, index) => series[index].axis !== "right"));
  const baseScale = leftScale || rightScale;
  const dualAxis = Boolean(leftScale && rightScale);
  const scaleOfSeries = (index) => (dualAxis && series[index].axis === "right" ? rightScale : baseScale);
  const colorOfAxis = (side) => colors[series.findIndex((item) => (item.axis === "right") === (side === "right"))];
  const width = 720;
  const height = 138;
  const padLeft = 44;
  const padRight = dualAxis ? 44 : 12;
  const span = width - padLeft - padRight;
  const position = new Map(axis.map((key, index) => [key, index]));
  const x = (key) => axis.length === 1
    ? padLeft + span / 2
    : padLeft + (position.get(key) / (axis.length - 1)) * span;
  const yRatio = (ratio) => height - ratio * (height - 18) - 8;
  const y = (scale, value) => yRatio((value - scale.min) / (scale.max - scale.min));
  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height + 22}` });
  svg.appendChild(svgNode("line", { x1: padLeft, x2: padLeft, y1: yRatio(1), y2: yRatio(0), class: "line-chart-axis" }));
  if (dualAxis) {
    svg.appendChild(svgNode("line", {
      x1: width - padRight, x2: width - padRight, y1: yRatio(1), y2: yRatio(0), class: "line-chart-axis",
    }));
  }
  [0, .5, 1].forEach((ratio) => {
    svg.appendChild(svgNode("line", {
      x1: padLeft, x2: width - padRight, y1: yRatio(ratio), y2: yRatio(ratio), class: "line-chart-grid",
    }));
    svg.appendChild(svgNode("text", {
      x: padLeft - 6, y: yRatio(ratio), "text-anchor": "end", "dominant-baseline": "middle",
      class: "line-chart-axis-label", ...(dualAxis ? { style: `fill: ${colorOfAxis("left")}` } : {}),
    }, formatDataNumber(baseScale.min + (baseScale.max - baseScale.min) * ratio, 1)));
    if (!dualAxis) return;
    svg.appendChild(svgNode("text", {
      x: width - padRight + 6, y: yRatio(ratio), "text-anchor": "start", "dominant-baseline": "middle",
      class: "line-chart-axis-label", style: `fill: ${colorOfAxis("right")}`,
    }, formatDataNumber(rightScale.min + (rightScale.max - rightScale.min) * ratio, 1)));
  });
  plots.forEach((itemPoints, seriesIndex) => {
    if (!itemPoints.length) return;
    const color = colors[seriesIndex % colors.length];
    const scale = scaleOfSeries(seriesIndex);
    // 전역 svg 규칙이 stroke·fill 속성을 덮으므로 계열 색은 인라인 스타일로 지정한다.
    svg.appendChild(svgNode("path", {
      d: itemPoints.map((point, index) => `${index ? "L" : "M"}${x(point.x)} ${y(scale, point.value)}`).join(" "),
      style: `stroke: ${color}`,
      class: "line-chart-line",
    }));
    itemPoints.forEach((point) => {
      svg.appendChild(svgNode("circle", {
        cx: x(point.x), cy: y(scale, point.value), r: 2.8, style: `fill: ${color}`, class: "line-chart-point",
        "aria-label": `${formatDataDate(point.x)} ${series[seriesIndex].label} ${formatDataNumber(point.value, series[seriesIndex].digits ?? 1)}`,
      }));
    });
  });
  // 눈금이 겹쳐 뭉개지지 않도록 처음과 끝을 포함해 최대 6개만 균등하게 찍는다.
  const tickCount = Math.min(axis.length, 6);
  const tickIndexes = [...new Set(Array.from({ length: tickCount }, (_, index) =>
    Math.round((index * (axis.length - 1)) / Math.max(tickCount - 1, 1))))];
  tickIndexes.forEach((index) => {
    svg.appendChild(svgNode("text", {
      x: x(axis[index]),
      y: height + 16,
      "text-anchor": index === 0 ? "start" : index === axis.length - 1 ? "end" : "middle",
      class: "line-chart-label",
    }, formatBucketDate(axis[index], days)));
  });
  const chart = document.createElement("div"); chart.className = "line-chart";
  const heading = document.createElement("div"); heading.className = "line-chart-title"; heading.textContent = title;
  const legend = document.createElement("div"); legend.className = "line-chart-legend";
  series.forEach((item, index) => {
    const label = document.createElement("span");
    const name = item.unit ? `${item.label}(${item.unit})` : item.label;
    // 축이 둘이면 어느 눈금을 읽어야 하는지 범례에서 알려준다.
    label.textContent = dualAxis ? `${name} · ${item.axis === "right" ? "우축" : "좌축"}` : name;
    label.style.setProperty("--legend-color", colors[index % colors.length]);
    legend.appendChild(label);
  });
  chart.append(heading, svg, legend); return chart;
}

function setDataPlaceholder(container, message, isError = false) {
  const placeholder = document.createElement("p");
  placeholder.className = isError ? "data-placeholder data-error" : "data-placeholder";
  placeholder.textContent = message;
  container.replaceChildren(placeholder);
}

function renderCheckup(payload) {
  const items = payload.items || [];
  elements.checkupMeta.textContent = payload.measured_at
    ? `검진일 ${payload.measured_at} · ${items.length}개 항목`
    : "검진 기록 없음";
  if (!items.length) {
    setDataPlaceholder(elements.checkupBody, "등록된 검진 결과가 없습니다.");
    return;
  }
  elements.checkupBody.replaceChildren(buildDataTable(checkupColumns, items));
  setDashboardStep("latest", `선택 검진 ${payload.measured_at || "없음"}`);
}

function resetCheckupRecords() {
  checkupRecords = [];
  selectedCheckupRecordId = "";
  elements.checkupRecordSelect.replaceChildren();
  elements.checkupRecordSelect.disabled = true;
}

async function loadCheckupRecords() {
  const response = await fetchWithSession("/me/checkup/records", { headers: { Accept: "application/json" } });
  if (response.status === 401) {
    showLoginScreen("다시 로그인해 주세요.");
    return false;
  }
  const payload = await response.json().catch(() => []);
  if (!response.ok) throw new Error(String(payload.detail || "검진 회차를 불러오지 못했습니다."));
  checkupRecords = Array.isArray(payload) ? payload : [];
  elements.checkupRecordSelect.replaceChildren();
  checkupRecords.forEach((record, index) => {
    const option = document.createElement("option");
    option.value = record.record_id;
    option.textContent = index === 0 ? `가장 최신 검진 · ${record.measured_at}` : `검진 · ${record.measured_at}`;
    elements.checkupRecordSelect.appendChild(option);
  });
  // 다시 불러오기로 목록을 갱신해도 사용자가 고른 회차를 유지하고, 없어진 회차만 최신으로 되돌린다.
  const stillExists = checkupRecords.some((record) => record.record_id === selectedCheckupRecordId);
  selectedCheckupRecordId = stillExists ? selectedCheckupRecordId : checkupRecords[0]?.record_id || "";
  elements.checkupRecordSelect.value = selectedCheckupRecordId;
  elements.checkupRecordSelect.disabled = !checkupRecords.length;
  return true;
}

/* 오른쪽 검증 패널. 검진과 생활건강이 같은 뼈대(4단계 흐름·4지표·로그·상세)를 쓰고
   단계와 지표 이름만 탭에 맞춰 바뀐다. 탭을 오갈 때 그 탭의 마지막 로그를 되살린다. */
const DASHBOARD_STEPS = ["latest", "history", "analysis", "result"];

const dashboardPresets = {
  checkup: {
    title: "검진 분석 검증",
    steps: ["선택 검진 조회", "전체 이력 수집", "AI 요약분석", "리포트 응답"],
    metrics: ["검진 회차", "분석 지표", "개선", "관리 필요"],
    idleLog: "AI 요약분석을 실행하면 처리 단계와 결과가 이곳에 기록됩니다.",
  },
  lifestyle: {
    title: "생활건강 분석 검증",
    steps: ["구간 데이터 조회", "항목별 지표 계산", "AI 요약분석", "리포트 응답"],
    metrics: ["분석 항목", "범위 이탈", "이상 지점", "관리 필요"],
    idleLog: "탭에서 AI 요약분석을 실행하면 처리 단계와 결과가 이곳에 기록됩니다.",
  },
};

// 탭마다 마지막 실행 기록. 탭을 옮겼다 돌아와도 그 탭의 로그가 그대로 남는다.
const dashboardResults = new Map();

function dashboardPreset(tab = activeDataTab) {
  return dashboardPresets[tab] || dashboardPresets.checkup;
}

function setDashboardStep(step, message, state = "done", record = true) {
  const item = document.querySelector(`[data-dashboard-step="${step}"]`);
  if (!item) return;
  item.dataset.state = state;
  const label = item.querySelector(`[data-dashboard-step-status="${step}"]`);
  if (label) label.textContent = message;
  // 되살릴 수 있도록 진행 상황을 탭별로 기록한다. 초기화·복원은 기록하지 않는다.
  const result = record ? dashboardResults.get(activeDataTab) : null;
  if (result) result.steps[step] = { message, state };
}

function setDashboardMetrics(values) {
  elements.dashboardMetricValues.forEach((element, index) => {
    const value = values[index];
    element.textContent = value === null || value === undefined ? "—" : String(value);
  });
}

function setDashboardBadge(text, tone = "neutral") {
  elements.dashboardStatusBadge.textContent = text;
  elements.dashboardStatusBadge.className = `quality-badge ${tone}`;
}

function formatElapsed(value) {
  const seconds = Number(value);
  return Number.isFinite(seconds) ? `${seconds.toFixed(3)}초` : "측정 불가";
}

function resetDashboardFlow(tab = activeDataTab) {
  const preset = dashboardPreset(tab);
  DASHBOARD_STEPS.forEach((step) => setDashboardStep(step, "대기 중", "pending", false));
  setDashboardBadge("대기");
  setDashboardMetrics([]);
  elements.dashboardReportLog.textContent = preset.idleLog;
  elements.dashboardVerificationDetails.replaceChildren();
  elements.dashboardVerificationDetails.hidden = true;
}

function applyDashboardPreset(tab) {
  const preset = dashboardPreset(tab);
  elements.dashboardPanelTitle.textContent = preset.title;
  DASHBOARD_STEPS.forEach((step, index) => {
    const label = document.querySelector(`[data-dashboard-step-label="${step}"]`);
    if (label) label.textContent = preset.steps[index];
  });
  elements.dashboardMetricLabels.forEach((element, index) => {
    element.textContent = preset.metrics[index] || "";
  });

  const result = dashboardResults.get(tab);
  if (!result) {
    resetDashboardFlow(tab);
    return;
  }
  // 이 탭에서 이미 돌린 분석이 있으면 그때의 단계·지표·로그를 그대로 되살린다.
  DASHBOARD_STEPS.forEach((step) => {
    const saved = result.steps[step] || { message: "대기 중", state: "pending" };
    setDashboardStep(step, saved.message, saved.state, false);
  });
  setDashboardBadge(result.badge.text, result.badge.tone);
  setDashboardMetrics(result.metrics);
  elements.dashboardReportLog.textContent = result.log;
  // 상세 항목 구성도 탭마다 다르므로 저장해 둔 것을 함께 되살린다.
  if (result.verification) renderDashboardVerification(result.verification, result.sections);
  else {
    elements.dashboardVerificationDetails.replaceChildren();
    elements.dashboardVerificationDetails.hidden = true;
  }
}

function appendDashboardDetails(title, value) {
  const details = document.createElement("details");
  details.className = "dashboard-detail";
  const summary = document.createElement("summary");
  summary.textContent = title;
  const content = document.createElement("pre");
  content.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  details.append(summary, content);
  elements.dashboardVerificationDetails.appendChild(details);
}

function renderDashboardVerification(verification, sections = null) {
  elements.dashboardVerificationDetails.replaceChildren();
  const timings = verification.timings || {};
  appendDashboardDetails("단계별 소요 시간", Object.fromEntries(
    Object.entries(timings).map(([key, value]) => [key, `${Number(value).toFixed(3)}초`]),
  ));
  (sections || [
    ["분석에 전달된 지표와 DB 판정", verification.analysis_input || {}],
    ["전체 검진 원본 이력", verification.history || []],
    ["데이터 출처 및 판정 기준", { source: verification.source, db_status_used: verification.db_status_used }],
  ]).forEach(([title, value]) => appendDashboardDetails(title, value));
  elements.dashboardVerificationDetails.hidden = false;
}

function finishDashboardRun(tab, { badge, metrics, log, verification, sections = null }) {
  const result = dashboardResults.get(tab) || { steps: {} };
  Object.assign(result, { badge, metrics, log, verification, sections });
  dashboardResults.set(tab, result);
  setDashboardBadge(badge.text, badge.tone);
  setDashboardMetrics(metrics);
  elements.dashboardReportLog.textContent = log;
  renderDashboardVerification(verification, sections);
}

function failDashboardRun(tab, message) {
  const result = dashboardResults.get(tab) || { steps: {} };
  Object.assign(result, { badge: { text: "오류", tone: "warning" }, metrics: [], log: message, verification: null });
  dashboardResults.set(tab, result);
  setDashboardBadge("오류", "warning");
  setDashboardMetrics([]);
  elements.dashboardReportLog.textContent = message;
}

function renderCheckupReport(report) {
  elements.checkupReport.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = report.headline;
  const summary = document.createElement("p");
  summary.textContent = report.summary;
  const analysis = document.createElement("p");
  analysis.textContent = report.overall_analysis;
  const recommendations = document.createElement("ul");
  (report.recommendations || []).forEach((recommendation) => {
    const item = document.createElement("li");
    item.textContent = recommendation;
    recommendations.appendChild(item);
  });
  elements.checkupReport.append(heading, summary, analysis);
  if (recommendations.children.length) elements.checkupReport.append(recommendations);
  elements.checkupReport.hidden = false;
}

async function loadCheckupReport() {
  dashboardResults.set("checkup", { steps: {}, badge: { text: "실행 중", tone: "info" }, metrics: [], log: "" });
  setDashboardStep("history", "DB 전체 이력 수집 중...", "active");
  setDashboardStep("analysis", "Gemini 응답 대기 중...", "active");
  setDashboardStep("result", "응답 대기 중", "pending");
  setDashboardBadge("실행 중", "info");
  elements.checkupReportButton.disabled = true;
  elements.checkupReportButton.textContent = "분석 중...";
  try {
    const response = await fetchWithSession("/me/checkup/report", { method: "POST", headers: { Accept: "application/json" } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(String(payload.detail || "AI 요약분석을 생성하지 못했습니다."));
    const timings = payload.verification?.timings || {};
    setDashboardStep("history", `${payload.checkup_count}회 전체 이력 수집 완료 · ${formatElapsed(timings.history_seconds)}`);
    setDashboardStep("analysis", `Gemini AI 응답 완료 · ${formatElapsed(timings.ai_seconds)}`);
    setDashboardStep("result", `구조화 리포트 수신 완료 · ${formatElapsed(timings.total_seconds)}`);
    const improved = (payload.report.improved || []).length;
    const managed = (payload.report.management_needed || []).length;
    finishDashboardRun("checkup", {
      badge: { text: "완료", tone: "success" },
      metrics: [payload.checkup_count, improved + (payload.report.maintained || []).length + managed, improved, managed],
      log: `전체 ${payload.checkup_count}회 검진 이력을 기반으로 AI 요약분석을 완료했습니다.`,
      verification: payload.verification || {},
    });
    renderCheckupReport(payload.report);
  } catch (error) {
    setDashboardStep("result", "분석 실패", "error");
    failDashboardRun("checkup", error instanceof Error ? error.message : "AI 요약분석을 생성하지 못했습니다.");
    elements.checkupReport.hidden = false;
    elements.checkupReport.textContent = error instanceof Error ? error.message : "AI 요약분석을 생성하지 못했습니다.";
  } finally {
    elements.checkupReportButton.disabled = false;
    elements.checkupReportButton.textContent = "AI 요약분석";
  }
}

// 당일 카드의 미니 그래프에 쓸 점의 개수. 너무 많으면 카드 안에서 뭉개진다.
const _SPARKLINE_MAX_POINTS = 24;
// 누적 막대에 쓰는 계열 색 수. styles.css의 --chart-s0~3과 짝을 맞춘다.
const _CHART_COLOR_COUNT = 4;
// 안내 문구에 늘어놓을 지표 이름 수. 넘치면 '외 N개'로 줄인다.
const _SCOPE_TITLE_LIMIT = 4;

// AI 분석 구간은 서비스가 탭마다 정한다. 화면의 기간 버튼은 그래프에만 적용된다.
// 캐시는 탭당 하나이고, 새 기록이 들어와 기준일이 바뀌면 버린다.
// 실행은 버튼을 눌렀을 때만 일어난다.
const lifestyleReports = new Map();

function setLifestyleStatus(message, isError = false) {
  // 안내 문구가 있을 때만 본문을 감춰 당일 수치·AI 분석·추이 순서를 항상 유지한다.
  elements.lifestyleStatus.textContent = message;
  elements.lifestyleStatus.hidden = !message;
  elements.lifestyleStatus.classList.toggle("data-error", Boolean(isError));
  elements.lifestyleContent.hidden = Boolean(message);
}

function lifestyleTabSeries(payload, tab) {
  const items = lifestyleTabMetricKeys(tab)
    .map((key) => {
      const metric = lifestyleMetrics[key];
      return {
        key,
        ...metric,
        series: metricDailySeries(payload, metric),
        // 카드에 곁들이는 한 줄은 집계값이 아니라 그날 원본 기록에서 뽑는다.
        rowsAt: (date) => ((payload[metric.source] || {}).rows || [])
          .filter((row) => String(row[metric.dateKey] || "").slice(0, 10) === date),
      };
    })
    .filter((item) => item.series.length);

  // 혈압처럼 둘을 같이 읽어야 뜻이 서는 항목은 카드 하나로 합친다.
  const byKey = new Map(items.map((item) => [item.key, item]));
  const merged = new Set();
  return items
    .map((item) => {
      const partners = [].concat(item.pairedWith || [])
        .map((key) => byKey.get(key))
        .filter(Boolean);
      if (!partners.length) return item;
      partners.forEach((partner) => merged.add(partner.key));
      return { ...item, label: item.pairedLabel || item.label, pairs: partners };
    })
    .filter((item) => !merged.has(item.key));
}

function buildSparkline(seriesList, unit) {
  // 점이 하나면 그릴 선이 없고, 너무 많으면 카드 안에서 뭉개진다.
  const plots = seriesList
    .map((series) => series.slice(-_SPARKLINE_MAX_POINTS))
    .filter((points) => points.length >= 2);
  if (!plots.length) return null;
  // 혈압처럼 둘을 겹쳐 그릴 때는 눈금을 같이 써야 두 값의 간격이 보인다.
  const values = plots.flat().map((point) => point.value);
  const low = Math.min(...values);
  const span = Math.max(...values) - low || 1;
  const width = 68;
  const height = 24;
  const svg = svgNode("svg", {
    class: "today-card-spark",
    viewBox: `0 0 ${width} ${height}`,
    "aria-label": `최근 ${plots[0].length}회 흐름`,
  });
  plots.forEach((points, order) => {
    const step = width / (points.length - 1);
    // 위아래로 2px씩 여백을 둬야 꼭짓점이 잘리지 않는다.
    const coords = points.map((point, index) => [
      index * step,
      height - 2 - ((point.value - low) / span) * (height - 4),
    ]);
    svg.appendChild(svgNode("polyline", {
      class: `today-card-spark-line s${order % _CHART_COLOR_COUNT}`,
      points: coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" "),
    }));
    const [lastX, lastY] = coords[coords.length - 1];
    svg.appendChild(svgNode("circle", {
      class: `today-card-spark-dot s${order % _CHART_COLOR_COUNT}`, cx: lastX, cy: lastY, r: 2.2,
    }));
  });
  svg.appendChild(svgNode("title", {}, `최근 ${plots[0].length}회 흐름${unit ? ` (${unit})` : ""}`));
  return svg;
}

function todayCardPoint(series, latestDate) {
  return series.find((point) => point.date === latestDate);
}

// 운동시간(분)과 운동칼로리(kcal)처럼 단위가 갈리는 짝인지. 혈압은 둘 다 mmHg다.
function pairedUnitsDiffer(item) {
  return (item.pairs || []).some((partner) => partner.unit !== item.unit);
}

function todayCardText(item, pick) {
  // 짝지은 항목은 '121/79'처럼 한 칸에 나란히 적는다. 값이 없는 쪽은 —로 둔다.
  // 단위가 갈리면 숫자마다 단위를 붙인다. '35/250'만으로는 어느 쪽이 무엇인지 모른다.
  const withUnit = pairedUnitsDiffer(item);
  const number = (entry) => {
    const value = pick(entry);
    const text = value === null || value === undefined ? "—" : formatDataNumber(value, entry.digits);
    return withUnit ? `${text}${entry.unit}` : text;
  };
  return [item, ...(item.pairs || [])].map(number).join("/");
}

function formatClockTime(value) {
  // 기록은 UTC로 저장된다(예: 새벽 1시 20분이 T16:20:00+00:00). 문자열을 잘라 읽으면
  // 오후 4시 20분으로 보이므로, 시각으로 파싱해 보는 사람의 시간대로 옮겨 적는다.
  const moment = new Date(String(value || ""));
  if (Number.isNaN(moment.getTime())) return "";
  const hour = moment.getHours();
  const minute = String(moment.getMinutes()).padStart(2, "0");
  return `${hour < 12 ? "오전" : "오후"} ${hour % 12 || 12}:${minute}`;
}

function buildTodayMetricCard(item, latestDate, days) {
  const card = document.createElement("article");
  card.className = "today-card";
  card.append(createTextElement("span", "today-card-label", item.label));

  const todayPoint = todayCardPoint(item.series, latestDate);
  const main = document.createElement("div");
  main.className = "today-card-main";
  const value = document.createElement("strong");
  value.className = "today-card-value";
  value.textContent = todayCardText(item, (entry) => todayCardPoint(entry.series, latestDate)?.value);
  // 단위가 갈리는 짝은 숫자마다 단위를 달고 나오므로 뒤에 또 붙이지 않는다.
  if (item.unit && !pairedUnitsDiffer(item)) {
    const unit = document.createElement("small");
    unit.className = "today-card-unit";
    unit.textContent = item.unit;
    value.appendChild(unit);
  }
  main.appendChild(value);
  // 카드 안에서 최근 흐름을 한눈에 보여 준다. 숫자 하나만으로는 방향을 알 수 없다.
  // 단위가 갈리는 짝은 눈금을 같이 쓸 수 없다. 분과 kcal을 한 축에 얹으면
  // 자릿수가 큰 쪽만 보이고 다른 쪽은 바닥에 눌린 직선이 된다. 앞의 것만 그린다.
  const spark = item.spark === false ? null : buildSparkline(
    pairedUnitsDiffer(item) ? [item.series]
      : [item.series, ...(item.pairs || []).map((partner) => partner.series)],
    item.unit,
  );
  if (spark) main.appendChild(spark);
  card.appendChild(main);

  const foot = document.createElement("footer");
  foot.className = "today-card-foot";
  const mean = (entry) => entry.series.reduce((sum, point) => sum + point.value, 0) / entry.series.length;
  const average = mean(item);
  if (!todayPoint) {
    // 항목마다 마지막 기록일이 갈릴 수 있어, 당일 기록이 없으면 언제 값인지 알린다.
    card.classList.add("is-empty");
    const last = item.series[item.series.length - 1];
    foot.appendChild(createTextElement("span", "today-card-average",
      `마지막 기록 ${last.date} · ${todayCardText(item, (entry) => todayCardPoint(entry.series, last.date)?.value)}`));
  } else if (item.series.length < 2) {
    foot.appendChild(createTextElement("span", "today-card-average", `최근 ${days}일 중 1일 기록`));
  } else if (item.pairs) {
    // 짝지은 항목에 화살표를 둘 붙이면 어수선하다. 방향은 위의 미니 그래프가 말한다.
    foot.appendChild(createTextElement("span", "today-card-average",
      `${days}일 평균 ${todayCardText(item, mean)}`));
  } else {
    const gap = todayPoint.value - average;
    // 표기 자릿수로 반올림했을 때 차이가 없으면 화살표 대신 '평균과 비슷'으로 적는다.
    const isFlat = Math.abs(gap) < 10 ** -(item.digits || 0) / 2;
    // 오르는 게 좋은지 나쁜지는 항목마다 다르므로 방향만 알리고 좋고 나쁨은 말하지 않는다.
    const delta = createTextElement(
      "span",
      isFlat ? "today-card-delta flat" : "today-card-delta",
      isFlat ? "평균과 비슷" : `${gap > 0 ? "▲" : "▼"} ${formatDataNumber(Math.abs(gap), item.digits)}`,
    );
    foot.append(delta, createTextElement("span", "today-card-average",
      `${days}일 평균 ${formatDataNumber(average, item.digits)}`));
  }
  if (item.note) {
    const note = item.note(item.rowsAt(latestDate));
    if (note) card.appendChild(createTextElement("span", "today-card-detail", note));
  }
  card.appendChild(foot);
  return card;
}

function renderLifestyleToday(payload, days) {
  const metrics = lifestyleTabSeries(payload, activeLifestyleTab);
  const latestDate = metrics.reduce((latest, item) => {
    const last = item.series[item.series.length - 1].date;
    return last > latest ? last : latest;
  }, "");
  elements.lifestyleTodayDate.textContent = latestDate ? `${latestDate} 기준` : "기록 없음";
  if (!metrics.length) {
    setDataPlaceholder(elements.lifestyleToday, "이 탭에 표시할 기록이 없습니다.");
    return { latestDate, count: 0 };
  }
  elements.lifestyleToday.replaceChildren(
    ...metrics.map((item) => buildTodayMetricCard(item, latestDate, days)),
  );
  return { latestDate, count: metrics.length };
}

function renderLifestyleTrends(payload, days, latestDate) {
  const config = lifestyleTabConfigs[activeLifestyleTab] || { groups: [] };
  const toSeries = (keys) => keys
    .map((key) => {
      const metric = lifestyleMetrics[key];
      return { key, ...metric, points: bucketSeries(metricDailySeries(payload, metric), days) };
    })
    .filter((item) => item.points.length);

  const blocks = (config.groups || []).map((group) => {
    // 항목을 미리 적을 수 없는 그룹(운동 종류)은 기록에서 계열을 직접 만든다.
    const series = group.deriveSeries
      ? group.deriveSeries(payload).map((item) => ({ ...item, points: bucketSeries(item.points, days) }))
          .filter((item) => item.points.length)
      : toSeries(group.metrics);
    // 표는 그래프와 다른 항목을 볼 수 있다. 없으면 그래프와 같은 항목을 쓴다.
    const tableSeries = group.columns ? toSeries(group.columns) : series;
    if (!series.length) return null;
    // 고른 기간보다 기록이 늦게 시작했으면 그 사실을 알리고 직전 한 칸을 비워 둔다.
    const firstBucket = series.map((item) => item.points[0].date).sort()[0];
    const startsLate = Boolean(latestDate) && windowStartBucket(latestDate, days) < firstBucket;
    const gapDate = startsLate ? previousBucket(firstBucket, days) : "";
    const block = document.createElement("section");
    block.className = "data-section";
    const heading = document.createElement("h3");
    heading.textContent = group.title;
    const range = document.createElement("span");
    range.className = "data-section-range";
    range.textContent = `${lifestyleAggregationLabel(days)} · ${series[0].points.length}구간`;
    heading.appendChild(range);
    // 그래프 종류는 그룹이 정하고, 없으면 탭 기본값을 따른다.
    const kind = group.chart || config.chart;
    const chart = kind === "stack"
      ? buildStackedChart(group.title, series, group.axis, days, gapDate)
      : kind === "line"
        ? buildLineChart(group.title, series, days, gapDate)
        : buildLifestyleBarChart(group.title, series[0], series[0].points, days, gapDate);
    block.append(heading);
    if (startsLate) {
      block.append(createTextElement("p", "data-section-note",
        `${withTopicParticle(group.title)} ${formatBucketDate(firstBucket, days)}부터 기록되었습니다.`));
    }
    if (chart) block.append(chart);
    block.append(buildTrendTable(tableSeries, days));
    return block;
  }).filter(Boolean);
  if (!blocks.length) {
    setDataPlaceholder(elements.lifestyleTrends, "선택한 기간에 기록이 없습니다.");
    return;
  }
  elements.lifestyleTrends.replaceChildren(...blocks);
}

function buildReportList(className, items, build) {
  const list = document.createElement("ul");
  list.className = className;
  items.forEach((item) => list.appendChild(build(item)));
  return list;
}

function appendReportSection(nodes, title, className, items, build) {
  if (!items.length) return;
  if (title) nodes.push(createTextElement("h5", "lifestyle-report-subtitle", title));
  nodes.push(buildReportList(className, items, build));
}

function lifestyleAnalysisScopeText(state) {
  // 이 탭이 어떤 지표를 보는지 그래프 그룹 제목에서 그대로 가져온다.
  const groups = (lifestyleTabConfigs[activeLifestyleTab] || {}).groups || [];
  const titles = groups.map((group) => group.title);
  const shown = titles.slice(0, _SCOPE_TITLE_LIMIT).join(" · ");
  const rest = titles.length - _SCOPE_TITLE_LIMIT;
  const metrics = rest > 0 ? `${shown} 외 ${rest}개` : shown;
  // 분석 구간은 서비스가 정하므로 한 번 돌려 보기 전에는 알 수 없다.
  const window = state?.status === "done"
    ? ` · 최근 ${state.recentDays}일과 전체 ${state.windowDays}일`
    : "";
  return metrics ? `${metrics}${window}` : "";
}

function renderLifestyleReport(hasData = true) {
  const state = lifestyleReports.get(activeLifestyleTab);
  elements.lifestyleAnalysisScope.textContent = lifestyleAnalysisScopeText(state);
  const isLoading = state?.status === "loading";
  elements.lifestyleReportButton.disabled = isLoading || !hasData;
  elements.lifestyleReportButton.textContent = isLoading ? "분석 중..." : "AI 요약분석";
  // 건강검진 탭과 같이, 버튼을 누르기 전에는 분석 영역을 열지 않는다.
  if (!state) {
    elements.lifestyleReport.replaceChildren();
    elements.lifestyleReport.hidden = true;
    return;
  }
  elements.lifestyleReport.hidden = false;
  if (isLoading) {
    setDataPlaceholder(elements.lifestyleReport, "AI가 이 탭의 기록을 살펴보고 있어요.");
    return;
  }
  if (state.status === "error") {
    setDataPlaceholder(elements.lifestyleReport, state.message, true);
    return;
  }
  // 사용자에게는 지금 상태와 할 일만 보여 준다.
  // 항목별 수치·판정·이상 지점은 오른쪽 검증 패널에만 남긴다.
  const report = state.report || {};
  const nodes = [
    createTextElement("h4", "", String(report.headline || "")),
    createTextElement("p", "", String(report.current_state || "")),
  ];
  appendReportSection(nodes, "지금 신경 쓰면 좋은 것", "lifestyle-report-actions", report.actions || [],
    (action) => createTextElement("li", "", String(action)));
  nodes.push(createTextElement("small", "lifestyle-report-footnote",
    `최근 ${state.recentDays}일과 전체 ${state.windowDays}일${state.coveredRange ? ` (${state.coveredRange})` : ""} 기록을 함께 보고 생성했습니다.`
    + " 아래 기간 버튼은 그래프에만 적용됩니다."
    + (state.dataTruncated ? " 기록이 많아 오래된 일부는 조회에서 제외됐습니다." : "")
    + " 참고범위는 일반 성인 기준이며 성별·나이·활동량을 반영하지 않습니다."));
  elements.lifestyleReport.replaceChildren(...nodes);
}

function lifestyleTabLabel(tab) {
  const button = elements.lifestyleTabs.find((item) => item.dataset.lifestyleTab === tab);
  return button ? button.textContent.trim() : tab;
}

function renderLifestyleDashboard(tabLabel, payload) {
  const verification = payload.verification || {};
  const timings = verification.timings || {};
  const analyzed = (verification.analysis_input || {}).metrics || [];
  // 판정과 이상 지점은 서비스가 계산해 내려준 값을 그대로 센다. 지표는 전체 구간 기준이다.
  const outOfRange = analyzed.filter((metric) => (metric.full || {}).out_of_range_days > 0).length;
  const anomalies = analyzed.reduce((sum, metric) => sum + (metric.anomalies || []).length, 0);
  const managed = analyzed.filter((metric) =>
    [(metric.full || {}).current_status, metric.latest_status].includes("관리 필요")).length;

  setDashboardStep("latest", `${tabLabel} 전체 ${payload.window_days}일 조회 완료 · ${formatElapsed(timings.window_seconds)}`);
  setDashboardStep("history", `${analyzed.length}개 항목 · 최근 ${payload.recent_days}일 대비 계산 완료 · ${formatElapsed(timings.analysis_seconds)}`);
  setDashboardStep("analysis", `Gemini AI 응답 완료 · ${formatElapsed(timings.ai_seconds)}`);
  setDashboardStep("result", `구조화 리포트 수신 완료 · ${formatElapsed(timings.total_seconds)}`);
  finishDashboardRun("lifestyle", {
    badge: { text: "완료", tone: "success" },
    metrics: [analyzed.length, outOfRange, anomalies, managed],
    log: `${tabLabel} 탭의 ${analyzed.length}개 항목을 전체 ${payload.window_days}일과 최근 ${payload.recent_days}일 두 구간으로 계산하고`
      + ` 프롬프트 v${payload.prompt_version || "?"}로 AI 요약분석을 완료했습니다.`
      + ` 기준일은 ${payload.latest_date || "기록 없음"}, 실제 데이터 범위는 ${payload.covered_range || "없음"}입니다.`
      + (payload.data_truncated ? " 조회 상한에 걸려 오래된 기록 일부가 제외됐습니다." : ""),
    verification,
    sections: [
      ["항목별 계산 근거와 코드 판정", verification.analysis_input || {}],
      ["이상 지점으로 잡힌 날", analyzed.flatMap((metric) =>
        (metric.anomalies || []).map((item) => ({ metric: metric.metric, ...item })))],
      ["함께 움직인 항목", (verification.analysis_input || {}).co_movements || []],
      ["데이터 출처 및 판정 기준", {
        source: verification.source,
        prompt_version: verification.prompt_version,
        reference_basis: (verification.analysis_input || {}).reference_basis,
        judged_by: "서비스 코드가 참고범위와 비교해 계산 (AI 재판정 금지)",
      }],
    ],
  });
}

async function loadLifestyleReport(force = false) {
  const tab = activeLifestyleTab;
  if (!force && lifestyleReports.has(tab)) return;
  lifestyleReports.set(tab, { status: "loading" });
  renderLifestyleReport();
  const tabLabel = lifestyleTabLabel(tab);
  dashboardResults.set("lifestyle", { steps: {}, badge: { text: "실행 중", tone: "info" }, metrics: [], log: "" });
  setDashboardStep("latest", `${tabLabel} 구간 데이터 조회 중...`, "active");
  setDashboardStep("history", "참고범위 판정 대기 중", "pending");
  setDashboardStep("analysis", "Gemini 응답 대기 중...", "active");
  setDashboardStep("result", "응답 대기 중", "pending");
  setDashboardBadge("실행 중", "info");
  try {
    const response = await fetchWithSession(
      `/me/lifestyle/report?domain=${encodeURIComponent(tab)}`,
      { method: "POST", headers: { Accept: "application/json" } },
    );
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      lifestyleReports.delete(tab);
      showLoginScreen("다시 로그인해 주세요.");
      return;
    }
    if (!response.ok) throw new Error(String(payload.detail || "AI 분석을 생성하지 못했습니다."));
    lifestyleReports.set(tab, {
      status: "done",
      report: payload.report,
      latestDate: payload.latest_date || "",
      windowDays: payload.window_days,
      recentDays: payload.recent_days,
      coveredRange: payload.covered_range || "",
      dataTruncated: Boolean(payload.data_truncated),
    });
    renderLifestyleDashboard(tabLabel, payload);
  } catch (error) {
    const message = error instanceof Error ? error.message : "AI 분석을 생성하지 못했습니다.";
    lifestyleReports.set(tab, { status: "error", message });
    setDashboardStep("result", "분석 실패", "error");
    failDashboardRun("lifestyle", message);
  }
  // 응답을 기다리는 사이 다른 탭으로 옮겼다면 그 탭 화면을 덮어쓰지 않는다.
  if (tab === activeLifestyleTab) renderLifestyleReport();
}

function renderLifestyle(payload) {
  const days = Number(payload.window_days) || lifestyleDays;
  // 당일 수치는 원본 기록을 그대로 읽어야 하므로 집계 전 응답을 그대로 보관한다.
  lifestylePayload = payload;
  const today = renderLifestyleToday(payload, days);
  renderLifestyleTrends(payload, days, today.latestDate);
  // 기간 버튼을 눌러도 분석은 그대로지만, 새 기록이 들어왔다면 옛 분석은 버린다.
  const cached = lifestyleReports.get(activeLifestyleTab);
  if (cached?.status === "done" && cached.latestDate && today.latestDate
    && cached.latestDate !== today.latestDate) {
    lifestyleReports.delete(activeLifestyleTab);
  }
  renderLifestyleReport(Boolean(today.count));
  elements.lifestyleMeta.textContent = today.count
    ? `${today.latestDate} 기준 · 최근 ${days}일 · ${today.count}개 항목`
    : "최근 기록 없음";
  setLifestyleStatus("");
}

function setLifestyleTab(tab) {
  activeLifestyleTab = tab;
  elements.lifestyleTabs.forEach((button) => {
    const selected = button.dataset.lifestyleTab === tab;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  if (lifestylePayload) renderLifestyle(lifestylePayload);
}

async function loadPersonalData(tab, { force = false } = {}) {
  if (!force && loadedDataTabs.has(tab)) return;
  const isCheckup = tab === "checkup";
  const meta = isCheckup ? elements.checkupMeta : elements.lifestyleMeta;

  meta.textContent = "불러오는 중...";
  if (isCheckup) setDataPlaceholder(elements.checkupBody, "검진 결과를 불러오고 있어요.");
  else setLifestyleStatus("생활 데이터를 불러오고 있어요.");
  elements.dataReloadButton.disabled = true;
  try {
    if (isCheckup && (!checkupRecords.length || force)) {
      if (!(await loadCheckupRecords())) return;
    }
    const resource = isCheckup
      ? `/me/checkup${selectedCheckupRecordId ? `?record_id=${encodeURIComponent(selectedCheckupRecordId)}` : ""}`
      : `/me/lifestyle?window_days=${lifestyleDays}`;
    const response = await fetchWithSession(resource, {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      showLoginScreen("다시 로그인해 주세요.");
      return;
    }
    if (!response.ok) {
      throw new Error(String(payload.detail || "개인 데이터를 불러오지 못했습니다."));
    }
    if (isCheckup) renderCheckup(payload);
    else renderLifestyle(payload);
    loadedDataTabs.add(tab);
  } catch (error) {
    meta.textContent = "불러오기 실패";
    const message = error instanceof Error ? error.message : "개인 데이터를 불러오지 못했습니다.";
    if (isCheckup) setDataPlaceholder(elements.checkupBody, message, true);
    else setLifestyleStatus(message, true);
  } finally {
    elements.dataReloadButton.disabled = false;
  }
}

function setDataTab(tab) {
  activeDataTab = tab;
  const isCheckup = tab === "checkup";
  elements.checkupTab.classList.toggle("active", isCheckup);
  elements.lifestyleTab.classList.toggle("active", !isCheckup);
  elements.checkupTab.setAttribute("aria-selected", String(isCheckup));
  elements.lifestyleTab.setAttribute("aria-selected", String(!isCheckup));
  elements.checkupPanel.hidden = !isCheckup;
  elements.lifestylePanel.hidden = isCheckup;
  applyDashboardPreset(tab);
  updatePersonalEnvironment();
  loadPersonalData(tab);
}

function updatePersonalEnvironment() {
  const showPersonal = activeView === "data";
  elements.personalEnvironment.hidden = !showPersonal || activeDataTab !== "checkup";
  elements.lifestyleEnvironment.hidden = !showPersonal || activeDataTab !== "lifestyle";
}

function setActiveView(view) {
  activeView = view;
  const isChat = view === "chat";
  elements.chatViewTab.classList.toggle("active", isChat);
  elements.dataViewTab.classList.toggle("active", !isChat);
  elements.chatViewTab.setAttribute("aria-selected", String(isChat));
  elements.dataViewTab.setAttribute("aria-selected", String(!isChat));
  elements.conversation.hidden = !isChat;
  elements.composerWrap.hidden = !isChat;
  elements.dataView.hidden = isChat;
  // '새 대화'는 챗 화면 전용 동작이다.
  elements.resetButton.hidden = !isChat;
  elements.chatInsightPanel.hidden = !isChat;
  elements.dashboardInsightPanel.hidden = isChat;
  elements.projectEnvironmentContent.hidden = !isChat;
  elements.projectEnvironmentHeader.hidden = !isChat;
  updatePersonalEnvironment();
  elements.conversationHistory.hidden = !isChat;
  if (isChat) elements.input.focus();
  // 패널 복원은 setDataTab의 applyDashboardPreset이 맡는다.
  else setDataTab(activeDataTab);
}

function resetPersonalData() {
  loadedDataTabs.clear();
  resetCheckupRecords();
  activeDataTab = "checkup";
  elements.checkupMeta.textContent = "—";
  elements.lifestyleMeta.textContent = "—";
  dashboardResults.clear();
  resetDashboardFlow();
  lifestylePayload = null;
  lifestyleReports.clear();
  lifestyleDays = LIFESTYLE_DEFAULT_DAYS;
  elements.lifestylePeriods.forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.lifestyleDays) === lifestyleDays);
  });
  setDataPlaceholder(elements.checkupBody, "검진 결과를 불러오고 있어요.");
  setLifestyleStatus("생활 데이터를 불러오고 있어요.");
  setActiveView("chat");
}

function resetConversation() {
  if (isRequesting) return;
  elements.messages.replaceChildren();
  elements.messages.hidden = true;
  elements.welcome.hidden = false;
  elements.emptyInsight.hidden = false;
  elements.auditCardList.replaceChildren();
  elements.auditCountBadge.className = "quality-badge neutral";
  elements.auditCountBadge.textContent = "0건";
  conversationHistory = [];
  conversationSummary = "";
  currentSessionId = "";
  renderSuggestionCards();
  elements.input.value = "";
  resizeInput();
  elements.input.focus();
}

elements.input.addEventListener("input", resizeInput);
elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.form.requestSubmit();
  }
});
elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitQuestion(elements.input.value);
});
elements.resetButton.addEventListener("click", resetConversation);
elements.newConversationButton.addEventListener("click", () => {
  setActiveView("chat");
  resetConversation();
});
elements.chatViewTab.addEventListener("click", () => setActiveView("chat"));
elements.dataViewTab.addEventListener("click", () => setActiveView("data"));
elements.checkupTab.addEventListener("click", () => setDataTab("checkup"));
elements.lifestyleTab.addEventListener("click", () => setDataTab("lifestyle"));
elements.lifestyleTabs.forEach((button) => {
  button.addEventListener("click", () => setLifestyleTab(button.dataset.lifestyleTab));
});
elements.lifestylePeriods.forEach((button) => {
  button.addEventListener("click", () => {
    lifestyleDays = Number(button.dataset.lifestyleDays);
    elements.lifestylePeriods.forEach((periodButton) => periodButton.classList.toggle("active", periodButton === button));
    loadedDataTabs.delete("lifestyle");
    loadPersonalData("lifestyle", { force: true });
  });
});
elements.dataReloadButton.addEventListener("click", () => {
  // 다시 불러오기는 AI 분석까지 새로 받는다.
  if (activeDataTab === "lifestyle") lifestyleReports.clear();
  loadPersonalData(activeDataTab, { force: true });
});
elements.lifestyleReportButton.addEventListener("click", () => loadLifestyleReport(true));
elements.checkupReportButton.addEventListener("click", loadCheckupReport);
elements.checkupRecordSelect.addEventListener("change", () => {
  selectedCheckupRecordId = elements.checkupRecordSelect.value;
  loadPersonalData("checkup", { force: true });
});
elements.loginForm.addEventListener("submit", login);
elements.loginModeButton.addEventListener("click", () => setAuthMode("login"));
elements.signupModeButton.addEventListener("click", () => setAuthMode("signup"));
elements.logoutButton.addEventListener("click", logout);
document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => submitQuestion(button.dataset.question || ""));
});

renderSuggestionCards();
resizeInput();
loadProjectEnvironment();
restoreSession();
