// company_detail.js (지표 패널 + 재무테이블 모두 유지 버전)

const API_BASE = "http://127.0.0.1:8000";

// 상단 더미(주가 영역) – lookup/stock API 실패 시에만 fallback 용
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

// ===== 공용 포맷터 =====
const money = (v) =>
  v == null || v === "" ? "-" : Number(v).toLocaleString("ko-KR");
const pct = (v) =>
  v == null || v === "" || isNaN(v) ? "-" : Number(v).toFixed(2) + "%";

// 쿼리스트링 가져오기
function getQuery(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}

// 이름 또는 코드 → 6자리 코드 해석
async function resolveToCode(nameOrCode) {
  const s = (nameOrCode || "").trim();
  if (/^\d{6}$/.test(s)) return s; // 이미 코드 형태면 그대로

  const r = await fetch(
    `${API_BASE}/api/stocks/lookup?q=${encodeURIComponent(s)}&limit=1`
  );
  if (!r.ok) return null;
  const js = await r.json();
  const it = (js.results || [])[0];
  return it ? it.stock_code : null;
}

// /api/stocks/{code} → JSON
async function fetchStock(code) {
  const r = await fetch(`${API_BASE}/api/stocks/${code}`);
  if (!r.ok) throw new Error(`종목 ${code} 조회 실패 (${r.status})`);
  return r.json();
}

// 상단 헤더/수치 채우기 (백엔드 응답 기반)
function fillHeaderFromAPI(resp) {
  const cd = resp.current_data || resp || {};
  const hist = Array.isArray(resp.history_data) ? resp.history_data : [];
  const last = hist.length ? hist[hist.length - 1] : {};
  const prev = hist.length > 1 ? hist[hist.length - 2] : {};

  // DOM
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
  const asOfEl = document.getElementById("as-of");

  // 헤더
  if (nameEl) nameEl.textContent = resp.stock_name || resp.stock_code || "";
  if (codeEl) codeEl.textContent = resp.stock_code || "";

  // 현재가
  if (priceEl) priceEl.textContent = money(cd.close_price);

  // 전일대비
  if (diffEl) {
    const changePrice = cd.change_price ?? 0;
    const sign = changePrice >= 0 ? "+" : "-";
    const arrow = sign === "+" ? "▲" : "▼";
    const txt = `${sign}${money(Math.abs(changePrice))} (${pct(cd.change_rate)})`;
    diffEl.textContent = `${arrow} ${txt}`;
    diffEl.classList.remove("up", "down");
    diffEl.classList.add(sign === "+" ? "up" : "down");
  }

  // 전일 / 시가 / 고가 / 저가 (히스토리 활용)
  if (prevEl) prevEl.textContent = prev && prev.close ? money(prev.close) : "-";
  if (openEl) openEl.textContent = last && last.open ? money(last.open) : "-";
  if (highEl) highEl.textContent = last && last.high ? money(last.high) : "-";
  if (lowEl) lowEl.textContent = last && last.low ? money(last.low) : "-";

  // 거래량
  if (volEl) volEl.textContent = money(cd.volume);

  // 거래대금 (백만 단위)
  if (valEl) {
    const tv = last && last.trading_value ? last.trading_value : cd.trading_value;
    const mil = tv ? Math.round(Number(tv) / 1_000_000) : null;
    valEl.textContent = mil == null ? "-" : money(mil);
  }

  // 기준일
  if (asOfEl) {
    const d =
      cd.date && typeof cd.date === "string"
        ? cd.date.replace(/(\d{4})(\d{2})(\d{2})/, "$1.$2.$3")
        : "";
    asOfEl.textContent = d ? `${d} 기준` : "";
  }

  drawPriceChart(hist);
  fillFactorPanelsFromStock(cd);
}

