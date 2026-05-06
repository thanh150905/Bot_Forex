const state = {
  token: localStorage.getItem("user_token") || "",
  authMode: "login",
  pendingRegisterEmail: "",
  pendingRegisterPassword: "",
  pendingResetEmail: "",
  currentView: "overview",
  summary: null,
  profile: null,
  accounts: [],
  editingAccountId: null,
  trades: [],
  sessions: [],
  commands: [],
  runtimeStatuses: [],
  notifications: [],
  seenNotifications: new Set(JSON.parse(localStorage.getItem("user_seen_notifications") || "[]")),
  filters: {
    trades: "",
    tradeStatus: "",
    tradeSide: "",
  },
};

const pageMeta = {
  overview: ["Tổng quan", "Theo dõi bot và lệnh giao dịch của bạn."],
  accounts: ["Tài khoản MT5", "User tự thêm, tự bật chạy và tự dừng bot máy khách."],
  trades: ["Lệnh giao dịch", "Lịch sử lệnh do bot báo cáo về server."],
  notifications: ["Thông báo", "Hoạt động mới từ tài khoản, lệnh, bot và command."],
  profile: ["Hồ sơ", "Cập nhật thông tin tài khoản và bảo mật."],
  sessions: ["Phiên bot", "Các lần bot xác thực hoặc bị từ chối."],
};

const $ = (selector) => document.querySelector(selector);

function ensureDeviceId() {
  let id = localStorage.getItem("portal_device_id");
  if (id) return id;
  const bytes = new Uint8Array(24);
  window.crypto.getRandomValues(bytes);
  id = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  localStorage.setItem("portal_device_id", id);
  return id;
}

function deviceName() {
  const platform = navigator.userAgentData?.platform || navigator.platform || "Unknown";
  return `${platform} | ${navigator.userAgent.slice(0, 90)}`;
}

