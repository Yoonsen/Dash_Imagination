// Client-side table sorting for place lists and collocations.
// Sorts rendered rows in the browser to avoid server roundtrips.
(function () {
  function parseHeaderKey(btn) {
    const dataKey = btn.getAttribute("data-key");
    if (dataKey) return dataKey;
    const rawId = btn.getAttribute("id");
    if (!rawId) return null;
    try {
      const obj = JSON.parse(rawId);
      return obj.key || null;
    } catch (e) {
      return null;
    }
  }

  function getCellValue(row, key) {
    const cells = row.children;
    if (!cells || cells.length < 4) return "";
    if (key === "token") return cells[0].textContent || "";
    if (key === "name") return cells[1].textContent || "";
    if (key === "book_count") return Number(cells[2].textContent || 0);
    if (key === "frequency") return Number(cells[3].textContent || 0);
    return "";
  }

  function attachSorter(container) {
    if (!container) return;
    const headerButtons = container.querySelectorAll(".places-sort-header");
    if (!headerButtons.length) return;

    const state = { dir: {} }; // per-key direction

    headerButtons.forEach((btn) => {
      const key = parseHeaderKey(btn);
      if (!key) return;
      state.dir[key] = "desc";
      const handler = (e) => {
        // prevent Dash callbacks from re-sorting server-side; keep client-only
        e.preventDefault();
        e.stopPropagation();
        const rows = Array.from(container.querySelectorAll(".place-item"));
        if (!rows.length) return;
        const parent = rows[0].parentNode;
        const currentDir = state.dir[key] || "desc";
        const nextDir = currentDir === "desc" ? "asc" : "desc";
        state.dir[key] = nextDir;

        rows.sort((a, b) => {
          const va = getCellValue(a, key);
          const vb = getCellValue(b, key);
          if (va === vb) return 0;
          if (typeof va === "number" && typeof vb === "number") {
            return nextDir === "asc" ? va - vb : vb - va;
          }
          return nextDir === "asc"
            ? String(va).localeCompare(String(vb))
            : String(vb).localeCompare(String(va));
        });

        rows.forEach((r) => parent.appendChild(r));
      };

      if (btn.__clientSortHandler) {
        btn.removeEventListener("click", btn.__clientSortHandler, true);
      }
      btn.__clientSortHandler = handler;
      btn.addEventListener("click", handler, { capture: true });
    });
  }

  function initAll() {
    ["places-frequency-table", "places-sampling-table", "places-collocation-table"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) attachSorter(el);
    });
    attachHtmlTableSorter("corpus-browse-table", {
      title: "text",
      author: "text",
      category: "text",
      year: "number",
      placename_count: "number",
    });
  }

  // Generic HTML table sorter for corpus view
  function attachHtmlTableSorter(containerId, typeMap) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const table = container.querySelector("table");
    if (!table) return;
    const ths = table.querySelectorAll("th");
    const tbody = table.querySelector("tbody");
    if (!ths.length || !tbody) return;
    const state = {};
    ths.forEach((th, idx) => {
      const key = Object.keys(typeMap || {})[idx];
      if (!key) return;
      state[key] = "desc";
      th.style.cursor = "pointer";
      const handler = (e) => {
        e.preventDefault();
        e.stopPropagation();
        const rows = Array.from(tbody.querySelectorAll("tr"));
        if (!rows.length) return;
        const nextDir = state[key] === "desc" ? "asc" : "desc";
        state[key] = nextDir;
        rows.sort((a, b) => {
          const va = a.children[idx]?.textContent?.trim() || "";
          const vb = b.children[idx]?.textContent?.trim() || "";
          const isNum = (typeMap || {})[key] === "number";
          if (isNum) {
            const na = Number(va) || 0;
            const nb = Number(vb) || 0;
            return nextDir === "asc" ? na - nb : nb - na;
          }
          return nextDir === "asc"
            ? va.localeCompare(vb)
            : vb.localeCompare(va);
        });
        rows.forEach((r) => tbody.appendChild(r));
      };
      if (th.__clientSortHandler) {
        th.removeEventListener("click", th.__clientSortHandler, true);
      }
      th.__clientSortHandler = handler;
      th.addEventListener("click", handler, { capture: true });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initAll();
    const observer = new MutationObserver(() => initAll());
    observer.observe(document.body, { childList: true, subtree: true });
  });
})();
