// Booking panels for the dashboard: find services, book a time, manage bookings,
// manage own services and weekly hours (freelancers). The password form is in password.js.
// One API layer, two backends (same switch as auth.js):
//   backend "local"    -> /api/... on the Python server (cookie session, rules in the server and in SQLite triggers)
//   backend "supabase" -> RPC functions and REST tables (RLS and database rules enforce everything)
// Everything shown on screen is written with textContent, never innerHTML. No inline scripts.
(function () {
  "use strict";

  var cfg = window.XLANORA_CONFIG || { backend: "local" };
  var isSupabase = cfg.backend === "supabase";
  var i18nNode = document.getElementById("i18n");
  var t = i18nNode ? JSON.parse(i18nNode.textContent) : {};
  var s = Object.assign({}, t.bk || {}, t.rv || {}, t.od || {});
  // Times are shown with AM/PM (values sent to the server stay 24-hour HH:MM).
  function clock(hhmm) {
    var parts = String(hhmm).split(":");
    var h = parseInt(parts[0], 10);
    var minutes = parts[1] || "00";
    var arabic = document.documentElement.lang === "ar";
    var suffix = h < 12 ? (arabic ? "ص" : "AM") : (arabic ? "م" : "PM");
    return ((h % 12) || 12) + ":" + minutes + " " + suffix;
  }
  var TZ_MIN = 180;          // Asia/Riyadh is UTC+3 all year (no daylight saving)
  var MAX_DAYS = 60;         // same horizon as the server
  var ME = null;             // the signed-in user: { id, role, specialty, email, full_name }
  var selectedService = null;
  var selectedTime = "";

  if (!window.XLANORA_AUTH || !document.getElementById("bookings-panel")) return;

  // ---------- small helpers ----------
  function $(id) { return document.getElementById(id); }
  function show(id, visible) { var n = $(id); if (n) n.hidden = !visible; }
  function el(tag, className, text) {
    var n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function fill(text, vars) {
    return String(text).replace(/\{(\w+)\}/g, function (_, key) { return vars[key] !== undefined ? vars[key] : ""; });
  }
  function setStatus(node, text, kind) {
    node.textContent = text || "";
    node.className = "form-status" + (kind ? " is-" + kind : "");
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function hm(minutes) { return pad(Math.floor(minutes / 60)) + ":" + pad(minutes % 60); }
  function localParts(date) {
    var shifted = new Date(date.getTime() + TZ_MIN * 60000);
    return { date: shifted.toISOString().slice(0, 10), time: shifted.toISOString().slice(11, 16) };
  }
  function addDays(isoDate, days) {
    var d = new Date(isoDate + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
  }
  function todayLocal() { return localParts(new Date()).date; }
  function statusLabel(status) { return s["bk_status_" + status] || status; }
  function priceText(price) { return fill(s.bk_price, { price: price }); }
  function durationText(minutes) { return fill(s.bk_duration, { minutes: minutes }); }
  function categoryLabel(slug) { return (t.specialties || {})[slug] || slug; }

  // ---------- HTTP ----------
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
  // Errors from the local server arrive as { errors: {...} }; from Supabase as { message, ... }.
  function fieldErrors(res) {
    if (!res || !res.data) return {};
    return res.data.errors || res.data;
  }
  function sbMessage(res) {
    return (res && res.data && (res.data.message || res.data.hint)) || "";
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

  // ---------- API (both backends, same return shapes) ----------
  var api = {
    services: function (filters) {
      if (isSupabase) {
        return sbCall("POST", "/rest/v1/rpc/list_services", {
          p_category: filters.category || null,
          p_text: filters.q || null,
          p_max_price: filters.max_price === "" ? null : Number(filters.max_price),
          p_sort: filters.sort || "newest"
        }).then(function (res) { return { ok: res.ok, data: res.data || [] }; });
      }
      return localCall("GET", "/api/services" + encode(filters)).then(function (res) {
        return { ok: res.ok, data: (res.data && res.data.services) || [] };
      });
    },

    slots: function (serviceId, date) {
      if (isSupabase) {
        return sbCall("POST", "/rest/v1/rpc/service_slots", { p_service: serviceId, p_date: date })
          .then(function (res) {
            return { ok: res.ok, data: (res.data || []).map(function (row) { return row.slot_time; }) };
          });
      }
      return localCall("GET", "/api/services/" + serviceId + "/slots?date=" + encodeURIComponent(date))
        .then(function (res) { return { ok: res.ok, data: (res.data && res.data.slots) || [], res: res }; });
    },

    book: function (serviceId, date, time, note) {
      if (isSupabase) {
        return sbCall("POST", "/rest/v1/rpc/book_service", {
          p_service: serviceId, p_date: date, p_time: time, p_note: note || ""
        });
      }
      return localCall("POST", "/api/bookings", { service_id: serviceId, date: date, time: time, note: note || "" });
    },

    bookings: function () {
      if (isSupabase) {
        return sbCall("POST", "/rest/v1/rpc/my_bookings", {}).then(function (res) {
          var rows = (res.data || []).map(function (row) {
            var local = localParts(new Date(row.starts_at));
            return {
              id: row.id, status: row.status, service_title: row.service_title, price_sar: row.price_sar,
              provider_name: row.provider_name, client_name: row.client_name, contact: row.contact,
              note: row.note, date: local.date, time: local.time,
              agreed_price_sar: row.agreed_price_sar, payment_method: row.payment_method,
              payment_method_note: row.payment_method_note, client_paid_at: row.client_paid_at,
              provider_received_at: row.provider_received_at, delivery_confirmed_at: row.delivery_confirmed_at,
              payment_currency: row.payment_currency
            };
          });
          return { ok: res.ok, data: rows };
        });
      }
      return localCall("GET", "/api/bookings").then(function (res) {
        var rows = ((res.data && res.data.bookings) || []).map(function (row) {
          return {
            id: row.id, status: row.status, service_title: row.service_title, price_sar: row.price_sar,
            provider_name: row.provider_name, client_name: row.client_name, contact: row.contact,
            note: row.note, date: row.local_date, time: row.local_time,
            agreed_price_sar: row.agreed_price_sar, payment_method: row.payment_method,
            payment_method_note: row.payment_method_note, client_paid_at: row.client_paid_at,
            provider_received_at: row.provider_received_at, delivery_confirmed_at: row.delivery_confirmed_at,
            payment_currency: row.payment_currency
          };
        });
        return { ok: res.ok, data: rows };
      });
    },

    action: function (bookingId, action) {
      if (isSupabase) {
        return sbCall("POST", "/rest/v1/rpc/set_booking_status", { p_booking: bookingId, p_action: action });
      }
      return localCall("POST", "/api/bookings/" + bookingId + "/" + action, {});
    },

    // ----- direct payment, confirmations, delivery, reports (no site payments) -----
    orderCall: function (bookingId, name, localPath, body) {
      if (isSupabase) {
        return sbCall("POST", "/rest/v1/rpc/" + name, Object.assign({ p_booking: bookingId }, body || {}));
      }
      return localCall("POST", "/api/bookings/" + bookingId + "/" + localPath, body || {});
    },
    setPaymentMethod: function (bookingId, method, note, currency) {
      if (isSupabase) {
        return this.orderCall(bookingId, "set_payment_method", "",
          { p_method: method, p_note: note || "", p_currency: currency || "SAR" });
      }
      return this.orderCall(bookingId, "", "payment-method", { method: method, note: note || "", currency: currency || "SAR" });
    },
    confirmPayment: function (bookingId) {
      return this.orderCall(bookingId, "confirm_payment", "confirm-payment", {});
    },
    confirmDelivery: function (bookingId) {
      return this.orderCall(bookingId, "confirm_delivery", "confirm-delivery", {});
    },
    reportOrder: function (bookingId, reason, details) {
      if (isSupabase) {
        return this.orderCall(bookingId, "report_order", "", { p_reason: reason, p_details: details || "" });
      }
      return this.orderCall(bookingId, "", "report", { reason: reason, details: details || "" });
    },
    orderActivity: function (bookingId) {
      if (isSupabase) {
        return sbCall("POST", "/rest/v1/rpc/order_activity", { p_booking: bookingId }).then(function (res) {
          return { ok: res.ok, data: (res.data || []).map(function (row) {
            return { action: row.action, created_at: row.created_at, by_you: row.by_you };
          }) };
        });
      }
      return localCall("GET", "/api/bookings/" + bookingId + "/activity").then(function (res) {
        return { ok: res.ok, data: (res.data && res.data.activity) || [] };
      });
    },

    myServices: function () {
      if (isSupabase) {
        return sbCall("GET", "/rest/v1/services?select=id,title,description,price_sar,duration_minutes,category" +
          "&provider_id=eq." + ME.id + "&active=eq.true&order=id.desc").then(function (res) {
          return { ok: res.ok, data: res.data || [] };
        });
      }
      return localCall("GET", "/api/my/services").then(function (res) {
        return { ok: res.ok, data: (res.data && res.data.services) || [] };
      });
    },

    saveService: function (id, payload) {
      if (isSupabase) {
        // The database trigger (migration 008) refuses a fourth active service with "service_limit";
        // report it in the same shape the local server uses, so one message covers both versions.
        var mapLimit = function (res) {
          if (!res.ok && res.data && /service_limit/.test(String(res.data.message || ""))) {
            res.data = { errors: { services: "limit_reached" } };
          }
          return res;
        };
        if (id) return sbCall("PATCH", "/rest/v1/services?id=eq." + id, payload, "return=minimal").then(mapLimit);
        var row = Object.assign({ provider_id: ME.id, category: ME.specialty }, payload);
        return sbCall("POST", "/rest/v1/services", row, "return=minimal").then(mapLimit);
      }
      return id ? localCall("PUT", "/api/my/services/" + id, payload)
                : localCall("POST", "/api/my/services", payload);
    },

    removeService: function (id) {
      if (isSupabase) return sbCall("PATCH", "/rest/v1/services?id=eq." + id, { active: false }, "return=minimal");
      return localCall("DELETE", "/api/my/services/" + id);
    },

    hours: function () {
      if (isSupabase) {
        return sbCall("GET", "/rest/v1/availability?select=weekday,start_minute,end_minute&provider_id=eq." +
          ME.id + "&order=weekday.asc,start_minute.asc").then(function (res) {
          return {
            ok: res.ok,
            data: (res.data || []).map(function (r) { return { weekday: r.weekday, start: r.start_minute, end: r.end_minute }; })
          };
        });
      }
      return localCall("GET", "/api/my/availability").then(function (res) {
        return { ok: res.ok, data: (res.data && res.data.windows) || [] };
      });
    },

    saveHours: function (windows) {
      if (isSupabase) return sbCall("POST", "/rest/v1/rpc/save_availability", { p_windows: windows });
      return localCall("PUT", "/api/my/availability", { windows: windows });
    },

  };

  // ---------- error wording ----------
  function bookingError(res) {
    if (isSupabase) {
      var msg = sbMessage(res);
      if (msg.indexOf("email_not_verified") >= 0) return s.vf_book_blocked;
      if (msg.indexOf("slot_unavailable") >= 0 || msg.indexOf("exclusion") >= 0 || msg.indexOf("booking_overlaps") >= 0) return s.bk_err_slot;
      if (msg.indexOf("booking_in_past") >= 0 || msg.indexOf("in the past") >= 0) return s.bk_err_past;
      if (msg.indexOf("forbidden") >= 0) return s.bk_err_own;
      return s.bk_err_generic;
    }
    var errors = fieldErrors(res);
    if (errors.form === "email_not_verified") return s.vf_book_blocked;
    if (errors.slot) return s.bk_err_slot;
    if (errors.service_id === "own_service") return s.bk_err_own;
    if (errors.date === "in_past" || errors.date === "past") return s.bk_err_past;
    if (errors.date || errors.time || errors.note) return s.bk_err_invalid;
    return s.bk_err_generic;
  }
  function genericError(res) {
    if (!res) return s.bk_err_network;
    return s.bk_err_generic;
  }

  // ---------- services search (client) ----------
  var searchForm = $("search-form");
  function renderServices(rows) {
    var grid = $("service-results");
    grid.replaceChildren();
    if (!rows.length) { grid.appendChild(el("p", "muted", s.bk_no_results)); return; }
    rows.forEach(function (service) {
      var card = el("article", "service-card booking-card");
      card.appendChild(el("p", "eyebrow", categoryLabel(service.category)));
      card.appendChild(el("h3", null, service.title));
      card.appendChild(el("p", "muted", s.bk_by + " " + service.provider_name));
      card.appendChild(el("p", "muted", service.description));
      var meta = el("p", "booking-meta-line");
      meta.appendChild(el("strong", null, priceText(service.price_sar)));
      meta.appendChild(document.createTextNode(" · " + durationText(service.duration_minutes)));
      card.appendChild(meta);
      var choose = el("button", "btn", s.bk_choose);
      choose.type = "button";
      choose.addEventListener("click", function () { openBooking(service); });
      card.appendChild(choose);
      grid.appendChild(card);
    });
  }
  function runSearch(event) {
    if (event) event.preventDefault();
    var status = $("search-status");
    var maxPrice = searchForm.max_price.value.trim();
    if (maxPrice !== "" && (!/^\d+$/.test(maxPrice) || Number(maxPrice) > 100000)) {
      setStatus(status, s.bk_err_invalid, "error");
      return;
    }
    setStatus(status, s.bk_searching);
    api.services({
      category: searchForm.category.value,
      q: searchForm.q.value.trim(),
      max_price: maxPrice,
      sort: searchForm.sort.value
    }).then(function (res) {
      if (!res.ok) { setStatus(status, s.bk_search_error, "error"); return; }
      setStatus(status, "");
      renderServices(res.data);
    }).catch(function () {
      setStatus(status, s.bk_err_network, "error");
    });
  }

  // ---------- booking a time (client) ----------
  function openBooking(service) {
    selectedService = service;
    selectedTime = "";
    show("client-panel", false);
    show("book-panel", true);
    $("book-service-name").textContent = service.title + " · " + s.bk_by + " " + service.provider_name +
      " · " + priceText(service.price_sar) + " · " + durationText(service.duration_minutes);
    var form = $("book-form");
    var today = todayLocal();
    form.date.min = today;
    form.date.max = addDays(today, MAX_DAYS);
    form.date.value = "";
    form.note.value = "";
    setStatus($("book-status"), "");
    clearSlots(s.bk_pick_date);
    updateSubmit();
    $("book-panel").scrollIntoView({ block: "start" });
  }
  function closeBooking() {
    selectedService = null;
    selectedTime = "";
    show("book-panel", false);
    show("client-panel", true);
  }
  function clearSlots(hint) {
    $("slot-list").replaceChildren();
    $("slot-hint").textContent = hint;
  }
  function updateSubmit() {
    $("book-submit").disabled = !(selectedService && $("book-form").date.value && selectedTime);
  }
  function loadSlots() {
    var date = $("book-form").date.value;
    selectedTime = "";
    updateSubmit();
    if (!date || !selectedService) { clearSlots(s.bk_pick_date); return; }
    var today = todayLocal();
    if (date < today || date > addDays(today, MAX_DAYS)) { clearSlots(s.bk_err_invalid); return; }
    clearSlots(s.bk_slots_loading);
    var requested = selectedService.id + "|" + date;
    $("book-form").dataset.request = requested;
    api.slots(selectedService.id, date).then(function (res) {
      if ($("book-form").dataset.request !== requested) return;  // a newer date was chosen meanwhile
      if (!res.ok) { clearSlots(s.bk_err_generic); return; }
      if (!res.data.length) { clearSlots(s.bk_no_slots); return; }
      $("slot-hint").textContent = "";
      var list = $("slot-list");
      res.data.forEach(function (time) {
        var button = el("button", "slot-button", clock(time));
        button.type = "button";
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", function () {
          selectedTime = time;
          Array.prototype.forEach.call(list.children, function (other) {
            other.setAttribute("aria-pressed", other === button ? "true" : "false");
          });
          updateSubmit();
        });
        list.appendChild(button);
      });
    }).catch(function () {
      clearSlots(s.bk_err_network);
    });
  }
  function submitBooking(event) {
    event.preventDefault();
    var form = $("book-form");
    var status = $("book-status");
    var note = form.note.value.trim();
    if (!selectedService || !form.date.value || !selectedTime) { setStatus(status, s.bk_err_invalid, "error"); return; }
    if (note.length > 500) { setStatus(status, s.bk_err_invalid, "error"); return; }
    $("book-submit").disabled = true;
    api.book(selectedService.id, form.date.value, selectedTime, note).then(function (res) {
      if (res.ok) {
        setStatus(status, s.bk_booked, "success");
        closeBooking();
        setStatus($("bookings-status"), s.bk_booked, "success");
        loadBookings();
        return;
      }
      setStatus(status, bookingError(res), "error");
      if (fieldErrors(res).slot) loadSlots();  // the list changed: refresh the free times
      updateSubmit();
    }).catch(function () {
      setStatus(status, s.bk_err_network, "error");
      updateSubmit();
    });
  }

  // ---------- bookings list (both roles) ----------
  // ---------- orders: direct payment, confirmations, delivery, reports ----------
  var METHOD_KEYS = ["bank_transfer", "cash", "other"];
  var REPORT_KEYS = ["no_show", "no_payment", "poor_quality", "abuse", "other"];
  function orderError(res) {
    var code = isSupabase ? sbMessage(res) : ((res.data && res.data.errors && res.data.errors.form) || "");
    var map = [["invalid_method", s.od_err_method], ["note_required", s.od_err_note], ["note_too_long", s.od_err_note],
      ["no_payment_method", s.od_err_payment_first], ["not_completed", s.od_err_delivery],
      ["already_reported", s.od_err_reported], ["not_allowed", s.od_err_not_allowed]];
    for (var i = 0; i < map.length; i++) { if (code.indexOf(map[i][0]) >= 0) return map[i][1]; }
    return s.od_err_generic;
  }
  function yesNo(flag) { return flag ? s.od_yes : s.od_not_yet; }
  var SAR_PER_USD = 3.75;  // fixed peg; the same rate is shown to the customer
  function usdOf(sar) { return (Math.round((Number(sar) / SAR_PER_USD) * 100) / 100).toFixed(2); }
  function labelled(parent, text, className) { parent.appendChild(el("p", className || "order-line", text)); }

  function orderSection(row, role) {
    var box = el("section", "order-box");
    box.setAttribute("aria-label", s.od_payment_title);
    var status = $("bookings-status");
    var amount = row.agreed_price_sar != null ? row.agreed_price_sar : row.price_sar;
    labelled(box, fill(s.od_amount, { amount: amount }), "order-amount");
    labelled(box, fill(s.od_amount_equivalent, { amount: usdOf(amount), currency: "USD" }), "order-line");
    labelled(box, fill(s.od_amount_to_pay, { amount: row.payment_currency === "USD" ? usdOf(amount) : amount,
      currency: row.payment_currency || "SAR" }), "order-line");
    labelled(box, s.od_contact_first, "order-note");
    labelled(box, s.od_payment_note, "muted order-note");

    function run(promise, done) {
      promise.then(function (res) {
        if (res.ok) { setStatus(status, done, "success"); loadBookings(); }
        else { setStatus(status, orderError(res), "error"); }
      }).catch(function () { setStatus(status, s.bk_err_network, "error"); });
    }
    function button(label, className, onClick) {
      var b = el("button", className || "btn", label);
      b.type = "button";
      b.addEventListener("click", onClick);
      return b;
    }

    // payment method (customer chooses; visible once accepted or completed)
    if (row.status === "accepted" || row.status === "completed") {
      if (role === "client" && row.status === "accepted") {
        var form = el("form", "order-method");
        var fieldset = el("fieldset", "order-options");
        fieldset.appendChild(el("legend", null, s.od_method_label));
        METHOD_KEYS.forEach(function (key, i) {
          var label = el("label", "order-option");
          var input = el("input");
          input.type = "radio"; input.name = "method-" + row.id; input.value = key;
          input.checked = row.payment_method ? row.payment_method === key : i === 0;
          label.appendChild(input);
          label.appendChild(document.createTextNode(" " + s["od_method_" + key]));
          fieldset.appendChild(label);
        });
        form.appendChild(fieldset);
        var currencyFs = el("fieldset", "order-options");
        currencyFs.appendChild(el("legend", null, s.od_currency_label));
        ["SAR", "USD"].forEach(function (code) {
          var label = el("label", "order-option");
          var input = el("input");
          input.type = "radio"; input.name = "currency-" + row.id; input.value = code;
          input.checked = (row.payment_currency || "SAR") === code;
          label.appendChild(input);
          label.appendChild(document.createTextNode(" " + s["od_currency_" + (code === "SAR" ? "sar" : "usd")]));
          currencyFs.appendChild(label);
        });
        currencyFs.appendChild(el("p", "muted order-line", s.od_currency_rate));
        form.appendChild(currencyFs);
        var noteLabel = el("label", "order-note-field", s.od_method_note_label);
        var note = el("input");
        note.type = "text"; note.maxLength = 200; note.value = row.payment_method_note || "";
        note.setAttribute("aria-label", s.od_method_note_label);
        noteLabel.appendChild(note);
        form.appendChild(noteLabel);
        var saveBtn = el("button", "btn", s.od_method_save); saveBtn.type = "submit";
        form.appendChild(saveBtn);
        form.addEventListener("submit", function (event) {
          event.preventDefault();
          var chosen = form.querySelector("input[name=method-" + row.id + "]:checked");
          var currency = form.querySelector("input[name=currency-" + row.id + "]:checked");
          run(api.setPaymentMethod(row.id, chosen ? chosen.value : "bank_transfer", note.value,
            currency ? currency.value : "SAR"), s.od_saved);
        });
        box.appendChild(form);
      } else {
        labelled(box, row.payment_method
          ? fill(s.od_method_current, { method: s["od_method_" + row.payment_method] || row.payment_method })
          : s.od_method_none);
      }

      // payment confirmations: each side separately
      labelled(box, s.od_customer_paid + ": " + yesNo(row.client_paid_at), "order-line");
      labelled(box, s.od_freelancer_received + ": " + yesNo(row.provider_received_at), "order-line");
      if (row.payment_method && role === "client" && !row.client_paid_at) {
        var paidBtn = button(s.od_confirm_paid, "btn", function () {
          run(api.confirmPayment(row.id), s.od_saved);
        });
        box.appendChild(paidBtn);
      }
      if (row.payment_method && role === "freelancer" && !row.provider_received_at) {
        box.appendChild(button(s.od_confirm_received, "btn", function () {
          run(api.confirmPayment(row.id), s.od_saved);
        }));
      }
    }

    // delivery and rating eligibility
    if (row.status === "completed") {
      var delivery = el("div", "order-delivery");
      delivery.appendChild(el("h4", null, s.od_delivery_title));
      if (role === "client") {
        if (row.delivery_confirmed_at) {
          labelled(delivery, s.od_delivery_done);
          labelled(delivery, s.od_rating_ready, "order-line");
        } else {
          labelled(delivery, s.od_delivery_pending_customer);
          delivery.appendChild(button(s.od_delivery_confirm, "btn", function () {
            run(api.confirmDelivery(row.id), s.od_saved);
          }));
          labelled(delivery, s.od_rating_after_delivery, "muted order-line");
        }
      } else {
        labelled(delivery, row.delivery_confirmed_at ? s.od_delivery_freelancer_done : s.od_delivery_waiting);
      }
      box.appendChild(delivery);
    }

    // reports and activity history (both parties)
    if (row.status !== "rejected") {
      var report = el("form", "order-report");
      report.appendChild(el("h4", null, s.od_report_title));
      var reason = el("select");
      reason.setAttribute("aria-label", s.od_report_reason);
      REPORT_KEYS.forEach(function (key) {
        var option = el("option", null, s["od_reason_" + key]);
        option.value = key;
        reason.appendChild(option);
      });
      var details = el("input");
      details.type = "text"; details.maxLength = 1000; details.placeholder = s.od_report_details;
      details.setAttribute("aria-label", s.od_report_details);
      report.appendChild(reason);
      report.appendChild(details);
      var sendBtn = el("button", "btn btn-ghost", s.od_report_send); sendBtn.type = "submit";
      report.appendChild(sendBtn);
      report.addEventListener("submit", function (event) {
        event.preventDefault();
        run(api.reportOrder(row.id, reason.value, details.value), s.od_reported);
      });
      box.appendChild(report);

      var activityBox = el("div", "order-activity");
      var toggle = button(s.od_activity_show, "btn btn-ghost", function () {
        if (!activityBox.hidden && activityBox.childNodes.length) { activityBox.hidden = true; toggle.textContent = s.od_activity_show; return; }
        api.orderActivity(row.id).then(function (res) {
          activityBox.replaceChildren();
          if (!res.ok) { activityBox.appendChild(el("p", "muted", s.od_err_generic)); }
          else if (!res.data.length) { activityBox.appendChild(el("p", "muted", s.od_activity_none)); }
          else {
            var list = el("ol", "order-events");
            res.data.forEach(function (ev) {
              var when = new Date(ev.created_at).toLocaleString(t.locale_tag || undefined);
              list.appendChild(el("li", null, (s["od_ev_" + ev.action] || ev.action) + " · " + when));
            });
            activityBox.appendChild(list);
          }
          activityBox.hidden = false;
          toggle.textContent = s.od_activity_hide;
        });
      });
      activityBox.hidden = true;
      box.appendChild(toggle);
      box.appendChild(activityBox);
    }
    return box;
  }

  function bookingCard(row, role) {
    var card = el("article", "booking-card");
    var head = el("div", "booking-head");
    head.appendChild(el("h3", null, row.service_title));
    head.appendChild(el("span", "status-badge status-" + row.status, statusLabel(row.status)));
    card.appendChild(head);

    var meta = el("dl", "booking-facts");
    function fact(label, value) {
      meta.appendChild(el("dt", null, label));
      meta.appendChild(el("dd", null, value));
    }
    fact(role === "client" ? s.bk_provider : s.bk_client, role === "client" ? row.provider_name : row.client_name);
    fact(s.bk_when, row.date + " · " + clock(row.time));
    fact(s.bk_contact, row.contact || s.bk_contact_hidden);
    fact("SAR", String(row.price_sar));
    if (row.note) fact(s.bk_note_shown, row.note);
    card.appendChild(meta);
    card.appendChild(orderSection(row, role));

    var actions = [];
    if (role === "client" && (row.status === "pending" || row.status === "accepted")) {
      actions.push(["cancel", s.bk_action_cancel]);
    }
    if (role === "freelancer" && row.status === "pending") {
      actions.push(["accept", s.bk_action_accept], ["reject", s.bk_action_reject]);
    }
    if (role === "freelancer" && row.status === "accepted") {
      actions.push(["complete", s.bk_action_complete]);
    }
    if (actions.length) {
      var bar = el("div", "actions");
      actions.forEach(function (pair) {
        var button = el("button", pair[0] === "reject" || pair[0] === "cancel" ? "btn btn-ghost" : "btn", pair[1]);
        button.type = "button";
        button.addEventListener("click", function () { runAction(row.id, pair[0]); });
        bar.appendChild(button);
      });
      card.appendChild(bar);
    }
    return card;
  }
  function runAction(bookingId, action) {
    var status = $("bookings-status");
    setStatus(status, "");
    api.action(bookingId, action).then(function (res) {
      if (res.ok) {
        setStatus(status, s.bk_action_done, "success");
        loadBookings();
      } else {
        setStatus(status, s.bk_action_error, "error");
      }
    }).catch(function () {
      setStatus(status, s.bk_err_network, "error");
    });
  }
  function loadBookings() {
    var list = $("bookings-list");
    api.bookings().then(function (res) {
      if (!res.ok) { setStatus($("bookings-status"), s.bk_err_generic, "error"); return; }
      list.replaceChildren();
      if (!res.data.length) { list.appendChild(el("p", "muted", s.bk_no_bookings)); return; }
      res.data.forEach(function (row) { list.appendChild(bookingCard(row, ME.role)); });
    }).catch(function () {
      setStatus($("bookings-status"), s.bk_err_network, "error");
    });
  }

  // ---------- services (freelancer) ----------
  var serviceForm = $("service-form");
  function resetServiceForm() {
    serviceForm.reset();
    serviceForm.elements["id"].value = "";
    $("service-form-title").textContent = s.bk_add_service;
    $("service-cancel").hidden = true;
  }
  function editService(service) {
    serviceForm.elements["id"].value = service.id;
    serviceForm.title.value = service.title;
    serviceForm.description.value = service.description;
    serviceForm.price_sar.value = service.price_sar;
    serviceForm.duration_minutes.value = service.duration_minutes;
    $("service-form-title").textContent = s.bk_edit_service;
    $("service-cancel").hidden = false;
    serviceForm.title.focus();
    serviceForm.scrollIntoView({ block: "start" });
  }
  function loadServices() {
    var list = $("services-list");
    api.myServices().then(function (res) {
      if (!res.ok) { setStatus($("services-status"), s.bk_err_generic, "error"); return; }
      list.replaceChildren();
      if (!res.data.length) { list.appendChild(el("p", "muted", s.bk_no_services)); return; }
      res.data.forEach(function (service) {
        var card = el("article", "booking-card");
        card.appendChild(el("h3", null, service.title));
        card.appendChild(el("p", "muted", priceText(service.price_sar) + " · " + durationText(service.duration_minutes)));
        var bar = el("div", "actions");
        var edit = el("button", "btn btn-ghost", s.bk_edit);
        edit.type = "button";
        edit.addEventListener("click", function () { editService(service); });
        var remove = el("button", "btn btn-ghost", s.bk_remove);
        remove.type = "button";
        remove.addEventListener("click", function () {
          if (!window.confirm(s.bk_remove_confirm)) return;
          api.removeService(service.id).then(function (r) {
            if (r.ok) { setStatus($("services-status"), s.bk_service_removed, "success"); loadServices(); }
            else setStatus($("services-status"), s.bk_err_generic, "error");
          }).catch(function () { setStatus($("services-status"), s.bk_err_network, "error"); });
        });
        bar.appendChild(edit);
        bar.appendChild(remove);
        card.appendChild(bar);
        list.appendChild(card);
      });
    }).catch(function () {
      setStatus($("services-status"), s.bk_err_network, "error");
    });
  }
  function submitService(event) {
    event.preventDefault();
    var status = $("services-status");
    var title = serviceForm.title.value.trim();
    var description = serviceForm.description.value.trim();
    var price = serviceForm.price_sar.value.trim();
    var duration = Number(serviceForm.duration_minutes.value);
    if (title.length < 3 || title.length > 100 || description.length < 10 || description.length > 1000 ||
        !/^\d+$/.test(price) || Number(price) > 100000) {
      setStatus(status, s.bk_err_invalid, "error");
      return;
    }
    var payload = { title: title, description: description, price_sar: Number(price), duration_minutes: duration };
    var id = serviceForm.elements["id"].value;
    api.saveService(id || null, payload).then(function (res) {
      if (!res.ok) {
        var limited = res.data && res.data.errors && res.data.errors.services === "limit_reached";
        setStatus(status, limited ? s.bk_err_limit : s.bk_err_invalid, "error");
        return;
      }
      setStatus(status, s.bk_service_saved, "success");
      resetServiceForm();
      loadServices();
    }).catch(function () {
      setStatus(status, s.bk_err_network, "error");
    });
  }

  // ---------- weekly hours (freelancer) ----------
  var hoursForm = $("hours-form");
  function timeOptions(select, from, to) {
    select.replaceChildren();
    for (var m = from; m <= to; m += 30) {
      var option = el("option", null, clock(hm(m % 1440)));
      if (m === 1440) option.textContent = (document.documentElement.lang === "ar") ? "١٢:٠٠ ص (منتصف الليل)" : "12:00 AM (midnight)";
      option.value = String(m);
      select.appendChild(option);
    }
  }
  function buildHoursForm() {
    for (var i = 0; i < 7; i++) {
      timeOptions(hoursForm.elements["start" + i], 0, 1410);
      timeOptions(hoursForm.elements["end" + i], 30, 1440);
      hoursForm.elements["start" + i].value = "540";
      hoursForm.elements["end" + i].value = "1020";
    }
  }
  function loadHours() {
    api.hours().then(function (res) {
      if (!res.ok) { setStatus($("hours-status"), s.bk_err_generic, "error"); return; }
      buildHoursForm();
      for (var i = 0; i < 7; i++) hoursForm.elements["open" + i].checked = false;
      res.data.forEach(function (w) {
        if (hoursForm.elements["open" + w.weekday].checked) return;  // one window per day in this screen
        hoursForm.elements["open" + w.weekday].checked = true;
        hoursForm.elements["start" + w.weekday].value = String(w.start);
        hoursForm.elements["end" + w.weekday].value = String(w.end);
      });
    }).catch(function () {
      setStatus($("hours-status"), s.bk_err_network, "error");
    });
  }
  function submitHours(event) {
    event.preventDefault();
    var status = $("hours-status");
    var windows = [];
    for (var i = 0; i < 7; i++) {
      if (!hoursForm.elements["open" + i].checked) continue;
      var start = Number(hoursForm.elements["start" + i].value);
      var end = Number(hoursForm.elements["end" + i].value);
      if (end <= start) { setStatus(status, s.bk_hours_error, "error"); return; }
      windows.push({ weekday: i, start: start, end: end });
    }
    api.saveHours(windows).then(function (res) {
      if (res.ok) { setStatus(status, s.bk_hours_saved, "success"); return; }
      var errors = fieldErrors(res);
      var overlap = errors.windows === "overlap" || sbMessage(res).indexOf("exclusion") >= 0;
      setStatus(status, overlap ? s.bk_hours_error : s.bk_err_generic, "error");
    }).catch(function () {
      setStatus(status, s.bk_err_network, "error");
    });
  }

  // ---------- wiring ----------
  function wire() {
    searchForm.addEventListener("submit", runSearch);
    $("book-form").date.addEventListener("change", loadSlots);
    $("book-form").addEventListener("submit", submitBooking);
    $("book-back").addEventListener("click", closeBooking);
    serviceForm.addEventListener("submit", submitService);
    $("service-cancel").addEventListener("click", function () { resetServiceForm(); setStatus($("services-status"), ""); });
    hoursForm.addEventListener("submit", submitHours);
  }

  function start(user) {
    ME = user;
    wire();
    if (user.role === "client") {
      show("client-panel", true);
      show("bookings-panel", true);
      runSearch(null);
      loadBookings();
    } else if (user.role === "freelancer") {
      $("bookings-title").textContent = s.bk_incoming;
      show("bookings-panel", true);
      show("services-panel", true);
      show("hours-panel", true);
      buildHoursForm();
      loadServices();
      loadHours();
      loadBookings();
    }
  }

  window.XLANORA_AUTH.me().then(function (res) {
    if (res.status === 200 && res.data && res.data.user) start(res.data.user);
  }).catch(function () { /* signed out or offline: the account page already explains it */ });
})();
