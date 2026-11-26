// Mobile menu toggle. Keeps aria-expanded and the button label in sync.
(function () {
  "use strict";

  var header = document.querySelector(".site-header");
  var toggle = document.querySelector(".menu-toggle");
  if (!header || !toggle) return;

  function setOpen(open) {
    header.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    var label = open ? toggle.dataset.labelClose : toggle.dataset.labelOpen;
    if (label) toggle.setAttribute("aria-label", label);
  }

  toggle.addEventListener("click", function () {
    setOpen(!header.classList.contains("nav-open"));
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && header.classList.contains("nav-open")) {
      setOpen(false);
      toggle.focus();
    }
  });
})();
