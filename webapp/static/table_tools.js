/**
 * Table enhancement toolkit:
 *  - Expand/collapse wrapper to break out of the .container max-width
 *  - Drag-to-resize column handles between <th> cells
 *  - Double-click a handle to auto-fit that column to its content
 *  - Persists expanded state and column widths per-table (by id / text signature)
 *
 * Attaches to every .table-wrapper that contains a .data-table, on DOM ready
 * and (via MutationObserver) on dynamically injected tables.
 */
(function () {
    'use strict';

    var STORAGE_KEY_PREFIX = 'tblw__';
    var MIN_COL_WIDTH = 40;
    var MAX_COL_WIDTH = 1200;

    function tableKey(table) {
        if (table.id) return 'id:' + table.id;
        var wrapper = table.closest('.table-wrapper');
        if (wrapper && wrapper.id) return 'wrap:' + wrapper.id;
        // Fallback: hash of the column header text
        var headers = [];
        table.querySelectorAll('thead th').forEach(function (th) {
            headers.push((th.textContent || '').trim().slice(0, 24));
        });
        var path = (location.pathname || '').replace(/\//g, '_');
        return 'path:' + path + '|cols:' + headers.join('|');
    }

    function loadState(key) {
        try {
            var raw = localStorage.getItem(STORAGE_KEY_PREFIX + key);
            return raw ? JSON.parse(raw) : null;
        } catch (e) { return null; }
    }

    function saveState(key, state) {
        try {
            localStorage.setItem(STORAGE_KEY_PREFIX + key, JSON.stringify(state));
        } catch (e) { /* quota / private mode */ }
    }

    function ensureToolbar(wrapper) {
        if (wrapper.querySelector(':scope > .table-toolbar')) return;
        var bar = document.createElement('div');
        bar.className = 'table-toolbar';
        bar.innerHTML =
            '<button type="button" class="table-tool-btn" data-action="fit" title="Auto-fit columns to contents">' +
                '<span class="tt-icon">&#8596;</span> Fit' +
            '</button>' +
            '<button type="button" class="table-tool-btn" data-action="reset" title="Reset column widths">' +
                '<span class="tt-icon">&#10226;</span>' +
            '</button>' +
            '<button type="button" class="table-tool-btn" data-action="expand" title="Expand table to full width">' +
                '<span class="tt-icon tt-icon-expand">&#8690;</span>' +
                '<span class="tt-icon tt-icon-collapse" style="display:none;">&#8689;</span>' +
            '</button>';
        // Insert the toolbar before the table
        wrapper.insertBefore(bar, wrapper.firstChild);

        bar.addEventListener('click', function (e) {
            var btn = e.target.closest('button[data-action]');
            if (!btn) return;
            var action = btn.getAttribute('data-action');
            var table = wrapper.querySelector('.data-table');
            if (!table) return;
            if (action === 'expand') toggleExpand(wrapper, table);
            else if (action === 'fit') autoFitAllColumns(table);
            else if (action === 'reset') resetColumnWidths(wrapper, table);
        });
    }

    function toggleExpand(wrapper, table) {
        var expanded = wrapper.classList.toggle('table-expanded');
        var key = tableKey(table);
        var state = loadState(key) || {};
        state.expanded = expanded;
        saveState(key, state);
        // Toggle icon
        var exp = wrapper.querySelector('.tt-icon-expand');
        var col = wrapper.querySelector('.tt-icon-collapse');
        if (exp && col) {
            exp.style.display = expanded ? 'none' : '';
            col.style.display = expanded ? '' : 'none';
        }
    }

    /**
     * Measure the widest cell in a column and return an appropriate pixel width.
     * Creates a hidden mirror cell so we don't disturb the live layout.
     */
    function measureColumn(table, colIdx) {
        var rows = table.rows;
        if (!rows.length) return MIN_COL_WIDTH;

        // Prefer a lightweight approach: use scrollWidth of current cells when
        // their own width isn't constrained. To do that we temporarily remove
        // any width on the header and let the browser compute natural width.
        var th = rows[0].cells[colIdx];
        if (!th) return MIN_COL_WIDTH;

        var prevWidth = th.style.width;
        var prevMinWidth = th.style.minWidth;
        var prevMaxWidth = th.style.maxWidth;
        th.style.width = 'auto';
        th.style.minWidth = '0';
        th.style.maxWidth = 'none';

        var max = 0;
        for (var i = 0; i < rows.length; i++) {
            var cell = rows[i].cells[colIdx];
            if (!cell) continue;
            var prev = cell.style.width;
            cell.style.width = 'auto';
            // scrollWidth includes overflowing content; add padding allowance
            var w = cell.scrollWidth;
            if (w > max) max = w;
            cell.style.width = prev;
        }

        th.style.width = prevWidth;
        th.style.minWidth = prevMinWidth;
        th.style.maxWidth = prevMaxWidth;

        // Add a little breathing room; clamp to sane bounds.
        var result = Math.max(MIN_COL_WIDTH, Math.min(MAX_COL_WIDTH, max + 16));
        return result;
    }

    function setColumnWidth(table, colIdx, widthPx) {
        var th = table.rows[0] && table.rows[0].cells[colIdx];
        if (!th) return;
        // Force table to respect explicit widths
        table.style.tableLayout = 'fixed';
        th.style.width = widthPx + 'px';
        th.style.minWidth = widthPx + 'px';
        th.style.maxWidth = widthPx + 'px';
        // Apply to cells in this column so ellipsis works uniformly
        for (var i = 1; i < table.rows.length; i++) {
            var cell = table.rows[i].cells[colIdx];
            if (!cell) continue;
            cell.style.width = widthPx + 'px';
            cell.style.minWidth = widthPx + 'px';
            cell.style.maxWidth = widthPx + 'px';
            cell.style.overflow = 'hidden';
            cell.style.textOverflow = 'ellipsis';
            if (!cell.title && cell.textContent && cell.textContent.length > 20) {
                cell.title = cell.textContent.trim();
            }
        }
    }

    function autoFitColumn(table, colIdx) {
        // Temporarily allow the column to shrink to content.
        var th = table.rows[0] && table.rows[0].cells[colIdx];
        if (!th) return;
        // Remove fixed sizing to measure true natural width
        var prevLayout = table.style.tableLayout;
        table.style.tableLayout = 'auto';
        for (var i = 0; i < table.rows.length; i++) {
            var cell = table.rows[i].cells[colIdx];
            if (!cell) continue;
            cell.style.width = '';
            cell.style.minWidth = '';
            cell.style.maxWidth = '';
            cell.style.overflow = '';
            cell.style.textOverflow = '';
        }
        // Force reflow
        void table.offsetWidth;
        var width = measureColumn(table, colIdx);
        table.style.tableLayout = prevLayout;
        setColumnWidth(table, colIdx, width);
        return width;
    }

    function autoFitAllColumns(table) {
        if (!table.rows.length) return;
        var cols = table.rows[0].cells.length;
        // First, blow out all constraints so measurement is unbiased
        var prevLayout = table.style.tableLayout;
        table.style.tableLayout = 'auto';
        for (var r = 0; r < table.rows.length; r++) {
            for (var c = 0; c < table.rows[r].cells.length; c++) {
                var cell = table.rows[r].cells[c];
                cell.style.width = '';
                cell.style.minWidth = '';
                cell.style.maxWidth = '';
                cell.style.overflow = '';
                cell.style.textOverflow = '';
            }
        }
        void table.offsetWidth;
        var widths = [];
        for (var i = 0; i < cols; i++) {
            widths.push(measureColumn(table, i));
        }
        table.style.tableLayout = prevLayout;
        for (var j = 0; j < cols; j++) {
            setColumnWidth(table, j, widths[j]);
        }
        saveWidths(table, widths);
    }

    function resetColumnWidths(wrapper, table) {
        var key = tableKey(table);
        var state = loadState(key) || {};
        delete state.widths;
        saveState(key, state);
        table.style.tableLayout = '';
        if (!table.rows.length) return;
        for (var r = 0; r < table.rows.length; r++) {
            for (var c = 0; c < table.rows[r].cells.length; c++) {
                var cell = table.rows[r].cells[c];
                cell.style.width = '';
                cell.style.minWidth = '';
                cell.style.maxWidth = '';
                cell.style.overflow = '';
                cell.style.textOverflow = '';
            }
        }
    }

    function saveWidths(table, widths) {
        var key = tableKey(table);
        var state = loadState(key) || {};
        state.widths = widths;
        saveState(key, state);
    }

    function applyStoredState(wrapper, table) {
        var key = tableKey(table);
        var state = loadState(key);
        if (!state) return;
        if (state.expanded) {
            wrapper.classList.add('table-expanded');
            var exp = wrapper.querySelector('.tt-icon-expand');
            var col = wrapper.querySelector('.tt-icon-collapse');
            if (exp && col) { exp.style.display = 'none'; col.style.display = ''; }
        }
        if (state.widths && state.widths.length && table.rows[0]) {
            if (state.widths.length === table.rows[0].cells.length) {
                for (var i = 0; i < state.widths.length; i++) {
                    setColumnWidth(table, i, state.widths[i]);
                }
            }
        }
    }

    function installResizers(table) {
        if (!table.rows.length) return;
        table.classList.add('table-with-resizers');
        var headerRow = table.rows[0];
        for (var i = 0; i < headerRow.cells.length - 1; i++) {
            var th = headerRow.cells[i];
            if (th.querySelector(':scope > .col-resizer')) continue;
            // Header must be positioned to host the absolute handle
            var cs = window.getComputedStyle(th);
            if (cs.position === 'static') th.style.position = 'relative';
            var grip = document.createElement('span');
            grip.className = 'col-resizer';
            grip.setAttribute('data-col-index', String(i));
            grip.title = 'Drag to resize · double-click to auto-fit';
            th.appendChild(grip);
            attachResizerHandlers(grip, table, i);
        }
    }

    function attachResizerHandlers(grip, table, colIdx) {
        var startX = 0, startWidth = 0, active = false;

        function onDown(e) {
            e.preventDefault();
            e.stopPropagation();
            active = true;
            startX = (e.touches ? e.touches[0].clientX : e.clientX);
            var th = table.rows[0].cells[colIdx];
            startWidth = th.offsetWidth;
            document.body.classList.add('col-resizing');
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
            document.addEventListener('touchmove', onMove, { passive: false });
            document.addEventListener('touchend', onUp);
        }

        function onMove(e) {
            if (!active) return;
            e.preventDefault();
            var clientX = (e.touches ? e.touches[0].clientX : e.clientX);
            var delta = clientX - startX;
            var next = Math.max(MIN_COL_WIDTH, Math.min(MAX_COL_WIDTH, startWidth + delta));
            setColumnWidth(table, colIdx, next);
        }

        function onUp() {
            if (!active) return;
            active = false;
            document.body.classList.remove('col-resizing');
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onUp);
            // Persist the new widths
            var widths = [];
            var headerRow = table.rows[0];
            for (var i = 0; i < headerRow.cells.length; i++) {
                widths.push(headerRow.cells[i].offsetWidth);
            }
            saveWidths(table, widths);
        }

        grip.addEventListener('mousedown', onDown);
        grip.addEventListener('touchstart', onDown, { passive: false });
        grip.addEventListener('dblclick', function (e) {
            e.preventDefault();
            e.stopPropagation();
            autoFitColumn(table, colIdx);
            // Save updated widths
            var headerRow = table.rows[0];
            var widths = [];
            for (var i = 0; i < headerRow.cells.length; i++) {
                widths.push(headerRow.cells[i].offsetWidth);
            }
            saveWidths(table, widths);
        });
        // Swallow clicks so sort handlers on <th> don't fire
        grip.addEventListener('click', function (e) { e.stopPropagation(); });
    }

    function enhanceWrapper(wrapper) {
        var table = wrapper.querySelector('.data-table');
        if (!table || table.dataset.tblEnhanced === '1') return;
        // Skip tiny tables (< 2 data rows) where enhancement adds noise
        if (table.rows.length < 2) return;
        table.dataset.tblEnhanced = '1';
        ensureToolbar(wrapper);
        installResizers(table);
        applyStoredState(wrapper, table);
    }

    function enhanceAll(root) {
        root = root || document;
        root.querySelectorAll('.table-wrapper').forEach(enhanceWrapper);
    }

    function observeDynamic() {
        if (!window.MutationObserver) return;
        var mo = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var m = mutations[i];
                if (!m.addedNodes) continue;
                for (var j = 0; j < m.addedNodes.length; j++) {
                    var n = m.addedNodes[j];
                    if (n.nodeType !== 1) continue;
                    if (n.matches && n.matches('.table-wrapper')) enhanceWrapper(n);
                    if (n.querySelectorAll) enhanceAll(n);
                }
            }
        });
        mo.observe(document.body, { childList: true, subtree: true });
    }

    function init() {
        enhanceAll(document);
        observeDynamic();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose for ad-hoc use
    window.TableTools = {
        enhanceAll: enhanceAll,
        enhanceWrapper: enhanceWrapper,
        autoFitAllColumns: autoFitAllColumns,
        resetColumnWidths: resetColumnWidths
    };
})();
