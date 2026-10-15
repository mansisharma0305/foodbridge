/* Small progressive enhancements: confirm dialogs and loading states. */
(function () {
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
      return;
    }
    if (!form.hasAttribute("data-loading")) return;
    var button = form.querySelector('button[type="submit"], input[type="submit"]');
    if (!button || button.disabled) return;
    // Disable after the browser has collected the form data.
    window.setTimeout(function () {
      button.disabled = true;
      if (button.tagName === "BUTTON") {
        button.setAttribute("data-original", button.innerHTML);
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Please wait…';
      }
    }, 0);
  });

  // Restore buttons if the page is shown again from the back/forward cache.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll("button[data-original]").forEach(function (b) {
      b.innerHTML = b.getAttribute("data-original");
      b.disabled = false;
    });
  });
})();
