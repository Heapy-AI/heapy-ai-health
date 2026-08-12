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
  environmentStatus: document.querySelector("#environmentStatus"),
  vectorBackendLabel: document.querySelector("#vectorBackendLabel"),
  embedModelLabel: document.querySelector("#embedModelLabel"),
  totalChunkCount: document.querySelector("#totalChunkCount"),
  classifierLabel: document.querySelector("#classifierLabel"),
  collectionTotalLabel: document.querySelector("#collectionTotalLabel"),
  environmentCollectionList: document.querySelector("#environmentCollectionList"),
  conversationList: document.querySelector("#conversationList"),
  newConversationButton: document.querySelector("#newConversationButton"),
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

    setEnvironmentBadge(data.ready ? "ready" : "warning", data.ready ? "준비 완료" : "점검 필요");
    elements.vectorBackendLabel.textContent = String(data.vector_backend || "unknown").toUpperCase();
    elements.embedModelLabel.textContent = data.embed_model || "unknown";
    elements.embedModelLabel.title = data.embed_model || "unknown";
    elements.totalChunkCount.textContent = totalChunks.toLocaleString("ko-KR");
    elements.classifierLabel.textContent = classifier.ready
      ? classifier.model_version || "준비 완료"
      : "모델 없음";
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
elements.newConversationButton.addEventListener("click", resetConversation);
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
