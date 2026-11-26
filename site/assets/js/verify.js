// E-mail verification for the local server version: the dashboard banner (with a resend button)
// and the verify page that opens the link from the e-mail. The Supabase version confirms through Supabase Auth.
(function () {
  "use strict";
  var cfg = window.XLANORA_CONFIG || {};
  var isSupabase = cfg.backend === "supabase";
  var lang = document.documentElement.lang === "ar" ? "ar" : "en";
  var i18nNode = document.getElementById("i18n");
  var copy = {};
  try { copy = (i18nNode && JSON.parse(i18nNode.textContent).rv) || {}; } catch (e) { copy = {}; }

  function $(id) { return document.getElementById(id); }
  function setText(node, text, kind) {
    if (!node) return;
    node.textContent = text || "";
    node.className = "form-status" + (kind === "ok" ? " is-ok" : kind === "error" ? " is-error" : "");
  }
  function readJson(res) {
    return res.text().then(function (text) { try { return text ? JSON.parse(text) : {}; } catch (e) { return {}; } });
  }
  function post(path, body) {
    return fetch(path, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {})
    }).then(function (res) { return readJson(res).then(function (data) { return { ok: res.ok, status: res.status, data: data }; }); });
  }

  // Verify page: the token comes from the link in the e-mail.
  if ($("vf-page") && !isSupabase) {
    var token = new URLSearchParams(window.location.search).get("token") || "";
    var result = $("vf-result");
    if (!token) { setText(result, copy.vf_invalid, "error"); return; }
    post("/api/auth/verify", { token: token }).then(function (res) {
      setText(result, res.ok ? copy.vf_done : copy.vf_invalid, res.ok ? "ok" : "error");
    }).catch(function () { setText(result, copy.vf_invalid, "error"); });
    return;
  }
  if ($("vf-page") && isSupabase) {
    setText($("vf-result"), copy.vf_sb_done, "ok");
    return;
  }

  // Dashboard banner: shown only to signed-in accounts whose e-mail is not confirmed yet.
  var banner = $("vf-banner");
  if (!banner || isSupabase) return;
  fetch("/api/me", { credentials: "same-origin" }).then(function (res) {
    return res.ok ? readJson(res) : null;
  }).then(function (data) {
    var user = data && (data.user || data);
    if (!user || user.email_verified !== false) return;
    banner.hidden = false;
    var button = $("vf-resend");
    if (!button) return;
    button.addEventListener("click", function () {
      button.disabled = true;
      post("/api/auth/resend-verification", {}).then(function (res) {
        button.disabled = false;
        if (res.status === 202) setText($("vf-status"), copy.vf_sent, "ok");
        else if (res.ok && res.data && res.data.queued === 0) setText($("vf-status"), copy.vf_wait, "error");
        else setText($("vf-status"), copy.vf_wait, "error");
      }).catch(function () { button.disabled = false; });
    });
  }).catch(function () { /* no banner if the check fails */ });
})();
