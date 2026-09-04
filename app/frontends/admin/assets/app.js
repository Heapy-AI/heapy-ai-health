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
  dashboardLatestStatus: document.querySelector("#dashboardLatestStatus"),
  dashboardHistoryStatus: document.querySelector("#dashboardHistoryStatus"),
  dashboardAnalysisStatus: document.querySelector("#dashboardAnalysisStatus"),
  dashboardResultStatus: document.querySelector("#dashboardResultStatus"),
  dashboardCheckupCount: document.querySelector("#dashboardCheckupCount"),
  dashboardMetricCount: document.querySelector("#dashboardMetricCount"),
  dashboardImprovedCount: document.querySelector("#dashboardImprovedCount"),
  dashboardManagementCount: document.querySelector("#dashboardManagementCount"),
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
const bioTypeLabels = {
  weight: "체중",
  bmi: "BMI",
  blood_pressure: "혈압",
  blood_glucose: "혈당",
  heart_rate: "심박수",
  sleep: "수면시간",
};
const exerciseTypeLabels = { walking: "걷기", running: "달리기", indoor_cycling: "실내 자전거" };
const mealTypeLabels = { breakfast: "아침", lunch: "점심", dinner: "저녁", snack: "간식" };
const bioUnitLabels = { hour: "시간" };

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
  if (text.startsWith("정상")) return "normal";
  if (text.includes("경계") || text.includes("주의")) return "caution";
  if (text.includes("의심") || text.includes("이상") || text.includes("위험")) return "danger";
  return "neutral";
}

function createStatusChip(status) {
  const chip = document.createElement("span");
  chip.className = `status-chip ${statusChipClass(status)}`;
  chip.textContent = String(status || "미분류");
  return chip;
}

function bioValueText(row) {
  const detail = row.detail_data && typeof row.detail_data === "object" ? row.detail_data : {};
  const rawUnit = String(row.unit || "");
  const unit = bioUnitLabels[rawUnit] || rawUnit;
  // 혈압은 value에 수축기만 담기므로 이완기까지 함께 표기한다.
  if (
    row.bio_type === "blood_pressure"
    && detail.systolic !== null && detail.systolic !== undefined
    && detail.diastolic !== null && detail.diastolic !== undefined
  ) {
    return `${detail.systolic}/${detail.diastolic}${unit ? ` ${unit}` : ""}`;
  }
  const value = formatDataNumber(row.value, 1);
  return unit && value !== "—" ? `${value} ${unit}` : value;
}

