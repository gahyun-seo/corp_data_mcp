// company_detail.js (요약연결재무정보 선택 가능 버전)

const API_BASE = "http://127.0.0.1:8000";

// 상단 더미(주가 영역) – 지금 하는 재무랑 별개
const COMPANY_DATA = {
  "삼성전자": {
    code: "005930",
    price: "100,300",
    diff: { sign: "-", text: "-4,300 (-4.10%)" },
    prev: "104,900",
    open: "103,500",
    high: "103,800",
    low: "96,700",
    volume: "36,942,796",
    value: "3,696,550",
  },
  "SK하이닉스": {
    code: "000660",
    price: "144,000",
    diff: { sign: "+", text: "+3,200 (+2.27%)" },
    prev: "140,800",
    open: "142,000",
    high: "146,000",
    low: "141,500",
    volume: "12,842,100",
    value: "1,240,500",
  },
};

// 위쪽 패널 제목 프리셋
const PANEL_PRESETS = {
  bs: ["자산총계", "부채총계", "자본총계"],
  is: ["매출액", "영업이익", "당기순이익"],
  cf: ["영업활동현금흐름", "투자활동현금흐름", "재무활동현금흐름"],
  // ✅ 요약연결재무정보일 때는 대표 3개만
  all: ["자산총계", "부채총계", "자본총계"],
};

// 백엔드 -> 프런트 테이블 이름 매핑
const TABLE_NAME_BY_VIEW = {
  bs: "연결재무상태표",
  is: "연결포괄손익계산서",
  cf: "연결현금흐름표",
  all: "요약연결재무정보", // ✅ 이거 이미 네가 써놨던 거 살림
};

let CURRENT_FINANCE = null;
let CURRENT_VIEW_TYPE = "bs";

// 숫자 3자리 콤마
function formatNumber(val) {
  if (val === null || val === undefined || val === "") return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return val;
  return n.toLocaleString("ko-KR");
}

// 쿼리스트링 가져오기
function getQuery(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}

// 상단 회사 정보
function renderCompanyHeader(co, nameLabel) {
  const nameEl = document.getElementById("co-name");
  const codeEl = document.getElementById("co-code");
  const priceEl = document.getElementById("current-price");
  const diffEl = document.getElementById("price-change");
  const prevEl = document.getElementById("prev-close");
  const openEl = document.getElementById("open-price");
  const highEl = document.getElementById("high-price");
  const lowEl = document.getElementById("low-price");
  const volEl = document.getElementById("volume");
  const valEl = document.getElementById("value");
  const financeTitle = document.getElementById("finance-title");

  if (nameEl) nameEl.textContent = nameLabel;
  if (codeEl) codeEl.textContent = co.code;
  if (priceEl) priceEl.textContent = co.price;
  if (diffEl) {
    diffEl.textContent = `${co.diff.sign === "-" ? "▼" : "▲"} ${co.diff.text}`;
    diffEl.classList.remove("down", "up");
    diffEl.classList.add(co.diff.sign === "-" ? "down" : "up");
  }
  if (prevEl) prevEl.textContent = co.prev;
  if (openEl) openEl.textContent = co.open;
  if (highEl) highEl.textContent = co.high;
  if (lowEl) lowEl.textContent = co.low;
  if (volEl) volEl.textContent = co.volume;
  if (valEl) valEl.textContent = co.value;

  // 기본은 재무상태표
  if (financeTitle) financeTitle.textContent = `${nameLabel}의 재무상태표`;
}

// 투자자 표 (더미)
function fillInvestorTable(type) {
  const table = document.getElementById("investor-table");
  const title = document.getElementById("investor-title");
  if (!table) return;
  table.innerHTML = "";

  if (type === "broker") {
    title.textContent = "투자자별 매매동향";
    const thead = document.createElement("thead");
    thead.innerHTML =
      "<tr><th>매도 상위</th><th>거래량</th><th>매수 상위</th><th>거래량</th></tr>";
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    [
      ["미래에셋증권", "6,147,541", "4,925,367"],
      ["삼성증권", "1,547,200", "1,125,000"],
      ["키움증권", "980,300", "720,000"],
      ["한국투자", "870,000", "650,000"],
      ["NH투자증권", "640,000", "520,000"],
    ].forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row[0]}</td><td>${row[1]}</td><td>${row[0]}</td><td>${row[2]}</td>`;
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
  } else {
    title.textContent = "외국인 거래현황";
    const thead = document.createElement("thead");
    thead.innerHTML = "<tr><th>구분</th><th>거래량</th><th colspan='2'>비고</th></tr>";
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    [
      ["외국인 순매수", "3,420,000", "—"],
      ["기관 순매수", "1,120,000", "—"],
      ["연기금", "420,000", "—"],
      ["프로그램", "210,000", "—"],
    ].forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row[0]}</td><td>${row[1]}</td><td colspan="2">${
        row[2] ?? ""
      }</td>`;
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
  }
}

