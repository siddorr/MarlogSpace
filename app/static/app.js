const state = {
  token: localStorage.getItem("desk_app_token") || "",
  me: null,
  users: [],
  desks: [],
  reservations: [],
};

const el = {
  authCard: document.getElementById("authCard"),
  appCard: document.getElementById("appCard"),
  nameInput: document.getElementById("nameInput"),
  loginBtn: document.getElementById("loginBtn"),
  authMessage: document.getElementById("authMessage"),
  sessionBadge: document.getElementById("sessionBadge"),
  logoutBtn: document.getElementById("logoutBtn"),
  dateInput: document.getElementById("dateInput"),
  slotInput: document.getElementById("slotInput"),
  deskInput: document.getElementById("deskInput"),
  bookBtn: document.getElementById("bookBtn"),
  appMessage: document.getElementById("appMessage"),
  calendarStrip: document.getElementById("calendarStrip"),
  deskMap: document.getElementById("deskMap"),
  myReservations: document.getElementById("myReservations"),
  absenceDeskInput: document.getElementById("absenceDeskInput"),
  absenceDateInput: document.getElementById("absenceDateInput"),
  absenceSlotInput: document.getElementById("absenceSlotInput"),
  absenceStateInput: document.getElementById("absenceStateInput"),
  saveAbsenceBtn: document.getElementById("saveAbsenceBtn"),
  adminPanel: document.getElementById("adminPanel"),
  adminStats: document.getElementById("adminStats"),
  adminUserName: document.getElementById("adminUserName"),
  adminUserEnabled: document.getElementById("adminUserEnabled"),
  adminUserAdmin: document.getElementById("adminUserAdmin"),
  saveUserBtn: document.getElementById("saveUserBtn"),
  adminDeskId: document.getElementById("adminDeskId"),
  adminDeskLabel: document.getElementById("adminDeskLabel"),
  adminDeskEnabled: document.getElementById("adminDeskEnabled"),
  adminDeskOwner: document.getElementById("adminDeskOwner"),
  saveDeskBtn: document.getElementById("saveDeskBtn"),
};

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function message(target, text, ok = false) {
  target.textContent = text;
  target.classList.remove("ok", "error");
  if (!text) return;
  target.classList.add(ok ? "ok" : "error");
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  headers["Content-Type"] = "application/json";
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const res = await fetch(path, { ...options, headers });
  let data = null;
  try {
    data = await res.json();
  } catch (_) {
    data = null;
  }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return data;
}

function userById(userId) {
  return state.users.find((u) => u.user_id === userId);
}

function renderSession() {
  if (!state.me) {
    el.sessionBadge.classList.add("hidden");
    return;
  }
  el.sessionBadge.classList.remove("hidden");
  el.sessionBadge.textContent = `${state.me.name} | ${state.me.is_admin ? "admin" : "user"}`;
}

function renderDesks() {
  el.deskInput.innerHTML = "";
  el.absenceDeskInput.innerHTML = "";

  state.desks.forEach((desk) => {
    const opt = document.createElement("option");
    opt.value = desk.desk_id;
    opt.textContent = `${desk.label} (${desk.desk_id.slice(0, 6)})`;
    el.deskInput.appendChild(opt);

    if (state.me && desk.owner_user_id === state.me.user_id) {
      const ownOpt = document.createElement("option");
      ownOpt.value = desk.desk_id;
      ownOpt.textContent = `${desk.label}`;
      el.absenceDeskInput.appendChild(ownOpt);
    }
  });
}

function labelForDate(dateString) {
  const d = new Date(`${dateString}T00:00:00`);
  return {
    day: d.toLocaleDateString(undefined, { weekday: "short" }),
    date: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  };
}

function isWorkday(dateString) {
  const d = new Date(`${dateString}T00:00:00`);
  const w = d.getDay();
  return w >= 0 && w <= 4;
}

