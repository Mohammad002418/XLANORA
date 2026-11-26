// Freelancer pages: the directory (services.html), one freelancer's profile (freelancer.html), and the
// clients' saved list (wishlist.html). Two backends, one behaviour (the same switch as auth.js and portfolio.js):
//   local    -> /api/freelancers, /api/freelancers/<id>, /api/wishlist on the Python server
//   supabase -> freelancer_profiles view, services, portfolio_items and wishlist tables (RLS decides)
// Everything shown is written with textContent or DOM methods. No inline scripts.
(function () {
  "use strict";

  var cfg = window.XLANORA_CONFIG || { backend: "local" };
  var isSupabase = cfg.backend === "supabase";
  var i18nNode = document.getElementById("i18n");
  if (!i18nNode) return;
  var t = JSON.parse(i18nNode.textContent);
  var s = Object.assign({}, t.fl || {}, t.wl || {}, t.rv || {});
  var pf = t.pf || {};
  var specialties = t.specialties || {};
  var base = "/" + (t.locale || "en") + "/";
  var page = document.body.getAttribute("data-page") || "";
  var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  var NUMERIC_ID = /^[0-9]{1,12}$/;
  var IMAGE_PATH = /^\/uploads\/[a-f0-9]{32}\.(jpg|png|webp|mp4|webm|mov)$/;

  var viewer = null;     // the signed-in client, or null
  var saved = {};        // ids of the freelancers this client saved, as strings
  var readyPromise = null;
  var reviewSaved = false; // true after this visit's review was saved: the form stays with its message

  function $(id) { return document.getElementById(id); }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function setStatus(node, text, kind) {
    if (!node) return;
    node.textContent = text || "";
    node.className = "form-status" + (kind ? " is-" + kind : "");
  }
  function statusNode() { return $("fl-status") || $("wl-status") || $("fp-status"); }
  function fill(template, values) {
    return String(template).replace(/\{(\w+)\}/g, function (match, key) {
      return values[key] !== undefined ? String(values[key]) : match;
    });
  }
  function safeLink(url) {
    return typeof url === "string" && url.indexOf("https://") === 0 ? url : "";
  }
  function imageSource(url) {
    if (typeof url === "string" && IMAGE_PATH.test(url)) return url;
    return safeLink(url);
  }
  // Characters with a meaning in PostgREST filters or in LIKE patterns are removed from user text.
  function cleanQuery(text) {
    return String(text || "").replace(/[,()*%_"\\]/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);
  }
  function readBody(res) {
    return res.text().then(function (text) {
      try { return text ? JSON.parse(text) : null; } catch (e) { return null; }
    });
  }
  // Public reads. Supabase reads use the anonymous key: the view and the public tables allow them.
  function getJson(url, supabase) {
    var options = { headers: { Accept: "application/json" } };
    if (supabase) {
      options.headers.apikey = cfg.supabaseAnonKey;
      options.headers.Authorization = "Bearer " + cfg.supabaseAnonKey;
      url = cfg.supabaseUrl + "/rest/v1/" + url;
    } else {
      options.credentials = "same-origin";
    }
    return fetch(url, options).then(function (res) {
      return readBody(res).then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
    });
  }
  // Signed-in Supabase calls (the client's own wishlist) carry the user's token, so RLS applies to them.
  function sbAuthed(method, path, body) {
    var token = window.XLANORA_AUTH ? window.XLANORA_AUTH.token() : null;
    var options = {
      method: method,
      headers: { apikey: cfg.supabaseAnonKey, Authorization: "Bearer " + (token || cfg.supabaseAnonKey), "Content-Type": "application/json" }
    };
    if (body !== undefined) options.body = JSON.stringify(body);
    return fetch(cfg.supabaseUrl + "/rest/v1/" + path, options).then(function (res) {
      return readBody(res).then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
    });
  }
  function localWrite(method, path, body) {
    var options = { method: method, headers: { Accept: "application/json" }, credentials: "same-origin" };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(path, options).then(function (res) {
      return readBody(res).then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
    });
  }
  function priceText(value) { return fill(s.fl_price, { price: value }); }
  function starText(rating) {
    var n = Math.round(Number(rating) || 0);
    return new Array(n + 1).join("\u2605") + new Array(6 - n).join("\u2606");
  }
  function dateText(value) {
    var d = new Date(value);
    return isNaN(d.getTime()) ? "" : d.toLocaleDateString(t.locale === "ar" ? "ar" : "en", { year: "numeric", month: "short", day: "numeric" });
  }
  function ratingLine(rating_avg, rating_count) {
    var count = Number(rating_count) || 0;
    if (!count) return s.rv_new;
    return fill(s.rv_card, { rating: Number(rating_avg).toFixed(1), count: count });
  }
  function countText(count) {
    return count === 1 ? s.fl_services_one : fill(s.fl_services_count, { count: count });
  }

  function initialNode(name) {
    var node = el("span", "avatar avatar-initial", String(name || "").trim().charAt(0).toUpperCase());
    node.setAttribute("aria-hidden", "true");
    return node;
  }
  function avatarNode(url, name) {
    var src = imageSource(url);
    if (!src) return initialNode(name);
    var img = document.createElement("img");
    img.className = "avatar";
    img.alt = "";
    img.width = 72;
    img.height = 72;
    img.loading = "lazy";
    img.decoding = "async";
    img.referrerPolicy = "no-referrer";
    img.src = src;
    img.addEventListener("error", function () { img.replaceWith(initialNode(name)); });
    return img;
  }

  // ---------- who is viewing, and which freelancers they saved ----------
  function loadViewer() {
    if (!window.XLANORA_AUTH) return Promise.resolve(null);
    return window.XLANORA_AUTH.me().then(function (res) {
      var user = res.status === 200 && res.data && res.data.user ? res.data.user : null;
      return user && user.role === "client" ? user : null;
    }).catch(function () { return null; });
  }
  function loadSaved(user) {
    var request = isSupabase
      ? sbAuthed("GET", "wishlist?select=freelancer_id&client_id=eq." + encodeURIComponent(user.id))
          .then(function (r) { return (Array.isArray(r.data) ? r.data : []).map(function (row) { return String(row.freelancer_id); }); })
      : getJson("/api/wishlist").then(function (r) { return ((r.data && r.data.items) || []).map(function (i) { return String(i.id); }); });
    return request.catch(function () { return []; }).then(function (ids) {
      saved = {};
      ids.forEach(function (id) { saved[id] = true; });
    });
  }
  function whenReady() {
    if (!readyPromise) {
      readyPromise = loadViewer().then(function (user) {
        viewer = user;
        return user ? loadSaved(user) : null;
      });
    }
    return readyPromise;
  }
  function setSaved(user, id, wantSaved) {
    if (isSupabase) {
      return wantSaved
        ? sbAuthed("POST", "wishlist", { client_id: user.id, freelancer_id: id })
        : sbAuthed("DELETE", "wishlist?client_id=eq." + encodeURIComponent(user.id) + "&freelancer_id=eq." + encodeURIComponent(id));
    }
    return wantSaved
      ? localWrite("POST", "/api/wishlist", { freelancer_id: id })
      : localWrite("DELETE", "/api/wishlist/" + encodeURIComponent(id));
  }
  function saveButton(user, id) {
    var key = String(id);
    var button = el("button", "btn btn-ghost btn-small save-btn", "");
    button.type = "button";
    function paint() {
      var on = !!saved[key];
      button.textContent = on ? s.fl_saved : s.fl_save;
      button.setAttribute("aria-pressed", on ? "true" : "false");
    }
    paint();
    button.addEventListener("click", function () {
      var wantSaved = !saved[key];
      button.disabled = true;
      setSaved(user, id, wantSaved).then(function (res) {
        button.disabled = false;
        if (!res.ok) { setStatus(statusNode(), s.fl_save_error, "error"); return; }
        if (wantSaved) saved[key] = true; else delete saved[key];
        paint();
        setStatus(statusNode(), "", "");
      }).catch(function () {
        button.disabled = false;
        setStatus(statusNode(), s.fl_save_error, "error");
      });
    });
    return button;
  }
  function removeButton(user, id, card) {
    var button = el("button", "btn btn-ghost btn-small save-btn", s.fl_remove);
    button.type = "button";
    button.addEventListener("click", function () {
      button.disabled = true;
      setSaved(user, id, false).then(function (res) {
        if (!res.ok) { button.disabled = false; setStatus($("wl-status"), s.fl_save_error, "error"); return; }
        delete saved[String(id)];
        card.remove();
        if (!$("wl-results").children.length) showEmptyWishlist();
      }).catch(function () {
        button.disabled = false;
        setStatus($("wl-status"), s.fl_save_error, "error");
      });
    });
    return button;
  }

  // ---------- directory: services.html ----------
  function localDirectory(q, category) {
    var qs = [];
    if (q) qs.push("q=" + encodeURIComponent(q));
    if (category) qs.push("category=" + encodeURIComponent(category));
    return getJson("/api/freelancers" + (qs.length ? "?" + qs.join("&") : "")).then(function (res) {
      if (!res.ok) return { ok: false, list: [] };
      return { ok: true, list: res.data && Array.isArray(res.data.freelancers) ? res.data.freelancers : [] };
    });
  }

  // Adds service count and lowest price (from the active services) to freelancer rows from the view.
  function withServiceSummary(rows) {
    if (!rows.length) return Promise.resolve([]);
    var ids = rows.map(function (r) { return encodeURIComponent(r.id); }).join(",");
    return getJson("services?select=provider_id,price_sar&active=eq.true&provider_id=in.(" + ids + ")", true)
      .then(function (sv) {
        var summary = {};
        (Array.isArray(sv.data) ? sv.data : []).forEach(function (row) {
          var entry = summary[row.provider_id] || { count: 0, from: null };
          entry.count += 1;
          if (entry.from === null || row.price_sar < entry.from) entry.from = row.price_sar;
          summary[row.provider_id] = entry;
        });
        return rows.map(function (r) {
          var entry = summary[r.id] || { count: 0, from: null };
          return {
            id: r.id, full_name: r.full_name, specialty: r.specialty, avatar_url: r.avatar_url,
            headline: r.headline, service_count: entry.count, from_price: entry.from
          };
        });
      });
  }

  function supabaseDirectory(q, category) {
    var parts = ["select=id,full_name,specialty,avatar_url,headline,rating_avg,rating_count", "order=full_name.asc", "limit=100"];
    if (category) parts.push("specialty=eq." + encodeURIComponent(category));
    if (q) {
      var like = "*" + q + "*";
      parts.push("or=" + encodeURIComponent("(full_name.ilike." + like + ",headline.ilike." + like + ")"));
    }
    return getJson("freelancer_profiles?" + parts.join("&"), true).then(function (res) {
      if (!res.ok) return { ok: false, list: [] };
      return withServiceSummary(Array.isArray(res.data) ? res.data : []).then(function (list) {
        return { ok: true, list: list };
      });
    });
  }

  function freelancerCard(f, action) {
    var card = el("article", "freelancer-card");
    var top = el("div", "freelancer-top");
    top.appendChild(avatarNode(f.avatar_url, f.full_name));
    var who = el("div", "freelancer-who");
    who.appendChild(el("h3", null, f.full_name));
    who.appendChild(el("p", "muted", specialties[f.specialty] || ""));
    top.appendChild(who);
    card.appendChild(top);
    if (f.headline) card.appendChild(el("p", "freelancer-headline", f.headline));
    var meta = el("p", "freelancer-meta");
    if (f.from_price !== null && f.from_price !== undefined) {
      meta.appendChild(el("strong", null, fill(s.fl_from_price, { price: f.from_price })));
    }
    meta.appendChild(el("span", null, countText(Number(f.service_count) || 0)));
    meta.appendChild(el("span", "freelancer-rating", ratingLine(f.rating_avg, f.rating_count)));
    card.appendChild(meta);
    var actions = el("div", "freelancer-actions");
    var link = el("a", "btn btn-small freelancer-link", s.fl_view);
    link.href = base + "freelancer.html?id=" + encodeURIComponent(f.id);
    actions.appendChild(link);
    if (action) actions.appendChild(action(card));
    card.appendChild(actions);
    return card;
  }

  function renderDirectory(list) {
    var results = $("fl-results");
    var status = $("fl-status");
    results.replaceChildren();
    if (!list.length) { setStatus(status, s.fl_empty, ""); return; }
    setStatus(status, "", "");
    list.forEach(function (f) {
      results.appendChild(freelancerCard(f, viewer ? function () { return saveButton(viewer, f.id); } : null));
    });
  }

  function runSearch(event) {
    if (event) event.preventDefault();
    var form = $("fl-search");
    var q = cleanQuery(form.q.value);
    var category = form.category.value;
    var status = $("fl-status");
    setStatus(status, s.fl_loading, "");
    $("fl-results").replaceChildren();
    var request = isSupabase ? supabaseDirectory(q, category) : localDirectory(q, category);
    var alertNode = $("fl-alert");
    if (alertNode) { alertNode.hidden = true; setStatus(alertNode, "", ""); }
    Promise.all([request, whenReady()]).then(function (both) {
      var res = both[0];
      if (!res.ok) { setStatus(status, s.fl_error, "error"); return; }
      renderDirectory(res.list);
      notifyCategory(category);
    }).catch(function () { setStatus(status, s.fl_error, "error"); });
  }

  // A signed-in customer who looks for a category tells the freelancers of that category by e-mail.
  // The server limits this to one alert per category every 24 hours and never blocks the search.
  function supabaseAlert(category) {
    var token = window.XLANORA_AUTH ? window.XLANORA_AUTH.token() : null;
    return fetch(cfg.supabaseUrl + "/functions/v1/category-alert", {
      method: "POST",
      headers: { apikey: cfg.supabaseAnonKey, Authorization: "Bearer " + (token || cfg.supabaseAnonKey), "Content-Type": "application/json" },
      body: JSON.stringify({ category: category })
    }).then(function (res) { return readBody(res).then(function (data) { return { ok: res.ok, data: data }; }); });
  }
  function notifyCategory(category) {
    var alertNode = $("fl-alert");
    if (!alertNode || !viewer || !category) return;
    var request = isSupabase ? supabaseAlert(category) : localWrite("POST", "/api/category-alerts", { category: category });
    request.then(function (res) {
      if (!res.ok || !res.data) return;
      setStatus(alertNode, res.data.recent ? s.al_recent : s.al_sent, "ok");
      alertNode.hidden = false;
    }).catch(function () { /* the search already worked; the alert is best effort */ });
  }

  // ---------- one freelancer: freelancer.html?id=... ----------
  function localDetail(id) {
    return getJson("/api/freelancers/" + encodeURIComponent(id)).then(function (res) {
      if (res.status === 404) return { status: 404 };
      if (!res.ok || !res.data || !res.data.freelancer) return { status: res.status || 0 };
      return { status: 200, detail: res.data };
    });
  }

  // The newest completed booking with this freelancer that the signed-in client has not reviewed yet.
  function supabaseReviewBooking(enc) {
    if (!viewer) return Promise.resolve(null);
    return Promise.all([
      sbAuthed("GET", "bookings?select=id,ends_at&client_id=eq." + encodeURIComponent(viewer.id) +
               "&provider_id=eq." + enc + "&status=eq.completed&order=ends_at.desc", undefined),
      sbAuthed("GET", "reviews?select=booking_id&client_id=eq." + encodeURIComponent(viewer.id) +
               "&freelancer_id=eq." + enc, undefined)
    ]).then(function (r) {
      var done = {};
      (Array.isArray(r[1].data) ? r[1].data : []).forEach(function (row) { done[String(row.booking_id)] = true; });
      var open = (Array.isArray(r[0].data) ? r[0].data : []).filter(function (row) { return !done[String(row.id)]; });
      return open.length ? open[0].id : null;
    }).catch(function () { return null; });
  }
  function supabaseDetail(id) {
    var enc = encodeURIComponent(id);
    return Promise.all([
      getJson("freelancer_profiles?select=id,full_name,specialty,avatar_url,headline,rating_avg,rating_count&id=eq." + enc, true),
      getJson("services?select=id,title,description,price_sar,duration_minutes,category" +
              "&active=eq.true&provider_id=eq." + enc + "&order=created_at.desc", true),
      getJson("portfolio_items?select=id,title,description,image_url,project_url,category" +
              "&active=eq.true&provider_id=eq." + enc + "&order=created_at.desc", true),
      getJson("public_reviews?select=id,rating,comment,created_at,client_name&freelancer_id=eq." + enc +
              "&order=created_at.desc&limit=20", true),
      supabaseReviewBooking(enc)
    ]).then(function (r) {
      if (!r[0].ok) return { status: r[0].status || 0 };
      var rows = Array.isArray(r[0].data) ? r[0].data : [];
      if (!rows.length) return { status: 404 };
      return {
        status: 200,
        detail: {
          freelancer: rows[0],
          services: Array.isArray(r[1].data) ? r[1].data : [],
          portfolio: Array.isArray(r[2].data) ? r[2].data : [],
          reviews: Array.isArray(r[3].data) ? r[3].data : [],
          review_booking_id: r[4]
        }
      };
    });
  }

  function workCard(item) {
    var card = el("article", "work-card");
    var media = el("figure", "work-media");
    var src = imageSource(item.image_url);
    if (src && /\.(mp4|webm|mov)$/.test(src)) {
      var clip = document.createElement("video");
      clip.src = src;
      clip.controls = true;
      clip.preload = "metadata";
      clip.setAttribute("playsinline", "");
      clip.addEventListener("error", function () { media.replaceChildren(el("p", "work-noimage", pf.pf_no_image)); });
      media.appendChild(clip);
    } else if (src) {
      var img = document.createElement("img");
      img.src = src;
      img.alt = item.title;
      img.loading = "lazy";
      img.decoding = "async";
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", function () { media.replaceChildren(el("p", "work-noimage", pf.pf_no_image)); });
      media.appendChild(img);
    } else {
      media.appendChild(el("p", "work-noimage", pf.pf_no_image));
    }
    card.appendChild(media);
    var body = el("div", "work-body");
    body.appendChild(el("h3", null, item.title));
    body.appendChild(el("p", null, item.description));
    var project = safeLink(item.project_url);
    if (project) {
      var link = el("a", "text-link", pf.pf_view_project);
      link.href = project;
      link.target = "_blank";
      link.rel = "noopener noreferrer nofollow";
      body.appendChild(link);
    }
    card.appendChild(body);
    return card;
  }

  function renderDetail(detail) {
    var f = detail.freelancer;
    var services = detail.services || [];
    var portfolio = detail.portfolio || [];
    var lowest = null;
    services.forEach(function (sv) {
      if (lowest === null || sv.price_sar < lowest) lowest = sv.price_sar;
    });

    var info = el("div", "fp-info");
    info.appendChild(el("h2", null, f.full_name));
    info.appendChild(el("p", "muted", specialties[f.specialty] || ""));
    if (f.headline) info.appendChild(el("p", "fp-headline", f.headline));
    var meta = el("p", "freelancer-meta");
    if (lowest !== null) meta.appendChild(el("strong", null, fill(s.fl_from_price, { price: lowest })));
    meta.appendChild(el("span", null, countText(services.length)));
    meta.appendChild(el("span", "freelancer-rating", ratingLine(f.rating_avg, f.rating_count)));
    info.appendChild(meta);
    var actions = el("div", "fp-actions");
    var quote = el("a", "btn", s.fl_request);
    quote.href = base + "contact.html";
    actions.appendChild(quote);
    if (viewer) actions.appendChild(saveButton(viewer, f.id));
    info.appendChild(actions);
    $("fp-head").replaceChildren(avatarNode(f.avatar_url, f.full_name), info);

    var list = $("fp-services");
    list.replaceChildren();
    if (!services.length) {
      list.appendChild(el("p", "muted", s.fl_no_services));
    } else {
      services.forEach(function (sv) {
        var row = el("article", "fp-service");
        row.appendChild(el("h3", null, sv.title));
        row.appendChild(el("p", null, sv.description));
        var facts = el("p", "freelancer-meta");
        facts.appendChild(el("strong", null, priceText(sv.price_sar)));
        facts.appendChild(el("span", null, fill(s.fl_duration, { minutes: sv.duration_minutes })));
        facts.appendChild(el("span", null, specialties[sv.category] || ""));
        row.appendChild(facts);
        list.appendChild(row);
      });
    }

    var works = $("fp-portfolio");
    works.replaceChildren();
    if (!portfolio.length) {
      works.appendChild(el("p", "muted", s.fl_no_portfolio));
    } else {
      portfolio.forEach(function (item) { works.appendChild(workCard(item)); });
    }

    renderReviews(detail);

    setStatus($("fp-status"), "", "");
    $("fp-body").hidden = false;
  }

  // ---------- reviews: the list, and the form for a completed booking that is not reviewed yet ----------
  function reviewItem(item) {
    var card = el("article", "review-item");
    var head = el("p", "review-head");
    head.appendChild(el("strong", null, item.client_name || ""));
    var stars = el("span", "review-stars", starText(item.rating));
    stars.setAttribute("aria-label", fill(s.rv_star_label, { n: item.rating }));
    head.appendChild(stars);
    card.appendChild(head);
    if (item.comment) card.appendChild(el("p", "review-comment", item.comment));
    card.appendChild(el("p", "muted small", dateText(item.created_at)));
    return card;
  }
  function renderReviews(detail) {
    var f = detail.freelancer;
    var reviews = detail.reviews || [];
    $("fp-rating").textContent = Number(f.rating_count) ? ratingLine(f.rating_avg, f.rating_count) : "";
    var list = $("fp-reviews");
    list.replaceChildren();
    if (!reviews.length) {
      list.appendChild(el("p", "muted", s.rv_none));
    } else {
      reviews.forEach(function (item) { list.appendChild(reviewItem(item)); });
    }
    var form = $("fp-review-form");
    form.hidden = !(detail.review_booking_id || reviewSaved);
    if (detail.review_booking_id && !reviewSaved) buildReviewForm(f.id, detail.review_booking_id);
  }
  function buildReviewForm(freelancerId, bookingId) {
    var form = $("rv-form");
    var status = $("rv-status");
    var stars = $("rv-stars");
    var submit = form.querySelector("button[type=submit]");
    stars.replaceChildren();
    for (var n = 1; n <= 5; n++) {
      var label = el("label", "star-option");
      var input = el("input");
      input.type = "radio";
      input.name = "rating";
      input.value = String(n);
      input.setAttribute("aria-label", fill(s.rv_star_label, { n: n }));
      label.appendChild(input);
      label.appendChild(el("span", "star-glyph", "\u2605"));
      stars.appendChild(label);
    }
    setStatus(status, "", "");
    form.onsubmit = function (event) {
      event.preventDefault();
      var checked = form.querySelector("input[name=rating]:checked");
      var rating = checked ? Number(checked.value) : 0;
      var comment = String(form.comment.value || "").trim();
      if (!rating) { setStatus(status, s.rv_error_rating, "error"); return; }
      if (comment.length > 600) { setStatus(status, s.rv_error_comment, "error"); return; }
      submit.disabled = true;
      var request = isSupabase
        ? sbAuthed("POST", "reviews", { booking_id: bookingId, client_id: viewer.id, freelancer_id: freelancerId, rating: rating, comment: comment })
        : localWrite("POST", "/api/reviews", { booking_id: Number(bookingId), rating: rating, comment: comment });
      request.then(function (res) {
        if (res.status === 201 || res.ok) {
          reviewSaved = true;  // keep the form and its message on this page; it disappears on the next visit
          submit.disabled = true;
          setStatus(status, s.rv_saved, "ok");
          loadDetail(freelancerId);
          return;
        }
        submit.disabled = false;
        var formError = res.data && res.data.errors ? res.data.errors.form : "";
        var raw = JSON.stringify(res.data || {});
        if (formError === "email_not_verified" || raw.indexOf("email_not_verified") >= 0) {
          setStatus(status, s.vf_book_blocked, "error");
        } else if (res.status === 404 || res.status === 409 || res.status === 403) {
          setStatus(status, s.rv_error_gone, "error");
        } else {
          setStatus(status, s.rv_error, "error");
        }
      }).catch(function () {
        submit.disabled = false;
        setStatus(status, s.rv_error, "error");
      });
    };
  }

  function showProfileProblem(text) {
    setStatus($("fp-status"), text, "error");
    $("fp-body").hidden = true;
  }

  function loadDetail(id) {
    return whenReady().then(function () {
      return isSupabase ? supabaseDetail(id) : localDetail(id);
    }).then(function (res) {
      if (res.status === 404) { showProfileProblem(s.fl_not_found); return; }
      if (res.status !== 200) { showProfileProblem(s.fl_error_profile); return; }
      renderDetail(res.detail);
    }).catch(function () { showProfileProblem(s.fl_error_profile); });
  }
  function initDetail() {
    var id = (new URLSearchParams(window.location.search).get("id") || "").trim();
    var valid = isSupabase ? UUID.test(id) : NUMERIC_ID.test(id);
    if (!valid) { showProfileProblem(s.fl_not_found); return; }
    loadDetail(id);
  }

  // ---------- saved freelancers: wishlist.html (clients only) ----------
  function showEmptyWishlist() {
    $("wl-results").replaceChildren();
    setStatus($("wl-status"), s.wl_empty, "");
  }

  function localWishlist() {
    return getJson("/api/wishlist").then(function (res) {
      if (!res.ok) return { ok: false, list: [] };
      return { ok: true, list: (res.data && res.data.items) || [] };
    });
  }

  function supabaseWishlist(user) {
    return sbAuthed("GET", "wishlist?select=freelancer_id,created_at&client_id=eq." + encodeURIComponent(user.id) + "&order=created_at.desc")
      .then(function (res) {
        if (!res.ok) return { ok: false, list: [] };
        var ids = (Array.isArray(res.data) ? res.data : []).map(function (row) { return row.freelancer_id; });
        if (!ids.length) return { ok: true, list: [] };
        return getJson("freelancer_profiles?select=id,full_name,specialty,avatar_url,headline,rating_avg,rating_count&id=in.(" +
                       ids.map(encodeURIComponent).join(",") + ")", true).then(function (profiles) {
          var rows = Array.isArray(profiles.data) ? profiles.data : [];
          var order = {};
          ids.forEach(function (id, i) { order[id] = i; });
          rows.sort(function (a, b) { return order[a.id] - order[b.id]; });
          return withServiceSummary(rows).then(function (list) { return { ok: true, list: list }; });
        });
      });
  }

  function initWishlist() {
    whenReady().then(function () {
      if (!viewer) return;  // visitors and freelancers keep the sign-in note
      $("wl-gate").hidden = true;
      $("wl-body").hidden = false;
      setStatus($("wl-status"), s.fl_loading, "");
      var request = isSupabase ? supabaseWishlist(viewer) : localWishlist();
      request.then(function (res) {
        if (!res.ok) { setStatus($("wl-status"), s.wl_error, "error"); return; }
        if (!res.list.length) { showEmptyWishlist(); return; }
        setStatus($("wl-status"), "", "");
        res.list.forEach(function (f) {
          $("wl-results").appendChild(freelancerCard(f, function (card) { return removeButton(viewer, f.id, card); }));
        });
      }).catch(function () { setStatus($("wl-status"), s.wl_error, "error"); });
    });
  }

  if (page === "services") {
    var form = $("fl-search");
    if (form && $("fl-results")) {
      form.addEventListener("submit", runSearch);
      runSearch(null);
    }
  }
  if (page === "freelancer" && $("fp-body")) initDetail();
  if (page === "wishlist" && $("wl-gate")) initWishlist();
})();
