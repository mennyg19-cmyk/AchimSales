// Small bits of interactivity for the schedule form: show the weekday or
// month-day fields only for the matching frequency, and show only the tabs that
// belong to the report that's currently selected. The form works without this
// (the server validates and defaults); this just hides options that don't apply.

(function () {
  "use strict";

  function showCadenceFields(form) {
    var freq = form.querySelector("[data-freq]").value;
    form.querySelectorAll(".cadence-block").forEach(function (block) {
      block.hidden = block.getAttribute("data-when") !== freq;
    });
  }

  function filterTabs(form) {
    var report = form.querySelector("[data-report-select]").value;
    var tabSelect = form.querySelector("[data-tab-select]");
    if (!tabSelect) return;
    var stillValid = false;
    Array.prototype.forEach.call(tabSelect.options, function (option) {
      var owner = option.getAttribute("data-report");
      var matches = !owner || owner === report; // the blank "first tab" option has no owner
      option.hidden = !matches;
      if (matches && option.selected) stillValid = true;
    });
    if (!stillValid) tabSelect.value = "";
  }

  document.querySelectorAll(".sched-form").forEach(function (form) {
    var freq = form.querySelector("[data-freq]");
    var report = form.querySelector("[data-report-select]");
    if (freq) freq.addEventListener("change", function () { showCadenceFields(form); });
    if (report) report.addEventListener("change", function () { filterTabs(form); });
    showCadenceFields(form);
    filterTabs(form);
  });
})();
