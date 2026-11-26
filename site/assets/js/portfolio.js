// Portfolio page (portfolio.html): freelancers manage their own work samples. Visitors and clients see
// a note instead; the public view of a freelancer's work is on the freelancer's profile page.
// Two backends, one behaviour (same switch as auth.js and bookings.js):
//   local    -> /api/portfolio and /api/my/portfolio on the Python server
//   supabase -> list_portfolio RPC and portfolio_items table (row-level security decides who may write)
// Everything shown is written with textContent. No inline scripts.
(function () {
  "use strict";

  var cfg = window.XLANORA_CONFIG || { backend: "local" };
  var isSupabase = cfg.backend === "supabase";
  var i18nNode = document.getElementById("i18n");
  var t = i18nNode ? JSON.parse(i18nNode.textContent) : {};
  var s = t.pf || {};
  var bk = t.bk || {};
  var ME = null;
  var editingId = "";
  var IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
  var VIDEO_TYPES = ["video/mp4", "video/webm", "video/quicktime"];
  var MAX_IMAGE_BYTES = 10 * 1024 * 1024;  // photos: 10 MB (the server checks the same limits)
  var MAX_VIDEO_BYTES = 50 * 1024 * 1024;  // videos: 50 MB
  var pr = t.pr || {};

  function $(id) { return document.getElementById(id); }
  function el(tag, className, text) {
    var n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function setStatus(node, text, kind) {
    node.textContent = text || "";
    node.className = "form-status" + (kind ? " is-" + kind : "");
  }
  function categoryLabel(slug) { return (t.specialties || {})[slug] || slug; }
  function readBody(res) {
    return res.text().then(function (text) {
      try { return text ? JSON.parse(text) : null; } catch (e) { return null; }
    });
  }
  function localCall(method, path, body) {
    var options = { method: method, headers: { Accept: "application/json" }, credentials: "same-origin" };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(path, options).then(function (res) {
      return readBody(res).then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
    });
  }
  function sbCall(method, path, body, prefer) {
    var token = window.XLANORA_AUTH.token();
    var headers = {
      apikey: cfg.supabaseAnonKey,
      Authorization: "Bearer " + (token || cfg.supabaseAnonKey),
      "Content-Type": "application/json"
    };
    if (prefer) headers.Prefer = prefer;
    var options = { method: method, headers: headers };
    if (body !== undefined) options.body = JSON.stringify(body);
    return fetch(cfg.supabaseUrl + path, options).then(function (res) {
      return readBody(res).then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
    });
  }
  function encode(params) {
    var parts = [];
    Object.keys(params).forEach(function (key) {
      if (params[key] !== "" && params[key] !== null && params[key] !== undefined) {
        parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(params[key]));
      }
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  // Safe image: only https links are shown; anything else falls back to the text placeholder.
  function safeLink(url) {
    return typeof url === "string" && url.indexOf("https://") === 0 ? url : "";
  }
  // A photo or video uploaded from the device is served by this site as /uploads/<random name>.
  function imageSource(url) {
    if (typeof url === "string" && /^\/uploads\/[a-f0-9]{32}\.(jpg|png|webp|mp4|webm|mov)$/.test(url)) return url;
    return safeLink(url);
  }
  function isVideoUrl(url) { return typeof url === "string" && /\.(mp4|webm|mov)$/.test(url); }
  // "image", "video" or "" for a file the chooser may not offer: the type and the size limit both apply.
  function fileKind(file) {
    if (!file) return "";
    if (IMAGE_TYPES.indexOf(file.type) >= 0) return file.size <= MAX_IMAGE_BYTES ? "image" : "";
    if (VIDEO_TYPES.indexOf(file.type) >= 0) return file.size <= MAX_VIDEO_BYTES ? "video" : "";
    return "";
  }
  // Some systems give a video an empty MIME type; the file extension decides the type then.
  var EXT_TYPES = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp",
                    mp4: "video/mp4", webm: "video/webm", mov: "video/quicktime" };
  function typedFile(file) {
    if (!file) return null;
    if (IMAGE_TYPES.concat(VIDEO_TYPES).indexOf(file.type) >= 0) return file;
    var m = /\.([a-z0-9]+)$/i.exec(file.name || "");
    var type = m ? EXT_TYPES[m[1].toLowerCase()] : "";
    return type ? new File([file], file.name, { type: type }) : file;
  }
  function chosenFile() {
    var input = $("pf-file");
    return input && input.files && input.files[0] ? typedFile(input.files[0]) : null;
  }
  function previewChosen() {
    var img = $("pf-preview");
    var file = chosenFile();
    if (fileKind(file) !== "image") {
      img.hidden = true; img.removeAttribute("src");
      return;
    }
    var reader = new FileReader();
    reader.onload = function () { img.src = reader.result; img.hidden = false; };
    reader.readAsDataURL(file);
  }
  function uploadImage(itemId, file) {
    return fetch("/api/my/portfolio/" + encodeURIComponent(itemId) + "/image", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": file.type, Accept: "application/json" },
      body: file
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        return { ok: res.ok, status: res.status, data: data };
      });
    });
  }

  // Supabase: store the photo, then point the item at its public link. Local: the server stores it.
  function uploadItemPhoto(itemId, file) {
    if (!isSupabase) return uploadImage(itemId, file);
    return sbCall("GET", "/rest/v1/portfolio_items?select=image_url&id=eq." + itemId).then(function (cur) {
      var old = cur.ok && Array.isArray(cur.data) && cur.data[0] ? cur.data[0].image_url : "";
      return window.XLANORA_AUTH.uploadPhoto(ME.id, file).then(function (up) {
        if (!up.ok) return { ok: false, status: up.status };
        return sbCall("PATCH", "/rest/v1/portfolio_items?id=eq." + itemId, { image_url: up.url }, "return=minimal")
          .then(function (res) {
            if (!res.ok) { window.XLANORA_AUTH.deletePhoto(up.url); return { ok: false, status: res.status }; }
            window.XLANORA_AUTH.deletePhoto(old);  // the replaced photo, if it was stored by this site
            return { ok: true, status: 200 };
          });
      });
    });
  }

  // ---------- public list ----------
  function myItems() {
    if (isSupabase) {
      return sbCall("GET", "/rest/v1/portfolio_items?select=id,title,description,image_url,project_url,category" +
        "&provider_id=eq." + ME.id + "&active=eq.true&order=id.desc");
    }
    return localCall("GET", "/api/my/portfolio").then(function (res) {
      return { ok: res.ok, data: (res.data && res.data.items) || [] };
    });
  }
  function saveItem(id, payload) {
    if (isSupabase) {
      if (id) return sbCall("PATCH", "/rest/v1/portfolio_items?id=eq." + id, payload, "return=minimal");
      return sbCall("POST", "/rest/v1/portfolio_items",
        Object.assign({ provider_id: ME.id, category: ME.specialty }, payload), "return=representation");
    }
    return id ? localCall("PUT", "/api/my/portfolio/" + id, payload)
              : localCall("POST", "/api/my/portfolio", payload);
  }
  function removeItem(id) {
    if (isSupabase) return sbCall("PATCH", "/rest/v1/portfolio_items?id=eq." + id, { active: false }, "return=minimal");
    return localCall("DELETE", "/api/my/portfolio/" + id);
  }

  function resetForm() {
    var form = $("pf-form");
    form.reset();
    $("pf-preview").hidden = true;
    $("pf-preview").removeAttribute("src");
    form.elements["id"].value = "";
    editingId = "";
    $("pf-form-title").textContent = s.pf_add;
    $("pf-cancel").hidden = true;
  }
  function editItem(item) {
    var form = $("pf-form");
    form.elements["id"].value = item.id;
    form.title.value = item.title;
    form.description.value = item.description;
    var isUpload = typeof item.image_url === "string" && item.image_url.indexOf("/uploads/") === 0;
    form.image_url.value = isUpload ? "" : (item.image_url || "");
    if (isUpload && !isVideoUrl(item.image_url)) { $("pf-preview").src = item.image_url; $("pf-preview").hidden = false; }
    form.project_url.value = item.project_url || "";
    editingId = String(item.id);
    $("pf-form-title").textContent = s.pf_edit_item;
    $("pf-cancel").hidden = false;
    form.title.focus();
    form.scrollIntoView({ block: "start" });
  }
  function loadItems() {
    var list = $("pf-list");
    myItems().then(function (res) {
      if (!res.ok) { setStatus($("pf-status"), s.pf_err_generic, "error"); return; }
      list.replaceChildren();
      if (!res.data.length) { list.appendChild(el("p", "muted", s.pf_none)); return; }
      res.data.forEach(function (item) {
        var card = el("article", "booking-card");
        var thumb = imageSource(item.image_url);
        if (thumb && isVideoUrl(thumb)) {
          var clip = el("video", "manage-thumb");
          clip.src = thumb;
          clip.controls = true;
          clip.preload = "metadata";
          clip.setAttribute("playsinline", "");
          card.appendChild(clip);
        } else if (thumb) {
          var picture = el("img", "manage-thumb");
          picture.src = thumb;
          picture.alt = "";
          picture.width = 240;
          picture.height = 135;
          picture.loading = "lazy";
          picture.decoding = "async";
          card.appendChild(picture);
        }
        card.appendChild(el("p", "eyebrow", categoryLabel(item.category)));
        card.appendChild(el("h3", null, item.title));
        card.appendChild(el("p", "muted", item.description));
        var bar = el("div", "actions");
        var edit = el("button", "btn btn-ghost", s.pf_edit);
        edit.type = "button";
        edit.addEventListener("click", function () { editItem(item); });
        var remove = el("button", "btn btn-ghost", s.pf_remove);
        remove.type = "button";
        remove.addEventListener("click", function () {
          if (!window.confirm(s.pf_remove_confirm)) return;
          removeItem(item.id).then(function (r) {
            if (r.ok) { setStatus($("pf-status"), s.pf_removed, "success"); loadItems(); }
            else setStatus($("pf-status"), s.pf_err_generic, "error");
          }).catch(function () { setStatus($("pf-status"), s.pf_err_network, "error"); });
        });
        bar.appendChild(edit);
        bar.appendChild(remove);
        card.appendChild(bar);
        list.appendChild(card);
      });
    }).catch(function () {
      setStatus($("pf-status"), s.pf_err_network, "error");
    });
  }
  function submitItem(event) {
    event.preventDefault();
    var form = $("pf-form");
    var status = $("pf-status");
    var title = form.title.value.trim();
    var description = form.description.value.trim();
    var image = form.image_url.value.trim();
    var project = form.project_url.value.trim();
    var linksOk = [image, project].every(function (url) {
      return url === "" || (url.indexOf("https://") === 0 && !/\s/.test(url) && url.length <= 500);
    });
    if (title.length < 3 || title.length > 100 || description.length < 10 || description.length > 1000 || !linksOk) {
      setStatus(status, s.pf_err_invalid, "error");
      return;
    }
    var file = chosenFile();
    if (file && !fileKind(file)) {
      var known = IMAGE_TYPES.concat(VIDEO_TYPES).indexOf(file.type) >= 0;
      setStatus(status, known ? s.pf_upload_err_size : s.pf_upload_err_type, "error");
      return;
    }
    var payload = { title: title, description: description, image_url: image || null, project_url: project || null };
    saveItem(form.elements["id"].value || null, payload).then(function (res) {
      if (!res.ok) { setStatus(status, s.pf_err_invalid, "error"); return null; }
      var id = form.elements["id"].value || (Array.isArray(res.data) ? res.data[0].id : res.data && res.data.id);
      if (!file) return true;
      return uploadItemPhoto(id, file).then(function (up) {
        if (!up.ok) { setStatus(status, s.pf_err_photo, "error"); loadItems(); return null; }
        return true;
      });
    }).then(function (done) {
      if (!done) return;
      setStatus(status, s.pf_saved, "success");
      resetForm();
      loadItems();
    }).catch(function () {
      setStatus(status, s.pf_err_network, "error");
    });
  }

  function init() {
    if (!$("portfolio-manage") || !window.XLANORA_AUTH) return;
    $("pf-form").addEventListener("submit", submitItem);
    if ($("pf-file")) $("pf-file").addEventListener("change", previewChosen);
    $("pf-cancel").addEventListener("click", function () { resetForm(); setStatus($("pf-status"), ""); });
    window.XLANORA_AUTH.me().then(function (res) {
      if (res.status !== 200 || !res.data || !res.data.user || res.data.user.role !== "freelancer") return;
      ME = res.data.user;
      $("pf-gate").hidden = true;
      $("portfolio-manage").hidden = false;
      loadItems();
    }).catch(function () { /* signed out: the page keeps its sign-in message */ });
  }
  init();
})();
