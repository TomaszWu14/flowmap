// Flow playback: a token travels along the map and every step is narrated from the map data (no AI).
(function () {
  const wrap = document.querySelector(".map-wrap");
  const toolbar = wrap && wrap.querySelector(".map-toolbar");
  if (!toolbar) return;

  const SPEEDS = [0.5, 1, 2];
  const MAX_STEPS = 60;
  const TYPE_TEXT = {
    start: () => "Tu zaczyna się proces.",
    screen: (who) => `${who} widzi ten ekran.`,
    user_action: (who) => `Działanie wykonuje: ${who}.`,
    automation: () => "System robi to automatycznie, bez udziału człowieka.",
    integration: () => "Wymiana danych z systemem zewnętrznym.",
    wait: () => "Proces czeka na zdarzenie albo odpowiedź.",
    decision: (who) => `Decyzja — ${who} wybiera dalszą ścieżkę:`,
    end: () => "Tu proces się kończy.",
  };
  let path = [], card = null, timer = null, playing = false, speed = 1, autoFirst = false, choices = null;

  const fm = () => window.flowMap;
  const ms = (base) => base / SPEEDS[speed];

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;  // user content is always text, never HTML
    return e;
  }

  function graph() {
    const data = fm().data();
    const by = {}, out = {};
    data.nodes.forEach((n) => { by[n.key] = n; });
    data.edges.forEach((e) => { (out[e.source] = out[e.source] || []).push(e); });
    return { by, out, start: data.nodes.find((n) => n.type === "start") };
  }

  const dot = (s) => (/[.!?…:]$/.test(s) ? s : s + ".");

  function narrate(n, outs, by) {
    const lines = [(TYPE_TEXT[n.type] || (() => ""))(n.actor || "użytkownik")];
    if (n.outputs && n.outputs.length) lines.push(`${n.type === "screen" ? "Pokazuje" : "Wynik"}: ${n.outputs.join(", ")}.`);
    if (n.inputs && n.inputs.length) lines.push(`Dane: ${n.inputs.join(", ")}.`);
    if (n.description) lines.push(dot(n.description));
    if (n.type === "decision") outs.forEach((e) => lines.push(`• ${e.label || "dalej"} → ${by[e.target].title}`));
    else if (outs.length === 1) lines.push(dot(`Dalej: ${by[outs[0].target].title}`));
    else if (outs.length > 1) lines.push(`Dalej jedna z ${outs.length} ścieżek.`);
    else if (n.type !== "end") lines.push("⚠ Po tym kroku nic się nie dzieje — ślepy zaułek.");
    return lines;
  }

  function highlight() {
    const cy = fm().cy;
    cy.batch(() => {
      cy.elements().removeClass("play-current play-visited play-edge").addClass("play-dim");
      path.forEach((key, i) => {
        cy.getElementById(key).removeClass("play-dim").addClass("play-visited");
        if (i) cy.edges(`[source = "${path[i - 1]}"][target = "${key}"]`).removeClass("play-dim").addClass("play-edge");
      });
      cy.getElementById(path[path.length - 1]).addClass("play-current");
    });
  }

  function render(message) {
    const { by, out } = graph();
    const n = by[path[path.length - 1]];
    const outs = out[n.key] || [];
    card.replaceChildren();
    const head = el("div", "player-head");
    head.append(el("span", `type-chip t-${n.type}`, n.type_label || n.type),
      el("span", "muted", `Krok ${path.length}${n.actor ? " · " + n.actor : ""}`));
    card.append(head, el("strong", "player-title", n.title));
    narrate(n, outs, by).forEach((line) => card.append(el("p", "player-line", line)));
    if (message) card.append(el("div", "alert info", message));
    if (choices) {
      const box = el("div", "player-choices");
      choices.forEach((e, i) => {
        const b = el("button", `btn small ${e.condition === "error" ? "danger" : i === 0 ? "primary" : ""}`,
          `${e.label || "dalej"} → ${by[e.target].title}`);
        b.type = "button";
        b.addEventListener("click", () => { choices = null; travel(e, true); });
        box.append(b);
      });
      card.append(box);
    }
    const controls = el("div", "player-controls");
    const button = (label, title, fn) => {
      const b = el("button", "btn small", label);
      b.type = "button";
      b.title = title;
      b.setAttribute("aria-label", title);
      b.addEventListener("click", fn);
      controls.append(b);
    };
    button("⏮", "Krok wstecz (←)", back);
    button(playing ? "⏸" : "▶", playing ? "Pauza (spacja)" : "Odtwórz (spacja)", toggle);
    button("⏭", "Następny krok (→)", next);
    button(`${SPEEDS[speed]}×`, "Prędkość", () => { speed = (speed + 1) % SPEEDS.length; render(); });
    button("↺", "Od nowa", start);
    button("✕", "Zamknij (Esc)", close);
    card.append(controls);
    const auto = el("label", "player-auto");
    const box = el("input");
    box.type = "checkbox";
    box.checked = autoFirst;
    box.addEventListener("change", () => { autoFirst = box.checked; });
    auto.append(box, document.createTextNode(" na decyzjach idź pierwszą gałęzią"));
    card.append(auto);
  }

  function focus(key) {
    // Center the step in the part of the map the card does not cover (on phones the card spans the width).
    const { cy, minZoom } = fm();
    const zoom = Math.max(cy.zoom(), minZoom);
    const covered = card && card.offsetWidth > cy.width() * 0.6 ? card.offsetHeight + 16 : 0;
    const pos = cy.getElementById(key).position();
    cy.animate({ zoom, pan: { x: cy.width() / 2 - pos.x * zoom, y: (cy.height() - covered) / 2 - pos.y * zoom } },
      { duration: ms(350) });
  }

  function show(message) {
    highlight();
    render(message);
    focus(path[path.length - 1]);
  }

  function schedule() {
    clearTimeout(timer);
    if (playing) timer = setTimeout(advance, ms(2200));
  }

  function advance() {
    const { out } = graph();
    const outs = out[path[path.length - 1]] || [];
    if (!outs.length || path.length >= MAX_STEPS) {
      playing = false;
      show(path.length >= MAX_STEPS ? `Zatrzymano po ${MAX_STEPS} krokach — czy to nie pętla?` : "Koniec przejścia.");
      return;
    }
    if (outs.length > 1 && !autoFirst) {
      playing = false;
      choices = outs;
      show("Wybierz ścieżkę, którą ma pójść proces.");
      return;
    }
    travel(outs.length > 1 ? (outs.find((e) => e.condition !== "error") || outs[0]) : outs[0], playing);
  }

  function travel(edge, keepPlaying) {
    const { cy } = fm();
    const from = cy.getElementById(edge.source).position();
    const to = cy.getElementById(edge.target).position();
    cy.remove("#__token");
    const token = cy.add({ group: "nodes", data: { id: "__token", type: "token", label: "" }, classes: "token",
      position: { x: from.x, y: from.y } });
    token.animate({ position: { x: to.x, y: to.y } }, {
      duration: ms(700),
      complete: () => {
        cy.remove("#__token");
        path.push(edge.target);
        playing = keepPlaying;
        show();
        schedule();
      },
    });
  }

  function toggle() {
    if (!card) return start();
    choices = null;
    playing = !playing;
    render();
    if (playing) advance();
    else clearTimeout(timer);
  }

  function next() { playing = false; clearTimeout(timer); choices = null; advance(); }

  function back() {
    playing = false;
    clearTimeout(timer);
    choices = null;
    if (path.length > 1) path.pop();
    show();
  }

  function start() {
    const { start: first } = graph();
    if (!first) return;
    clearTimeout(timer);
    if (!card) {
      card = el("section", "player");
      card.setAttribute("aria-label", "Odtwarzanie procesu");
      card.setAttribute("aria-live", "polite");
      wrap.append(card);
    }
    const panel = document.getElementById("panel");
    if (panel && window.matchMedia("(max-width: 900px)").matches) panel.classList.add("collapsed");
    path = [first.key];
    choices = null;
    playing = true;
    show();
    schedule();
  }

  function close() {
    clearTimeout(timer);
    playing = false;
    if (card) card.remove();
    card = null;
    const cy = fm() && fm().cy;
    if (cy) {
      cy.remove("#__token");
      cy.elements().removeClass("play-current play-visited play-edge play-dim");
    }
  }

  const open = el("button", "btn small", "▶ Odtwórz");
  open.type = "button";
  open.title = "Odtwórz przepływ krok po kroku, z opisem";
  open.addEventListener("click", () => (card ? close() : start()));
  toolbar.insertBefore(open, toolbar.children[1] || null);

  // The map re-renders after every edit: the old path may not exist any more.
  document.addEventListener("flowmap:loaded", () => { if (card) close(); });

  document.addEventListener("keydown", (ev) => {
    const t = ev.target;
    if (!card || (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)))) return;
    const keys = { " ": toggle, ArrowRight: next, ArrowLeft: back, Escape: close };
    if (keys[ev.key]) { ev.preventDefault(); keys[ev.key](); }
  });
})();
