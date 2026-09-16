function csrfToken() {
  return document.body.getAttribute("data-csrf") || "";
}

function csrfHeaders() {
  return {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken(),
  };
}
