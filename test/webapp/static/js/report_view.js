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
        refreshBtn:         $("refreshDataBtn"),
        resetBtn:           $("resetViewBtn"),
        exportBtn:          $("exportXlsxBtn"),
        exportRowCount:     $("exportRowCount"),
        emailBtn:           $("emailNowBtn"),
        scheduleBtn:        $("scheduleBtn"),
        presetBtn:          $("savePresetBtn"),

        // Sort & Group toolbar
        sortGroupBar:       $("sortGroupBar"),
        sortChips:          $("sortChips"),
        groupChips:         $("groupChips"),
        addSortSelect:      $("addSortSelect"),
        addGroupSelect:     $("addGroupSelect"),

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
        // Snapshot of the layout right after the first runReport() so
        // "Reset to default view" can restore it. Populated by
        // captureDefaultLayout() once on first load.
        defaultLayout: null,
    };

    /** Floating popover for a single column filter (one open at a time). */
    let colFilterPopover = null;
    let colFilterPopoverAnchor = null;
    let colFilterOutsideHandler = null;
    let colFilterKeyHandler = null;

    // ---------- Boot -----------------------------------------------------
    runReport().catch(function (err) {
        showStatus("Could not load report: " + (err.message || err), true);
    });
    wireActionButtons();
    wireDrawer();
    wireModals();
    wireScheduleModal();
    wireSortGroupBar();

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
            api:                  { cls: "src-live",   text: "LIVE DATA" },
            reporting_api:        { cls: "src-live",   text: "LIVE DATA" },
            fresh_cache:          { cls: "src-cache",  text: "API CACHE" },
            stale_cache:          { cls: "src-cache",  text: "STALE CACHE" },
            mirror_after_failure: { cls: "src-mirror", text: "SQLITE MIRROR" },
            mirror_no_api:        { cls: "src-mirror", text: "SQLITE MIRROR" },
            failed:               { cls: "src-error",  text: "DATA FAILED" },
            reporting_api_failed: { cls: "src-error",  text: "API FAILED" },
        };
        const info = known[meta.source] || { cls: "src-cache", text: meta.source };

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
        if (meta.error) tipParts.push("Error: " + meta.error);
        el.title = tipParts.filter(Boolean).join("\n");
        el.hidden = false;
    }

    // ---------- Fetch & render ------------------------------------------
    /**
     * Fetch the report and build the grid.
     *
     * @param {object} [opts]
     * @param {boolean} [opts.preserveLayout] If true, the user's current
     *        column hides / column order / hidden tabs are kept after
     *        the new data lands. Used by the "Refresh data" button.
     */
    async function runReport(opts) {
        opts = opts || {};
        const preserveLayout = !!opts.preserveLayout;
        // Snapshot the layout BEFORE wiping state so we can restore it.
        const snapshot = preserveLayout ? snapshotLayout() : null;

        showStatus(preserveLayout ? "Refreshing data…" : "Loading report…", false, true);
        const payload = await postJson(cfg.runUrl, {
            params: cfg.params,
            cache_mode: "cache_first",
            wait_seconds: 5,
        });
        const cacheMeta = payload && payload._cache_first;
        if (cacheMeta && cacheMeta.state === "refreshing" && cacheMeta.job_id) {
            showStatus("Fresh data is still loading…", false, true);
            pollFreshData(cacheMeta.job_id, { preserveLayout: preserveLayout, snapshot: snapshot, autoApply: false });
            return;
        }

        applyReportPayload(payload, preserveLayout, snapshot);

        if (cacheMeta && cacheMeta.job_id && /^cached_/.test(cacheMeta.state || "")) {
            const cacheMsg = cachedDataMessage(cacheMeta);
            flashToast(cacheMsg || "Using cached data while fresh data loads.");
            pollFreshData(cacheMeta.job_id, { preserveLayout: true, snapshot: snapshot, autoApply: false });
        }
    }

    function applyReportPayload(payload, preserveLayout, snapshot) {
        renderSourceBadge(payload.data_source);
        state.generatedAt = payload.generated_at || null;
        state.activeTab = null;
        state.tabs = Object.create(null);
        state.tabOrder = [];
        state.hiddenTabs = new Set();

        (payload.tabs || []).forEach(function (t) {
            // The server can hint at a starting sort/group layout for a
            // tab (the Summary tab uses this to come pre-grouped by
            // Customer Name). The user can edit/remove these like any
            // other sort/group level via the toolbar.
            const seed = t.default_layout || {};
            const seedSort = Array.isArray(seed.sort_levels)
                ? seed.sort_levels.map(function (s) { return { field: s.field, dir: s.dir || "asc" }; })
                : [];
            const seedGroup = Array.isArray(seed.group_levels)
                ? seed.group_levels.slice()
                : [];

            state.tabs[t.key] = {
                name:         t.name,
                sourceTabKey: t.duplicate_of || t.key,
                isDuplicate:  !!t.duplicate_of,
                data:         Array.isArray(t.rows) ? t.rows : [],
                columnsMeta:  Array.isArray(t.columns) ? t.columns.map(cloneCol) : [],
                hiddenFields: new Set(),
                fieldOrder:   (t.columns || []).map(function (c) { return c.field; }),
                grid:         null,
                container:    null,
                // User-driven sort + group state. Each level is
                // {field, dir} for sort and a bare field name for group.
                sortLevels:   seedSort,
                groupLevels:  seedGroup,
                columnFilters: Object.create(null),
            };
            state.tabOrder.push(t.key);
        });

        if (!state.tabOrder.length) {
            showStatus("", false, false);
            els.emptyState.hidden = false;
            els.emptyStateMsg.textContent = "No tabs were returned.";
            return;
        }

        if (snapshot) {
            applyLayoutSnapshot(snapshot);
        } else {
            applyPresetLayouts();
        }

        buildTabStrip();
        buildGridContainers();
        const firstVisible = (snapshot && state.tabs[snapshot.activeTab] && !state.hiddenTabs.has(snapshot.activeTab))
            ? snapshot.activeTab
            : (state.tabOrder.find(function (k) { return !state.hiddenTabs.has(k); }) || state.tabOrder[0]);
        activateTab(firstVisible);
        refreshHiddenUi();

        // First load only: stash the original layout so the "Reset to
        // default view" button can put it back. Sort / group / column
        // filters all live on tab state, so this can run without waiting
        // for Tabulator to finish building.
        if (!preserveLayout && !state.defaultLayout) {
            state.defaultLayout = snapshotLayout();
            updateChangedState();
        }
        updateChangedState();
        updateExportRowCount();

        const tsLabel = state.generatedAt
            ? ("Generated " + fmtLocal(state.generatedAt))
            : "Generated just now";
        showStatus(tsLabel, false, false);
    }

    function pollFreshData(jobId, opts) {
        opts = opts || {};
        if (!jobId) return;
        const url = (window.V2_URL_PREFIX || "") + "/api/reports/jobs/" + encodeURIComponent(jobId);
        let attempts = 0;
        function tick() {
            attempts += 1;
            fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
                .then(function (r) { return r.json(); })
                .then(function (j) {
                    if (j.status === "success" && j.payload) {
                        const apply = opts.autoApply || window.confirm(freshDataPrompt(j));
                        if (apply) {
                            const snap = snapshotLayout();
                            applyReportPayload(j.payload, true, snap);
                            flashToast("Fresh data loaded.");
                        } else {
                            flashToast("Fresh data is ready when you refresh.");
                        }
                        return;
                    }
                    if (j.status === "failed") {
                        showStatus("Fresh refresh failed: " + (j.error || "unknown error"), true, false);
                        return;
                    }
                    if (attempts < 180) {
                        setTimeout(tick, 2000);
                    }
                })
                .catch(function () {
                    if (attempts < 180) setTimeout(tick, 3000);
                });
        }
        setTimeout(tick, 1500);
    }

    function cachedDataMessage(meta) {
        const parts = [];
        if (meta && meta.refreshed_utc) {
            parts.push("Showing cache from " + fmtLocal(meta.refreshed_utc));
            const age = relativeAge(meta.refreshed_utc);
            if (age) parts.push(age + " old");
        }
        if (meta && meta.total_rows != null) {
            parts.push(fmtInt(meta.total_rows) + " tab rows");
        }
        return parts.length ? (parts.join(" · ") + ". Fresh data is loading.") : "";
    }

    function freshDataPrompt(job) {
        const currentRows = totalCurrentRows();
        const freshRows = job.fresh_row_count != null ? Number(job.fresh_row_count) : totalRowsFromPayload(job.payload);
        const delta = job.row_delta != null ? Number(job.row_delta) : (freshRows - currentRows);
        const lines = ["Fresh data is ready."];
        const currentStamp = job.cached_refreshed_utc || (state.generatedAt || "");
        const freshStamp = job.fresh_refreshed_utc || job.refreshed_utc || "";
        if (currentStamp && freshStamp) {
            lines.push("Current view: " + fmtLocal(currentStamp) + " (" + (relativeAge(currentStamp, freshStamp) || "older") + " older than fresh data).");
            lines.push("Fresh data: " + fmtLocal(freshStamp) + ".");
        } else if (freshStamp) {
            lines.push("Fresh data: " + fmtLocal(freshStamp) + ".");
        }
        lines.push("Rows: " + fmtInt(currentRows) + " now, " + fmtInt(freshRows) + " fresh (" + signedInt(delta) + ").");
        lines.push("");
        lines.push("Update this view using your current layout?");
        return lines.join("\n");
    }

    /** Capture the user's current per-tab visibility / order / sort /
     *  filter / active-tab state so it can be re-applied (Refresh data)
     *  or compared against (Reset visibility / changed-marker).
     *  Sort, group, and column filters all live on tab state, so a
     *  snapshot is meaningful even before grids finish building. */
    function snapshotLayout() {
        const snap = {
            activeTab:  state.activeTab,
            hiddenTabs: Array.from(state.hiddenTabs),
            tabs:       {},
        };
        state.tabOrder.forEach(function (key) {
            const t = state.tabs[key];
            if (!t) return;
            snap.tabs[key] = {
                hidden_fields: Array.from(t.hiddenFields),
                field_order:   t.fieldOrder.slice(),
                sort_levels:   (t.sortLevels || []).map(function (s) { return { field: s.field, dir: s.dir }; }),
                group_levels:  (t.groupLevels || []).slice(),
                filters:       filtersSnapshotForPersist(t),
                duplicate_of:  t.isDuplicate ? (t.sourceTabKey || null) : null,
                tab_name:      t.name || "",
            };
        });
        return snap;
    }

    /** Push a snapshot back onto fresh state. Anything that no longer
     *  exists in the new payload (a column the SP dropped, a tab that
     *  isn't returned anymore) is silently skipped. */
    function applyLayoutSnapshot(snap) {
        if (!snap) return;
        Object.keys(snap.tabs || {}).forEach(function (tabKey) {
            if (state.tabs[tabKey]) return;
            const saved = snap.tabs[tabKey] || {};
            const sourceKey = saved.duplicate_of;
            if (!sourceKey || !state.tabs[sourceKey]) return;
            state.tabs[tabKey] = cloneTabState(
                state.tabs[sourceKey],
                saved.tab_name || state.tabs[sourceKey].name,
                sourceKey,
            );
            state.tabOrder.push(tabKey);
        });
        state.hiddenTabs = new Set(snap.hiddenTabs.filter(function (k) { return !!state.tabs[k]; }));

        Object.keys(snap.tabs).forEach(function (tabKey) {
            const t = state.tabs[tabKey];
            const saved = snap.tabs[tabKey];
            if (!t || !saved) return;

            const validFields = new Set(t.columnsMeta.map(function (c) { return c.field; }));
            (saved.hidden_fields || []).forEach(function (f) {
                if (validFields.has(f)) t.hiddenFields.add(f);
            });
            if (Array.isArray(saved.field_order) && saved.field_order.length) {
                const ordered = [];
                const seen = new Set();
                saved.field_order.forEach(function (f) {
                    if (validFields.has(f) && !seen.has(f)) {
                        ordered.push(f); seen.add(f);
                    }
                });
                t.columnsMeta.forEach(function (c) {
                    if (!seen.has(c.field)) ordered.push(c.field);
                });
                t.fieldOrder = ordered;
            }
            // Sort + group state can be restored synchronously since we
            // own the data pipeline.
            t.sortLevels = (saved.sort_levels || []).filter(function (s) {
                return validFields.has(s.field);
            }).map(function (s) { return { field: s.field, dir: s.dir || "asc" }; });
            t.groupLevels = (saved.group_levels || []).filter(function (f) {
                return validFields.has(f);
            });
            resetColumnFiltersFromSaved(
                t,
                (saved.filters || []).filter(function (f) {
                    return validFields.has(f.field);
                }),
            );
        });
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
        materializePresetDuplicateTabs(layouts);

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
            if (Array.isArray(saved.sort_levels)) {
                tab.sortLevels = saved.sort_levels.map(function (s) {
                    return { field: s.field, dir: s.dir || "asc" };
                });
            }
            if (Array.isArray(saved.group_levels)) {
                tab.groupLevels = saved.group_levels.slice();
            }
            if (Array.isArray(saved.filters)) {
                resetColumnFiltersFromSaved(
                    tab,
                    saved.filters.filter(function (f) {
                        return f && validFields.has(f.field);
                    }),
                );
            }
        });
    }

    function materializePresetDuplicateTabs(layouts) {
        Object.keys(layouts).forEach(function (tabKey) {
            if (state.tabs[tabKey]) return;
            const saved = layouts[tabKey] || {};
            const sourceKey = saved.duplicate_of || saved.source_tab_key;
            if (!sourceKey || !state.tabs[sourceKey]) return;
            state.tabs[tabKey] = cloneTabState(
                state.tabs[sourceKey],
                saved.tab_name || state.tabs[sourceKey].name,
                sourceKey,
            );
            state.tabOrder.push(tabKey);
        });
    }

    function cloneTabState(source, name, sourceKey) {
        return {
            name:         name || source.name,
            sourceTabKey: sourceKey || source.sourceTabKey || null,
            isDuplicate:  true,
            data:         (source.data || []).map(function (r) { return Object.assign({}, r); }),
            columnsMeta:  (source.columnsMeta || []).map(cloneCol),
            hiddenFields: new Set(Array.from(source.hiddenFields || [])),
            fieldOrder:   (source.fieldOrder || []).slice(),
            grid:         null,
            container:    null,
            sortLevels:   (source.sortLevels || []).map(function (s) { return { field: s.field, dir: s.dir || "asc" }; }),
            groupLevels:  (source.groupLevels || []).slice(),
            columnFilters:(function () {
                const s = source.columnFilters;
                const out = Object.create(null);
                if (!s || typeof s !== "object") return out;
                Object.keys(s).forEach(function (k) {
                    out[k] = cloneFilterVal(s[k]);
                });
                return out;
            })(),
        };
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
            btn.innerHTML = '<span class="viewer-tab-name"></span>';
            btn.querySelector(".viewer-tab-name").textContent = t.name;
            btn.addEventListener("click", function (e) {
                activateTab(key);
            });
            btn.addEventListener("contextmenu", function (e) {
                e.preventDefault();
                openTabContextMenu(key, e.clientX, e.clientY);
            });
            els.tabStrip.appendChild(btn);
        });
    }

    let tabContextMenuEl = null;
    function closeTabContextMenu() {
        if (tabContextMenuEl && tabContextMenuEl.parentNode) {
            tabContextMenuEl.parentNode.removeChild(tabContextMenuEl);
        }
        tabContextMenuEl = null;
    }

    function openTabContextMenu(key, x, y) {
        closeTabContextMenu();
        const t = state.tabs[key];
        if (!t) return;
        const menu = document.createElement("div");
        menu.className = "tab-context-menu";
        const mkBtn = function (label, onClick, danger) {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "tab-context-item" + (danger ? " danger" : "");
            b.textContent = label;
            b.addEventListener("click", function (ev) {
                ev.preventDefault();
                closeTabContextMenu();
                onClick();
            });
            return b;
        };
        menu.appendChild(mkBtn("Duplicate tab", function () { duplicateTabWithPrompt(key); }, false));
        menu.appendChild(
            mkBtn(t.isDuplicate ? "Delete tab" : "Hide tab", function () { hideTab(key); }, !!t.isDuplicate),
        );
        menu.style.left = Math.max(8, x) + "px";
        menu.style.top = Math.max(8, y) + "px";
        document.body.appendChild(menu);
        tabContextMenuEl = menu;
        setTimeout(function () {
            document.addEventListener("click", closeTabContextMenu, { once: true, capture: true });
            document.addEventListener("contextmenu", closeTabContextMenu, { once: true, capture: true });
            document.addEventListener("keydown", function escClose(ev) {
                if (ev.key === "Escape") closeTabContextMenu();
            }, { once: true, capture: true });
        }, 0);
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
        closeColHeaderFilterPopover();
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
        renderSortGroupBar();
        updateExportRowCount();
    }

    function ensureGrid(key) {
        const t = state.tabs[key];
        if (t.grid) return t.grid;

        // We compute sorted/grouped display rows ourselves so we can
        // inject totals + spacer rows on group breaks. Tabulator just
        // renders + column header filter buttons / column moves / hides.
        t.grid = new Tabulator(t.container, {
            data:          computeDisplayRows(t),
            layout:        "fitDataTable",    // natural width -> grid-root scrolls
            columnDefaults:{
                headerHozAlign: "left",
                hozAlign:       "left",
                resizable:      true,
                headerContextMenu: tabulatorHeaderCtxMenu(key),
                headerSort:     false,        // we handle sort ourselves
            },
            columns:       buildColumnDefs(key),
            movableColumns:true,
            height:        "60vh",
            placeholder:   "No rows for the selected filters.",
            // Style server-shipped totals/spacers (Summary tab) and
            // user-driven group breaks identically: bold+border for
            // totals, blank-row for spacers, double-border for grand.
            rowFormatter:  decorateRow,
            columnMoved:   function () { syncFieldOrder(key); updateChangedState(); },
            dataFiltered:  function () {
                rebuildGridDataFromFilters(key);
                if (key === state.activeTab) updateExportRowCount();
                updateChangedState();
            },
        });

        // Custom header click handler -> our own sort-level state.
        // Plain click  = replace sort (1 level, descending if numeric/percent
        //                else ascending); a second click on same column flips dir.
        // Shift+click  = add a new level (or flip dir of an existing level).
        t.grid.on("headerClick", function (ev, column) {
            if (ev && ev.target && ev.target.closest && ev.target.closest(".col-header-filter-btn")) return;
            const field = column.getField();
            if (!field) return;
            const meta = t.columnsMeta.find(function (c) { return c.field === field; });
            if (!meta) return;

            const existing = t.sortLevels.find(function (s) { return s.field === field; });
            if (ev.shiftKey) {
                if (existing) {
                    existing.dir = (existing.dir === "asc") ? "desc" : "asc";
                } else {
                    t.sortLevels.push({ field: field, dir: defaultDirFor(meta.type) });
                }
            } else {
                if (existing && t.sortLevels.length === 1) {
                    existing.dir = (existing.dir === "asc") ? "desc" : "asc";
                } else {
                    t.sortLevels = [{ field: field, dir: defaultDirFor(meta.type) }];
                }
            }
            applySortGroupChange(key);
        });

        t.grid.on("tableBuilt", function () {
            delete t._restoreSorters;  // legacy: sort now lives on tab.sortLevels
            const f = activeHeaderFilters(t);
            t._hasActiveFilters = f.length > 0;
            t._filteredRawCount = applyHeaderFiltersToRaw(t, f).length;
            if (typeof feather !== "undefined") feather.replace();
            syncColHeaderFilterButtons(key);
            if (key === state.activeTab) {
                renderSortGroupBar();
                updateExportRowCount();
            }
            updateChangedState();
        });

        return t.grid;
    }

    function defaultDirFor(type) {
        return (type === "money" || type === "int" || type === "percent" || type === "date")
            ? "desc"
            : "asc";
    }

    /** Tabulator rowFormatter: paint totals / spacer rows distinctly so
     *  the on-screen preview matches what Excel will render. */
    function decorateRow(row) {
        const data = row.getData();
        const el = row.getElement();
        el.classList.remove("row-total", "row-grand-total", "row-spacer");
        if (!data) return;
        if (data._is_spacer) {
            el.classList.add("row-spacer");
            return;
        }
        if (data._is_total) {
            el.classList.add("row-total");
            // Heuristic: GRAND TOTAL rows are styled extra-bold. The
            // builder marks them by putting "GRAND TOTAL" in the first
            // text column.
            const txt = JSON.stringify(data || {}).toUpperCase();
            if (txt.indexOf("GRAND TOTAL") >= 0) {
                el.classList.add("row-grand-total");
            }
        }
    }

    /** Compute the list of rows Tabulator should render for tab `t`,
     *  honouring the user's sortLevels + groupLevels. Totals + spacer
     *  rows are injected on group breaks (none if the user has cleared
     *  the group levels).
     *
     *  Optionally pre-filter the raw rows with `filterFn(row) -> bool`
     *  so totals reflect only the visible subset. */
    function computeDisplayRows(t, filterFn) {
        const rawAll = (t.data || []).slice();
        let raw = rawAll.filter(function (r) { return !(r && (r._is_total || r._is_spacer)); });
        if (typeof filterFn === "function") {
            raw = raw.filter(filterFn);
        }

        // Sort: group levels first (they always win), then user sorts.
        const sortKeys = (t.groupLevels || []).map(function (f) {
            return { field: f, dir: "asc" };
        }).concat(t.sortLevels || []);
        if (sortKeys.length) {
            const cmp = compareByKeys(t, sortKeys);
            raw.sort(cmp);
        }

        if (!t.groupLevels || !t.groupLevels.length) return raw;

        // Walk and inject per-group-level totals + spacer at each break.
        return injectGroupTotals(t, raw);
    }

    function ensureColumnFilters(t) {
        if (!t) return;
        if (!t.columnFilters) t.columnFilters = Object.create(null);
    }

    function cloneFilterVal(v) {
        if (v && typeof v === "object" && v.op) {
            if (Array.isArray(v.v)) return { op: v.op, v: v.v.slice() };
            return { op: v.op, v: v.v };
        }
        return v;
    }

    function resetColumnFiltersFromSaved(t, list) {
        ensureColumnFilters(t);
        Object.keys(t.columnFilters).forEach(function (k) {
            delete t.columnFilters[k];
        });
        const valid = new Set((t.columnsMeta || []).map(function (c) { return c.field; }));
        (list || []).forEach(function (f) {
            if (!f || !valid.has(f.field)) return;
            if (f.value === "" || f.value == null) return;
            t.columnFilters[f.field] = cloneFilterVal(f.value);
        });
    }

    function filtersSnapshotForPersist(t) {
        return activeHeaderFilters(t).map(function (f) {
            return { field: f.field, value: cloneFilterVal(f.value) };
        });
    }

    function serializeFiltersForCompare(filtersArr) {
        return (filtersArr || []).filter(function (f) {
            return f && f.field && f.value !== "" && f.value != null;
        }).map(function (f) {
            return f.field + ":" + JSON.stringify(f.value);
        }).sort().join("|");
    }

    /** Active filters for the grid pipeline (stored on tab `columnFilters`). */
    function activeHeaderFilters(t) {
        if (!t) return [];
        ensureColumnFilters(t);
        var out = [];
        Object.keys(t.columnFilters).forEach(function (field) {
            var val = t.columnFilters[field];
            if (val === "" || val == null) return;
            if (typeof val === "object" && val.op && isEmptyFilter(val)) return;
            out.push({ field: field, value: val });
        });
        return out;
    }

    function applyHeaderFiltersToRaw(t, filters) {
        const raw = (t.data || []).filter(function (r) { return r && !r._is_total && !r._is_spacer; });
        if (!filters || !filters.length) return raw;
        return raw.filter(function (row) {
            return filters.every(function (f) {
                const meta = t.columnsMeta.find(function (c) { return c.field === f.field; });
                if (!meta) return true;
                return applyHeaderFilter(meta, f.value, row[f.field], row);
            });
        });
    }

    function rebuildGridDataFromFilters(key) {
        const t = state.tabs[key];
        if (!t || !t.grid || t._rebuildingData) return;
        const filters = activeHeaderFilters(t);
        const filteredRaw = applyHeaderFiltersToRaw(t, filters);
        t._hasActiveFilters = filters.length > 0;
        t._filteredRawCount = filteredRaw.length;
        t._rebuildingData = true;
        try {
            const display = computeDisplayRows(t, function (r) {
                return filteredRaw.indexOf(r) >= 0;
            });
            t.grid.setData(display);
        } catch (_) {
            // ignore
        } finally {
            t._rebuildingData = false;
        }
        syncColHeaderFilterButtons(key);
    }

    function compareByKeys(t, keys) {
        const typeOf = {};
        t.columnsMeta.forEach(function (c) { typeOf[c.field] = c.type; });
        return function (a, b) {
            for (let i = 0; i < keys.length; i++) {
                const k = keys[i];
                const va = a[k.field];
                const vb = b[k.field];
                let c = compareVals(va, vb, typeOf[k.field] || "text");
                if (k.dir === "desc") c = -c;
                if (c !== 0) return c;
            }
            return 0;
        };
    }

    function compareVals(a, b, type) {
        // Empty / null sorts last, regardless of direction (consistent w/ Excel).
        const aEmpty = (a === null || a === undefined || a === "");
        const bEmpty = (b === null || b === undefined || b === "");
        if (aEmpty && bEmpty) return 0;
        if (aEmpty) return 1;
        if (bEmpty) return -1;
        if (type === "money" || type === "int" || type === "percent") {
            const na = Number(a), nb = Number(b);
            if (!isNaN(na) && !isNaN(nb)) return na - nb;
        }
        if (type === "date") {
            const da = Date.parse(a), db = Date.parse(b);
            if (!isNaN(da) && !isNaN(db)) return da - db;
        }
        const sa = String(a).toLowerCase();
        const sb = String(b).toLowerCase();
        if (sa < sb) return -1;
        if (sa > sb) return 1;
        return 0;
    }

    /** Walk pre-sorted rows. Whenever any of the group-level keys
     *  changes (most-significant first), close out the corresponding
     *  level by emitting a totals row plus a spacer row. Each level
     *  tracks its own startIdx; when an outer level breaks, every
     *  inner level's startIdx also resets to the outer break point.
     *
     *  Totals rows are emitted INNER -> OUTER (most-specific first)
     *  so the visual order matches Excel's pivot-style subtotal layout. */
    function injectGroupTotals(t, rows) {
        if (!rows.length) return rows;
        const levels = t.groupLevels.slice();
        const numericFields = t.columnsMeta
            .filter(function (c) { return c.type === "money" || c.type === "int"; })
            .map(function (c) { return c.field; });

        // Per-level: index of the first row of this level's current run.
        const startIdx = levels.map(function () { return 0; });
        const out = [];

        function emitTotals(level, fromIdx, toIdx, isGrand) {
            const slice = rows.slice(fromIdx, toIdx);
            if (!slice.length) return;
            const total = {};
            const firstText = (t.columnsMeta.find(function (c) { return c.type !== "money" && c.type !== "int" && c.type !== "percent"; }) || t.columnsMeta[0]);
            t.columnsMeta.forEach(function (col) {
                if (numericFields.indexOf(col.field) >= 0) {
                    total[col.field] = slice.reduce(function (s, r) {
                        const v = Number(r[col.field]);
                        return s + (isNaN(v) ? 0 : v);
                    }, 0);
                } else {
                    total[col.field] = "";
                }
            });
            if (isGrand) {
                total[firstText.field] = "GRAND TOTAL";
            } else {
                const gField = levels[level];
                const gVal = slice[0][gField];
                total[firstText.field] = (gVal === null || gVal === undefined || gVal === "")
                    ? "TOTALS"
                    : String(gVal) + " (Total)";
            }
            total._is_total  = true;
            total._is_spacer = false;
            if (isGrand) total._is_grand = true;
            out.push(total);
            const spacer = {};
            t.columnsMeta.forEach(function (c) { spacer[c.field] = ""; });
            spacer._is_spacer = true;
            out.push(spacer);
        }

        for (let i = 0; i < rows.length; i++) {
            const row = rows[i];
            row._is_total = false;
            row._is_spacer = false;
            if (i > 0) {
                // Find the outer-most level that broke. Inner levels
                // implicitly break when an outer level breaks (we
                // never have to check them separately).
                let brokeAt = -1;
                for (let lvl = 0; lvl < levels.length; lvl++) {
                    if (rows[i][levels[lvl]] !== rows[i - 1][levels[lvl]]) {
                        brokeAt = lvl;
                        break;
                    }
                }
                if (brokeAt >= 0) {
                    // Emit totals INNER -> OUTER for every level that broke.
                    for (let close = levels.length - 1; close >= brokeAt; close--) {
                        emitTotals(close, startIdx[close], i, false);
                    }
                    // Reset inner levels' startIdx to the new break point
                    // so their next totals only cover from here on.
                    for (let close = levels.length - 1; close >= brokeAt; close--) {
                        startIdx[close] = i;
                    }
                }
            }
            out.push(row);
        }

        // Close every open group at the end of data, INNER -> OUTER.
        for (let close = levels.length - 1; close >= 0; close--) {
            emitTotals(close, startIdx[close], rows.length, false);
        }
        emitTotals(0, 0, rows.length, true);

        return out;
    }

    function applySortGroupChange(key) {
        const t = state.tabs[key];
        if (!t || !t.grid) return;
        try {
            const filters = activeHeaderFilters(t);
            const filteredRaw = applyHeaderFiltersToRaw(t, filters);
            t._hasActiveFilters = filters.length > 0;
            t._filteredRawCount = filteredRaw.length;
            t.grid.setData(computeDisplayRows(t, function (r) { return filteredRaw.indexOf(r) >= 0; }));
        } catch (_) {}
        renderSortGroupBar();
        updateChangedState();
        updateExportRowCount();
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
                sorter:       columnSorter(meta.type),
                titleFormatter: function () {
                    const wrap = document.createElement("div");
                    wrap.className = "col-header-inner";
                    const lbl = document.createElement("span");
                    lbl.className = "col-header-label";
                    lbl.textContent = meta.label;
                    const btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "col-header-filter-btn";
                    btn.title = "Filter this column";
                    btn.setAttribute("aria-label", "Filter " + meta.label);
                    btn.dataset.field = meta.field;
                    btn.innerHTML = '<i data-feather="filter" width="14" height="14"></i>';
                    const tab = state.tabs[key];
                    const cur = tab && tab.columnFilters && tab.columnFilters[meta.field];
                    var filOn = false;
                    if (cur != null && cur !== "") {
                        if (typeof cur === "string") filOn = true;
                        else if (typeof cur === "object" && cur.op && !isEmptyFilter(cur)) filOn = true;
                    }
                    btn.classList.toggle("has-active-filter", filOn);

                    btn.addEventListener("click", function (ev) {
                        ev.preventDefault();
                        ev.stopPropagation();
                        openColHeaderFilterPopover(key, meta.field, btn);
                    });
                    btn.addEventListener("mousedown", function (ev) {
                        ev.stopPropagation();
                    });

                    wrap.appendChild(lbl);
                    wrap.appendChild(btn);
                    return wrap;
                },
            };
        }).filter(Boolean);
    }

    // ---------- Column filter editors (per-header popovers) ----------
    //
    // Each column filter is an object stored on `tab.columnFilters[field]`:
    //   { op: <operator>, v: <string|number|[lo,hi]|string[]> }.
    // The grid pipeline applies these in `activeHeaderFilters()` before
    // sort/group injection. Pass `success = null` so users commit with Apply.
    //
    // Operators per column type:
    //   text:    contains, equals, starts, ends, in (multi), empty, notEmpty
    //   number:  eq, ne, gt, ge, lt, le, between, empty, notEmpty
    //   date:    on, before, after, between, empty, notEmpty
    //
    // A tiny operator-picker pill on the left swaps the value editor on
    // the right (one input vs. two-input range vs. comma-list vs. nothing).

    const TEXT_OPS   = [
        { op: "contains", label: "contains",  short: "⌕"  },
        { op: "equals",   label: "equals",    short: "="  },
        { op: "starts",   label: "starts with", short: "a…" },
        { op: "ends",     label: "ends with", short: "…z" },
        { op: "in",       label: "is one of (comma-separated)", short: "{ }" },
        { op: "empty",    label: "is empty",     short: "∅"  },
        { op: "notEmpty", label: "is not empty", short: "!∅" },
    ];
    const NUM_OPS    = [
        { op: "eq",       label: "equals",        short: "="  },
        { op: "ne",       label: "not equal",     short: "≠"  },
        { op: "gt",       label: "greater than",  short: ">"  },
        { op: "ge",       label: "greater or eq", short: "≥"  },
        { op: "lt",       label: "less than",     short: "<"  },
        { op: "le",       label: "less or eq",    short: "≤"  },
        { op: "between",  label: "between",       short: "↔"  },
        { op: "empty",    label: "is empty",      short: "∅"  },
        { op: "notEmpty", label: "is not empty",  short: "!∅" },
    ];
    const DATE_OPS   = [
        { op: "on",       label: "on",            short: "="  },
        { op: "before",   label: "before",        short: "<"  },
        { op: "after",    label: "after",         short: ">"  },
        { op: "between",  label: "between",       short: "↔"  },
        { op: "empty",    label: "is empty",      short: "∅"  },
        { op: "notEmpty", label: "is not empty",  short: "!∅" },
    ];

    function operatorsFor(type) {
        if (type === "money" || type === "int" || type === "percent") return NUM_OPS;
        if (type === "date") return DATE_OPS;
        return TEXT_OPS;
    }

    /** Layout: [ op-button ][ value input(s) ]. State on `wrap.__hfState`. */
    function buildColumnFilterEditor(meta, success, initialValue) {
        const ops = operatorsFor(meta.type);
        const wrap = document.createElement("div");
        wrap.className = "hf-wrap";

        const opBtn = document.createElement("button");
        opBtn.type = "button";
        opBtn.className = "hf-op";
        opBtn.tabIndex = 0;
        wrap.appendChild(opBtn);

        const valHost = document.createElement("span");
        valHost.className = "hf-val";
        wrap.appendChild(valHost);

        const filtState = wrap.__hfState = { op: ops[0].op, v: emptyValueFor(ops[0].op) };

        if (initialValue != null && initialValue !== "") {
            if (typeof initialValue === "object" && initialValue.op != null) {
                const known = ops.some(function (o) { return o.op === initialValue.op; });
                if (known) {
                    filtState.op = initialValue.op;
                    filtState.v = (initialValue.v !== undefined && initialValue.v !== null)
                        ? initialValue.v
                        : emptyValueFor(initialValue.op);
                    if (filtState.op === "between" && !Array.isArray(filtState.v)) {
                        filtState.v = ["", ""];
                    }
                }
            } else if (typeof initialValue === "string") {
                filtState.op = "contains";
                filtState.v = initialValue;
            }
        }

        function setOp(newOp) {
            filtState.op = newOp;
            filtState.v = emptyValueFor(newOp);
            renderOpBtn();
            renderValEditor();
            commit();
        }

        function renderOpBtn() {
            const def = ops.find(function (o) { return o.op === filtState.op; }) || ops[0];
            opBtn.textContent = def.short;
            opBtn.title = def.label;
        }

        function renderValEditor() {
            valHost.innerHTML = "";
            if (filtState.op === "empty" || filtState.op === "notEmpty") {
                return;
            }
            if (filtState.op === "between") {
                const lo = mkInput(meta.type === "date" ? "date" : "number", "min");
                const sep = document.createElement("span");
                sep.className = "hf-sep";
                sep.textContent = "–";
                const hi = mkInput(meta.type === "date" ? "date" : "number", "max");
                lo.value = (Array.isArray(filtState.v) && filtState.v[0] != null) ? filtState.v[0] : "";
                hi.value = (Array.isArray(filtState.v) && filtState.v[1] != null) ? filtState.v[1] : "";
                lo.addEventListener("input", function () {
                    filtState.v = [lo.value, hi.value];
                    commit();
                });
                hi.addEventListener("input", function () {
                    filtState.v = [lo.value, hi.value];
                    commit();
                });
                valHost.appendChild(lo);
                valHost.appendChild(sep);
                valHost.appendChild(hi);
                return;
            }
            const inputType = (meta.type === "date") ? "date"
                : (meta.type === "money" || meta.type === "int" || meta.type === "percent") ? "number"
                : "text";
            const inp = mkInput(inputType, filtState.op === "in" ? "a, b, c…" : "");
            inp.value = filtState.v != null ? String(filtState.v) : "";
            inp.addEventListener("input", function () {
                filtState.v = inp.value;
                commit();
            });
            valHost.appendChild(inp);
        }

        function mkInput(type, placeholder) {
            const el = document.createElement("input");
            el.type = type;
            el.className = "hf-input";
            if (placeholder) el.placeholder = placeholder;
            el.addEventListener("click", function (e) { e.stopPropagation(); });
            el.addEventListener("mousedown", function (e) { e.stopPropagation(); });
            return el;
        }

        function commit() {
            if (!success || typeof success !== "function") return;
            if (isEmptyFilter(filtState)) {
                success("");
                return;
            }
            success({ op: filtState.op, v: filtState.v });
        }

        opBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            openOpMenu(opBtn, ops, filtState.op, setOp);
        });
        opBtn.addEventListener("mousedown", function (e) { e.stopPropagation(); });

        renderOpBtn();
        renderValEditor();
        return wrap;
    }

    function emptyValueFor(op) {
        if (op === "between") return ["", ""];
        if (op === "in")      return "";
        if (op === "empty" || op === "notEmpty") return null;
        return "";
    }

    function isEmptyFilter(s) {
        if (s.op === "empty" || s.op === "notEmpty") return false;  // op IS the filter
        if (Array.isArray(s.v)) {
            return s.v.every(function (x) { return x === "" || x == null; });
        }
        return s.v === "" || s.v == null;
    }

    /** Floating popover with the operator list. Positioned under the
     *  operator button. Closes on outside-click or selection. */
    function openOpMenu(anchor, ops, currentOp, onPick) {
        // Close any existing menu first.
        document.querySelectorAll(".hf-menu").forEach(function (m) { m.remove(); });

        const rect = anchor.getBoundingClientRect();
        const menu = document.createElement("div");
        menu.className = "hf-menu";
        menu.style.position = "fixed";
        menu.style.top  = (rect.bottom + 2) + "px";
        menu.style.left = rect.left + "px";
        menu.style.zIndex = "1000";

        ops.forEach(function (o) {
            const item = document.createElement("button");
            item.type = "button";
            item.className = "hf-menu-item" + (o.op === currentOp ? " active" : "");
            item.innerHTML = '<span class="hf-menu-short">' + escHtml(o.short) + '</span>'
                           + '<span class="hf-menu-label">' + escHtml(o.label) + '</span>';
            item.addEventListener("click", function (e) {
                e.stopPropagation();
                menu.remove();
                document.removeEventListener("click", onDocClick, true);
                onPick(o.op);
            });
            menu.appendChild(item);
        });

        function onDocClick(ev) {
            if (!menu.contains(ev.target) && ev.target !== anchor) {
                menu.remove();
                document.removeEventListener("click", onDocClick, true);
            }
        }
        setTimeout(function () {
            document.addEventListener("click", onDocClick, true);
        }, 0);

        document.body.appendChild(menu);
    }

    function colHeaderFilterPopoverIsOpen() {
        return !!(colFilterPopover && colFilterPopover.parentNode);
    }

    function closeColHeaderFilterPopover() {
        if (colFilterOutsideHandler) {
            document.removeEventListener("click", colFilterOutsideHandler, true);
            colFilterOutsideHandler = null;
        }
        if (colFilterKeyHandler) {
            document.removeEventListener("keydown", colFilterKeyHandler, true);
            colFilterKeyHandler = null;
        }
        colFilterPopoverAnchor = null;
        if (colFilterPopover && colFilterPopover.parentNode) {
            colFilterPopover.parentNode.removeChild(colFilterPopover);
        }
        colFilterPopover = null;
    }

    function syncColHeaderFilterButtons(tabKey) {
        const t = state.tabs[tabKey];
        if (!t || !t.grid) return;
        const active = {};
        activeHeaderFilters(t).forEach(function (f) {
            active[f.field] = true;
        });
        try {
            t.grid.getColumns().forEach(function (col) {
                const cell = col.getElement();
                if (!cell) return;
                const btn = cell.querySelector(".col-header-filter-btn");
                if (!btn) return;
                btn.classList.toggle("has-active-filter", !!active[col.getField()]);
            });
        } catch (_) {}
    }

    function positionColFilterPopover(panel, anchorEl) {
        const rect = anchorEl.getBoundingClientRect();
        const margin = 8;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const pr = panel.getBoundingClientRect();
        const pw = pr.width;
        const ph = pr.height;
        let left = rect.left;
        let top = rect.bottom + 6;
        if (left + pw > vw - margin) left = Math.max(margin, vw - pw - margin);
        if (top + ph > vh - margin) top = Math.max(margin, rect.top - ph - 6);
        if (left < margin) left = margin;
        panel.style.left = left + "px";
        panel.style.top = top + "px";
    }

    function openColHeaderFilterPopover(tabKey, field, anchorEl) {
        const tab = state.tabs[tabKey];
        if (!tab || !field || !anchorEl) return;
        const meta = tab.columnsMeta.find(function (c) { return c.field === field; });
        if (!meta) return;

        if (colFilterPopover &&
            colFilterPopover.dataset.tabKey === tabKey &&
            colFilterPopover.dataset.field === field) {
            closeColHeaderFilterPopover();
            return;
        }
        closeColHeaderFilterPopover();

        colFilterPopoverAnchor = anchorEl;

        const panel = document.createElement("div");
        panel.className = "col-filter-popover";
        panel.dataset.tabKey = tabKey;
        panel.dataset.field = field;
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-label", "Filter " + meta.label);

        const head = document.createElement("div");
        head.className = "col-filter-popover-head";
        const ht = document.createElement("span");
        ht.className = "col-filter-popover-title";
        ht.textContent = meta.label;
        const hx = document.createElement("button");
        hx.type = "button";
        hx.className = "col-filter-popover-x";
        hx.setAttribute("aria-label", "Close");
        hx.textContent = "×";
        hx.addEventListener("click", function (e) {
            e.preventDefault();
            closeColHeaderFilterPopover();
        });
        head.appendChild(ht);
        head.appendChild(hx);

        const bodyEl = document.createElement("div");
        bodyEl.className = "col-filter-popover-body";
        const initial = tab.columnFilters && tab.columnFilters[field];
        bodyEl.appendChild(buildColumnFilterEditor(meta, null, initial));

        const foot = document.createElement("div");
        foot.className = "col-filter-popover-foot";

        function applyOneColumnFilter() {
            ensureColumnFilters(tab);
            const wrap = bodyEl.querySelector(".hf-wrap");
            const filt = wrap && wrap.__hfState;
            if (!filt) return;
            if (isEmptyFilter(filt)) delete tab.columnFilters[field];
            else {
                tab.columnFilters[field] = {
                    op: filt.op,
                    v: Array.isArray(filt.v) ? filt.v.slice() : filt.v,
                };
            }
            rebuildGridDataFromFilters(tabKey);
            closeColHeaderFilterPopover();
            if (tabKey === state.activeTab) {
                renderSortGroupBar();
                updateExportRowCount();
            }
            updateChangedState();
        }

        const clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "btn btn-outline col-filter-popover-btn";
        clearBtn.textContent = "Clear";
        clearBtn.addEventListener("click", function (e) {
            e.preventDefault();
            ensureColumnFilters(tab);
            delete tab.columnFilters[field];
            rebuildGridDataFromFilters(tabKey);
            closeColHeaderFilterPopover();
            if (tabKey === state.activeTab) {
                renderSortGroupBar();
                updateExportRowCount();
            }
            updateChangedState();
        });

        const applyBtn = document.createElement("button");
        applyBtn.type = "button";
        applyBtn.className = "btn btn-primary col-filter-popover-btn";
        applyBtn.textContent = "Apply";
        applyBtn.addEventListener("click", function (e) {
            e.preventDefault();
            applyOneColumnFilter();
        });

        foot.appendChild(clearBtn);
        foot.appendChild(applyBtn);
        panel.appendChild(head);
        panel.appendChild(bodyEl);
        panel.appendChild(foot);

        panel.style.position = "fixed";
        panel.style.zIndex = "480";
        document.body.appendChild(panel);
        colFilterPopover = panel;

        setTimeout(function () {
            positionColFilterPopover(panel, anchorEl);
        }, 0);
        requestAnimationFrame(function () {
            positionColFilterPopover(panel, anchorEl);
        });

        colFilterOutsideHandler = function (ev) {
            if (!colFilterPopover) return;
            if (colFilterPopover.contains(ev.target)) return;
            if (colFilterPopoverAnchor && colFilterPopoverAnchor.contains(ev.target)) return;
            closeColHeaderFilterPopover();
        };
        setTimeout(function () {
            document.addEventListener("click", colFilterOutsideHandler, true);
        }, 0);

        colFilterKeyHandler = function (ev) {
            if (ev.key !== "Escape") return;
            if (!colFilterPopover) return;
            ev.preventDefault();
            ev.stopPropagation();
            closeColHeaderFilterPopover();
        };
        document.addEventListener("keydown", colFilterKeyHandler, true);

        if (typeof feather !== "undefined") feather.replace();

        applyBtn.focus();
    }

    /** Decide whether a row passes the per-column filter. */
    function applyHeaderFilter(meta, filterVal, cellVal, rowData) {
        if (filterVal === "" || filterVal == null) return true;

        // Backwards compat: older saved layouts stored a bare string —
        // treat it as substring (contains).
        if (typeof filterVal === "string") {
            return matchText("contains", filterVal, cellVal);
        }

        const op = filterVal.op;
        const v  = filterVal.v;

        if (op === "empty")    return cellVal == null || cellVal === "";
        if (op === "notEmpty") return !(cellVal == null || cellVal === "");

        const t = meta.type;
        if (t === "money" || t === "int" || t === "percent") {
            return matchNumber(op, v, cellVal);
        }
        if (t === "date") {
            return matchDate(op, v, cellVal);
        }
        return matchText(op, v, cellVal);
    }

    function matchText(op, v, cellVal) {
        const cell = (cellVal == null) ? "" : String(cellVal);
        const cellLc = cell.toLowerCase();
        if (op === "in") {
            const needles = String(v || "").split(",")
                .map(function (s) { return s.trim().toLowerCase(); })
                .filter(Boolean);
            if (!needles.length) return true;
            return needles.indexOf(cellLc) >= 0;
        }
        const needle = String(v || "").toLowerCase();
        if (!needle) return true;
        if (op === "equals")   return cellLc === needle;
        if (op === "starts")   return cellLc.indexOf(needle) === 0;
        if (op === "ends")     return cellLc.lastIndexOf(needle) === cellLc.length - needle.length && cellLc.length >= needle.length;
        return cellLc.indexOf(needle) >= 0;  // contains (default)
    }

    function matchNumber(op, v, cellVal) {
        const cell = (cellVal === "" || cellVal == null) ? null : Number(cellVal);
        if (op === "between") {
            const lo = (Array.isArray(v) && v[0] !== "" && v[0] != null) ? Number(v[0]) : null;
            const hi = (Array.isArray(v) && v[1] !== "" && v[1] != null) ? Number(v[1]) : null;
            if (lo == null && hi == null) return true;
            if (cell == null || isNaN(cell)) return false;
            if (lo != null && cell < lo) return false;
            if (hi != null && cell > hi) return false;
            return true;
        }
        const n = Number(v);
        if (v === "" || v == null || isNaN(n)) return true;
        if (cell == null || isNaN(cell)) return false;
        switch (op) {
            case "eq": return cell === n;
            case "ne": return cell !== n;
            case "gt": return cell >  n;
            case "ge": return cell >= n;
            case "lt": return cell <  n;
            case "le": return cell <= n;
        }
        return true;
    }

    function matchDate(op, v, cellVal) {
        const cell = parseDateMs(cellVal);
        if (op === "between") {
            const lo = (Array.isArray(v) && v[0]) ? parseDateMs(v[0]) : null;
            const hi = (Array.isArray(v) && v[1]) ? parseDateMs(v[1]) : null;
            if (lo == null && hi == null) return true;
            if (cell == null) return false;
            if (lo != null && cell < lo) return false;
            // "between" is inclusive; bump hi to end-of-day so the
            // user picking the same date for both bounds matches that day.
            if (hi != null && cell > hi + (24 * 3600 * 1000 - 1)) return false;
            return true;
        }
        if (!v) return true;
        const target = parseDateMs(v);
        if (target == null) return true;
        if (cell == null) return false;
        if (op === "on")     return cell >= target && cell < target + 24 * 3600 * 1000;
        if (op === "before") return cell <  target;
        if (op === "after")  return cell >= target + 24 * 3600 * 1000;
        return true;
    }

    function parseDateMs(v) {
        if (v == null || v === "") return null;
        if (v instanceof Date) return v.getTime();
        const s = String(v);
        // YYYY-MM-DD or YYYY-MM-DDTHH:...
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
        if (m) {
            return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])).getTime();
        }
        const t = Date.parse(s);
        return isNaN(t) ? null : t;
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
        // Tabulator renders the label string directly into the menu DOM but
        // doesn't trigger feather.replace() afterward, so <i data-feather=...>
        // never becomes an SVG. Inline an SVG instead so the icon shows up
        // on first menu open without depending on a global rescan.
        var eyeOffSvg =
            "<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' " +
            "viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' " +
            "stroke-linecap='round' stroke-linejoin='round' " +
            "style='vertical-align:-2px;margin-right:6px;'>" +
            "<path d='M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 " +
            "18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 " +
            "18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24'/>" +
            "<line x1='1' y1='1' x2='23' y2='23'/></svg>";
        return [
            {
                label: eyeOffSvg + "Hide this column",
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
        closeColHeaderFilterPopover();
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
        const t = state.tabs[key];
        if (t && t.isDuplicate) {
            deleteTabPermanently(key);
            return;
        }
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

    function deleteTabPermanently(key) {
        closeColHeaderFilterPopover();
        const t = state.tabs[key];
        if (!t) return;
        if (t.grid) {
            try { t.grid.destroy(); } catch (_) {}
        }
        delete state.tabs[key];
        state.hiddenTabs.delete(key);
        state.tabOrder = state.tabOrder.filter(function (k) { return k !== key; });
        const pane = els.gridRoot.querySelector('.grid-pane[data-key="' + cssEsc(key) + '"]');
        if (pane && pane.parentNode) pane.parentNode.removeChild(pane);
        buildTabStrip();
        if (state.activeTab === key) {
            const next = state.tabOrder.find(function (k) { return !state.hiddenTabs.has(k); });
            if (next) activateTab(next);
            else {
                state.activeTab = null;
                els.gridRoot.querySelectorAll(".grid-pane").forEach(function (p) { p.classList.remove("active"); });
                els.emptyState.hidden = false;
                els.emptyStateMsg.textContent = "No tabs are available.";
            }
        }
        refreshHiddenUi();
        updateChangedState();
        updateExportRowCount();
    }

    function duplicateTabWithPrompt(key) {
        const src = state.tabs[key];
        if (!src) return;
        const raw = window.prompt("Duplicate tab name:", src.name + " (Copy)");
        if (raw == null) return;
        const name = String(raw || "").trim();
        if (!name) {
            alert("Tab name is required.");
            return;
        }
        const dupKey = makeDuplicateTabKey(key);
        state.tabs[dupKey] = cloneTabState(src, name, key);
        state.tabOrder.push(dupKey);
        const div = document.createElement("div");
        div.className = "grid-pane";
        div.dataset.key = dupKey;
        const inner = document.createElement("div");
        inner.className = "grid-container";
        div.appendChild(inner);
        els.gridRoot.appendChild(div);
        state.tabs[dupKey].container = inner;
        buildTabStrip();
        activateTab(dupKey);
        refreshHiddenUi();
        updateChangedState();
    }

    function makeDuplicateTabKey(sourceKey) {
        let n = 1;
        while (true) {
            const k = String(sourceKey) + "__dup" + n;
            if (!state.tabs[k]) return k;
            n += 1;
        }
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

        updateChangedState();
        updateExportRowCount();
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
            if (e.key !== "Escape") return;
            if (colHeaderFilterPopoverIsOpen()) return;
            closeDrawer();
        });
    }

    // ---------- Sort & Group toolbar ------------------------------------
    function renderSortGroupBar() {
        const bar = els.sortGroupBar;
        if (!bar) return;
        const key = state.activeTab;
        const t = key ? state.tabs[key] : null;
        if (!t) {
            bar.hidden = true;
            return;
        }
        bar.hidden = false;
        renderChips(els.sortChips, t, /*kind*/ "sort");
        renderChips(els.groupChips, t, /*kind*/ "group");
        populateAddSelect(els.addSortSelect,  t, /*kind*/ "sort");
        populateAddSelect(els.addGroupSelect, t, /*kind*/ "group");
    }

    function renderChips(ul, t, kind) {
        if (!ul) return;
        ul.innerHTML = "";
        const list = (kind === "sort") ? t.sortLevels : t.groupLevels.map(function (f) { return { field: f }; });
        list.forEach(function (item, idx) {
            const meta = t.columnsMeta.find(function (c) { return c.field === item.field; });
            const label = meta ? meta.label : item.field;

            const li = document.createElement("li");
            li.className = "sortgroup-chip";
            li.draggable = true;
            li.dataset.idx = String(idx);
            li.dataset.kind = kind;

            const rank = document.createElement("span");
            rank.className = "sortgroup-chip-rank";
            rank.textContent = String(idx + 1);
            li.appendChild(rank);

            const name = document.createElement("span");
            name.textContent = label;
            li.appendChild(name);

            if (kind === "sort") {
                const dirBtn = document.createElement("button");
                dirBtn.type = "button";
                dirBtn.className = "sortgroup-chip-dir";
                dirBtn.title = "Toggle direction";
                dirBtn.textContent = (item.dir === "desc") ? "↓" : "↑";
                dirBtn.addEventListener("click", function (e) {
                    e.stopPropagation();
                    item.dir = (item.dir === "asc") ? "desc" : "asc";
                    applySortGroupChange(state.activeTab);
                });
                li.appendChild(dirBtn);
            }

            const x = document.createElement("button");
            x.type = "button";
            x.className = "sortgroup-chip-x";
            x.title = (kind === "sort") ? "Remove sort level" : "Remove group level";
            x.textContent = "×";
            x.addEventListener("click", function (e) {
                e.stopPropagation();
                if (kind === "sort") {
                    t.sortLevels.splice(idx, 1);
                } else {
                    t.groupLevels.splice(idx, 1);
                }
                applySortGroupChange(state.activeTab);
            });
            li.appendChild(x);

            // Drag-to-reorder
            li.addEventListener("dragstart", function (e) {
                e.dataTransfer.setData("text/plain", String(idx) + "|" + kind);
                e.dataTransfer.effectAllowed = "move";
            });
            li.addEventListener("dragover", function (e) {
                e.preventDefault();
                li.classList.add("drag-over");
            });
            li.addEventListener("dragleave", function () { li.classList.remove("drag-over"); });
            li.addEventListener("drop", function (e) {
                e.preventDefault();
                li.classList.remove("drag-over");
                const data = String(e.dataTransfer.getData("text/plain") || "");
                const parts = data.split("|");
                if (parts.length !== 2 || parts[1] !== kind) return;
                const fromIdx = parseInt(parts[0], 10);
                const toIdx = idx;
                if (isNaN(fromIdx) || fromIdx === toIdx) return;
                const arr = (kind === "sort") ? t.sortLevels : t.groupLevels;
                const [moved] = arr.splice(fromIdx, 1);
                arr.splice(toIdx, 0, moved);
                applySortGroupChange(state.activeTab);
            });

            ul.appendChild(li);
        });
    }

    function populateAddSelect(sel, t, kind) {
        if (!sel) return;
        const used = new Set(
            kind === "sort"
                ? t.sortLevels.map(function (s) { return s.field; })
                : t.groupLevels
        );
        sel.innerHTML = "";
        const ph = document.createElement("option");
        ph.value = "";
        ph.textContent = (kind === "sort") ? "+ Add sort level…" : "+ Add group level…";
        sel.appendChild(ph);
        sel.disabled = false;
        sel.parentElement.style.display = "";
        t.columnsMeta.forEach(function (c) {
            if (used.has(c.field)) return;
            // Don't offer numeric columns as group keys (rarely useful;
            // sorting on them is fine).
            if (kind === "group" && (c.type === "money" || c.type === "int" || c.type === "percent")) return;
            const opt = document.createElement("option");
            opt.value = c.field;
            opt.textContent = c.label;
            sel.appendChild(opt);
        });
    }

    function wireSortGroupBar() {
        if (els.addSortSelect) {
            els.addSortSelect.addEventListener("change", function () {
                const f = els.addSortSelect.value;
                if (!f) return;
                const t = state.tabs[state.activeTab];
                if (!t) return;
                const meta = t.columnsMeta.find(function (c) { return c.field === f; });
                t.sortLevels.push({ field: f, dir: defaultDirFor(meta ? meta.type : "text") });
                els.addSortSelect.value = "";
                applySortGroupChange(state.activeTab);
            });
        }
        if (els.addGroupSelect) {
            els.addGroupSelect.addEventListener("change", function () {
                const f = els.addGroupSelect.value;
                if (!f) return;
                const t = state.tabs[state.activeTab];
                if (!t) return;
                t.groupLevels.push(f);
                els.addGroupSelect.value = "";
                applySortGroupChange(state.activeTab);
            });
        }
    }

    // ---------- Action buttons ------------------------------------------
    function wireActionButtons() {
        if (els.refreshBtn) els.refreshBtn.addEventListener("click", refreshData);
        if (els.resetBtn)   els.resetBtn.addEventListener("click", resetView);
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
                sort_levels:   (t.sortLevels || []).map(function (s) { return { field: s.field, dir: s.dir || "asc" }; }),
                group_levels:  (t.groupLevels || []).slice(),
                filters:       filtersSnapshotForPersist(t),
                duplicate_of:  t.isDuplicate ? (t.sourceTabKey || null) : null,
                tab_name:      t.name || "",
            };
        });
        return out;
    }

    // ---------- Refresh / Reset ----------------------------------------
    async function refreshData() {
        if (!els.refreshBtn) return;
        els.refreshBtn.disabled = true;
        const old = els.refreshBtn.innerHTML;
        els.refreshBtn.textContent = "Refreshing…";
        try {
            await runReport({ preserveLayout: true });
        } catch (err) {
            alert("Refresh failed: " + (err.message || err));
        } finally {
            els.refreshBtn.innerHTML = old;
            els.refreshBtn.disabled = false;
            if (typeof feather !== "undefined") feather.replace();
        }
    }

    function resetView() {
        if (!state.defaultLayout) return;
        const def = state.defaultLayout;
        state.tabOrder = state.tabOrder.filter(function (k) { return !!(def.tabs && def.tabs[k]); });
        Object.keys(state.tabs).forEach(function (k) {
            if (def.tabs && def.tabs[k]) return;
            const t = state.tabs[k];
            if (t && t.grid) {
                try { t.grid.destroy(); } catch (_) {}
            }
            delete state.tabs[k];
        });

        // Restore tab visibility + per-tab column hides + column order.
        state.hiddenTabs = new Set(def.hiddenTabs.filter(function (k) { return !!state.tabs[k]; }));

        state.tabOrder.forEach(function (key) {
            const t = state.tabs[key];
            const saved = (def.tabs && def.tabs[key]) || {};
            if (!t) return;

            // Hidden fields
            t.hiddenFields = new Set((saved.hidden_fields || []).filter(function (f) {
                return t.columnsMeta.some(function (c) { return c.field === f; });
            }));
            // Field order
            if (Array.isArray(saved.field_order) && saved.field_order.length) {
                const valid = new Set(t.columnsMeta.map(function (c) { return c.field; }));
                const ordered = [];
                const seen = new Set();
                saved.field_order.forEach(function (f) {
                    if (valid.has(f) && !seen.has(f)) { ordered.push(f); seen.add(f); }
                });
                t.columnsMeta.forEach(function (c) {
                    if (!seen.has(c.field)) ordered.push(c.field);
                });
                t.fieldOrder = ordered;
            }
            // Restore sort + group levels
            t.sortLevels  = (saved.sort_levels || []).map(function (s) { return { field: s.field, dir: s.dir }; });
            t.groupLevels = (saved.group_levels || []).slice();
            resetColumnFiltersFromSaved(t, saved.filters || []);

            // Tear down the Tabulator instance so column order and
            // restored filters take effect on the next build.
            if (t.grid) {
                try { t.grid.destroy(); } catch (_) {}
                t.grid = null;
            }
        });

        buildTabStrip();
        const target = (state.tabs[def.activeTab] && !state.hiddenTabs.has(def.activeTab))
            ? def.activeTab
            : (state.tabOrder.find(function (k) { return !state.hiddenTabs.has(k); }) || state.tabOrder[0]);
        activateTab(target);
        refreshHiddenUi();
    }

    /** Compares current layout against the default snapshot and toggles
     *  the "Reset to default view" button + updates row-count chip. */
    function updateChangedState() {
        if (!els.resetBtn) return;
        const changed = state.defaultLayout ? layoutHasChanged() : false;
        els.resetBtn.hidden = !changed;
    }

    function layoutHasChanged() {
        const def = state.defaultLayout;
        if (!def) return false;

        // Tab visibility
        const curHidden = Array.from(state.hiddenTabs).sort().join("|");
        const defHidden = (def.hiddenTabs || []).slice().sort().join("|");
        if (curHidden !== defHidden) return true;

        // Per-tab column hides + order + active sorters/filters
        for (let i = 0; i < state.tabOrder.length; i++) {
            const key = state.tabOrder[i];
            const t = state.tabs[key];
            const saved = (def.tabs && def.tabs[key]) || {};
            if (!t) continue;

            const ch = Array.from(t.hiddenFields).sort().join("|");
            const dh = (saved.hidden_fields || []).slice().sort().join("|");
            if (ch !== dh) return true;

            const co = (t.fieldOrder || []).join("|");
            const dor = (saved.field_order || []).join("|");
            if (co && dor && co !== dor) return true;

            // Sort levels
            const cs = (t.sortLevels || []).map(function (s) { return s.field + ":" + s.dir; }).join("|");
            const ds = (saved.sort_levels || []).map(function (s) { return s.field + ":" + s.dir; }).join("|");
            if (cs !== ds) return true;
            // Group levels
            const cg = (t.groupLevels || []).join("|");
            const dg = (saved.group_levels || []).join("|");
            if (cg !== dg) return true;

            const curFil = serializeFiltersForCompare(activeHeaderFilters(t));
            const defFil = serializeFiltersForCompare(saved.filters || []);
            if (curFil !== defFil) return true;
        }
        return false;
    }

    /** Update the chip next to "Export Excel" with row counts for the
     *  active tab. Filtered? Show "X of Y rows" in amber. Otherwise
     *  just "Y rows" in neutral grey. */
    function updateExportRowCount() {
        const el = els.exportRowCount;
        if (!el) return;
        const key = state.activeTab;
        const t = key ? state.tabs[key] : null;
        if (!t) {
            el.hidden = true;
            return;
        }
        // Count only "real" rows (not server-baked or group-injected
        // totals / spacer rows) so the chip stays meaningful.
        const isReal = function (r) { return r && !r._is_total && !r._is_spacer; };
        const total = (t.data || []).filter(isReal).length;
        const filters = activeHeaderFilters(t);
        const filtered = !!(t._hasActiveFilters || filters.length);
        const visible = filtered ? (t._filteredRawCount != null ? t._filteredRawCount : applyHeaderFiltersToRaw(t, filters).length) : total;
        el.hidden = false;
        el.classList.toggle("is-filtered", filtered);
        el.textContent = "Exporting " + fmtInt(visible) + " of " + fmtInt(total) + " rows";
    }

    // ---------- Excel export (client-side, WYSIWYG) ----------------------
    /**
     * Build an .xlsx in the browser using ExcelJS so the file mirrors
     * exactly what the user sees:
     *   - one sheet per VISIBLE tab (hidden tabs skipped)
     *   - column order matches what's on screen
     *   - hidden columns excluded
     *   - rows respect the current sort + header filters
     *   - cell formatting (money / int / percent / date) preserved
     */
    async function exportExcel() {
        if (typeof ExcelJS === "undefined") {
            alert("Excel library failed to load. Check your network and try again.");
            return;
        }
        els.exportBtn.disabled = true;
        const old = els.exportBtn.innerHTML;
        els.exportBtn.textContent = "Exporting…";
        try {
            const wb = new ExcelJS.Workbook();
            wb.creator = "Sales Reports v2";
            wb.created = new Date();

            const visibleTabKeys = state.tabOrder.filter(function (k) { return !state.hiddenTabs.has(k); });
            if (!visibleTabKeys.length) {
                throw new Error("No visible tabs to export.");
            }

            const usedSheetNames = new Set();
            visibleTabKeys.forEach(function (key) {
                const t = state.tabs[key];
                if (!t) return;
                addTabAsSheet(wb, t, usedSheetNames);
            });

            const buf = await wb.xlsx.writeBuffer();
            const blob = new Blob([buf], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });
            const fname = (cfg.reportName || cfg.reportKey || "report")
                .replace(/[\\/?*:[\]]/g, "_")
                .replace(/\s+/g, "_") + ".xlsx";
            triggerDownload(blob, fname);
        } catch (err) {
            alert("Export failed: " + (err.message || err));
        } finally {
            els.exportBtn.innerHTML = old;
            els.exportBtn.disabled = false;
            if (typeof feather !== "undefined") feather.replace();
        }
    }

    function addTabAsSheet(wb, tab, usedNames) {
        // Pull the rows in the user's current visible order. If the
        // grid hasn't been built (the tab was never activated), fall
        // back to the raw data.
        let rows;
        const filters = activeHeaderFilters(tab);
        const filteredRaw = applyHeaderFiltersToRaw(tab, filters);
        rows = computeDisplayRows(tab, function (r) { return filteredRaw.indexOf(r) >= 0; });

        // Build the visible columns in their on-screen order.
        const fields = tab.fieldOrder.filter(function (f) {
            return !tab.hiddenFields.has(f) && tab.columnsMeta.some(function (c) { return c.field === f; });
        });
        const visibleCols = fields.map(function (f) {
            return tab.columnsMeta.find(function (c) { return c.field === f; });
        }).filter(Boolean);

        if (!visibleCols.length) {
            // Edge case: every column on this tab is hidden. Skip the sheet.
            return;
        }

        const sheetName = uniqueSheetName(tab.name || "Sheet", usedNames);
        const ws = wb.addWorksheet(sheetName, {
            views: [{ state: "frozen", ySplit: 1 }],
        });

        ws.columns = visibleCols.map(function (col) {
            return {
                header: col.label || col.field,
                key:    col.field,
                width:  excelColumnWidth(col),
                style:  excelColumnStyle(col),
            };
        });

        // Header styling: white text on dark navy, bold.
        const headerRow = ws.getRow(1);
        headerRow.font = { bold: true, color: { argb: "FFFFFFFF" } };
        headerRow.fill = {
            type: "pattern",
            pattern: "solid",
            fgColor: { argb: "FF1F4E78" },
        };
        headerRow.alignment = { vertical: "middle", horizontal: "left" };

        // Data rows.
        rows.forEach(function (row) {
            if (row && row._is_spacer) {
                ws.addRow({});  // visually blank line, mirrors screen spacer
                return;
            }
            const out = {};
            visibleCols.forEach(function (col) {
                out[col.field] = coerceForExcel(row[col.field], col.type);
            });
            const r = ws.addRow(out);
            if (row && row._is_total) {
                const isGrand = row._is_grand
                    || JSON.stringify(row).toUpperCase().indexOf("GRAND TOTAL") >= 0;
                r.font = { bold: true, color: isGrand ? { argb: "FF000000" } : undefined };
                r.fill = {
                    type: "pattern", pattern: "solid",
                    fgColor: { argb: isGrand ? "FFFFE69C" : "FFEFEFEF" },
                };
                r.border = {
                    top:    { style: isGrand ? "double" : "thin" },
                    bottom: { style: isGrand ? "double" : "thin" },
                };
            }
        });
    }

    function uniqueSheetName(name, used) {
        // Excel sheet names: max 31 chars, none of these: : \ / ? * [ ]
        let base = String(name || "Sheet").replace(/[\\/?*:[\]]/g, "_").trim() || "Sheet";
        if (base.length > 31) base = base.slice(0, 31);
        if (!used.has(base)) { used.add(base); return base; }
        let i = 2;
        while (true) {
            const candidate = (base.slice(0, 27) + " (" + i + ")").slice(0, 31);
            if (!used.has(candidate)) { used.add(candidate); return candidate; }
            i += 1;
        }
    }

    function excelColumnWidth(col) {
        const headerLen = String(col.label || col.field || "").length;
        const typeGuess = ({
            money:   14,
            int:     10,
            percent: 10,
            date:    12,
            text:    22,
        })[col.type || "text"] || 16;
        return Math.min(42, Math.max(headerLen + 3, typeGuess));
    }

    function excelColumnStyle(col) {
        switch (col.type) {
            case "money":
                return { numFmt: '"$"#,##0.00;[Red]-"$"#,##0.00', alignment: { horizontal: "right" } };
            case "int":
                return { numFmt: "#,##0", alignment: { horizontal: "right" } };
            case "percent":
                return { numFmt: "0.00%", alignment: { horizontal: "right" } };
            case "date":
                return { numFmt: "mm/dd/yyyy", alignment: { horizontal: "left" } };
            default:
                return { alignment: { horizontal: "left" } };
        }
    }

    function coerceForExcel(value, type) {
        if (value === null || value === undefined || value === "") return null;
        if (type === "money" || type === "int" || type === "percent") {
            const n = typeof value === "number" ? value : parseFloat(value);
            if (!isFinite(n) || isNaN(n)) return null;
            return n;
        }
        if (type === "date") {
            if (value instanceof Date) return value;
            // ISO date string -> Date (local; ExcelJS treats it as a real date)
            const s = String(value).slice(0, 10);
            if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
                const parts = s.split("-");
                return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
            }
            return String(value);
        }
        return String(value);
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
                    if (j.used_cached_data) msg += "; used cached report data";
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
            const ct = r.headers.get("Content-Type") || "";
            const isJson = ct.indexOf("application/json") >= 0;
            if (!r.ok) {
                if (isJson) {
                    return r.json().then(function (j) {
                        // Server-shaped errors carry a friendly message
                        // (e.g. mirror window exceeded). Surface that
                        // verbatim so users see plain English.
                        const msg = (j && (j.message || j.error)) || ("HTTP " + r.status);
                        const err = new Error(msg);
                        err.stage = j && j.stage;
                        err.status = r.status;
                        throw err;
                    });
                }
                return r.text().then(function (t) {
                    throw new Error("HTTP " + r.status + (t ? ": " + t.slice(0, 120) : ""));
                });
            }
            return isJson ? r.json() : r.text();
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
    function cssEsc(s) {
        if (s == null) return "";
        const str = String(s);
        if (typeof CSS !== "undefined" && typeof CSS.escape === "function") return CSS.escape(str);
        return str.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    }
    function totalRowsFromPayload(payload) {
        let total = 0;
        ((payload && payload.tabs) || []).forEach(function (tab) {
            if (tab && Array.isArray(tab.rows)) total += tab.rows.length;
        });
        return total;
    }
    function totalCurrentRows() {
        let total = 0;
        state.tabOrder.forEach(function (key) {
            const t = state.tabs[key];
            if (t && Array.isArray(t.data)) total += t.data.length;
        });
        return total;
    }
    function signedInt(v) {
        const n = Number(v || 0);
        return (n > 0 ? "+" : "") + fmtInt(n) + " rows";
    }
    function relativeAge(fromIso, toIso) {
        if (!fromIso) return "";
        const from = Date.parse(fromIso);
        const to = toIso ? Date.parse(toIso) : Date.now();
        if (isNaN(from) || isNaN(to)) return "";
        let seconds = Math.max(0, Math.round((to - from) / 1000));
        if (seconds < 60) return seconds + " sec";
        const minutes = Math.round(seconds / 60);
        if (minutes < 60) return minutes + " min";
        const hours = Math.round(minutes / 60);
        if (hours < 48) return hours + " hr";
        const days = Math.round(hours / 24);
        return days + " day" + (days === 1 ? "" : "s");
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
