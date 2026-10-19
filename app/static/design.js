// Mermaid preview on the 'Projekt aplikacji' tab: render on load, after HTMX swaps and on theme change.
(function () {
  if (!window.mermaid) return;

  function theme() {
    return document.documentElement.dataset.theme === "dark" ? "dark" : "default";
  }

  function render() {
    window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: theme() });
    document.querySelectorAll("pre.mermaid").forEach((el) => {
      el.removeAttribute("data-processed");
      el.textContent = el.dataset.source;
    });
    window.mermaid.run({ querySelector: "pre.mermaid" }).catch((err) => console.warn("mermaid", err));
  }

  document.addEventListener("DOMContentLoaded", render);
  document.addEventListener("htmx:afterSwap", render);
  document.addEventListener("themeChanged", render);
})();
