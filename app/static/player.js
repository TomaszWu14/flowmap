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
    parallel: () => "Bramka AND.",
    end: () => "Tu proces się kończy.",
  };
  let path = [], card = null, timer = null, playing = false, speed = 1, autoFirst = false, choices = null;
  let lanesStack = [];  // open AND splits: {split, rest: [edges], total}

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
    const split = n.type === "parallel" && outs.length > 1;
    if (n.type === "parallel") lines[0] = split ? "Ścieżki równoległe — wszystkie dzieją się jednocześnie:"
      : "Zbiegnięcie ścieżek — proces czeka, aż wszystkie się zakończą.";
    if (n.type === "decision" || split) outs.forEach((e) => lines.push(`• ${e.label || "dalej"} → ${by[e.target].title}`));
    else if (outs.length === 1) lines.push(dot(`Dalej: ${by[outs[0].target].title}`));
    else if (outs.length > 1) lines.push(`Dalej jedna z ${outs.length} ścieżek.`);
    else if (n.type !== "end") lines.push("⚠ Po tym kroku nic się nie dzieje — ślepy zaułek.");
    return lines;
  }

  function highlight() {
    const cy = fm().cy;
    cy.batch(() => {
      cy.elements().removeClass("play-current play-visited play-edge");
      cy.elements().not(".lane-el").addClass("play-dim");
      path.forEach((key, i) => {
        cy.getElementById(key).removeClass("play-dim").addClass("play-visited");
        if (i) cy.edges(`[source = "${path[i - 1]}"][target = "${key}"]`).removeClass("play-dim").addClass("play-edge");
      });
      cy.getElementById(path[path.length - 1]).addClass("play-current");
    });
  }

  function render(message) {
    if (!card) return;  // closed meanwhile (e.g. Esc during a token animation)
    const { by, out } = graph();
    const n = by[path[path.length - 1]];
    const outs = out[n.key] || [];
    card.replaceChildren();
    const head = el("div", "player-head");
    const chip = el("span", `type-chip t-${n.type}`, n.type_label || n.type);
    const body = n.icon && fm().icon(n.icon);
    if (body) {  // static bundled SVG, not user content
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      ["width", "height"].forEach((a) => svg.setAttribute(a, "14"));
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("fill", "none");
      svg.setAttribute("stroke", "currentColor");
      svg.setAttribute("stroke-width", "2");
      svg.setAttribute("class", "picto");
      // nosemgrep: insecure-document-method, insecure-innerhtml — static bundled icon SVG, not user content
      svg.innerHTML = body;
      chip.prepend(svg, " ");
    }
    head.append(chip, el("span", "muted", `Krok ${path.length}${n.actor ? " · " + n.actor : ""}`
      + (n.icon_label ? " · " + n.icon_label : "")));
    card.append(head, el("strong", "player-title", n.title));
    if (n.image_url) {
      const img = el("img", "player-img");
      img.src = n.image_url;
      img.alt = `Grafika kroku „${n.title}”`;
      img.addEventListener("load", () => place(anchor()));
      card.append(img);
    }
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

  // Wide maps: the card floats next to the step (or the moving token) and follows it.
  // Narrow maps (phones): the card stays docked at the bottom edge.
  const floating = () => wrap.clientWidth >= 700;

  function place(ele) {
    if (!card || !ele || !ele.length) return;
    card.classList.toggle("floating", floating());
    if (!floating()) { card.style.left = card.style.top = ""; return; }
    const mapEl = fm().cy.container();
    const bb = ele.renderedBoundingBox();
    const offL = mapEl.offsetLeft, offT = mapEl.offsetTop;
    const W = wrap.clientWidth, H = wrap.clientHeight, cw = card.offsetWidth, ch = card.offsetHeight;
    let left = offL + bb.x2 + 18, side = "right";
    if (left + cw > W - 8) { left = offL + bb.x1 - 18 - cw; side = "left"; }
    left = Math.max(8, Math.min(left, W - cw - 8));
    const top = Math.max(offT + 8, Math.min(offT + (bb.y1 + bb.y2) / 2 - ch / 2, H - ch - 8));
    card.style.left = left + "px";
    card.style.top = top + "px";
    card.dataset.side = side;
  }
  const anchor = () => {
    const cy = fm().cy;
    const token = cy.getElementById("__token");
    return token.length ? token : cy.getElementById(path[path.length - 1]);
  };

  function focus(key) {
    const { cy, minZoom } = fm();
    const zoom = Math.max(cy.zoom(), minZoom);
    const pos = cy.getElementById(key).position();
    let x = cy.width() / 2, y = cy.height() / 2;
    if (floating()) x = cy.width() * 0.36;  // leave room for the card on the right
    else if (card) y = (cy.height() - card.offsetHeight - 16) / 2;  // docked card covers the bottom
    cy.animate({ zoom, pan: { x: x - pos.x * zoom, y: y - pos.y * zoom } },
      { duration: ms(350), complete: () => place(anchor()) });
  }

  function show(message) {
    highlight();
    render(message);
    place(anchor());
    focus(path[path.length - 1]);
  }

  function schedule() {
    clearTimeout(timer);
    if (playing) timer = setTimeout(advance, ms(2200));
  }

  function advance() {
    const { by, out } = graph();
    const cur = by[path[path.length - 1]];
    const outs = out[cur.key] || [];
    const top = lanesStack[lanesStack.length - 1];
    const atJoin = cur.type === "parallel" && outs.length <= 1 && (out[cur.key] || []).length !== 0
      && !(cur.data && (cur.data.branches || []).length);
    if (top && top.rest.length && (atJoin || !outs.length)) {  // next parallel path, from the split again
      const edge = top.rest.shift();
      path.push(top.split);
      show(`Ścieżka równoległa ${top.total - top.rest.length} z ${top.total}.`);
      return travel(edge, playing);
    }
    if (top && !top.rest.length && atJoin) lanesStack.pop();
    if (cur.type === "parallel" && outs.length > 1) {
      lanesStack.push({ split: cur.key, rest: outs.slice(1), total: outs.length });
      return travel(outs[0], playing);
    }
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
      step: () => place(token),
      complete: () => {
        cy.remove("#__token");
        if (!card) return;
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
    lanesStack = [];
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

  // Keep the card next to the step when the user pans or zooms by hand.
  const follow = () => { if (card) place(anchor()); };
  const hook = () => { if (window.flowMap) window.flowMap.cy.on("viewport", follow); else setTimeout(hook, 200); };
  hook();
  window.addEventListener("resize", follow);

  // The map re-renders after every edit: the old path may not exist any more.
  document.addEventListener("flowmap:loaded", () => { if (card) close(); });

  document.addEventListener("keydown", (ev) => {
    const t = ev.target;
    if (!card || (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)))) return;
    const keys = { " ": toggle, ArrowRight: next, ArrowLeft: back, Escape: close };
    // nosemgrep: unsafe-dynamic-method — key picks a function from a fixed key map
    if (keys[ev.key]) { ev.preventDefault(); keys[ev.key](); }
  });
})();
