// Profile photo on the dashboard (every signed-in role). The photo is checked on the device and again
// on the server: JPG, PNG or WebP, up to 10 MB, and the file must really be that image type.
// Written with textContent and DOM methods only; the file is sent as raw bytes, never as HTML.
(function () {
  "use strict";

  var cfg = window.XLANORA_CONFIG || { backend: "local" };
  var isSupabase = cfg.backend === "supabase";
  var panel = document.getElementById("profile-panel");
  var i18nNode = document.getElementById("i18n");
  if (!panel || !i18nNode || !window.XLANORA_AUTH) return;
  var t = JSON.parse(i18nNode.textContent);
  var s = t.pr || {};
  var IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
  var MAX_IMAGE_BYTES = 10 * 1024 * 1024;  // the server checks the same limit
  var current = null;  // the signed-in user, as last shown

  function $(id) { return document.getElementById(id); }

  function setStatus(text, kind) {
    var n = $("avatar-status");
    n.textContent = text || "";
    n.className = "form-status" + (kind ? " is-" + kind : "");
  }

  // Shows the saved photo, or the first letter of the name when there is none.
  function showAvatar(url, name) {
    var img = $("profile-avatar");
    var initial = $("profile-initial");
    if (url) {
      img.src = url;
      img.alt = name || "";
      img.hidden = false;
      initial.hidden = true;
    } else {
      img.hidden = true;
      img.removeAttribute("src");
      initial.hidden = false;
      initial.textContent = String(name || "").trim().charAt(0).toUpperCase();
    }
  }

  function render(user) {
    current = user;
    panel.hidden = false;
    $("profile-name").textContent = user.full_name || "";
    $("profile-role").textContent = user.role === "freelancer" ? s.profile_role_freelancer : s.profile_role_client;
    showAvatar(user.avatar_url, user.full_name);
  }

  function chosen() {
    var input = $("avatar-file");
    return input.files && input.files[0] ? input.files[0] : null;
  }

  // Preview the chosen file before saving; refuse wrong types and large files right away.
  $("avatar-file").addEventListener("change", function () {
    var file = chosen();
    setStatus("");
    $("avatar-save").disabled = true;
    if (!file) return;
    if (IMAGE_TYPES.indexOf(file.type) < 0) { setStatus(s.profile_err_type, "error"); $("avatar-file").value = ""; return; }
    if (file.size > MAX_IMAGE_BYTES) { setStatus(s.profile_err_size, "error"); $("avatar-file").value = ""; return; }
    var reader = new FileReader();
    reader.onload = function () {
      var img = $("profile-avatar");
      img.src = reader.result;
      img.hidden = false;
      $("profile-initial").hidden = true;
    };
    reader.readAsDataURL(file);
    $("avatar-save").disabled = false;
  });

  // Local: the server stores the picture. Supabase: Storage stores it, then the profile row points at it.
  function sendLocal(file) {
    return fetch("/api/me/avatar", {
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
  function sendSupabase(file) {
    return window.XLANORA_AUTH.uploadPhoto(current.id, file).then(function (up) {
      if (!up.ok) return { ok: false, status: up.status, data: null };
      var old = current.avatar_url;
      return window.XLANORA_AUTH.setAvatar(current.id, up.url).then(function (saved) {
        if (!saved.ok) {
          window.XLANORA_AUTH.deletePhoto(up.url);
          return { ok: false, status: saved.status, data: null };
        }
        window.XLANORA_AUTH.deletePhoto(old);  // the replaced picture, if this site stored it
        return { ok: true, status: 200, data: { avatar_url: up.url } };
      });
    });
  }

  $("avatar-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var file = chosen();
    if (!file || !current) return;
    var button = $("avatar-save");
    button.disabled = true;
    setStatus("");
    (isSupabase ? sendSupabase(file) : sendLocal(file)).then(function (res) {
      if (res.ok && res.data && res.data.avatar_url) {
        current.avatar_url = res.data.avatar_url;
        showAvatar(res.data.avatar_url, $("profile-name").textContent);
        $("avatar-file").value = "";
        setStatus(s.profile_saved, "success");
        return;
      }
      if (res.status === 415) setStatus(s.profile_err_type, "error");
      else if (res.status === 413) setStatus(s.profile_err_size, "error");
      else setStatus(s.profile_err_generic, "error");
      button.disabled = false;
    }).catch(function () {
      setStatus(s.profile_err_generic, "error");
      button.disabled = false;
    });
  });

  window.XLANORA_AUTH.me().then(function (res) {
    if (res.status === 200 && res.data && res.data.user) render(res.data.user);
  }).catch(function () { /* signed out: the dashboard already asks the visitor to sign in */ });
})();
