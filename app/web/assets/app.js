/** HEAPY 웹 앱 상호작용. 작성자: 김진우 */
const elements = {
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
  llmBackendLabel: document.querySelector("#llmBackendLabel"),
  totalChunkCount: document.querySelector("#totalChunkCount"),
  classifierLabel: document.querySelector("#classifierLabel"),
  collectionTotalLabel: document.querySelector("#collectionTotalLabel"),
  environmentCollectionList: document.querySelector("#environmentCollectionList"),
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
    elements.llmBackendLabel.textContent = String(data.llm_backend || "unknown").toUpperCase();
    elements.llmBackendLabel.title = data.llm_backend || "unknown";
    elements.totalChunkCount.textContent = totalChunks.toLocaleString("ko-KR");
    elements.classifierLabel.textContent = classifier.ready
      ? classifier.model_version || "준비 완료"
      : "모델 없음";
    renderCollections(indexedChunks);
  } catch (error) {
    setEnvironmentBadge("error", "연결 실패");
    elements.vectorBackendLabel.textContent = "확인 불가";
    elements.embedModelLabel.textContent = "확인 불가";
    elements.llmBackendLabel.textContent = "확인 불가";
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
  avatar.innerHTML = '<img src="/assets/images/heapy-doctor.png" alt="" aria-hidden="true" />';
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

function appendLocalAssistantMessage(answer) {
  const message = document.createElement("div");
  message.className = "message assistant";
  message.appendChild(createAssistantAvatar());
  const content = document.createElement("div");
  content.className = "message-content";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = answer;
  content.appendChild(bubble);
  message.appendChild(content);
  elements.messages.appendChild(message);
  scrollToLatest();
}

function getConfirmationTerm(data) {
  const terms = Array.isArray(data.resolved_terms) ? data.resolved_terms : [];
  return terms.find((term) => term.match_kind === "initials") || terms[0] || null;
}

function buildConfirmedQuestion(data) {
  const term = getConfirmationTerm(data);
  const originalQuestion = String(data.question || "").trim();
  const source = String(term?.input || "").trim();
  const canonical = String(term?.canonical_name || term?.matched_alias || "").trim();
  if (!canonical) return originalQuestion;
  if (!source || !originalQuestion.includes(source)) return canonical;
  return originalQuestion.replace(source, canonical);
}

function handleQueryConfirmation(data, accepted, actions) {
  actions.remove();
  if (accepted) {
    if (data.confirmation_id) {
      submitQuestion(data.question, "예", {
        confirmationId: data.confirmation_id,
        confirmationAnswer: true,
      });
    } else {
      // 구버전 API와의 하위 호환용 fallback. 최신 서버는 confirmation_id를
      // 발급하므로 원문을 다시 resolver에 넣지 않는다.
      submitQuestion(buildConfirmedQuestion(data), "예");
    }
    return;
  }
  appendUserMessage("아니요");
  appendLocalAssistantMessage("알겠어요. 정확한 용어나 질문을 입력해 주세요.");
  elements.input.focus();
}

function createQueryConfirmationActions(data) {
  const actions = document.createElement("div");
  actions.className = "query-confirmation-actions";
  const yesButton = document.createElement("button");
  yesButton.type = "button";
  yesButton.className = "confirmation-button primary";
  yesButton.textContent = "예";
  yesButton.addEventListener("click", () => handleQueryConfirmation(data, true, actions));
  const noButton = document.createElement("button");
  noButton.type = "button";
  noButton.className = "confirmation-button";
  noButton.textContent = "아니요";
  noButton.addEventListener("click", () => handleQueryConfirmation(data, false, actions));
  actions.append(yesButton, noButton);
  return actions;
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
    bubble.textContent = sanitizeAnswerText(data.answer) || "답변을 생성하지 못했습니다.";
  } else if (message.dataset.started !== "true") {
    bubble.classList.remove("loading-bubble");
    bubble.textContent = sanitizeAnswerText(data.answer) || "답변을 생성하지 못했습니다.";
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
    groundedChip.textContent = "근거 계획 승인";
    meta.appendChild(groundedChip);
  }
  if (data.query_confirmation === true) {
    const confirmationChip = document.createElement("span");
    confirmationChip.className = "answer-chip";
    confirmationChip.textContent = "검색어 확인 필요";
    meta.appendChild(confirmationChip);
  }
  if (data.resolution_status === "AMBIGUOUS") {
    const ambiguousChip = document.createElement("span");
    ambiguousChip.className = "answer-chip warning";
    ambiguousChip.textContent = "검색어 구체화 필요";
    meta.appendChild(ambiguousChip);
  }
  const resolvedTerms = Array.isArray(data.resolved_terms) ? data.resolved_terms : [];
  if (resolvedTerms.length) {
    const resolvedChip = document.createElement("span");
    resolvedChip.className = "answer-chip";
    resolvedChip.textContent = `표준용어 보정 ${resolvedTerms.length}건`;
    meta.appendChild(resolvedChip);
  }
  if (data.audit_status === "failed" || data.audit_status === "error") {
    const auditChip = document.createElement("span");
    auditChip.className = "answer-chip warning";
    auditChip.textContent = "감사 확인 필요";
    meta.appendChild(auditChip);
  }
  content.querySelector(".answer-meta")?.remove();
  content.appendChild(meta);
  content.querySelector(".query-confirmation-actions")?.remove();
  if (data.query_confirmation === true) {
    content.appendChild(createQueryConfirmationActions(data));
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
  bubble.textContent = sanitizeAnswerText(message.dataset.rawAnswer, true);
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
  let sanitized = String(text || "").replace(/\[C\d+\]/g, "");
  if (hidePartialLabel) sanitized = sanitized.replace(/\[(?:C\d*)?$/g, "");
  return sanitized
    .replace(/[ \t]+\n/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .trimStart();
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
    query_confirmation: { label: "검색어 확인 대기", className: "not_applicable" },
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

function appendGroundingPlan(body, data) {
  const plan = data.grounding_plan;
  const section = appendAuditSection(body, "선검증 근거 계획");
  if (!plan) {
    section.appendChild(createTextElement("div", "no-source", "이 응답 경로에는 근거 계획이 없습니다."));
    return;
  }

  section.appendChild(createTextElement("p", "environment-placeholder", plan.reason || "판단 이유 없음"));
  const list = document.createElement("ul");
  list.className = "plan-fact-list";
  (plan.facts || []).forEach((fact) => {
    const item = createTextElement("li", "plan-fact", fact.statement || "사실 내용 없음");
    item.appendChild(
      createTextElement("em", "", `근거: ${(fact.cited_chunk_ids || []).join(", ") || "없음"}`),
    );
    list.appendChild(item);
  });
  if (!list.childElementCount) {
    list.appendChild(createTextElement("li", "plan-fact", "승인된 근거 사실이 없습니다."));
  }
  section.appendChild(list);
}

function appendUnsupportedClaims(body, data) {
  const claims = Array.isArray(data.unsupported_claims) ? data.unsupported_claims : [];
  if (!claims.length && !(data.grounding_errors || []).length) return;
  const section = appendAuditSection(body, "감사 경고");
  const list = document.createElement("ul");
  list.className = "unsupported-list";
  [...claims, ...(data.grounding_errors || [])].forEach((claim) => {
    list.appendChild(createTextElement("li", "", claim));
  });
  section.appendChild(list);
}

function appendResolvedTerms(body, data) {
  const terms = Array.isArray(data.resolved_terms) ? data.resolved_terms : [];
  if (!terms.length) return;
  const section = appendAuditSection(body, "검색어 정규화");
  const list = document.createElement("ul");
  list.className = "plan-fact-list";
  terms.forEach((term) => {
    const item = createTextElement(
      "li",
      "plan-fact",
      `${term.input || "입력 용어"} → ${term.canonical_name || "표준용어"}`,
    );
    item.appendChild(
      createTextElement(
        "em",
        "",
        `${term.term_type || "OTHER"} · ${term.match_kind || "fuzzy"} · score ${term.score ?? "—"}`,
      ),
    );
    list.appendChild(item);
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
    chunks.slice(0, 6).forEach((chunk, index) => {
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
      const preview = createTextElement("p", "", String(chunk.text || "본문 없음").slice(0, 150));
      const source = createTextElement(
        "span",
        "chunk-source",
        String(chunk.source || "출처 미상").split(" · ")[0],
      );
      item.append(header, meta, preview, source);
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
    ["근거 상태", data.grounded === true ? "계획 승인" : data.grounded === false ? "계획 거절" : "검색 미사용"],
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
  addMonitorItem(monitorList, "응답 경로", data.intent_source === "safety_guard" ? "Safety Guard" : "Intent v6");
  addMonitorItem(monitorList, "검증 방식", formatVerification(data.verification_method));
  addMonitorItem(monitorList, "검증 사유", data.verification_reason);
  addMonitorItem(monitorList, "분류 검토", data.uncertain ? "필요" : "불필요");
  addMonitorItem(monitorList, "검색 컬렉션", (data.searched_collections || []).join(", ") || "검색 안 함");
  addMonitorItem(monitorList, "실패 컬렉션", (data.failed_collections || []).join(", ") || "없음");
  monitorSection.appendChild(monitorList);

  appendResolvedTerms(body, data);
  appendGroundingPlan(body, data);
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
    prevalidated_post_audit: "근거 계획 + 사후 감사",
    prevalidated_audit_warning: "근거 계획 + 감사 경고",
    prevalidated_audit_error: "근거 계획 + 감사 오류",
    plan_rejected: "근거 계획 거절",
    fixed_response: "고정 응답",
    not_applicable: "검증 대상 아님",
  };
  return names[method] || method || "—";
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
  } catch (error) {
    tokenPacer.cancel();
    throw error;
  }
}

async function submitQuestion(question, displayQuestion = "", options = {}) {
  const normalized = question.trim();
  if (!normalized || isRequesting) return;

  isRequesting = true;
  setConversationMode();
  setInsightPending();
  appendUserMessage(displayQuestion.trim() || normalized);
  appendLoadingMessage();
  elements.input.value = "";
  resizeInput();

  try {
    const payload = { question: normalized };
    if (options.confirmationId) {
      payload.confirmation_id = options.confirmationId;
      payload.confirmation_answer = options.confirmationAnswer === true;
    }
    const response = await fetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
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
document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => submitQuestion(button.dataset.question || ""));
});

renderSuggestionCards();
resizeInput();
loadProjectEnvironment();
