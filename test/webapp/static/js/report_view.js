/* Sales Reports v2 -- Report Viewer
 *
 * Mobile-first multi-tab grid with:
 *   - deletable tabs and columns (both land in a bottom-sheet / side-panel drawer)
 *   - column restore gated by whether its source tab is still visible
 *   - Save as Preset (fully wired), Schedule / Email Now (stubs for now)
 *   - multi-sheet Excel export
 *
 * We use a *single* Tabulator instance and swap its data/columns when the
 * active tab changes. That keeps the DOM light on phones and avoids the
 * layout flicker you get from stacking multiple grids.
 */

(function () {
    "use strict";

    // ------------------------------------------------------------------
    // Wiring
    // ------------------------------------------------------------------

    const root = document.getElementById("reportView");
    if (!root) return;

    const cfg = {
        reportKey:  root.dataset.reportKey,
        reportName: root.dataset.reportName,
        runUrl:     root.dataset.runUrl,
        exportUrl:  root.dataset.exportUrl,
        presetsUrl: root.dataset.presetsUrl,
        homeUrl:    root.dataset.homeUrl,
        params:     safeParseJSON(root.dataset.params, {}),
    };

    const els = {
        tabStrip:           document.getElementById("tabStrip"),
        gridRoot:           document.getElementById("gridRoot"),
        loading:            document.getElementById("loading"),
        generatedAt:        document.getElementById("generatedAt"),
        runError:           document.getElementById("runError"),
        exportBtn:          document.getElementById("exportXlsxBtn"),
        saveBtn:            document.getElementById("savePresetBtn"),
        scheduleBtn:        document.getElementById("scheduleBtn"),
        emailBtn:           document.getElementById("emailNowBtn"),

        drawer:             document.getElementById("deletedDrawer"),
        drawerHandle:       document.getElementById("drawerHandle"),
        drawerCount:        document.getElementById("drawerCount"),
        deletedTabsSection: document.getElementById("deletedTabsSection"),
        deletedTabsList:    document.getElementById("deletedTabsList"),
        deletedTabsCount:   document.getElementById("deletedTabsCount"),
        deletedColsSection: document.getElementById("deletedColsSection"),
        deletedColsList:    document.getElementById("deletedColsList"),
        deletedColsCount:   document.getElementById("deletedColsCount"),

        savePresetModal:    document.getElementById("savePresetModal"),
        savePresetName:     document.getElementById("savePresetName"),
        savePresetError:    document.getElementById("savePresetError"),
        savePresetConfirm:  document.getElementById("savePresetConfirm"),
        scheduleModal:      document.getElementById("scheduleModal"),
        emailNowModal:      document.getElementById("emailNowModal"),
    };

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------

    /** @type {Object<string, {key:string, label:string, columns:Array, rows:Array,
     *                          hiddenFields:Set<string>, order:string[]}>} */
    let tabs = {};
    let tabOrder = [];       // original ordering from the payload
    let deletedTabs = new Set();
    let activeKey   = null;
    let grid        = null;  // Tabulator instance

    // ------------------------------------------------------------------
    // Kick off
    // ------------------------------------------------------------------

    runReport().catch((err) => {
        console.error(err);
        showError(err.message || "Could not run the report.");
    });

    els.exportBtn.addEventListener("click", exportExcel);
    els.saveBtn.addEventListener("click", openSavePreset);
    els.scheduleBtn.addEventListener("click", () => openModal(els.scheduleModal));
    els.emailBtn.addEventListener("click",    () => openModal(els.emailNowModal));
    els.savePresetConfirm.addEventListener("click", submitSavePreset);

    // Generic modal close handlers (data-close buttons and overlay click)
    document.querySelectorAll(".modal-overlay").forEach((m) => {
        m.addEventListener("click", (e) => {
            if (e.target === m || e.target.closest("[data-close]")) closeModal(m);
        });
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") document.querySelectorAll(".modal-overlay.open").forEach(closeModal);
    });

    // Drawer toggle (mobile bottom-sheet). On desktop it's pinned open via CSS.
    els.drawerHandle.addEventListener("click", () => els.drawer.classList.toggle("open"));

    // ------------------------------------------------------------------
    // Run the report
    // ------------------------------------------------------------------

    async function runReport() {
        els.loading.hidden = false;
        const resp = await fetch(cfg.runUrl, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ params: cfg.params }),
        });
        if (!resp.ok) {
            throw new Error(`Report run failed (${resp.status}).`);
        }
        const payload = await resp.json();
        ingestPayload(payload);
    }

    function ingestPayload(payload) {
        els.loading.hidden = true;
        if (payload.generated_at) {
            els.generatedAt.textContent =
                "Generated " + formatDateTime(payload.generated_at);
        }

        const incoming = Array.isArray(payload.tabs) ? payload.tabs : [];
        tabs = {};
        tabOrder = [];
        incoming.forEach((t) => {
            const columns = Array.isArray(t.columns) ? t.columns : [];
            const key = String(t.key || ("tab_" + tabOrder.length));
            tabs[key] = {
                key,
                label:        t.label || key,
                columns,
                rows:         Array.isArray(t.rows) ? t.rows : [],
                hiddenFields: new Set(),
                order:        columns.map((c) => c.field),
            };
            tabOrder.push(key);
        });

        if (!tabOrder.length) {
            showError("The report returned no tabs.");
            return;
        }

        // Everything ready: enable toolbar + show the first tab.
        els.exportBtn.disabled    = false;
        els.saveBtn.disabled      = false;
        els.scheduleBtn.disabled  = false;
        els.emailBtn.disabled     = false;

        renderTabStrip();
        activateTab(tabOrder[0]);
        renderDrawer();
    }

    function showError(msg) {
        els.loading.hidden = true;
        els.runError.hidden = false;
        const p = els.runError.querySelector("p");
        if (p) p.textContent = msg;
    }

    // ------------------------------------------------------------------
    // Tab strip
    // ------------------------------------------------------------------

    function renderTabStrip() {
        els.tabStrip.innerHTML = "";
        const visibleKeys = tabOrder.filter((k) => !deletedTabs.has(k));

        if (!visibleKeys.length) {
            // No tabs visible -- tear down the grid.
            if (grid) { grid.destroy(); grid = null; }
            els.gridRoot.innerHTML = `
                <div class="empty-state" style="margin:0;">
                    <i data-feather="inbox"></i>
                    <h2>No tabs visible</h2>
                    <p>Restore a tab from the deleted drawer to show data.</p>
                </div>`;
            refreshFeather();
            return;
        }

        visibleKeys.forEach((key) => {
            const t = tabs[key];
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "tab-btn" + (key === activeKey ? " active" : "");
            btn.dataset.tabKey = key;
            btn.setAttribute("role", "tab");

            const label = document.createElement("span");
            label.className = "tab-label";
            label.textContent = t.label;

            const close = document.createElement("button");
            close.type = "button";
            close.className = "tab-close";
            close.title = "Delete tab";
            close.innerHTML = `<i data-feather="x"></i>`;
            close.addEventListener("click", (e) => {
                e.stopPropagation();
                deleteTab(key);
            });

            btn.appendChild(label);
            btn.appendChild(close);
            btn.addEventListener("click", () => activateTab(key));

            els.tabStrip.appendChild(btn);
        });
        refreshFeather();
    }

    // ------------------------------------------------------------------
    // Tab activation + grid swap
    // ------------------------------------------------------------------

    function activateTab(key) {
        if (!tabs[key] || deletedTabs.has(key)) return;
        activeKey = key;

        // Update tab strip selection
        els.tabStrip.querySelectorAll(".tab-btn").forEach((b) => {
            b.classList.toggle("active", b.dataset.tabKey === key);
        });

        const t = tabs[key];
        const columnDefs = buildColumnDefs(t);

        if (!grid) {
            // Build the grid DOM
            els.gridRoot.innerHTML = `<div class="grid-container" id="gridContainer"></div>`;
            const container = document.getElementById("gridContainer");

            grid = new Tabulator(container, {
                data:           t.rows,
                columns:        columnDefs,
                layout:         "fitData",       // columns size to content
                layoutColumnsOnNewData: false,
                responsiveLayout: false,          // we want horizontal scroll, NOT column collapse
                movableColumns: true,
                reactiveData:   false,
                virtualDomHoz:  true,
                placeholder:    "No rows.",
                columnDefaults: {
                    resizable:  "header",
                    tooltip:    true,
                    headerMenu: headerMenu,
                },
            });

            grid.on("columnMoved", (_col, components) => {
                const current = tabs[activeKey];
                if (!current) return;
                current.order = components
                    .map((c) => c.getField())
                    .filter((f) => !!f);
            });
        } else {
            grid.setColumns(columnDefs);
            grid.replaceData(t.rows);
        }
    }

    // Header dropdown menu (works for touch + desktop)
    function headerMenu() {
        return [
            {
                label: `<i data-feather="eye-off" style="width:14px;height:14px;vertical-align:-2px;"></i> Hide column`,
                action: (_e, col) => {
                    hideField(activeKey, col.getField());
                },
            },
        ];
    }

    // ------------------------------------------------------------------
    // Column defs
    // ------------------------------------------------------------------

    function buildColumnDefs(tab) {
        const inOrder = tab.order && tab.order.length
            ? tab.order.map((f) => tab.columns.find((c) => c.field === f)).filter(Boolean)
            : tab.columns.slice();

        return inOrder.map((col) => ({
            title:     col.title || col.field,
            field:     col.field,
            visible:   !tab.hiddenFields.has(col.field),
            formatter: cellFormatter(col.type),
            hozAlign:  alignFor(col.type),
            sorter:    sorterFor(col.type),
            minWidth:  minWidthFor(col.type),
            contextMenu: [
                {
                    label: "Hide column",
                    action: (_e, column) => hideField(tab.key, column.getField()),
                },
            ],
        }));
    }

    function alignFor(type) {
        return (type === "money" || type === "int" || type === "percent") ? "right" : "left";
    }
    function sorterFor(type) {
        if (type === "date")                                 return "datetime";
        if (type === "money" || type === "int" || type === "percent") return "number";
        return "string";
    }
    function minWidthFor(type) {
        if (type === "money")   return 110;
        if (type === "percent") return 90;
        if (type === "int")     return 80;
        if (type === "date")    return 120;
        return 100;
    }

    function cellFormatter(type) {
        if (type === "money") {
            return (cell) => {
                const v = cell.getValue();
                if (v === null || v === undefined || v === "") return "";
                const n = Number(v);
                if (!isFinite(n)) return "";
                return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            };
        }
        if (type === "int") {
            return (cell) => {
                const v = cell.getValue();
                if (v === null || v === undefined || v === "") return "";
                const n = Number(v);
                if (!isFinite(n)) return "";
                return n.toLocaleString("en-US");
            };
        }
        if (type === "percent") {
            return (cell) => {
                const v = cell.getValue();
                if (v === null || v === undefined || v === "") return "";
                const n = Number(v);
                if (!isFinite(n)) return "";
                return n.toFixed(1) + "%";
            };
        }
        if (type === "date") {
            return (cell) => {
                const v = cell.getValue();
                if (!v) return "";
                const d = new Date(v);
                if (isNaN(d.getTime())) return String(v);
                return d.toLocaleDateString("en-US");
            };
        }
        return (cell) => {
            const v = cell.getValue();
            return v === null || v === undefined ? "" : String(v);
        };
    }

    // ------------------------------------------------------------------
    // Delete / restore
    // ------------------------------------------------------------------

    function hideField(tabKey, field) {
        const t = tabs[tabKey];
        if (!t || !field) return;
        t.hiddenFields.add(field);
        // If it's the active tab, update the live grid
        if (tabKey === activeKey && grid) {
            const col = grid.getColumn(field);
            if (col) col.hide();
        }
        renderDrawer();
    }

    function restoreField(tabKey, field) {
        const t = tabs[tabKey];
        if (!t) return;
        t.hiddenFields.delete(field);
        if (tabKey === activeKey && grid) {
            const col = grid.getColumn(field);
            if (col) col.show();
        }
        renderDrawer();
    }

    function deleteTab(key) {
        if (!tabs[key]) return;
        deletedTabs.add(key);

        // If the active tab was deleted, pick the next visible one
        if (key === activeKey) {
            const nextKey = tabOrder.find((k) => !deletedTabs.has(k));
            if (nextKey) {
                activateTab(nextKey);
            } else {
                activeKey = null;
            }
        }
        renderTabStrip();
        renderDrawer();
    }

    function restoreTab(key) {
        if (!deletedTabs.has(key)) return;
        deletedTabs.delete(key);
        if (!activeKey) activateTab(key);
        renderTabStrip();
        renderDrawer();
    }

    // ------------------------------------------------------------------
    // Drawer rendering
    // ------------------------------------------------------------------

    function renderDrawer() {
        const deletedTabKeys = tabOrder.filter((k) => deletedTabs.has(k));
        const deletedColumns = collectDeletedColumns();
        const total = deletedTabKeys.length + deletedColumns.length;

        if (total === 0) {
            els.drawer.hidden = true;
            els.drawer.classList.remove("open");
            return;
        }
        els.drawer.hidden = false;
        els.drawerCount.textContent = String(total);

        // Tabs section
        if (deletedTabKeys.length) {
            els.deletedTabsSection.hidden = false;
            els.deletedTabsCount.textContent = String(deletedTabKeys.length);
            els.deletedTabsList.innerHTML = "";
            deletedTabKeys.forEach((key) => {
                const t = tabs[key];
                const li = document.createElement("li");
                li.className = "deleted-item";
                li.innerHTML = `
                    <div class="deleted-item-label">${escapeHtml(t.label)}</div>
                    <button type="button" class="restore">Restore</button>`;
                li.querySelector("button").addEventListener("click", () => restoreTab(key));
                els.deletedTabsList.appendChild(li);
            });
        } else {
            els.deletedTabsSection.hidden = true;
            els.deletedTabsList.innerHTML = "";
        }

        // Columns section
        if (deletedColumns.length) {
            els.deletedColsSection.hidden = false;
            els.deletedColsCount.textContent = String(deletedColumns.length);
            els.deletedColsList.innerHTML = "";
            deletedColumns.forEach((item) => {
                const li = document.createElement("li");
                li.className = "deleted-item";
                const tabDeleted = deletedTabs.has(item.tabKey);
                const restoreMarkup = tabDeleted
                    ? `<span class="restore-hint">Restore tab first</span>`
                    : `<button type="button" class="restore">Restore</button>`;
                li.innerHTML = `
                    <div class="deleted-item-label">
                        ${escapeHtml(item.label)}
                        <span class="deleted-item-sub">from ${escapeHtml(item.tabLabel)}</span>
                    </div>
                    ${restoreMarkup}`;
                const btn = li.querySelector("button.restore");
                if (btn) btn.addEventListener("click", () => restoreField(item.tabKey, item.field));
                els.deletedColsList.appendChild(li);
            });
        } else {
            els.deletedColsSection.hidden = true;
            els.deletedColsList.innerHTML = "";
        }
    }

    function collectDeletedColumns() {
        const out = [];
        tabOrder.forEach((key) => {
            const t = tabs[key];
            if (!t) return;
            t.hiddenFields.forEach((field) => {
                const col = t.columns.find((c) => c.field === field);
                if (!col) return;
                out.push({
                    tabKey:   key,
                    tabLabel: t.label,
                    field:    col.field,
                    label:    col.title || col.field,
                });
            });
        });
        return out;
    }

    // ------------------------------------------------------------------
    // Excel export
    // ------------------------------------------------------------------

    async function exportExcel() {
        if (!tabOrder.length) return;
        els.exportBtn.disabled = true;
        const originalHtml = els.exportBtn.innerHTML;
        els.exportBtn.innerHTML = `<i data-feather="loader"></i> Exporting...`;
        refreshFeather();

        try {
            const layouts = {};
            tabOrder.forEach((key) => {
                if (deletedTabs.has(key)) return;
                const t = tabs[key];
                layouts[key] = {
                    order:  t.order.slice(),
                    hidden: Array.from(t.hiddenFields),
                };
            });

            const resp = await fetch(cfg.exportUrl, {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    params:  cfg.params,
                    layouts,
                    dropped_tabs: Array.from(deletedTabs),
                }),
            });
            if (!resp.ok) throw new Error(`Export failed (${resp.status}).`);

            const blob = await resp.blob();
            const cd = resp.headers.get("Content-Disposition") || "";
            const filename = filenameFromDisposition(cd, `${cfg.reportKey}.xlsx`);

            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = filename;
            document.body.appendChild(a); a.click();
            setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 500);
        } catch (err) {
            alert(err.message || "Export failed.");
        } finally {
            els.exportBtn.disabled = false;
            els.exportBtn.innerHTML = originalHtml;
            refreshFeather();
        }
    }

    // ------------------------------------------------------------------
    // Save as Preset
    // ------------------------------------------------------------------

    function openSavePreset() {
        els.savePresetError.hidden = true;
        els.savePresetError.textContent = "";
        els.savePresetName.value = "";
        openModal(els.savePresetModal);
        setTimeout(() => els.savePresetName.focus(), 50);
    }

    async function submitSavePreset() {
        const name = (els.savePresetName.value || "").trim();
        if (!name) {
            els.savePresetError.textContent = "Please enter a name.";
            els.savePresetError.hidden = false;
            return;
        }
        els.savePresetConfirm.disabled = true;
        try {
            const resp = await fetch(cfg.presetsUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    name,
                    report_key: cfg.reportKey,
                    params:     cfg.params,
                }),
            });
            if (resp.status === 409) {
                const data = await resp.json().catch(() => ({}));
                els.savePresetError.textContent = data.error || "Name already in use.";
                els.savePresetError.hidden = false;
                return;
            }
            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                throw new Error(data.error || `Save failed (${resp.status}).`);
            }
            closeModal(els.savePresetModal);
            toast(`Saved "${name}" to My Presets.`);
        } catch (err) {
            els.savePresetError.textContent = err.message || "Save failed.";
            els.savePresetError.hidden = false;
        } finally {
            els.savePresetConfirm.disabled = false;
        }
    }

    function toast(message) {
        const t = document.createElement("div");
        t.className = "alert alert-success";
        t.style.cssText = "position:fixed; top:70px; left:50%; transform:translateX(-50%); z-index:600; box-shadow:var(--shadow-lg);";
        t.textContent = message;
        document.body.appendChild(t);
        setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = "0"; }, 2200);
        setTimeout(() => t.remove(), 2600);
    }

    // ------------------------------------------------------------------
    // Modal helpers
    // ------------------------------------------------------------------

    function openModal(modal) {
        if (modal) modal.classList.add("open");
    }
    function closeModal(modal) {
        if (modal) modal.classList.remove("open");
    }

    // ------------------------------------------------------------------
    // Utils
    // ------------------------------------------------------------------

    function safeParseJSON(raw, fallback) {
        try { return JSON.parse(raw); } catch (e) { return fallback; }
    }
    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({
            "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
        }[c]));
    }
    function formatDateTime(iso) {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso;
        return d.toLocaleString(undefined, {
            year: "numeric", month: "short", day: "numeric",
            hour: "numeric", minute: "2-digit",
        });
    }
    function filenameFromDisposition(header, fallback) {
        const m = /filename\*?=(?:UTF-8'')?["']?([^"';]+)/i.exec(header || "");
        return m ? decodeURIComponent(m[1]) : fallback;
    }
    function refreshFeather() {
        if (typeof feather !== "undefined") feather.replace();
    }
})();
