document.addEventListener("click", (event) => {
  const close = event.target.closest(".flash-close");
  if (close) close.closest(".flash")?.remove();
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest("form[data-confirm]");
  if (form && !window.confirm(form.dataset.confirm || "Are you sure?")) {
    event.preventDefault();
  }
});

// Dismiss flash messages automatically after a short delay.
window.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flash").forEach((item) => {
    window.setTimeout(() => item.classList.add("flash-fade"), 6500);
    window.setTimeout(() => item.remove(), 7000);
  });
});
