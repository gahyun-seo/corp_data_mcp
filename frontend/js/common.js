document.addEventListener("DOMContentLoaded", () => {
  const nav = document.getElementById("top-nav");
  if (!nav) return;

  let visible = true;
  const SHOW_ZONE = 100; // 화면 상단 100px 이내면 보여줌
  const HIDE_DELAY = 400; // 마우스가 떠난 후 약간 딜레이 주기

  let hideTimer = null;

  // 마우스 움직임 감지
  window.addEventListener("mousemove", (e) => {
    const y = e.clientY;

    // 마우스가 상단 근처에 있으면 네비 보여주기
    if (y <= SHOW_ZONE) {
      if (!visible) {
        nav.classList.remove("hidden");
        visible = true;
      }
      if (hideTimer) {
        clearTimeout(hideTimer);
        hideTimer = null;
      }
    } else {
      // 상단 벗어나면 일정 시간 후 숨기기
      if (visible && !hideTimer) {
        hideTimer = setTimeout(() => {
          nav.classList.add("hidden");
          visible = false;
          hideTimer = null;
        }, HIDE_DELAY);
      }
    }
  });

  // 현재 페이지 active 표시
  const path = window.location.pathname.split("/").pop();
  document.querySelectorAll(".nav-link").forEach((link) => {
    const href = link.getAttribute("href");
    if (href === path) {
      link.classList.add("active");
    }
  });
});
