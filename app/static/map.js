// Process map: Cytoscape + dagre. Labels are plain text (Cytoscape never renders HTML).
(function () {
  const el = document.getElementById("map");
  if (!el || !window.cytoscape) return;
  if (window.cytoscapeDagre) cytoscape.use(window.cytoscapeDagre);

  const cfg = el.dataset;
  const readOnly = cfg.readonly === "1";
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const csrf = csrfMeta ? csrfMeta.content : "";
  let selected = null;
  let lastData = { nodes: [], edges: [] };
  const MIN_READABLE_ZOOM = 0.8;
  const LANE_H = 150;

  // Pictograms (Lucide SVG bodies from /static/icons.json), tinted per node and theme.
  let ICON_BODIES = {};
  const iconCache = {};
  function iconUri(key, color) {
    const body = ICON_BODIES[key];
    if (!body) return "none";
    const id = key + color;
    if (!iconCache[id]) {
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" `
        + `stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
      iconCache[id] = "data:image/svg+xml;utf8," + encodeURIComponent(svg);
    }
    return iconCache[id];
  }
  const hasIcon = (n) => Boolean(n.data("icon") && ICON_BODIES[n.data("icon")]);
  const ROLE_PALETTE = ["#2f6fdf", "#c2410c", "#15803d", "#7c3aed", "#b45309", "#0e7490", "#be185d", "#4d7c0f"];
  let colorMode = "type";
  try { colorMode = localStorage.getItem("fm-color-mode") || "type"; } catch (e) { /* ignore */ }
  const roles = () => [...new Set((lastData.nodes || []).map((n) => n.actor).filter(Boolean))].sort();
  const roleColor = (actor) => {
    const i = roles().indexOf(actor);
    return i < 0 ? css("--muted") : ROLE_PALETTE[i % ROLE_PALETTE.length];
  };
  const nodeColor = (n) => (colorMode === "role" && !["start", "end"].includes(n.data("type"))
    ? roleColor(n.data("actor")) : css("--t-" + n.data("type")));

  const GATEWAYS = ["decision", "parallel"];
  const SHAPES = {
    start: "round-rectangle", end: "round-rectangle", decision: "diamond", parallel: "diamond", screen: "rectangle",
    user_action: "round-rectangle", automation: "cut-rectangle", wait: "barrel", integration: "rhomboid",
  };

  function style() {
    return [
      { selector: "node", style: {
        "shape": (n) => SHAPES[n.data("type")] || "round-rectangle",
        "width": (n) => (GATEWAYS.includes(n.data("type")) ? 150 : 176),
        "height": (n) => (GATEWAYS.includes(n.data("type")) ? 96 : 66),
        "background-color": css("--surface"), "border-width": 2,
        "border-color": nodeColor,
        "label": "data(label)", "color": css("--ink"), "font-size": 11,
        "background-image": (n) => (hasIcon(n) ? iconUri(n.data("icon"), ["start", "end"].includes(n.data("type"))
          ? css("--surface") : nodeColor(n)) : "none"),
        "background-width": 20, "background-height": 20, "background-clip": "none",
        "background-position-x": 12, "background-position-y": "50%",
        "text-margin-x": (n) => (hasIcon(n) ? 12 : 0),
        "text-wrap": "wrap", "text-max-width": (n) => (GATEWAYS.includes(n.data("type")) ? 100 : hasIcon(n) ? 132 : 156),
        "text-valign": "center", "text-halign": "center",
      } },
      { selector: "node[type='parallel']", style: { "background-position-x": "50%", "background-position-y": "16%",
        "background-width": 16, "background-height": 16, "text-margin-x": 0, "text-margin-y": 8 } },
      { selector: "node[type='start'], node[type='end']", style: {
        "background-color": (n) => css("--t-" + n.data("type")), "color": css("--surface"), "font-weight": "bold",
      } },
      { selector: "node.pending", style: { "border-style": "double", "border-width": 5, "border-color": css("--accent") } },
      { selector: "node.issue", style: { "underlay-color": css("--danger"), "underlay-opacity": 0.18, "underlay-padding": 7 } },
      { selector: "node.diff-added", style: { "background-color": css("--ok"), "background-opacity": 0.22, "border-width": 3 } },
      { selector: "node.diff-changed", style: { "background-color": css("--warn"), "background-opacity": 0.28, "border-width": 3 } },
      { selector: "node.dim", style: { "opacity": 0.25 } },
      { selector: "node.match", style: { "border-width": 4, "border-color": css("--accent") } },
      { selector: ".play-dim", style: { "opacity": 0.3 } },
      { selector: "node.play-visited", style: { "border-color": css("--accent"), "border-width": 3 } },
      { selector: "node.play-current", style: { "border-width": 5, "underlay-color": css("--accent"),
        "underlay-opacity": 0.25, "underlay-padding": 10 } },
      { selector: "edge.play-edge", style: { "width": 3.5, "line-color": css("--accent"), "target-arrow-color": css("--accent") } },
      { selector: "node.token", style: { "shape": "ellipse", "width": 18, "height": 18, "background-color": css("--accent"),
        "border-width": 3, "border-color": css("--surface"), "label": "", "events": "no", "z-index": 99 } },
      { selector: "node.focus", style: { "overlay-color": css("--accent"), "overlay-opacity": 0.16, "overlay-padding": 6 } },
      { selector: "node.lane", style: { "shape": "rectangle", "background-color": css("--surface"),
        "background-opacity": 0.6, "border-width": 1, "border-color": css("--line"), "padding": 0, "label": "",
        "background-image": "none", "events": "no" } },
      { selector: "node.lane-odd", style: { "background-color": css("--surface-2") } },
      { selector: "node.lane-head", style: { "shape": "rectangle", "width": 150, "height": LANE_H - 2,
        "background-color": css("--surface"), "border-width": 0, "label": "data(label)", "font-size": 12,
        "font-weight": "bold", "color": css("--ink"), "text-valign": "center", "text-halign": "center",
        "text-margin-x": 0, "text-margin-y": 18, "text-wrap": "wrap", "text-max-width": 132,
        "background-image": (n) => iconUri(n.data("icon"), css("--ink")), "background-width": 26,
        "background-height": 26, "background-position-x": "50%", "background-position-y": "26%" } },
      { selector: "node.lane-anchor", style: { "width": 1, "height": LANE_H - 2, "opacity": 0, "events": "no",
        "label": "", "background-image": "none" } },
      { selector: "edge", style: {
        "width": 1.6, "line-color": css("--muted"), "target-arrow-color": css("--muted"), "target-arrow-shape": "triangle",
        "curve-style": "bezier", "label": "data(label)", "font-size": 10, "color": css("--ink"),
        "text-background-color": css("--bg"), "text-background-opacity": 1, "text-background-padding": 2,
      } },
      { selector: "edge[condition='error']", style: {
        "line-style": "dashed", "line-color": css("--danger"), "target-arrow-color": css("--danger"),
      } },
      { selector: "edge.taxi", style: { "curve-style": "taxi", "taxi-direction": "horizontal", "taxi-turn": 40 } },
    ];
  }

  const cy = cytoscape({
    container: el, style: style(), minZoom: 0.2, maxZoom: 2.5,
    boxSelectionEnabled: false, autoungrabify: readOnly,
  });
  document.addEventListener("themeChanged", () => cy.style(style()));

  function elements(data) {
    const lanes = lanesOn(data) ? data.lanes.order : null;
    const laneNodes = [];
    if (lanes) {
      lanes.forEach((role, i) => {
        const id = "lane-" + i;
        laneNodes.push({ group: "nodes", data: { id, type: "lane" }, classes: "lane-el lane" + (i % 2 ? " lane-odd" : "") },
          { group: "nodes", data: { id: "lanehead-" + i, parent: id, type: "lane-head", role,
            label: role || "Bez przypisanej roli", icon: data.lanes.icons[role] || "briefcase" }, classes: "lane-el lane-head" },
          { group: "nodes", data: { id: "laneend-" + i, parent: id, type: "lane-anchor" }, classes: "lane-el lane-anchor" });
      });
    }
    const nodes = data.nodes.map((n) => {
      const classes = [n.pending ? "pending" : "", n.issues.length ? "issue" : "",
        n.diff ? "diff-" + n.diff : ""].join(" ").trim();
      const label = n.title + (n.actor ? "\n— " + n.actor : "") + (n.issues.length ? "\n⚠ " + n.issues.length : "") + (n.comments ? "  💬 " + n.comments : "")
        + (n.images ? "  🖼 " + n.images : "");
      const item = { group: "nodes", data: { id: n.key, type: n.type, actor: n.actor || "", icon: n.type === "parallel" ? "plus" : (n.icon || ""), label: label },
        classes: classes };
      if (n.x !== null && n.y !== null) item.position = { x: n.x, y: n.y };
      if (lanes) item.data.parent = "lane-" + Math.max(0, lanes.indexOf(n.lane || ""));
      return item;
    });
    const edges = data.edges.map((e, i) => ({
      group: "edges",
      data: { id: "e" + i, source: e.source, target: e.target, label: e.label || "", condition: e.condition || "" },
      classes: lanes ? "taxi" : "",
    }));
    return laneNodes.concat(nodes, edges);
  }

  function updateChrome(data) {
    const score = document.getElementById("score-value");
    if (score) {
      score.textContent = data.score;
      const ring = document.getElementById("score-ring");
      ring.style.setProperty("--p", data.score);
      const color = data.score >= 80 ? css("--ok") : data.score >= 50 ? css("--warn") : css("--danger");
      ring.style.setProperty("--score-color", color);
      document.getElementById("score-label").textContent =
        data.issues.length ? data.issues.length + " do poprawy" : "kompletna";
    }
    const u = document.getElementById("btn-undo"); if (u) u.disabled = !data.can_undo;
    const r = document.getElementById("btn-redo"); if (r) r.disabled = !data.can_redo;
  }

  function inView(node) {
    const bb = node.renderedBoundingBox();
    return bb.x1 >= 0 && bb.y1 >= 0 && bb.x2 <= cy.width() && bb.y2 <= cy.height();
  }

  // Stable layout: steps keep the place they had in the previous render; new steps land under their
  // predecessor. Only the first render and "Ułóż" run the full dagre layout.
  const prev = {};
  let firstLoad = true, forceLayout = false;
  const relayout = document.querySelector("button[title='Ułóż mapę automatycznie']");
  if (relayout) relayout.addEventListener("click", () => { forceLayout = true; });

  function placeNew(data) {
    const parents = {};
    data.edges.forEach((e) => { (parents[e.target] = parents[e.target] || []).push(e.source); });
    const placed = {};
    data.nodes.forEach((n) => { if (prev[n.key]) placed[n.key] = prev[n.key]; });
    const maxY = Math.max(0, ...Object.values(placed).map((p) => p.y));
    const busy = (pos) => Object.values(placed).some((p) => Math.abs(p.x - pos.x) < 195 && Math.abs(p.y - pos.y) < 100);
    let waiting = data.nodes.filter((n) => !placed[n.key]);
    for (let pass = 0; waiting.length && pass < 60; pass++) {
      waiting = waiting.filter((n) => {
        const from = (parents[n.key] || []).find((k) => placed[k]);
        if (!from && pass < 59) return true;  // its parent is new too: place that one first
        const base = from ? placed[from] : { x: 0, y: maxY };
        const pos = { x: base.x, y: base.y + 135 };
        while (busy(pos)) pos.x += 215;
        placed[n.key] = pos;
        return false;
      });
    }
    return { placed, parents };
  }

  const iconsReady = fetch(cfg.iconsUrl || "/static/icons.json").then((r) => (r.ok ? r.json() : {}))
    .then((b) => { ICON_BODIES = b; }).catch(() => {});

  // --- swimlanes: one lane per workstation, steps left to right ---------------------------
  let viewPref = null, viewChanged = false;
  try { viewPref = localStorage.getItem("fm-view"); } catch (e) { /* ignore */ }
  function lanesOn(data) {
    const order = (data && data.lanes && data.lanes.order) || [];
    return viewPref ? viewPref === "lanes" : order.length >= 2;
  }

  function layoutLanes(data, animate) {
    const steps = cy.nodes().not(".lane-el");
    steps.layout({ name: window.cytoscapeDagre ? "dagre" : "breadthfirst", rankDir: "LR", nodeSep: 30,
      rankSep: 80, fit: false, animate: false }).run();
    const order = data.lanes.order;
    const laneOf = (n) => Math.max(0, order.indexOf((data.nodes.find((x) => x.key === n.id()) || {}).lane || ""));
    const xs = {};
    steps.forEach((n) => { xs[n.id()] = n.position("x"); });
    const byLane = {};
    steps.forEach((n) => { (byLane[laneOf(n)] = byLane[laneOf(n)] || []).push(n); });
    Object.values(byLane).forEach((ns) => {  // no two steps of one lane on top of each other
      ns.sort((a, b) => xs[a.id()] - xs[b.id()]);
      let last = -Infinity;
      ns.forEach((n) => { xs[n.id()] = Math.max(xs[n.id()], last + 205); last = xs[n.id()]; });
    });
    const minX = Math.min(...Object.values(xs)), maxX = Math.max(...Object.values(xs));
    steps.forEach((n) => {
      const target = { x: xs[n.id()], y: laneOf(n) * LANE_H + LANE_H / 2 };
      if (animate && prev[n.id()]) {
        n.position(prev[n.id()]);
        n.animate({ position: target }, { duration: 320, easing: "ease-out-cubic" });
      } else {
        n.position(target);
      }
    });
    order.forEach((_, i) => {
      cy.getElementById("lanehead-" + i).position({ x: minX - 210, y: i * LANE_H + LANE_H / 2 });
      cy.getElementById("laneend-" + i).position({ x: maxX + 120, y: i * LANE_H + LANE_H / 2 });
    });
  }

  const LANE_CHOICES = { briefcase: "Biuro", warehouse: "Magazyn", truck: "Transport", user: "Klient / osoba",
    users: "Zespół", server: "System", bot: "Automat" };
  const menu = document.createElement("div");
  menu.className = "lane-menu";
  menu.hidden = true;
  el.parentElement.append(menu);
  async function saveLane(body) {
    const res = await fetch(cfg.lanesUrl, { method: "POST", body: JSON.stringify(body),
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf } });
    menu.hidden = true;
    if (!res.ok && window.flowToast) window.flowToast("Nie udało się zapisać toru.", { error: true });
    load();
  }
  function laneMenu(head) {
    if (!cfg.lanesUrl) return;
    const role = head.data("role");
    menu.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = head.data("label");
    menu.append(title);
    const icons = document.createElement("div");
    icons.className = "lane-menu-icons";
    Object.entries(LANE_CHOICES).forEach(([key, name]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn small" + (key === head.data("icon") ? " primary" : "");
      b.title = name;
      b.setAttribute("aria-label", "Ikona stanowiska: " + name);
      const img = document.createElement("img");
      img.src = iconUri(key, key === head.data("icon") ? "#ffffff" : css("--ink"));
      img.alt = "";
      img.width = img.height = 18;
      b.append(img);
      b.addEventListener("click", () => saveLane({ role, icon: key }));
      icons.append(b);
    });
    menu.append(icons);
    const row = document.createElement("div");
    row.className = "row";
    [["↑ Wyżej", -1], ["↓ Niżej", 1]].forEach(([label, move]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn small";
      b.textContent = label;
      b.addEventListener("click", () => saveLane({ role, move }));
      row.append(b);
    });
    const close = document.createElement("button");
    close.type = "button";
    close.className = "btn small";
    close.textContent = "Zamknij";
    close.addEventListener("click", () => { menu.hidden = true; });
    row.append(close);
    menu.append(row);
    const p = head.renderedPosition();
    menu.style.left = Math.max(8, p.x + 90) + "px";
    menu.style.top = Math.max(60, p.y - 40) + "px";
    menu.hidden = false;
  }
  cy.on("viewport", () => { menu.hidden = true; });

  async function load(focus) {
    await iconsReady;
    const res = await fetch(cfg.graphUrl, { headers: { Accept: "application/json" } });
    if (!res.ok) return;
    const data = await res.json();
    cy.nodes().not(".token, .lane-el").forEach((n) => { prev[n.id()] = { ...n.position() }; });
    const allPositioned = data.nodes.every((n) => n.x !== null && n.y !== null);
    const inLanes = lanesOn(data);
    const refit = firstLoad || forceLayout || viewChanged;
    const stable = !inLanes && !refit && data.nodes.some((n) => prev[n.key]);
    cy.elements().remove();
    cy.add(elements(data));
    if (inLanes) {
      layoutLanes(data, !refit);
      if (refit) {
        cy.fit(cy.elements(), 40);
        if (cy.zoom() < MIN_READABLE_ZOOM) {  // big map: stay readable, start at the lane headers (top-left)
          cy.zoom(MIN_READABLE_ZOOM);
          const bb = cy.elements().boundingBox();
          cy.pan({ x: 16 - bb.x1 * MIN_READABLE_ZOOM, y: 16 - bb.y1 * MIN_READABLE_ZOOM });
        }
      }
    } else if (stable) {
      const { placed, parents } = placeNew(data);
      cy.nodes().forEach((n) => {
        const target = placed[n.id()];
        if (!target) return;
        if (prev[n.id()]) { n.position(target); return; }
        const from = (parents[n.id()] || []).map((k) => placed[k]).find(Boolean) || target;
        n.position({ ...from });
        n.style("opacity", 0);
        n.animate({ position: target, style: { opacity: 1 } }, { duration: 320, easing: "ease-out-cubic" });
      });
    } else if (allPositioned && !forceLayout) {
      cy.layout({ name: "preset", fit: true, padding: 60 }).run();
    } else {
      const animate = forceLayout && Object.keys(prev).length > 0;
      if (animate) cy.nodes().forEach((n) => { if (prev[n.id()]) n.position(prev[n.id()]); });
      cy.layout({ name: window.cytoscapeDagre ? "dagre" : "breadthfirst", rankDir: "TB", nodeSep: 40, rankSep: 60,
        fit: true, padding: 60, directed: true, animate, animationDuration: 450 }).run();
    }
    if (focus !== undefined) selected = focus || null;
    if (!stable && !inLanes && !forceLayout) {
      if (cy.zoom() > 1.2) { cy.zoom(1.2); cy.center(); }
      if (cy.zoom() < MIN_READABLE_ZOOM) {
        // Whole map would shrink labels below ~9 px: stay readable, center on the step in focus.
        const pending = data.nodes.find((n) => n.pending);
        const start = data.nodes.find((n) => n.type === "start");
        const key = selected || (pending && pending.key) || (start && start.key);
        cy.zoom(MIN_READABLE_ZOOM);
        const node = key && cy.getElementById(key);
        if (node && node.length) {
          // Process flows downward: keep the focused step high, the start step near the top edge.
          const y = cy.height() * (start && key === start.key ? 0.12 : 0.25);
          const pos = node.position();
          cy.pan({ x: cy.width() / 2 - pos.x * MIN_READABLE_ZOOM, y: y - pos.y * MIN_READABLE_ZOOM });
        }
      }
    }
    firstLoad = false;
    viewChanged = false;
    cy.nodes(".lane-el").ungrabify();
    if (inLanes) cy.nodes().ungrabify();  // positions come from the lanes layout
    forceLayout = false;
    for (const k of Object.keys(prev)) delete prev[k];
    updateChrome(data);
    lastData = data;
    document.dispatchEvent(new CustomEvent("flowmap:loaded"));
    cy.nodes().removeClass("focus");
    if (selected && cy.getElementById(selected).length) {
      const node = cy.getElementById(selected);
      node.addClass("focus");
      if (!inView(node)) cy.animate({ center: { eles: node }, duration: 250 });
    }
  }

  // --- hover card: details of a step without opening the panel ---------------------------
  const tip = document.createElement("div");
  tip.className = "map-tip";
  tip.hidden = true;
  el.parentElement.append(tip);
  const tipLine = (label, value) => {
    if (!value) return;
    const p = document.createElement("p");
    const b = document.createElement("b");
    b.textContent = label + ": ";
    p.append(b, document.createTextNode(value));
    tip.append(p);
  };
  if (window.matchMedia("(hover: hover)").matches) {
    cy.on("mouseover", "node", (ev) => {
      const n = lastData.nodes.find((x) => x.key === ev.target.id());
      if (!n) return;
      tip.replaceChildren();
      const head = document.createElement("strong");
      head.textContent = n.title;
      tip.append(head);
      tipLine("Typ", n.type_label);
      tipLine("Czynność", n.icon_label);
      tipLine("Rola", n.actor);
      tipLine("Pokazuje", (n.outputs || []).join(", "));
      tipLine("Dane", (n.inputs || []).join(", "));
      tipLine("Opis", n.description);
      tipLine("Do poprawy", (n.issues || []).join(" · "));
      tipLine("Komentarze", n.comments ? String(n.comments) : "");
      if (n.image_url) {
        const img = document.createElement("img");
        img.src = n.image_url;
        img.alt = "";
        img.className = "map-tip-img";
        tip.append(img);
      }
      const pos = ev.target.renderedPosition();
      tip.style.left = Math.min(pos.x + 20, el.clientWidth - 300) + "px";
      tip.style.top = Math.max(pos.y + 40, 60) + "px";
      tip.hidden = false;
    });
    cy.on("mouseout", "node", () => { tip.hidden = true; });
    cy.on("viewport tapstart", () => { tip.hidden = true; });
  }

  // --- colours by type or by role ----------------------------------------------------------
  const legend = el.parentElement.querySelector(".legend");
  if (legend) {
    const typeLegend = legend.innerHTML;
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "legend-toggle";
    const paint = () => {
      legend.innerHTML = colorMode === "role" ? "" : typeLegend;
      if (colorMode === "role") {
        roles().forEach((r) => {
          const s = document.createElement("span");
          const i = document.createElement("i");
          i.style.setProperty("--c", roleColor(r));
          s.append(i, document.createTextNode(r));
          legend.append(s);
        });
      }
      toggle.textContent = colorMode === "role" ? "Kolory: role ⇄" : "Kolory: typy ⇄";
      toggle.title = "Przełącz kolorowanie kroków: typ kroku albo rola";
      legend.prepend(toggle);
      legend.removeAttribute("aria-hidden");
    };
    toggle.addEventListener("click", () => {
      colorMode = colorMode === "role" ? "type" : "role";
      try { localStorage.setItem("fm-color-mode", colorMode); } catch (e) { /* ignore */ }
      cy.style(style());
      paint();
    });
    document.addEventListener("flowmap:loaded", paint);
  }

  // --- full screen (button + F) ------------------------------------------------------------
  const wrapEl = el.closest(".map-wrap");
  const bar = wrapEl && wrapEl.querySelector(".map-toolbar");
  if (bar) {
    const view = document.createElement("button");
    view.type = "button";
    view.className = "btn small";
    const label = () => {
      const on = lanesOn(lastData);
      view.textContent = on ? "↧ Przepływ" : "▤ Tory";
      view.title = on ? "Widok przepływu (kroki z góry na dół)" : "Widok torów: pas dla każdego stanowiska pracy";
    };
    view.addEventListener("click", () => {
      viewPref = lanesOn(lastData) ? "flow" : "lanes";
      try { localStorage.setItem("fm-view", viewPref); } catch (e) { /* ignore */ }
      viewChanged = true;
      load();
    });
    bar.insertBefore(view, bar.children[2] || null);
    document.addEventListener("flowmap:loaded", label);
  }
  if (wrapEl && bar && wrapEl.requestFullscreen) {
    const fs = document.createElement("button");
    fs.type = "button";
    fs.className = "btn small";
    fs.textContent = "⛶";
    fs.title = "Pełny ekran (F)";
    fs.setAttribute("aria-label", "Pełny ekran");
    const flip = () => (document.fullscreenElement ? document.exitFullscreen() : wrapEl.requestFullscreen());
    fs.addEventListener("click", flip);
    bar.append(fs);
    document.addEventListener("fullscreenchange", () => setTimeout(() => cy.resize(), 50));
    document.addEventListener("keydown", (ev) => {
      const t = ev.target;
      if (ev.key.toLowerCase() !== "f" || ev.ctrlKey || ev.metaKey || ev.altKey) return;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      ev.preventDefault();
      flip();
    });
  }

  function openNode(node) {
    if (!cfg.panelUrl) return;
    selected = node.id();
    cy.nodes().removeClass("focus");
    node.addClass("focus");
    window.htmx.ajax("GET", cfg.panelUrl + "?node=" + encodeURIComponent(selected), { target: "#panel-body", swap: "innerHTML" });
    const panel = document.getElementById("panel");
    if (panel) panel.classList.remove("collapsed");
  }

  cy.on("tap", "node", (ev) => {
    if (ev.target.hasClass("lane-head")) return laneMenu(ev.target);
    if (ev.target.hasClass("lane-el")) return;
    openNode(ev.target);
  });

  // Search: highlight matching steps, Enter jumps to the next one and opens it.
  const search = document.getElementById("map-search");
  const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ł/g, "l");
  let matches = [], current = -1;
  function runSearch() {
    const q = fold(search.value.trim());
    cy.nodes().removeClass("match dim");
    matches = q ? cy.nodes().not(".lane-el").filter((n) => fold(n.data("label")).includes(q)).toArray() : [];
    current = -1;
    if (q) {
      cy.nodes().not(".lane-el").addClass("dim");
      matches.forEach((n) => n.removeClass("dim").addClass("match"));
    }
    const count = document.getElementById("map-search-count");
    const n = matches.length, few = n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14);
    if (count) count.textContent = !q ? "" : !n ? "brak" : n + (n === 1 ? " wynik" : few ? " wyniki" : " wyników");
  }
  if (search) {
    search.addEventListener("input", runSearch);
    search.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && matches.length) {
        ev.preventDefault();
        current = (current + 1) % matches.length;
        const node = matches[current];
        cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), MIN_READABLE_ZOOM), duration: 200 });
        openNode(node);
      } else if (ev.key === "Escape") {
        search.value = "";
        runSearch();
        search.blur();
      }
    });
  }

  // Keyboard: 1–9 pick a tile, I = "Inne", Ctrl+Z / Ctrl+Shift+Z (Ctrl+Y) undo / redo, / or Ctrl+F = search.
  function typing(el) {
    return el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
  }
  function press(id) {
    const btn = document.getElementById(id);
    if (btn && !btn.disabled) btn.click();
  }
  document.addEventListener("keydown", (ev) => {
    const mod = ev.ctrlKey || ev.metaKey;
    if (search && ((mod && ev.key.toLowerCase() === "f") || (ev.key === "/" && !typing(ev.target)))) {
      ev.preventDefault();
      search.focus();
      search.select();
      return;
    }
    if (typing(ev.target)) return;
    if (mod && ev.key.toLowerCase() === "z") {
      ev.preventDefault();
      press(ev.shiftKey ? "btn-redo" : "btn-undo");
    } else if (mod && ev.key.toLowerCase() === "y") {
      ev.preventDefault();
      press("btn-redo");
    } else if (!mod && !ev.altKey && /^[1-9]$/.test(ev.key)) {
      const tile = document.querySelectorAll("#panel-body .tile")[Number(ev.key) - 1];
      if (tile) { ev.preventDefault(); tile.click(); }
    } else if (!mod && !ev.altKey && ev.key.toLowerCase() === "i") {
      const other = document.querySelector("#panel-body details.other");
      if (other) {
        ev.preventDefault();
        other.open = true;
        const field = other.querySelector("textarea, input:not([type=hidden])");
        if (field) field.focus();
      }
    }
  });

  if (!readOnly && cfg.positionsUrl) {
    cy.on("dragfree", "node", () => {
      if (lanesOn(lastData)) return;
      const pos = {};
      cy.nodes().forEach((n) => { pos[n.id()] = [Math.round(n.position("x")), Math.round(n.position("y"))]; });
      fetch(cfg.positionsUrl, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf }, body: JSON.stringify(pos),
      });
    });
  }

  window.flowMap = { cy, data: () => lastData, minZoom: MIN_READABLE_ZOOM, icon: (k) => ICON_BODIES[k] || "" };  // player.js
  document.body.addEventListener("mapChanged", (ev) => load(ev.detail ? ev.detail.focus : undefined));
  load();
})();
