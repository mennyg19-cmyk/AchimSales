(function () {
  if (typeof Tabulator === "undefined") return;

  var siteFilterClose = null;

  function closeSiteFilter() {
    var pop = document.getElementById("siteColFilter");
    if (pop) pop.remove();
    if (siteFilterClose) siteFilterClose();
    siteFilterClose = null;
  }

  function openSiteFilter(column) {
    closeSiteFilter();
    var field = column.getField();
    var table = column.getTable();
    var current = "";
    (table.getFilters(true) || []).forEach(function (f) {
      if (f.field === field) current = String(f.value || "");
    });
    var pop = document.createElement("div");
    pop.id = "siteColFilter";
    pop.className = "col-filter-popover";
    pop.innerHTML =
      '<div class="col-filter-popover-title">Filter this column</div>'
      + '<input type="text" id="siteColFilterValue" placeholder="contains…">'
      + '<div class="col-filter-popover-foot">'
      + '<button type="button" class="btn btn-sm btn-outline" id="siteColFilterClear">Clear</button>'
      + '<button type="button" class="btn btn-sm btn-primary" id="siteColFilterApply">Apply</button>'
      + "</div>";
    document.body.appendChild(pop);
    var rect = column.getElement().getBoundingClientRect();
    pop.style.left = Math.min(rect.left, window.innerWidth - 260) + "px";
    pop.style.top = rect.bottom + 4 + "px";
    var input = document.getElementById("siteColFilterValue");
    input.value = current;
    input.focus();
    function apply(value) {
      table.removeFilter(field);
      if (String(value || "").trim()) table.addFilter(field, "like", value.trim());
      closeSiteFilter();
    }
    document.getElementById("siteColFilterApply").addEventListener("click", function () {
      apply(input.value);
    });
    document.getElementById("siteColFilterClear").addEventListener("click", function () {
      apply("");
    });
    input.addEventListener("keydown", function (evt) {
      if (evt.key === "Enter") apply(input.value);
    });
    setTimeout(function () {
      function onOut(evt) {
        if (!pop.contains(evt.target)) closeSiteFilter();
      }
      function onEsc(evt) {
        if (evt.key === "Escape") closeSiteFilter();
      }
      document.addEventListener("click", onOut);
      document.addEventListener("keydown", onEsc);
      siteFilterClose = function () {
        document.removeEventListener("click", onOut);
        document.removeEventListener("keydown", onEsc);
      };
    }, 0);
  }

  function siteHeaderMenu() {
    return [
      {
        label: "Filter this column",
        action: function (_e, column) { openSiteFilter(column); },
      },
      {
        label: "Hide column",
        action: function (_e, column) { column.hide(); },
      },
      {
        label: "Freeze / unfreeze",
        action: function (_e, column) {
          var def = column.getDefinition();
          column.getTable().updateColumnDefinition(column.getField(), { frozen: !def.frozen });
        },
      },
      {
        label: "Group by this column",
        action: function (_e, column) {
          column.getTable().setGroupBy(column.getField());
        },
      },
      {
        label: "Clear grouping",
        action: function (_e, column) {
          column.getTable().setGroupBy(false);
        },
      },
    ];
  }

  function slug(title, idx) {
    var base = String(title || "col").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
    return (base || "col") + "_" + idx;
  }

  function enhance(table) {
    if (table.dataset.siteTableDone === "1") return;
    if (!table.tHead || !table.tBodies.length) return;
    var heads = [];
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, idx) {
      heads.push({ title: th.textContent.trim() || ("Col " + (idx + 1)), idx: idx });
    });
    if (!heads.length) return;
    var owner = "";
    var grouped = false;
    var data = [];
    Array.prototype.forEach.call(table.tBodies[0].rows, function (tr) {
      if (tr.classList.contains("ps-owner-row")) {
        grouped = true;
        owner = tr.cells[0] ? tr.cells[0].textContent.trim() : "";
        return;
      }
      var rec = { _owner: owner };
      heads.forEach(function (head) {
        var td = tr.cells[head.idx];
        var field = slug(head.title, head.idx);
        if (!td) {
          rec[field] = "";
          return;
        }
        var htmlish = td.querySelector("form, a, button, details, input");
        rec[field] = htmlish ? td.innerHTML : td.innerText.replace(/\s+/g, " ").trim();
        rec[field + "_html"] = htmlish ? 1 : 0;
      });
      data.push(rec);
    });
    var host = document.createElement("div");
    host.className = "site-table-host";
    table.parentNode.insertBefore(host, table);
    table.hidden = true;
    table.dataset.siteTableDone = "1";
    var columns = heads.map(function (head) {
      var field = slug(head.title, head.idx);
      var isHtml = data.some(function (row) { return row[field + "_html"]; });
      var isActions = /action/i.test(head.title);
      return {
        title: head.title,
        field: field,
        headerMenu: siteHeaderMenu,
        headerMenuIcon: "⋮",
        headerSort: !isActions && !/active/i.test(head.title),
        formatter: isHtml ? "html" : "plaintext",
        frozen: isActions,
        minWidth: isActions ? 280 : 72,
        tooltip: !isHtml,
      };
    });
    var grid = new Tabulator(host, {
      data: data,
      columns: columns,
      layout: "fitDataStretch",
      movableColumns: true,
      groupBy: grouped ? "_owner" : false,
      placeholder: "No rows",
      rowHeight: 36,
    });
    host._tabulator = grid;
  }

  document.querySelectorAll("table.js-site-table").forEach(enhance);
})();
