// Administrator inbox: lists the contact-form messages. Only an administrator account gets the data;
// the server returns 403 to everyone else, and this page only decides what to show.
// Everything from the messages is written with textContent (never as HTML).
(function () {
  "use strict";

  var gate = document.getElementById("adm-gate");
  var main = document.getElementById("adm-main");
  var i18nNode = document.getElementById("i18n");
  if (!gate || !main || !i18nNode) return;
  var t = JSON.parse(i18nNode.textContent);
  var s = t.adm || {};

  function $(id) { return document.getElementById(id); }
  function el(tag, className, text) {
    var n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function showGate(text) {
    gate.textContent = text;
    gate.hidden = false;
    main.hidden = true;
  }
  function render(messages) {
    var body = $("adm-contacts");
    body.replaceChildren();
    if (!messages.length) {
      var empty = el("tr");
      var cell = el("td", "muted", s.adm_empty);
      cell.colSpan = 5;
      empty.appendChild(cell);
      body.appendChild(empty);
      return;
    }
    messages.forEach(function (m) {
      var row = el("tr");
      row.appendChild(el("td", null, String(m.created_at || "").replace("T", " ").slice(0, 16)));
      row.appendChild(el("td", null, m.name));
      var cell = el("td");
      var link = el("a", null, m.email);
      link.href = "mailto:" + encodeURI(m.email);
      cell.appendChild(link);
      row.appendChild(cell);
      row.appendChild(el("td", null, m.service || "-"));
      var text = el("td", "pre-wrap", m.message);
      row.appendChild(text);
      body.appendChild(row);
    });
  }
  function load() {
    $("adm-status").textContent = "";
    window.XLANORA_AUTH.inbox().then(function (res) {
      if (res.status !== 200) { $("adm-status").textContent = s.adm_error; $("adm-status").className = "form-status is-error"; return; }
      render(res.data.messages || []);
    }).catch(function () {
      $("adm-status").textContent = s.adm_error;
      $("adm-status").className = "form-status is-error";
    });
  }

  if (!window.XLANORA_AUTH) return;
  window.XLANORA_AUTH.me().then(function (res) {
    var user = res.data && res.data.user;
    if (!user) { showGate(s.adm_gate); return; }
    if (!user.is_admin) { showGate(s.adm_forbidden); return; }
    gate.hidden = true;
    main.hidden = false;
    load();
  }).catch(function () { showGate(s.adm_gate); });
})();