// (fallback) 더미 헤더 렌더
function renderCompanyHeaderDummy(co, nameLabel) {
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

// ===================== 가격 차트 (상단 큰 그래프 + 축 + 툴팁) =====================

function formatDateLabel(d) {
  if (!d) return "";
  d = String(d);
  // 20240115 -> 2024.01.15
  return d.replace(/(\d{4})(\d{2})(\d{2})/, "$1.$2.$3");
}

// history_data에서 (date, close) 배열 뽑기
function extractPointsForChart(history) {
  if (!Array.isArray(history)) return [];
  return history
    .map((row) => {
      const close =
        row.close != null
          ? Number(row.close)
          : row.close_price != null
          ? Number(row.close_price)
          : null;
      const date = row.date || row.trading_date || row.basDt || row.bas_dt;
      if (close == null || isNaN(close)) return null;
      return { date, close };
    })
    .filter((p) => p !== null);
}

// 0~1 정규화
function normalizeChart(values) {
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max === min) return values.map(() => 0.5);
  return values.map((v) => (v - min) / (max - min));
}

function drawPriceChart(history) {
  const container = document.getElementById("price-chart-graph");
  if (!container) return;

  container.innerHTML = "";
  container.style.position = "relative";

  const pts = extractPointsForChart(history);
  if (pts.length < 2) return;

  // 최근 60개만 사용
  const slice = pts.slice(-60);
  const closes = slice.map((p) => p.close);
  const dates = slice.map((p) => p.date);
  const norm = normalizeChart(closes);

  const svgNS = "http://www.w3.org/2000/svg";
  const w = 420;
  const h = 220;
  const paddingX = 36;
  const paddingY = 20;

  const innerW = w - paddingX * 2;
  const innerH = h - paddingY * 2;
  const step = innerW / (closes.length - 1);

  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", "100%");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("class", "price-chart-svg");

  // ===== defs: 그라데이션 =====
  const defs = document.createElementNS(svgNS, "defs");
  const grad = document.createElementNS(svgNS, "linearGradient");
  grad.setAttribute("id", "priceChartGrad");
  grad.setAttribute("x1", "0");
  grad.setAttribute("y1", "0");
  grad.setAttribute("x2", "0");
  grad.setAttribute("y2", "1");

  const stop1 = document.createElementNS(svgNS, "stop");
  stop1.setAttribute("offset", "0%");
  stop1.setAttribute("stop-color", "#00D23F");
  stop1.setAttribute("stop-opacity", "0.25");

  const stop2 = document.createElementNS(svgNS, "stop");
  stop2.setAttribute("offset", "100%");
  stop2.setAttribute("stop-color", "#00D23F");
  stop2.setAttribute("stop-opacity", "0");

  grad.appendChild(stop1);
  grad.appendChild(stop2);
  defs.appendChild(grad);
  svg.appendChild(defs);

  // ===== 축 그리기 =====
  const xAxis = document.createElementNS(svgNS, "line");
  xAxis.setAttribute("x1", paddingX);
  xAxis.setAttribute("y1", h - paddingY);
  xAxis.setAttribute("x2", w - paddingX);
  xAxis.setAttribute("y2", h - paddingY);
  xAxis.setAttribute("stroke", "#222");
  xAxis.setAttribute("stroke-width", "1");
  xAxis.setAttribute("opacity", "0.6");
  svg.appendChild(xAxis);

  const yAxis = document.createElementNS(svgNS, "line");
  yAxis.setAttribute("x1", paddingX);
  yAxis.setAttribute("y1", paddingY);
  yAxis.setAttribute("x2", paddingX);
  yAxis.setAttribute("y2", h - paddingY);
  yAxis.setAttribute("stroke", "#222");
  yAxis.setAttribute("stroke-width", "1");
  yAxis.setAttribute("opacity", "0.6");
  svg.appendChild(yAxis);

  const priceMin = Math.min(...closes);
  const priceMax = Math.max(...closes);

  // y축 라벨 (min / max)
  const yMinText = document.createElementNS(svgNS, "text");
  yMinText.setAttribute("x", paddingX - 6);
  yMinText.setAttribute("y", h - paddingY);
  yMinText.setAttribute("text-anchor", "end");
  yMinText.setAttribute("dominant-baseline", "middle");
  yMinText.setAttribute("fill", "#888");
  yMinText.setAttribute("font-size", "10");
  yMinText.textContent = money(Math.round(priceMin));
  svg.appendChild(yMinText);

  const yMaxText = document.createElementNS(svgNS, "text");
  yMaxText.setAttribute("x", paddingX - 6);
  yMaxText.setAttribute("y", paddingY);
  yMaxText.setAttribute("text-anchor", "end");
  yMaxText.setAttribute("dominant-baseline", "middle");
  yMaxText.setAttribute("fill", "#888");
  yMaxText.setAttribute("font-size", "10");
  yMaxText.textContent = money(Math.round(priceMax));
  svg.appendChild(yMaxText);

  // x축 라벨 (시작 / 끝 날짜)
  const firstDate = formatDateLabel(dates[0]);
  const lastDate = formatDateLabel(dates[dates.length - 1]);

  const xStartText = document.createElementNS(svgNS, "text");
  xStartText.setAttribute("x", paddingX);
  xStartText.setAttribute("y", h - paddingY + 14);
  xStartText.setAttribute("text-anchor", "start");
  xStartText.setAttribute("fill", "#888");
  xStartText.setAttribute("font-size", "10");
  xStartText.textContent = firstDate;
  svg.appendChild(xStartText);

  const xEndText = document.createElementNS(svgNS, "text");
  xEndText.setAttribute("x", w - paddingX);
  xEndText.setAttribute("y", h - paddingY + 14);
  xEndText.setAttribute("text-anchor", "end");
  xEndText.setAttribute("fill", "#888");
  xEndText.setAttribute("font-size", "10");
  xEndText.textContent = lastDate;
  svg.appendChild(xEndText);

  // ===== 라인 & 영역 path =====
  let dLine = "";
  let dArea = "";

  norm.forEach((v, i) => {
    const x = paddingX + i * step;
    const y = paddingY + (1 - v) * innerH;

    dLine += (i === 0 ? "M" : "L") + x + " " + y + " ";

    if (i === 0) {
      dArea = "M" + x + " " + (paddingY + innerH) + " L" + x + " " + y + " ";
    } else {
      dArea += "L" + x + " " + y + " ";
    }

    if (i === norm.length - 1) {
      dArea += "L" + x + " " + (paddingY + innerH) + " Z";
    }
  });

  const area = document.createElementNS(svgNS, "path");
  area.setAttribute("d", dArea.trim());
  area.setAttribute("fill", "url(#priceChartGrad)");

  const path = document.createElementNS(svgNS, "path");
  path.setAttribute("d", dLine.trim());
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "#00D23F");
  path.setAttribute("stroke-width", "2.4");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");

  svg.appendChild(area);
  svg.appendChild(path);

  // ===== 커서 라인 & 포인트 원 =====
  const cursorLine = document.createElementNS(svgNS, "line");
  cursorLine.setAttribute("stroke", "#FFFFFF");
  cursorLine.setAttribute("stroke-width", "1.2");
  cursorLine.setAttribute("stroke-opacity", "0.7");
  cursorLine.setAttribute("y1", paddingY);
  cursorLine.setAttribute("y2", h - paddingY);
  cursorLine.style.opacity = "0";
  svg.appendChild(cursorLine);

  const cursorDot = document.createElementNS(svgNS, "circle");
  cursorDot.setAttribute("r", "4");
  cursorDot.setAttribute("fill", "#00D23F");
  cursorDot.setAttribute("stroke", "#FFFFFF");
  cursorDot.setAttribute("stroke-width", "1.2");
  cursorDot.style.opacity = "0";
  svg.appendChild(cursorDot);

  // ===== 툴팁 div =====
  const tooltip = document.createElement("div");
  tooltip.className = "price-tooltip";
  tooltip.style.opacity = "0";
  container.appendChild(tooltip);

  // ===== 인터랙션 (마우스 오버) =====
  svg.addEventListener("mousemove", (e) => {
    const rect = svg.getBoundingClientRect();
    const xPix = e.clientX - rect.left;

    // padding 안쪽만
    const minX = paddingX;
    const maxX = w - paddingX;
    const clamped = Math.min(Math.max(xPix * (w / rect.width), minX), maxX);

    const t = (clamped - paddingX) / innerW;
    const idx = Math.round(t * (closes.length - 1));
    const i = Math.min(Math.max(idx, 0), closes.length - 1);

    const vx = paddingX + i * step;
    const vy = paddingY + (1 - norm[i]) * innerH;

    cursorLine.setAttribute("x1", vx);
    cursorLine.setAttribute("x2", vx);
    cursorLine.style.opacity = "1";

    cursorDot.setAttribute("cx", vx);
    cursorDot.setAttribute("cy", vy);
    cursorDot.style.opacity = "1";

    const dateLabel = formatDateLabel(dates[i]);
    const priceLabel = money(closes[i]);

    tooltip.textContent = `${dateLabel} · ${priceLabel}`;

    // tooltip 위치 (컨테이너 기준)
    const relX = (vx / w) * 100;
    const relY = (vy / h) * 100;
    tooltip.style.left = relX + "%";
    tooltip.style.top = relY + "%";
    tooltip.style.opacity = "1";
  });

  svg.addEventListener("mouseleave", () => {
    cursorLine.style.opacity = "0";
    cursorDot.style.opacity = "0";
    tooltip.style.opacity = "0";
  });

  container.appendChild(svg);
}

