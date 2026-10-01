function mountFolderPicker(opts) {
  var current = "";
  var input = document.getElementById(opts.inputId);
  var breadcrumb = document.getElementById(opts.breadcrumbId);
  var picker = document.getElementById(opts.pickerId);
  var selected = document.getElementById(opts.selectedId);
  var status = document.getElementById(opts.statusId);
  var rootLabel = opts.rootLabel || "Root";

  function showSelected() {
    if (!selected) return;
    var path = input ? input.value : "";
    selected.textContent = path ? "Will save to: " + path : "";
  }

  function renderBreadcrumb(path) {
    if (!breadcrumb) return;
    breadcrumb.replaceChildren();
    function crumb(label, target) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "sp-crumb";
      button.textContent = label;
      button.addEventListener("click", function () { load(target); });
      breadcrumb.appendChild(button);
    }
    crumb(rootLabel, "");
    var acc = "";
    (path ? path.split("/") : []).forEach(function (part) {
      acc = acc ? acc + "/" + part : part;
      breadcrumb.appendChild(document.createTextNode(" / "));
      crumb(part, acc);
    });
    var use = document.createElement("button");
    use.type = "button";
    use.className = "sp-use";
    use.textContent = "Use this folder";
    use.addEventListener("click", function () {
      if (input) input.value = current;
      showSelected();
    });
    breadcrumb.appendChild(use);
  }

  function renderFolders(folders) {
    if (!picker) return;
    picker.replaceChildren();
    if (!folders.length) {
      picker.innerHTML = '<div class="sp-empty">No subfolders here.</div>';
      return;
    }
    folders.forEach(function (folder) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "sp-folder";
      button.textContent = folder.name;
      button.addEventListener("click", function () { load(folder.path); });
      picker.appendChild(button);
    });
  }

  function load(path) {
    current = path || "";
    renderBreadcrumb(current);
    fetch(opts.foldersUrl + "?path=" + encodeURIComponent(current), { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
      .then(function (result) {
        if (!result.ok) {
          if (picker) picker.textContent = result.data.error || "Could not list folders.";
          return;
        }
        renderFolders(result.data.folders || []);
      })
      .catch(function () {
        if (picker) picker.textContent = "Could not list folders.";
      });
  }

  function init() {
    fetch(opts.statusUrl, { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var section = document.getElementById(opts.sectionId);
        if (!data.enabled) {
          if (section) section.hidden = true;
          return;
        }
        if (section) section.hidden = false;
        if (status) status.textContent = data.configured ? "" : "(practice folders until Graph is set)";
        showSelected();
        load(input && input.value && input.value.indexOf("{") === -1 ? input.value : "");
      })
      .catch(function () {
        if (status) status.textContent = "Folder list unavailable.";
      });
  }

  if (input) input.addEventListener("change", showSelected);
  return { init: init };
}
