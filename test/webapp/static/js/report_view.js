/*
 * Sales Reports v2 -- Report Viewer (mobile-first)
 *
 * Layout goals:
 *   - Table always at natural width (layout: fitDataTable). A horizontally-
 *     scrollable wrapper handles overflow on phones so the page stays usable.
 *   - Tabs are deletable (X button on each). Hidden tabs + hidden columns
 *     both land in a shared "Hidden" panel with two sections.
 *   - On desktop (>=769px) the panel is a sticky right sidebar that appears
 *     only when something is hidden. On mobile (<=768px) it becomes a
 *     bottom-drawer sheet opened via a floating "Hidden (N)" button.
 *   - A deleted column cannot be restored while its parent tab is hidden
 *     (the restore button is disabled with a reason).
 *   - Action buttons: Export Excel, Send email now, Schedule, Save as preset.
 *
 * We use one Tabulator instance per tab (created lazily on first activation).
 * State lives on `state.tabs[key]` as { data, columnsMeta, hiddenFields,
 * fieldOrder, grid }.
 */

(function () {
    "use strict";

    const root = document.getElementById("reportView");
    if (!root) return;

    // ---------- Config & DOM lookup --------------------------------------
    const cfg = {
        reportKey:      root.dataset.reportKey,
        reportName:     root.dataset.reportName,
        runUrl:         root.dataset.runUrl,
        exportUrl:      root.dataset.exportUrl,
        emailUrl:       root.dataset.emailUrl,
        scheduleUrl:    root.dataset.scheduleUrl,
        presetSaveUrl:  root.dataset.presetSaveUrl,
        filterUrl:      root.dataset.filterUrl,
        params:         safeParse(root.dataset.params, {}),
        presetLayouts:  safeParse(root.dataset.presetLayouts, {}),
        presetName:     root.dataset.presetName || "",
    };

    const $ = (id) => document.getElementById(id);
    const els = {
        tabStrip:           $("tabStrip"),
        gridRoot:           $("gridRoot"),
        status:             $("viewStatus"),
        emptyState:         $("emptyState"),
        emptyStateMsg:      $("emptyStateMsg"),
        sourceBadge:        $("dataSourceBadge"),
        apiSentPanel:       $("apiSentPanel"),
        apiSentUrl:         $("apiSentUrl"),
        apiSentBody:        $("apiSentBody"),
        apiSentHint:        $("apiSentHint"),

        // Hidden panel (desktop)
        panel:              $("hiddenPanel"),
        panelTabsSec:       $("hiddenTabsSection"),
        panelTabsList:      $("hiddenTabsList"),
        panelColsSec:       $("hiddenColsSection"),
        panelColsList:      $("hiddenColsList"),
        restoreAllBtn:      $("restoreAllBtn"),

        // Mobile FAB + drawer
        fab:                $("hiddenFab"),
        fabCount:           $("hiddenFabCount"),
        drawerBackdrop:     $("drawerBackdrop"),
        drawerSheet:        $("drawerSheet"),
        drawerTabsSec:      $("hiddenTabsSectionM"),
        drawerTabsList:     $("hiddenTabsListM"),
        drawerColsSec:      $("hiddenColsSectionM"),
        drawerColsList:     $("hiddenColsListM"),
        restoreAllBtnM:     $("restoreAllBtnMobile"),

        // Action buttons
        exportBtn:          $("exportXlsxBtn"),
        emailBtn:           $("emailNowBtn"),
        scheduleBtn:        $("scheduleBtn"),
        presetBtn:          $("savePresetBtn"),

        // Modals
        presetModal:        $("presetModal"),
        presetNameInput:    $("presetNameInput"),
        presetIncludeLayout:$("presetIncludeLayout"),
        presetMsg:          $("presetMsg"),
        presetSaveBtn:      $("presetSaveBtn"),

        emailModal:         $("emailModal"),
        emailRecipients:    $("emailRecipients"),
        emailSubject:       $("emailSubject"),
        emailMsg:           $("emailMsg"),
        emailSendBtn:       $("emailSendBtn"),
        emailSpCheck:       $("emailSharePointCheck"),
        emailSpPicker:      $("emailSharePointPicker"),
        emailSpPath:        $("emailSharePointPath"),
        emailSpPickBtn:     $("emailSharePointPick"),

        scheduleModal:      $("scheduleModal"),
        cadenceGroup:       $("cadenceGroup"),
        weeklyRow:          $("weeklyRow"),
        weekdayGroup:       $("weekdayGroup"),
        monthlyRow:         $("monthlyRow"),
        monthdayGroup:      $("monthdayGroup"),
        scheduleTime:       $("scheduleTime"),
        scheduleStart:      $("scheduleStart"),
        scheduleHasEnd:     $("scheduleHasEnd"),
        scheduleEnd:        $("scheduleEnd"),
        scheduleRecipients: $("scheduleRecipients"),
        scheduleName:       $("scheduleName"),
        schedulePreview:    $("schedulePreview"),
        scheduleMsg:        $("scheduleMsg"),
        scheduleSaveBtn:    $("scheduleSaveBtn"),
        scheduleSpCheck:    $("scheduleSharePointCheck"),
        scheduleSpPicker:   $("scheduleSharePointPicker"),
        scheduleSpPath:     $("scheduleSharePointPath"),
        scheduleSpPickBtn:  $("scheduleSharePointPick"),
    };

    // ---------- State ----------------------------------------------------
    /** Shape:
     *  {
     *    generatedAt: ISO,
     *    activeTab:   string | null,
     *    tabs: {
     *      <tabKey>: {
     *        name:        string,
     *        data:        [...rows],
     *        columnsMeta: [{field, label, type}, ...],   // canonical source order
     *        hiddenFields: Set<string>,
     *        fieldOrder:  [field, ...],                  // current display order
     *        grid:        Tabulator | null,
     *        container:   HTMLDivElement,
     *      }
     *    },
     *    tabOrder:    [tabKey, ...],
     *    hiddenTabs:  Set<string>,
     *    scheduleUi:  { cadence, weekdays: Set, monthday }
     *  }
     */
    const state = {
        generatedAt: null,
        activeTab:   null,
        tabs:        Object.create(null),
        tabOrder:    [],
        hiddenTabs:  new Set(),
        scheduleUi:  { cadence: "daily", weekdays: new Set(["mon"]), monthdays: new Set([1]) },
    };

    // ---------- Boot -----------------------------------------------------
    runReport().catch(function (err) {
        showStatus("Could not load report: " + (err.message || err), true);
    });
    wireActionButtons();
    wireDrawer();
    wireModals();
    wireScheduleModal();

    // ---------- Data-source badge --------------------------------------
    function renderApiSentPanel(meta) {
        const panel = els.apiSentPanel;
        if (!panel) return;
        const body = (meta && meta.request_body) || null;
        const url  = (meta && meta.endpoint) || null;
        if (!body && !url) {
            panel.hidden = true;
            return;
        }
        if (els.apiSentUrl)  els.apiSentUrl.textContent  = url || "(no URL)";
        if (els.apiSentBody) els.apiSentBody.textContent = JSON.stringify(body || {}, null, 2);
        if (els.apiSentHint) {
            const keys = body ? Object.keys(body).length : 0;
            els.apiSentHint.textContent = keys
                ? `(${keys} param${keys === 1 ? "" : "s"})`
                : "(no params)";
        }
        panel.hidden = false;
    }

    function renderSourceBadge(meta) {
        renderApiSentPanel(meta);

        const el = els.sourceBadge;
        if (!el) return;

        if (!meta || !meta.source) {
            el.hidden = true;
            return;
        }
        const known = {
            reporting_api:        { cls: "src-live",    text: "LIVE DATA" },
            reporting_api_failed: { cls: "src-error",   text: "API FAILED" },
            fixture:              { cls: "src-fixture", text: "TEST DATA (fixture)" },
            random_mock:          { cls: "src-mock",    text: "MOCK DATA" },
        };
        const info = known[meta.source] || { cls: "src-mock", text: meta.source };

        el.className = "data-source-badge " + info.cls;
        el.textContent = info.text;
        const tipParts = [meta.label || ""];
        if (meta.rows_fetched != null) tipParts.push("Rows: " + meta.rows_fetched);
        if (meta.elapsed_ms != null) {
            const secs = (meta.elapsed_ms / 1000).toFixed(1);
            const tip = "API call: " + meta.elapsed_ms + " ms (" + secs + " s)";
            tipParts.push(meta.timeout_s ? tip + " of " + meta.timeout_s + " s timeout" : tip);
        }
        if (meta.endpoint) tipParts.push("Endpoint: " + meta.endpoint);
        if (meta.fixture_file) tipParts.push("File: " + meta.fixture_file);
        if (meta.api_error) tipParts.push("Last API error: " + meta.api_error);
        if (meta.error) tipParts.push("Error: " + meta.error);
        el.title = tipParts.filter(Boolean).join("\n");
        el.hidden = false;
    }

    // ---------- Fetch & render ------------------------------------------
    async function runReport() {
        showStatus("Loading report…", false, true);
        const payload = await postJson(cfg.runUrl, cfg.params);

        renderSourceBadge(payload.data_source);
        state.generatedAt = payload.generated_at || null;
        state.activeTab = null;
        state.tabs = Object.create(null);
        state.tabOrder = [];
        state.hiddenTabs = new Set();

        (payload.tabs || []).forEach(function (t) {
            state.tabs[t.key] = {
                name:         t.name,
                data:         Array.isArray(t.rows) ? t.rows : [],
                columnsMeta:  Array.isArray(t.columns) ? t.columns.map(cloneCol) : [],
                hiddenFields: new Set(),
                fieldOrder:   (t.columns || []).map(function (c) { return c.field; }),
                grid:         null,
                container:    null,
            };
            state.tabOrder.push(t.key);
        });

        if (!state.tabOrder.length) {
            showStatus("", false, false);
            els.emptyState.hidden = false;
            els.emptyStateMsg.textContent = "No tabs were returned.";
            return;
        }

        applyPresetLayouts();

        buildTabStrip();
        buildGridContainers();
        const firstVisible = state.tabOrder.find(function (k) { return !state.hiddenTabs.has(k); })
            || state.tabOrder[0];
        activateTab(firstVisible);
        refreshHiddenUi();

        const tsLabel = state.generatedAt
            ? ("Generated " + fmtLocal(state.generatedAt))
            : "Generated just now";
        showStatus(tsLabel, false, false);
    }

    function cloneCol(c) {
        return { field: c.field, label: c.label || c.field, type: c.type || "text" };
    }

    // If we arrived from the home page's "Run preset" button, the server
    // stamps a `data-preset-layouts` blob onto the root with the layout the
    // user saved last time. Merge it into per-tab state *before* we build
    // grids so the first paint already matches their saved layout.
    function applyPresetLayouts() {
        const layouts = cfg.presetLayouts || {};
        if (!layouts || typeof layouts !== "object") return;

        Object.keys(layouts).forEach(function (tabKey) {
            const saved = layouts[tabKey] || {};
            const tab = state.tabs[tabKey];
            if (!tab) return; // stale preset referencing a tab the report no longer has

            if (saved.tab_hidden) {
                state.hiddenTabs.add(tabKey);
            }

            const validFields = new Set(tab.columnsMeta.map(function (c) { return c.field; }));

            if (Array.isArray(saved.hidden_fields)) {
                saved.hidden_fields.forEach(function (f) {
                    if (validFields.has(f)) tab.hiddenFields.add(f);
                });
            }

            if (Array.isArray(saved.field_order) && saved.field_order.length) {
                const ordered = [];
                const seen = new Set();
                saved.field_order.forEach(function (f) {
                    if (validFields.has(f) && !seen.has(f)) {
                        ordered.push(f);
                        seen.add(f);
                    }
                });
                // Append any new fields the report gained since the preset was saved
                tab.columnsMeta.forEach(function (c) {
                    if (!seen.has(c.field)) ordered.push(c.field);
                });
                tab.fieldOrder = ordered;
            }
        });
    }

    // ---------- Tabs -----------------------------------------------------
    function buildTabStrip() {
        els.tabStrip.innerHTML = "";
        state.tabOrder.forEach(function (key) {
            if (state.hiddenTabs.has(key)) return;
            const t = state.tabs[key];
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "viewer-tab";
            btn.setAttribute("role", "tab");
            btn.dataset.key = key;
            btn.innerHTML =
                '<span class="viewer-tab-name"></span>' +
                '<button type="button" class="viewer-tab-close" aria-label="Hide tab" title="Hide tab">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 6L18 18M6 18L18 6"/></svg>' +
                '</button>';
            btn.querySelector(".viewer-tab-name").textContent = t.name;
            btn.addEventListener("click", function (e) {
                if (e.target.closest(".viewer-tab-close")) {
                    e.stopPropagation();
                    hideTab(key);
                    return;
                }
                activateTab(key);
            });
            els.tabStrip.appendChild(btn);
        });
    }

    function buildGridContainers() {
        els.gridRoot.innerHTML = "";
        state.tabOrder.forEach(function (key) {
            const div = document.createElement("div");
            div.className = "grid-pane";
            div.dataset.key = key;
            const inner = document.createElement("div");
            inner.className = "grid-container";
            div.appendChild(inner);
            els.gridRoot.appendChild(div);
            state.tabs[key].container = inner;
        });
    }

    function activateTab(key) {
        if (!state.tabs[key] || state.hiddenTabs.has(key)) {
            // Pick the first visible tab instead.
            const fallback = state.tabOrder.find(function (k) { return !state.hiddenTabs.has(k); });
            if (!fallback) {
                state.activeTab = null;
                els.gridRoot.querySelectorAll(".grid-pane").forEach(function (p) { p.classList.remove("active"); });
                els.emptyState.hidden = false;
                els.emptyStateMsg.textContent = "All tabs are hidden. Restore one from the Hidden panel to see data.";
                return;
            }
            key = fallback;
        }
        els.emptyState.hidden = true;
        state.activeTab = key;

        // Tab strip visual state
        els.tabStrip.querySelectorAll(".viewer-tab").forEach(function (b) {
            const active = b.dataset.key === key;
            b.classList.toggle("active", active);
            b.setAttribute("aria-selected", active ? "true" : "false");
        });

        // Show the matching pane, hide others
        els.gridRoot.querySelectorAll(".grid-pane").forEach(function (p) {
            p.classList.toggle("active", p.dataset.key === key);
        });

        ensureGrid(key);
        refreshHiddenUi();
    }

    function ensureGrid(key) {
        const t = state.tabs[key];
        if (t.grid) return t.grid;

        t.grid = new Tabulator(t.container, {
            data:          t.data,
            layout:        "fitDataTable",    // natural width -> grid-root scrolls
            columnDefaults:{
                headerHozAlign: "left",
                hozAlign:       "left",
                resizable:      true,
                headerContextMenu: tabulatorHeaderCtxMenu(key),
            },
            columns:       buildColumnDefs(key),
            movableColumns:true,
            height:        "60vh",
            placeholder:   "No rows for the selected filters.",
            columnMoved:   function () { syncFieldOrder(key); },
        });
        return t.grid;
    }

    function buildColumnDefs(key) {
        const t = state.tabs[key];
        const hidden = t.hiddenFields;
        return t.fieldOrder.map(function (field) {
            const meta = t.columnsMeta.find(function (m) { return m.field === field; });
            if (!meta) return null;
            const isNumeric = (meta.type === "money" || meta.type === "int" || meta.type === "percent");
            return {
                title:        meta.label,
                field:        meta.field,
                visible:      !hidden.has(meta.field),
                formatter:    columnFormatter(meta.type),
                hozAlign:     isNumeric ? "right" : "left",
                headerFilter: "input",                          // filterable
                sorter:       columnSorter(meta.type),          // sortable
            };
        }).filter(Boolean);
    }

    function columnSorter(type) {
        switch (type) {
            case "money":
            case "int":
            case "percent": return "number";
            case "date":    return "date";
            default:        return "string";
        }
    }

    function tabulatorHeaderCtxMenu(key) {
        return [
            {
                label: "<i data-feather='eye-off' style='width:14px;height:14px;vertical-align:-2px;'></i>  Hide this column",
                action: function (e, column) {
                    hideColumn(key, column.getField());
                },
            },
        ];
    }

    function columnFormatter(type) {
        switch (type) {
            case "money":   return function (cell) { return fmtMoney(cell.getValue()); };
            case "int":     return function (cell) { return fmtInt(cell.getValue()); };
            case "percent": return function (cell) { return fmtPercent(cell.getValue()); };
            case "date":    return function (cell) { return fmtDate(cell.getValue()); };
            default:        return function (cell) { return escHtml(cell.getValue()); };
        }
    }

    function syncFieldOrder(key) {
        const t = state.tabs[key];
        if (!t.grid) return;
        t.fieldOrder = t.grid.getColumns().map(function (col) { return col.getField(); });
    }

    // ---------- Hide / restore: columns & tabs --------------------------
    function hideColumn(tabKey, field) {
        const t = state.tabs[tabKey];
        if (!t) return;
        t.hiddenFields.add(field);
        if (t.grid) {
            const col = t.grid.getColumn(field);
            if (col) col.hide();
        }
        refreshHiddenUi();
    }

    function restoreColumn(tabKey, field) {
        if (state.hiddenTabs.has(tabKey)) return;  // blocked
        const t = state.tabs[tabKey];
        if (!t) return;
        t.hiddenFields.delete(field);
        if (t.grid) {
            const col = t.grid.getColumn(field);
            if (col) col.show();
        }
        refreshHiddenUi();
    }

    function hideTab(key) {
        if (state.hiddenTabs.has(key)) return;
        state.hiddenTabs.add(key);
        buildTabStrip();
        if (state.activeTab === key) {
            const next = state.tabOrder.find(function (k) { return !state.hiddenTabs.has(k); });
            if (next) activateTab(next);
            else {
                state.activeTab = null;
                els.gridRoot.querySelectorAll(".grid-pane").forEach(function (p) { p.classList.remove("active"); });
                els.emptyState.hidden = false;
                els.emptyStateMsg.textContent = "All tabs are hidden. Restore one from the Hidden panel to see data.";
            }
        }
        refreshHiddenUi();
    }

    function restoreTab(key) {
        if (!state.hiddenTabs.has(key)) return;
        state.hiddenTabs.delete(key);
        buildTabStrip();
        activateTab(key);
    }

    function restoreEverything() {
        state.hiddenTabs.clear();
        state.tabOrder.forEach(function (k) {
            const t = state.tabs[k];
            if (!t) return;
            t.hiddenFields.clear();
            if (t.grid) {
                t.columnsMeta.forEach(function (m) {
                    const c = t.grid.getColumn(m.field);
                    if (c) c.show();
                });
            }
        });
        buildTabStrip();
        if (state.tabOrder.length) activateTab(state.tabOrder[0]);
        refreshHiddenUi();
    }

    // ---------- Hidden panel rendering ----------------------------------
    function refreshHiddenUi() {
        const hiddenTabKeys = state.tabOrder.filter(function (k) { return state.hiddenTabs.has(k); });
        const hiddenCols = [];  // [{tabKey, tabName, field, label, tabHidden}]
        state.tabOrder.forEach(function (k) {
            const t = state.tabs[k];
            if (!t) return;
            t.hiddenFields.forEach(function (field) {
                const meta = t.columnsMeta.find(function (m) { return m.field === field; });
                hiddenCols.push({
                    tabKey:    k,
                    tabName:   t.name,
                    field:     field,
                    label:     meta ? meta.label : field,
                    tabHidden: state.hiddenTabs.has(k),
                });
            });
        });

        const anyHidden = hiddenTabKeys.length > 0 || hiddenCols.length > 0;
        els.panel.hidden = !anyHidden;

        // Desktop panel
        renderHiddenSection(els.panelTabsSec, els.panelTabsList, hiddenTabKeys, hiddenCols, /*mobile*/ false);

        // Mobile drawer duplicates
        renderHiddenSection(els.drawerTabsSec, els.drawerTabsList, hiddenTabKeys, hiddenCols, /*mobile*/ true);

        // FAB count
        els.fab.style.display = ""; // CSS media query controls visibility
        els.fabCount.textContent = String(hiddenTabKeys.length + hiddenCols.length);
        if (!anyHidden) {
            closeDrawer();
        }
    }

    function renderHiddenSection(tabsSec, tabsList, hiddenTabs, hiddenCols, mobile) {
        // --- Tabs section ---
        tabsSec.hidden = hiddenTabs.length === 0;
        tabsList.innerHTML = "";
        hiddenTabs.forEach(function (key) {
            const t = state.tabs[key];
            const li = document.createElement("li");
            li.innerHTML =
                '<span class="name"></span>' +
                '<button type="button" class="restore-btn" title="Restore tab">Restore</button>';
            li.querySelector(".name").textContent = t.name;
            li.querySelector(".restore-btn").addEventListener("click", function () {
                restoreTab(key);
                if (mobile) closeDrawer();
            });
            tabsList.appendChild(li);
        });

        // --- Columns section (shares the same hidden-section markup via the same wrapper block) ---
        const colsSec  = mobile ? els.drawerColsSec  : els.panelColsSec;
        const colsList = mobile ? els.drawerColsList : els.panelColsList;
        colsSec.hidden = hiddenCols.length === 0;
        colsList.innerHTML = "";
        hiddenCols.forEach(function (row) {
            const li = document.createElement("li");
            if (row.tabHidden) li.classList.add("restore-blocked");

            const tag = document.createElement("span");
            tag.className = "tag";
            tag.textContent = row.tabName;
            li.appendChild(tag);

            const name = document.createElement("span");
            name.className = "name";
            name.textContent = row.label;
            li.appendChild(name);

            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "restore-btn";
            btn.textContent = "Restore";
            if (row.tabHidden) {
                btn.disabled = true;
                btn.title = "Restore the parent tab first";
            } else {
                btn.addEventListener("click", function () {
                    restoreColumn(row.tabKey, row.field);
                    if (mobile) closeDrawer();
                });
            }
            li.appendChild(btn);

            if (row.tabHidden) {
                const reason = document.createElement("div");
                reason.className = "restore-reason";
                reason.textContent = "Parent tab “" + row.tabName + "” is hidden.";
                li.appendChild(reason);
            }

            colsList.appendChild(li);
        });
    }

    function openDrawer() {
        els.drawerBackdrop.classList.add("open");
        els.drawerSheet.classList.add("open");
    }
    function closeDrawer() {
        els.drawerBackdrop.classList.remove("open");
        els.drawerSheet.classList.remove("open");
    }

    function wireDrawer() {
        els.fab.addEventListener("click", openDrawer);
        els.drawerBackdrop.addEventListener("click", closeDrawer);
        els.restoreAllBtn.addEventListener("click", restoreEverything);
        els.restoreAllBtnM.addEventListener("click", function () {
            restoreEverything();
            closeDrawer();
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") closeDrawer();
        });
    }

    // ---------- Action buttons ------------------------------------------
    function wireActionButtons() {
        els.exportBtn.addEventListener("click", exportExcel);
        els.emailBtn.addEventListener("click", function () { openModal(els.emailModal, prepEmailModal); });
        els.scheduleBtn.addEventListener("click", function () { openModal(els.scheduleModal, prepScheduleModal); });
        els.presetBtn.addEventListener("click", function () { openModal(els.presetModal, prepPresetModal); });
    }

    function collectLayouts() {
        // Snapshot of the current per-tab layout so we can send it to the
        // export / preset / schedule endpoints.
        const out = {};
        state.tabOrder.forEach(function (key) {
            const t = state.tabs[key];
            out[key] = {
                tab_hidden:    state.hiddenTabs.has(key),
                hidden_fields: Array.from(t.hiddenFields),
                field_order:   t.fieldOrder.slice(),
            };
        });
        return out;
    }

    async function exportExcel() {
        els.exportBtn.disabled = true;
        const old = els.exportBtn.innerHTML;
        els.exportBtn.textContent = "Exporting…";
        try {
            const res = await fetch(cfg.exportUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ params: cfg.params, layouts: collectLayouts() }),
            });
            if (!res.ok) throw new Error("HTTP " + res.status);
            const blob = await res.blob();
            const fname = fileNameFromHeader(res.headers.get("Content-Disposition"))
                       || (cfg.reportKey + ".xlsx");
            triggerDownload(blob, fname);
        } catch (err) {
            alert("Export failed: " + (err.message || err));
        } finally {
            els.exportBtn.innerHTML = old;
            els.exportBtn.disabled = false;
            if (typeof feather !== "undefined") feather.replace();
        }
    }

    // ---------- Modals ---------------------------------------------------
    function openModal(modalEl, prepFn) {
        if (typeof prepFn === "function") prepFn();
        modalEl.classList.add("open");
    }
    function closeModal(modalEl) { modalEl.classList.remove("open"); }

    function wireModals() {
        document.querySelectorAll("[data-close-modal]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                const m = document.getElementById(btn.getAttribute("data-close-modal"));
                if (m) closeModal(m);
            });
        });
        [els.presetModal, els.emailModal, els.scheduleModal].forEach(function (m) {
            m.addEventListener("click", function (e) {
                if (e.target === m) closeModal(m);
            });
        });

        // Save preset
        els.presetSaveBtn.addEventListener("click", async function () {
            els.presetMsg.style.display = "none";
            const name = (els.presetNameInput.value || "").trim();
            if (!name) {
                els.presetMsg.style.display = "";
                els.presetMsg.textContent = "Give it a name.";
                return;
            }
            const body = {
                name:       name,
                report_key: cfg.reportKey,
                params:     cfg.params,
                layouts:    els.presetIncludeLayout.checked ? collectLayouts() : {},
            };
            els.presetSaveBtn.disabled = true;
            try {
                const j = await postJson(cfg.presetSaveUrl, body);
                if (j && j.id) {
                    closeModal(els.presetModal);
                    flashToast("Preset saved. It's on your home page now.");
                } else {
                    els.presetMsg.style.display = "";
                    els.presetMsg.textContent = (j && j.error) || "Could not save preset.";
                }
            } catch (err) {
                els.presetMsg.style.display = "";
                els.presetMsg.textContent = err.message || String(err);
            } finally {
                els.presetSaveBtn.disabled = false;
            }
        });

        // Send email now
        els.emailSendBtn.addEventListener("click", async function () {
            els.emailMsg.style.display = "none";
            const recips = (els.emailRecipients.value || "").trim();
            const spOn   = !!(els.emailSpCheck && els.emailSpCheck.checked);
            const spPath = spOn && els.emailSpPath ? (els.emailSpPath.value || "").trim() : "";
            if (!recips && !spPath) {
                els.emailMsg.style.display = "";
                els.emailMsg.textContent =
                  "Enter at least one email address, or pick a SharePoint folder.";
                return;
            }
            if (spOn && !spPath) {
                els.emailMsg.style.display = "";
                els.emailMsg.textContent = "Pick a SharePoint folder (or uncheck the box).";
                return;
            }
            const body = {
                recipients:      recips,
                subject:         (els.emailSubject.value || "").trim() || defaultEmailSubject(),
                params:          cfg.params,
                layouts:         collectLayouts(),
                sharepoint_path: spPath || null,
            };
            els.emailSendBtn.disabled = true;
            try {
                const j = await postJson(cfg.emailUrl, body);
                if (j && j.ok) {
                    closeModal(els.emailModal);
                    let msg = recips
                      ? ("Email captured in outbox (" + (j.recipients_count || 0) + " recipient(s))")
                      : "Report saved.";
                    if (j.sharepoint_saved) msg += "; SharePoint: saved";
                    flashToast(msg + ".");
                } else {
                    els.emailMsg.style.display = "";
                    els.emailMsg.textContent = (j && j.error) || "Could not send.";
                }
            } catch (err) {
                els.emailMsg.style.display = "";
                els.emailMsg.textContent = err.message || String(err);
            } finally {
                els.emailSendBtn.disabled = false;
            }
        });

        // ---- SharePoint picker wiring (email modal) --------------------
        if (els.emailSpCheck && els.emailSpPicker) {
            els.emailSpCheck.addEventListener("change", function () {
                els.emailSpPicker.hidden = !els.emailSpCheck.checked;
            });
        }
        if (els.emailSpPickBtn) {
            els.emailSpPickBtn.addEventListener("click", async function () {
                if (!window.openSharePointPicker) {
                    alert("SharePoint picker not loaded.");
                    return;
                }
                const p = await window.openSharePointPicker({
                    initialPath: (els.emailSpPath && els.emailSpPath.value) || "",
                });
                if (p !== null && els.emailSpPath) els.emailSpPath.value = p;
            });
        }

        // ---- SharePoint picker wiring (schedule modal) -----------------
        if (els.scheduleSpCheck && els.scheduleSpPicker) {
            els.scheduleSpCheck.addEventListener("change", function () {
                els.scheduleSpPicker.hidden = !els.scheduleSpCheck.checked;
            });
        }
        if (els.scheduleSpPickBtn) {
            els.scheduleSpPickBtn.addEventListener("click", async function () {
                if (!window.openSharePointPicker) {
                    alert("SharePoint picker not loaded.");
                    return;
                }
                const p = await window.openSharePointPicker({
                    initialPath: (els.scheduleSpPath && els.scheduleSpPath.value) || "",
                });
                if (p !== null && els.scheduleSpPath) els.scheduleSpPath.value = p;
            });
        }
    }

    function prepPresetModal() {
        els.presetMsg.style.display = "none";
        els.presetNameInput.value = defaultPresetName();
        els.presetIncludeLayout.checked = hasAnyCustomisation();
        setTimeout(function () { els.presetNameInput.focus(); els.presetNameInput.select(); }, 30);
    }

    function prepEmailModal() {
        els.emailMsg.style.display = "none";
        if (!els.emailSubject.value) els.emailSubject.value = defaultEmailSubject();
    }

    function hasAnyCustomisation() {
        if (state.hiddenTabs.size > 0) return true;
        return state.tabOrder.some(function (k) {
            const t = state.tabs[k];
            if (!t) return false;
            if (t.hiddenFields.size > 0) return true;
            // Order different from canonical?
            const canonical = t.columnsMeta.map(function (m) { return m.field; }).join("|");
            return t.fieldOrder.join("|") !== canonical;
        });
    }

    function defaultPresetName() {
        const now = new Date();
        return cfg.reportName + " - " + now.toLocaleDateString();
    }
    function defaultEmailSubject() {
        return cfg.reportName + " (test)";
    }

    // ---------- Schedule modal ------------------------------------------
    function wireScheduleModal() {
        // Cadence pills
        els.cadenceGroup.addEventListener("click", function (e) {
            const pill = e.target.closest(".pill");
            if (!pill) return;
            els.cadenceGroup.querySelectorAll(".pill").forEach(function (p) { p.classList.remove("active"); });
            pill.classList.add("active");
            state.scheduleUi.cadence = pill.dataset.cadence;
            els.weeklyRow.hidden  = state.scheduleUi.cadence !== "weekly";
            els.monthlyRow.hidden = state.scheduleUi.cadence !== "monthly";
            updateSchedulePreview();
        });

        // Weekday chips
        els.weekdayGroup.addEventListener("click", function (e) {
            const b = e.target.closest(".weekday");
            if (!b) return;
            const d = b.dataset.day;
            if (state.scheduleUi.weekdays.has(d)) {
                state.scheduleUi.weekdays.delete(d);
                b.classList.remove("active");
            } else {
                state.scheduleUi.weekdays.add(d);
                b.classList.add("active");
            }
            updateSchedulePreview();
        });

        // Monthday buttons (multi-select like weekday)
        els.monthdayGroup.addEventListener("click", function (e) {
            const b = e.target.closest(".monthday");
            if (!b) return;
            const d = parseInt(b.dataset.day, 10);
            if (state.scheduleUi.monthdays.has(d)) {
                state.scheduleUi.monthdays.delete(d);
                b.classList.remove("active");
            } else {
                state.scheduleUi.monthdays.add(d);
                b.classList.add("active");
            }
            updateSchedulePreview();
        });

        // Time, dates
        ["input", "change"].forEach(function (ev) {
            els.scheduleTime.addEventListener(ev, updateSchedulePreview);
            els.scheduleStart.addEventListener(ev, updateSchedulePreview);
            els.scheduleEnd.addEventListener(ev, updateSchedulePreview);
        });
        els.scheduleHasEnd.addEventListener("change", function () {
            els.scheduleEnd.disabled = !els.scheduleHasEnd.checked;
            updateSchedulePreview();
        });

        els.scheduleSaveBtn.addEventListener("click", saveSchedule);
    }

    function prepScheduleModal() {
        els.scheduleMsg.style.display = "none";

        // Default weekdays = Monday preselected
        els.weekdayGroup.querySelectorAll(".weekday").forEach(function (b) {
            const on = state.scheduleUi.weekdays.has(b.dataset.day);
            b.classList.toggle("active", on);
        });

        // Default monthdays = 1st preselected
        els.monthdayGroup.querySelectorAll(".monthday").forEach(function (b) {
            const d = parseInt(b.dataset.day, 10);
            const on = state.scheduleUi.monthdays.has(d);
            b.classList.toggle("active", on);
        });

        if (!els.scheduleStart.value) els.scheduleStart.value = todayIso();
        if (!els.scheduleTime.value)  els.scheduleTime.value  = "07:00";
        if (!els.scheduleName.value)  els.scheduleName.value  = defaultPresetName();

        updateSchedulePreview();
    }

    function updateSchedulePreview() {
        const c = state.scheduleUi.cadence;
        const time = els.scheduleTime.value || "07:00";
        const time12 = fmt12h(time);
        const start = els.scheduleStart.value || todayIso();
        let cadenceStr;
        if (c === "daily") {
            cadenceStr = "every day";
        } else if (c === "weekly") {
            const dayNames = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
            const pretty = dayNames.filter(function (d) { return state.scheduleUi.weekdays.has(d); })
                                  .map(function (d) { return weekdayPretty(d); });
            cadenceStr = pretty.length
                ? "every week on " + prettyJoin(pretty)
                : "weekly (pick a day!)";
        } else if (c === "monthly") {
            const days = Array.from(state.scheduleUi.monthdays).sort(function (a, b) { return a - b; });
            if (!days.length) {
                cadenceStr = "monthly (pick a day!)";
            } else {
                const dayStrs = days.map(function (d) { return d === -1 ? "last day" : String(d); });
                cadenceStr = "on the " + prettyJoin(dayStrs) + " of every month";
            }
        } else {
            cadenceStr = "one time only";
        }
        const endBit = els.scheduleHasEnd.checked && els.scheduleEnd.value
            ? ", ending " + prettyDate(els.scheduleEnd.value)
            : "";
        const recips = (els.scheduleRecipients.value || "").trim();
        const recipBit = recips
            ? ", emailing " + recips
            : ", emailing (no one yet -- add addresses below)";
        els.schedulePreview.textContent =
            "Runs " + cadenceStr + " at " + time12 +
            " starting " + prettyDate(start) + endBit + recipBit + ".";
    }

    async function saveSchedule() {
        els.scheduleMsg.style.display = "none";
        const c = state.scheduleUi.cadence;
        const recips = (els.scheduleRecipients.value || "").trim();
        const name = (els.scheduleName.value || "").trim();
        const spOn   = !!(els.scheduleSpCheck && els.scheduleSpCheck.checked);
        const spPath = spOn && els.scheduleSpPath ? (els.scheduleSpPath.value || "").trim() : "";

        if (!name) return scheduleError("Give the schedule a name.");
        if (!recips && !spPath)
            return scheduleError(
                "Pick at least one delivery target: email recipients or SharePoint folder.");
        if (spOn && !spPath) return scheduleError("Pick a SharePoint folder (or uncheck the box).");
        if (!els.scheduleTime.value) return scheduleError("Pick a time of day.");
        if (!els.scheduleStart.value) return scheduleError("Pick a start date.");
        if (c === "weekly" && state.scheduleUi.weekdays.size === 0)
            return scheduleError("Pick at least one day of the week.");
        if (c === "monthly" && state.scheduleUi.monthdays.size === 0)
            return scheduleError("Pick at least one day of the month.");

        const body = {
            name:            name,
            report_key:      cfg.reportKey,
            params:          cfg.params,
            layouts:         collectLayouts(),
            cadence:         c,
            weekdays:        c === "weekly" ? Array.from(state.scheduleUi.weekdays).join(",") : "",
            monthdays:       c === "monthly" ? Array.from(state.scheduleUi.monthdays).join(",") : "",
            time_hhmm:       els.scheduleTime.value,
            start_date:      els.scheduleStart.value,
            end_date:        els.scheduleHasEnd.checked ? els.scheduleEnd.value : null,
            recipients:      recips,
            sharepoint_path: spPath || null,
        };
        els.scheduleSaveBtn.disabled = true;
        try {
            const j = await postJson(cfg.scheduleUrl, body);
            if (j && j.id) {
                closeModal(els.scheduleModal);
                flashToast("Scheduled. It's saved under /schedules.");
            } else {
                scheduleError((j && j.error) || "Could not save schedule.");
            }
        } catch (err) {
            scheduleError(err.message || String(err));
        } finally {
            els.scheduleSaveBtn.disabled = false;
        }
    }

    function scheduleError(msg) {
        els.scheduleMsg.style.display = "";
        els.scheduleMsg.textContent = msg;
    }

    // ---------- Utils ----------------------------------------------------
    function showStatus(msg, isError, spin) {
        if (!msg) {
            els.status.innerHTML = state.generatedAt
                ? '<span class="subtle">Generated ' + escHtml(fmtLocal(state.generatedAt)) + '</span>'
                : "";
            return;
        }
        const cls = isError ? "subtle" : "subtle";
        const spinner = spin ? '<span class="spinner-small"></span>' : "";
        els.status.innerHTML = spinner + '<span class="' + cls + '" style="' +
            (isError ? "color:var(--error);" : "") + '">' + escHtml(msg) + '</span>';
    }

    function postJson(url, payload) {
        return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload || {}),
        }).then(function (r) {
            if (!r.ok) {
                return r.text().then(function (t) {
                    throw new Error("HTTP " + r.status + (t ? ": " + t.slice(0, 120) : ""));
                });
            }
            const ct = r.headers.get("Content-Type") || "";
            return ct.indexOf("application/json") >= 0 ? r.json() : r.text();
        });
    }

    function safeParse(s, fallback) {
        try { return JSON.parse(s || "{}"); } catch (_) { return fallback; }
    }
    function escHtml(s) {
        if (s == null) return "";
        return String(s)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }
    function fmtLocal(iso) {
        try {
            const d = new Date(iso);
            if (isNaN(d)) return iso;
            return d.toLocaleString();
        } catch (_) { return iso; }
    }
    function fmtMoney(v) {
        if (v == null || v === "") return "";
        const n = Number(v);
        if (isNaN(n)) return escHtml(v);
        return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
    }
    function fmtInt(v) {
        if (v == null || v === "") return "";
        const n = Number(v);
        if (isNaN(n)) return escHtml(v);
        return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    function fmtPercent(v) {
        if (v == null || v === "") return "";
        const n = Number(v);
        if (isNaN(n)) return escHtml(v);
        return (n * 100).toFixed(1) + "%";
    }
    function fmtDate(v) {
        if (!v) return "";
        try {
            const d = new Date(v);
            if (isNaN(d)) return escHtml(v);
            return d.toLocaleDateString();
        } catch (_) { return escHtml(v); }
    }
    function fileNameFromHeader(h) {
        if (!h) return null;
        const m = /filename\*?=(?:UTF-8'')?\"?([^;\"]+)\"?/i.exec(h);
        return m ? decodeURIComponent(m[1]) : null;
    }
    function triggerDownload(blob, name) {
        const a = document.createElement("a");
        const url = URL.createObjectURL(blob);
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        setTimeout(function () {
            URL.revokeObjectURL(url);
            a.remove();
        }, 100);
    }
    function flashToast(msg) {
        // Very lightweight toast so we don't pull in a dependency.
        const t = document.createElement("div");
        t.textContent = msg;
        t.style.cssText = [
            "position:fixed",
            "left:50%",
            "bottom:110px",
            "transform:translateX(-50%)",
            "background:var(--primary)",
            "color:#fff",
            "padding:10px 14px",
            "border-radius:10px",
            "font-size:14px",
            "box-shadow:var(--shadow-lg)",
            "z-index:400",
            "opacity:0",
            "transition:opacity .2s",
        ].join(";");
        document.body.appendChild(t);
        requestAnimationFrame(function () { t.style.opacity = "1"; });
        setTimeout(function () {
            t.style.opacity = "0";
            setTimeout(function () { t.remove(); }, 300);
        }, 2400);
    }
    function todayIso() {
        const d = new Date();
        return d.getFullYear() + "-" +
               String(d.getMonth() + 1).padStart(2, "0") + "-" +
               String(d.getDate()).padStart(2, "0");
    }
    function prettyDate(iso) {
        try {
            const d = new Date(iso + "T00:00:00");
            if (isNaN(d)) return iso;
            return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
        } catch (_) { return iso; }
    }
    function fmt12h(hhmm) {
        const parts = (hhmm || "").split(":");
        let h = parseInt(parts[0], 10);
        const m = (parts[1] || "00").padStart(2, "0");
        if (isNaN(h)) return hhmm;
        const ampm = h >= 12 ? "PM" : "AM";
        h = h % 12; if (h === 0) h = 12;
        return h + ":" + m + " " + ampm;
    }
    function weekdayPretty(d) {
        return { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" }[d] || d;
    }
    function prettyJoin(arr) {
        if (arr.length <= 1) return arr[0] || "";
        if (arr.length === 2) return arr[0] + " and " + arr[1];
        return arr.slice(0, -1).join(", ") + ", and " + arr[arr.length - 1];
    }
})();
