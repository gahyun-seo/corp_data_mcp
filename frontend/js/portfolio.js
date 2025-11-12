// =========================
// 1) 그래프 슬라이더 + 제목 변경 (기존 유지)
// =========================
const slides = document.querySelectorAll(".chart-slide");
const dots = document.querySelectorAll(".chart-status .dot");
const prevBtn = document.querySelector(".chart-prev");
const nextBtn = document.querySelector(".chart-next");
const chartTitle = document.querySelector(".chart-tab");

const chartTitles = [
  "Portfolio Weights",
  "Sharpe / Volatility / Return",
];

let currentSlide = 0;

function showSlide(index) {
  slides.forEach((slide, i) => slide.classList.toggle("active", i === index));
  dots.forEach((dot, i) => dot.classList.toggle("active", i === index));
  if (chartTitle && chartTitles[index]) chartTitle.textContent = chartTitles[index];
  currentSlide = index;
}
showSlide(0);

if (prevBtn) {
  prevBtn.addEventListener("click", () => {
    const next = (currentSlide - 1 + slides.length) % slides.length;
    showSlide(next);
  });
}
if (nextBtn) {
  nextBtn.addEventListener("click", () => {
    const next = (currentSlide + 1) % slides.length;
    showSlide(next);
  });
}
dots.forEach((dot) => {
  dot.addEventListener("click", () => showSlide(Number(dot.dataset.index)));
});

// =========================
// 2) 드롭다운 (기존 유지)
// =========================
const dropdownButtons = document.querySelectorAll(".select-pill");
dropdownButtons.forEach((btn) => {
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const targetId = btn.getAttribute("data-dropdown-target");
    const list = document.getElementById(targetId);
    const isOpen = list && list.style.display === "block";
    document.querySelectorAll(".select-list").forEach((ul) => (ul.style.display = "none"));
    if (list) list.style.display = isOpen ? "none" : "block";
  });
});
document.querySelectorAll(".select-list li").forEach((item) => {
  item.addEventListener("click", () => {
    const value = item.dataset.value;
    const parentList = item.parentElement;
    const btn = document.querySelector(`[data-dropdown-target="${parentList.id}"]`);
    if (btn) {
      const textNode = btn.childNodes[0];
      if (textNode) textNode.textContent = value + " ";
    }
    parentList.style.display = "none";
  });
});
document.addEventListener("click", () => {
  document.querySelectorAll(".select-list").forEach((ul) => (ul.style.display = "none"));
});

// =========================
// 3) API 연결 + 테이블 렌더링
// =========================
const API_BASE = "http://127.0.0.1:8000";

const companiesWrap = document.getElementById("companies-wrap");
const addStockForm = document.getElementById("add-stock-form");
const stockInput = document.getElementById("stock-input");

const selectedCodes = new Set();   // 현재 추가된 종목 코드
const companyCache  = new Map();   // code -> /api/stocks 응답

// (핵심) 좌측 버튼에서 '표시 라벨 → 데이터 키' 매핑
const labelToKey = {
  "주가정보": "overview",
  "시가총액 (백만원)": "market_cap",
  "상장주식수": "listed_shares",
  "거래량": "volume",
  "거래대금": "trading_value",
  "전일대비": "change_price",
  "등락률(%)": "change_rate",
  "PER": "per",
  "PBR": "pbr",
  "EPS": "eps",
  "BPS": "bps",
  "배당수익률(%)": "div_yield",
  // (주의) 재무제표 항목(매출/영업이익/ROE/부채비율 등)은 현재 API에 없음 → "-"로 표시됨
};

// 좌측 버튼에서 '표시 순서'와 '키'를 추출 (data-key 있으면 우선 사용)
function getMetricKeysInOrder() {
  const metricBtns = document.querySelectorAll(".metrics-col .metric-btn");
  const keys = [];
  metricBtns.forEach((btn, i) => {
    const explicit = btn.dataset.key && btn.dataset.key.trim();
    if (explicit) {
      keys.push(explicit);
    } else {
      const label = (btn.textContent || "").trim();
      keys.push(labelToKey[label] || "__unknown__");
    }
  });
  return keys;
}

