// finance_search.js

const API_BASE = "http://127.0.0.1:8000";

// 기본으로 보여줄 종목 코드들 (KOSPI 대표 몇 개)
const DEFAULT_CODES = [
  "005930", // 삼성전자
  "051910", // LG화학
  "000660", // SK하이닉스
  "005380", // 현대차
  "035720", // 카카오
  "005490", // POSCO홀딩스
  "329180",
  "012450",
  "000270",
  "068270",
  "402340",
  "035420",
];

// 카드가 붙을 영역 & 디테일 페이지 경로
const tickerEl = document.getElementById("fs-ticker");
const DETAIL_PAGE = "company_detail.html";

// ----- 공통 포맷터 -----
const money = (v) =>
  v == null || v === ""
    ? "-"
    : Number(v).toLocaleString("ko-KR");

const pct = (v) =>
  v == null || isNaN(v)
    ? "-"
    : Number(v).toFixed(2) + "%";

// ----- 미니 차트용 헬퍼 함수들 -----

// history_data에서 종가 배열 뽑기
function extractCloses(history) {
  if (!Array.isArray(history)) return [];
  const closes = history
    .map((row) => {
      // history_data에는 보통 "close" 컬럼이 들어 있음
      if (row.close != null) return Number(row.close);
      if (row.close_price != null) return Number(row.close_price);
      return null;
    })
    .filter((v) => v != null && !isNaN(v));
  // 마지막 30개만 사용
  const N = 30;
  return closes.slice(-N);
}

// 0~1로 정규화
function normalize(values) {
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max === min) return values.map(() => 0.5); // 전부 같으면 가운데 직선
  return values.map((v) => (v - min) / (max - min));
}

// SVG path 문자열 만들기
function buildSparklineSvg(prices, isMinus) {
  const svgNS = "http://www.w3.org/2000/svg";
  const w = 120;
  const h = 40;
  const padding = 4;

  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("class", "fs-card-graph");
  svg.setAttribute("width", w);
  svg.setAttribute("height", h);
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const step = (w - 2 * padding) / (prices.length - 1);

  let d = "";
  prices.forEach((p, i) => {
    const x = padding + i * step;
    const y = h - padding - ((p - min) / span) * (h - 2 * padding);
    d += (i === 0 ? "M" : "L") + x + " " + y + " ";
  });

  const path = document.createElementNS(svgNS, "path");
  path.setAttribute("d", d.trim());
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", isMinus ? "#00D23F" : "#FB781B");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("stroke-linecap", "round");

  svg.appendChild(path);
  return svg;
}

// 실제로 SVG 미니 그래프 그리기
function renderMiniChart(parentEl, values) {
  if (!values || values.length < 2) return;

  const width = 120;
  const height = 40;

  const norm = normalize(values);
  const d = buildSparkPath(norm, width, height);

  if (!d) return;

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  // ✅ 여기 className을 fs-card-graph 로 설정 (기존 CSS 사용)
  svg.setAttribute("class", "fs-card-graph");
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const path = document.createElementNS(svgNS, "path");
  path.setAttribute("d", d);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke-width", "2");

  svg.appendChild(path);
  parentEl.appendChild(svg);
}

// ----- 백엔드에서 주가 카드용 데이터 가져오기 -----
async function loadCardByCode(code) {
  try {
    const res = await fetch(`${API_BASE}/api/stocks/${code}`);
    if (!res.ok) {
      console.warn("loadCardByCode error:", code, res.status);
      return null;
    }
    const js = await res.json();
    const cd = js.current_data || {};
    const history = js.history_data || [];

    const name = js.stock_name || code;
    const dateRaw = cd.date || "";
    const dateText =
      dateRaw.replace(/(\d{4})(\d{2})(\d{2})/, "$1.$2.$3") + " 기준";

    const closePrice = cd.close_price;
    const changePrice = cd.change_price ?? 0;
    const changeRate = cd.change_rate;

    const sign = changePrice >= 0 ? "+" : "-";
    const absChange = Math.abs(changePrice || 0);

    const changeText = `${sign}${money(absChange)} (${pct(changeRate)})`;

    // 히스토리에서 종가 데이터 뽑아서 스파크라인용으로 같이 넘겨줌
    const sparkValues = extractCloses(history);

    return {
      name,
      time: dateText,
      price: money(closePrice),
      change: changeText,
      up: changePrice >= 0,
      code: js.stock_code,
      spark: sparkValues,
    };
  } catch (e) {
    console.warn("loadCardByCode exception:", code, e);
    return null;
  }
}

// ----- 카드 DOM 생성 -----
function createCard(c) {
  const card = document.createElement("div");
  card.className = "fs-card";

  // up 여부가 있으면 그걸 쓰고, 없으면 문자열 기준으로 판단
  const isMinus =
    typeof c.up === "boolean"
      ? !c.up
      : c.change.trim().indexOf("-") === 0;

  const changeColor = isMinus ? "#00D23F" : "#FB781B"; // -면 초록, +면 주황
  const arrow = isMinus ? "▼" : "▲";

  // 기존 구조 유지 + 비어있는 svg 자리 하나 만들어 둠
  card.innerHTML =
    '<div class="fs-card-bg"></div>' +
    '<div class="fs-card-time">' + c.time + '</div>' +
    '<div class="fs-card-name" style="left:19.43px;top:34.98px;">' + c.name + '</div>' +
    '<div class="fs-card-price">' + c.price + '</div>' +
    '<div class="fs-card-change" style="color:' + changeColor + ';">' +
      arrow + ' ' + c.change +
    '</div>' +
    // 🔹 여기 원래 이미지가 들어가던 자리
    '<svg class="fs-card-graph"></svg>';

  card.dataset.name = c.name;
  card.dataset.code = c.code || "";

  // 🔹 방금 만든 빈 svg를 실제 sparkline svg로 교체
  const placeholderSvg = card.querySelector(".fs-card-graph");
  if (placeholderSvg && Array.isArray(c.spark) && c.spark.length > 1) {
    const realSvg = buildSparklineSvg(c.spark, isMinus);
    placeholderSvg.replaceWith(realSvg);
  }

  // 카드 클릭하면 해당 종목 디테일로 이동
  card.addEventListener("click", () => {
    const q = card.dataset.name || card.dataset.code || "삼성전자";
    window.location.href = `${DETAIL_PAGE}?q=${encodeURIComponent(q)}`;
  });

  return card;
}

// ----- 기본 카드들 렌더링 (실데이터) -----
(async function mountDefaultCards() {
  if (!tickerEl) return;

  // 백엔드에서 대표 종목들 로딩
  const items = await Promise.all(
    DEFAULT_CODES.map((code) => loadCardByCode(code))
  );
  const valid = items.filter(Boolean);

  // 실패해서 아무것도 없으면 그냥 종료
  if (valid.length === 0) return;

  // 무한 느낌 나게 두 번 붙이기
  for (let i = 0; i < 2; i++) {
    valid.forEach((c) => {
      tickerEl.appendChild(createCard(c));
    });
  }
})();

// ----- 검색 -> 디테일 페이지로 이동 -----
const fsForm = document.getElementById("fs-search-form");
const fsInput = document.getElementById("fs-search-input");

if (fsForm && fsInput) {
  fsForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = fsInput.value.trim();
    if (!q) return;
    // 여기서 q는 회사명 또는 종목코드. company_detail.js에서 resolveToCode로 처리.
    window.location.href = `${DETAIL_PAGE}?q=${encodeURIComponent(q)}`;
  });
}