// Accounts for XLANORA: register, sign in, sign out, dashboard, and the header link.
// One API layer, two backends:
//   backend "local"    -> /api/auth/* on the Python server (HttpOnly cookie session)
//   backend "supabase" -> Supabase Auth + REST (token kept in localStorage, RLS enforces access)
// Everything shown on screen is written with textContent, never innerHTML.
(function () {
  "use strict";

  var cfg = window.XLANORA_CONFIG || { backend: "local" };
  var isSupabase = cfg.backend === "supabase";
  var TOKEN_KEY = "xlanora_sb_token";
  var page = document.body.getAttribute("data-page") || "";
  var lang = document.documentElement.lang === "ar" ? "ar" : "en";
  var base = "/" + lang + "/";
  var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  var i18nNode = document.getElementById("i18n");
  var t = i18nNode ? JSON.parse(i18nNode.textContent) : {};

  // ---------- token storage (Supabase mode only) ----------
  function getToken() {
    try { return window.localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
  }
  function setToken(token) {
    try { window.localStorage.setItem(TOKEN_KEY, token); } catch (e) { /* storage blocked */ }
  }
  function clearToken() {
    try { window.localStorage.removeItem(TOKEN_KEY); } catch (e) { /* storage blocked */ }
  }

  // ---------- HTTP helpers ----------
  function readJson(res) {
    return res.json().catch(function () { return {}; });
  }

  function localRequest(method, path, payload) {
    var options = { method: method, headers: { Accept: "application/json" }, credentials: "same-origin" };
    if (payload !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    return fetch(path, options).then(function (res) {
      return readJson(res).then(function (data) { return { status: res.status, data: data }; });
    });
  }

  function sbHeaders(token) {
    return {
      apikey: cfg.supabaseAnonKey,
      Authorization: "Bearer " + (token || cfg.supabaseAnonKey),
      "Content-Type": "application/json"
    };
  }

  function sbSignup(payload) {
    return fetch(cfg.supabaseUrl + "/auth/v1/signup", {
      method: "POST",
      headers: sbHeaders(""),
      body: JSON.stringify({
        email: payload.email,
        password: payload.password,
        data: { full_name: payload.full_name, role: payload.role, specialty: payload.specialty || null }
      })
    }).then(function (res) {
      return readJson(res).then(function (d) {
        if (res.status === 429) return { status: 429, data: {} };
        if (!res.ok) {
          var msg = String(d.msg || d.message || d.error_description || "").toLowerCase();
          if (msg.indexOf("already") !== -1 || msg.indexOf("registered") !== -1) {
            return { status: 409, data: { errors: { email: "email_taken" } } };
          }
          return { status: 400, data: { errors: { form: "generic" } } };
        }
        if (!d.access_token) return { status: 202, data: { confirm: true } }; // email confirmation is on
        setToken(d.access_token);
        return sbMe().then(function (r) { return { status: 201, data: r.data }; });
      });
    });
  }

  function sbLogin(payload) {
    return fetch(cfg.supabaseUrl + "/auth/v1/token?grant_type=password", {
      method: "POST",
      headers: sbHeaders(""),
      body: JSON.stringify({ email: payload.email, password: payload.password })
    }).then(function (res) {
      return readJson(res).then(function (d) {
        if (res.status === 429) return { status: 429, data: {} };
        if (!res.ok || !d.access_token) return { status: 401, data: { errors: { form: "invalid_credentials" } } };
        setToken(d.access_token);
        return sbMe();
      });
    });
  }

  function sbMe() {
    var token = getToken();
    if (!token) return Promise.resolve({ status: 401, data: {} });
    return fetch(cfg.supabaseUrl + "/auth/v1/user", { headers: sbHeaders(token) }).then(function (res) {
      if (!res.ok) { clearToken(); return { status: 401, data: {} }; }
      return readJson(res).then(function (authUser) {
        return fetch(cfg.supabaseUrl + "/rest/v1/profiles?select=id,full_name,role,specialty,is_admin,avatar_url,headline&id=eq." + encodeURIComponent(authUser.id), {
          headers: sbHeaders(token)
        }).then(readJson).then(function (rows) {
          var profile = Array.isArray(rows) ? rows[0] : null;
          if (!profile) return { status: 401, data: {} };
          return {
            status: 200,
            data: { user: { id: profile.id, email: authUser.email, full_name: profile.full_name, role: profile.role, specialty: profile.specialty, is_admin: profile.is_admin === true, avatar_url: profile.avatar_url || null, headline: profile.headline || "" } }
          };
        });
      });
    });
  }

  // ---------- the API used by every page ----------
  var api = {
    register: function (payload) {
      return isSupabase ? sbSignup(payload) : localRequest("POST", "/api/auth/register", payload);
    },
    login: function (payload) {
      return isSupabase ? sbLogin(payload) : localRequest("POST", "/api/auth/login", payload);
    },
    logout: function () {
      if (!isSupabase) return localRequest("POST", "/api/auth/logout", {});
      var token = getToken();
      clearToken();
      if (token) {
        fetch(cfg.supabaseUrl + "/auth/v1/logout", { method: "POST", headers: sbHeaders(token) }).catch(function () {});
      }
      return Promise.resolve({ status: 200, data: {} });
    },
    me: function () {
      return isSupabase ? sbMe() : localRequest("GET", "/api/me");
    },
    requests: function () {
      if (!isSupabase) return localRequest("GET", "/api/requests");
      var token = getToken();
      if (!token) return Promise.resolve({ status: 401, data: {} });
      var cols = "id,name,email,phone,service,message,created_at";
      return fetch(cfg.supabaseUrl + "/rest/v1/contact_messages?select=" + cols + "&order=created_at.desc&limit=100", {
        headers: sbHeaders(token)
      }).then(function (res) {
        if (res.status === 401 || res.status === 403) return { status: 401, data: {} };
        return readJson(res).then(function (rows) {
          return { status: res.ok ? 200 : 500, data: { requests: Array.isArray(rows) ? rows : [] } };
        });
      });
    }
  };

  // ---------- photos (Supabase only) ----------
  // Files go to the public bucket "photos" under <user id>/<random name>. The bucket and the database
  // (migrations 009 and 016) decide who may write: only the owner, only photos up to 10 MB and videos up to 50 MB.
  var PHOTO_BUCKET = "photos";
  var PHOTO_EXT = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"
  };
  function photoPrefix() { return cfg.supabaseUrl + "/storage/v1/object/public/" + PHOTO_BUCKET + "/"; }
  function photoHeaders(token) {
    return { apikey: cfg.supabaseAnonKey, Authorization: "Bearer " + token };
  }
  function randomHex() {
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    return Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }
  // Uploads one image and resolves to { ok, url } (the public link) or { ok: false, status }.
  function uploadPhoto(ownerId, file) {
    var token = getToken();
    var ext = PHOTO_EXT[file && file.type];
    if (!token || !ext || !ownerId) return Promise.resolve({ ok: false, status: 401 });
    var path = ownerId + "/" + randomHex() + "." + ext;
    var headers = photoHeaders(token);
    headers["Content-Type"] = file.type;
    headers["x-upsert"] = "false";
    return fetch(cfg.supabaseUrl + "/storage/v1/object/" + PHOTO_BUCKET + "/" + path, {
      method: "POST", headers: headers, body: file
    }).then(function (res) {
      return res.ok ? { ok: true, url: photoPrefix() + path } : { ok: false, status: res.status };
    }).catch(function () { return { ok: false, status: 0 }; });
  }
  // Removes a photo this site stored. Links to anything else are left alone.
  function deletePhoto(url) {
    var token = getToken();
    if (!token || typeof url !== "string" || url.indexOf(photoPrefix()) !== 0) return Promise.resolve(false);
    return fetch(cfg.supabaseUrl + "/storage/v1/object/" + PHOTO_BUCKET + "/" + url.slice(photoPrefix().length), {
      method: "DELETE", headers: photoHeaders(token)
    }).then(function (res) { return res.ok; }).catch(function () { return false; });
  }
  // Sets the signed-in user's profile picture. Row-level security and a trigger check the link.
  function setAvatar(userId, url) {
    var token = getToken();
    if (!token || !userId) return Promise.resolve({ ok: false, status: 401 });
    var headers = photoHeaders(token);
    headers["Content-Type"] = "application/json";
    headers.Prefer = "return=minimal";
    return fetch(cfg.supabaseUrl + "/rest/v1/profiles?id=eq." + encodeURIComponent(userId), {
      method: "PATCH", headers: headers, body: JSON.stringify({ avatar_url: url })
    }).then(function (res) { return { ok: res.ok, status: res.status }; })
      .catch(function () { return { ok: false, status: 0 }; });
  }

  // The administrator's inbox. Local: the server checks the administrator flag. Supabase: RLS returns
  // every message only to an administrator (migration 008); anyone else gets no rows.
  api.inbox = function () {
    if (!isSupabase) return localRequest("GET", "/api/admin/contacts");
    var token = getToken();
    if (!token) return Promise.resolve({ status: 401, data: {} });
    var cols = "id,name,email,phone,service,message,created_at";
    return fetch(cfg.supabaseUrl + "/rest/v1/contact_messages?select=" + cols + "&order=created_at.desc&limit=200", {
      headers: sbHeaders(token)
    }).then(function (res) {
      if (res.status === 401 || res.status === 403) return { status: 403, data: {} };
      return readJson(res).then(function (rows) {
        return { status: res.ok ? 200 : 500, data: { messages: Array.isArray(rows) ? rows : [] } };
      });
    });
  };

  // Shared with contact.js so Supabase submissions carry the signed-in user's token.
  window.XLANORA_AUTH = {
    token: getToken,
    me: function () { return api.me(); },
    inbox: function () { return api.inbox(); },
    uploadPhoto: uploadPhoto,
    deletePhoto: deletePhoto,
    setAvatar: setAvatar
  };

  // ---------- small helpers ----------
  function setStatus(el, text, kind) {
    if (!el) return;
    el.textContent = text;
    el.className = "form-status" + (kind ? " " + kind : "");
  }

  function setFieldError(field, message) {
    var box = document.getElementById(field + "-error");
    if (box) box.textContent = message || "";
    var input = document.getElementById(field);
    if (input) input.setAttribute("aria-invalid", message ? "true" : "false");
  }

  function clearErrors(fields) {
    fields.forEach(function (f) { setFieldError(f, ""); });
  }

  function showServerErrors(errors, fields) {
    var first = null;
    Object.keys(errors || {}).forEach(function (key) {
      var msg = errors[key] === "email_taken" ? t.email_taken : (t.errors && t.errors[key]) || t.generic;
      if (fields.indexOf(key) !== -1) {
        setFieldError(key, msg);
        if (!first) first = document.getElementById(key);
      }
    });
    if (first) first.focus();
    return first;
  }

  function goTo(path) {
    window.location.href = base + path;
  }

  // The header follows the account: sign-in or dashboard link, profile and sign-out when signed in,
  // and the Portfolio link only for freelancers.
  function updateHeader(user) {
    var signedIn = !!user;
    document.querySelectorAll(".nav-auth").forEach(function (link) {
      if (signedIn) {
        link.textContent = link.getAttribute("data-dashboard");
        link.setAttribute("href", link.getAttribute("data-dashboard-href"));
      } else {
        link.textContent = link.getAttribute("data-signin");
        link.setAttribute("href", base + "login.html");
      }
    });
    document.querySelectorAll(".nav-signed-in").forEach(function (node) { node.hidden = !signedIn; });
    document.querySelectorAll(".nav-freelancer").forEach(function (node) {
      node.hidden = !(signedIn && user.role === "freelancer");
    });
    document.querySelectorAll(".nav-client").forEach(function (node) {
      node.hidden = !(signedIn && user.role === "client");
    });
  }

  function bindSignOut() {
    var button = document.getElementById("nav-signout");
    if (!button || button.getAttribute("data-bound") === "1") return;
    button.setAttribute("data-bound", "1");
    button.addEventListener("click", function () {
      button.disabled = true;
      Promise.resolve()
        .then(function () { return api.logout(); })
        .catch(function () { /* the local session is cleared either way */ })
        .then(function () { goTo("index.html"); });
    });
  }

  // ---------- register page ----------
  function initRegister() {
    var form = document.getElementById("register-form");
    var status = document.getElementById("form-status");
    var wrap = document.getElementById("specialty-wrap");
    var submit = form.querySelector('button[type="submit"]');
    var FIELDS = ["name", "email", "password", "role", "specialty"];
    // Allowed specialties come from the dropdown itself (build/content_auth.py feeds it).
    var SPECIALTIES = Array.prototype.map.call(form.elements.specialty.options, function (o) { return o.value; }).filter(Boolean);

    function selectedRole() {
      var checked = form.querySelector('input[name="role"]:checked');
      return checked ? checked.value : "client";
    }

    function syncSpecialty() {
      var freelancer = selectedRole() === "freelancer";
      wrap.hidden = !freelancer;
      if (!freelancer) form.elements.specialty.value = "";
    }

    form.querySelectorAll('input[name="role"]').forEach(function (radio) {
      radio.addEventListener("change", syncSpecialty);
    });
    syncSpecialty();

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearErrors(FIELDS);
      var values = {
        full_name: form.elements.full_name.value.trim(),
        email: form.elements.email.value.trim().toLowerCase(),
        password: form.elements.password.value,
        role: selectedRole(),
        specialty: form.elements.specialty.value
      };

      var errors = {};
      if (values.full_name.length < 2 || values.full_name.length > 80) errors.name = t.errors.full_name;
      if (values.email.length > 254 || !EMAIL.test(values.email)) errors.email = t.errors.email;
      if (values.password.length < 8 || values.password.length > 128) errors.password = t.errors.password;
      if (values.role === "freelancer" && SPECIALTIES.indexOf(values.specialty) === -1) errors.specialty = t.errors.specialty;

      if (Object.keys(errors).length) {
        Object.keys(errors).forEach(function (k) { setFieldError(k, errors[k]); });
        setStatus(status, t.generic, "err");
        form.querySelector('[aria-invalid="true"]').focus();
        return;
      }

      var payload = {
        full_name: values.full_name,
        email: values.email,
        password: values.password,
        role: values.role,
        specialty: values.role === "freelancer" ? values.specialty : ""
      };
      submit.disabled = true;
      setStatus(status, t.submitting, "");
      api.register(payload).then(function (res) {
        if (res.status === 201) {
          setStatus(status, t.success_register, "ok");
          setTimeout(function () { goTo("dashboard.html"); }, 700);
        } else if (res.status === 202) {
          setStatus(status, t.success_register, "ok");
        } else if (res.status === 409) {
          setFieldError("email", t.email_taken);
          setStatus(status, t.email_taken, "err");
        } else if (res.status === 429) {
          setStatus(status, t.rate, "err");
        } else if (res.status === 400 && res.data && res.data.errors) {
          showServerErrors(res.data.errors, FIELDS);
          setStatus(status, t.generic, "err");
        } else {
          setStatus(status, t.network, "err");
        }
      }).catch(function () {
        setStatus(status, t.network, "err");
      }).finally(function () {
        submit.disabled = false;
      });
    });
  }

  // ---------- login page ----------
  function initLogin() {
    var form = document.getElementById("login-form");
    var status = document.getElementById("form-status");
    var submit = form.querySelector('button[type="submit"]');
    var FIELDS = ["email", "password"];

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearErrors(FIELDS);
      var email = form.elements.email.value.trim().toLowerCase();
      var password = form.elements.password.value;
      var errors = {};
      if (email.length > 254 || !EMAIL.test(email)) errors.email = t.errors.email;
      if (!password) errors.password = t.generic;
      if (Object.keys(errors).length) {
        Object.keys(errors).forEach(function (k) { setFieldError(k, errors[k]); });
        setStatus(status, t.generic, "err");
        form.querySelector('[aria-invalid="true"]').focus();
        return;
      }
      submit.disabled = true;
      setStatus(status, t.submitting, "");
      api.login({ email: email, password: password }).then(function (res) {
        if (res.status === 200) {
          setStatus(status, t.success_login, "ok");
          setTimeout(function () { goTo("dashboard.html"); }, 500);
        } else if (res.status === 429) {
          setStatus(status, t.rate, "err");
        } else if (res.status === 401) {
          setStatus(status, t.invalid_login, "err");
        } else {
          setStatus(status, t.network, "err");
        }
      }).catch(function () {
        setStatus(status, t.network, "err");
      }).finally(function () {
        submit.disabled = false;
      });
    });
  }

  // ---------- dashboard ----------
  function serviceLabel(slug) {
    if (!slug) return "—";
    if (slug === "unsure") return t.not_sure;
    return (t.specialties && t.specialties[slug]) || slug;
  }

  function formatDate(value) {
    var d = new Date(value);
    if (isNaN(d.getTime())) return value || "";
    return d.toLocaleDateString(lang === "ar" ? "ar-SA" : "en-GB", { year: "numeric", month: "short", day: "numeric" });
  }

  function requestCard(req, role) {
    var article = document.createElement("article");
    article.className = "request-card";

    var title = document.createElement("h3");
    title.textContent = serviceLabel(req.service);
    article.appendChild(title);

    var message = document.createElement("p");
    message.textContent = req.message || "";
    article.appendChild(message);

    var meta = document.createElement("dl");
    meta.className = "request-meta";
    var rows = [];
    if (role === "freelancer") {
      rows.push([t.contact, req.name + " · " + req.email + (req.phone ? " · " + req.phone : "")]);
    }
    rows.push([t.received, formatDate(req.created_at)]);
    rows.forEach(function (pair) {
      var dt = document.createElement("dt");
      dt.textContent = pair[0];
      var dd = document.createElement("dd");
      dd.textContent = pair[1];
      meta.appendChild(dt);
      meta.appendChild(dd);
    });
    article.appendChild(meta);
    return article;
  }

  function initDashboard(me) {
    var who = document.getElementById("dash-who");
    var lead = document.getElementById("dash-lead");
    var status = document.getElementById("dash-status");
    var list = document.getElementById("requests");
    var logout = document.getElementById("logout-btn");

    if (me.status !== 200) {
      status.textContent = t.go_signin + " ";
      var link = document.createElement("a");
      link.href = base + "login.html";
      link.textContent = t.signin;
      status.appendChild(link);
      return;
    }

    var user = me.data.user;
    var roleName = user.role === "client" ? t.role_client : t.role_freelancer;
    who.textContent = t.signed_as + " " + user.full_name + " (" + roleName + ")";
    lead.textContent = user.role === "client"
      ? t.lead_client
      : t.lead_freelancer.replace("{specialty}", serviceLabel(user.specialty));

    logout.hidden = false;
    logout.addEventListener("click", function () {
      logout.disabled = true;
      api.logout().then(function () { window.location.href = base; });
    });

    setStatus(status, t.loading, "");
    api.requests().then(function (res) {
      if (res.status === 401) {
        setStatus(status, t.go_signin, "err");
        return;
      }
      if (res.status !== 200) {
        setStatus(status, t.network, "err");
        return;
      }
      var items = (res.data && res.data.requests) || [];
      if (!items.length) {
        setStatus(status, user.role === "client" ? t.empty_client : t.empty_freelancer, "");
        return;
      }
      setStatus(status, "", "");
      items.forEach(function (req) { list.appendChild(requestCard(req, user.role)); });
    }).catch(function () {
      setStatus(status, t.network, "err");
    });
  }

  // ---------- start ----------
  api.me().then(function (me) {
    var user = me.status === 200 && me.data && me.data.user ? me.data.user : null;
    updateHeader(user);
    bindSignOut();
    if (page === "login" && user) return goTo("dashboard.html");
    if (page === "register" && user) return goTo("dashboard.html");
    if (page === "dashboard") return initDashboard(me);
  }).catch(function () {
    updateHeader(null);
    bindSignOut();
    if (page === "dashboard") initDashboard({ status: 401 });
  });

  if (page === "register") initRegister();
  if (page === "login") initLogin();
})();
