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
  const MIN_READABLE_ZOOM = 0.8;

  const SHAPES = {
    start: "round-rectangle", end: "round-rectangle", decision: "diamond", screen: "rectangle",
    user_action: "round-rectangle", automation: "cut-rectangle", wait: "barrel", integration: "rhomboid",
  };

  function style() {
    return [
      { selector: "node", style: {
        "shape": (n) => SHAPES[n.data("type")] || "round-rectangle",
        "width": (n) => (n.data("type") === "decision" ? 150 : 176),
        "height": (n) => (n.data("type") === "decision" ? 96 : 66),
        "background-color": css("--surface"), "border-width": 2,
        "border-color": (n) => css("--t-" + n.data("type")),
        "label": "data(label)", "color": css("--ink"), "font-size": 11,
        "text-wrap": "wrap", "text-max-width": (n) => (n.data("type") === "decision" ? 100 : 156),
        "text-valign": "center", "text-halign": "center",
      } },
      { selector: "node[type='start'], node[type='end']", style: {
        "background-color": (n) => css("--t-" + n.data("type")), "color": css("--surface"), "font-weight": "bold",
      } },
      { selector: "node.pending", style: { "border-style": "double", "border-width": 5, "border-color": css("--accent") } },
      { selector: "node.issue", style: { "underlay-color": css("--danger"), "underlay-opacity": 0.18, "underlay-padding": 7 } },
      { selector: "node.diff-added", style: { "background-color": css("--ok"), "background-opacity": 0.22, "border-width": 3 } },
      { selector: "node.diff-changed", style: { "background-color": css("--warn"), "background-opacity": 0.28, "border-width": 3 } },
      { selector: "node.dim", style: { "opacity": 0.25 } },
      { selector: "node.match", style: { "border-width": 4, "border-color": css("--accent") } },
      { selector: "node.focus", style: { "overlay-color": css("--accent"), "overlay-opacity": 0.16, "overlay-padding": 6 } },
      { selector: "edge", style: {
        "width": 1.6, "line-color": css("--muted"), "target-arrow-color": css("--muted"), "target-arrow-shape": "triangle",
        "curve-style": "bezier", "label": "data(label)", "font-size": 10, "color": css("--ink"),
        "text-background-color": css("--bg"), "text-background-opacity": 1, "text-background-padding": 2,
      } },
      { selector: "edge[condition='error']", style: {
        "line-style": "dashed", "line-color": css("--danger"), "target-arrow-color": css("--danger"),
      } },
    ];
  }

  const cy = cytoscape({
    container: el, style: style(), minZoom: 0.2, maxZoom: 2.5,
    boxSelectionEnabled: false, autoungrabify: readOnly,
  });
  document.addEventListener("themeChanged", () => cy.style(style()));

  function elements(data) {
    const nodes = data.nodes.map((n) => {
      const classes = [n.pending ? "pending" : "", n.issues.length ? "issue" : "",
        n.diff ? "diff-" + n.diff : ""].join(" ").trim();
      const label = n.title + (n.actor ? "\n— " + n.actor : "") + (n.issues.length ? "\n⚠ " + n.issues.length : "") + (n.comments ? "  💬 " + n.comments : "");
      const item = { group: "nodes", data: { id: n.key, type: n.type, label: label }, classes: classes };
      if (n.x !== null && n.y !== null) item.position = { x: n.x, y: n.y };
      return item;
    });
    const edges = data.edges.map((e, i) => ({
      group: "edges",
      data: { id: "e" + i, source: e.source, target: e.target, label: e.label || "", condition: e.condition || "" },
    }));
    return nodes.concat(edges);
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

  async function load(focus) {
    const res = await fetch(cfg.graphUrl, { headers: { Accept: "application/json" } });
    if (!res.ok) return;
    const data = await res.json();
    const allPositioned = data.nodes.every((n) => n.x !== null && n.y !== null);
    cy.elements().remove();
    cy.add(elements(data));
    const layout = allPositioned
      ? { name: "preset", fit: true, padding: 60 }
      : { name: window.cytoscapeDagre ? "dagre" : "breadthfirst", rankDir: "TB", nodeSep: 40, rankSep: 60,
          fit: true, padding: 60, directed: true };
    cy.layout(layout).run();
    if (focus !== undefined) selected = focus || null;
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
    updateChrome(data);
    cy.nodes().removeClass("focus");
    if (selected && cy.getElementById(selected).length) {
      const node = cy.getElementById(selected);
      node.addClass("focus");
      if (!inView(node)) cy.animate({ center: { eles: node }, duration: 200 });
    }
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

  cy.on("tap", "node", (ev) => openNode(ev.target));

  // Search: highlight matching steps, Enter jumps to the next one and opens it.
  const search = document.getElementById("map-search");
  const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ł/g, "l");
  let matches = [], current = -1;
  function runSearch() {
    const q = fold(search.value.trim());
    cy.nodes().removeClass("match dim");
    matches = q ? cy.nodes().filter((n) => fold(n.data("label")).includes(q)).toArray() : [];
    current = -1;
    if (q) {
      cy.nodes().addClass("dim");
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
      const pos = {};
      cy.nodes().forEach((n) => { pos[n.id()] = [Math.round(n.position("x")), Math.round(n.position("y"))]; });
      fetch(cfg.positionsUrl, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf }, body: JSON.stringify(pos),
      });
    });
  }

  document.body.addEventListener("mapChanged", (ev) => load(ev.detail ? ev.detail.focus : undefined));
  load();
})();
