// 더미 데이터 (프론트 전용)
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
  "현대차": {
    code: "005380",
    price: "212,500",
    diff: { sign: "-", text: "-1,500 (-0.70%)" },
    prev: "214,000",
    open: "213,500",
    high: "215,500",
    low: "211,000",
    volume: "4,320,000",
    value: "590,300",
  },
  "LG화학": {
    code: "051910",
    price: "501,000",
    diff: { sign: "+", text: "+6,000 (+1.21%)" },
    prev: "495,000",
    open: "498,000",
    high: "503,000",
    low: "494,500",
    volume: "780,200",
    value: "393,000",
  },
};

// 투자자/외국인 더미
const INVESTOR_DATA = {
  broker: [
    ["미래에셋증권", "6,147,541", "4,925,367"],
    ["삼성증권", "1,547,200", "1,125,000"],
    ["키움증권", "980,300", "720,000"],
    ["한국투자", "870,000", "650,000"],
    ["NH투자증권", "640,000", "520,000"],
  ],
  foreigner: [
    ["외국인 순매수", "3,420,000", "—"],
    ["기관 순매수", "1,120,000", "—"],
    ["연기금", "420,000", "—"],
    ["프로그램", "210,000", "—"],
  ],
};

// 드롭다운에 따른 위쪽 패널 제목
const PANEL_PRESETS = {
  bs: ["자산총계", "부채총계", "자본총계"],
  is: ["매출액", "영업이익", "당기순이익"],
  cf: ["영업활동현금흐름", "투자활동현금흐름", "재무활동현금흐름"],
};

// 드롭다운에 따른 표(왼쪽 열) 라벨
const METRIC_LABELS = {
  bs: [
    "자산총계",
    "유동자산",
    "비유동자산",
    "부채총계",
    "유동부채",
    "비유동부채",
    "자본총계",
    "자본금",
    "이익잉여금",
    "기타포괄손익",
    "자본조정",
    "소수주주지분",
  ],
  is: [
    "매출액",
    "매출원가",
    "매출총이익",
    "판매관리비",
    "영업이익",
    "영업외수익",
    "법인세비용차감전이익",
    "법인세",
    "당기순이익",
    "총포괄이익",
    "주당순이익(EPS)",
    "기타",
  ],
  cf: [
    "영업활동현금흐름",
    "당기순이익",
    "감가상각비",
    "투자활동현금흐름",
    "유형자산취득",
    "재무활동현금흐름",
    "배당금지급",
    "차입금변동",
    "현금및현금성자산증가",
    "기초현금",
    "기말현금",
    "기타",
  ],
};

// util: 쿼리 파라미터
function getQuery(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}

// 페이지 로드
document.addEventListener("DOMContentLoaded", () => {
  const q = getQuery("q");
  const co = q && COMPANY_DATA[q] ? COMPANY_DATA[q] : COMPANY_DATA["삼성전자"];
  const coName = q || "삼성전자";

  // 기본 회사 정보 그리기
  renderCompany(co, coName);

  // 검색 => 다른 회사로 이동
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
      // 버튼 텍스트 바꾸기
      btn.childNodes[0].nodeValue = type === "broker" ? "거래원 정보" : "외국인 거래현황";
      investorDropdown.classList.remove("open");
    });

    // 초기값
    fillInvestorTable("broker");
  }

  // info 드롭다운 (재무상태표 / 손익계산서 / 현금흐름표)
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
      applyInfoType(type, coName); // 여기서 패널 + 제목 + row 라벨 다 바꿈
      btn.childNodes[0].nodeValue =
        type === "bs" ? "재무상태표" : type === "is" ? "손익계산서" : "현금흐름표";
      infoDropdown.classList.remove("open");
    });

    // 페이지 처음 열릴 때도 한 번 적용해두기 (기본 bs)
    applyInfoType("bs", coName);
  }

  // 연도 버튼
  document.querySelectorAll(".year-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".year-chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const year = btn.dataset.year;
      showYear(year);
    });
  });
});

// 회사 데이터 뿌리기
function renderCompany(co, nameLabel) {
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
  if (financeTitle) financeTitle.textContent = `${nameLabel}의 재무상태표`;
}

// 투자자 테이블 채우기
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
    INVESTOR_DATA.broker.forEach((row) => {
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
    INVESTOR_DATA.foreigner.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row[0]}</td><td>${row[1]}</td><td colspan="2">${
        row[2] ?? ""
      }</td>`;
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
  }
}

// 정보 드롭다운 바뀔 때 아래 패널, 제목, 표 라벨까지 다 바꾸기
function applyInfoType(type, coName) {
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
        : `${coName}의 현금흐름표`;
  }

  // ✅ 왼쪽 표 라벨도 같이 바꾸기
  updateMetricNames(type);
}

// 왼쪽 열 라벨 갈아끼우기
function updateMetricNames(type) {
  const labels = METRIC_LABELS[type] || METRIC_LABELS.bs;
  const pills = document.querySelectorAll(".metric-col .metric-pill");
  pills.forEach((el, idx) => {
    if (labels[idx]) {
      el.textContent = labels[idx];
    } else {
      el.textContent = "";
    }
  });
}

// 연도 보여줄 때는 단순히 active만 바꿈 (여러 값 세트면 여기서 바꿔)
function showYear(year) {
  document.querySelectorAll(".year-col").forEach((col) => {
    col.style.opacity = col.dataset.year === year ? "1" : "0.35";
  });
}