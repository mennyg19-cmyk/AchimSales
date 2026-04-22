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
        reportKey:    root.dataset.reportKey,
        reportName:   root.dataset.reportName,
        salesmenUrl:  root.dataset.salesmenUrl,
        customersUrl: root.dataset.customersUrl,
        yearsUrl:     root.dataset.yearsUrl,
        viewUrl:      root.dataset.viewUrl,
        hasPeriod:    root.dataset.hasPeriod   === "true",
        hasStatus:    root.dataset.hasStatus   === "true",
        hasYear:      root.dataset.hasYear     === "true",
        hasSalesman:  root.dataset.hasSalesman === "true",
        hasCustomer:  root.dataset.hasCustomer === "true",
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

    // ---- Salesman dropdown --------------------------------------------
    async function initSalesman() {
        if (!cfg.hasSalesman) return;
        const sel = $("salesmanSelect");
        try {
            const rows = await fetchJson(cfg.salesmenUrl);
            const opts = ['<option value="">All Salesmen</option>'].concat(
                rows.map((r) => `<option value="${esc(r.key)}">${esc(r.name)}</option>`),
            );
            sel.innerHTML = opts.join("");
        } catch {
            // Leave the existing "All Salesmen" option in place.
        }

        // When the salesman changes, reload the customer list (if shown).
        if (cfg.hasCustomer) {
            sel.addEventListener("change", loadCustomers);
        }
    }

    // ---- Customer multi-select ----------------------------------------
    const customerState = {
        all: [],         // [{key, name}]
        selected: new Map(),  // key -> name
    };

    async function loadCustomers() {
        if (!cfg.hasCustomer) return;
        const list = $("customerList");
        list.innerHTML = '<div class="customer-picker-loading">Loading customers&hellip;</div>';
        customerState.selected.clear();
        renderChips();

        let url = cfg.customersUrl;
        const sm = cfg.hasSalesman ? ($("salesmanSelect")?.value || "") : "";
        if (sm) url += (url.includes("?") ? "&" : "?") + "salesman=" + encodeURIComponent(sm);

        try {
            customerState.all = await fetchJson(url);
            renderList(customerState.all);
        } catch (e) {
            list.innerHTML = `<div class="customer-picker-empty">Could not load customers (${esc(e.message || e)}).</div>`;
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

    // ---- Boot ---------------------------------------------------------
    initPeriod();
    initStatus();
    initYear();
    initSalesman();
    if (cfg.hasCustomer) { initCustomerSearch(); loadCustomers(); }
})();
