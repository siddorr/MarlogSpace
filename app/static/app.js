const state = {
  token: localStorage.getItem("marlogspace_token") || "",
  me: null,
  locations: [],
  floors: [],
  desks: [],
  bookings: [],
  notifications: [],
  recurring: [],
  whitelist: [],
  audit: [],
  stats: null,
  activeTab: "map",
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
  tabBar: document.getElementById("tabBar"),
  appMessage: document.getElementById("appMessage"),
  locationInput: document.getElementById("locationInput"),
  floorInput: document.getElementById("floorInput"),
  dateInput: document.getElementById("dateInput"),
  slotInput: document.getElementById("slotInput"),
  deskMap: document.getElementById("deskMap"),
  bookingList: document.getElementById("bookingList"),
  notificationList: document.getElementById("notificationList"),
  releaseDeskInput: document.getElementById("releaseDeskInput"),
  releaseDateInput: document.getElementById("releaseDateInput"),
  releaseSlotInput: document.getElementById("releaseSlotInput"),
  saveReleaseBtn: document.getElementById("saveReleaseBtn"),
  recurringDeskInput: document.getElementById("recurringDeskInput"),
  weekdayInput: document.getElementById("weekdayInput"),
  recurringSlotInput: document.getElementById("recurringSlotInput"),
  saveRecurringBtn: document.getElementById("saveRecurringBtn"),
  recurringList: document.getElementById("recurringList"),
  adminStats: document.getElementById("adminStats"),
  whitelistEmail: document.getElementById("whitelistEmail"),
  saveWhitelistBtn: document.getElementById("saveWhitelistBtn"),
  whitelistList: document.getElementById("whitelistList"),
  deskIdInput: document.getElementById("deskIdInput"),
  deskLabelInput: document.getElementById("deskLabelInput"),
  deskOwnerInput: document.getElementById("deskOwnerInput"),
  deskXInput: document.getElementById("deskXInput"),
  deskYInput: document.getElementById("deskYInput"),
  saveDeskBtn: document.getElementById("saveDeskBtn"),
  auditList: document.getElementById("auditList"),
};