// ===== 가운데 3개 패널: PER / PBR / 배당수익률 (그래프 버전) =====
function fillFactorPanelsFromStock(cd) {

  const p1Title = document.getElementById("panel-title-1");
  const p2Title = document.getElementById("panel-title-2");
  const p3Title = document.getElementById("panel-title-3");

  const bodies = document.querySelectorAll(".panel-body");
  const b1 = bodies[0];
  const b2 = bodies[1];
  const b3 = bodies[2];

  if (!p1Title || !p2Title || !p3Title || !b1 || !b2 || !b3) return;

  // 제목 고정
  p1Title.textContent = "PER";
  p2Title.textContent = "PBR";
  p3Title.textContent = "배당수익률";

  // 원시 값
  const per = cd.per;
  const pbr = cd.pbr;
  const divYield = cd.div_yield; // 0.03 → 3%

  // 그래프 계산용 숫자 (배당은 % 기준으로)
  const perVal =
    per == null || isNaN(per) ? null : Number(per);
  const pbrVal =
    pbr == null || isNaN(pbr) ? null : Number(pbr);
  const divPctVal =
    divYield == null || isNaN(divYield)
      ? null
      : Number(divYield) * 100;

  const values = [perVal, pbrVal, divPctVal];
  const safeVals = values.filter((v) => v != null && v > 0);
  const maxVal = safeVals.length ? Math.max(...safeVals) : 1;

  // 내부 헬퍼: 하나의 패널 채우기
  function setPanel(el, rawVal, labelTextFormatter) {
    el.innerHTML = ""; // 초기화

    const bar = document.createElement("div");
    bar.className = "panel-bar";

    const fill = document.createElement("div");
    fill.className = "panel-bar-fill";

    const label = document.createElement("div");
    label.className = "panel-value-label";

    if (rawVal == null || isNaN(rawVal)) {
      // 값 없으면 그냥 '-'만
      fill.style.transform = "scaleX(0)";
      label.textContent = "-";
    } else {
      const ratio = Math.max(0.1, rawVal / maxVal); // 최소 10%는 채워지게
      fill.style.transform = `scaleX(${Math.min(ratio, 1)})`;
      label.textContent = labelTextFormatter(rawVal);
    }

    bar.appendChild(fill);
    el.appendChild(bar);
    el.appendChild(label);
  }

  // 패널 3개 채우기
  setPanel(b1, perVal, (v) => v.toFixed(2));               // PER
  setPanel(b2, pbrVal, (v) => v.toFixed(2));               // PBR
  setPanel(b3, divPctVal, (v) => v.toFixed(2) + "%");      // 배당수익률
}