function renderCalendar() {
  const start = new Date();
  el.calendarStrip.innerHTML = "";
  for (let i = 0; i < 7; i += 1) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const iso = d.toISOString().slice(0, 10);
    const l = labelForDate(iso);
    const btn = document.createElement("button");
    btn.className = `day-pill${el.dateInput.value === iso ? " active" : ""}${isWorkday(iso) ? "" : " off"}`;
    btn.innerHTML = `<small>${l.day}</small><strong>${l.date}</strong>`;
    btn.type = "button";
    btn.addEventListener("click", () => {
      el.dateInput.value = iso;
      renderCalendar();
      renderDeskMap();
    });
    el.calendarStrip.appendChild(btn);
  }
}

function renderDeskMap() {
  const selectedDate = el.dateInput.value;
  const byOwner = {};
  state.desks.forEach((desk) => {
    if (!desk.owner_user_id) return;
    const owner = userById(desk.owner_user_id);
    if (!owner) return;
    byOwner[owner.name.trim().toLowerCase()] = desk;
  });

  const namedSpotMap = {
    guy: "A1",
    tal: "A2",
    merav: "C1",
    shoval: "C2",
    frida: "C3",
    majd: "C4",
    garik: "C5",
    oren: "C6",
  };

  const spots = {
    A1: null,
    A2: null,
    B1: null,
    B2: null,
    B3: null,
    B4: null,
    C1: null,
    C2: null,
    C3: null,
    C4: null,
    C5: null,
    C6: null,
    D1: null,
    D2: null,
    D3: null,
    D4: null,
  };

  const usedDeskIds = new Set();
  Object.entries(namedSpotMap).forEach(([name, spot]) => {
    const desk = byOwner[name];
    if (desk) {
      spots[spot] = desk;
      usedDeskIds.add(desk.desk_id);
    }
  });

  const unnamedSpots = ["B1", "B2", "B3", "B4", "D1", "D2", "D3", "D4"];
  const remaining = state.desks
    .filter((d) => !usedDeskIds.has(d.desk_id))
    .sort((a, b) => a.label.localeCompare(b.label));

  unnamedSpots.forEach((spot, idx) => {
    if (remaining[idx]) {
      spots[spot] = remaining[idx];
    }
  });
  const overflowDesks = remaining.slice(unnamedSpots.length);

  function reservationFor(deskId, slot) {
    return state.reservations.find(
      (r) => r.desk_id === deskId && r.date === selectedDate && r.slot === slot
    );
  }

  function occupantLabel(reservation) {
    if (!reservation) return "Free";
    const u = userById(reservation.user_id);
    return `${u ? u.name : reservation.user_id}${reservation.auto ? " (auto)" : ""}`;
  }

  function seatState(am, pm) {
    const list = [am, pm].filter(Boolean);
    if (!list.length) return "slot-free";
    if (list.some((r) => !r.auto)) return "slot-manual";
    return "slot-auto";
  }

  function seatHtml(spotKey, fallbackLabel = "Desk") {
    const desk = spots[spotKey];
    if (!desk) {
      return `<div class="seat seat-empty"><div class="seat-title">${fallbackLabel}</div></div>`;
    }
    const owner = desk.owner_user_id ? userById(desk.owner_user_id) : null;
    const am = reservationFor(desk.desk_id, "AM");
    const pm = reservationFor(desk.desk_id, "PM");
    const cls = seatState(am, pm);
    const selectedClass = el.deskInput.value === desk.desk_id ? " seat-selected" : "";
    return `
      <div class="seat ${cls} seat-selectable${selectedClass}" data-desk-id="${desk.desk_id}">
        <div class="seat-title">${owner ? owner.name : desk.label}</div>
        <div class="seat-sub">${desk.label}</div>
        <div class="seat-line">AM: ${occupantLabel(am)}</div>
        <div class="seat-line">PM: ${occupantLabel(pm)}</div>
      </div>
    `;
  }

  function seatHtmlForDesk(desk) {
    const owner = desk.owner_user_id ? userById(desk.owner_user_id) : null;
    const am = reservationFor(desk.desk_id, "AM");
    const pm = reservationFor(desk.desk_id, "PM");
    const cls = seatState(am, pm);
    const selectedClass = el.deskInput.value === desk.desk_id ? " seat-selected" : "";
    return `
      <div class="seat ${cls} seat-selectable${selectedClass}" data-desk-id="${desk.desk_id}">
        <div class="seat-title">${owner ? owner.name : desk.label}</div>
        <div class="seat-sub">${desk.label}</div>
        <div class="seat-line">AM: ${occupantLabel(am)}</div>
        <div class="seat-line">PM: ${occupantLabel(pm)}</div>
      </div>
    `;
  }

  el.deskMap.innerHTML = `
    <div class="floorplan-grid">
      <div class="zone zone-a">
        ${seatHtml("A1", "Desk")}
        ${seatHtml("A2", "Desk")}
      </div>
      <div class="zone zone-b">
        ${seatHtml("B1")}
        ${seatHtml("B2")}
        ${seatHtml("B3")}
        ${seatHtml("B4")}
      </div>
      <div class="zone zone-c">
        ${seatHtml("C1")}
        ${seatHtml("C2")}
        ${seatHtml("C3")}
        ${seatHtml("C4")}
        ${seatHtml("C5")}
        ${seatHtml("C6")}
      </div>
      <div class="zone zone-d">
        ${seatHtml("D1")}
        ${seatHtml("D2")}
        ${seatHtml("D3")}
        ${seatHtml("D4")}
      </div>
    </div>
    ${
      overflowDesks.length
        ? `<div class="zone zone-overflow">${overflowDesks.map((desk) => seatHtmlForDesk(desk)).join("")}</div>`
        : ""
    }
  `;

  el.deskMap.querySelectorAll(".seat-selectable[data-desk-id]").forEach((node) => {
    node.addEventListener("click", () => {
      const deskId = node.getAttribute("data-desk-id");
      if (!deskId) return;
      el.deskInput.value = deskId;
      renderDeskMap();
      message(el.appMessage, "Desk selected", true);
    });
  });
}

