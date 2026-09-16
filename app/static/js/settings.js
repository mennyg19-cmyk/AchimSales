async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: csrfHeaders(),
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || "Save failed (HTTP " + res.status + ")");
  }
  return data;
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".vis-toggle").forEach((box) => {
    box.addEventListener("change", () => {
      postJson("/api/settings/visibility", { key: box.getAttribute("data-key"), enabled: box.checked })
        .catch((err) => alert(err.message));
    });
  });
  document.querySelectorAll(".flag-toggle").forEach((box) => {
    box.addEventListener("change", () => {
      postJson("/api/settings/flag", { key: box.getAttribute("data-key"), enabled: box.checked })
        .catch((err) => alert(err.message));
    });
  });
  const testToggle = document.getElementById("scheduleTestToggle");
  if (testToggle) {
    testToggle.addEventListener("change", () => {
      postJson("/api/settings/test-mode", { enabled: testToggle.checked })
        .catch((err) => alert(err.message));
    });
  }
  const exclPicker = document.getElementById("exclPicker");
  const exclSearch = document.getElementById("exclSearch");
  const exclMenu = document.getElementById("exclMenu");
  const exclPills = document.getElementById("exclPills");
  const exclSave = document.getElementById("exclSave");
  if (exclPicker && exclSearch && exclMenu && exclPills && exclSave) {
    let customers = [];
    let excluded = [];
    try {
      customers = JSON.parse(exclPicker.getAttribute("data-customers") || "[]");
      if (!Array.isArray(customers)) throw new Error("not an array");
    } catch (err) {
      alert("Customer list could not be read (" + err.message + "). Expected a JSON array.");
      customers = [];
    }
    try {
      excluded = JSON.parse(exclPicker.getAttribute("data-excluded") || "[]");
      if (!Array.isArray(excluded)) throw new Error("not an array");
    } catch (err) {
      alert("Saved exclusions could not be read (" + err.message + "). Expected a JSON array.");
      excluded = [];
    }
    const selected = new Set(excluded.map(String).filter(Boolean));
    const EXCL_MENU_LIMIT = 200;

    function customerLabel(account) {
      const row = customers.find((item) => item.account === account);
      return row ? row.name : account;
    }

    function renderExclPills() {
      exclPills.replaceChildren();
      selected.forEach((account) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "customer-chip";
        chip.setAttribute("data-account", account);
        chip.textContent = customerLabel(account) + " ✕";
        chip.addEventListener("click", () => {
          selected.delete(account);
          renderExclPills();
          if (!exclMenu.hidden) renderExclMenu();
        });
        exclPills.appendChild(chip);
      });
    }

    function renderExclMenu() {
      const term = (exclSearch.value || "").trim().toLowerCase();
      const rows = customers.filter((item) => {
        const hay = ((item.name || "") + " " + (item.account || "")).toLowerCase();
        return !term || hay.indexOf(term) !== -1;
      });
      exclMenu.replaceChildren();
      rows.slice(0, EXCL_MENU_LIMIT).forEach((item) => {
        const label = document.createElement("label");
        label.className = "customer-option";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.className = "excl-box";
        box.value = item.account;
        box.checked = selected.has(item.account);
        box.addEventListener("change", () => {
          if (box.checked) selected.add(item.account);
          else selected.delete(item.account);
          renderExclPills();
        });
        const text = document.createElement("span");
        text.textContent = (item.name || item.account) + " · " + item.account;
        label.appendChild(box);
        label.appendChild(text);
        exclMenu.appendChild(label);
      });
      if (!rows.length) {
        const empty = document.createElement("div");
        empty.className = "customer-empty";
        empty.textContent = customers.length ? "No matches" : "No customers loaded.";
        exclMenu.appendChild(empty);
      } else if (rows.length > EXCL_MENU_LIMIT) {
        const more = document.createElement("div");
        more.className = "customer-empty";
        more.textContent = "Type to narrow the list.";
        exclMenu.appendChild(more);
      }
      exclMenu.hidden = false;
    }

    renderExclPills();
    exclSearch.addEventListener("focus", renderExclMenu);
    exclSearch.addEventListener("input", renderExclMenu);
    document.addEventListener("click", (evt) => {
      if (!evt.target.closest("#exclPicker") && !evt.target.closest("#exclPills")) {
        exclMenu.hidden = true;
      }
    });
    exclSave.addEventListener("click", async () => {
      try {
        await postJson("/api/settings/exclusions", { accounts: Array.from(selected) });
        alert("Exclusions saved.");
      } catch (err) {
        alert(err.message);
      }
    });
  }
  const addForm = document.getElementById("testEmailAdd");
  if (addForm) {
    addForm.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      const input = document.getElementById("testEmailInput");
      const chips = Array.from(document.querySelectorAll(".js-test-email-remove")).map((btn) => btn.getAttribute("data-email"));
      if (input.value) chips.push(input.value);
      try {
        await postJson("/api/settings/test-emails", { emails: chips });
        location.reload();
      } catch (err) {
        alert(err.message);
      }
    });
  }
  document.querySelectorAll(".js-test-email-remove").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const remove = btn.getAttribute("data-email");
      const chips = Array.from(document.querySelectorAll(".js-test-email-remove"))
        .map((item) => item.getAttribute("data-email"))
        .filter((email) => email !== remove);
      try {
        await postJson("/api/settings/test-emails", { emails: chips });
        location.reload();
      } catch (err) {
        alert(err.message);
      }
    });
  });
});
