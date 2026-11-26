// Contact form: client-side validation (same rules as the server), prefilled service,
// and submission to the configured backend. Messages come from the page's i18n JSON.
(function () {
  "use strict";

  var form = document.getElementById("contact-form");
  if (!form) return;

  var i18nNode = document.getElementById("i18n");
  var t = i18nNode ? JSON.parse(i18nNode.textContent) : { errors: {}, generic: "", network: "", success: "", sending: "" };
  var cfg = window.XLANORA_CONFIG || { backend: "local", endpoint: "/api/contact" };
  var status = document.getElementById("form-status");
  var submit = form.querySelector('button[type="submit"]');
  // Allowed values come from the page's own dropdown, so the list lives in one place (build/content.py).
  var SERVICES = Array.prototype.map.call(form.elements.service.options, function (o) { return o.value; });

  // Prefill from ?service=slug (linked from service pages).
  var preset = new URLSearchParams(window.location.search).get("service");
  if (preset && SERVICES.indexOf(preset) !== -1) {
    form.elements.service.value = preset;
  }

  var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var PHONE = /^[0-9+\-\s()]{0,30}$/;

  function rules(values) {
    var errors = {};
    var name = values.name.trim();
    if (name.length < 2 || name.length > 80) errors.name = t.errors.name;
    if (values.email.length > 254 || !EMAIL.test(values.email)) errors.email = t.errors.email;
    if (values.phone && !PHONE.test(values.phone)) errors.phone = t.errors.phone;
    if (SERVICES.indexOf(values.service) === -1) errors.service = t.errors.service;
    var message = values.message.trim();
    if (message.length < 10 || message.length > 2000) errors.message = t.errors.message;
    return errors;
  }

  function readValues() {
    return {
      name: form.elements.name.value,
      email: form.elements.email.value.trim(),
      phone: form.elements.phone.value.trim(),
      service: form.elements.service.value,
      message: form.elements.message.value,
      website: form.elements.website.value
    };
  }

  function showErrors(errors) {
    ["name", "email", "phone", "service", "message"].forEach(function (field) {
      var input = form.elements[field];
      var box = document.getElementById(field + "-error");
      var message = errors[field] || "";
      if (box) box.textContent = message;
      if (input) input.setAttribute("aria-invalid", message ? "true" : "false");
    });
  }

  function setStatus(text, kind) {
    status.textContent = text;
    status.className = "form-status" + (kind ? " " + kind : "");
  }

  function sendLocal(values) {
    return fetch(cfg.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(values)
    });
  }

  function sendSupabase(values) {
    var body = {
      name: values.name.trim(),
      email: values.email,
      phone: values.phone || null,
      service: values.service,
      message: values.message.trim()
    };
    return fetch(cfg.supabaseUrl + "/rest/v1/contact_messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: cfg.supabaseAnonKey,
        Authorization: "Bearer " + ((window.XLANORA_AUTH && window.XLANORA_AUTH.token()) || cfg.supabaseAnonKey),
        Prefer: "return=minimal"
      },
      body: JSON.stringify(body)
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var values = readValues();

    // Honeypot filled: pretend success without sending anything.
    if (values.website) {
      form.reset();
      setStatus(t.success, "ok");
      return;
    }

    var errors = rules(values);
    showErrors(errors);
    if (Object.keys(errors).length) {
      setStatus(t.generic, "err");
      var first = form.querySelector('[aria-invalid="true"]');
      if (first) first.focus();
      return;
    }

    submit.disabled = true;
    setStatus(t.sending, "");

    var request = cfg.backend === "supabase" ? sendSupabase(values) : sendLocal(values);
    request
      .then(function (response) {
        if (response.status === 201 || response.status === 204) {
          form.reset();
          showErrors({});
          setStatus(t.success, "ok");
          return null;
        }
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (data && data.errors) showErrors(data.errors);
          setStatus(response.status === 400 ? t.generic : t.network, "err");
        });
      })
      .catch(function () {
        setStatus(t.network, "err");
      })
      .finally(function () {
        submit.disabled = false;
      });
  });
})();
