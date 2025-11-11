// 더미 티커 데이터
const dummyCompanies = [
  {
    name: "삼성전자",
    time: "2025.11.05 15:30 기준",
    price: "100,600",
    change: "-4,300 (-4.10%)",
    up: false,
  },
  {
    name: "LG화학",
    time: "2025.11.05 15:30 기준",
    price: "512,000",
    change: "+3,200 (+0.63%)",
    up: true,
  },
  {
    name: "SK하이닉스",
    time: "2025.11.05 15:30 기준",
    price: "144,000",
    change: "-1,100 (-0.76%)",
    up: false,
  },
  {
    name: "현대차",
    time: "2025.11.05 15:30 기준",
    price: "212,500",
    change: "+5,200 (+2.43%)",
    up: true,
  },
  {
    name: "카카오",
    time: "2025.11.05 15:30 기준",
    price: "57,200",
    change: "-800 (-1.38%)",
    up: false,
  },
  {
    name: "POSCO홀딩스",
    time: "2025.11.05 15:30 기준",
    price: "414,500",
    change: "+2,400 (+0.58%)",
    up: true,
  },
];

// 카드 렌더링
const tickerEl = document.getElementById("fs-ticker");
const DETAIL_PAGE = "company_detail.html";

function createCard(c) {
  var card = document.createElement("div");
  card.className = "fs-card";

  var isMinus = c.change.trim().indexOf("-") === 0;
  var changeColor = isMinus ? "#00D23F" : "#FB781B"; // -면 초록, +면 주황
  var arrow = isMinus ? "▼" : "▲";


  card.innerHTML =
    '<div class="fs-card-bg"></div>' +
    '<div class="fs-card-time">' + c.time + '</div>' +
    '<div class="fs-card-name" style="left:19.43px;top:34.98px;">' + c.name + '</div>' +
    '<div class="fs-card-price">' + c.price + '</div>' +
    '<div class="fs-card-change" style="color:' + changeColor + ';">' +
      arrow + ' ' + c.change +
    '</div>' +
    '<img class="fs-card-graph" src="assets/company_graph.png" alt="' + c.name + ' 그래프" />';

  card.dataset.name = c.name;

  // 카드 클릭하면 해당 종목 디테일로 이동
  card.addEventListener("click", () => {
    const name = card.dataset.name || "삼성전자";
    window.location.href = `${DETAIL_PAGE}?q=${encodeURIComponent(name)}`;
  });

  return card;
}

// 무한 느낌 나게 두 번 붙이기
if (tickerEl) {
  for (let i = 0; i < 2; i++) {
    dummyCompanies.forEach((c) => {
      tickerEl.appendChild(createCard(c));
    });
  }
}

// 검색 -> 디테일 페이지로 이동
const fsForm = document.getElementById("fs-search-form");
const fsInput = document.getElementById("fs-search-input");


if (fsForm && fsInput) {
  fsForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = fsInput.value.trim();
    if (!q) return;
    window.location.href = `${DETAIL_PAGE}?q=${encodeURIComponent(q)}`;
  });
}