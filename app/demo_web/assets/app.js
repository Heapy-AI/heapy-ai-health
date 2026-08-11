// HEAPY 사용자 시연 UI. 작성자: 김진우
const elements = {
  conversation: document.querySelector("#conversation"),
  welcome: document.querySelector("#welcome"),
  messages: document.querySelector("#messages"),
  form: document.querySelector("#chatForm"),
  input: document.querySelector("#questionInput"),
  sendButton: document.querySelector("#sendButton"),
  resetButton: document.querySelector("#resetButton"),
};

const STREAM_CHARACTER_DELAY_MS = 28;
const STREAM_COMMA_DELAY_MS = 70;
const STREAM_SENTENCE_DELAY_MS = 130;
let isRequesting = false;
let conversationHistory = [];
let conversationSummary = "";

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
  content.appendChild(bubble);
  message.appendChild(content);
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
    const response = await fetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: normalized,
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
  elements.messages.replaceChildren();
  elements.messages.hidden = true;
  elements.welcome.hidden = false;
  conversationHistory = [];
  conversationSummary = "";
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
document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => submitQuestion(button.dataset.question || ""));
});

resizeInput();
