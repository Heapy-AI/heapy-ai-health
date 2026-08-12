// HEAPY 사용자 UI. 작성자: 김진우
const elements = {
  initialLoadingScreen: document.querySelector("#initialLoadingScreen"),
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
  conversationList: document.querySelector("#conversationList"),
  newConversationButton: document.querySelector("#newConversationButton"),
  conversation: document.querySelector("#conversation"),
  welcome: document.querySelector("#welcome"),
  messages: document.querySelector("#messages"),
  conversationLoading: document.querySelector("#conversationLoading"),
  deleteConversationDialog: document.querySelector("#deleteConversationDialog"),
  deleteConversationTitle: document.querySelector("#deleteConversationTitle"),
  form: document.querySelector("#chatForm"),
  input: document.querySelector("#questionInput"),
  sendButton: document.querySelector("#sendButton"),
  resetButton: document.querySelector("#resetButton"),
};

const STREAM_CHARACTER_DELAY_MS = 28;
const STREAM_COMMA_DELAY_MS = 70;
const STREAM_SENTENCE_DELAY_MS = 130;
const INITIAL_LOADING_MINIMUM_MS = 450;
const initialLoadingStartedAt = performance.now();
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
let isRequesting = false;
let conversationHistory = [];
let conversationSummary = "";
let currentSessionId = "";
let conversationSessions = [];
let authMode = "login";
let conversationLoadSequence = 0;

function setLoginError(message = "") {
  elements.loginError.textContent = message;
  elements.loginError.hidden = !message;
}

function setAuthMode(mode) {
  authMode = mode;
  const isSignup = mode === "signup";
  elements.loginModeButton.classList.toggle("active", !isSignup);
  elements.signupModeButton.classList.toggle("active", isSignup);
  elements.signupFields.hidden = !isSignup;
  elements.nameInput.required = isSignup;
  elements.birthDateInput.required = isSignup;
  elements.sexInput.required = isSignup;
  elements.loginTitle.textContent = isSignup ? "HEAPY와 함께 시작해요" : "다시 만나서 반가워요";
  elements.authDescription.textContent = isSignup
    ? "건강 프로필과 로그인 계정을 함께 만들어요."
    : "HEAPY 계정으로 로그인해 주세요.";
  elements.loginButton.textContent = isSignup ? "회원가입" : "로그인";
  setLoginError();
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
  elements.passwordInput.value = "";
  setAuthMode("login");
  setLoginError(message);
  elements.emailInput.focus();
}

function hideInitialLoadingScreen() {
  const elapsed = performance.now() - initialLoadingStartedAt;
  const delay = Math.max(0, INITIAL_LOADING_MINIMUM_MS - elapsed);
  window.setTimeout(() => {
    elements.initialLoadingScreen.classList.add("leaving");
    window.setTimeout(() => {
      elements.initialLoadingScreen.hidden = true;
    }, 240);
  }, delay);
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
  try {
    let response = await fetch("/auth/me", { headers: { Accept: "application/json" } });
    if (response.status === 401 && await refreshSession()) {
      response = await fetch("/auth/me", { headers: { Accept: "application/json" } });
    }
    if (!response.ok) {
      showLoginScreen();
      return;
    }
    renderAuthenticatedUser(await response.json());
  } catch {
    showLoginScreen("로그인 상태를 확인하지 못했습니다. 다시 로그인해 주세요.");
  } finally {
    hideInitialLoadingScreen();
  }
}

