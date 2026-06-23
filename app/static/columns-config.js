/**
 * ColumnConfig — módulo reutilizable de personalización de columnas.
 *
 * Auto-inicializa toda tabla con atributo data-columns-table="<id>".
 * Lee los <th data-column="slug" data-mandatory="true|false"> del encabezado.
 * Etiqueta cada <td> con data-column-slug al init (basado en posición original).
 * Persiste visible+orden en localStorage["a3_cols_<id>"].
 * Aplica display:none y reordena celdas por SLUG (no por índice posicional).
 * MutationObserver taggea filas nuevas (paginación/ajax) y les aplica la config.
 * Compatible con filtros, búsqueda, ordenamiento y paginación existentes.
 */
(() => {
  const STORAGE_PREFIX = "a3_cols_";
  const SERVER_ENDPOINT = "/api/dashboard/column-prefs";
  const registry = new Map(); // tableId -> instancia, para sincronizar con el servidor
  // Anchos mínimos por tier (deben coincidir con app.css → th[data-col-size]).
  const TIER_PX = { xs: 80, sm: 120, md: 160, lg: 220, xl: 300 };

  class ColumnConfig {
    constructor(table) {
      this.table = table;
      this.tableId = table.dataset.columnsTable;
      this.headers = Array.from(table.querySelectorAll("thead th[data-column]"));
      this.columns = this.headers.map((th) => ({
        slug: th.dataset.column,
        label: th.textContent.trim().replace(/\s+/g, " ").slice(0, 45),
        mandatory: th.dataset.mandatory === "true",
        size: TIER_PX[th.dataset.colSize] ? th.dataset.colSize : "md",
        th,
      }));
      if (!this.columns.length) return;
      this.storageKey = STORAGE_PREFIX + this.tableId;
      this.panel = null;
      this.currentPrefs = null;
      this.saveTimer = null;
      registry.set(this.tableId, this);
      this.tagAllRows();
      this.bindButton();
      this.applySaved();
      this.observeBody();
    }

    tagAllRows() {
      const tbody = this.table.querySelector("tbody");
      if (!tbody) return;
      tbody.querySelectorAll("tr").forEach((row) => this.tagRow(row));
    }

    tagRow(row) {
      if (row.dataset.colsTagged) return;
      const cells = row.children;
      for (let i = 0; i < this.headers.length && i < cells.length; i++) {
        const slug = this.headers[i].dataset.column;
        if (slug) cells[i].dataset.columnSlug = slug;
      }
      row.dataset.colsTagged = "1";
    }

    observeBody() {
      const tbody = this.table.querySelector("tbody");
      if (!tbody || !window.MutationObserver) return;
      const observer = new MutationObserver((mutations) => {
        let hasNewRows = false;
        mutations.forEach((m) => {
          m.addedNodes.forEach((node) => {
            if (node.nodeName === "TR") { this.tagRow(node); hasNewRows = true; }
            else if (node.querySelectorAll) {
              node.querySelectorAll("tr").forEach((row) => { this.tagRow(row); hasNewRows = true; });
            }
          });
        });
        if (hasNewRows && this.currentPrefs) this.applyColumns(this.currentPrefs);
      });
      observer.observe(tbody, { childList: true, subtree: true });
    }

    bindButton() {
      const btn = this.table.closest("section, .card")?.querySelector(`[data-columns-btn="${this.tableId}"]`);
      if (!btn) return;
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        this.togglePanel();
      });
    }

    getDefaults() {
      return {
        visible: this.columns.map((c) => c.slug),
        order: this.columns.map((c) => c.slug),
      };
    }

    loadPrefs() {
      try {
        const raw = localStorage.getItem(this.storageKey);
        if (!raw) return this.getDefaults();
        const prefs = JSON.parse(raw);
        if (!prefs.visible || !prefs.order) return this.getDefaults();
        const valid = this.columns.map((c) => c.slug);
        prefs.visible = prefs.visible.filter((s) => valid.includes(s));
        prefs.order = prefs.order.filter((s) => valid.includes(s));
        this.columns.forEach((c) => { if (!prefs.order.includes(c.slug)) prefs.order.push(c.slug); });
        this.columns.forEach((c) => { if (c.mandatory && !prefs.visible.includes(c.slug)) prefs.visible.push(c.slug); });
        return prefs;
      } catch { return this.getDefaults(); }
    }

    savePrefs(prefs) {
      try { localStorage.setItem(this.storageKey, JSON.stringify(prefs)); } catch {}
      this.queueServerSave(prefs);
    }

    // Sincroniza con el servidor en segundo plano (debounce) sin bloquear la UI.
    queueServerSave(prefs) {
      clearTimeout(this.saveTimer);
      const snapshot = { visible: [...prefs.visible], order: [...prefs.order] };
      this.saveTimer = setTimeout(() => {
        fetch(SERVER_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ table_id: this.tableId, prefs: snapshot }),
        }).catch(() => {});
      }, 600);
    }

    // Aplica preferencias traidas del servidor (fuente de verdad entre dispositivos al cargar).
    applyServerPrefs(serverPrefs) {
      if (!serverPrefs || !Array.isArray(serverPrefs.visible) || !Array.isArray(serverPrefs.order)) return;
      try { localStorage.setItem(this.storageKey, JSON.stringify(serverPrefs)); } catch {}
      const normalized = this.loadPrefs();
      this.applyColumns(normalized);
      if (this.panel && this.panel.isConnected) { this.closePanel(); }
    }

    applySaved() {
      const prefs = this.loadPrefs();
      this.applyColumns(prefs);
    }

    applyColumns(prefs) {
      const orderMap = new Map(prefs.order.map((s, i) => [s, i]));
      const visibleSet = new Set(prefs.visible);
      const tbody = this.table.querySelector("tbody");
      const rows = tbody ? Array.from(tbody.querySelectorAll("tr")) : [];
      const theadRow = this.table.querySelector("thead tr");
      if (!theadRow) return;
      const ordered = [...this.columns].sort((a, b) => (orderMap.get(a.slug) ?? 99) - (orderMap.get(b.slug) ?? 99));

      ordered.forEach((col) => {
        const visible = visibleSet.has(col.slug);
        col.th.style.display = visible ? "" : "none";
        rows.forEach((row) => {
          const cell = row.querySelector(`td[data-column-slug="${col.slug}"]`);
          if (cell) cell.style.display = visible ? "" : "none";
        });
        if (visible && theadRow.lastElementChild !== col.th) {
          theadRow.appendChild(col.th);
          rows.forEach((row) => {
            const cell = row.querySelector(`td[data-column-slug="${col.slug}"]`);
            if (cell && row.lastElementChild !== cell) row.appendChild(cell);
          });
        }
      });
      this.currentPrefs = prefs;
      this.recalcLayout(prefs);
    }

    // Redistribuye el ancho según las columnas VISIBLES. Si el presupuesto de
    // anchos mínimos entra en el contenedor: layout fijo proporcional (sin
    // huecos ni scroll). Si no entra: layout auto con scroll mínimo necesario.
    recalcLayout(prefs) {
      const visibleCols = this.columns.filter((c) => prefs.visible.includes(c.slug));
      this.columns.forEach((c) => { if (!prefs.visible.includes(c.slug)) c.th.style.width = ""; });
      if (!visibleCols.length) return;
      const budget = visibleCols.reduce((sum, c) => sum + (TIER_PX[c.size] || TIER_PX.md), 0);
      const container = this.table.parentElement;
      const avail = container ? container.clientWidth : 0;
      if (avail && budget <= avail) {
        this.table.classList.add("cols-fitted");
        this.table.style.minWidth = "0";
        visibleCols.forEach((c) => {
          const pct = (TIER_PX[c.size] || TIER_PX.md) / budget * 100;
          c.th.style.width = pct.toFixed(3) + "%";
        });
      } else {
        this.table.classList.remove("cols-fitted");
        this.table.style.minWidth = budget + "px";
        visibleCols.forEach((c) => { c.th.style.width = ""; });
      }
    }

    togglePanel() {
      if (this.panel && this.panel.isConnected) { this.closePanel(); return; }
      this.buildPanel();
    }

    buildPanel() {
      const prefs = this.loadPrefs();
      this.currentPrefs = prefs;
      const visibleSet = new Set(prefs.visible);
      const ordered = [...this.columns].sort((a, b) => (prefs.order.indexOf(a.slug) ?? 99) - (prefs.order.indexOf(b.slug) ?? 99));

      const panel = document.createElement("div");
      panel.className = "cols-panel";
      panel.innerHTML = `
        <div class="cols-panel-head">
          <strong>Columnas</strong>
          <button type="button" class="cols-close" aria-label="Cerrar">&times;</button>
        </div>
        <div class="cols-actions">
          <button type="button" class="cols-action" data-action="all">Mostrar todas</button>
          <button type="button" class="cols-action" data-action="none">Ocultar opcionales</button>
          <button type="button" class="cols-action" data-action="reset">Restablecer</button>
        </div>
        <input type="search" class="cols-search" placeholder="Buscar columna..." aria-label="Buscar columna">
        <ul class="cols-list" role="listbox">
          ${ordered.map((col) => `
            <li class="cols-item ${col.mandatory ? "mandatory" : ""}" data-slug="${col.slug}" draggable="${col.mandatory ? "false" : "true"}">
              <span class="cols-drag" aria-hidden="true">${col.mandatory ? "" : "&#9776;"}</span>
              <label>
                <input type="checkbox" ${visibleSet.has(col.slug) ? "checked" : ""} ${col.mandatory ? "disabled" : ""} data-slug="${col.slug}">
                <span>${col.label}</span>
                ${col.mandatory ? '<em class="cols-mandatory-tag">obligatoria</em>' : ""}
              </label>
            </li>
          `).join("")}
        </ul>
      `;
      document.body.appendChild(panel);
      panel.__owner = this;
      this.panel = panel;
      this.bindPanelEvents(panel);
      requestAnimationFrame(() => panel.classList.add("open"));
    }

    bindPanelEvents(panel) {
      panel.querySelector(".cols-close").addEventListener("click", () => this.closePanel());
      panel.addEventListener("click", (e) => {
        if (e.target === panel) this.closePanel();
      });
      panel.querySelector(".cols-search").addEventListener("input", (e) => {
        const q = e.target.value.toLowerCase().trim();
        panel.querySelectorAll(".cols-item").forEach((item) => {
          const label = item.querySelector("span span")?.textContent.toLowerCase() || "";
          item.style.display = (!q || label.includes(q)) ? "" : "none";
        });
      });
      panel.querySelectorAll(".cols-action").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          const action = e.target.dataset.action;
          let prefs = this.loadPrefs();
          if (action === "all") {
            prefs.visible = this.columns.map((c) => c.slug);
          } else if (action === "none") {
            prefs.visible = this.columns.filter((c) => c.mandatory).map((c) => c.slug);
          } else if (action === "reset") {
            prefs = this.getDefaults();
          }
          this.savePrefs(prefs);
          this.applyColumns(prefs);
          this.refreshCheckboxes(prefs);
        });
      });
      panel.querySelectorAll('.cols-item input[type="checkbox"]').forEach((cb) => {
        cb.addEventListener("change", (e) => {
          const slug = e.target.dataset.slug;
          const prefs = this.loadPrefs();
          if (e.target.checked && !prefs.visible.includes(slug)) prefs.visible.push(slug);
          if (!e.target.checked) prefs.visible = prefs.visible.filter((s) => s !== slug);
          this.savePrefs(prefs);
          this.applyColumns(prefs);
        });
      });
      this.bindDragDrop(panel);
    }

    refreshCheckboxes(prefs) {
      if (!this.panel) return;
      const visibleSet = new Set(prefs.visible);
      this.panel.querySelectorAll('.cols-item input[type="checkbox"]').forEach((cb) => {
        cb.checked = visibleSet.has(cb.dataset.slug);
      });
    }

    bindDragDrop(panel) {
      const list = panel.querySelector(".cols-list");
      let dragItem = null;
      list.addEventListener("dragstart", (e) => {
        const item = e.target.closest(".cols-item");
        if (!item || item.classList.contains("mandatory")) { e.preventDefault(); return; }
        dragItem = item;
        item.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
      });
      list.addEventListener("dragend", () => {
        if (dragItem) dragItem.classList.remove("dragging");
        dragItem = null;
        this.persistOrderFromPanel();
      });
      list.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (!dragItem) return;
        const target = e.target.closest(".cols-item");
        if (!target || target === dragItem) return;
        const items = Array.from(list.querySelectorAll(".cols-item"));
        const dragIdx = items.indexOf(dragItem);
        const targetIdx = items.indexOf(target);
        if (dragIdx < targetIdx) target.after(dragItem);
        else target.before(dragItem);
      });
      list.addEventListener("drop", (e) => { e.preventDefault(); });
    }

    persistOrderFromPanel() {
      if (!this.panel) return;
      const items = Array.from(this.panel.querySelectorAll(".cols-item"));
      const newOrder = items.map((item) => item.dataset.slug);
      const prefs = this.loadPrefs();
      prefs.order = newOrder;
      this.savePrefs(prefs);
      this.applyColumns(prefs);
    }

    closePanel() {
      if (!this.panel) return;
      this.panel.classList.remove("open");
      setTimeout(() => { if (this.panel) { this.panel.remove(); this.panel = null; } }, 200);
    }
  }

  function initAll() {
    document.querySelectorAll("table[data-columns-table]").forEach((table) => {
      if (!table.dataset.colsInit) { new ColumnConfig(table); table.dataset.colsInit = "1"; }
    });
  }

  // Hibrido: ya se aplico localStorage al instante; ahora traemos el estado del
  // servidor (compartido entre dispositivos) y, si existe, sobreescribe lo local.
  async function hydrateFromServer() {
    if (!registry.size) return;
    let data;
    try {
      const res = await fetch(SERVER_ENDPOINT, { headers: { Accept: "application/json" } });
      if (!res.ok) return;
      data = await res.json();
    } catch { return; }
    const prefsByTable = (data && data.prefs) || {};
    registry.forEach((instance, tableId) => {
      if (prefsByTable[tableId]) instance.applyServerPrefs(prefsByTable[tableId]);
    });
  }

  function boot() { initAll(); hydrateFromServer(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-columns-btn]")) return;
    document.querySelectorAll(".cols-panel.open").forEach((panel) => {
      if (!panel.contains(e.target) && panel.__owner) panel.__owner.closePanel();
    });
  });

  // Recalcular distribución al cambiar el tamaño de la ventana (debounced).
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      registry.forEach((instance) => {
        if (instance.currentPrefs) instance.recalcLayout(instance.currentPrefs);
      });
    }, 150);
  });

  window.ColumnConfig = ColumnConfig;
})();