const screens = ["map", "bookings", "release", "notifications", "admin"];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function message(target, text, ok = false) {
  target.textContent = text;
  target.classList.remove("ok", "error");
  if (text) target.classList.add(ok ? "ok" : "error");
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  headers["Content-Type"] = "application/json";
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`);
  return data;
}

function persistToken() {
  if (state.token) localStorage.setItem("marlogspace_token", state.token);
  else localStorage.removeItem("marlogspace_token");
}

function tabsForRole() {
  const base = [
    { id: "map", label: "Office Map" },
    { id: "bookings", label: "Bookings" },
    { id: "release", label: "Releases" },
    { id: "notifications", label: "Notifications" },
  ];
  if (state.me?.is_admin) base.push({ id: "admin", label: "Admin" });
  return base;
}

function renderTabs() {
  el.tabBar.innerHTML = "";
  tabsForRole().forEach((tab) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `btn${state.activeTab === tab.id ? " btn-primary" : ""}`;
    button.textContent = tab.label;
    button.addEventListener("click", () => {
      state.activeTab = tab.id;
      renderTabs();
      renderScreens();
    });
    el.tabBar.appendChild(button);
  });
}

function renderScreens() {
  screens.forEach((id) => {
    const node = document.getElementById(`screen-${id}`);
    if (!node) return;
    node.classList.toggle("hidden", state.activeTab !== id);
  });
}

function renderSession() {
  if (!state.me) {
    el.sessionBadge.classList.add("hidden");
    el.logoutBtn.classList.add("hidden");
    return;
  }
  el.sessionBadge.classList.remove("hidden");
  el.logoutBtn.classList.remove("hidden");
  el.sessionBadge.textContent = `${state.me.name} | ${state.me.is_admin ? "admin" : "user"} | ${state.me.email}`;
}

function fillSelect(select, items, valueKey, labelKey) {
  const current = select.value;
  select.innerHTML = "";
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item[valueKey];
    option.textContent = item[labelKey];
    select.appendChild(option);
  });
  if (current && items.some((item) => item[valueKey] === current)) {
    select.value = current;
  }
}

function deskLabel(item) {
  return `${item.label}${item.owner_user_id ? ` | owner ${item.owner_user_id.slice(0, 6)}` : ""}`;
}

function stateClass(item) {
  return {
    free: "slot-free",
    pending: "slot-pending",
    booked: "slot-manual",
    owned: "slot-auto",
    blocked: "slot-blocked",
  }[item.state] || "slot-free";
}

function renderDeskMap() {
  el.deskMap.innerHTML = "";
  if (!state.desks.length) {
    el.deskMap.textContent = "No desks on this floor";
    return;
  }
  const maxX = Math.max(...state.desks.map((desk) => desk.x), 0) + 28;
  const maxY = Math.max(...state.desks.map((desk) => desk.y), 0) + 22;
  el.deskMap.style.minHeight = `${Math.max(maxY * 4, 320)}px`;
  el.deskMap.style.setProperty("--map-width", `${maxX}`);
  state.desks.forEach((desk) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `seat map-seat ${stateClass(desk)}`;
    card.style.left = `${desk.x}%`;
    card.style.top = `${desk.y}%`;
    card.innerHTML = `
      <div class="seat-title">${desk.label}</div>
      <div class="seat-sub">${desk.state}</div>
      <div class="seat-line">${desk.owner_user_id ? `owner ${desk.owner_user_id.slice(0, 6)}` : "shared desk"}</div>
      <div class="seat-line">${desk.pending_request_count ? `${desk.pending_request_count} pending` : "ready"}</div>
    `;
    card.addEventListener("click", () => createBooking(desk.desk_id));
    el.deskMap.appendChild(card);
  });
}

function renderBookings() {
  el.bookingList.innerHTML = "";
  if (!state.bookings.length) {
    el.bookingList.innerHTML = "<li>No bookings yet</li>";
    return;
  }
  state.bookings.forEach((booking) => {
    const row = document.createElement("li");
    row.innerHTML = `<span>${booking.date} | ${booking.slot} | ${booking.status}</span>`;
    const actions = document.createElement("div");
    const cancelBtn = document.createElement("button");
    cancelBtn.className = "btn";
    cancelBtn.textContent = "Cancel";
    cancelBtn.addEventListener("click", async () => {
      await api(`/api/bookings/${booking.booking_id}/cancel`, { method: "POST" });
      await refreshApp();
    });
    actions.appendChild(cancelBtn);
    if (state.me?.is_admin && booking.status === "pending") {
      const approveBtn = document.createElement("button");
      approveBtn.className = "btn btn-primary";
      approveBtn.textContent = "Approve";
      approveBtn.addEventListener("click", async () => {
        await api(`/api/bookings/${booking.booking_id}/approve`, { method: "POST" });
        await refreshApp();
      });
      actions.appendChild(approveBtn);
    }
    row.appendChild(actions);
    el.bookingList.appendChild(row);
  });
}

function renderNotifications() {
  el.notificationList.innerHTML = "";
  if (!state.notifications.length) {
    el.notificationList.innerHTML = "<li>No notifications</li>";
    return;
  }
  state.notifications.forEach((item) => {
    const row = document.createElement("li");
    row.innerHTML = `<span>${item.message}</span>`;
    const button = document.createElement("button");
    button.className = "btn";
    button.textContent = item.read_at ? "Read" : "Mark Read";
    button.disabled = Boolean(item.read_at);
    button.addEventListener("click", async () => {
      await api(`/api/notifications/${item.notification_id}/read`, { method: "POST" });
      await refreshApp();
    });
    row.appendChild(button);
    el.notificationList.appendChild(row);
  });
}

function renderRecurring() {
  el.recurringList.innerHTML = "";
  state.recurring.forEach((item) => {
    const row = document.createElement("li");
    row.textContent = `${item.desk_id.slice(0, 6)} | weekday ${item.weekday} | ${item.slot}`;
    el.recurringList.appendChild(row);
  });
}

function renderAdmin() {
  el.adminStats.innerHTML = "";
  if (state.stats) {
    Object.entries(state.stats).forEach(([key, value]) => {
      const chip = document.createElement("span");
      chip.textContent = `${key}: ${value}`;
      el.adminStats.appendChild(chip);
    });
  }

  el.whitelistList.innerHTML = "";
  state.whitelist.forEach((item) => {
    const row = document.createElement("li");
    row.innerHTML = `<span>${item.email}</span>`;
    const button = document.createElement("button");
    button.className = "btn";
    button.textContent = "Delete";
    button.addEventListener("click", async () => {
      await api(`/api/admin/whitelist/${item.whitelist_id}`, { method: "DELETE" });
      await refreshApp();
    });
    row.appendChild(button);
    el.whitelistList.appendChild(row);
  });

  el.auditList.innerHTML = "";
  state.audit.slice(0, 30).forEach((item) => {
    const row = document.createElement("li");
    row.textContent = `${item.timestamp} | ${item.action} | ${item.details}`;
    el.auditList.appendChild(row);
  });
}

function renderOwnedDeskInputs() {
  const owned = state.desks.filter((desk) => desk.owner_user_id === state.me?.user_id);
  const fallback = state.me?.is_admin ? state.desks : owned;
  fillSelect(el.releaseDeskInput, fallback, "desk_id", "label");
  fillSelect(el.recurringDeskInput, fallback, "desk_id", "label");
}

async function createBooking(deskId) {
  try {
    const booking = await api("/api/bookings", {
      method: "POST",
      body: JSON.stringify({
        desk_id: deskId,
        date: el.dateInput.value,
        slot: el.slotInput.value,
      }),
    });
    message(el.appMessage, `Booking ${booking.status}`, true);
    await refreshApp();
  } catch (error) {
    message(el.appMessage, error.message);
  }
}

async function refreshFloors() {
  if (!el.locationInput.value) return;
  state.floors = await api(`/api/floors?location_id=${encodeURIComponent(el.locationInput.value)}`);
  fillSelect(el.floorInput, state.floors, "floor_id", "name");
}

async function refreshDesks() {
  if (!el.floorInput.value || !el.dateInput.value) return;
  const params = new URLSearchParams({
    location_id: el.locationInput.value,
    floor_id: el.floorInput.value,
    date: el.dateInput.value,
  });
  state.desks = await api(`/api/desks?${params.toString()}`);
}

async function refreshApp() {
  if (!state.token) return;
  state.me = await api("/api/auth/session");
  state.locations = await api("/api/locations");
  fillSelect(el.locationInput, state.locations, "location_id", "name");
  await refreshFloors();
  await refreshDesks();
  state.bookings = await api("/api/bookings");
  state.notifications = await api("/api/notifications");
  state.recurring = await api("/api/desk-releases/recurring");
  if (state.me.is_admin) {
    state.stats = await api("/api/admin/stats");
    state.whitelist = await api("/api/admin/whitelist");
    state.audit = await api("/api/admin/audit-log");
  } else {
    state.stats = null;
    state.whitelist = [];
    state.audit = [];
  }
  renderSession();
  renderTabs();
  renderScreens();
  renderDeskMap();
  renderBookings();
  renderNotifications();
  renderRecurring();
  renderOwnedDeskInputs();
  renderAdmin();
  el.authCard.classList.add("hidden");
  el.appCard.classList.remove("hidden");
}

async function initializeSession() {
  el.dateInput.value = todayISO();
  el.releaseDateInput.value = todayISO();
  if (!state.token) return;
  try {
    await refreshApp();
  } catch (_) {
    state.token = "";
    persistToken();
  }
}

el.requestOtpBtn.addEventListener("click", async () => {
  try {
    await api("/api/auth/request-otp", {
      method: "POST",
      body: JSON.stringify({ email: el.emailInput.value }),
    });
    message(el.authMessage, "OTP sent. Check configured email or server log.", true);
  } catch (error) {
    message(el.authMessage, error.message);
  }
});

el.verifyOtpBtn.addEventListener("click", async () => {
  try {
    const result = await api("/api/auth/verify-otp", {
      method: "POST",
      body: JSON.stringify({ email: el.emailInput.value, code: el.otpInput.value }),
    });
    state.token = result.token;
    persistToken();
    await refreshApp();
    message(el.authMessage, "", true);
  } catch (error) {
    message(el.authMessage, error.message);
  }
});

el.logoutBtn.addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (_) {
    // Ignore server logout failures during local cleanup.
  }
  state.token = "";
  state.me = null;
  persistToken();
  el.authCard.classList.remove("hidden");
  el.appCard.classList.add("hidden");
  renderSession();
});

el.locationInput.addEventListener("change", async () => {
  await refreshFloors();
  await refreshDesks();
  renderDeskMap();
});

el.floorInput.addEventListener("change", async () => {
  await refreshDesks();
  renderDeskMap();
});

el.dateInput.addEventListener("change", async () => {
  await refreshDesks();
  renderDeskMap();
});

el.saveReleaseBtn.addEventListener("click", async () => {
  try {
    await api("/api/desk-releases/manual", {
      method: "POST",
      body: JSON.stringify({
        desk_id: el.releaseDeskInput.value,
        date: el.releaseDateInput.value,
        slot: el.releaseSlotInput.value,
        released: true,
      }),
    });
    await refreshApp();
  } catch (error) {
    message(el.appMessage, error.message);
  }
});

el.saveRecurringBtn.addEventListener("click", async () => {
  try {
    await api("/api/desk-releases/recurring", {
      method: "POST",
      body: JSON.stringify({
        desk_id: el.recurringDeskInput.value,
        weekday: Number(el.weekdayInput.value),
        slot: el.recurringSlotInput.value,
        is_active: true,
      }),
    });
    await refreshApp();
  } catch (error) {
    message(el.appMessage, error.message);
  }
});

el.saveWhitelistBtn.addEventListener("click", async () => {
  try {
    await api("/api/admin/whitelist", {
      method: "POST",
      body: JSON.stringify({ email: el.whitelistEmail.value }),
    });
    el.whitelistEmail.value = "";
    await refreshApp();
  } catch (error) {
    message(el.appMessage, error.message);
  }
});

el.saveDeskBtn.addEventListener("click", async () => {
  try {
    await api("/api/admin/desks", {
      method: "POST",
      body: JSON.stringify({
        desk_id: el.deskIdInput.value || null,
        floor_id: el.floorInput.value,
        label: el.deskLabelInput.value,
        owner_user_id: el.deskOwnerInput.value || null,
        enabled: true,
        is_blocked: false,
        x: Number(el.deskXInput.value),
        y: Number(el.deskYInput.value),
        zone: null,
        equipment: {},
      }),
    });
    await refreshApp();
  } catch (error) {
    message(el.appMessage, error.message);
  }
});

initializeSession();