async function login(event) {
  event.preventDefault();
  setLoginError();
  const isSignup = authMode === "signup";
  elements.loginButton.disabled = true;
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
    const response = await fetch(isSignup ? "/auth/signup" : "/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "인증 처리에 실패했습니다.");
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
  conversationSessions = sessions;
  elements.conversationList.replaceChildren();
  if (!sessions.length) {
    const empty = document.createElement("p");
    empty.className = "conversation-list-empty";
    empty.textContent = "저장된 대화가 없습니다.";
    elements.conversationList.appendChild(empty);
    return;
  }
  sessions.forEach((session) => {
    const item = document.createElement("div");
    item.className = "conversation-item";
    item.classList.toggle("active", session.session_id === currentSessionId);
    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "conversation-item-main";
    const title = document.createElement("strong");
    title.textContent = session.title || "새 대화";
    const time = document.createElement("time");
    const updatedAt = new Date(session.updated_at);
    time.textContent = Number.isNaN(updatedAt.getTime())
      ? ""
      : new Intl.DateTimeFormat("ko-KR", { month: "numeric", day: "numeric" }).format(updatedAt);
    openButton.append(title, time);
    openButton.addEventListener("click", () => loadConversation(session.session_id));

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "conversation-delete-button";
    deleteButton.setAttribute("aria-label", `${title.textContent} 대화 삭제`);
    deleteButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14M10 10v6m4-6v6" /></svg>';
    deleteButton.addEventListener("click", () => {
      deleteConversation(session.session_id, title.textContent, deleteButton);
    });

    item.append(openButton, deleteButton);
    elements.conversationList.appendChild(item);
  });
}

function confirmConversationDeletion(title) {
  elements.deleteConversationTitle.textContent = `“${title || "새 대화"}”`;
  elements.deleteConversationDialog.returnValue = "cancel";
  return new Promise((resolve) => {
    elements.deleteConversationDialog.addEventListener(
      "close",
      () => resolve(elements.deleteConversationDialog.returnValue === "confirm"),
      { once: true },
    );
    elements.deleteConversationDialog.showModal();
  });
}

async function deleteConversation(sessionId, title, deleteButton) {
  if (isRequesting) {
    window.alert("답변 생성이 끝난 후 대화를 삭제해 주세요.");
    return;
  }
  const confirmed = await confirmConversationDeletion(title);
  if (!confirmed) return;

  deleteButton.disabled = true;
  try {
    const response = await fetchWithSession(`/conversations/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "대화를 삭제하지 못했습니다.");

    conversationSessions = conversationSessions.filter(
      (session) => session.session_id !== sessionId,
    );
    if (currentSessionId === sessionId) {
      resetConversation();
    } else {
      renderConversationSessions(conversationSessions);
    }
  } catch (error) {
    window.alert(error instanceof Error ? error.message : "대화를 삭제하지 못했습니다.");
  } finally {
    deleteButton.disabled = false;
  }
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
  const loadSequence = ++conversationLoadSequence;
  const previousSessionId = currentSessionId;
  currentSessionId = sessionId;
  renderConversationSessions(conversationSessions);
  elements.welcome.hidden = true;
  elements.messages.hidden = true;
  elements.conversationLoading.hidden = false;
  try {
    const response = await fetchWithSession(`/conversations/${encodeURIComponent(sessionId)}`, {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(() => ({}));
    if (loadSequence !== conversationLoadSequence) return;
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
    scrollToLatest();
  } catch (error) {
    if (loadSequence !== conversationLoadSequence) return;
    currentSessionId = previousSessionId;
    renderConversationSessions(conversationSessions);
    elements.messages.replaceChildren();
    elements.messages.hidden = false;
    appendErrorMessage(error instanceof Error ? error.message : "대화를 불러오지 못했습니다.");
  } finally {
    if (loadSequence === conversationLoadSequence) {
      elements.conversationLoading.hidden = true;
    }
  }
}

function updateConversationSessionPreview(data) {
  const sessionId = String(data.session_id || "");
  if (!sessionId) return;
  const existing = conversationSessions.find((session) => session.session_id === sessionId);
  const question = String(data.original_question || data.question || "새 대화").trim();
  const preview = {
    session_id: sessionId,
    title: existing?.title && existing.title !== "새 대화"
      ? existing.title
      : question.slice(0, 60) || "새 대화",
    summary: data.conversation_summary || existing?.summary || "",
    created_at: existing?.created_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  conversationSessions = [
    preview,
    ...conversationSessions.filter((session) => session.session_id !== sessionId),
  ];
  renderConversationSessions(conversationSessions);
}

function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 120)}px`;
  elements.sendButton.disabled = !elements.input.value.trim() || isRequesting;
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

function createAssistantAvatar() {
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  const image = document.createElement("img");
  image.src = "/images/heapy-doctor.png";
  image.alt = "HEAPY";
  avatar.appendChild(image);
  return avatar;
}

function appendUserMessage(text) {
  const message = document.createElement("div");
  message.className = "message user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  message.appendChild(bubble);
  elements.messages.appendChild(message);
  scrollToLatest();
}

function appendLoadingMessage() {
  const message = document.createElement("div");
  message.className = "message assistant";
  message.dataset.loading = "true";
  message.appendChild(createAssistantAvatar());
  const content = document.createElement("div");
  content.className = "message-content";
  const bubble = document.createElement("div");
  bubble.className = "bubble loading-bubble";
  bubble.append(document.createElement("span"), document.createElement("span"), document.createElement("span"));
  const status = document.createElement("p");
  status.className = "loading-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  status.textContent = "답변 요청을 전송하는 중입니다";
  content.append(bubble, status);
  message.appendChild(content);
  elements.messages.appendChild(message);
  scrollToLatest();
}

function updateLoadingProgress(payload) {
  const status = document.querySelector('[data-loading="true"] .loading-status');
  const message = String(payload?.message || "").trim();
  if (!status || !message) return;
  status.textContent = message;
  status.dataset.stage = String(payload?.stage || "");
  scrollToLatest();
}

function hideLoadingProgress() {
  document.querySelector('[data-loading="true"] .loading-status')?.remove();
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
  message.querySelector(".loading-status")?.remove();

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

function appendErrorMessage(text) {
  document.querySelector('[data-loading="true"]')?.remove();
  const message = document.createElement("div");
  message.className = "message assistant error";
  message.appendChild(createAssistantAvatar());
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  message.appendChild(bubble);
  elements.messages.appendChild(message);
  scrollToLatest();
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
  if (!response.body) throw new Error("이 브라우저에서는 스트리밍 답변을 사용할 수 없어요.");
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
        if (event?.eventName === "progress") {
          if (event.payload?.stage === "answer_stream_complete") {
            void tokenPacer.drain().then(hideLoadingProgress);
          } else {
            updateLoadingProgress(event.payload);
          }
        }
        if (event?.eventName === "token") tokenPacer.push(event.payload.text || "");
        if (event?.eventName === "complete") completePayload = event.payload;
        if (event?.eventName === "error") throw new Error(event.payload.message || "답변을 불러오지 못했어요.");
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }

    if (!completePayload) throw new Error("답변 연결이 예상보다 일찍 종료됐어요.");
    await tokenPacer.drain();
    appendAssistantMessage(completePayload);
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
  updateConversationSessionPreview(data);
  loadConversationSessions();
}

async function submitQuestion(question, options = {}) {
  const normalized = question.trim();
  if (!normalized || isRequesting) return;

  isRequesting = true;
  setConversationMode();
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
      throw new Error(payload.detail || "건강정보 서버가 아직 준비되지 않았어요.");
    }
    await consumeChatStream(response);
  } catch (error) {
    appendErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류가 발생했어요.");
  } finally {
    isRequesting = false;
    resizeInput();
    elements.input.focus();
  }
}

function resetConversation() {
  if (isRequesting) return;
  conversationLoadSequence += 1;
  elements.conversationLoading.hidden = true;
  elements.messages.replaceChildren();
  elements.messages.hidden = true;
  elements.welcome.hidden = false;
  conversationHistory = [];
  conversationSummary = "";
  currentSessionId = "";
  renderConversationSessions(conversationSessions);
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
  resetConversation();
  loadConversationSessions();
});
elements.loginForm.addEventListener("submit", login);
elements.loginModeButton.addEventListener("click", () => setAuthMode("login"));
elements.signupModeButton.addEventListener("click", () => setAuthMode("signup"));
elements.logoutButton.addEventListener("click", logout);
elements.deleteConversationDialog.addEventListener("click", (event) => {
  if (event.target === elements.deleteConversationDialog) {
    elements.deleteConversationDialog.close("cancel");
  }
});
document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => submitQuestion(button.dataset.question || ""));
});

resizeInput();
renderSuggestionCards();
restoreSession();