function renderMyReservations() {
  if (!state.me) {
    el.myReservations.innerHTML = "";
    return;
  }

  const mine = state.reservations
    .filter((r) => r.user_id === state.me.user_id && !r.auto)
    .sort((a, b) => `${a.date}${a.slot}`.localeCompare(`${b.date}${b.slot}`));

  el.myReservations.innerHTML = "";
  if (!mine.length) {
    el.myReservations.innerHTML = "<li>No explicit reservations</li>";
    return;
  }

  mine.forEach((r) => {
    const desk = state.desks.find((d) => d.desk_id === r.desk_id);
    const li = document.createElement("li");
    li.innerHTML = `
      <span>${r.date} ${r.slot} | ${desk ? desk.label : r.desk_id}</span>
      <button class="btn" data-cancel="${r.reservation_id}">Cancel</button>
    `;
    el.myReservations.appendChild(li);
  });

  el.myReservations.querySelectorAll("button[data-cancel]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/reservations/${btn.dataset.cancel}`, { method: "DELETE" });
        await refreshData();
        message(el.appMessage, "Reservation cancelled", true);
      } catch (err) {
        message(el.appMessage, err.message, false);
      }
    });
  });
}

async function refreshData() {
  const start = todayISO();
  const end = new Date(Date.now() + 6 * 86400000).toISOString().slice(0, 10);
  const [me, users, desks, reservations] = await Promise.all([
    api("/api/me"),
    api("/api/users"),
    api("/api/desks"),
    api(`/api/reservations?start_date=${start}&end_date=${end}`),
  ]);
  state.me = me;
  state.users = users;
  state.desks = desks;
  state.reservations = reservations;

  renderSession();
  renderDesks();
  renderCalendar();
  renderDeskMap();
  renderMyReservations();
  renderAdmin();
}