// ===================== 재무 테이블 =====================

const PANEL_PRESETS = {
  bs: ["자산총계", "부채총계", "자본총계"],
  is: ["매출액", "영업이익", "당기순이익"],
  cf: ["영업활동현금흐름", "투자활동현금흐름", "재무활동현금흐름"],
  all: ["자산총계", "부채총계", "자본총계"],
};

const TABLE_NAME_BY_VIEW = {
  bs: "연결재무상태표",
  is: "연결포괄손익계산서",
  cf: "연결현금흐름표",
  all: "요약연결재무정보",
};

let CURRENT_FINANCE = null;
let CURRENT_VIEW_TYPE = "bs";

function formatNumber(val) {
  if (val === null || val === undefined || val === "") return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return val;
  return n.toLocaleString("ko-KR");
}

// 실제로 그리드 그리기 (재무 테이블)
function renderFinanceTable(viewType) {
  if (!CURRENT_FINANCE) return;

  const tableName = TABLE_NAME_BY_VIEW[viewType];
  const rows =
    (CURRENT_FINANCE.tables && CURRENT_FINANCE.tables[tableName]) || [];

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

  // 연도 열 4개 고정 (예시: 2022, 2023, 2024, 2025)
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

// 드롭다운에서 타입 바꼈을 때 (테이블 + 타이틀만 담당)
function applyInfoType(type, coName) {
  CURRENT_VIEW_TYPE = type;

  const financeTitle = document.getElementById("finance-title");
  if (financeTitle) {
    financeTitle.textContent =
      type === "bs"
        ? `${coName}의 재무상태표`
        : type === "is"
        ? `${coName}의 손익계산서`
        : type === "cf"
        ? `${coName}의 현금흐름표`
        : `${coName}의 요약재무정보`;
  }

  renderFinanceTable(type);
}

// 연도 칩 – 지금은 전부 opacity=1 (디자인만)
function showYear(year) {
  document.querySelectorAll(".year-col").forEach((col) => {
    col.style.opacity = col.dataset.year === year ? "1" : "1";
  });
}

// ===================== 가운데 회색 패널(지표 영역) =====================

function fillPanels(type, metrics) {
  const p1 = document.querySelector("#panel-title-1");
  const p2 = document.querySelector("#panel-title-2");
  const p3 = document.querySelector("#panel-title-3");

  if (!p1 || !p2 || !p3 || !metrics) return;

  if (type === "bs") {
    p1.textContent = "부채비율";
    p2.textContent = "유동비율";
    p3.textContent = "자기자본회전율";

    setPanelValues([
      metrics.debt_ratio,
      metrics.current_ratio,
      metrics.equity_turnover,
    ]);
  } else if (type === "is") {
    p1.textContent = "ROE";
    p2.textContent = "영업이익률";
    p3.textContent = "순이익률";

    setPanelValues([metrics.roe, metrics.op_margin, metrics.ni_margin]);
  } else if (type === "cf") {
    p1.textContent = "이자보상배율";
    p2.textContent = "영업현금흐름";
    p3.textContent = "배당금지급";

    setPanelValues([
      metrics.interest_cov,
      getMetric(CURRENT_FINANCE, "연결현금흐름표", "영업활동현금흐름"),
      getMetric(CURRENT_FINANCE, "연결현금흐름표", "배당금의 지급"),
    ]);
  } else if (type === "all") {
    p1.textContent = "ROE";
    p2.textContent = "부채비율";
    p3.textContent = "매출증가율";

    setPanelValues([
      metrics.roe,
      metrics.debt_ratio,
      null, // 증가율은 나중에 추가 가능
    ]);
  }
}

function setPanelValues(values) {
  const panels = document.querySelectorAll(".panel-body");
  panels.forEach((el, idx) => {
    const v = values[idx];
    if (v == null || Number.isNaN(v)) {
      el.textContent = "-";
    } else {
      el.textContent = (v * 100).toFixed(2) + "%";
    }
  });
}

// ===================== 투자자 테이블 (더미 그대로 유지) =====================

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
    thead.innerHTML =
      "<tr><th>구분</th><th>거래량</th><th colspan='2'>비고</th></tr>";
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

// ===================== DOMContentLoaded =====================

document.addEventListener("DOMContentLoaded", async () => {
  // 0) 일단 기본 더미값 안 보이게 플레이스홀더로 리셋
  const priceEl = document.getElementById("current-price");
  const diffEl = document.getElementById("price-change");
  const prevEl = document.getElementById("prev-close");
  const openEl = document.getElementById("open-price");
  const highEl = document.getElementById("high-price");
  const lowEl = document.getElementById("low-price");
  const volEl = document.getElementById("volume");
  const valEl = document.getElementById("value");
  const asOfEl = document.getElementById("as-of");

  [priceEl, prevEl, openEl, highEl, lowEl, volEl, valEl].forEach((el) => {
    if (el) el.textContent = "-";
  });
  if (diffEl) diffEl.textContent = "";
  if (asOfEl) asOfEl.textContent = "";

  // 1) 어떤 기업으로 들어왔는지
  const q = getQuery("q") || "삼성전자";
  let coName = q;
  let code = null;

  // 우선 상단 이름만 q로 바꿔두기 (삼성전자 더미 대신)
  const nameEl = document.getElementById("co-name");
  if (nameEl) nameEl.textContent = coName;

  try {
    code = await resolveToCode(q);
  } catch (e) {
    console.warn("resolveToCode error:", e);
  }

  // 2) 헤더 채우기 (실데이터 → 실패시 더미)
  if (!code) {
    console.warn("코드 해석 실패, 더미 데이터 사용");
    const dummy = COMPANY_DATA[q] || COMPANY_DATA["삼성전자"];
    coName = q in COMPANY_DATA ? q : "삼성전자";
    renderCompanyHeaderDummy(dummy, coName);
  } else {
    try {
      const data = await fetchStock(code);
      coName = data.stock_name || coName;
      fillHeaderFromAPI(data);
    } catch (e) {
      console.warn("fetchStock error, 더미로 fallback:", e);
      const dummy = COMPANY_DATA[q] || COMPANY_DATA["삼성전자"];
      coName = q in COMPANY_DATA ? q : "삼성전자";
      renderCompanyHeaderDummy(dummy, coName);
    }
  }

  // 3) 상단 검색 → 다른 종목 디테일로 이동 + 자동완성 드롭다운
  const form = document.getElementById("detail-search-form");
  const input = document.getElementById("detail-search-input");

  if (form && input) {
    // 기본 검색 동작
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) return;
      window.location.href = `company_detail.html?q=${encodeURIComponent(v)}`;
    });

    // 자동완성 컨테이너 만들기
    form.style.position = "relative";

    const dropdown = document.createElement("div");
    dropdown.className = "stock-autocomplete";
    Object.assign(dropdown.style, {
      position: "absolute",
      left: "0",
      right: "0",
      top: "100%", // 인풋 바로 아래
      marginTop: "4px",
      background: "#000",
      borderRadius: "16px",
      boxShadow: "0 16px 40px rgba(0,0,0,0.4)",
      padding: "4px 0",
      maxHeight: "260px",
      overflowY: "auto",
      zIndex: "200",
      display: "none",
    });
    form.appendChild(dropdown);

    let acTimer = null;

    function hideDropdown() {
      dropdown.style.display = "none";
      dropdown.innerHTML = "";
    }

    function showDropdown() {
      dropdown.style.display = "block";
    }

    async function fetchSuggestions(q) {
      try {
        const res = await fetch(
          `${API_BASE}/api/stocks/lookup?q=${encodeURIComponent(q)}&limit=8`
        );
        if (!res.ok) {
          hideDropdown();
          return;
        }
        const js = await res.json();
        const items = js.results || [];
        if (!items.length) {
          hideDropdown();
          return;
        }

        dropdown.innerHTML = "";
        items.forEach((it) => {
          const row = document.createElement("div");
          row.className = "stock-autocomplete-item";
          Object.assign(row.style, {
            padding: "8px 14px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontSize: "13px",
            cursor: "pointer",
            color: "#F5F5F5",
          });

          row.innerHTML =
            `<span>${it.stock_name}</span>` +
            `<span style="opacity:0.7;font-variant-numeric:tabular-nums;">${it.stock_code}</span>`;

          row.addEventListener("mouseenter", () => {
            row.style.background = "rgba(255,255,255,0.06)";
          });
          row.addEventListener("mouseleave", () => {
            row.style.background = "transparent";
          });

          row.addEventListener("click", () => {
            input.value = it.stock_name; // 회사명으로 채우기
            hideDropdown();
          });

          dropdown.appendChild(row);
        });

        showDropdown();
      } catch (err) {
        console.warn("autocomplete error", err);
        hideDropdown();
      }
    }

    // 입력 이벤트 → 디바운스 후 자동완성 호출
    input.addEventListener("input", () => {
      const v = input.value.trim();
      if (!v) {
        hideDropdown();
        return;
      }
      if (acTimer) clearTimeout(acTimer);
      acTimer = setTimeout(() => {
        fetchSuggestions(v);
      }, 180);
    });

    // 포커스 잃으면 살짝 있다가 닫기 (클릭 이벤트 먼저 처리되게)
    input.addEventListener("blur", () => {
      setTimeout(() => {
        hideDropdown();
      }, 150);
    });

    // 인풋 클릭 시 다시 열릴 수 있게 (값이 있을 때만)
    input.addEventListener("focus", () => {
      if (dropdown.innerHTML.trim()) {
        showDropdown();
      }
    });
  }

  // 4) 투자자 드롭다운 (더미 그대로)
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

  // 5) 백엔드에서 재무 가져오기 (+ 지표 계산)
  if (code) {
    try {
      const resp = await fetch(`${API_BASE}/finance/${code}`);
      if (resp.ok) {
        CURRENT_FINANCE = await resp.json();
        console.log("[finance] loaded", CURRENT_FINANCE);

        // 재무 표 그리기
        applyInfoType("bs", coName);

        // // 지표 계산해서 패널 채우기
        // const metrics = computeIndicators(CURRENT_FINANCE);
        // window.FIN_METRICS = metrics; // 전역 저장
      } else {
        console.warn("finance api not ok", resp.status);
        CURRENT_FINANCE = null;
      }
    } catch (err) {
      console.warn("finance api error", err);
      CURRENT_FINANCE = null;
    }
  }

  // 6) info 드롭다운 (재무상태표/손익계산서/현금흐름표/요약)
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

      // 테이블/타이틀 변경
      applyInfoType(type, coName);

      // 패널 지표도 같이 변경
      if (window.FIN_METRICS) {
        fillPanels(type, window.FIN_METRICS);
      }

      // 버튼 라벨도 교체
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
});

