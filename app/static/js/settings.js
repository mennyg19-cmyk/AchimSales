async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".vis-toggle").forEach((box) => {
    box.addEventListener("change", () => {
      postJson("/api/settings/visibility", { key: box.getAttribute("data-key"), enabled: box.checked });
    });
  });
  document.querySelectorAll(".flag-toggle").forEach((box) => {
    box.addEventListener("change", () => {
      postJson("/api/settings/flag", { key: box.getAttribute("data-key"), enabled: box.checked });
    });
  });
  const testToggle = document.getElementById("scheduleTestToggle");
  if (testToggle) {
    testToggle.addEventListener("change", () => {
      postJson("/api/settings/test-mode", { enabled: testToggle.checked });
    });
  }
  const exclSave = document.getElementById("exclSave");
  if (exclSave) {
    exclSave.addEventListener("click", async () => {
      const accounts = Array.from(document.querySelectorAll(".excl-box:checked")).map((box) => box.value);
      await postJson("/api/settings/exclusions", { accounts });
      alert("Exclusions saved.");
    });
  }
  const addForm = document.getElementById("testEmailAdd");
  if (addForm) {
    addForm.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      const input = document.getElementById("testEmailInput");
      const chips = Array.from(document.querySelectorAll(".js-test-email-remove")).map((btn) => btn.getAttribute("data-email"));
      if (input.value) chips.push(input.value);
      await postJson("/api/settings/test-emails", { emails: chips });
      location.reload();
    });
  }
  document.querySelectorAll(".js-test-email-remove").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const remove = btn.getAttribute("data-email");
      const chips = Array.from(document.querySelectorAll(".js-test-email-remove"))
        .map((item) => item.getAttribute("data-email"))
        .filter((email) => email !== remove);
      await postJson("/api/settings/test-emails", { emails: chips });
      location.reload();
    });
  });
});
