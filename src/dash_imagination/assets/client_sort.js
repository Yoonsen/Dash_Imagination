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
    if (!container || container.__clientSorterAttached) return;
    container.__clientSorterAttached = true;
    const state = { dir: {} };
    const handler = (e) => {
      const target = e.target.closest(".places-sort-header");
      if (!target || !container.contains(target)) return;
      e.preventDefault();
      e.stopPropagation();
      const key = parseHeaderKey(target);
      if (!key) return;
      state.dir[key] = state.dir[key] === "asc" ? "desc" : "asc";
      const rows = Array.from(container.querySelectorAll(".place-item"));
      if (!rows.length) return;
      const parent = rows[0].parentNode;
      const nextDir = state.dir[key];
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
    container.addEventListener("click", handler, true);
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
    if (!container || container.__clientSorterAttached) return;
    const table = container.querySelector("table");
    const tbody = container.querySelector("tbody");
    if (!table || !tbody) return;
    container.__clientSorterAttached = true;
    const state = {};
    const handler = (e) => {
      const th = e.target.closest("th");
      if (!th || !table.contains(th)) return;
      e.preventDefault();
      e.stopPropagation();
      const idx = Array.from(th.parentNode.children).indexOf(th);
      const key = Object.keys(typeMap || {})[idx];
      if (!key) return;
      state[key] = state[key] === "asc" ? "desc" : "asc";
      const nextDir = state[key];
      const rows = Array.from(tbody.querySelectorAll("tr"));
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
    container.addEventListener("click", handler, true);
  }

  document.addEventListener("DOMContentLoaded", () => {
    initAll();
    const observer = new MutationObserver(() => initAll());
    observer.observe(document.body, { childList: true, subtree: true });
  });
})();