async function loginFlow() {
  const name = el.nameInput.value.trim();
  if (!name) {
    message(el.authMessage, "Name is required", false);
    return;
  }
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    state.token = data.token;
    localStorage.setItem("desk_app_token", state.token);
    message(el.authMessage, "Logged in", true);
    await enterApp();
  } catch (err) {
    message(el.authMessage, err.message, false);
  }
}

async function enterApp() {
  try {
    await refreshData();
    el.authCard.classList.add("hidden");
    el.appCard.classList.remove("hidden");
  } catch (err) {
    state.token = "";
    localStorage.removeItem("desk_app_token");
    state.me = null;
    el.authCard.classList.remove("hidden");
    el.appCard.classList.add("hidden");
    message(el.authMessage, `Login required: ${err.message}`, false);
  }
}

function renderAdmin() {
  if (!state.me || !state.me.is_admin) {
    el.adminPanel.classList.add("hidden");
    return;
  }
  el.adminPanel.classList.remove("hidden");
  api("/api/admin/stats")
    .then((stats) => {
      el.adminStats.innerHTML = `
        <span>Total reservations: ${stats.total_reservations}</span>
        <span>Active users: ${stats.active_users}</span>
        <span>Enabled desks: ${stats.enabled_desks}</span>
      `;
    })
    .catch((err) => {
      el.adminStats.textContent = err.message;
    });
}

async function bind() {
  el.dateInput.value = todayISO();
  el.absenceDateInput.value = todayISO();
  el.slotInput.value = "FULL";
  el.absenceSlotInput.value = "FULL";

  el.loginBtn.addEventListener("click", loginFlow);

  el.bookBtn.addEventListener("click", async () => {
    try {
      await api("/api/reservations", {
        method: "POST",
        body: JSON.stringify({
          desk_id: el.deskInput.value,
          date: el.dateInput.value,
          slot: el.slotInput.value,
        }),
      });
      await refreshData();
      message(el.appMessage, "Reservation saved", true);
    } catch (err) {
      message(el.appMessage, err.message, false);
    }
  });

  el.dateInput.addEventListener("change", () => {
    renderCalendar();
    renderDeskMap();
  });

  el.saveAbsenceBtn.addEventListener("click", async () => {
    try {
      await api("/api/named-desk/absences", {
        method: "PUT",
        body: JSON.stringify({
          desk_id: el.absenceDeskInput.value,
          date: el.absenceDateInput.value,
          slot: el.absenceSlotInput.value,
          released: el.absenceStateInput.value === "true",
        }),
      });
      await refreshData();
      message(el.appMessage, "Absence state updated", true);
    } catch (err) {
      message(el.appMessage, err.message, false);
    }
  });

  el.saveUserBtn.addEventListener("click", async () => {
    try {
      await api("/api/admin/users", {
        method: "POST",
        body: JSON.stringify({
          name: el.adminUserName.value.trim(),
          enabled: el.adminUserEnabled.value === "true",
          is_admin: el.adminUserAdmin.value === "true",
        }),
      });
      await refreshData();
      message(el.appMessage, "User updated", true);
    } catch (err) {
      message(el.appMessage, err.message, false);
    }
  });

  el.saveDeskBtn.addEventListener("click", async () => {
    try {
      await api("/api/admin/desks", {
        method: "POST",
        body: JSON.stringify({
          desk_id: el.adminDeskId.value.trim() || null,
          label: el.adminDeskLabel.value.trim(),
          enabled: el.adminDeskEnabled.value === "true",
          owner_user_id: el.adminDeskOwner.value.trim() || null,
        }),
      });
      await refreshData();
      message(el.appMessage, "Desk updated", true);
    } catch (err) {
      message(el.appMessage, err.message, false);
    }
  });

  el.logoutBtn.addEventListener("click", async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (_) {
      // ignore
    }
    state.token = "";
    state.me = null;
    localStorage.removeItem("desk_app_token");
    el.authCard.classList.remove("hidden");
    el.appCard.classList.add("hidden");
    renderSession();
    message(el.authMessage, "Logged out", true);
  });

  if (state.token) {
    await enterApp();
  }
}

bind();
