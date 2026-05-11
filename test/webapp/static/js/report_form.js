/* Filter page for a report.
 *
 * Reads report capabilities + API URLs from `data-*` attributes on the root
 * .report-form-page element. When the user submits, we build a query string
 * from whatever fields are visible and redirect to /report/<key>/view.
 */
(function () {
    "use strict";

    const root = document.querySelector(".report-form-page");
    if (!root) return;

    const cfg = {
        reportKey:        root.dataset.reportKey,
        reportName:       root.dataset.reportName,
        salesmenUrl:      root.dataset.salesmenUrl,
        customersUrl:     root.dataset.customersUrl,
        yearsUrl:         root.dataset.yearsUrl,
        viewUrl:          root.dataset.viewUrl,
        previewUrl:       root.dataset.previewUrl,
        lookupStatusUrl:  root.dataset.lookupStatusUrl,
        hasPeriod:        root.dataset.hasPeriod   === "true",
        hasStatus:        root.dataset.hasStatus   === "true",
        hasYear:          root.dataset.hasYear     === "true",
        hasSalesman:      root.dataset.hasSalesman === "true",
        hasCustomer:      root.dataset.hasCustomer === "true",
    };

    const $ = (id) => document.getElementById(id);
    const form = $("reportForm");

    // ---- Period buttons ------------------------------------------------
    function initPeriod() {
        if (!cfg.hasPeriod) return;
        const periodInput = $("periodInput");
        const customRange = $("customDateRange");

        root.querySelectorAll(".period-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                root.querySelectorAll(".period-btn").forEach((b) => b.classList.remove("active"));
                btn.classList.add("active");
                const p = btn.dataset.period;
                periodInput.value = p;
                customRange.hidden = p !== "custom";
                if (p === "custom") {
                    const from = $("fromDate"), to = $("toDate");
                    if (from && !from.value) {
                        const now = new Date();
                        from.value = toIso(new Date(now.getFullYear(), now.getMonth(), 1));
                        to.value   = toIso(now);
                    }
                }
            });
        });
    }

    // ---- Status buttons ------------------------------------------------
    function initStatus() {
        if (!cfg.hasStatus) return;
        const statusInput = $("statusInput");
        root.querySelectorAll(".status-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                root.querySelectorAll(".status-btn").forEach((b) => b.classList.remove("active"));
                btn.classList.add("active");
                statusInput.value = btn.dataset.status || "";
            });
        });
    }

    // ---- Year dropdown -------------------------------------------------
    async function initYear() {
        if (!cfg.hasYear) return;
        const sel = $("yearInput");
        try {
            const rows = await fetchJson(cfg.yearsUrl);
            sel.innerHTML = rows
                .map((r, i) => `<option value="${esc(r.key)}"${i === 0 ? " selected" : ""}>${esc(r.name)}</option>`)
                .join("");
        } catch {
            sel.innerHTML = '<option value="">(failed to load)</option>';
        }
    }

    // ---- Salesman + Customer dropdowns --------------------------------
    //
    // The lookup data lives behind a slow API call. We must NOT block any
    // other UI work on it (especially the live API-preview panel). So:
    //   1. Fire salesman + customer fetches in the background, ignore failures.
    //   2. Poll /lookups/status while they're loading so the user sees
    //      progress instead of silence.
    //   3. When the brother delivers the dedicated lookup SPs, this whole
    //      polling dance can collapse to a single round-trip.

    function initSalesmanShell() {
        // Just wire up the change handler; the options come from kickoffLookups().
        if (!cfg.hasSalesman) return;
        if (cfg.hasCustomer) {
            const sel = $("salesmanSelect");
            sel.addEventListener("change", () => loadCustomers());
        }
    }

    function applySalesmen(rows) {
        if (!cfg.hasSalesman) return;
        const sel = $("salesmanSelect");
        const current = sel.value;
        const opts = ['<option value="">All Salesmen</option>'].concat(
            rows.map((r) => `<option value="${esc(r.key)}">${esc(r.name)}</option>`),
        );
        sel.innerHTML = opts.join("");
        if (current) sel.value = current; // preserve user's selection
    }

    // ---- Customer multi-select ----------------------------------------
    const customerState = {
        all: [],         // [{key, name}]
        selected: new Map(),  // key -> name
        lastFetchUrl: null,
    };

    async function loadCustomers() {
        if (!cfg.hasCustomer) return;
        const list = $("customerList");

        let url = cfg.customersUrl;
        const sm = cfg.hasSalesman ? ($("salesmanSelect")?.value || "") : "";
        if (sm) url += (url.includes("?") ? "&" : "?") + "salesman=" + encodeURIComponent(sm);
        customerState.lastFetchUrl = url;

        if (list && customerState.all.length === 0) {
            list.innerHTML = '<div class="customer-picker-loading">Waiting for customer list&hellip;</div>';
        }

        try {
            const rows = await fetchJson(url);
            // Bail out if a newer fetch superseded this one.
            if (customerState.lastFetchUrl !== url) return;
            customerState.all = rows;
            // Drop selections that aren't in the new salesman's book.
            const valid = new Set(rows.map((r) => r.key));
            for (const key of [...customerState.selected.keys()]) {
                if (!valid.has(key)) customerState.selected.delete(key);
            }
            renderChips();
            renderList(rows);
        } catch (e) {
            if (list) {
                list.innerHTML = `<div class="customer-picker-empty">Could not load customers (${esc(e.message || e)}).</div>`;
            }
        }
    }

    function renderList(rows) {
        const list = $("customerList");
        if (!rows.length) {
            list.innerHTML = '<div class="customer-picker-empty">No customers found.</div>';
            return;
        }
        list.innerHTML = rows.map((c) => {
            const on = customerState.selected.has(c.key);
            return `
                <label class="customer-item">
                    <input type="checkbox" class="cust-check" value="${esc(c.key)}"${on ? " checked" : ""}>
                    <span class="cust-label"><strong>${esc(c.key)}</strong> &middot; ${esc(c.name)}</span>
                </label>`;
        }).join("");
        list.querySelectorAll(".cust-check").forEach((cb) => {
            cb.addEventListener("change", () => {
                const key = cb.value;
                const row = customerState.all.find((r) => r.key === key);
                if (cb.checked && row) customerState.selected.set(key, row.name);
                else                   customerState.selected.delete(key);
                renderChips();
            });
        });
    }

    function renderChips() {
        const chipsEl = $("selectedCustomers");
        const countEl = $("customerCount");
        const entries = [...customerState.selected.entries()];

        chipsEl.innerHTML = entries.map(([k, n]) =>
            `<span class="chip" data-key="${esc(k)}"><span>${esc(k)} &middot; ${esc(n)}</span><span class="chip-remove" aria-hidden="true">&times;</span></span>`
        ).join("");

        chipsEl.querySelectorAll(".chip").forEach((chip) => {
            chip.addEventListener("click", () => {
                const k = chip.dataset.key;
                customerState.selected.delete(k);
                // Uncheck the matching row if present.
                const cb = document.querySelector(`.cust-check[value="${cssEsc(k)}"]`);
                if (cb) cb.checked = false;
                renderChips();
            });
        });

        if (countEl) {
            if (entries.length) {
                countEl.textContent = `${entries.length} selected`;
                countEl.hidden = false;
            } else {
                countEl.hidden = true;
            }
        }
    }

    function initCustomerSearch() {
        if (!cfg.hasCustomer) return;
        const search = $("customerSearch");
        search.addEventListener("input", () => {
            const q = search.value.trim().toLowerCase();
            if (!q) return renderList(customerState.all);
            const filtered = customerState.all.filter((c) =>
                c.key.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)
            );
            renderList(filtered);
        });
    }

    // ---- Submit -------------------------------------------------------
    function buildQueryString() {
        const parts = [];
        const add = (k, v) => { if (v !== "" && v != null) parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`); };

        if (cfg.hasPeriod) {
            const p = $("periodInput").value;
            add("period", p);
            if (p === "custom") {
                add("start_date", $("fromDate").value);
                add("end_date",   $("toDate").value);
            }
        }
        if (cfg.hasYear) add("year", $("yearInput").value);
        if (cfg.hasStatus) add("status", $("statusInput").value);
        if (cfg.hasSalesman) add("salesman", $("salesmanSelect").value);
        if (cfg.hasCustomer) {
            for (const key of customerState.selected.keys()) add("customers", key);
        }
        return parts.join("&");
    }

    form.addEventListener("submit", (e) => {
        e.preventDefault();
        const qs = buildQueryString();
        window.location.href = cfg.viewUrl + (qs ? "?" + qs : "");
    });

    // ---- API preview --------------------------------------------------
    let previewTimer = null;
    function refreshApiPreview() {
        if (!cfg.previewUrl) return;
        const urlEl  = $("apiPreviewUrl");
        const bodyEl = $("apiPreviewBody");
        const hintEl = $("apiPreviewHint");
        if (!bodyEl) return;

        const qs = buildQueryString();
        fetch(cfg.previewUrl + (qs ? "?" + qs : ""), {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        })
        .then((r) => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
        .then((preview) => {
            urlEl.textContent  = preview.url || "(REPORTING_API_BASE_URL not set)";
            bodyEl.textContent = JSON.stringify(preview.body || {}, null, 2);
            const keys = Object.keys(preview.body || {}).length;
            const cfgState = preview.configured ? "" : " — API not configured";
            hintEl.textContent = keys
                ? `(${keys} param${keys === 1 ? "" : "s"})${cfgState}`
                : `(no params)${cfgState}`;
        })
        .catch((e) => {
            bodyEl.textContent = "// preview failed: " + e.message;
        });
    }
    function schedulePreviewRefresh() {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(refreshApiPreview, 200);
    }
    // Anything that changes a filter should re-fire the preview.
    form.addEventListener("input",  schedulePreviewRefresh);
    form.addEventListener("change", schedulePreviewRefresh);
    form.addEventListener("click",  (e) => {
        if (e.target.closest(".period-btn") || e.target.closest(".status-btn")
            || e.target.closest(".customer-pill") || e.target.closest(".customer-card")) {
            schedulePreviewRefresh();
        }
    });

    // ---- Helpers ------------------------------------------------------
    function fetchJson(url) {
        return fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            });
    }
    function toIso(d) {
        const m = (d.getMonth() + 1).toString().padStart(2, "0");
        const day = d.getDate().toString().padStart(2, "0");
        return `${d.getFullYear()}-${m}-${day}`;
    }
    function esc(s) {
        return String(s ?? "")
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }
    function cssEsc(s) { return String(s ?? "").replace(/(["\\])/g, "\\$1"); }

    // ---- Lookup polling -----------------------------------------------
    // The first time anyone hits the form, the server kicks off a slow
    // populate. We poll status until it's ready, then fill the dropdowns.
    let lookupPollTimer = null;
    let lookupReady = false;
    let lookupSource = null; // "live" | "mirror"
    let lookupPollStartedAt = Date.now();
    const MIRROR_FALLBACK_GRACE_MS = 5000;

    function setLookupBanner(text, kind) {
        const el = $("lookupBanner");
        if (!el) return;
        if (!text) {
            el.hidden = true;
            el.textContent = "";
            el.className = "lookup-banner";
            return;
        }
        el.hidden = false;
        el.textContent = text;
        el.className = "lookup-banner" + (kind ? (" lookup-banner-" + kind) : "");
    }

    function loadLookupDropdowns(source) {
        lookupReady = true;
        lookupSource = source || "live";
        if (cfg.hasSalesman) {
            fetchJson(cfg.salesmenUrl).then(applySalesmen).catch(() => {});
        }
        if (cfg.hasCustomer) {
            loadCustomers();
        }
    }

    function mirrorFallbackAllowed() {
        return (Date.now() - lookupPollStartedAt) >= MIRROR_FALLBACK_GRACE_MS;
    }

    async function pollLookupStatus() {
        if (!cfg.lookupStatusUrl) return;
        try {
            const status = await fetchJson(cfg.lookupStatusUrl);
            const mirrorRows = status.mirror_row_count || 0;

            if (!status.configured) {
                setLookupBanner("Reporting API not configured. Type in a salesman/customer if you need to filter.", "warn");
                lookupReady = true; // Stop polling; nothing to wait for.
                return;
            }

            if (status.cached_row_count > 0 && (!lookupReady || lookupSource === "mirror")) {
                // Live/in-process data is available now. If we had loaded
                // the mirror after a long wait, swap the dropdowns back to
                // the fresh API-backed cache without requiring a page reload.
                setLookupBanner("", null);
                loadLookupDropdowns("live");
                return;
            }

            if (status.status === "loading") {
                const elapsed = status.started_at
                    ? Math.round((Date.now() / 1000 - status.started_at)) : 0;
                if (mirrorRows > 0 && mirrorFallbackAllowed() && !lookupReady) {
                    setLookupBanner(
                        "The live customer/salesman list is still loading, so this page is temporarily " +
                        "showing the offline mirror. It will swap to live data when ready.",
                        "info"
                    );
                    loadLookupDropdowns("mirror");
                    schedulePoll(10000);
                    return;
                }
                setLookupBanner(
                    mirrorRows > 0
                        ? `Loading live customer/salesman list from server\u2026 (${elapsed}s). Offline mirror is available if this takes too long.`
                        : `Loading customer/salesman list from server\u2026 (${elapsed}s)`,
                    "info"
                );
                schedulePoll(2000);
                return;
            }

            if (status.status === "error") {
                if (mirrorRows > 0 && mirrorFallbackAllowed() && !lookupReady) {
                    setLookupBanner(
                        "Live lookup is still unavailable after retrying, so this page is showing the " +
                        "offline customer/salesman list. It will keep checking for live data.",
                        "info"
                    );
                    loadLookupDropdowns("mirror");
                    schedulePoll(15000);
                    return;
                }
                setLookupBanner(
                    mirrorRows > 0
                        ? "Live customer/salesman lookup failed, but it is retrying. Holding the offline mirror for now so we do not show stale data too early."
                        : "Couldn't load the customer/salesman list yet. Retrying live API; the form still works if you type values manually.",
                    mirrorRows > 0 ? "info" : "warn"
                );
                schedulePoll(10000);
                return;
            }

            // Idle / unknown -- give the server a chance to start by
            // polling status. The status endpoint now kicks the populate;
            // don't hit dropdown endpoints here, because those intentionally
            // serve the mirror immediately when cache is empty.
            setLookupBanner("Starting customer/salesman lookup from the reporting API\u2026", "info");
            schedulePoll(2000);
        } catch (e) {
            // Network or auth error on the status endpoint itself; back off.
            schedulePoll(10000);
        }
    }

    function schedulePoll(delayMs) {
        clearTimeout(lookupPollTimer);
        lookupPollTimer = setTimeout(pollLookupStatus, delayMs);
    }

    // ---- Boot ---------------------------------------------------------
    // Order matters: kick the API preview off FIRST so the panel fills in
    // immediately even while the slow lookup populate is in flight.
    refreshApiPreview();
    initPeriod();
    initStatus();
    initYear();
    initSalesmanShell();
    if (cfg.hasCustomer) initCustomerSearch();
    // Lookup populate runs in parallel with everything else.
    if (cfg.hasSalesman || cfg.hasCustomer) pollLookupStatus();
})();
