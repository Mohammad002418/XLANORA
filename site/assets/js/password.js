// Change-password form on the signed-in user's own profile page only.
// Shown only to a signed-in user. The server (local) or Supabase Auth changes the password of the account
// that is signed in on this browser; nobody can change another account's password from here.
// Everything on screen is written with textContent. No inline scripts.
(function () {
  "use strict";

  var form = document.getElementById("password-form");
  var section = document.getElementById("password-section");
  if (!form || !section || !window.XLANORA_AUTH) return;

  var cfg = window.XLANORA_CONFIG || { backend: "local" };
  var isSupabase = cfg.backend === "supabase";
  var i18nNode = document.getElementById("i18n");
  var t = i18nNode ? JSON.parse(i18nNode.textContent) : {};
  var s = t.pw || {};
  var status = document.getElementById("password-status");
  var ME = null;

  function setStatus(text, kind) {
    status.textContent = text || "";
    status.className = "form-status" + (kind ? " " + kind : "");
  }
  function readBody(res) {
    return res.text().then(function (text) {
      try { return text ? JSON.parse(text) : null; } catch (e) { return null; }
    });
  }
  function localChange(current, next) {
    return fetch("/api/auth/password", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ current_password: current, new_password: next })
    }).then(function (res) {
      return readBody(res).then(function (data) { return { ok: res.ok, data: data }; });
    });
  }
  function supabaseChange(current, next) {
    // Check the current password by signing in again, then set the new one for the signed-in account.
    return fetch(cfg.supabaseUrl + "/auth/v1/token?grant_type=password", {
      method: "POST",
      headers: { apikey: cfg.supabaseAnonKey, "Content-Type": "application/json" },
      body: JSON.stringify({ email: ME.email, password: current })
    }).then(function (res) {
      if (!res.ok) return { ok: false, data: { code: "wrong_password" } };
      return fetch(cfg.supabaseUrl + "/auth/v1/user", {
        method: "PUT",
        headers: {
          apikey: cfg.supabaseAnonKey,
          Authorization: "Bearer " + (window.XLANORA_AUTH.token() || cfg.supabaseAnonKey),
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ password: next })
      }).then(function (r) { return readBody(r).then(function (d) { return { ok: r.ok, data: d }; }); });
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var current = form.current_password.value;
    var next = form.new_password.value;
    if (!current || next.length < 8 || next.length > 128) {
      setStatus(s.bk_password_invalid || "", "error");
      return;
    }
    setStatus("");
    var call = isSupabase ? supabaseChange(current, next) : localChange(current, next);
    call.then(function (res) {
      if (res.ok) {
        form.reset();
        setStatus(s.bk_password_saved || "", "success");
        return;
      }
      var code = (res.data && res.data.code) || "";
      var errors = (res.data && res.data.errors) || {};
      if (code === "wrong_password" || errors.current_password === "wrong_password") {
        setStatus(s.bk_password_wrong || "", "error");
      } else if (errors.new_password) {
        setStatus(s.bk_password_invalid || "", "error");
      } else {
        setStatus(s.bk_err_generic || "", "error");
      }
    }).catch(function () {
      setStatus(s.bk_err_network || "", "error");
    });
  });

  // Only a signed-in user sees the form, and only on their own profile page.
  window.XLANORA_AUTH.me().then(function (res) {
    if (res.status === 200 && res.data && res.data.user) {
      ME = res.data.user;
      section.hidden = false;
    }
  }).catch(function () { /* signed out or offline: the form stays hidden */ });
})();