function authHeaders() {
  return {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${state.token}`,
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}

function money(value) {
  if (value === null || value === undefined) return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return "-";
  return `${number >= 0 ? "+" : ""}$${number.toFixed(2)}`;
}

function plainMoney(value) {
  if (value === null || value === undefined) return "$0.00";
  const number = Number(value);
  if (Number.isNaN(number)) return "$0.00";
  return `$${number.toFixed(2)}`;
}

function shortKey(value) {
  const text = String(value || "-");
  if (text.length <= 14) return text;
  return `${text.slice(0, 8)}...${text.slice(-4)}`;
}

function saveSeenNotifications() {
  localStorage.setItem("user_seen_notifications", JSON.stringify(Array.from(state.seenNotifications).slice(0, 80)));
}

function activityMarkup(item) {
  const severity = safeSeverity(item.severity);
  return `
    <div class="activity-row ${severity}">
      <strong>${escapeHtml(item.title || item.type || "Thông báo")}</strong>
      <small>${escapeHtml(item.message || "-")}</small>
      <small>${formatDate(item.created_at)}</small>
    </div>
  `;
}

function secondsText(value) {
  if (value === null || value === undefined) return "chưa từng kết nối";
  const number = Number(value);
  if (number < 60) return `${number}s trước`;
  if (number < 3600) return `${Math.floor(number / 60)} phút trước`;
  if (number < 86400) return `${Math.floor(number / 3600)} giờ trước`;
  return `${Math.floor(number / 86400)} ngày trước`;
}

function includesText(row, query) {
  if (!query) return true;
  return JSON.stringify(row).toLowerCase().includes(query.toLowerCase());
}

function safeSeverity(severity) {
  return ["ok", "warn", "bad"].includes(severity) ? severity : "ok";
}

function runtimeStateLabel(status) {
  return {
    hold: "Đang chờ",
    skipped: "Bị chặn",
    opened: "Đã vào lệnh",
    dry_run: "Dry run",
    rejected: "MT5 từ chối",
    error: "Lỗi",
    paused: "Tạm dừng",
    ready: "Sẵn sàng",
  }[status] || status || "-";
}

function signalBadge(signal) {
  const value = String(signal || "HOLD").toUpperCase();
  const cls = value === "BUY" ? "ok" : value === "SELL" ? "warn" : "";
  return `<span class="pill ${cls}">${escapeHtml(value)}</span>`;
}

function severityText(severity) {
  return {
    ok: "OK",
    warn: "CẢNH BÁO",
    bad: "LỖI",
  }[safeSeverity(severity)];
}

function showToast(message, severity = "ok") {
  const stack = $("#toastStack");
  if (!stack) return;
  const safe = safeSeverity(severity);
  const card = document.createElement("div");
  const label = document.createElement("span");
  const copy = document.createElement("div");
  const progress = document.createElement("span");
  card.className = `toast-card ${safe}`;
  card.setAttribute("role", "status");
  label.className = "toast-kind";
  label.textContent = severityText(safe);
  copy.textContent = message;
  progress.className = "toast-progress";
  card.append(label, copy, progress);
  stack.prepend(card);
  Array.from(stack.querySelectorAll(".toast-card")).slice(4).forEach((item) => item.remove());
  window.setTimeout(() => card.classList.add("closing"), 3600);
  window.setTimeout(() => card.remove(), 4100);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(options.auth === false ? {"Content-Type": "application/json"} : authHeaders()),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (options.auth !== false && (response.status === 401 || response.status === 403)) {
      logout(false);
    }
    throw new Error(data.detail || data.message || `HTTP ${response.status}`);
  }
  return data;
}

function setLoggedIn(loggedIn) {
  $("#loginPanel").classList.toggle("hidden", loggedIn);
  $("#content").classList.toggle("hidden", !loggedIn);
  $("#logoutBtn").classList.toggle("hidden", !loggedIn);
  $("#refreshBtn").disabled = !loggedIn;
  $("#portalStatus").textContent = loggedIn ? "Đã đăng nhập" : "Chưa đăng nhập";
  $("#portalStatusDot").classList.toggle("ok", loggedIn);
}

const authMeta = {
  login: ["Đăng nhập khách hàng", "Đăng nhập bằng email và mật khẩu đã đăng ký."],
  register: ["Đăng ký tài khoản", "Tạo mật khẩu rồi nhận mã xác thực qua email."],
  registerVerify: ["Xác thực đăng ký", "Nhập mã 6 số đã gửi về email để hoàn tất đăng ký."],
  forgot: ["Quên mật khẩu", "Nhập email tài khoản để nhận mã đặt lại mật khẩu."],
  reset: ["Đặt lại mật khẩu", "Nhập mã reset và mật khẩu mới của bạn."],
};

function setAuthMode(mode) {
  state.authMode = mode;
  const [title, subtitle] = authMeta[mode] || authMeta.login;
  $("#authTitle").textContent = title;
  $("#authSubtitle").textContent = subtitle;

  const visibleForm = {
    login: "userLoginForm",
    register: "userRegisterForm",
    registerVerify: "userRegisterVerifyForm",
    forgot: "forgotPasswordForm",
    reset: "resetPasswordForm",
  }[mode] || "userLoginForm";

  document.querySelectorAll(".auth-form").forEach((form) => {
    form.classList.toggle("hidden", form.id !== visibleForm);
  });
  document.querySelectorAll(".auth-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.authMode === (mode === "registerVerify" ? "register" : mode));
  });

  const firstInput = $(`#${visibleForm} input`);
  if (firstInput) firstInput.focus();
}

function clearAuthMessages() {
  [
    "#userLoginMessage",
    "#userRegisterMessage",
    "#userRegisterVerifyMessage",
    "#forgotPasswordMessage",
    "#resetPasswordMessage",
  ].forEach((selector) => {
    const node = $(selector);
    if (node) node.textContent = "";
  });
}

function resetAuthFlow() {
  state.pendingRegisterEmail = "";
  state.pendingRegisterPassword = "";
  state.pendingResetEmail = "";
  clearAuthMessages();
  ["#userRegisterVerifyForm", "#resetPasswordForm"].forEach((selector) => {
    const form = $(selector);
    if (form) form.reset();
  });
  setAuthMode("login");
}

function setView(view) {
  state.currentView = view;
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("hidden", section.id !== `view-${view}`);
  });
  const [title, subtitle] = pageMeta[view] || pageMeta.overview;
  $("#pageTitle").textContent = title;
  $("#pageSubtitle").textContent = subtitle;
}