// ===================== 지표 계산 유틸 =====================

function getMetric(fin, table, account) {
  if (!fin || !fin.tables) return null;
  const rows = fin.tables[table] || [];
  const item = rows.find((r) => r.name === account);
  return item ? Number(item.current) : null;
}

function computeIndicators(fin) {
  const bs = "연결재무상태표";
  const is = "연결포괄손익계산서";
  const cf = "연결현금흐름표";

  const asset = getMetric(fin, bs, "자산총계");
  const debt = getMetric(fin, bs, "부채총계");
  const equity = getMetric(fin, bs, "자본총계");
  const ca = getMetric(fin, bs, "유동자산");
  const cl = getMetric(fin, bs, "유동부채");
  const ar = getMetric(fin, bs, "매출채권");
  const inv = getMetric(fin, bs, "재고자산");

  const revenue = getMetric(fin, is, "매출액");
  const op = getMetric(fin, is, "영업이익");
  const ni = getMetric(fin, is, "당기순이익");

  const interest = getMetric(fin, cf, "이자의 지급");
  const tax = getMetric(fin, cf, "법인세 납부액");

  return {
    // 수익성
    roe: equity ? ni / equity : null,
    op_margin: revenue ? op / revenue : null,
    ni_margin: revenue ? ni / revenue : null,

    // 건전성
    debt_ratio: equity ? debt / equity : null,
    current_ratio: cl ? ca / cl : null,
    interest_cov: interest ? op / interest : null,

    // 활동성
    asset_turnover: asset ? revenue / asset : null,
    equity_turnover: equity ? revenue / equity : null,
    ar_turnover: ar ? revenue / ar : null,
    inv_turnover: inv ? revenue / inv : null,
  };
}