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

let isRequesting = false;

function sanitizeAnswerText(text) {
  return String(text || "")
    .replace(/\[C\d+\]/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .trimStart();
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
  content.appendChild(bubble);
  message.appendChild(content);
  elements.messages.appendChild(message);
  scrollToLatest();
  return { message, content, bubble };
}

function startAnswer(loading, text) {
  if (loading.message.dataset.started !== "true") {
    loading.message.dataset.started = "true";
    loading.bubble.className = "bubble";
    loading.bubble.replaceChildren();
  }
  loading.bubble.textContent += sanitizeAnswerText(text);
  scrollToLatest();
}

function appendAnswerInfo(content, data) {
  const sources = [...new Set(Array.isArray(data.sources) ? data.sources : [])];
  if (sources.length) {
    const details = document.createElement("details");
    details.className = "source-details";
    const summary = document.createElement("summary");
    summary.textContent = `답변 출처 ${sources.length}개`;
    const list = document.createElement("ul");
    sources.forEach((source) => {
      const item = document.createElement("li");
      item.textContent = source;
      list.appendChild(item);
    });
    details.append(summary, list);
    content.appendChild(details);
  }
  if (data.grounded === false) {
    const notice = document.createElement("p");
    notice.className = "answer-notice";
    notice.textContent = "확인 가능한 근거가 부족한 답변입니다. 참고용으로만 이용해 주세요.";
    content.appendChild(notice);
  }
}

function appendErrorMessage(text, loading) {
  loading?.message.remove();
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

async function consumeChatStream(response, loading) {
  if (!response.body) throw new Error("이 브라우저에서는 스트리밍 답변을 사용할 수 없어요.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let completePayload = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const event = parseSseBlock(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (event?.eventName === "token") startAnswer(loading, event.payload.text || "");
      if (event?.eventName === "complete") completePayload = event.payload;
      if (event?.eventName === "error") throw new Error(event.payload.message || "답변을 불러오지 못했어요.");
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }

  if (!completePayload) throw new Error("답변 연결이 예상보다 일찍 종료됐어요.");
  if (loading.message.dataset.started !== "true") startAnswer(loading, completePayload.answer || "답변을 준비하지 못했어요.");
  appendAnswerInfo(loading.content, completePayload);
}

async function submitQuestion(question) {
  const normalized = question.trim();
  if (!normalized || isRequesting) return;

  isRequesting = true;
  setConversationMode();
  appendUserMessage(normalized);
  const loading = appendLoadingMessage();
  elements.input.value = "";
  resizeInput();

  try {
    const response = await fetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: normalized }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "건강정보 서버가 아직 준비되지 않았어요.");
    }
    await consumeChatStream(response, loading);
  } catch (error) {
    appendErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류가 발생했어요.", loading);
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
