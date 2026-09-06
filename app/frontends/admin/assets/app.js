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
let lifestyleDays = 365;
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
  systolic: { label: "수축기 혈압", unit: "mmHg", digits: 0, ...bioMetric("blood_pressure", (row) => row.detail_data?.systolic) },
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

  intakeCalories: { label: "섭취칼로리", unit: "kcal", digits: 0, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.calories },
  carbohydrate: { label: "탄수화물", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.carbohydrate },
  protein: { label: "단백질", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.protein },
  totalFat: { label: "지방", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.total_fat },
  sodium: { label: "나트륨", unit: "mg", digits: 0, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.sodium },
  sugar: { label: "당", unit: "g", digits: 1, source: "food", dateKey: "consumed_at", daily: "sum", value: (row) => row.sugar },
  water: { label: "수분 섭취", unit: "mL", digits: 0, source: "water", dateKey: "consumed_at", daily: "sum", value: (row) => row.water_amount },

  sleepHours: { label: "수면시간", unit: "시간", digits: 1, source: "sleep", dateKey: "measured_at", daily: "sum", value: (row) => row.value },
  sleepScore: { label: "수면점수", unit: "점", digits: 0, source: "sleep", dateKey: "measured_at", daily: "mean", value: (row) => row.detail_data?.sleep_score },
  deepSleep: { label: "깊은수면", unit: "분", digits: 0, source: "sleep", dateKey: "measured_at", daily: "sum", value: (row) => row.detail_data?.deep_sleep_min },
  awake: { label: "깬 시간", unit: "분", digits: 0, source: "sleep", dateKey: "measured_at", daily: "sum", value: (row) => row.detail_data?.awake_min },
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
    groups: [
      { title: "걸음 수", metrics: ["steps"] },
      { title: "계단", metrics: ["floors"] },
      { title: "활동시간", metrics: ["activeTime"] },
      { title: "이동거리", metrics: ["activeDistance"] },
      { title: "활동칼로리", metrics: ["activeCalories"] },
      { title: "운동시간", metrics: ["exerciseTime"] },
      { title: "운동거리", metrics: ["exerciseDistance"] },
      { title: "운동칼로리", metrics: ["exerciseCalories"] },
    ],
  },
  nutrition: {
    chart: "bar",
    groups: [
      { title: "섭취칼로리", metrics: ["intakeCalories"] },
      { title: "탄수화물", metrics: ["carbohydrate"] },
      { title: "단백질", metrics: ["protein"] },
      { title: "지방", metrics: ["totalFat"] },
      { title: "나트륨", metrics: ["sodium"] },
      { title: "당", metrics: ["sugar"] },
      { title: "수분 섭취", metrics: ["water"] },
    ],
  },
  sleep: {
    chart: "line",
    groups: [
      { title: "수면시간", metrics: ["sleepHours"] },
      { title: "수면점수", metrics: ["sleepScore"] },
      { title: "깊은수면과 깬 시간", metrics: ["deepSleep", "awake"] },
    ],
  },
};

// 당일 카드는 그래프 그룹에 쓰인 항목을 같은 순서로 보여준다.
function lifestyleTabMetricKeys(tab) {
  return (lifestyleTabConfigs[tab]?.groups || []).flatMap((group) => group.metrics);
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

function buildLifestyleBarChart(title, metric, points) {
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
    guide.style.bottom = `${22 + (tick / max) * 128}px`;
    bars.appendChild(guide);
  });
  points.forEach((point) => {
    const item = document.createElement("div");
    item.className = "data-chart-item";
    const bar = document.createElement("span");
    bar.className = "data-chart-bar";
    bar.style.height = `${Math.max((point.value / max) * 100, 8)}%`;
    bar.title = `${formatGraphDate(point.date)}: ${formatDataNumber(point.value, metric.digits)}${metric.unit ? ` ${metric.unit}` : ""}`;
    const label = document.createElement("small");
    label.textContent = formatGraphDate(point.date);
    item.append(bar, label);
    bars.appendChild(item);
  });
  plot.append(axis, bars);
  chart.append(heading, plot);
  return chart;
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
    { label: lifestyleBucketLabel(days), value: (row) => row.date },
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

