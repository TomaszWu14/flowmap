// Global helpers: theme, bottom sheet, copy, confirm, toasts with Undo, save status, drafts, panel resize.
(function () {
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("theme");
    if (saved) root.dataset.theme = saved;
  } catch (e) { /* storage blocked */ }

  document.addEventListener("submit", (ev) => {
    const msg = ev.target.dataset && ev.target.dataset.confirm;
    if (msg && !window.confirm(msg)) { ev.preventDefault(); return; }
    // data-once: forms that spend AI requests — a double click must not send (and pay) twice
    if (ev.target.dataset && "once" in ev.target.dataset) {
      setTimeout(() => ev.target.querySelectorAll("button[type=submit]").forEach((b) => { b.disabled = true; }), 0);
    }
  });

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

  // --- toasts (server sends HX-Trigger {"toast": {"message", "undo"}}) -------------------
  function toast(message, opts = {}) {
    const box = document.getElementById("toasts");
    if (!box) return;
    const t = document.createElement("div");
    t.className = "toast" + (opts.error ? " error" : "");
    t.setAttribute("role", opts.error ? "alert" : "status");
    const text = document.createElement("span");
    text.textContent = message;
    t.append(text);
    const undoBtn = document.getElementById("btn-undo");
    if (opts.undo && undoBtn) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn small";
      b.textContent = "Cofnij";
      b.addEventListener("click", () => { undoBtn.click(); t.remove(); });
      t.append(b);
    }
    const x = document.createElement("button");
    x.type = "button";
    x.className = "toast-close";
    x.setAttribute("aria-label", "Zamknij");
    x.textContent = "×";
    x.addEventListener("click", () => t.remove());
    t.append(x);
    box.append(t);
    while (box.children.length > 3) box.firstElementChild.remove();
    setTimeout(() => t.remove(), opts.error ? 9000 : 6000);
  }
  window.flowToast = toast;
  document.body.addEventListener("toast", (ev) => toast(ev.detail.message, { undo: ev.detail.undo }));

  // --- save status + connection errors for every HTMX request ---------------------------
  const status = document.getElementById("save-status");
  let statusTimer = null;
  function setStatus(text, cls) {
    if (!status) return;
    clearTimeout(statusTimer);
    status.textContent = text;
    status.className = "save-status " + (cls || "");
    if (cls === "ok") statusTimer = setTimeout(() => { status.textContent = ""; }, 2500);
  }
  const writes = (ev) => (ev.detail.requestConfig || {}).verb !== "get";
  document.body.addEventListener("htmx:beforeRequest", (ev) => { if (writes(ev)) setStatus("Zapisywanie…", "busy"); });
  document.body.addEventListener("htmx:afterRequest", (ev) => {
    if (writes(ev) && ev.detail.successful) setStatus("Zapisano ✓", "ok");
  });
  document.body.addEventListener("htmx:responseError", (ev) => {
    setStatus("Nie zapisano", "err");
    const code = ev.detail.xhr.status;
    toast(code === 403 ? "Nie masz uprawnień do tej zmiany." : code === 404
      ? "Tego elementu już nie ma — odśwież stronę." : `Serwer zwrócił błąd (${code}). Spróbuj ponownie.`, { error: true });
  });
  document.body.addEventListener("htmx:sendError", () => {
    setStatus("Brak połączenia", "err");
    toast("Brak połączenia z serwerem — zmiana nie została zapisana. Sprawdź internet i spróbuj ponownie.", { error: true });
  });

  // --- drafts of free-text answers survive panel reloads (per project, step and question) ---
  function restoreDrafts(root) {
    root.querySelectorAll("[data-draft]").forEach((field) => {
      const key = "fm-draft:" + field.dataset.draft;
      try {
        const saved = localStorage.getItem(key);
        if (saved && !field.value) {
          field.value = saved;
          const details = field.closest("details");
          if (details) details.open = true;
        }
      } catch (e) { /* storage blocked */ }
      field.addEventListener("input", () => {
        try { field.value ? localStorage.setItem(key, field.value) : localStorage.removeItem(key); } catch (e) { /* ignore */ }
      });
      const form = field.form;
      if (form) form.addEventListener("htmx:afterRequest", (ev) => {
        if (ev.detail.successful) try { localStorage.removeItem(key); } catch (e) { /* ignore */ }
      });
    });
  }
  restoreDrafts(document);
  document.body.addEventListener("htmx:afterSwap", (ev) => restoreDrafts(ev.detail.target));

  // --- resizable question panel (desktop) --------------------------------------------------
  const handle = document.querySelector(".panel-resize");
  const workspace = document.querySelector(".workspace");
  if (handle && workspace) {
    const setWidth = (px) => {
      const w = Math.round(Math.min(Math.max(px, 300), window.innerWidth * 0.6));
      workspace.style.setProperty("--panel-w", w + "px");
      try { localStorage.setItem("fm-panel-w", String(w)); } catch (e) { /* ignore */ }
      window.dispatchEvent(new Event("resize"));  // Cytoscape re-measures its container
    };
    try { const saved = Number(localStorage.getItem("fm-panel-w")); if (saved) setWidth(saved); } catch (e) { /* ignore */ }
    handle.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      handle.setPointerCapture(ev.pointerId);
      const move = (e) => setWidth(window.innerWidth - e.clientX);
      const up = () => { handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", up); };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
    });
    handle.addEventListener("keydown", (ev) => {
      const now = parseInt(getComputedStyle(workspace).getPropertyValue("--panel-w")) || 400;
      if (ev.key === "ArrowLeft") { ev.preventDefault(); setWidth(now + 30); }
      if (ev.key === "ArrowRight") { ev.preventDefault(); setWidth(now - 30); }
    });
  }

  // --- images: shrink in the browser (≤ 1600 px), upload by picker, drag & drop or paste -----
  async function shrink(file) {
    if (file.type === "image/gif" || !window.createImageBitmap) return file;  // keep animations as they are
    const bmp = await createImageBitmap(file);
    const scale = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
    if (scale === 1 && file.size <= 1.5 * 1024 * 1024) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.85));
    return new File([blob], (file.name || "grafika").replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
  }
  const csrfToken = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  async function uploadImages(gallery, files) {
    let current = gallery;
    for (const original of files) {
      if (!original.type.startsWith("image/")) continue;
      const fd = new FormData();
      fd.append("file", await shrink(original));
      fd.append("node_key", current.dataset.nodeKey || "");
      try {
        const res = await fetch(current.dataset.uploadUrl, { method: "POST", body: fd, headers: { "X-CSRFToken": csrfToken() } });
        const html = await res.text();
        const box = document.createElement("div");
        // nosemgrep: insecure-innerhtml — HTML fragment from our own server (autoescaped Jinja template)
        box.innerHTML = html;
        const fresh = box.firstElementChild;
        if (fresh) {
          current.replaceWith(fresh);
          if (window.htmx) window.htmx.process(fresh);
          current = fresh;
        }
        if (!res.ok) throw new Error(String(res.status));
      } catch (e) {
        toast("Nie udało się wysłać grafiki.", { error: true });
        return;
      }
    }
    document.body.dispatchEvent(new CustomEvent("mapChanged", { detail: {} }));
    toast("Dodano grafikę.");
  }
  document.addEventListener("change", (ev) => {
    const input = ev.target.closest && ev.target.closest("[data-image-input]");
    if (input && input.files.length) uploadImages(input.closest("[data-gallery]"), [...input.files]);
  });
  document.addEventListener("dragover", (ev) => {
    const g = ev.target.closest && ev.target.closest("[data-gallery]");
    if (g && g.querySelector("[data-image-input]")) { ev.preventDefault(); g.classList.add("drag"); }
  });
  document.addEventListener("dragleave", (ev) => {
    const g = ev.target.closest && ev.target.closest("[data-gallery]");
    if (g) g.classList.remove("drag");
  });
  document.addEventListener("drop", (ev) => {
    const g = ev.target.closest && ev.target.closest("[data-gallery]");
    if (!g || !g.querySelector("[data-image-input]")) return;
    ev.preventDefault();
    g.classList.remove("drag");
    uploadImages(g, [...ev.dataTransfer.files]);
  });
  document.addEventListener("paste", (ev) => {
    const t = ev.target;
    if (t && (t.isContentEditable || ["INPUT", "TEXTAREA"].includes(t.tagName))) return;
    const files = [...(ev.clipboardData ? ev.clipboardData.files : [])].filter((f) => f.type.startsWith("image/"));
    const gallery = [...document.querySelectorAll("[data-gallery]")].find((g) => g.querySelector("[data-image-input]"));
    if (files.length && gallery) { ev.preventDefault(); uploadImages(gallery, files); }
  });

  // Recruitment mode countdown; the server enforces the deadline, the page reloads to show the locked map.
  document.querySelectorAll("[data-deadline]").forEach((el) => {
    const end = Date.parse(el.dataset.deadline);
    let timer = null;
    const tick = () => {
      const left = Math.max(0, Math.round((end - Date.now()) / 1000));
      el.textContent = "⏱ " + Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0");
      el.classList.toggle("urgent", left <= 300);
      if (left === 0 && timer) { clearInterval(timer); el.textContent = "⏱ Czas minął"; setTimeout(() => location.reload(), 1500); }
    };
    tick();
    if (end > Date.now()) timer = setInterval(tick, 1000);
  });
})();
