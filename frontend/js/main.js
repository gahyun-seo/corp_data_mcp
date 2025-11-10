// ======================================================
// 0) 공통 설정
// ======================================================
const API_BASE = "http://127.0.0.1:8000"; // 백엔드 주소

// URL에서 파라미터 읽기
function getQueryParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}

// ======================================================
// 1) 공통: 스무스 스크롤
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

// 채팅 말풍선 - 유저
function appendUserMessage(text) {
  if (!chatBody) return;

  const wrap = document.createElement("div");
  wrap.className = "user-msg";

  const bubble = document.createElement("div");
  bubble.className = "user-bubble";

  const header = document.createElement("div");
  header.className = "user-header";

  const avatar = document.createElement("div");
  avatar.className = "avatar";

  const label = document.createElement("span");
  label.className = "user-label";
  label.textContent = "You";

  header.appendChild(avatar);
  header.appendChild(label);

  const msg = document.createElement("div");
  msg.className = "user-text";
  msg.textContent = text;

  bubble.appendChild(header);
  bubble.appendChild(msg);
  wrap.appendChild(bubble);
  chatBody.appendChild(wrap);

  const hr = document.createElement("hr");
  hr.className = "inline-divider";
  chatBody.appendChild(hr);

  chatBody.scrollTop = chatBody.scrollHeight;
}

// 채팅 말풍선 - 에이전트
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

  let i = 0;
  const speed = 12;
  const timer = setInterval(() => {
    content.textContent = text.slice(0, i);
    chatBody.scrollTop = chatBody.scrollHeight;
    i++;
    if (i > text.length) clearInterval(timer);
  }, speed);
}

// 근거 표시 (있으면)
function appendRefs(chunks) {
  if (!chatBody) return;
  if (!chunks || !chunks.length) return;

  const box = document.createElement("div");
  box.className = "agent-refs";
  box.textContent = "📎 참고 문서:";

  chunks.slice(0, 3).forEach((c) => {
    const line = document.createElement("div");
    line.className = "agent-ref-line";
    line.textContent = `[${c.stock_code}] ${c.title}`;
    box.appendChild(line);
  });

  chatBody.appendChild(box);
  chatBody.scrollTop = chatBody.scrollHeight;
}

// 실제 백엔드 호출 함수
async function sendToBackend(question) {
  // 로딩
  const loading = document.createElement("div");
  loading.className = "agent-msg";
  loading.textContent = "생각 중...";
  chatBody.appendChild(loading);
  chatBody.scrollTop = chatBody.scrollHeight;

  try {
    const res = await fetch(`${API_BASE}/ai/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        top_k: 8,
      }),
    });
    console.log("status:", res.status);
    const data = await res.json();

    chatBody.removeChild(loading);
    appendAgentMessage(data.answer || "(응답이 없습니다)");
    // appendRefs(data.chunks);
  } catch (err) {
    console.error("fetch error:", err);
    chatBody.removeChild(loading);
    appendAgentMessage("❗ 서버 요청 중 오류가 났습니다.");
  }
}

// 채팅 페이지일 때만 작동
if (chatBody && chatForm && chatInput) {
  // 1) URL로부터 온 첫 질문
  const firstQ = getQueryParam("q") || "삼성전자 최근 분기 재무 요약";

  // 화면에 사용자 메시지로 찍고
  appendUserMessage(firstQ);
  if (chatTitle) chatTitle.textContent = firstQ;

  // 🔥 여기! 메인 화면에서 넘어온 첫 질문을 바로 백엔드로 보냄
  sendToBackend(firstQ);

  // 2) 이후 사용자가 직접 입력하는 경우
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = chatInput.value.trim();
    if (!q) return;

    appendUserMessage(q);
    if (chatTitle) chatTitle.textContent = q;

    await sendToBackend(q);

    chatInput.value = "";
  });
}