function statusLabel(status) {
  return {
    stopped: "Đã dừng",
    waiting_client: "Chờ máy khách",
    pending_start: "Chờ chạy",
    running: "Đang chạy",
    paused: "Tạm dừng",
    pending_stop: "Chờ dừng",
    pending_restart: "Chờ restart",
    error: "Lỗi",
  }[status] || status || "-";
}

function accountActionButtons(account) {
  const isRunning = account.is_active && ["waiting_client", "pending_start", "pending_restart", "running"].includes(account.run_status);
  const primaryAction = isRunning ? "stop" : "start";
  const primaryText = isRunning ? "Dừng" : "Run";
  return `
    <div class="row-actions">
      <button class="small-button ${isRunning ? "danger" : ""}" data-account-command="${account.id}" data-action="${primaryAction}">${primaryText}</button>
      <button class="small-button" data-account-command="${account.id}" data-action="restart">Restart</button>
      <button class="small-button" data-account-edit="${account.id}">Sửa</button>
    </div>
  `;
}

function renderSummary() {
  const data = state.summary;
  if (!data) return;
  const stats = data.stats || {};
  const license = data.license || {};
  const online = Boolean(license.online);
  const firstAccount = state.accounts[0];

  $("#botState").textContent = online ? "Online" : "Offline";
  $("#botSeen").textContent = secondsText(license.seconds_since_seen);
  $("#accountCount").textContent = String(stats.mt5_accounts || 0);
  $("#accountMode").textContent = firstAccount ? `${firstAccount.dry_run ? "Dry run" : "Live"} | ${firstAccount.symbols}` : "-";
  $("#openTrades").textContent = String(stats.open_trades || 0);
  $("#totalTrades").textContent = `${stats.total_trades || 0} tổng`;
  $("#closedProfit").textContent = money(stats.closed_profit || 0);
  $("#closedTrades").textContent = `${stats.closed_trades || 0} đã đóng`;
  $("#todayProfit").textContent = money(stats.today_profit || 0);
  $("#pendingCommands").textContent = String(stats.pending_commands || 0);
  $("#winRate").textContent = `${Number(stats.win_rate || 0).toFixed(1)}%`;
  $("#winRateDetail").textContent = `${stats.winning_trades || 0} thắng / ${stats.closed_trades || 0} đóng`;
  $("#profitFactor").textContent = stats.profit_factor === null || stats.profit_factor === undefined ? "-" : Number(stats.profit_factor).toFixed(2);
  $("#grossProfitLoss").textContent = `${plainMoney(stats.gross_profit || 0)} / ${plainMoney(Math.abs(stats.gross_loss || 0))}`;
  $("#totalLot").textContent = Number(stats.total_lot || 0).toFixed(2);
  $("#openLot").textContent = `${Number(stats.open_lot || 0).toFixed(2)} đang mở`;
  $("#closedPips").textContent = Number(stats.closed_pips || 0).toFixed(1);
  $("#latestTrade").textContent = stats.latest_trade
    ? `${stats.latest_trade.symbol} ${stats.latest_trade.direction} ${formatDate(stats.latest_trade.opened_at)}`
    : "Chưa có lệnh";

  $("#licenseOnlineBadge").textContent = online ? "Online" : "Offline";
  $("#licenseInfo").innerHTML = `
    <div><span>License</span><strong>${escapeHtml(shortKey(license.license_key))}</strong></div>
    <div><span>IP lock</span><strong>${escapeHtml(license.allowed_ip || "chưa lock")}</strong></div>
    <div><span>MT Account</span><strong>${escapeHtml(license.mt_account || "-")}</strong></div>
    <div><span>Lần thấy cuối</span><strong>${formatDate(license.last_verified)}</strong></div>
  `;

  const symbols = stats.symbols || [];
  $("#symbolStatsCount").textContent = String(symbols.length);
  $("#symbolStatsList").innerHTML = symbols.length ? symbols.map((row) => `
    <div class="metric-row">
      <div>
        <strong>${escapeHtml(row.symbol)}</strong>
        <small>${row.total || 0} lệnh | ${Number(row.lot || 0).toFixed(2)} lot</small>
      </div>
      <strong>${money(row.profit || 0)}</strong>
    </div>
  `).join("") : `<div class="empty-state compact">Chưa có dữ liệu symbol</div>`;
}

