// Account details on profile.html: full name, and a headline for freelancers.
// The photo is handled by profile.js. Two backends, one behaviour:
//   local    -> POST /api/me/profile (the server validates the name and headline)
//   supabase -> PATCH profiles (row-level security and the column grant decide what may change)
// Written with textContent only. No inline scripts.
(function () {
  "use strict";

  var cfg = window.XLANORA_CONFIG || { backend: "local" };
  var isSupabase = cfg.backend === "supabase";
  var i18nNode = document.getElementById("i18n");
  var form = document.getElementById("profile-form");
  if (!i18nNode || !form || !window.XLANORA_AUTH) return;
  var t = JSON.parse(i18nNode.textContent);
  var s = t.pr || {};
  var base = "/" + (t.locale || "en") + "/";
  var current = null;  // the signed-in user, as last shown or saved

  function $(id) { return document.getElementById(id); }
  function setStatus(text, kind) {
    var node = $("pp-status");
    node.textContent = text || "";
    node.className = "form-status" + (kind ? " is-" + kind : "");
  }
  function readBody(res) {
    return res.text().then(function (text) {
      try { return text ? JSON.parse(text) : null; } catch (e) { return null; }
    });
  }

  // ---------- profile completion (freelancers): four steps, counted from the same data as the rest of the site ----------
  var pc = t.pc || {};
  function fill(template, values) {
    return String(template).replace(/\{(\w+)\}/g, function (match, key) {
      return values[key] !== undefined ? String(values[key]) : match;
    });
  }
  function mk(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function countLocal(path, key) {
    return fetch(path, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (res) { return res.ok ? res.json() : {}; })
      .then(function (data) { return Array.isArray(data[key]) ? data[key].length : 0; })
      .catch(function () { return 0; });
  }
  function countSupabase(path) {
    var token = window.XLANORA_AUTH.token();
    return fetch(cfg.supabaseUrl + "/rest/v1/" + path, {
      headers: { apikey: cfg.supabaseAnonKey, Authorization: "Bearer " + (token || cfg.supabaseAnonKey), Accept: "application/json" }
    }).then(function (res) { return res.ok ? res.json() : []; })
      .then(function (rows) { return Array.isArray(rows) ? rows.length : 0; })
      .catch(function () { return 0; });
  }
  function setStep(li, label, done, href) {
    li.className = "pc-step" + (done ? " is-done" : "");
    var go = mk("a", "text-link", pc.pc_go);
    go.href = href;
    li.replaceChildren(mk("span", "pc-step-label", label), mk("span", "pc-step-state", done ? pc.pc_done : pc.pc_todo), go);
  }
  function renderCompletion(user) {
    var panel = $("pc-panel");
    if (!panel) return;
    if (user.role !== "freelancer") { panel.hidden = true; return; }
    panel.hidden = false;
    var uid = encodeURIComponent(user.id);
    var photoDone = !!user.avatar_url;
    var headlineDone = !!String(user.headline || "").trim();
    Promise.all([
      isSupabase ? countSupabase("services?select=id&provider_id=eq." + uid + "&active=eq.true") : countLocal("/api/my/services", "services"),
      isSupabase ? countSupabase("portfolio_items?select=id&provider_id=eq." + uid + "&active=eq.true") : countLocal("/api/my/portfolio", "items")
    ]).then(function (counts) {
      var serviceDone = counts[0] > 0;
      var portfolioDone = counts[1] > 0;
      setStep($("pc-photo"), pc.pc_photo, photoDone, "#profile-panel");
      setStep($("pc-headline"), pc.pc_headline, headlineDone, "#profile-form");
      setStep($("pc-service"), pc.pc_service, serviceDone, base + "dashboard.html");
      setStep($("pc-portfolio"), pc.pc_portfolio, portfolioDone, base + "portfolio.html");
      var done = [photoDone, headlineDone, serviceDone, portfolioDone].filter(Boolean).length;
      $("pc-bar").style.width = (done / 4 * 100) + "%";
      panel.querySelector(".pc-progress").setAttribute("aria-valuenow", String(done));
      $("pc-count").textContent = fill(pc.pc_count, { done: done });
    });
  }

  function show(user) {
    current = user;
    var isFreelancer = user.role === "freelancer";
    form.elements.full_name.value = user.full_name || "";
    form.elements.headline.value = user.headline || "";
    $("pp-headline-field").hidden = !isFreelancer;
    $("pp-email").textContent = user.email || "";
    $("pp-role").textContent = isFreelancer ? s.profile_role_freelancer : s.profile_role_client;
    var pub = $("pp-public");
    pub.hidden = !isFreelancer;
    if (isFreelancer) pub.href = base + "freelancer.html?id=" + encodeURIComponent(user.id);
    $("pp-gate").hidden = true;
    $("pp-body").hidden = false;
    renderCompletion(user);
  }

  function saveLocal(body) {
    return fetch("/api/me/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body)
    }).then(function (res) {
      return readBody(res).then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
    });
  }

  function saveSupabase(body) {
    var token = window.XLANORA_AUTH.token();
    return fetch(cfg.supabaseUrl + "/rest/v1/profiles?id=eq." + encodeURIComponent(current.id), {
      method: "PATCH",
      headers: {
        apikey: cfg.supabaseAnonKey,
        Authorization: "Bearer " + (token || cfg.supabaseAnonKey),
        "Content-Type": "application/json",
        Prefer: "return=representation"
      },
      body: JSON.stringify(body)
    }).then(function (res) {
      return readBody(res).then(function (rows) {
        // A write that matches no row is reported as success by PATCH, so check that a row came back.
        var ok = res.ok && Array.isArray(rows) && rows.length === 1;
        return { ok: ok, status: ok ? 200 : res.status || 0, data: {} };
      });
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var name = form.elements.full_name.value.trim();
    var isFreelancer = current && current.role === "freelancer";
    var headline = isFreelancer ? form.elements.headline.value.trim() : (current.headline || "");
    if (name.length < 2 || name.length > 80) { setStatus(s.profile_err_name, "error"); return; }
    if (headline.length > 160) { setStatus(s.profile_err_headline, "error"); return; }
    var body = { full_name: name, headline: headline };
    var button = form.querySelector("button[type=submit]");
    button.disabled = true;
    setStatus("", "");
    var request = isSupabase ? saveSupabase(body) : saveLocal(body);
    request.then(function (res) {
      button.disabled = false;
      if (res.ok) {
        current.full_name = name;
        current.headline = headline;
        var card = $("profile-name");
        if (card) card.textContent = name;
        setStatus(s.profile_details_saved, "ok");
        renderCompletion(current);
        return;
      }
      if (res.status === 400 && res.data && (res.data.full_name || res.data.headline)) {
        setStatus(res.data.headline ? s.profile_err_headline : s.profile_err_name, "error");
        return;
      }
      setStatus(s.profile_err_details, "error");
    }).catch(function () {
      button.disabled = false;
      setStatus(s.profile_err_details, "error");
    });
  });

  window.XLANORA_AUTH.me().then(function (res) {
    if (res.status === 200 && res.data && res.data.user) show(res.data.user);
  }).catch(function () { /* signed out: the page keeps its sign-in message */ });
})();