// 숫자 포맷터 보강
const fmtInt = (v) => (v === null || v === undefined || v === "" ? "-" : Number(v).toLocaleString("ko-KR"));
const fmtPct = (v) => (v === null || v === undefined || v === "" || isNaN(v) ? "-" : (Number(v)).toFixed(2) + "%");

async function fetchStockByCode(code) {
  const res = await fetch(`${API_BASE}/api/stocks/${code}`);
  if (!res.ok) throw new Error(`종목 ${code} 조회 실패 (${res.status})`);
  return res.json();
}
// ■ 시가총액: '백만원' 단위로 표시 (예: 1,234,567,890 → 1,234,568 백만원)
function fmtMWon(v) {
  if (v === null || v === undefined || v === "" || isNaN(v)) return "-";
  const mwon = Math.round(Number(v) / 1_000_000);
  return mwon.toLocaleString("ko-KR");
}

// ■ 소수 2자리 고정 (PBR 등)
function fmtFixed2(v) {
  if (v === null || v === undefined || v === "" || isNaN(v)) return "-";
  return Number(v).toFixed(2);
}

const fmtSigned = (v, digits = 2, suffix = "") => {
  if (v === null || v === undefined || v === "" || isNaN(v)) return "-";
  const num = Number(v);
  const sign = num > 0 ? "+" : num < 0 ? "−" : "";
  return sign + Math.abs(num).toFixed(digits) + suffix;
};


// 값 포맷터
function valueOfKey(key, cd) {
  switch (key) {
    case "close_price":    return fmtInt(cd.close_price);
    case "market_cap":     return fmtMWon(cd.market_cap);
    case "listed_shares":  return fmtInt(cd.listed_shares);
    case "volume":         return fmtInt(cd.volume);
    case "trading_value":  return fmtInt(cd.trading_value);
    case "change_price":   return fmtSigned(cd.change_price, 0, "");
    case "change_rate":    return fmtSigned(cd.change_rate, 2, "%");
    case "per":            return (cd.per ?? "-");
    case "pbr":            return cd.pbr == null ? "-" : fmtFixed2(cd.pbr);   // ← 소수 2자리
    case "eps":            return cd.eps == null ? "-" : fmtInt(cd.eps);      // ← 콤마
    case "bps":            return cd.bps == null ? "-" : fmtInt(cd.bps);      // ← 콤마
    case "div_yield":      return (cd.div_yield == null ? "-" : fmtPct(cd.div_yield));
    default:               return "-"; // API에 없는 항목(재무제표 등)은 "-" 처리
  }
}

// 회사 한 컬럼 생성 (API 응답 → DOM)
function createCompanyColFromAPI(resp) {
  const col = document.createElement("div");
  col.className = "company-col";

  // 헤더(회사명)
  const head = document.createElement("div");
  head.className = "company-head";
  const cname = resp.stock_name || resp.stock_code || "";
  head.textContent = cname || "";
  col.appendChild(head);

  // 각 지표 칸 채우기: 첫 줄은 헤더가 차지하므로 2번째 버튼부터 셀 생성
  const keys = getMetricKeysInOrder();
  const cd = resp.current_data || {};
  keys.forEach((key, idx) => {
    if (idx === 0) return; // 첫 줄은 헤더와 정렬
    const cell = document.createElement("div");
    cell.className = "company-cell";
    cell.textContent = valueOfKey(key, cd);
    col.appendChild(cell);
  });

  return col;
}

// 더미 로직 전면 OFF (※ 기존 더미 add/remove 전부 삭제)
// - 초기 삼성전자 4개 추가, dummyValue, createCompanyCol 등 모두 제거했습니다.

// =========================
// 4) 포트폴리오 최적화 (선택된 종목들 기반)
// =========================
let optimizeBtn = document.getElementById("optimize-btn");
// 없으면 자동으로 하나 만들어 붙여줌 (UX 편의)
if (!optimizeBtn) {
  const controls = document.querySelector(".portfolio-controls");
  if (controls) {
    const block = document.createElement("div");
    block.className = "control-block";
    block.innerHTML = `
      <p class="control-label">포트폴리오를<br/>최적화하세요:</p>
      <button id="optimize-btn" class="select-pill">최적화 실행</button>
    `;
    controls.appendChild(block);
    optimizeBtn = block.querySelector("#optimize-btn");
  }
}