function renderProfile() {
  const profile = state.profile;
  if (!profile) return;
  const user = profile.user || {};
  const license = profile.license || {};
  $("#profileStatus").textContent = license.online ? "Online" : "Offline";
  $("#profileInfo").innerHTML = `
    <div><span>Email</span><strong>${escapeHtml(user.email || "-")}</strong></div>
    <div><span>Tên hiển thị</span><strong>${escapeHtml(user.username || "-")}</strong></div>
    <div><span>Ngày tạo</span><strong>${formatDate(user.created_at)}</strong></div>
    <div><span>License</span><strong>${escapeHtml(shortKey(license.license_key))}</strong></div>
    <div><span>Hạn tài khoản</span><strong>${formatDate(user.expires_at)}</strong></div>
    <div><span>Ghi chú</span><strong>${escapeHtml(user.note || "-")}</strong></div>
  `;
  const form = $("#profileForm");
  if (form && document.activeElement?.form !== form) {
    form.elements.username.value = user.username || "";
    form.elements.note.value = user.note || "";
  }
}

function renderNotifications(toastNew = false) {
  const items = state.notifications || [];
  $("#notificationsCount").textContent = String(items.length);
  $("#activityCount").textContent = String(Math.min(items.length, 8));
  $("#notificationsList").innerHTML = items.length
    ? items.map(activityMarkup).join("")
    : `<div class="empty-state compact">Chưa có thông báo</div>`;
  $("#activityList").innerHTML = items.length
    ? items.slice(0, 8).map(activityMarkup).join("")
    : `<div class="empty-state compact">Chưa có hoạt động mới</div>`;

  if (toastNew) {
    items.slice(0, 6).reverse().forEach((item) => {
      if (!state.seenNotifications.has(item.id)) {
        state.seenNotifications.add(item.id);
        showToast(item.title || "Thông báo mới", item.severity || "ok");
      }
    });
    saveSeenNotifications();
  } else {
    items.slice(0, 20).forEach((item) => state.seenNotifications.add(item.id));
    saveSeenNotifications();
  }
}