function buildLineChart(title, series) {
  const colors = ["#2f8f6b", "#e3924d", "#5e83c5", "#bd6c9b"];
  const plots = series.map((item) => item.points
    .map((point) => ({ x: String(point.date || ""), value: Number(point.value) }))
    .filter((point) => point.x && Number.isFinite(point.value))
    .sort((left, right) => left.x.localeCompare(right.x)));
  // 시리즈마다 x를 새로 매기면 선이 옆으로 나열되므로 측정 시점을 공통 축으로 삼아 겹쳐 그린다.
  const axis = [...new Set(plots.flat().map((point) => point.x))].sort();
  if (!axis.length) return null;
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
    }, formatGraphDate(axis[index])));
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

// AI 분석은 화면에서 고른 기간을 그대로 분석한다. 구간이 다르면 결론도 달라지므로
// 탭과 기간을 함께 캐시 키로 쓴다. 실행은 버튼을 눌렀을 때만 일어난다.
const lifestyleReports = new Map();

function lifestyleReportKey(tab = activeLifestyleTab, days = lifestyleDays) {
  return `${tab}|${days}`;
}

function formatReportNumber(value) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return formatDataNumber(number, Number.isInteger(number) ? 0 : 1);
}

function setLifestyleStatus(message, isError = false) {
  // 안내 문구가 있을 때만 본문을 감춰 당일 수치·AI 분석·추이 순서를 항상 유지한다.
  elements.lifestyleStatus.textContent = message;
  elements.lifestyleStatus.hidden = !message;
  elements.lifestyleStatus.classList.toggle("data-error", Boolean(isError));
  elements.lifestyleContent.hidden = Boolean(message);
}

function lifestyleTabSeries(payload, tab) {
  return lifestyleTabMetricKeys(tab)
    .map((key) => {
      const metric = lifestyleMetrics[key];
      return { key, ...metric, series: metricDailySeries(payload, metric) };
    })
    .filter((item) => item.series.length);
}