async function callOptimize() {
  if (selectedCodes.size < 2) {
    alert("최소 2개 종목이 필요합니다.");
    return null;
  }
  const body = {
    stock_codes: Array.from(selectedCodes),
    days: 252
  };
  const res = await fetch(`${API_BASE}/api/portfolio/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(`최적화 실패: ${msg}`);
  }
  return res.json();
}

if (optimizeBtn) {
  optimizeBtn.addEventListener("click", async () => {
    console.log("[optimize] clicked. selectedCodes=", Array.from(selectedCodes));
    try {
      const result = await callOptimize();
      if (!result) return;

      // 에이전트 패널 업데이트
      const title = document.querySelector(".agent-title");
      const highlight = document.querySelector(".agent-highlight");
      const body = document.querySelector(".agent-body");


      // if (title) title.textContent = "Your Agent Says:";
      // if (highlight) {
      //   highlight.textContent =
      //     `샤프 ${Number(result.sharpe_ratio).toFixed(2)}, 기대수익률 ${(Number(result.expected_return)*100).toFixed(2)}%, 변동성 ${(Number(result.volatility)*100).toFixed(2)}%`;
      // }
      // if (body && Array.isArray(result.stock_codes) && Array.isArray(result.weights_percent)) {
      //   const pairs = result.stock_codes.map((c, i) => `${c}: ${Number(result.weights_percent[i]).toFixed(2)}%`);
      //   body.textContent = `권장 비중 — ${pairs.join(" · ")}`;
      // }
      renderWeightsChart(result);
      renderStatsChart(result);
    } catch (err) {
      alert(err.message);
    }
  });
}

// =========================
// 5. 회사명/코드 자동완성
// =========================
const suggestEl = document.getElementById("search-suggest");
let suggestData = [];
let suggestIndex = -1;
let debounceTimer = null;

function clearSuggest() {
  suggestData = [];
  suggestIndex = -1;
  if (suggestEl) {
    suggestEl.innerHTML = "";
    suggestEl.classList.remove("show"); 
  }
}

function renderSuggest(items) {
  if (!suggestEl) return;
  suggestEl.innerHTML = "";
  if (!items || items.length === 0) {
    suggestEl.classList.remove("show"); 
    return;
  }

  items.forEach((it, idx) => {
    const li = document.createElement("li");
    li.className = "suggest-item";
    li.textContent = `${it.stock_name} (${it.stock_code}) · ${it.market}`;
    li.addEventListener("click", async () => {
      await addByCode(it.stock_code);
      clearSuggest();
      stockInput.value = "";
    });
    suggestEl.appendChild(li);
  });

  suggestEl.classList.add("show");

  stockInput.addEventListener("blur", () => {
  // 클릭 선택을 위해 약간 지연 후 닫기
  setTimeout(() => clearSuggest(), 120);
});

}

// 코드 추가 공통 함수
async function addByCode(code) {
  try {
    const data = await fetchStockByCode(code);
    if (selectedCodes.has(data.stock_code)) {
      alert("이미 추가된 종목입니다.");
      return;
    }
    selectedCodes.add(data.stock_code);
    companyCache.set(data.stock_code, data);
    companiesWrap.appendChild(createCompanyColFromAPI(data));
    companiesWrap.scrollLeft = companiesWrap.scrollWidth;
  } catch (err) {
    alert(err.message);
  }
}

async function fetchLookup(q) {
  const url = `${API_BASE}/api/stocks/lookup?q=${encodeURIComponent(q)}&limit=8`;
  const res = await fetch(url);
  if (!res.ok) return [];
  const js = await res.json();
  return js.results || [];
}

if (stockInput) {
  stockInput.addEventListener("input", () => {
    const q = stockInput.value.trim();
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      // 6자리 숫자면 바로 끝 (자동완성 불필요)
      if (/^\d{6}$/.test(q)) { clearSuggest(); return; }
      if (q.length < 1) { clearSuggest(); return; }
      try {
        const items = await fetchLookup(q);
        suggestData = items;
        renderSuggest(items);
      } catch {
        clearSuggest();
      }
    }, 200);
  });

  // Enter: 6자리면 바로 추가, 아니면 제안 1개 있으면 첫 번째 추가
  stockInput.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const q = stockInput.value.trim();
      if (/^\d{6}$/.test(q)) {
        await addByCode(q);
        stockInput.value = "";
        clearSuggest();
        return;
      }
      if (suggestData.length > 0) {
        await addByCode(suggestData[0].stock_code);
        stockInput.value = "";
        clearSuggest();
      }
    }
    // ESC: 제안 닫기
    if (e.key === "Escape") {
      clearSuggest();
    }
  });
}

// 제출 버튼은 여전히 코드/이름 모두 지원
if (addStockForm && stockInput && companiesWrap) {
  addStockForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = stockInput.value.trim();
    if (!q) return;

    try {
      if (/^\d{6}$/.test(q)) {
        await addByCode(q);
      } else {
        const items = await fetchLookup(q);
        if (items.length === 0) {
          alert("검색 결과가 없습니다.");
        } else {
          await addByCode(items[0].stock_code);
        }
      }
    } finally {
      stockInput.value = "";
      clearSuggest();
    }
  });
}

// 전역 차트 핸들러
let weightsChart = null;
let statsChart = null;

function toPercentWeights(result) {
  // weights_percent가 있으면 사용, 없으면 weights→%로 변환
  if (Array.isArray(result.weights_percent)) return result.weights_percent.map(Number);
  if (Array.isArray(result.weights)) return result.weights.map(w => Number(w) * 100);
  return [];
}

function getLabels(result) {
  if (Array.isArray(result.stock_names) && result.stock_names.length) return result.stock_names;
  if (Array.isArray(result.stock_codes)) return result.stock_codes;
  return [];
}

// 종목 비중 바차트
function renderWeightsChart(result) {
  const ctx = document.getElementById("weightsChart")?.getContext("2d");
  if (!ctx) return;

  // 기존 인스턴스 제거(덮어그리기 방지)
  if (weightsChart) { weightsChart.destroy(); }

  const labels = getLabels(result);
  const data = toPercentWeights(result);

  weightsChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Weight (%)",
        data,
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "rgba(255,255,255,0.85)" } },
        tooltip: {
          callbacks: { label: (ctx) => `${ctx.parsed.y.toFixed(2)}%` }
        }
      },
      scales: {
        x: {
          ticks: { color: "rgba(255,255,255,0.8)" },
          grid: { color: "rgba(255,255,255,0.06)" }
        },
        y: {
          beginAtZero: true,
          ticks: {
            color: "rgba(255,255,255,0.8)",
            callback: v => v + "%"
          },
          grid: { color: "rgba(255,255,255,0.06)" }
        }
      }
    }
  });
}

function renderStatsChart(result) {
  const ctx = document.getElementById("statsChart")?.getContext("2d");
  if (!ctx) return;

  if (statsChart) { statsChart.destroy(); }

  const ret = Number(result.expected_return) * 100;   // %
  const vol = Number(result.volatility) * 100;        // %
  const sh  = Number(result.sharpe_ratio);            // 단위 없음

  statsChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["Expected Return", "Volatility", "Sharpe"],
      datasets: [
        {
          label: "Return / Volatility (%)",
          data: [ret, vol, null],
          borderWidth: 1,
          yAxisID: "y"
        },
        {
          label: "Sharpe",
          data: [null, null, sh],
          borderWidth: 1,
          yAxisID: "y1"
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "rgba(255,255,255,0.85)" } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const label = ctx.dataset.label || "";
              const v = ctx.parsed.y;
              if (ctx.dataset.yAxisID === "y") return `${label}: ${v.toFixed(2)}%`;
              return `${label}: ${v.toFixed(2)}`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: { color: "rgba(255,255,255,0.8)" },
          grid: { color: "rgba(255,255,255,0.06)" }
        },
        y: {  // % 축
          beginAtZero: true,
          ticks: {
            color: "rgba(255,255,255,0.8)",
            callback: v => v + "%"
          },
          grid: { color: "rgba(255,255,255,0.06)" }
        },
        y1: { // 샤프 축
          position: "right",
          beginAtZero: true,
          ticks: { color: "rgba(255,255,255,0.8)" },
          grid: { drawOnChartArea: false }
        }
      }
    }
  });
}