function renderAccounts() {
  $("#accountsCount").textContent = String(state.accounts.length);
  const table = $("#accountsTable");
  if (!state.accounts.length) {
    table.innerHTML = `<tr><td colspan="7"><div class="empty-state compact">Chưa có tài khoản MT5</div></td></tr>`;
    return;
  }
  table.innerHTML = state.accounts.map((account) => `
    <tr>
      <td>${escapeHtml(account.label || `MT5 #${account.id}`)}<br><span class="muted">${escapeHtml(account.broker || "-")}</span></td>
      <td>${escapeHtml(account.mt_login)}<br><span class="muted">${escapeHtml(account.mt_server)}</span></td>
      <td>${escapeHtml(account.symbols)}<br><span class="muted">${escapeHtml(account.timeframe || "-")}</span></td>
      <td>${Number(account.lot_size || 0).toFixed(2)}<br><span class="muted">Max ${account.max_total_positions}</span></td>
      <td><span class="badge">${escapeHtml(statusLabel(account.run_status))}</span><br><span class="muted">${account.dry_run ? "Dry run" : "Live thật"}</span></td>
      <td>${formatDate(account.updated_at)}<br><span class="muted">${escapeHtml(account.last_error || "")}</span></td>
      <td>
        ${accountActionButtons(account)}
        <span class="muted">${escapeHtml(account.note || "")}</span>
      </td>
    </tr>
  `).join("");
}

function filteredTrades() {
  return state.trades
    .filter((trade) => !state.filters.tradeStatus || trade.status === state.filters.tradeStatus)
    .filter((trade) => !state.filters.tradeSide || trade.direction === state.filters.tradeSide)
    .filter((trade) => includesText(trade, state.filters.trades));
}

function renderTrades() {
  const rows = filteredTrades();
  $("#tradesCount").textContent = `${rows.length}/${state.trades.length}`;
  const table = $("#tradesTable");
  if (!rows.length) {
    table.innerHTML = `<tr><td colspan="9"><div class="empty-state compact">Chưa có lệnh giao dịch</div></td></tr>`;
    return;
  }
  table.innerHTML = rows.map((trade) => `
    <tr>
      <td>${escapeHtml(trade.ticket)}</td>
      <td>${escapeHtml(trade.symbol)}</td>
      <td><span class="badge">${escapeHtml(trade.direction)}</span></td>
      <td>${escapeHtml(trade.status)}</td>
      <td>${escapeHtml(trade.entry_price)}</td>
      <td>${escapeHtml(trade.sl_price || "-")} / ${escapeHtml(trade.tp_price || "-")}</td>
      <td>${money(trade.profit)}<br><span class="muted">${trade.pips ?? "-"} pips</span></td>
      <td>${formatDate(trade.opened_at)}</td>
      <td>${escapeHtml(trade.note || "-")}</td>
    </tr>
  `).join("");
}

function renderSessions() {
  $("#sessionsCount").textContent = String(state.sessions.length);
  const table = $("#sessionsTable");
  if (!state.sessions.length) {
    table.innerHTML = `<tr><td colspan="5"><div class="empty-state compact">Chưa có phiên bot</div></td></tr>`;
    return;
  }
  table.innerHTML = state.sessions.map((session) => `
    <tr>
      <td>${formatDate(session.created_at)}</td>
      <td><span class="badge">${escapeHtml(session.action)}</span></td>
      <td>${escapeHtml(session.ip_address)}</td>
      <td>${escapeHtml(session.mt_account || "-")}</td>
      <td>${escapeHtml(session.reason || "-")}</td>
    </tr>
  `).join("");
}

function renderCommands() {
  $("#commandsCount").textContent = String(state.commands.length);
  const table = $("#commandsTable");
  if (!state.commands.length) {
    table.innerHTML = `<tr><td colspan="5"><div class="empty-state compact">Chưa có command</div></td></tr>`;
    return;
  }
  table.innerHTML = state.commands.slice(0, 12).map((command) => `
    <tr>
      <td>#${command.id}</td>
      <td>${escapeHtml(command.action)}</td>
      <td><span class="badge">${escapeHtml(command.status)}</span></td>
      <td>${escapeHtml(command.result || "-")}</td>
      <td>${formatDate(command.created_at)}</td>
    </tr>
  `).join("");
}

function renderRuntimeStatuses() {
  const rows = state.runtimeStatuses || [];
  const count = $("#runtimeStatusCount");
  const table = $("#runtimeStatusTable");
  if (!count || !table) return;
  count.textContent = String(rows.length);
  if (!rows.length) {
    table.innerHTML = `<tr><td colspan="7"><div class="empty-state compact">Bot chưa gửi lý do realtime</div></td></tr>`;
    return;
  }
  table.innerHTML = rows.map((row) => `
    <tr>
      <td><strong>${escapeHtml(row.symbol)}</strong><br><span class="muted">${escapeHtml(row.timeframe || "-")}</span></td>
      <td>${signalBadge(row.signal)}<br><span class="muted">${escapeHtml(runtimeStateLabel(row.run_state))}</span></td>
      <td>${escapeHtml(row.reason || "-")}</td>
      <td>${Number(row.spread_points || 0).toFixed(1)}</td>
      <td>${row.open_positions}/${row.max_positions}<br><span class="muted">Tổng ${row.total_positions}/${row.max_total_positions}</span></td>
      <td>${row.dry_run ? "Dry run" : "Live thật"}<br><span class="muted">${row.session_allowed ? "trong phiên" : "ngoài phiên"}</span></td>
      <td>${formatDate(row.updated_at)}</td>
    </tr>
  `).join("");
}

async function refreshAll() {
  if (!state.token) return;
  const [profile, summary, accounts, trades, sessions, commands, runtimeStatuses, notifications] = await Promise.all([
    api("/user/me"),
    api("/user/summary"),
    api("/user/mt5-accounts"),
    api("/user/trades?limit=200"),
    api("/user/sessions?limit=100"),
    api("/user/commands?limit=100"),
    api("/user/bot-statuses?limit=50"),
    api("/user/notifications?limit=40"),
  ]);
  const hadNotifications = state.notifications.length > 0;
  state.profile = profile;
  state.summary = summary;
  state.accounts = accounts;
  state.trades = trades;
  state.sessions = sessions;
  state.commands = commands;
  state.runtimeStatuses = runtimeStatuses;
  state.notifications = notifications;
  renderSummary();
  renderProfile();
  renderAccounts();
  renderTrades();
  renderSessions();
  renderCommands();
  renderRuntimeStatuses();
  renderNotifications(hadNotifications);
}

function assertPasswordPair(password, confirmPassword) {
  if (String(password || "").length < 8) {
    throw new Error("Mật khẩu tối thiểu 8 ký tự");
  }
  if (password !== confirmPassword) {
    throw new Error("Hai mật khẩu chưa khớp");
  }
}

function finishUserLogin(data) {
  state.token = data.access_token;
  localStorage.setItem("user_token", state.token);
  resetAuthFlow();
  setLoggedIn(true);
}

async function loginWithPassword(event) {
  event.preventDefault();
  $("#userLoginMessage").textContent = "";
  const form = new FormData(event.currentTarget);
  const submit = event.currentTarget.querySelector("button[type='submit']");
  try {
    submit.disabled = true;
    const data = await api("/auth/user/password-login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({
        email: form.get("email"),
        password: form.get("password"),
        device_id: ensureDeviceId(),
        device_name: deviceName(),
      }),
    });
    finishUserLogin(data);
    await refreshAll();
    showToast(data.message || "Đăng nhập thành công");
  } catch (error) {
    $("#userLoginMessage").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

async function requestRegisterCode(event) {
  event.preventDefault();
  $("#userRegisterMessage").textContent = "";
  const form = new FormData(event.currentTarget);
  const submit = event.currentTarget.querySelector("button[type='submit']");
  try {
    const email = String(form.get("email") || "").trim().toLowerCase();
    const password = String(form.get("password") || "");
    assertPasswordPair(password, String(form.get("confirm_password") || ""));
    submit.disabled = true;
    const data = await api("/auth/user/register/request-code", {
      method: "POST",
      auth: false,
      body: JSON.stringify({
        email,
        password,
      }),
    });
    state.pendingRegisterEmail = data.email || email;
    state.pendingRegisterPassword = password;
    setAuthMode("registerVerify");
    $("#userRegisterVerifyMessage").textContent = data.message || "Đã gửi mã xác thực.";
  } catch (error) {
    $("#userRegisterMessage").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

async function verifyRegisterCode(event) {
  event.preventDefault();
  $("#userRegisterVerifyMessage").textContent = "";
  const form = new FormData(event.currentTarget);
  const submit = event.currentTarget.querySelector("button[type='submit']");
  try {
    if (!state.pendingRegisterEmail || !state.pendingRegisterPassword) {
      throw new Error("Phiên đăng ký đã mất. Vui lòng gửi mã lại.");
    }
    submit.disabled = true;
    const data = await api("/auth/user/register/verify", {
      method: "POST",
      auth: false,
      body: JSON.stringify({
        email: state.pendingRegisterEmail,
        password: state.pendingRegisterPassword,
        code: form.get("code"),
        device_id: ensureDeviceId(),
        device_name: deviceName(),
      }),
    });
    finishUserLogin(data);
    await refreshAll();
    showToast(data.message || "Đăng ký thành công");
  } catch (error) {
    $("#userRegisterVerifyMessage").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

async function requestPasswordReset(event) {
  event.preventDefault();
  $("#forgotPasswordMessage").textContent = "";
  const form = new FormData(event.currentTarget);
  const submit = event.currentTarget.querySelector("button[type='submit']");
  try {
    submit.disabled = true;
    const email = String(form.get("email") || "").trim().toLowerCase();
    const data = await api("/auth/user/password-reset/request-code", {
      method: "POST",
      auth: false,
      body: JSON.stringify({email}),
    });
    state.pendingResetEmail = data.email || email;
    setAuthMode("reset");
    $("#resetPasswordMessage").textContent = data.message || "Đã gửi mã reset.";
  } catch (error) {
    $("#forgotPasswordMessage").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

async function confirmPasswordReset(event) {
  event.preventDefault();
  $("#resetPasswordMessage").textContent = "";
  const form = new FormData(event.currentTarget);
  const submit = event.currentTarget.querySelector("button[type='submit']");
  try {
    if (!state.pendingResetEmail) {
      throw new Error("Phiên reset đã mất. Vui lòng gửi mã lại.");
    }
    const newPassword = String(form.get("new_password") || "");
    assertPasswordPair(newPassword, String(form.get("confirm_password") || ""));
    submit.disabled = true;
    const data = await api("/auth/user/password-reset/confirm", {
      method: "POST",
      auth: false,
      body: JSON.stringify({
        email: state.pendingResetEmail,
        code: form.get("code"),
        new_password: newPassword,
      }),
    });
    const resetEmail = state.pendingResetEmail;
    state.pendingResetEmail = "";
    $("#userLoginForm [name='email']").value = resetEmail;
    setAuthMode("login");
    showToast(data.message || "Đặt lại mật khẩu thành công");
  } catch (error) {
    $("#resetPasswordMessage").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

function logout(showMessage = true) {
  state.token = "";
  localStorage.removeItem("user_token");
  setLoggedIn(false);
  resetAuthFlow();
  if (showMessage) showToast("Đã đăng xuất");
}

function resetMt5AccountForm() {
  const form = $("#mt5AccountForm");
  if (!form) return;
  state.editingAccountId = null;
  form.reset();
  form.elements.lot_size.value = "0.01";
  form.elements.max_positions.value = "10";
  form.elements.max_total_positions.value = "10";
  form.elements.dry_run.value = "true";
  form.elements.mt_password.required = true;
  $("#userMt5FormTitle").textContent = "Thiết lập tài khoản MT5";
  $("#userMt5SubmitBtn").textContent = "Lưu và bật chạy";
  $("#mt5FormMessage").textContent = "";
}

function fillMt5AccountForm(account) {
  const form = $("#mt5AccountForm");
  if (!form || !account) return;
  state.editingAccountId = account.id;
  form.elements.label.value = account.label || "";
  form.elements.broker.value = account.broker || "";
  form.elements.mt_login.value = account.mt_login || "";
  form.elements.mt_server.value = account.mt_server || "";
  form.elements.mt_password.value = "";
  form.elements.mt_password.required = false;
  form.elements.symbol_mode.value = account.symbol_mode || "XAU";
  form.elements.symbols.value = account.symbols || "";
  form.elements.timeframe.value = account.timeframe || "M1";
  form.elements.lot_size.value = account.lot_size || 0.01;
  form.elements.max_positions.value = account.max_positions || 10;
  form.elements.max_total_positions.value = account.max_total_positions || 10;
  form.elements.dry_run.value = String(Boolean(account.dry_run));
  form.elements.note.value = account.note || "";
  $("#userMt5FormTitle").textContent = `Sửa tài khoản MT5 #${account.id}`;
  $("#userMt5SubmitBtn").textContent = "Lưu thay đổi";
  $("#mt5FormMessage").textContent = "Mật khẩu bỏ trống sẽ giữ nguyên. Bấm Restart nếu bot đang chạy để nhận cấu hình mới.";
  $("#mt5AccountForm").scrollIntoView({behavior: "smooth", block: "start"});
}

async function handleAccountAction(event) {
  const button = event.target.closest("[data-account-command]");
  const editButton = event.target.closest("[data-account-edit]");
  if (editButton) {
    const account = state.accounts.find((item) => String(item.id) === String(editButton.dataset.accountEdit));
    fillMt5AccountForm(account);
    return;
  }
  if (!button) return;
  const accountId = button.dataset.accountCommand;
  const action = button.dataset.action;
  const confirmed = window.confirm(`${action === "start" ? "Bật chạy" : action === "stop" ? "Dừng" : "Restart"} tài khoản MT5 này?`);
  if (!confirmed) return;
  try {
    $("#accountMessage").textContent = "";
    const data = await api(`/user/mt5-accounts/${accountId}/command`, {
      method: "POST",
      body: JSON.stringify({action, reason: `User portal ${action}`}),
    });
    showToast(data.message || "Đã gửi yêu cầu");
    await refreshAll();
  } catch (error) {
    $("#accountMessage").textContent = error.message;
  }
}

async function createMt5Account(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const message = $("#mt5FormMessage");
  message.textContent = "";
  try {
    const password = String(data.get("mt_password") || "");
    const payload = {
      label: data.get("label"),
      broker: data.get("broker"),
      mt_login: data.get("mt_login"),
      mt_server: data.get("mt_server"),
      symbol_mode: data.get("symbol_mode"),
      symbols: data.get("symbols"),
      timeframe: data.get("timeframe"),
      lot_size: Number(data.get("lot_size") || 0.01),
      max_positions: Number(data.get("max_positions") || 10),
      max_total_positions: Number(data.get("max_total_positions") || 10),
      dry_run: String(data.get("dry_run")) === "true",
      note: data.get("note"),
    };
    if (!state.editingAccountId || password) payload.mt_password = password;
    const path = state.editingAccountId ? `/user/mt5-accounts/${state.editingAccountId}` : "/user/mt5-accounts";
    const method = state.editingAccountId ? "PATCH" : "POST";
    const result = await api(path, {
      method,
      body: JSON.stringify(payload),
    });
    resetMt5AccountForm();
    showToast(result.message || "Đã lưu tài khoản MT5");
    await refreshAll();
  } catch (error) {
    message.textContent = error.message;
  }
}

async function updateProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  $("#profileMessage").textContent = "";
  try {
    const result = await api("/user/me", {
      method: "PATCH",
      body: JSON.stringify({
        username: data.get("username"),
        note: data.get("note"),
      }),
    });
    showToast(result.message || "Đã cập nhật hồ sơ");
    await refreshAll();
  } catch (error) {
    $("#profileMessage").textContent = error.message;
  }
}