function buildTodayMetricCard(item, latestDate, days) {
  const card = document.createElement("article");
  card.className = "today-card";

  const head = document.createElement("header");
  head.className = "today-card-head";
  const label = document.createElement("span");
  label.className = "today-card-label";
  label.textContent = item.label;
  head.appendChild(label);
  if (item.unit) {
    const unit = document.createElement("span");
    unit.className = "today-card-unit";
    unit.textContent = item.unit;
    head.appendChild(unit);
  }

  const todayPoint = item.series.find((point) => point.date === latestDate);
  const value = document.createElement("strong");
  value.className = "today-card-value";
  value.textContent = todayPoint ? formatDataNumber(todayPoint.value, item.digits) : "—";

  const foot = document.createElement("footer");
  foot.className = "today-card-foot";
  const average = item.series.reduce((sum, point) => sum + point.value, 0) / item.series.length;
  const last = item.series[item.series.length - 1];
  if (!todayPoint) {
    // 항목마다 마지막 기록일이 갈릴 수 있어, 당일 기록이 없으면 언제 값인지 알린다.
    card.classList.add("is-empty");
    foot.appendChild(createTextElement("span", "today-card-average",
      `마지막 기록 ${last.date} · ${formatDataNumber(last.value, item.digits)}`));
  } else if (item.series.length < 2) {
    foot.appendChild(createTextElement("span", "today-card-average", `최근 ${days}일 중 1일 기록`));
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

  card.append(head, value, foot);
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

function renderLifestyleTrends(payload, days) {
  const config = lifestyleTabConfigs[activeLifestyleTab] || { groups: [] };
  const blocks = (config.groups || []).map((group) => {
    const series = group.metrics
      .map((key) => {
        const metric = lifestyleMetrics[key];
        return { key, ...metric, points: bucketSeries(metricDailySeries(payload, metric), days) };
      })
      .filter((item) => item.points.length);
    if (!series.length) return null;
    const block = document.createElement("section");
    block.className = "data-section";
    const heading = document.createElement("h3");
    heading.textContent = group.title;
    const range = document.createElement("span");
    range.className = "data-section-range";
    range.textContent = `${lifestyleAggregationLabel(days)} · ${series[0].points.length}구간`;
    heading.appendChild(range);
    const chart = config.chart === "line"
      ? buildLineChart(group.title, series)
      : buildLifestyleBarChart(group.title, series[0], series[0].points);
    block.append(heading);
    if (chart) block.append(chart);
    block.append(buildTrendTable(series, days));
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

function buildReportMetricItem(metric) {
  const item = document.createElement("li");
  const head = document.createElement("div");
  head.className = "lifestyle-report-metric-head";
  head.appendChild(createTextElement("strong", "",
    metric.unit ? `${metric.metric} (${metric.unit})` : String(metric.metric || "")));
  // 판정은 서비스가 참고범위와 비교해 계산한 값을 그대로 보여준다.
  if (metric.status) head.appendChild(createStatusChip(metric.status));
  if (metric.trend) {
    const change = metric.change === null || metric.change === undefined
      ? ""
      : ` ${metric.change > 0 ? "+" : ""}${formatReportNumber(metric.change)}`;
    head.appendChild(createTextElement("span", "lifestyle-trend-chip", `${metric.trend}${change}`));
  }
  if (metric.reference) {
    head.appendChild(createTextElement("span", "lifestyle-report-reference", `참고 ${metric.reference}`));
  }
  item.appendChild(head);

  // 과거 구간과 현재 구간을 나란히 놓아 '그때는 어땠고 지금은 어떤지'가 한눈에 보이게 한다.
  if (metric.previous !== null && metric.previous !== undefined
    && metric.current !== null && metric.current !== undefined) {
    const shift = document.createElement("div");
    shift.className = "lifestyle-report-shift";
    shift.append(
      createTextElement("span", "", `전반 ${formatReportNumber(metric.previous)}`),
      ...(metric.previous_status ? [createStatusChip(metric.previous_status)] : []),
      createTextElement("span", "lifestyle-report-arrow", "→"),
      createTextElement("span", "", `후반 ${formatReportNumber(metric.current)}`),
      ...(metric.status ? [createStatusChip(metric.status)] : []),
    );
    item.appendChild(shift);
  }

  item.appendChild(createTextElement("span", "lifestyle-report-description", String(metric.description || "")));
  return item;
}

function buildReportAnomalyItem(anomaly) {
  const item = document.createElement("li");
  const head = document.createElement("div");
  head.className = "lifestyle-report-metric-head";
  head.appendChild(createTextElement("span", "lifestyle-anomaly-date", formatGraphDate(anomaly.date)));
  head.appendChild(createTextElement("strong", "",
    `${anomaly.metric} ${formatReportNumber(anomaly.value)}${anomaly.unit ? ` ${anomaly.unit}` : ""}`));
  if (anomaly.status) head.appendChild(createStatusChip(anomaly.status));
  item.append(head, createTextElement("span", "lifestyle-report-description", String(anomaly.description || "")));
  return item;
}

function appendReportSection(nodes, title, className, items, build) {
  if (!items.length) return;
  nodes.push(createTextElement("h5", "lifestyle-report-subtitle", title));
  nodes.push(buildReportList(className, items, build));
}

function renderLifestyleReport(hasData = true) {
  const state = lifestyleReports.get(lifestyleReportKey());
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
    setDataPlaceholder(elements.lifestyleReport, "AI가 항목별 특성에 맞춰 분석하고 있어요.");
    return;
  }
  if (state.status === "error") {
    setDataPlaceholder(elements.lifestyleReport, state.message, true);
    return;
  }
  const report = state.report || {};
  const nodes = [
    createTextElement("h4", "", String(report.headline || "")),
    createTextElement("p", "", String(report.summary || "")),
  ];
  appendReportSection(nodes, "항목별 변화", "lifestyle-report-metrics", report.metrics || [], buildReportMetricItem);
  appendReportSection(nodes, "발견된 패턴", "lifestyle-report-patterns", report.patterns || [],
    (pattern) => createTextElement("li", "", String(pattern)));
  appendReportSection(nodes, "눈에 띈 날", "lifestyle-report-anomalies", report.anomalies || [], buildReportAnomalyItem);
  nodes.push(createTextElement("p", "", String(report.overall_analysis || "")));
  appendReportSection(nodes, "관리 제안", "lifestyle-report-recommendations", report.recommendations || [],
    (recommendation) => createTextElement("li", "", String(recommendation)));
  nodes.push(createTextElement("small", "lifestyle-report-footnote",
    `${state.latestDate ? `${state.latestDate} 당일 수치와 ` : ""}최근 ${state.windowDays}일 기록을 근거로 생성했습니다.`
    + " 참고범위는 일반 성인 기준이며 성별·나이·활동량을 반영하지 않습니다."));
  elements.lifestyleReport.replaceChildren(...nodes);
}

function lifestyleTabLabel(tab) {
  const button = elements.lifestyleTabs.find((item) => item.dataset.lifestyleTab === tab);
  return button ? button.textContent.trim() : tab;
}

function renderLifestyleDashboard(tabLabel, days, payload) {
  const verification = payload.verification || {};
  const timings = verification.timings || {};
  const analyzed = (verification.analysis_input || {}).metrics || [];
  // 판정과 이상 지점은 서비스가 계산해 내려준 값을 그대로 센다.
  const outOfRange = analyzed.filter((metric) => metric.out_of_range_days > 0).length;
  const anomalies = analyzed.reduce((sum, metric) => sum + (metric.anomalies || []).length, 0);
  const managed = analyzed.filter((metric) =>
    [metric.current_status, metric.latest_status].includes("관리 필요")).length;

  setDashboardStep("latest", `${tabLabel} 최근 ${days}일 조회 완료 · ${formatElapsed(timings.window_seconds)}`);
  setDashboardStep("history", `${analyzed.length}개 항목 지표·판정 계산 완료 · ${formatElapsed(timings.analysis_seconds)}`);
  setDashboardStep("analysis", `Gemini AI 응답 완료 · ${formatElapsed(timings.ai_seconds)}`);
  setDashboardStep("result", `구조화 리포트 수신 완료 · ${formatElapsed(timings.total_seconds)}`);
  finishDashboardRun("lifestyle", {
    badge: { text: "완료", tone: "success" },
    metrics: [analyzed.length, outOfRange, anomalies, managed],
    log: `${tabLabel} 탭의 최근 ${payload.window_days || days}일 기록에서 ${analyzed.length}개 항목을 계산하고 AI 요약분석을 완료했습니다.`
      + ` 기준일은 ${payload.latest_date || "기록 없음"}입니다.`,
    verification,
    sections: [
      ["항목별 계산 근거와 코드 판정", verification.analysis_input || {}],
      ["이상 지점으로 잡힌 날", analyzed.flatMap((metric) =>
        (metric.anomalies || []).map((item) => ({ metric: metric.metric, ...item })))],
      ["데이터 출처 및 판정 기준", {
        source: verification.source,
        reference_basis: (verification.analysis_input || {}).reference_basis,
        judged_by: "서비스 코드가 참고범위와 비교해 계산 (AI 재판정 금지)",
      }],
    ],
  });
}

async function loadLifestyleReport(force = false) {
  const tab = activeLifestyleTab;
  const days = lifestyleDays;
  const key = lifestyleReportKey(tab, days);
  if (!force && lifestyleReports.has(key)) return;
  lifestyleReports.set(key, { status: "loading" });
  renderLifestyleReport();
  const tabLabel = lifestyleTabLabel(tab);
  dashboardResults.set("lifestyle", { steps: {}, badge: { text: "실행 중", tone: "info" }, metrics: [], log: "" });
  setDashboardStep("latest", `${tabLabel} 최근 ${days}일 조회 중...`, "active");
  setDashboardStep("history", "참고범위 판정 대기 중", "pending");
  setDashboardStep("analysis", "Gemini 응답 대기 중...", "active");
  setDashboardStep("result", "응답 대기 중", "pending");
  setDashboardBadge("실행 중", "info");
  try {
    const response = await fetchWithSession(
      `/me/lifestyle/report?domain=${encodeURIComponent(tab)}&window_days=${days}`,
      { method: "POST", headers: { Accept: "application/json" } },
    );
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      lifestyleReports.delete(key);
      showLoginScreen("다시 로그인해 주세요.");
      return;
    }
    if (!response.ok) throw new Error(String(payload.detail || "AI 분석을 생성하지 못했습니다."));
    lifestyleReports.set(key, {
      status: "done",
      report: payload.report,
      latestDate: payload.latest_date || "",
      windowDays: payload.window_days || days,
    });
    renderLifestyleDashboard(tabLabel, days, payload);
  } catch (error) {
    const message = error instanceof Error ? error.message : "AI 분석을 생성하지 못했습니다.";
    lifestyleReports.set(key, { status: "error", message });
    setDashboardStep("result", "분석 실패", "error");
    failDashboardRun("lifestyle", message);
  }
  // 응답을 기다리는 사이 탭이나 기간을 바꿨다면 그 화면을 덮어쓰지 않는다.
  if (key === lifestyleReportKey()) renderLifestyleReport();
}

function renderLifestyle(payload) {
  const days = Number(payload.window_days) || lifestyleDays;
  // 당일 수치는 원본 기록을 그대로 읽어야 하므로 집계 전 응답을 그대로 보관한다.
  lifestylePayload = payload;
  const today = renderLifestyleToday(payload, days);
  renderLifestyleTrends(payload, days);
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