// 실제로 그리드 그리기
function renderFinanceTable(viewType) {
  if (!CURRENT_FINANCE) return;

  const tableName = TABLE_NAME_BY_VIEW[viewType];
  const rows = (CURRENT_FINANCE.tables && CURRENT_FINANCE.tables[tableName]) || [];

  console.log(`[finance] table=${tableName}`, rows);

  const grid = document.getElementById("finance-grid");
  if (!grid) return;
  grid.innerHTML = "";

  // 왼쪽 항목
  const metricCol = document.createElement("div");
  metricCol.className = "metric-col";
  rows.forEach((row) => {
    const span = document.createElement("span");
    span.className = "metric-pill";
    span.textContent = row.name || "";
    metricCol.appendChild(span);
  });
  grid.appendChild(metricCol);

  // 연도 열 4개 고정 (앞의 설명처럼 2025=current, 2024=previous)
  const years = ["2022", "2023", "2024", "2025"];
  years.forEach((year) => {
    const col = document.createElement("div");
    col.className = "year-col";
    col.dataset.year = year;

    rows.forEach((row) => {
      const v = document.createElement("span");
      v.className = "val-pill";
      if (year === "2025") {
        v.textContent = formatNumber(row.current);
      } else if (year === "2024") {
        v.textContent = formatNumber(row.previous);
      } else {
        v.textContent = "-";
      }
      col.appendChild(v);
    });

    grid.appendChild(col);
  });
}

// 드롭다운에서 타입 바꼈을 때
function applyInfoType(type, coName) {
  CURRENT_VIEW_TYPE = type;

  const titles = PANEL_PRESETS[type] || PANEL_PRESETS.bs;
  const p1 = document.getElementById("panel-title-1");
  const p2 = document.getElementById("panel-title-2");
  const p3 = document.getElementById("panel-title-3");
  if (p1) p1.textContent = titles[0];
  if (p2) p2.textContent = titles[1];
  if (p3) p3.textContent = titles[2];

  const financeTitle = document.getElementById("finance-title");
  if (financeTitle) {
    financeTitle.textContent =
      type === "bs"
        ? `${coName}의 재무상태표`
        : type === "is"
        ? `${coName}의 손익계산서`
        : type === "cf"
        ? `${coName}의 현금흐름표`
        : `${coName}의 요약재무정보`; // ✅ all일 때
  }

  renderFinanceTable(type);
}

// 연도 칩 – 지금은 모두 1로 둔 상태 (애니메이션 끈 버전)
function showYear(year) {
  document.querySelectorAll(".year-col").forEach((col) => {
    col.style.opacity = col.dataset.year === year ? "1" : "1";
  });
}

// 로드
document.addEventListener("DOMContentLoaded", async () => {
  const q = getQuery("q");
  const co = q && COMPANY_DATA[q] ? COMPANY_DATA[q] : COMPANY_DATA["삼성전자"];
  const coName = q || "삼성전자";

  renderCompanyHeader(co, coName);

  // 검색 폼
  const form = document.getElementById("detail-search-form");
  const input = document.getElementById("detail-search-input");
  if (form && input) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) return;
      window.location.href = `company_detail.html?q=${encodeURIComponent(v)}`;
    });
  }

  // 투자자 드롭다운
  const investorDropdown = document.getElementById("investor-dropdown");
  if (investorDropdown) {
    const btn = investorDropdown.querySelector(".dropdown-btn");
    const list = investorDropdown.querySelector(".dropdown-list");

    btn.addEventListener("click", () => {
      investorDropdown.classList.toggle("open");
    });

    list.addEventListener("click", (e) => {
      const li = e.target.closest("li");
      if (!li) return;
      const type = li.dataset.type;
      fillInvestorTable(type);
      btn.childNodes[0].nodeValue =
        type === "broker" ? "거래원 정보" : "외국인 거래현황";
      investorDropdown.classList.remove("open");
    });

    fillInvestorTable("broker");
  }

  // 백엔드에서 재무 가져오기
  try {
    const resp = await fetch(`${API_BASE}/finance/${co.code}`);
    if (resp.ok) {
      CURRENT_FINANCE = await resp.json();
      console.log("[finance] loaded", CURRENT_FINANCE);
    } else {
      console.warn("finance api not ok", resp.status);
      CURRENT_FINANCE = null;
    }
  } catch (err) {
    console.warn("finance api error", err);
    CURRENT_FINANCE = null;
  }

  // info 드롭다운
  const infoDropdown = document.getElementById("info-dropdown");
  if (infoDropdown) {
    const btn = infoDropdown.querySelector(".dropdown-btn-dark");
    const list = infoDropdown.querySelector(".dropdown-list");

    btn.addEventListener("click", () => {
      infoDropdown.classList.toggle("open");
    });

    list.addEventListener("click", (e) => {
      const li = e.target.closest("li");
      if (!li) return;
      const type = li.dataset.type;
      applyInfoType(type, coName);
      // 버튼 라벨도 바꿔주기
      btn.childNodes[0].nodeValue =
        type === "bs"
          ? "재무상태표"
          : type === "is"
          ? "손익계산서"
          : type === "cf"
          ? "현금흐름표"
          : "요약재무정보";
      infoDropdown.classList.remove("open");
    });
  }

  // 처음엔 재무상태표
  applyInfoType("bs", coName);
});