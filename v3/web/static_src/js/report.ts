/**
 * Report viewer entry. Wires the page; grid/filters/jobs/views/delivery live
 * in sibling modules. The server owns math and scope.
 */

import { bindMenu } from "./dialog";
import { $, autoRunRequested, root, setAutoRunRequested, setStatus } from "./report-core";
import { closeEmailModal, emailMe, keepCurrentRun, openEmailModal, openScheduleWizard, sendEmail } from "./report-delivery";
import {
  applyDeepLink, initCustomRangeToggle, initLookups, refreshPreviewIfOpen, showApiPreview,
} from "./report-filters";
import { fitTableHeight, toggleColumnsPanel } from "./report-grid";
import {
  cancelRun, closeExportMenu, closeMoreMenu, exportExcel, isReportShown,
  loadExports, resetView, resumeInFlight, run, setControlsCollapsed, setToolbarEnabled,
  toggleExportMenu, toggleExportsPanel, toggleMoreMenu,
} from "./report-jobs";
import { autoOpenPresetIfRequested, loadCompanyDefault, saveView, togglePresetsPanel } from "./report-views";

document.addEventListener("DOMContentLoaded", async () => {
  if (!root) return;
  applyDeepLink();
  initCustomRangeToggle();
  $("controlsToggle")?.addEventListener("click", () => {
    setControlsCollapsed(!$("reportControls")?.classList.contains("collapsed"));
  });
  $("runBtn")?.addEventListener("click", () => run({ preserveLayout: isReportShown() }));
  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(fitTableHeight, 120);
  });
  $("apiRunBtn")?.addEventListener("click", () => {
    const panel = $("apiPreview") as HTMLTextAreaElement | null;
    if (!panel) return;
    try {
      const parsed = JSON.parse(panel.value);
      run({ overrideParams: parsed });
    } catch {
      setStatus("Invalid JSON in the API preview. Fix it and try again.", "error");
    }
  });
  $("cancelRunBtn")?.addEventListener("click", cancelRun);
  $("refreshBtn")?.addEventListener("click", () => run({ preserveLayout: true }));
  $("resetBtn")?.addEventListener("click", resetView);
  $("exportMenuBtn")?.addEventListener("click", toggleExportMenu);
  $("exportBtn")?.addEventListener("click", () => { closeExportMenu(); exportExcel(); });
  $("keepBtn")?.addEventListener("click", keepCurrentRun);
  $("exportsBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    closeExportMenu();
    toggleExportsPanel();
  });
  $("columnsBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    closeExportMenu();
    closeMoreMenu();
    toggleColumnsPanel();
  });
  $("saveViewBtn")?.addEventListener("click", saveView);
  $("presetsBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    closeExportMenu();
    closeMoreMenu();
    togglePresetsPanel();
  });
  $("moreBtn")?.addEventListener("click", toggleMoreMenu);
  $("emailBtn")?.addEventListener("click", openEmailModal);
  $("emailMeBtn")?.addEventListener("click", () => { void emailMe(); });
  $("emailClose")?.addEventListener("click", closeEmailModal);
  $("emailCancel")?.addEventListener("click", closeEmailModal);
  $("emailSend")?.addEventListener("click", sendEmail);
  $("emailModal")?.addEventListener("click", (e) => { if (e.target === $("emailModal")) closeEmailModal(); });
  $("scheduleBtn")?.addEventListener("click", openScheduleWizard);
  const exportBtn = $("exportMenuBtn");
  const exportMenu = $("exportMenu");
  if (exportBtn && exportMenu) bindMenu(exportBtn, exportMenu);
  const moreBtn = $("moreBtn");
  const moreMenu = $("moreMenu");
  if (moreBtn && moreMenu) bindMenu(moreBtn, moreMenu);
  const back = document.querySelector<HTMLAnchorElement>(".back-link");
  if (back) {
    try {
      const ref = document.referrer;
      if (ref) {
        const u = new URL(ref);
        if (u.origin === location.origin && u.pathname !== location.pathname) {
          back.href = ref;
        }
      }
    } catch { /* keep Reports */ }
  }
  $("previewBtn")?.addEventListener("click", () => { closeMoreMenu(); showApiPreview(); });
  $("filterForm")?.addEventListener("input", refreshPreviewIfOpen);
  $("filterForm")?.addEventListener("change", refreshPreviewIfOpen);
  setToolbarEnabled(false);
  loadExports();
  await Promise.all([initLookups(), loadCompanyDefault()]);
  const resumed = await resumeInFlight();
  if (!resumed) {
    await autoOpenPresetIfRequested();
    if (autoRunRequested) { setAutoRunRequested(false); run(); }
  }
});

export {};
