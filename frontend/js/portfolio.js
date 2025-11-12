// =========================
// 1. 그래프 슬라이더 + 제목 변경
// =========================

const slides = document.querySelectorAll(".chart-slide");
const dots = document.querySelectorAll(".chart-status .dot");
const prevBtn = document.querySelector(".chart-prev");
const nextBtn = document.querySelector(".chart-next");
const chartTitle = document.querySelector(".chart-tab");

const chartTitles = [
  "Efficient Frontier",
  "Risk vs Return Simulation",
  "Sector Allocation Visualization"
];

let currentSlide = 0;

function showSlide(index) {
  // 슬라이드 표시
  slides.forEach((slide, i) => {
    slide.classList.toggle("active", i === index);
  });

  // 상태 점 표시
  dots.forEach((dot, i) => {
    dot.classList.toggle("active", i === index);
  });

  // 제목도 변경
  if (chartTitle && chartTitles[index]) {
    chartTitle.textContent = chartTitles[index];
  }

  currentSlide = index;
}

// 처음 상태
showSlide(0);

// 화살표 이벤트
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

// 점 클릭
dots.forEach((dot) => {
  dot.addEventListener("click", () => {
    const idx = Number(dot.dataset.index);
    showSlide(idx);
  });
});


// =========================
// 2. 테이블 관련 (지표 + 회사 컬럼)
// =========================

// 왼쪽 지표 목록 (HTML이랑 순서 맞춰야 함)
const metrics = [
  "재무정보",  // ← 이 줄은 회사 이름이랑 같은 줄
  "매출액",
  "영업이익",
  "당기순이익",
  "영업이익률",
  "순이익률",
  "ROE",
  "부채비율",
  "당좌비율",
  "유보율",
  "EPS",
  "PBR",
  "주당배당금",
  "시가배당률",
  "배당성향"
];

const companiesWrap = document.getElementById("companies-wrap");

// 더미 데이터 (지금은 다 같은 값)
const dummyValue = "433,766";

// 회사 컬럼 만드는 함수
function createCompanyCol(name) {
  const col = document.createElement("div");
  col.className = "company-col";

  // 1) 회사 이름 (이게 '재무정보'랑 같은 줄)
  const head = document.createElement("div");
  head.className = "company-head";
  head.textContent = name;
  col.appendChild(head);

  // 2) 나머지 지표 값 (매출액부터 끝까지)
  const metricValues = metrics.slice(1); // 첫 번째(재무정보)는 빼고
  metricValues.forEach((_, idx) => {
    const cell = document.createElement("div");
    cell.className = "company-cell";
    // 첫 줄만 다른 값 보여주고 싶으면 여기 조건 달면 됨
    cell.textContent = dummyValue;
    col.appendChild(cell);
  });

  return col;
}

// 초기로 삼성전자 4개 정도 넣기
if (companiesWrap) {
  ["삼성전자", "삼성전자", "삼성전자", "삼성전자"].forEach((name) => {
    companiesWrap.appendChild(createCompanyCol(name));
  });
}


// =========================
// 3. 종목 추가 (검색 바 안에 버튼 있는 버전)
// =========================

const addStockForm = document.getElementById("add-stock-form");
const stockInput = document.getElementById("stock-input");

if (addStockForm && stockInput && companiesWrap) {
  addStockForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const name = stockInput.value.trim();
    if (!name) return;

    companiesWrap.appendChild(createCompanyCol(name));
    stockInput.value = "";

    // 추가되면 오른쪽 끝으로 스크롤
    companiesWrap.scrollLeft = companiesWrap.scrollWidth;
  });
}


// =========================
// 4. 드롭다운 (포트폴리오 목표 선택)
// =========================

const dropdownButtons = document.querySelectorAll(".select-pill");

dropdownButtons.forEach((btn) => {
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const targetId = btn.getAttribute("data-dropdown-target");
    const list = document.getElementById(targetId);
    const isOpen = list && list.style.display === "block";

    // 다른 드롭다운 닫기
    document.querySelectorAll(".select-list").forEach((ul) => {
      ul.style.display = "none";
    });

    // 이 드롭다운 토글
    if (list) {
      list.style.display = isOpen ? "none" : "block";
    }
  });
});

// 옵션 클릭하면 버튼 텍스트에 반영
document.querySelectorAll(".select-list li").forEach((item) => {
  item.addEventListener("click", () => {
    const value = item.dataset.value;
    const parentList = item.parentElement;
    const btn = document.querySelector(`[data-dropdown-target="${parentList.id}"]`);
    if (btn) {
      // 버튼의 첫 번째 텍스트만 바꾸기
      // (우리가 아이콘도 같이 넣어놨으니까)
      const textNode = btn.childNodes[0];
      if (textNode) {
        textNode.textContent = value + " ";
      }
    }
    parentList.style.display = "none";
  });
});

// 바깥 클릭하면 모두 닫기
document.addEventListener("click", () => {
  document.querySelectorAll(".select-list").forEach((ul) => (ul.style.display = "none"));
});