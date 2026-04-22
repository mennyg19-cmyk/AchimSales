/* Report viewer: multi-tab grid, simple column actions, Excel export.
 *
 * On load we POST the filter params (from data-params) to /run and get
 * back a payload shaped like:
 *   { tabs: [{ key, name, columns: [{field, header, type}], rows: [...] }] }
 *
 * Each tab gets its own Tabulator grid. Users can:
 *   - click a header to sort
 *   - drag headers to reorder
 *   - right-click a header -> "Hide column" (also supported via the tiny X
 *     button in the column header)
 * Hidden columns appear in a sidebar that only shows when at least one
 * column on the active tab is hidden. Clicking a hidden column puts it back.
 *
 * "Export to Excel" POSTs the current per-tab order+hidden layouts back to
 * /export.xlsx and the server builds a multi-sheet workbook.
 */

(function () {
    "use strict";

    const root = document.getElementById("reportView");
    if (!root) return;

    const cfg = {
        reportKey:  root.dataset.reportKey,
        reportName: root.dataset.reportName,
        runUrl:     root.dataset.runUrl,
        exportUrl:  root.dataset.exportUrl,
        params:     safeParse(root.dataset.params) || {},
    };

    const els = {
        loading:      document.getElementById("loading"),
        generatedAt:  document.getElementById("generatedAt"),
        tabStrip:     document.getElementById("tabStrip"),
        gridShell:    document.getElementById("gridShell"),
        gridRoot:     document.getElementById("gridRoot"),
        hiddenPanel:  document.getElementById("hiddenPanel"),
        hiddenList:   document.getElementById("hiddenList"),
        restoreAll:   document.getElementById("restoreAllBtn"),
        exportBtn:    document.getElementById("exportXlsxBtn"),
        runError:     document.getElementById("runError"),
    };

    // Per-tab state: tabs[tabKey] = { meta, columns, rows, container, grid, hidden: Set, order: [fields] }
    const state = {
        tabs: {},
        activeKey: null,
    };

    // -----------------------------------------------------------------
    // Boot
    // -----------------------------------------------------------------
    runReport().catch((err) => {
        console.error(err);
        showError(err.message || "Failed to run report.");
    });

    // -----------------------------------------------------------------
    // Fetch
    // -----------------------------------------------------------------
    async function runReport() {
        const resp = await fetch(cfg.runUrl, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ params: cfg.params }),
            credentials: "same-origin",
        });
        if (!resp.ok) {
            throw new Error(`Report run failed (${resp.status} ${resp.statusText})`);
        }
        const payload = await resp.json();
        els.loading.style.display = "none";
        if (payload.generated_at) {
            els.generatedAt.textContent = "Generated " + formatDateTime(payload.generated_at);
        }

        buildTabs(payload.tabs || []);
        if (payload.tabs && payload.tabs.length) {
            els.exportBtn.disabled = false;
        } else {
            showError("No data returned.");
        }
    }

    // -----------------------------------------------------------------
    // Tab strip + grids
    // -----------------------------------------------------------------
    function buildTabs(tabs) {
        els.tabStrip.innerHTML = "";
        els.gridRoot.innerHTML = "";

        tabs.forEach((tab, idx) => {
            const tabBtn = document.createElement("button");
            tabBtn.type = "button";
            tabBtn.className = "tab-btn";
            tabBtn.textContent = tab.name || tab.key;
            tabBtn.dataset.tabKey = tab.key;
            tabBtn.addEventListener("click", () => activateTab(tab.key));
            els.tabStrip.appendChild(tabBtn);

            const container = document.createElement("div");
            container.className = "grid-container";
            container.style.display = "none";
            els.gridRoot.appendChild(container);

            state.tabs[tab.key] = {
                meta:      tab,
                columns:   tab.columns || [],
                rows:      tab.rows || [],
                container: container,
                grid:      null,
                hidden:    new Set(),
                order:     (tab.columns || []).map((c) => c.field),
            };

            if (idx === 0) activateTab(tab.key);
        });
    }

    function activateTab(key) {
        if (state.activeKey === key) return;
        state.activeKey = key;

        // Toggle tab button state + grid visibility.
        els.tabStrip.querySelectorAll(".tab-btn").forEach((b) => {
            b.classList.toggle("active", b.dataset.tabKey === key);
        });
        Object.keys(state.tabs).forEach((k) => {
            state.tabs[k].container.style.display = (k === key) ? "block" : "none";
        });

        const tab = state.tabs[key];
        if (!tab.grid) initGrid(tab);
        refreshHiddenPanel();

        // Tabulator sometimes mis-measures when built in a hidden container.
        // Redraw once the tab is visible.
        if (tab.grid) {
            setTimeout(() => tab.grid.redraw(true), 0);
        }
    }

    function initGrid(tab) {
        const defs = buildColumnDefs(tab);
        tab.grid = new Tabulator(tab.container, {
            data:            tab.rows,
            columns:         defs,
            layout:          "fitDataStretch",
            movableColumns:  true,
            reactiveData:    false,
            headerSortClickElement: "header",
            placeholder:     "No rows.",
            height:          "100%",
        });

        // Track user reorder so exports respect it.
        tab.grid.on("columnMoved", function (_column, columns) {
            const visibleOrder = columns.map((c) => c.getField()).filter(Boolean);
            // Keep hidden fields at the end of the tracked order.
            const hiddenInOrder = tab.order.filter((f) => tab.hidden.has(f));
            tab.order = visibleOrder.concat(hiddenInOrder);
        });
    }

    // -----------------------------------------------------------------
    // Column defs
    // -----------------------------------------------------------------
    function buildColumnDefs(tab) {
        const byField = {};
        tab.columns.forEach((c) => { byField[c.field] = c; });

        return tab.order
            .filter((field) => !tab.hidden.has(field) && byField[field])
            .map((field) => columnDef(tab, byField[field]));
    }

    function columnDef(tab, col) {
        return {
            field:        col.field,
            title:        col.header || col.field,
            headerSort:   true,
            headerFilter: false,
            formatter:    cellFormatter(col.type),
            hozAlign:     isNumeric(col.type) ? "right" : "left",
            headerHozAlign: isNumeric(col.type) ? "right" : "left",
            // Per-column right-click menu: "Hide column".
            headerContextMenu: [
                {
                    label:  "Hide column",
                    action: (e, column) => hideField(tab, column.getField()),
                },
                {
                    separator: true,
                },
                {
                    label:  "Sort ascending",
                    action: (e, column) => column.getTable().setSort(column.getField(), "asc"),
                },
                {
                    label:  "Sort descending",
                    action: (e, column) => column.getTable().setSort(column.getField(), "desc"),
                },
                {
                    label:  "Clear sort",
                    action: (e, column) => column.getTable().clearSort(),
                },
            ],
        };
    }

    function cellFormatter(type) {
        switch (type) {
            case "money":
                return (cell) => {
                    const v = Number(cell.getValue());
                    if (!isFinite(v)) return "";
                    return v.toLocaleString("en-US", { style: "currency", currency: "USD" });
                };
            case "int":
                return (cell) => {
                    const v = Number(cell.getValue());
                    if (!isFinite(v)) return "";
                    return v.toLocaleString("en-US");
                };
            case "percent":
                return (cell) => {
                    const v = Number(cell.getValue());
                    if (!isFinite(v)) return "";
                    return (v * 100).toFixed(2) + "%";
                };
            case "date":
                return (cell) => {
                    const raw = cell.getValue();
                    if (!raw) return "";
                    const d = new Date(raw);
                    if (isNaN(d)) return String(raw);
                    return d.toLocaleDateString("en-US");
                };
            default:
                return (cell) => {
                    const v = cell.getValue();
                    return v == null ? "" : String(v);
                };
        }
    }

    function isNumeric(type) {
        return type === "money" || type === "int" || type === "percent";
    }

    // -----------------------------------------------------------------
    // Hide / restore columns
    // -----------------------------------------------------------------
    function hideField(tab, field) {
        if (!field || tab.hidden.has(field)) return;
        // Must always leave at least one visible column -- otherwise the
        // grid shows nothing and the user has no header to right-click.
        const visibleCount = tab.order.filter((f) => !tab.hidden.has(f)).length;
        if (visibleCount <= 1) {
            flash("At least one column must stay visible.");
            return;
        }
        tab.hidden.add(field);
        tab.grid.setColumns(buildColumnDefs(tab));
        refreshHiddenPanel();
    }

    function restoreField(tab, field) {
        if (!tab.hidden.has(field)) return;
        tab.hidden.delete(field);
        tab.grid.setColumns(buildColumnDefs(tab));
        refreshHiddenPanel();
    }

    function refreshHiddenPanel() {
        const tab = state.tabs[state.activeKey];
        if (!tab) return;

        const hidden = tab.order.filter((f) => tab.hidden.has(f));
        const byField = {};
        tab.columns.forEach((c) => { byField[c.field] = c; });

        els.hiddenList.innerHTML = "";
        hidden.forEach((field) => {
            const col = byField[field];
            const li = document.createElement("li");
            li.className = "col-item";
            li.innerHTML = `
                <span class="col-label">${escapeHtml(col.header || field)}</span>
                <span class="col-actions">
                    <button type="button" title="Restore column">+</button>
                </span>
            `;
            li.addEventListener("click", () => restoreField(tab, field));
            els.hiddenList.appendChild(li);
        });

        const hasHidden = hidden.length > 0;
        els.hiddenPanel.hidden = !hasHidden;
        els.gridShell.classList.toggle("no-panel", !hasHidden);
    }

    els.restoreAll.addEventListener("click", () => {
        const tab = state.tabs[state.activeKey];
        if (!tab) return;
        tab.hidden.clear();
        tab.grid.setColumns(buildColumnDefs(tab));
        refreshHiddenPanel();
    });

    // -----------------------------------------------------------------
    // Excel export
    // -----------------------------------------------------------------
    els.exportBtn.addEventListener("click", exportExcel);

    async function exportExcel() {
        els.exportBtn.disabled = true;
        const originalLabel = els.exportBtn.textContent;
        els.exportBtn.textContent = "Building...";
        try {
            const layouts = {};
            Object.keys(state.tabs).forEach((k) => {
                const tab = state.tabs[k];
                // Capture current on-screen order from Tabulator (which
                // reflects user drags), fall back to tab.order.
                let order = tab.order.slice();
                if (tab.grid) {
                    const cols = tab.grid.getColumns(false);
                    const visible = cols.map((c) => c.getField()).filter(Boolean);
                    const hiddenTail = tab.order.filter((f) => tab.hidden.has(f));
                    order = visible.concat(hiddenTail);
                }
                layouts[k] = {
                    order:  order,
                    hidden: Array.from(tab.hidden),
                };
            });

            const resp = await fetch(cfg.exportUrl, {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body:    JSON.stringify({ params: cfg.params, layouts: layouts }),
                credentials: "same-origin",
            });
            if (!resp.ok) {
                throw new Error(`Export failed (${resp.status})`);
            }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filenameFromDisposition(resp.headers.get("Content-Disposition"))
                       || (cfg.reportName.replace(/\s+/g, "_") + ".xlsx");
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 2000);
        } catch (err) {
            console.error(err);
            flash(err.message || "Export failed.");
        } finally {
            els.exportBtn.textContent = originalLabel;
            els.exportBtn.disabled = false;
        }
    }

    // -----------------------------------------------------------------
    // Utilities
    // -----------------------------------------------------------------
    function showError(msg) {
        els.loading.style.display = "none";
        els.runError.hidden = false;
        els.runError.querySelector("p").textContent = msg;
    }

    function flash(msg) {
        // Lightweight status message -- reuse the #loading span.
        if (!els.loading) return;
        const old = els.loading.style.display;
        els.loading.style.display = "inline";
        els.loading.style.color = "#f87171";
        els.loading.textContent = msg;
        setTimeout(() => {
            els.loading.style.display = old;
            els.loading.style.color = "";
            els.loading.textContent = "";
        }, 2500);
    }

    function safeParse(s) {
        if (!s) return null;
        try { return JSON.parse(s); } catch (_) { return null; }
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[c]));
    }

    function formatDateTime(iso) {
        try {
            const d = new Date(iso);
            return d.toLocaleString();
        } catch (_) {
            return iso;
        }
    }

    function filenameFromDisposition(disp) {
        if (!disp) return null;
        const m = /filename="?([^"]+)"?/i.exec(disp);
        return m ? m[1] : null;
    }
})();
