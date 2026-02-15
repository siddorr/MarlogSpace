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
  emailInput: document.getElementById("emailInput"),
  otpInput: document.getElementById("otpInput"),
  requestOtpBtn: document.getElementById("requestOtpBtn"),
  verifyOtpBtn: document.getElementById("verifyOtpBtn"),
  authMessage: document.getElementById("authMessage"),
  sessionBadge: document.getElementById("sessionBadge"),
  logoutBtn: document.getElementById("logoutBtn"),
  dateInput: document.getElementById("dateInput"),
  slotInput: document.getElementById("slotInput"),
  deskInput: document.getElementById("deskInput"),
  bookBtn: document.getElementById("bookBtn"),
  appMessage: document.getElementById("appMessage"),
  deskTableBody: document.querySelector("#deskTable tbody"),
  myReservations: document.getElementById("myReservations"),
  absenceDeskInput: document.getElementById("absenceDeskInput"),
  absenceDateInput: document.getElementById("absenceDateInput"),
  absenceSlotInput: document.getElementById("absenceSlotInput"),
  absenceStateInput: document.getElementById("absenceStateInput"),
  saveAbsenceBtn: document.getElementById("saveAbsenceBtn"),
  adminPanel: document.getElementById("adminPanel"),
  adminStats: document.getElementById("adminStats"),
  adminUserEmail: document.getElementById("adminUserEmail"),
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
  el.sessionBadge.textContent = `${state.me.email} | ${state.me.is_admin ? "admin" : "user"}`;
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

function renderSchedule() {
  const selectedDate = el.dateInput.value;
  const rows = state.desks
    .slice()
    .sort((a, b) => a.label.localeCompare(b.label))
    .map((desk) => {
      const am = state.reservations.find(
        (r) => r.desk_id === desk.desk_id && r.date === selectedDate && r.slot === "AM"
      );
      const pm = state.reservations.find(
        (r) => r.desk_id === desk.desk_id && r.date === selectedDate && r.slot === "PM"
      );
      return { desk, am, pm };
    });

  el.deskTableBody.innerHTML = "";
  rows.forEach(({ desk, am, pm }) => {
    const tr = document.createElement("tr");
    const amUser = am ? userById(am.user_id) : null;
    const pmUser = pm ? userById(pm.user_id) : null;
    tr.innerHTML = `
      <td>${desk.label}</td>
      <td>${am ? `${amUser ? amUser.email : am.user_id}${am.auto ? " (auto)" : ""}` : "-"}</td>
      <td>${pm ? `${pmUser ? pmUser.email : pm.user_id}${pm.auto ? " (auto)" : ""}` : "-"}</td>
    `;
    el.deskTableBody.appendChild(tr);
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
  renderSchedule();
  renderMyReservations();
  renderAdmin();
}

async function loginFlow() {
  const email = el.emailInput.value.trim();
  const code = el.otpInput.value.trim();
  if (!email || !code) {
    message(el.authMessage, "Email and OTP are required", false);
    return;
  }
  try {
    const data = await api("/api/auth/verify-otp", {
      method: "POST",
      body: JSON.stringify({ email, code }),
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

  el.requestOtpBtn.addEventListener("click", async () => {
    const email = el.emailInput.value.trim();
    if (!email) {
      message(el.authMessage, "Email is required", false);
      return;
    }
    try {
      await api("/api/auth/request-otp", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      message(el.authMessage, "OTP requested. Check your email or server log.", true);
    } catch (err) {
      message(el.authMessage, err.message, false);
    }
  });

  el.verifyOtpBtn.addEventListener("click", loginFlow);

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

  el.dateInput.addEventListener("change", renderSchedule);

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
          email: el.adminUserEmail.value.trim(),
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