function bioDetailText(row) {
  const detail = row.detail_data && typeof row.detail_data === "object" ? row.detail_data : {};
  const parts = [];
  if (row.bio_type === "blood_pressure" && detail.pulse !== null && detail.pulse !== undefined) {
    parts.push(`맥박 ${detail.pulse}bpm`);
  }
  if (row.bio_type === "blood_glucose" && "fasting" in detail) {
    parts.push(detail.fasting ? "공복" : "식후");
  }
  if (row.bio_type === "sleep") {
    if (detail.sleep_score !== null && detail.sleep_score !== undefined) parts.push(`수면점수 ${detail.sleep_score}`);
    if (detail.deep_sleep_min !== null && detail.deep_sleep_min !== undefined) parts.push(`깊은수면 ${detail.deep_sleep_min}분`);
    if (detail.awake_min !== null && detail.awake_min !== undefined) parts.push(`깬시간 ${detail.awake_min}분`);
  }
  return parts.join(" · ") || "—";
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

const lifestyleSections = [
  {
    key: "activity",
    title: "일별 활동량",
    columns: [
      { label: "날짜", value: (row) => formatDataDate(row.record_date) },
      { label: "걸음", numeric: true, value: (row) => formatDataNumber(row.steps) },
      { label: "계단", numeric: true, value: (row) => formatDataNumber(row.floors_climbed) },
      { label: "활동시간(분)", numeric: true, value: (row) => formatDataNumber(row.active_time) },
      // lifestyle_activity.active_distance는 km 단위로 적재된다.
      { label: "이동(km)", numeric: true, value: (row) => formatDataNumber(row.active_distance, 1) },
      { label: "활동칼로리", numeric: true, value: (row) => formatDataNumber(row.active_calories) },
    ],
  },
  {
    key: "exercise",
    title: "운동 기록",
    columns: [
      { label: "날짜", value: (row) => formatDataDate(row.record_date) },
      {
        label: "종목",
        value: (row) => {
          const raw = String(row.exercise_type || "");
          return exerciseTypeLabels[raw] || raw || "종목 미상";
        },
      },
      {
        label: "시간(분)",
        numeric: true,
        value: (row) => formatDataNumber(row.duration_sec === null || row.duration_sec === undefined ? null : Number(row.duration_sec) / 60),
      },
      // lifestyle_exercise.distance_m은 미터 단위이므로 km로 환산한다.
      {
        label: "거리(km)",
        numeric: true,
        value: (row) => formatDataNumber(row.distance_m === null || row.distance_m === undefined ? null : Number(row.distance_m) / 1000, 1),
      },
      { label: "칼로리", numeric: true, value: (row) => formatDataNumber(row.calories) },
    ],
  },
  {
    key: "bio",
    title: "신체·수면 지표",
    columns: [
      { label: "측정", value: (row) => formatDataDate(row.measured_at) },
      { label: "값", numeric: true, value: bioValueText },
      { label: "참고", value: bioDetailText },
    ],
  },
  {
    key: "food",
    title: "식사 기록",
    columns: [
      { label: "일시", value: (row) => formatDataDate(row.consumed_at) },
      {
        label: "구분",
        value: (row) => {
          const raw = String(row.meal_type || "");
          return mealTypeLabels[raw] || raw || "—";
        },
      },
      { label: "메뉴", value: (row) => String(row.title || "—") },
      { label: "칼로리", numeric: true, value: (row) => formatDataNumber(row.calories) },
      { label: "탄수(g)", numeric: true, value: (row) => formatDataNumber(row.carbohydrate, 1) },
      { label: "단백(g)", numeric: true, value: (row) => formatDataNumber(row.protein, 1) },
      { label: "지방(g)", numeric: true, value: (row) => formatDataNumber(row.total_fat, 1) },
      { label: "나트륨(mg)", numeric: true, value: (row) => formatDataNumber(row.sodium) },
      { label: "당(g)", numeric: true, value: (row) => formatDataNumber(row.sugar, 1) },
    ],
  },
  {
    key: "water",
    title: "수분 섭취",
    columns: [
      { label: "일시", value: (row) => formatDataDate(row.consumed_at) },
      { label: "섭취량(mL)", numeric: true, value: (row) => formatDataNumber(row.water_amount) },
    ],
  },
];

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

function buildLifestyleSection(spec, domain) {
  const rows = (domain && domain.rows) || [];
  if (!rows.length) return null;
  const section = document.createElement("section");
  section.className = "data-section";

  const heading = document.createElement("h3");
  heading.textContent = spec.title;
  const range = document.createElement("span");
  range.className = "data-section-range";
  range.textContent = domain.since && domain.until
    ? `${domain.since} ~ ${domain.until} · ${rows.length}건`
    : `${rows.length}건`;
  heading.appendChild(range);

  section.append(heading, buildDataTable(spec.columns, rows));
  return section;
}

function buildLifestyleChart(spec, domain) {
  const rows = (domain && domain.rows) || [];
  const metric = spec.chartMetric;
  const dateKey = spec.dateKey || (spec.key === "bio" ? "measured_at" : "record_date");
  const points = rows
    .map((row) => ({
      label: formatGraphDate(row[dateKey]),
      value: Number(row[metric.key]),
    }))
    .filter((point) => Number.isFinite(point.value))
    .reverse();
  if (!points.length) return null;

  const maxValue = Math.max(...points.map((point) => point.value), 1);
  const isSteps = metric.key === "steps";
  const max = isSteps ? Math.max(9000, Math.ceil(maxValue / 1000) * 1000) : maxValue;
  const ticks = isSteps
    ? [0, 3000, 6000, 9000].filter((tick) => tick <= max)
    : [0, max / 2, max];
  const chart = document.createElement("div");
  chart.className = "data-chart";
  const title = document.createElement("div");
  title.className = "data-chart-title";
  title.textContent = `${spec.title} · ${metric.label}`;
  const plot = document.createElement("div");
  plot.className = "data-chart-plot";
  const axis = document.createElement("div");
  axis.className = "data-chart-axis";
  ticks.slice().reverse().forEach((tick) => {
    const label = document.createElement("span");
    label.textContent = formatDataNumber(tick);
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
    bar.title = `${point.label}: ${formatDataNumber(point.value, metric.digits || 0)}${metric.unit ? ` ${metric.unit}` : ""}`;
    const label = document.createElement("small");
    label.textContent = point.label;
    item.append(bar, label);
    bars.appendChild(item);
  });
  plot.append(axis, bars);
  chart.append(title, plot);
  return chart;
}

function lifestyleBucket(value, days) {
  const text = String(value || "").slice(0, 10);
  if (!text) return "";
  if (days >= 180) return text.slice(0, 7);
  if (days >= 90) {
    const current = new Date(`${text}T00:00:00`);
    const day = current.getDay() || 7;
    current.setDate(current.getDate() - day + 1);
    return current.toISOString().slice(0, 10);
  }
  return text;
}

function averageValues(rows, fields) {
  const result = {};
  fields.forEach((field) => {
    const values = rows.map((row) => Number(row[field])).filter(Number.isFinite);
    if (values.length) result[field] = values.reduce((sum, value) => sum + value, 0) / values.length;
  });
  return result;
}

function averageBioRows(rows, days) {
  const groups = new Map();
  rows.forEach((row) => {
    const fasting = row.detail_data?.fasting;
    const category = row.bio_type === "blood_glucose" ? String(fasting) : "";
    const key = `${lifestyleBucket(row.measured_at, days)}|${row.bio_type}|${category}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  });
  return [...groups.values()].map((group) => {
    const first = group[0];
    const detailKeys = new Set(group.flatMap((row) => Object.keys(row.detail_data || {})));
    const details = {};
    detailKeys.forEach((key) => {
      const values = group.map((row) => Number(row.detail_data?.[key])).filter(Number.isFinite);
      if (values.length) details[key] = values.reduce((sum, value) => sum + value, 0) / values.length;
      else details[key] = rowValue(group, key);
    });
    return {
      ...first,
      measured_at: lifestyleBucket(first.measured_at, days),
      value: averageValues(group, ["value"]).value ?? first.value,
      detail_data: details,
    };
  });
}

function rowValue(rows, key) {
  return rows.find((row) => row.detail_data?.[key] !== undefined)?.detail_data?.[key];
}

function averageLifestyleRows(rows, dateKey, days, fields) {
  const groups = new Map();
  rows.forEach((row) => {
    const bucket = lifestyleBucket(row[dateKey], days);
    if (!groups.has(bucket)) groups.set(bucket, []);
    groups.get(bucket).push(row);
  });
  return [...groups.entries()].map(([bucket, group]) => ({
    ...group[0],
    [dateKey]: bucket,
    ...averageValues(group, fields),
    ...(dateKey === "record_date" && group.length > 1 ? { exercise_type: "기간 평균" } : {}),
  }));
}

function aggregateLifestylePayload(payload, days) {
  const result = { ...payload, window_days: days };
  result.activity = {
    ...payload.activity,
    rows: averageLifestyleRows(payload.activity?.rows || [], "record_date", days, ["steps", "floors_climbed", "active_time", "active_distance", "active_calories"]),
  };
  result.exercise = {
    ...payload.exercise,
    rows: averageLifestyleRows(payload.exercise?.rows || [], "record_date", days, ["duration_sec", "distance_m", "calories"]),
  };
  result.bio = { ...payload.bio, rows: averageBioRows(payload.bio?.rows || [], days) };
  result.sleep = {
    ...payload.sleep,
    rows: averageBioRows(payload.sleep?.rows || [], days),
  };
  result.food = {
    ...payload.food,
    rows: averageLifestyleRows(payload.food?.rows || [], "consumed_at", days, ["calories", "carbohydrate", "protein", "total_fat", "sodium", "sugar"]),
  };
  result.water = {
    ...payload.water,
    rows: averageLifestyleRows(payload.water?.rows || [], "consumed_at", days, ["water_amount"]),
  };
  return result;
}

function svgNode(name, attributes, text = "") {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text) node.textContent = text;
  return node;
}

function buildBioChart(title, series) {
  const colors = ["#2f8f6b", "#e3924d", "#5e83c5", "#bd6c9b"];
  const plots = series.map((item) => item.rows
    .map((row) => ({ x: String(row.measured_at || ""), value: Number(item.value(row)) }))
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
        "aria-label": `${formatDataDate(point.x)} ${series[seriesIndex].label} ${formatDataNumber(point.value, 1)}`,
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
    // 축이 둘이면 어느 눈금을 읽어야 하는지 범례에서 알려준다.
    label.textContent = dualAxis ? `${item.label} · ${item.axis === "right" ? "우축" : "좌축"}` : item.label;
    label.style.setProperty("--legend-color", colors[index % colors.length]);
    legend.appendChild(label);
  });
  chart.append(heading, svg, legend); return chart;
}

function buildBioCharts(rows) {
  const byType = (type) => rows.filter((row) => row.bio_type === type);
  const charts = [];
  const heart = byType("heart_rate");
  if (heart.length) charts.push(buildBioChart("심박수 · 측정값", [{ label: "심박수(bpm)", rows: heart, value: (row) => row.value }]));
  const bodyRows = [...byType("weight"), ...byType("bmi")];
  if (bodyRows.length) charts.push(buildBioChart("체중과 BMI", [
    { label: "체중(kg)", rows: byType("weight"), value: (row) => row.value },
    { label: "BMI", rows: byType("bmi"), value: (row) => row.value, axis: "right" },
  ]));
  const pressure = byType("blood_pressure");
  if (pressure.length) charts.push(buildBioChart("혈압", [
    { label: "수축기", rows: pressure, value: (row) => row.detail_data?.systolic },
    { label: "이완기", rows: pressure, value: (row) => row.detail_data?.diastolic },
  ]));
  const glucose = byType("blood_glucose");
  if (glucose.length) charts.push(buildBioChart("혈당 · 공복/식후 구분 포함", [
    { label: "공복", rows: glucose.filter((row) => row.detail_data?.fasting === true), value: (row) => row.value },
    { label: "식후", rows: glucose.filter((row) => row.detail_data?.fasting === false), value: (row) => row.value },
    { label: "구분 없음", rows: glucose.filter((row) => row.detail_data?.fasting !== true && row.detail_data?.fasting !== false), value: (row) => row.value },
  ]));
  return charts.filter(Boolean);
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

function setDashboardStep(step, message, state = "done") {
  const item = document.querySelector(`[data-dashboard-step="${step}"]`);
  if (!item) return;
  item.dataset.state = state;
  const label = item.querySelector("small");
  if (label) label.textContent = message;
}

function formatElapsed(value) {
  const seconds = Number(value);
  return Number.isFinite(seconds) ? `${seconds.toFixed(3)}초` : "측정 불가";
}

function resetDashboardFlow() {
  ["latest", "history", "analysis", "result"].forEach((step) => setDashboardStep(step, "대기 중", "pending"));
  elements.dashboardStatusBadge.textContent = "대기";
  elements.dashboardStatusBadge.className = "quality-badge neutral";
  elements.dashboardCheckupCount.textContent = "—";
  elements.dashboardMetricCount.textContent = "—";
  elements.dashboardImprovedCount.textContent = "—";
  elements.dashboardManagementCount.textContent = "—";
  elements.dashboardReportLog.textContent = "AI 요약분석을 실행하면 처리 단계와 결과가 이곳에 기록됩니다.";
  elements.dashboardVerificationDetails.replaceChildren();
  elements.dashboardVerificationDetails.hidden = true;
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

function renderDashboardVerification(verification) {
  elements.dashboardVerificationDetails.replaceChildren();
  const timings = verification.timings || {};
  appendDashboardDetails("단계별 소요 시간", Object.fromEntries(
    Object.entries(timings).map(([key, value]) => [key, `${Number(value).toFixed(3)}초`]),
  ));
  appendDashboardDetails("분석에 전달된 지표와 DB 판정", verification.analysis_input || {});
  appendDashboardDetails("전체 검진 원본 이력", verification.history || []);
  appendDashboardDetails("데이터 출처 및 판정 기준", {
    source: verification.source,
    db_status_used: verification.db_status_used,
  });
  elements.dashboardVerificationDetails.hidden = false;
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
  setDashboardStep("history", "DB 전체 이력 수집 중...", "active");
  setDashboardStep("analysis", "Gemini 응답 대기 중...", "active");
  setDashboardStep("result", "응답 대기 중", "pending");
  elements.dashboardStatusBadge.textContent = "실행 중";
  elements.dashboardStatusBadge.className = "quality-badge info";
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
    elements.dashboardCheckupCount.textContent = payload.checkup_count;
    elements.dashboardMetricCount.textContent = (payload.report.improved || []).length + (payload.report.maintained || []).length + (payload.report.management_needed || []).length;
    elements.dashboardImprovedCount.textContent = (payload.report.improved || []).length;
    elements.dashboardManagementCount.textContent = (payload.report.management_needed || []).length;
    elements.dashboardStatusBadge.textContent = "완료";
    elements.dashboardStatusBadge.className = "quality-badge success";
    elements.dashboardReportLog.textContent = `전체 ${payload.checkup_count}회 검진 이력을 기반으로 AI 요약분석을 완료했습니다.`;
    renderDashboardVerification(payload.verification || {});
    renderCheckupReport(payload.report);
  } catch (error) {
    setDashboardStep("result", "분석 실패", "error");
    elements.dashboardStatusBadge.textContent = "오류";
    elements.dashboardStatusBadge.className = "quality-badge warning";
    elements.dashboardReportLog.textContent = error instanceof Error ? error.message : "AI 요약분석을 생성하지 못했습니다.";
    elements.checkupReport.hidden = false;
    elements.checkupReport.textContent = error instanceof Error ? error.message : "AI 요약분석을 생성하지 못했습니다.";
  } finally {
    elements.checkupReportButton.disabled = false;
    elements.checkupReportButton.textContent = "AI 요약분석";
  }
}

function renderLifestyle(payload) {
  const days = Number(payload.window_days) || lifestyleDays;
  lifestylePayload = aggregateLifestylePayload(payload, days);
  const displayPayload = lifestylePayload;
  const tabSections = getLifestyleTabSections(displayPayload, activeLifestyleTab);
  const total = tabSections.reduce((sum, spec) => sum + (((spec.domain || {}).rows) || []).length, 0);
  const aggregationLabel = days >= 180 ? "월평균" : days >= 90 ? "주평균" : "일별 평균";
  elements.lifestyleMeta.textContent = total
    ? `최신 기록일 기준 ${days}일 · ${aggregationLabel} · ${total}건`
    : "최근 기록 없음";

  const sections = tabSections.flatMap((spec) => {
    const section = buildLifestyleSection(spec, spec.domain);
    const chart = spec.key === "bio" ? null : buildLifestyleChart(spec, spec.domain);
    return [chart, section].filter(Boolean);
  });
  if (activeLifestyleTab === "bio") sections.unshift(...buildBioCharts((payload.bio || {}).rows || []));
  if (!sections.length) {
    setDataPlaceholder(elements.lifestyleBody, "최근 등록된 생활 데이터가 없습니다.");
    return;
  }
  elements.lifestyleBody.replaceChildren(...sections);
}

function getLifestyleTabSections(payload, tab) {
  const bio = payload.bio || { rows: [] };
  const bioRows = bio.rows || [];
  const bioSpec = lifestyleSections.find((spec) => spec.key === "bio");
  const groupedBioSections = (rows, titlePrefix = "") => {
    const groups = new Map();
    rows.forEach((row) => {
      const type = String(row.bio_type || "unknown");
      if (!groups.has(type)) groups.set(type, []);
      groups.get(type).push(row);
    });
    return [...groups].map(([type, groupedRows]) => ({
      ...bioSpec,
      title: `${titlePrefix}${bioTypeLabels[type] || type}`,
      domain: { ...bio, rows: groupedRows },
      chartMetric: { key: "value", label: "측정값", digits: 1 },
    }));
  };
  if (tab === "bio") {
    return groupedBioSections(bioRows.filter((row) => row.bio_type !== "sleep"));
  }
  if (tab === "sleep") {
    const sleep = payload.sleep || { rows: [] };
    return [{
      ...bioSpec,
      title: "수면시간",
      domain: sleep,
      chartMetric: { key: "value", label: "수면시간", digits: 1, unit: "시간" },
    }];
  }
  if (tab === "activity") {
    return lifestyleSections
      .filter((spec) => spec.key === "activity" || spec.key === "exercise")
      .map((spec) => ({ ...spec, domain: payload[spec.key], chartMetric: spec.key === "activity" ? { key: "steps", label: "걸음 수" } : { key: "duration_sec", label: "운동시간(초)" } }));
  }
  return lifestyleSections
    .filter((spec) => spec.key === "food" || spec.key === "water")
    .map((spec) => ({
      ...spec,
      domain: payload[spec.key],
      chartMetric: spec.key === "water"
        ? { key: "water_amount", label: "수분 섭취량(mL)" }
        : { key: "calories", label: "칼로리" },
    }));
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
  const body = isCheckup ? elements.checkupBody : elements.lifestyleBody;
  const meta = isCheckup ? elements.checkupMeta : elements.lifestyleMeta;

  meta.textContent = "불러오는 중...";
  setDataPlaceholder(body, isCheckup ? "검진 결과를 불러오고 있어요." : "생활 데이터를 불러오고 있어요.");
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
    setDataPlaceholder(
      body,
      error instanceof Error ? error.message : "개인 데이터를 불러오지 못했습니다.",
      true,
    );
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
  else {
    resetDashboardFlow();
    setDataTab(activeDataTab);
  }
}

function resetPersonalData() {
  loadedDataTabs.clear();
  resetCheckupRecords();
  activeDataTab = "checkup";
  elements.checkupMeta.textContent = "—";
  elements.lifestyleMeta.textContent = "—";
  resetDashboardFlow();
  setDataPlaceholder(elements.checkupBody, "검진 결과를 불러오고 있어요.");
  setDataPlaceholder(elements.lifestyleBody, "생활 데이터를 불러오고 있어요.");
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
  loadPersonalData(activeDataTab, { force: true });
});
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
