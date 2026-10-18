// Small global helpers: theme toggle, bottom sheet, copy buttons.
(function () {
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("theme");
    if (saved) root.dataset.theme = saved;
  } catch (e) { /* storage blocked */ }

  document.addEventListener("click", (ev) => {
    const themeBtn = ev.target.closest("[data-theme-toggle]");
    if (themeBtn) {
      const dark = root.dataset.theme
        ? root.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
      try { localStorage.setItem("theme", root.dataset.theme); } catch (e) { /* ignore */ }
      document.dispatchEvent(new CustomEvent("themeChanged"));
    }
    const handle = ev.target.closest("[data-sheet-toggle]");
    if (handle) {
      const panel = document.getElementById("panel");
      panel.classList.toggle("collapsed");
      handle.setAttribute("aria-expanded", String(!panel.classList.contains("collapsed")));
    }
    const copyBtn = ev.target.closest("[data-copy]");
    if (copyBtn) {
      const src = document.getElementById(copyBtn.dataset.copy);
      if (src && navigator.clipboard) {
        navigator.clipboard.writeText(src.textContent).then(() => {
          const old = copyBtn.textContent;
          copyBtn.textContent = "Skopiowano";
          setTimeout(() => { copyBtn.textContent = old; }, 1500);
        });
      }
    }
  });
})();
