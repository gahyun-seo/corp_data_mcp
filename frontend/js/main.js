// ======================================================
// 1) 공통: 스무스 스크롤 (홈에서 쓰던 거)
// ======================================================
document.addEventListener("click", (e) => {
  const trigger = e.target.closest("[data-scroll-to]");
  if (!trigger) return;
  const selector = trigger.getAttribute("data-scroll-to");
  const target = document.querySelector(selector);
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

// ======================================================
// 2) AI Agent 첫 화면 (ai_agent.html)
//    - 검색 or 추천버튼 → 채팅 페이지로 이동
// ======================================================
const agentSearchForm = document.getElementById("agent-search-form");
const agentSearchInput = document.getElementById("agent-search-input");

if (agentSearchForm && agentSearchInput) {
  agentSearchForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = agentSearchInput.value.trim();
    if (!q) return;
    window.location.href = `ai_agent_chat.html?q=${encodeURIComponent(q)}`;
  });
}

const suggestionButtons = document.querySelectorAll(".suggest-btn");
if (suggestionButtons.length) {
  suggestionButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const q = btn.getAttribute("data-query") || btn.textContent.trim();
      window.location.href = `ai_agent_chat.html?q=${encodeURIComponent(q)}`;
    });
  });
}

// ======================================================
// 3) AI Agent 채팅 화면 (ai_agent_chat.html)
// ======================================================
const chatBody = document.getElementById("chat-body");
const chatForm = document.getElementById("chat-input-form");
const chatInput = document.getElementById("chat-input");
const chatTitle = document.getElementById("chat-topic");

// URL에서 q 파라미터 읽기
function getQueryParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}

// 유저 메시지 추가 (오른쪽)
function appendUserMessage(text) {
  if (!chatBody) return;

  const wrap = document.createElement("div");
  wrap.className = "user-msg";

  const bubble = document.createElement("div");
  bubble.className = "user-bubble";

  // 첫 줄: 아이콘 + You
  const header = document.createElement("div");
  header.className = "user-header";

  const avatar = document.createElement("div");
  avatar.className = "avatar";

  const label = document.createElement("span");
  label.className = "user-label";
  label.textContent = "You";

  header.appendChild(avatar);
  header.appendChild(label);

  // 두 번째 줄: 실제 메시지
  const msg = document.createElement("div");
  msg.className = "user-text";
  msg.textContent = text;

  bubble.appendChild(header);
  bubble.appendChild(msg);
  wrap.appendChild(bubble);
  chatBody.appendChild(wrap);

  // 구분선
  const hr = document.createElement("hr");
  hr.className = "inline-divider";
  chatBody.appendChild(hr);

  chatBody.scrollTop = chatBody.scrollHeight;
}

// MCP Agent 메시지 추가
function appendAgentMessage(text) {
  if (!chatBody) return;

  const wrap = document.createElement("div");
  wrap.className = "agent-msg";

  const avatar = document.createElement("div");
  avatar.className = "avatar agent";

  const meta = document.createElement("div");
  meta.className = "agent-meta";

  const name = document.createElement("div");
  name.className = "agent-name";
  name.textContent = "MCP Agent";

  const content = document.createElement("div");
  content.className = "agent-text";
  content.textContent = "";

  meta.appendChild(name);
  meta.appendChild(content);
  wrap.appendChild(avatar);
  wrap.appendChild(meta);
  chatBody.appendChild(wrap);

  // 타이핑 효과
  let i = 0;
  const speed = 12;
  const timer = setInterval(() => {
    content.textContent = text.slice(0, i);
    chatBody.scrollTop = chatBody.scrollHeight;
    i++;
    if (i > text.length) clearInterval(timer);
  }, speed);
}

// 채팅 페이지일 때만 초기 메시지 찍기
if (chatBody && chatForm && chatInput) {
  // 1) 처음 들어올 때 q가 있으면 그걸 첫 유저 메시지로
  const firstQ = getQueryParam("q") || "삼성전자 최근 분기 재무 요약";

  // 유저 메시지 먼저
  appendUserMessage(firstQ);

  // 상단 타이틀도 이걸로
  if (chatTitle) chatTitle.textContent = firstQ;

  // 에이전트 첫 답변
  const dummyFirst =
    "요청하신 항목을 요약해드릴게요.\n(데모 데이터)\n매출: 67조 4,000억 원\n영업이익: 8조 1,200억 원\n순이익: 6조 9,000억 원\n\n전년 동기 대비 매출은 약 12% 증가, 영업이익은 32% 증가했습니다.";
  appendAgentMessage(dummyFirst);

  // 2) 이후 사용자가 새로 질문 보낼 때
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = chatInput.value.trim();
    if (!q) return;

    // 유저 메시지 추가
    appendUserMessage(q);

    // 타이틀도 이 메시지로 갱신
    if (chatTitle) chatTitle.textContent = q;

    // 에이전트 답변 (나중에 fetch로 교체)
    const answer =
      q +
      " 에 대한 요약을 정리해드릴게요.\n(데모) 실제 값은 백엔드 응답으로 교체됩니다.";
    appendAgentMessage(answer);

    chatInput.value = "";
  });
}