async function changePassword(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  $("#passwordMessage").textContent = "";
  try {
    assertPasswordPair(data.get("new_password"), data.get("confirm_password"));
    const result = await api("/user/change-password", {
      method: "POST",
      body: JSON.stringify({
        old_password: data.get("old_password"),
        new_password: data.get("new_password"),
      }),
    });
    form.reset();
    showToast(result.message || "Đã đổi mật khẩu");
  } catch (error) {
    $("#passwordMessage").textContent = error.message;
  }
}

function refreshMotionIndexes() {
  const items = document.querySelectorAll(
    ".stat-card, .panel, .login-box, tbody tr, .button, .small-button, .badge, .pill, .nav-item, input, select, textarea, .metric-row, .activity-row, .readiness-item, .notification-item, .activity-item, .auth-tab, .quick-links a, .signal-metric, .indicator-grid div, .pnl-results div"
  );
  items.forEach((item, index) => {
    item.style.setProperty("--motion-index", String(index % 36));
  });
}

function startUiMotion() {
  document.body.classList.add("ui-live");
  refreshMotionIndexes();
  const observer = new MutationObserver(() => window.requestAnimationFrame(refreshMotionIndexes));
  observer.observe(document.body, {childList: true, subtree: true});
}

function bindEvents() {
  $("#userLoginForm").addEventListener("submit", loginWithPassword);
  $("#userRegisterForm").addEventListener("submit", requestRegisterCode);
  $("#userRegisterVerifyForm").addEventListener("submit", verifyRegisterCode);
  $("#forgotPasswordForm").addEventListener("submit", requestPasswordReset);
  $("#resetPasswordForm").addEventListener("submit", confirmPasswordReset);
  $("#forgotPasswordBtn").addEventListener("click", () => setAuthMode("forgot"));
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      clearAuthMessages();
      setAuthMode(button.dataset.authMode);
    });
  });
  $("#mt5AccountForm").addEventListener("submit", createMt5Account);
  $("#userMt5ResetBtn").addEventListener("click", resetMt5AccountForm);
  $("#profileForm").addEventListener("submit", updateProfile);
  $("#changePasswordForm").addEventListener("submit", changePassword);
  $("#logoutBtn").addEventListener("click", () => logout(true));
  $("#refreshBtn").addEventListener("click", async () => {
    try {
      await refreshAll();
      showToast("Đã làm mới dữ liệu");
    } catch (error) {
      showToast(error.message, "bad");
    }
  });
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => setView(item.dataset.view));
  });
  $("#accountsTable").addEventListener("click", handleAccountAction);
  $("#tradesFilter").addEventListener("input", (event) => {
    state.filters.trades = event.target.value;
    renderTrades();
  });
  $("#tradeStatusFilter").addEventListener("change", (event) => {
    state.filters.tradeStatus = event.target.value;
    renderTrades();
  });
  $("#tradeSideFilter").addEventListener("change", (event) => {
    state.filters.tradeSide = event.target.value;
    renderTrades();
  });
}

async function init() {
  bindEvents();
  startUiMotion();
  setView("overview");
  setLoggedIn(Boolean(state.token));
  if (!state.token) {
    setAuthMode("login");
    return;
  }
  try {
    await refreshAll();
  } catch (error) {
    showToast(error.message, "bad");
  }
}

init();
