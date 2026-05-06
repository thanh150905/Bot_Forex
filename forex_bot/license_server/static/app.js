const state = {
  token: localStorage.getItem("admin_token") || "",
  currentView: "overview",
  lastSignal: null,
  bots: [],
  mt5Accounts: [],
  users: [],
  licenses: [],
  sessions: [],
  trades: [],
  commands: [],
  readiness: null,
  activity: [],
  ops: null,
  runtimeStatuses: [],
  mt5TradeStats: null,
  mt5TradeStatsAccountId: null,
  mt5TradeStatsDays: 0,
  soundEnabled: localStorage.getItem("sound_enabled") === "true",
  desktopAlerts: localStorage.getItem("desktop_alerts") === "true",
  filters: {
    bots: "",
    mt5Accounts: "",
    users: "",
    licenses: "",
    sessions: "",
    trades: "",
    tradeStatus: "",
    tradeSide: "",
    mt5StatsTradeSearch: "",
    mt5StatsTradeStatus: "",
    mt5StatsTradeDirection: "",
    commands: "",
  },
  seenNotifications: new Set(JSON.parse(localStorage.getItem("seen_notifications") || "[]")),
  notificationTimer: null,
  editingMt5AccountId: null,
};

const pageMeta = {
  overview: ["Tổng quan", "Theo dõi license, IP lock, hoạt động bot và giao dịch."],
  ops: ["Vận hành live", "Theo dõi bot live, exposure đang mở và cảnh báo."],
  activity: ["Hoạt động", "Log mở lệnh, đóng lệnh, bot xác thực và bị từ chối."],
  analytics: ["Phân tích", "Lợi nhuận, tỷ lệ thắng và hiệu suất theo dữ liệu lệnh đã báo cáo."],
  strategy: ["Rủi ro chiến lược", "Toán học chi phí execution, bản đồ hệ thống và ma trận ưu tiên trước khi scale live."],
  control: ["Điều khiển", "Gửi lệnh vận hành live xuống các bot đang kết nối."],
  readiness: ["Sẵn sàng live", "Checklist production, trạng thái bảo mật và sức khỏe server."],
  bots: ["Bot giao dịch", "Trạng thái online/offline của từng bot theo license."],
  "mt5-accounts": ["Tài khoản MT5", "Thêm tài khoản khách để runner VPS chạy bot mà không cần gửi file."],
  "ai-bot": ["AI Bot", "Chạy phân tích xu hướng và tạo lệnh paper trực tiếp trên web."],
  users: ["Người dùng", "Tài khoản khách hàng được quản lý bởi license server."],
  licenses: ["License", "Khóa license, IP lock, trạng thái kích hoạt và số lần xác thực."],
  sessions: ["Phiên bot", "Các lần bot xác thực, ping hoặc bị từ chối gần đây."],
  trades: ["Lệnh giao dịch", "Các lệnh được bot kết nối báo cáo về server."],
  tools: ["Công cụ", "Xuất dữ liệu, kiểm tra server và tiện ích admin."],
};

const $ = (selector) => document.querySelector(selector);

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

function percent(value) {
  const number = Number(value);
  if (Number.isNaN(number)) return "0%";
  return `${number.toFixed(number % 1 === 0 ? 0 : 1)}%`;
}

function bytesText(value) {
  const number = Number(value || 0);
  if (number >= 1024 * 1024) return `${(number / 1024 / 1024).toFixed(1)} MB`;
  if (number >= 1024) return `${(number / 1024).toFixed(1)} KB`;
  return `${number} B`;
}

function percentText(value) {
  const number = Number(value);
  if (Number.isNaN(number)) return "-";
  return `${number.toFixed(1)}%`;
}

function shortKey(value) {
  const text = String(value || "-");
  if (text.length <= 14) return text;
  return `${text.slice(0, 8)}...${text.slice(-4)}`;
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

function severityText(severity) {
  return {
    ok: "OK",
    warn: "CẢNH BÁO",
    bad: "KHẨN",
  }[safeSeverity(severity)];
}

function setTextWithFlash(selector, value) {
  const element = $(selector);
  if (!element) return;
  const text = String(value ?? "");
  const changed = element.textContent !== text && element.textContent !== "";
  element.textContent = text;
  if (!changed) return;
  element.classList.remove("value-flash");
  void element.offsetWidth;
  element.classList.add("value-flash");
}

function updateNotificationBadge(count) {
  const badge = $("#notificationBadge");
  const button = $("#notificationJumpBtn");
  if (!badge || !button) return;
  const number = Number(count || 0);
  badge.textContent = number > 99 ? "99+" : String(number);
  button.classList.toggle("has-alerts", number > 0);
}

function updateLiveAlert(item) {
  const strip = $("#liveAlertStrip");
  if (!strip) return;
  if (!item) {
    strip.className = "live-alert-strip hidden";
    return;
  }
  const severity = safeSeverity(item.severity);
  strip.className = `live-alert-strip ${severity}`;
  $("#liveAlertTitle").textContent = item.title || "Thông báo mới";
  $("#liveAlertMessage").textContent = item.message || "-";
  $("#liveAlertTime").textContent = formatDate(item.created_at);
  $("#liveAlertDot").className = `live-alert-dot ${severity}`;
}

function includesText(row, query) {
  if (!query) return true;
  return JSON.stringify(row).toLowerCase().includes(query.toLowerCase());
}

function downloadCsv(filename, rows) {
  if (!rows.length) {
    showToast("Không có dữ liệu để xuất");
    return;
  }
  const headers = Object.keys(rows[0]);
  const csv = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => {
      const value = String(row[header] ?? "");
      return `"${value.replaceAll('"', '""')}"`;
    }).join(",")),
  ].join("\n");
  const blob = new Blob([csv], {type: "text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function showToast(message, severity = "ok") {
  const safe = safeSeverity(severity);
  const stack = $("#toastStack");
  if (stack) {
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
    return;
  }

  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.remove("toast-alert");
  void toast.offsetWidth;
  toast.classList.add("toast-alert");
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 3400);
}

function playAlertTone(severity = "ok") {
  if (!state.soundEnabled) return;
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  const context = new AudioContext();
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  oscillator.type = severity === "bad" ? "sawtooth" : "sine";
  oscillator.frequency.value = severity === "bad" ? 220 : severity === "warn" ? 440 : 660;
  gain.gain.setValueAtTime(0.0001, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.08, context.currentTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.28);
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + 0.3);
}

function sendDesktopAlert(title, message) {
  if (!state.desktopAlerts || !("Notification" in window) || Notification.permission !== "granted") return;
  new Notification(title, {body: message, tag: title});
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(state.token ? authHeaders() : {"Content-Type": "application/json"}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || `HTTP ${response.status}`);
  }
  return data;
}

async function optionalApi(path, fallback) {
  try {
    return await api(path);
  } catch (error) {
    console.warn(`${path}: ${error.message}`);
    return fallback;
  }
}

function setAuthenticated(isAuthenticated) {
  $("#loginPanel").classList.toggle("hidden", isAuthenticated);
  $("#content").classList.toggle("hidden", !isAuthenticated);
  $("#logoutBtn").classList.toggle("hidden", !isAuthenticated);
  $("#refreshBtn").classList.toggle("hidden", !isAuthenticated);
  $("#soundToggleBtn").classList.toggle("hidden", !isAuthenticated);
  $("#desktopNotifyBtn").classList.toggle("hidden", !isAuthenticated);
  $("#notificationJumpBtn").classList.toggle("hidden", !isAuthenticated);
  $("#liveAlertStrip").classList.toggle("hidden", !isAuthenticated || !state.activity.length);
}

async function checkHealth() {
  try {
    const data = await api("/health", {headers: {"Content-Type": "application/json"}});
    $("#serverStatus").textContent = data.status === "ok" ? "Đang online" : "Không rõ";
    document.querySelector(".status-dot").classList.toggle("ok", data.status === "ok");
  } catch {
    $("#serverStatus").textContent = "Mất kết nối";
    document.querySelector(".status-dot").classList.remove("ok");
  }
}

async function login(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  $("#loginMessage").textContent = "";

  try {
    const data = await api("/auth/admin/login", {
      method: "POST",
      body: JSON.stringify({
        username: form.get("username"),
        password: form.get("password"),
      }),
    });
    state.token = data.access_token;
    localStorage.setItem("admin_token", state.token);
    setAuthenticated(true);
    await refreshAll();
    startNotificationPolling();
    showToast("Đăng nhập thành công");
  } catch (error) {
    $("#loginMessage").textContent = error.message;
  }
}

function logout() {
  state.token = "";
  localStorage.removeItem("admin_token");
  if (state.notificationTimer) {
    window.clearInterval(state.notificationTimer);
    state.notificationTimer = null;
  }
  setAuthenticated(false);
  showToast("Đã đăng xuất");
}

async function refreshAll() {
  if (!state.token) return;
  const [dashboard, ops, bots, mt5Accounts, users, licenses, sessions, trades, commands, readiness, runtimeStatuses, notifications] = await Promise.all([
    api("/admin/dashboard"),
    optionalApi("/admin/ops-summary", null),
    api("/admin/bots"),
    optionalApi("/admin/mt5-accounts", []),
    api("/admin/users"),
    api("/admin/licenses"),
    api("/admin/sessions?limit=50"),
    api("/admin/trades?limit=100"),
    optionalApi("/admin/commands?limit=100", []),
    optionalApi("/admin/readiness", null),
    optionalApi("/admin/bot-statuses?limit=100", []),
    optionalApi("/admin/notifications?limit=50", []),
  ]);

  state.ops = ops;
  state.bots = bots;
  state.mt5Accounts = mt5Accounts;
  state.users = users;
  state.licenses = licenses;
  state.sessions = sessions;
  state.trades = trades;
  state.commands = commands;
  state.readiness = readiness;
  state.runtimeStatuses = runtimeStatuses;

  renderDashboard(dashboard);
  renderOps();
  renderBots();
  renderMt5AccountOptions();
  renderMt5Accounts();
  renderUsers();
  renderLicenses();
  renderSessions();
  renderTrades();
  renderAnalytics();
  renderCommands();
  renderReadiness();
  renderNotifications(notifications, false);
}

function startNotificationPolling() {
  if (state.notificationTimer) return;
  state.notificationTimer = window.setInterval(pollNotifications, 5000);
}

function renderDashboard(data) {
  $("#closedProfit").className = Number(data.trades.profit || 0) >= 0 ? "profit-positive" : "profit-negative";
  $("#todayProfit").className = Number(data.trades.today_profit || 0) >= 0 ? "profit-positive" : "profit-negative";
  setTextWithFlash("#totalUsers", data.users.total);
  setTextWithFlash("#activeUsers", `${data.users.active} đang hoạt động`);
  setTextWithFlash("#totalLicenses", data.licenses.total);
  setTextWithFlash("#activeLicenses", `${data.licenses.active} đang hoạt động`);
  setTextWithFlash("#onlineBots", data.bots?.online ?? 0);
  setTextWithFlash("#totalBots", `${data.bots?.total ?? 0} tổng`);
  setTextWithFlash("#openTrades", data.trades.open);
  setTextWithFlash("#totalTrades", `${data.trades.total} tổng`);
  setTextWithFlash("#closedTrades", `${data.trades.closed} đã đóng`);
  setTextWithFlash("#closedProfit", money(data.trades.profit));
  setTextWithFlash("#todayProfit", money(data.trades.today_profit));
}

function renderOps() {
  if (!state.ops) return;
  const ops = state.ops;
  state.runtimeStatuses = state.runtimeStatuses.length ? state.runtimeStatuses : (ops.runtime_statuses || []);
  const hasOnlineBot = Number(ops.bots.online || 0) > 0;
  const hasOpenTrades = Number(ops.risk.open_trades || 0) > 0;
  const hasRejects = Number(ops.risk.rejects_today || 0) > 0;
  const stateText = hasRejects ? "Cần xử lý cảnh báo" : hasOnlineBot ? "Đang giám sát live" : "Không có bot online";
  setTextWithFlash("#opsState", stateText);
  setTextWithFlash("#opsTimestamp", `Cập nhật ${formatDate(ops.timestamp)}`);
  $("#opsPulse").className = `ops-pulse ${hasOnlineBot ? "online" : "offline"} ${hasOpenTrades ? "trading" : ""}`;
  $("#opsTodayProfit").className = Number(ops.risk.today_closed_profit || 0) >= 0 ? "profit-positive" : "profit-negative";
  setTextWithFlash("#opsOnlineBots", ops.bots.online);
  setTextWithFlash("#opsTotalBots", `${ops.bots.total} tổng`);
  setTextWithFlash("#opsOpenTrades", ops.risk.open_trades);
  setTextWithFlash("#opsStaleTrades", `${ops.risk.stale_open_trades} treo lâu`);
  setTextWithFlash("#opsTodayProfit", money(ops.risk.today_closed_profit));
  setTextWithFlash("#opsTodayClosed", `${ops.risk.today_closed_trades} đã đóng`);
  setTextWithFlash("#opsRejects", ops.risk.rejects_today);
  setTextWithFlash("#opsSymbolCount", ops.symbols.length);
  setTextWithFlash("#opsOpenCount", ops.open_trades.length);

  const latest = state.activity[0];
  setTextWithFlash("#opsTicker", latest ? `${latest.title} - ${latest.message}` : "Chưa có sự kiện gần đây");

  $("#opsSymbolsTable").innerHTML = ops.symbols.map((row) => `
    <tr>
      <td>${escapeHtml(row.symbol)}</td>
      <td>${row.open}</td>
      <td>${row.buy}</td>
      <td>${row.sell}</td>
      <td>${row.lot}</td>
    </tr>
  `).join("") || emptyRow(5);

  $("#opsRecentClosedTable").innerHTML = ops.recent_closed.map((trade) => `
    <tr>
      <td>${escapeHtml(trade.ticket)}</td>
      <td>${escapeHtml(trade.symbol)}</td>
      <td>${sidePill(trade.direction)}</td>
      <td>${money(trade.profit)} (${trade.pips ?? "-"} pips)</td>
      <td>${formatDate(trade.closed_at)}</td>
    </tr>
  `).join("") || emptyRow(5);

  $("#opsOpenTradesTable").innerHTML = ops.open_trades.map((trade) => `
    <tr>
      <td>${escapeHtml(trade.ticket)}</td>
      <td><span class="license-key">${escapeHtml(shortKey(trade.license_key))}</span></td>
      <td>${escapeHtml(trade.symbol)}</td>
      <td>${sidePill(trade.direction)}</td>
      <td>${trade.lot_size}</td>
      <td>${trade.entry_price}</td>
      <td>${formatDate(trade.opened_at)}</td>
      <td>${escapeHtml(trade.note || "-")}</td>
    </tr>
  `).join("") || emptyRow(7);

  renderRuntimeStatuses();
}

function renderRuntimeStatuses() {
  const rows = state.runtimeStatuses || [];
  const count = $("#opsRuntimeStatusCount");
  const table = $("#opsRuntimeStatusTable");
  if (!count || !table) return;
  count.textContent = String(rows.length);
  table.innerHTML = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row.username || "-")}</td>
      <td><span class="license-key">${escapeHtml(row.license_short || shortKey(row.license_key))}</span><br><span class="muted">${escapeHtml(row.mt_account || "-")}</span></td>
      <td><strong>${escapeHtml(row.symbol)}</strong><br><span class="muted">${escapeHtml(row.timeframe || "-")}</span></td>
      <td>${signalPill(row.signal)}<br><span class="muted">${escapeHtml(runtimeStateLabel(row.run_state))}</span></td>
      <td>${escapeHtml(row.reason || "-")}</td>
      <td>${Number(row.spread_points || 0).toFixed(1)}</td>
      <td>${row.open_positions}/${row.max_positions}<br><span class="muted">Tổng ${row.total_positions}/${row.max_total_positions}</span></td>
      <td>${formatDate(row.updated_at)}<br><span class="muted">${row.dry_run ? "Dry run" : "Live thật"}</span></td>
    </tr>
  `).join("") || emptyRow(8);
}

function renderBots() {
  const rows = state.bots.filter((bot) => includesText(bot, state.filters.bots));
  $("#botsCount").textContent = `${rows.length}/${state.bots.length}`;
  $("#botsTable").innerHTML = rows.map((bot) => `
    <tr>
      <td>${botStatusPill(bot.status)}</td>
      <td>${escapeHtml(bot.username)} <span class="muted">#${bot.user_id}</span></td>
      <td><span class="license-key">${escapeHtml(bot.license_key)}</span></td>
      <td>${escapeHtml(bot.allowed_ip || "Tự lock")}</td>
      <td>${escapeHtml(bot.mt_account || "-")}</td>
      <td>${formatDate(bot.last_seen)} <span class="muted">${formatAge(bot.seconds_since_seen)}</span></td>
      <td>${bot.verify_count}</td>
    </tr>
  `).join("") || emptyRow(8);
}

function mt5RunStatusPill(status) {
  const labels = {
    stopped: "Đã dừng",
    waiting_client: "Chờ máy khách",
    pending_start: "Chờ chạy",
    running: "Đang chạy",
    paused: "Tạm dừng",
    pending_stop: "Chờ dừng",
    pending_restart: "Chờ restart",
    error: "Lỗi",
  };
  const cls = status === "running" ? "ok" : status === "error" ? "bad" : status?.startsWith("pending") || status === "waiting_client" || status === "paused" ? "warn" : "";
  return `<span class="pill ${cls}">${escapeHtml(labels[status] || status || "Không rõ")}</span>`;
}

function renderMt5AccountOptions() {
  const userSelect = $("#mt5UserSelect");
  const licenseSelect = $("#mt5LicenseSelect");
  if (!userSelect || !licenseSelect) return;
  const currentUser = userSelect.value;
  const currentLicense = licenseSelect.value;
  userSelect.innerHTML = state.users.map((user) => (
    `<option value="${user.id}">${escapeHtml(user.username)} #${user.id}</option>`
  )).join("");
  if (currentUser) userSelect.value = currentUser;

  licenseSelect.innerHTML = [
    '<option value="">Không gắn license</option>',
    ...state.licenses.map((license) => (
      `<option value="${escapeHtml(license.license_key)}">${escapeHtml(shortKey(license.license_key))} - ${escapeHtml(license.username || "-")}</option>`
    )),
  ].join("");
  if (currentLicense) licenseSelect.value = currentLicense;
}

function filteredMt5Accounts() {
  return state.mt5Accounts.filter((account) => includesText(account, state.filters.mt5Accounts));
}

function mt5AdminActions(account) {
  if (!account.can_admin_operate) {
    return `
      <div class="row-actions">
        <button class="small-button locked" disabled>Start</button>
        <button class="small-button locked" disabled>Stop</button>
        <button class="small-button locked" disabled>Restart</button>
        <button class="small-button" data-mt5-stats="${account.id}">Thống kê</button>
        <button class="small-button danger" data-mt5-delete="${account.id}">Xóa</button>
      </div>
    `;
  }
  return `
    <div class="row-actions">
      <button class="small-button" data-mt5-command="${account.id}" data-mt5-action="start">Start</button>
      <button class="small-button" data-mt5-command="${account.id}" data-mt5-action="stop">Stop</button>
      <button class="small-button" data-mt5-command="${account.id}" data-mt5-action="restart">Restart</button>
      <button class="small-button" data-mt5-stats="${account.id}">Thống kê</button>
      <button class="small-button" data-mt5-edit="${account.id}">Sửa</button>
      <button class="small-button danger" data-mt5-delete="${account.id}">Xóa</button>
    </div>
  `;
}

function renderMt5Accounts() {
  const table = $("#mt5AccountsTable");
  if (!table) return;
  const rows = filteredMt5Accounts();
  $("#mt5AccountsCount").textContent = `${rows.length}/${state.mt5Accounts.length}`;
  table.innerHTML = rows.map((account) => `
    <tr>
      <td>
        ${mt5RunStatusPill(account.run_status)}
        <span class="muted">${escapeHtml(account.source_label || "-")} | ${account.run_mode === "client" ? `máy khách ${escapeHtml(account.license_allowed_ip || "")}` : account.is_active ? "runner bật" : "runner tắt"}</span>
      </td>
      <td>${escapeHtml(account.username || "-")} <span class="muted">#${account.user_id}</span><br>${escapeHtml(account.label || "-")}</td>
      <td><span class="license-key">${escapeHtml(shortKey(account.license_key || "-"))}</span><br><span class="muted">${account.license_key ? account.license_active === false ? "license tắt" : "license OK" : "chưa gắn"}</span></td>
      <td><strong>${escapeHtml(account.mt_login)}</strong><br><span class="muted">${escapeHtml(account.mt_server)} ${account.broker ? `- ${escapeHtml(account.broker)}` : ""}</span></td>
      <td><strong>${escapeHtml(account.symbol_mode)}</strong><br><span class="muted">${escapeHtml(account.symbols)} / ${escapeHtml(account.timeframe)}</span></td>
      <td>${account.lot_size} lot<br><span class="muted">${account.max_positions}/${account.max_total_positions} lệnh, spread ${account.max_spread_points}</span></td>
      <td>${formatDate(account.updated_at)}<br><span class="muted">${account.dry_run ? "Dry run" : "Live thật"}</span></td>
      <td>
        ${mt5AdminActions(account)}
      </td>
    </tr>
  `).join("") || emptyRow(8);
}

async function loadMt5TradeStats(accountId, days = state.mt5TradeStatsDays) {
  if (String(state.mt5TradeStatsAccountId || "") !== String(accountId)) {
    state.filters.mt5StatsTradeSearch = "";
    state.filters.mt5StatsTradeStatus = "";
    state.filters.mt5StatsTradeDirection = "";
    if ($("#mt5StatsTradeSearch")) $("#mt5StatsTradeSearch").value = "";
    if ($("#mt5StatsTradeStatus")) $("#mt5StatsTradeStatus").value = "";
    if ($("#mt5StatsTradeDirection")) $("#mt5StatsTradeDirection").value = "";
  }
  state.mt5TradeStatsAccountId = accountId;
  state.mt5TradeStatsDays = Number(days || 0);
  const data = await api(`/admin/mt5-accounts/${accountId}/trade-stats?limit=300&days=${state.mt5TradeStatsDays}`);
  state.mt5TradeStats = data;
  renderMt5TradeStats();
  $("#mt5TradeStatsPanel")?.scrollIntoView({behavior: "smooth", block: "start"});
}

function moneyClass(value) {
  return Number(value || 0) >= 0 ? "profit-positive" : "profit-negative";
}

function formatCompactDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString([], {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"});
}

function statusTone(summary) {
  const profit = Number(summary.closed_profit || 0);
  const winRate = Number(summary.win_rate || 0);
  if (profit > 0 && winRate >= 50) return "ok";
  if (profit < 0) return "bad";
  return "warn";
}

function renderStatBar(row, labelKey) {
  const winRate = Math.max(0, Math.min(100, Number(row.win_rate || 0)));
  const profit = Number(row.profit || 0);
  return `
    <div class="bar-row">
      <div class="bar-row-top">
        <strong>${escapeHtml(row[labelKey] || "-")}</strong>
        <span class="${moneyClass(profit)}">${money(profit)}</span>
      </div>
      <div class="bar-track"><span style="width:${winRate}%"></span></div>
      <div class="bar-row-meta">
        <span>${row.total} lệnh</span>
        <span>${row.open} mở</span>
        <span>${row.closed} đóng</span>
        <span>${percent(row.win_rate)}</span>
      </div>
    </div>
  `;
}

function filteredMt5StatTrades() {
  const trades = state.mt5TradeStats?.trades || [];
  return trades.filter((trade) => {
    const query = state.filters.mt5StatsTradeSearch.trim().toLowerCase();
    if (query && !JSON.stringify(trade).toLowerCase().includes(query)) return false;
    if (state.filters.mt5StatsTradeStatus && trade.status !== state.filters.mt5StatsTradeStatus) return false;
    if (state.filters.mt5StatsTradeDirection && trade.direction !== state.filters.mt5StatsTradeDirection) return false;
    return true;
  });
}

function renderMt5TradeStats() {
  const panel = $("#mt5TradeStatsPanel");
  if (!panel || !state.mt5TradeStats) return;

  const {account, summary, history_total: historyTotal, message} = state.mt5TradeStats;
  const tone = statusTone(summary);
  panel.classList.remove("hidden");

  $("#mt5TradeStatsStatus").className = `pill ${tone}`;
  $("#mt5TradeStatsStatus").textContent = account.run_status || "-";
  $("#mt5TradeStatsTitle").textContent = account.label || `MT5 ${account.mt_login}`;
  $("#mt5TradeStatsSubtitle").textContent = message || `${account.username || "-"} - ${account.mt_login} - ${account.mt_server || "-"}`;
  $("#mt5StatsMeta").innerHTML = [
    `${escapeHtml(account.symbols || "-")}`,
    `${account.dry_run ? "Dry run" : "Live thật"}`,
    `${summary.scope_label}`,
    `${historyTotal ?? summary.total} lệnh lịch sử`,
  ].map((item) => `<span>${item}</span>`).join("");
  $("#mt5TradeStatsBadge").textContent = `${summary.total} lệnh`;

  $("#mt5StatsWinRate").textContent = percent(summary.win_rate);
  $("#mt5WinRing").style.setProperty("--win-rate", `${Math.max(0, Math.min(100, Number(summary.win_rate || 0)))}%`);
  $("#mt5StatsWinRateDetail").textContent = `${summary.wins} thắng / ${summary.closed} đã đóng`;
  $("#mt5StatsClosedProfit").textContent = money(summary.closed_profit);
  $("#mt5StatsClosedProfit").className = moneyClass(summary.closed_profit);
  $("#mt5StatsTradeCount").textContent = summary.total;
  $("#mt5StatsOpenClosed").textContent = `${summary.open} mở / ${summary.closed} đóng`;
  $("#mt5StatsProfitFactor").textContent = summary.profit_factor === null ? "-" : Number(summary.profit_factor).toFixed(2);
  $("#mt5StatsAvgProfit").textContent = `Avg ${money(summary.avg_closed_profit)}`;
  $("#mt5StatsGrossProfit").textContent = money(summary.gross_profit);
  $("#mt5StatsGrossProfit").className = moneyClass(summary.gross_profit);
  $("#mt5StatsGrossLoss").textContent = `Loss -$${Number(summary.gross_loss || 0).toFixed(2)}`;
  $("#mt5StatsOpenLot").textContent = Number(summary.open_lot || 0).toFixed(2);
  $("#mt5StatsTotalLot").textContent = `Tổng ${Number(summary.total_lot || 0).toFixed(2)} lot`;
  $("#mt5StatsClosedPips").textContent = Number(summary.closed_pips || 0).toFixed(1);
  $("#mt5StatsClosedPips").className = moneyClass(summary.closed_pips);
  $("#mt5StatsAvgPips").textContent = `Avg ${Number(summary.avg_closed_pips || 0).toFixed(1)}`;
  $("#mt5StatsLastTrade").textContent = formatCompactDate(summary.latest_trade_at);
  $("#mt5StatsScope").textContent = summary.scope_label || "Tất cả";
  $("#mt5StatsBestTrade").textContent = money(summary.best_trade?.profit || 0);
  $("#mt5StatsBestTrade").className = moneyClass(summary.best_trade?.profit || 0);
  $("#mt5StatsBestTicket").textContent = summary.best_trade?.ticket || "-";
  $("#mt5StatsWorstTrade").textContent = money(summary.worst_trade?.profit || 0);
  $("#mt5StatsWorstTrade").className = moneyClass(summary.worst_trade?.profit || 0);
  $("#mt5StatsWorstTicket").textContent = summary.worst_trade?.ticket || "-";

  $("#mt5StatsRangeTabs").querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.mt5StatsDays || 0) === state.mt5TradeStatsDays);
  });

  $("#mt5SymbolStatsList").innerHTML = (summary.symbols || []).map((row) => renderStatBar(row, "symbol")).join("")
    || `<p class="muted">Chưa có dữ liệu symbol.</p>`;
  $("#mt5DirectionStatsList").innerHTML = (summary.directions || []).map((row) => renderStatBar(row, "direction")).join("")
    || `<p class="muted">Chưa có dữ liệu BUY/SELL.</p>`;

  const trades = filteredMt5StatTrades();
  $("#mt5StatsTradeFilterText").textContent = `${trades.length}/${state.mt5TradeStats.trades.length} lệnh đang hiển thị trong phạm vi ${summary.scope_label}.`;
  $("#mt5TradeStatsTable").innerHTML = trades.map((trade) => {
    const profit = Number(trade.profit || 0);
    return `
      <tr>
        <td><span class="license-key">${escapeHtml(trade.ticket)}</span></td>
        <td><strong>${escapeHtml(trade.symbol)}</strong></td>
        <td>${sidePill(trade.direction)}</td>
        <td>${tradeStatusPill(trade.status)}</td>
        <td>${trade.lot_size}</td>
        <td>${trade.entry_price}<br><span class="muted">${trade.close_price ?? "-"}</span></td>
        <td><strong class="${moneyClass(profit)}">${money(trade.profit)}</strong><br><span class="muted">${trade.pips ?? "-"} pips</span></td>
        <td>${formatCompactDate(trade.opened_at)}<br><span class="muted">${formatCompactDate(trade.closed_at)}</span></td>
        <td>${escapeHtml(trade.note || "-")}</td>
      </tr>
    `;
  }).join("") || emptyRow(9);
}

function formBool(value) {
  return String(value) === "true";
}

function mt5AccountPayloadFromForm(formElement, isEdit = false) {
  const form = new FormData(formElement);
  const password = String(form.get("mt_password") || "");
  const payload = {
    user_id: Number(form.get("user_id")),
    license_key: form.get("license_key") || null,
    label: form.get("label") || null,
    broker: form.get("broker") || null,
    mt_login: String(form.get("mt_login") || "").trim(),
    mt_server: String(form.get("mt_server") || "").trim(),
    symbol_mode: form.get("symbol_mode"),
    symbols: form.get("symbols") || null,
    timeframe: "M1",
    lot_size: Number(form.get("lot_size") || 0.01),
    max_positions: Number(form.get("max_positions") || 10),
    max_total_positions: Number(form.get("max_total_positions") || 10),
    max_spread_points: Number(form.get("max_spread_points") || 350),
    dry_run: formBool(form.get("dry_run")),
    is_active: formBool(form.get("is_active")),
    note: form.get("note") || null,
  };
  if (!isEdit || password) payload.mt_password = password;
  return payload;
}

function resetMt5AccountForm() {
  const form = $("#mt5AccountForm");
  if (!form) return;
  state.editingMt5AccountId = null;
  form.reset();
  $("#mt5AccountFormTitle").textContent = "Thêm tài khoản MT5";
  $("#mt5AccountSubmitBtn").textContent = "Thêm tài khoản";
  renderMt5AccountOptions();
}

function fillMt5AccountForm(account) {
  const form = $("#mt5AccountForm");
  if (!form || !account) return;
  state.editingMt5AccountId = account.id;
  renderMt5AccountOptions();
  form.elements.user_id.value = account.user_id;
  form.elements.license_key.value = account.license_key || "";
  form.elements.label.value = account.label || "";
  form.elements.broker.value = account.broker || "";
  form.elements.mt_login.value = account.mt_login || "";
  form.elements.mt_server.value = account.mt_server || "";
  form.elements.mt_password.value = "";
  form.elements.symbol_mode.value = account.symbol_mode || "XAU";
  form.elements.symbols.value = account.symbols || "";
  form.elements.lot_size.value = account.lot_size || 0.01;
  form.elements.max_positions.value = account.max_positions || 10;
  form.elements.max_total_positions.value = account.max_total_positions || 10;
  form.elements.max_spread_points.value = account.max_spread_points || 350;
  form.elements.dry_run.value = String(Boolean(account.dry_run));
  form.elements.is_active.value = String(Boolean(account.is_active));
  form.elements.note.value = account.note || "";
  $("#mt5AccountFormTitle").textContent = `Sửa tài khoản MT5 #${account.id}`;
  $("#mt5AccountSubmitBtn").textContent = "Lưu thay đổi";
  $("#mt5AccountMessage").textContent = "Đang sửa tài khoản. Mật khẩu bỏ trống sẽ giữ nguyên.";
  window.scrollTo({top: 0, behavior: "smooth"});
}

function renderUsers() {
  const rows = state.users.filter((user) => includesText(user, state.filters.users));
  $("#usersCount").textContent = `${rows.length}/${state.users.length}`;
  $("#usersTable").innerHTML = rows.map((user) => `
    <tr>
      <td>${user.id}</td>
      <td>${escapeHtml(user.username)}</td>
      <td>${escapeHtml(user.email)}</td>
      <td><span class="badge">${user.source === "self_register" ? "Tự đăng ký" : "Admin"}</span><br><span class="muted">${user.has_password ? "Có mật khẩu" : "Chưa có mật khẩu"}</span></td>
      <td>${user.active_license_count || 0}/${user.license_count || 0} license<br><span class="muted">${user.mt5_account_count || 0} MT5</span></td>
      <td>${statusPill(user.is_active)}</td>
      <td>${formatDate(user.expires_at)}</td>
      <td>${formatDate(user.last_session_at)}</td>
      <td>${formatDate(user.created_at)}</td>
      <td>${escapeHtml(user.note || "-")}</td>
      <td>
        <div class="row-actions">
          <button class="small-button" data-user-toggle="${user.id}" data-user-active="${user.is_active ? "false" : "true"}">
            ${user.is_active ? "Tắt" : "Bật"}
          </button>
          <button class="small-button" data-user-note="${user.id}" data-current-note="${escapeHtml(user.note || "")}">Ghi chú</button>
          <button class="small-button" data-user-expiry="${user.id}">Hạn dùng</button>
          <button class="small-button danger" data-user-delete="${user.id}">Xóa</button>
        </div>
      </td>
    </tr>
  `).join("") || emptyRow(11);
}

function renderLicenses() {
  const rows = state.licenses.filter((license) => includesText(license, state.filters.licenses));
  $("#licensesCount").textContent = `${rows.length}/${state.licenses.length}`;
  $("#licensesTable").innerHTML = rows.map((license) => `
    <tr>
      <td><span class="license-key">${escapeHtml(license.license_key)}</span></td>
      <td>${escapeHtml(license.username || "-")} <span class="muted">#${license.user_id}</span></td>
      <td>${escapeHtml(license.allowed_ip || "Tự lock")}</td>
      <td>${escapeHtml(license.mt_account || "-")}</td>
      <td>${statusPill(license.is_active)}</td>
      <td>${formatDate(license.expires_at)}</td>
      <td>${license.verify_count} / ${formatDate(license.last_verified)}</td>
      <td>
        <div class="row-actions">
          <button class="small-button" data-copy="${escapeHtml(license.license_key)}">Sao chép</button>
          <button class="small-button" data-reset-ip="${escapeHtml(license.license_key)}">Reset IP</button>
          <button class="small-button" data-set-ip="${escapeHtml(license.license_key)}" data-current-ip="${escapeHtml(license.allowed_ip || "")}">Đặt IP</button>
          <button class="small-button" data-set-mt="${escapeHtml(license.license_key)}" data-current-mt="${escapeHtml(license.mt_account || "")}">MT</button>
          <button class="small-button" data-license-expiry="${escapeHtml(license.license_key)}">Hạn dùng</button>
          <button class="small-button" data-license-toggle="${escapeHtml(license.license_key)}" data-license-active="${license.is_active ? "false" : "true"}">
            ${license.is_active ? "Tắt" : "Bật"}
          </button>
          <button class="small-button danger" data-revoke="${escapeHtml(license.license_key)}">Thu hồi</button>
        </div>
      </td>
    </tr>
  `).join("") || emptyRow(8);
}

function renderSessions() {
  const rows = state.sessions.filter((session) => includesText(session, state.filters.sessions));
  $("#sessionsCount").textContent = `${rows.length}/${state.sessions.length}`;
  $("#sessionsTable").innerHTML = rows.map((session) => `
    <tr>
      <td>${formatDate(session.created_at)}</td>
      <td>${escapeHtml(session.license_key)}</td>
      <td>${escapeHtml(session.ip_address)}</td>
      <td>${actionPill(session.action)}</td>
      <td>${escapeHtml(session.mt_account || "-")}</td>
      <td>${escapeHtml(session.reason || "-")}</td>
    </tr>
  `).join("") || emptyRow(6);
}

function renderTrades() {
  const rows = filteredTrades();
  $("#tradesCount").textContent = `${rows.length}/${state.trades.length}`;
  $("#tradesTable").innerHTML = rows.map((trade) => `
    <tr>
      <td>${escapeHtml(trade.ticket)}</td>
      <td><span class="license-key">${escapeHtml(shortKey(trade.license_key))}</span></td>
      <td>${escapeHtml(trade.symbol)}</td>
      <td>${sidePill(trade.direction)}</td>
      <td>${tradeStatusPill(trade.status)}</td>
      <td>${trade.entry_price}</td>
      <td>${trade.sl_price ?? "-"} / ${trade.tp_price ?? "-"}</td>
      <td>${money(trade.profit)} (${trade.pips ?? "-"} pips)</td>
      <td>${formatDate(trade.opened_at)}</td>
      <td>${escapeHtml(trade.note || "-")}</td>
    </tr>
  `).join("") || emptyRow(10);
}

function filteredTrades() {
  return state.trades.filter((trade) => {
    if (!includesText(trade, state.filters.trades)) return false;
    if (state.filters.tradeStatus && trade.status !== state.filters.tradeStatus) return false;
    if (state.filters.tradeSide && trade.direction !== state.filters.tradeSide) return false;
    return true;
  });
}

function groupTrades(keyFn) {
  const groups = new Map();
  state.trades.forEach((trade) => {
    const key = keyFn(trade);
    const group = groups.get(key) || {key, trades: 0, open: 0, closed: 0, wins: 0, profit: 0};
    group.trades += 1;
    if (trade.status === "open") group.open += 1;
    if (trade.status === "closed") {
      group.closed += 1;
      const profit = Number(trade.profit || 0);
      group.profit += profit;
      if (profit > 0) group.wins += 1;
    }
    groups.set(key, group);
  });
  return Array.from(groups.values()).sort((a, b) => b.profit - a.profit);
}

function winRateText(wins, closed) {
  return closed ? `${Math.round((wins / closed) * 100)}%` : "0%";
}

function renderAnalytics() {
  const closed = state.trades.filter((trade) => trade.status === "closed");
  const wins = closed.filter((trade) => Number(trade.profit || 0) > 0);
  const grossWin = wins.reduce((sum, trade) => sum + Number(trade.profit || 0), 0);
  const grossLoss = Math.abs(closed.filter((trade) => Number(trade.profit || 0) < 0)
    .reduce((sum, trade) => sum + Number(trade.profit || 0), 0));
  const profitFactor = grossLoss ? grossWin / grossLoss : 0;
  const totalProfit = closed.reduce((sum, trade) => sum + Number(trade.profit || 0), 0);
  const best = closed.slice().sort((a, b) => Number(b.profit || 0) - Number(a.profit || 0))[0];
  const worst = closed.slice().sort((a, b) => Number(a.profit || 0) - Number(b.profit || 0))[0];
  const symbols = new Set(state.trades.map((trade) => trade.symbol));

  $("#winRate").textContent = winRateText(wins.length, closed.length);
  $("#winRateDetail").textContent = `${wins.length} thắng / ${closed.length} đã đóng`;
  $("#profitFactor").textContent = profitFactor.toFixed(2);
  $("#avgClosedProfit").textContent = money(closed.length ? totalProfit / closed.length : 0);
  $("#bestTrade").textContent = money(best?.profit || 0);
  $("#bestTradeTicket").textContent = best ? best.ticket : "-";
  $("#worstTrade").textContent = money(worst?.profit || 0);
  $("#worstTradeTicket").textContent = worst ? worst.ticket : "-";
  $("#symbolCount").textContent = symbols.size;

  $("#symbolAnalyticsTable").innerHTML = groupTrades((trade) => trade.symbol).map((group) => `
    <tr>
      <td>${escapeHtml(group.key)}</td>
      <td>${group.trades}</td>
      <td>${group.open}</td>
      <td>${group.closed}</td>
      <td>${winRateText(group.wins, group.closed)}</td>
      <td>${money(group.profit)}</td>
    </tr>
  `).join("") || emptyRow(6);

  $("#sideAnalyticsTable").innerHTML = groupTrades((trade) => trade.direction).map((group) => `
    <tr>
      <td>${sidePill(group.key)}</td>
      <td>${group.trades}</td>
      <td>${group.closed}</td>
      <td>${winRateText(group.wins, group.closed)}</td>
      <td>${money(group.profit)}</td>
    </tr>
  `).join("") || emptyRow(5);
}

function renderCommands() {
  const table = $("#commandsTable");
  if (!table) return;
  const rows = state.commands.filter((command) => includesText(command, state.filters.commands));
  $("#commandsCount").textContent = `${rows.length}/${state.commands.length}`;
  table.innerHTML = rows.map((command) => `
    <tr>
      <td>#${command.id}</td>
      <td><span class="license-key">${escapeHtml(shortKey(command.target_license_key))}</span></td>
      <td>${escapeHtml(commandActionLabel(command.action))}</td>
      <td>${escapeHtml(command.symbol || "-")}</td>
      <td>${commandStatusPill(command.status)}</td>
      <td>${escapeHtml(command.reason || "-")}</td>
      <td>${escapeHtml(command.result || "-")}</td>
      <td>${formatDate(command.created_at)}</td>
      <td><span class="muted">Chỉ xem</span></td>
    </tr>
  `).join("") || emptyRow(9);
}

function renderReadiness() {
  if (!state.readiness || !$("#readinessList")) return;
  const data = state.readiness;
  $("#readyActiveUsers").textContent = data.counts.active_users;
  $("#readyActiveLicenses").textContent = data.counts.active_licenses;
  $("#readyOpenTrades").textContent = data.counts.open_trades;
  $("#readyRejects").textContent = data.counts.rejects_24h;
  $("#readyPendingCommands").textContent = data.counts.pending_commands;
  $("#readyDbSize").textContent = bytesText(data.server.database_size_bytes);

  $("#readinessList").innerHTML = data.checks.map((check) => `
    <article class="readiness-item ${escapeHtml(check.status)}">
      <span>${readinessIcon(check.status)}</span>
      <div>
        <strong>${escapeHtml(check.name)}</strong>
        <p>${escapeHtml(check.detail)}</p>
      </div>
    </article>
  `).join("");

  $("#serverInfo").innerHTML = `
    <div><strong>Cổng</strong><span>${escapeHtml(data.server.port)}</span></div>
    <div><strong>Timeout ping</strong><span>${escapeHtml(data.server.bot_ping_timeout_seconds)}s</span></div>
    <div><strong>Cơ sở dữ liệu</strong><span>${escapeHtml(data.server.database_url)}</span></div>
    <div><strong>Cập nhật</strong><span>${formatDate(data.timestamp)}</span></div>
  `;
}

function numberFromInput(id, fallback) {
  const element = $(id);
  if (!element) return fallback;
  const value = Number(element.value);
  return Number.isFinite(value) ? value : fallback;
}

function renderPnlCalculator() {
  if (!$("#pnlCalculator")) return;
  const orders = Math.max(1, Math.round(numberFromInput("#calcOrders", 1)));
  const cost = Math.max(0, numberFromInput("#calcCost", 0));
  const winRate = Math.min(99, Math.max(1, numberFromInput("#calcWinRate", 50))) / 100;
  const avgWin = Math.max(0, numberFromInput("#calcAvgWin", 0));
  const avgLoss = Math.max(0, numberFromInput("#calcAvgLoss", 0));
  const signals = Math.max(1, Math.round(numberFromInput("#calcSignals", 1)));

  const grossPerOrder = winRate * avgWin - (1 - winRate) * avgLoss;
  const netPerOrder = grossPerOrder - cost;
  const costPerSignal = cost * orders;
  const netPerSignal = netPerOrder * orders;
  const dailyEv = netPerSignal * signals;
  const breakeven = avgWin + avgLoss > 0 ? ((avgLoss + cost) / (avgWin + avgLoss)) * 100 : 0;

  $("#calcCostSignal").textContent = money(costPerSignal);
  $("#calcNetSignal").textContent = money(netPerSignal);
  $("#calcDailyEv").textContent = money(dailyEv);
  $("#calcBreakeven").textContent = percentText(breakeven);
  $("#calcNetSignal").className = netPerSignal >= 0 ? "profit-positive" : "profit-negative";
  $("#calcDailyEv").className = dailyEv >= 0 ? "profit-positive" : "profit-negative";
}

function generateCandles(scenario = "up") {
  const candles = [];
  let price = 1.0800;

  for (let index = 0; index < 80; index += 1) {
    let drift = 0;
    if (scenario === "up") drift = 0.00012;
    if (scenario === "down") drift = -0.00012;
    if (scenario === "range") drift = Math.sin(index / 3) * 0.00004;

    const wave = Math.sin(index / 4) * 0.00008;
    const open = price;
    const close = Math.max(0.0001, open + drift + wave);
    const high = Math.max(open, close) + 0.00035;
    const low = Math.min(open, close) - 0.00035;
    price = close;

    candles.push({
      open: Number(open.toFixed(5)),
      high: Number(high.toFixed(5)),
      low: Number(low.toFixed(5)),
      close: Number(close.toFixed(5)),
      volume: 1000 + index * 3,
    });
  }

  return candles;
}

function fillDemoCandles() {
  const scenario = new FormData($("#aiBotForm")).get("scenario");
  $("#candlesInput").value = JSON.stringify(generateCandles(scenario), null, 2);
  $("#aiBotMessage").textContent = "Demo candles generated.";
}

async function analyzeAiBot(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  $("#aiBotMessage").textContent = "";
  $("#paperTradeBtn").disabled = true;

  try {
    const candles = JSON.parse($("#candlesInput").value || "[]");
    const result = await api("/admin/ai/trend", {
      method: "POST",
      body: JSON.stringify({
        symbol: form.get("symbol"),
        timeframe: form.get("timeframe"),
        strategy: form.get("strategy"),
        candles,
      }),
    });
    state.lastSignal = {
      ...result,
      lot_size: Number(form.get("lot_size") || 0.01),
    };
    renderSignal(result);
    $("#paperTradeBtn").disabled = result.signal === "HOLD";
  } catch (error) {
    $("#aiBotMessage").textContent = error.message;
    state.lastSignal = null;
    renderSignal(null);
  }
}

function rememberNotification(id) {
  state.seenNotifications.add(id);
  const recent = Array.from(state.seenNotifications).slice(-80);
  state.seenNotifications = new Set(recent);
  localStorage.setItem("seen_notifications", JSON.stringify(recent));
}

function renderNotifications(notifications, toastNew = true) {
  state.activity = notifications;
  updateNotificationBadge(notifications.length);
  updateLiveAlert(notifications[0]);
  renderActivity();
  renderOps();
  const list = $("#notificationList");
  if (list) {
    list.innerHTML = notifications.map((item) => {
      const isNew = state.seenNotifications.has(item.id) ? "" : "new";
      return `
      <div class="notification-item ${escapeHtml(safeSeverity(item.severity))} ${isNew}">
        <div>
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.message)}</span>
        </div>
        <time>${formatDate(item.created_at)}</time>
      </div>`;
    }).join("") || '<div class="empty-state compact">Chưa có thông báo</div>';
  }

  notifications
    .slice()
    .reverse()
    .forEach((item) => {
      if (state.seenNotifications.has(item.id)) return;
      rememberNotification(item.id);
      if (toastNew) {
        showToast(`${item.title}: ${item.message}`, item.severity);
        playAlertTone(item.severity);
        sendDesktopAlert(item.title, item.message);
      }
    });
}

function renderActivity() {
  const feed = $("#activityFeed");
  if (!feed) return;
  $("#activityCount").textContent = state.activity.length;
  feed.innerHTML = state.activity.map((item) => `
    <article class="activity-item ${escapeHtml(item.severity)}">
      <div class="activity-icon">${item.type === "trade" ? "TR" : "BT"}</div>
      <div>
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.message)}</p>
      </div>
      <time>${formatDate(item.created_at)}</time>
    </article>
  `).join("") || '<div class="empty-state compact">Chưa có hoạt động</div>';
}

async function pollNotifications() {
  if (!state.token) return;
  try {
    const [notifications, trades, bots, mt5Accounts, ops, commands, readiness, runtimeStatuses] = await Promise.all([
      optionalApi("/admin/notifications?limit=10", []),
      api("/admin/trades?limit=100"),
      api("/admin/bots"),
      optionalApi("/admin/mt5-accounts", state.mt5Accounts),
      optionalApi("/admin/ops-summary", null),
      optionalApi("/admin/commands?limit=100", []),
      optionalApi("/admin/readiness", null),
      optionalApi("/admin/bot-statuses?limit=100", state.runtimeStatuses),
    ]);
    state.trades = trades;
    state.bots = bots;
    state.mt5Accounts = mt5Accounts;
    state.ops = ops;
    state.commands = commands;
    state.readiness = readiness;
    state.runtimeStatuses = runtimeStatuses;
    renderNotifications(notifications, true);
    renderTrades();
    renderBots();
    renderMt5AccountOptions();
    renderMt5Accounts();
    renderAnalytics();
    renderOps();
    renderCommands();
    renderReadiness();
  } catch (error) {
    console.warn(error);
  }
}

function renderSignal(result) {
  if (!result) {
    $("#signalCard").innerHTML = '<div class="empty-state">Chưa có tín hiệu</div>';
    return;
  }

  const indicators = Object.entries(result.indicators || {})
    .map(([key, value]) => `<div><strong>${escapeHtml(key)}</strong><br>${escapeHtml(value)}</div>`)
    .join("");

  $("#signalCard").innerHTML = `
    <div class="signal-main">
      <div class="signal-metric">
        <span>Tín hiệu</span>
        <strong>${signalPill(result.signal)}</strong>
      </div>
      <div class="signal-metric">
        <span>Xu hướng</span>
        <strong>${escapeHtml(result.trend)}</strong>
      </div>
      <div class="signal-metric">
        <span>Giá vào</span>
        <strong>${escapeHtml(result.entry_price)}</strong>
      </div>
      <div class="signal-metric">
        <span>SL / TP</span>
        <strong>${escapeHtml(result.sl_price ?? "-")} / ${escapeHtml(result.tp_price ?? "-")}</strong>
      </div>
    </div>
    <div class="reason-box">${escapeHtml(result.reason)} Độ tin cậy: ${Math.round(result.confidence * 100)}%</div>
    <div class="indicator-grid">${indicators}</div>
  `;
}

async function createPaperTrade() {
  if (!state.lastSignal || state.lastSignal.signal === "HOLD") return;

  const result = await api("/admin/web-bot/paper-trade", {
    method: "POST",
    body: JSON.stringify({
      symbol: state.lastSignal.symbol,
      direction: state.lastSignal.signal,
      entry_price: state.lastSignal.entry_price,
      sl_price: state.lastSignal.sl_price,
      tp_price: state.lastSignal.tp_price,
      lot_size: state.lastSignal.lot_size,
      note: `Lệnh paper từ Web AI Bot: ${state.lastSignal.reason}`,
    }),
  });

  showToast(`Đã tạo lệnh paper: ${result.ticket}`);
  await refreshAll();
  setView("trades");
}

function emptyRow(columns) {
  return `<tr><td colspan="${columns}" class="muted">Không có dữ liệu</td></tr>`;
}

function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return "";
  if (seconds < 60) return `${seconds}s trước`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} phút trước`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ trước`;
  return `${Math.floor(seconds / 86400)} ngày trước`;
}

function statusPill(active) {
  return `<span class="pill ${active ? "ok" : "bad"}">${active ? "Đang hoạt động" : "Đã tắt"}</span>`;
}

function botStatusPill(status) {
  const labels = {
    online: "Đang online",
    offline: "Mất kết nối",
    never_connected: "Chưa từng kết nối",
    revoked: "Đã thu hồi",
    user_disabled: "User đã tắt",
  };
  const cls = status === "online" ? "ok" : status === "never_connected" ? "warn" : "bad";
  return `<span class="pill ${cls}">${labels[status] || escapeHtml(status)}</span>`;
}

function actionPill(action) {
  const labels = {
    verify: "Xác thực",
    reject: "Từ chối",
    ping: "Ping",
  };
  const cls = action === "reject" ? "bad" : action === "verify" ? "ok" : "warn";
  return `<span class="pill ${cls}">${escapeHtml(labels[action] || action)}</span>`;
}

function sidePill(direction) {
  return `<span class="pill ${direction === "BUY" ? "ok" : "warn"}">${escapeHtml(direction)}</span>`;
}

function signalPill(signal) {
  const cls = signal === "BUY" ? "ok" : signal === "SELL" ? "warn" : "";
  return `<span class="pill ${cls}">${escapeHtml(signal)}</span>`;
}

function tradeStatusPill(status) {
  const labels = {
    open: "Đang mở",
    closed: "Đã đóng",
    cancelled: "Đã hủy",
  };
  const cls = status === "closed" ? "ok" : status === "cancelled" ? "bad" : "warn";
  return `<span class="pill ${cls}">${escapeHtml(labels[status] || status)}</span>`;
}

function commandStatusPill(status) {
  const labels = {
    pending: "Đang chờ",
    delivered: "Đã gửi",
    done: "Hoàn tất",
    failed: "Lỗi",
    cancelled: "Đã hủy",
  };
  const cls = status === "done" ? "ok" : status === "failed" || status === "cancelled" ? "bad" : "warn";
  return `<span class="pill ${cls}">${escapeHtml(labels[status] || status)}</span>`;
}

function commandActionLabel(action) {
  const labels = {
    pause: "Tạm dừng",
    resume: "Chạy lại",
    close_all: "Đóng tất cả",
    close_symbol: "Đóng theo mã",
    set_config: "Cập nhật cấu hình",
  };
  return labels[action] || action;
}

function readinessIcon(status) {
  if (status === "ok") return "OK";
  if (status === "bad") return "SỬA";
  return "CẢNH BÁO";
}

function setView(view) {
  state.currentView = view;
  document.querySelectorAll(".view").forEach((element) => element.classList.add("hidden"));
  $(`#view-${view}`).classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  $("#pageTitle").textContent = pageMeta[view][0];
  $("#pageSubtitle").textContent = pageMeta[view][1];
}

async function createUser(event) {
  event.preventDefault();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  $("#userMessage").textContent = "";

  try {
    const data = await api("/admin/users", {
      method: "POST",
      body: JSON.stringify({
        username: form.get("username"),
        email: form.get("email"),
        note: form.get("note") || null,
      }),
    });
    $("#userMessage").textContent = `Đã tạo người dùng #${data.user_id}`;
    formElement.reset();
    await refreshAll();
  } catch (error) {
    $("#userMessage").textContent = error.message;
  }
}

async function createLicense(event) {
  event.preventDefault();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  $("#licenseMessage").textContent = "";

  try {
    const data = await api("/admin/licenses", {
      method: "POST",
      body: JSON.stringify({
        user_id: Number(form.get("user_id")),
        allowed_ip: form.get("allowed_ip") || null,
        mt_account: form.get("mt_account") || null,
      }),
    });
    $("#licenseMessage").textContent = `License: ${data.license_key}`;
    formElement.reset();
    await refreshAll();
  } catch (error) {
    $("#licenseMessage").textContent = error.message;
  }
}

async function handleLicenseAction(event) {
  const copyKey = event.target.dataset.copy;
  const resetKey = event.target.dataset.resetIp;
  const revokeKey = event.target.dataset.revoke;
  const toggleKey = event.target.dataset.licenseToggle;
  const toggleActive = event.target.dataset.licenseActive;
  const setIpKey = event.target.dataset.setIp;
  const setMtKey = event.target.dataset.setMt;
  const licenseExpiryKey = event.target.dataset.licenseExpiry;

  if (copyKey) {
    await navigator.clipboard.writeText(copyKey);
    showToast("Đã copy license");
    return;
  }

  if (resetKey) {
    await api("/admin/licenses/update-ip", {
      method: "PATCH",
      body: JSON.stringify({license_key: resetKey, new_ip: ""}),
    });
    await refreshAll();
    showToast("Đã reset IP lock");
    return;
  }

  if (setIpKey) {
    const ip = window.prompt("Nhập IP được phép. Để trống để tự lock.", event.target.dataset.currentIp || "");
    if (ip === null) return;
    await api("/admin/licenses/update-ip", {
      method: "PATCH",
      body: JSON.stringify({license_key: setIpKey, new_ip: ip}),
    });
    await refreshAll();
    showToast("Đã cập nhật IP được phép");
    return;
  }

  if (setMtKey) {
    const mt = window.prompt("Nhập MT account. Để trống để xóa.", event.target.dataset.currentMt || "");
    if (mt === null) return;
    await api("/admin/licenses/update-ip", {
      method: "PATCH",
      body: JSON.stringify({license_key: setMtKey, mt_account: mt}),
    });
    await refreshAll();
    showToast("Đã cập nhật MT account");
    return;
  }

  if (licenseExpiryKey) {
    const expiresAt = window.prompt("Nhập ngày hết hạn license dạng ISO, ví dụ 2026-12-31T23:59:00");
    if (!expiresAt) return;
    await api("/admin/licenses/update-ip", {
      method: "PATCH",
      body: JSON.stringify({license_key: licenseExpiryKey, expires_at: expiresAt}),
    });
    await refreshAll();
    showToast("Đã cập nhật hạn dùng license");
    return;
  }

  if (toggleKey) {
    await api("/admin/licenses/update-ip", {
      method: "PATCH",
      body: JSON.stringify({license_key: toggleKey, is_active: toggleActive === "true"}),
    });
    await refreshAll();
    showToast(toggleActive === "true" ? "Đã bật license" : "Đã tắt license");
    return;
  }

  if (revokeKey) {
    const confirmed = window.confirm("Thu hồi license này?");
    if (!confirmed) return;
    await api(`/admin/licenses/${encodeURIComponent(revokeKey)}`, {method: "DELETE"});
    await refreshAll();
    showToast("Đã thu hồi license");
  }
}

async function handleUserAction(event) {
  const toggleUser = event.target.dataset.userToggle;
  const toggleActive = event.target.dataset.userActive;
  const noteUser = event.target.dataset.userNote;
  const expiryUser = event.target.dataset.userExpiry;
  const deleteUser = event.target.dataset.userDelete;

  if (toggleUser) {
    await api(`/admin/users/${toggleUser}`, {
      method: "PATCH",
      body: JSON.stringify({is_active: toggleActive === "true"}),
    });
    await refreshAll();
    showToast(toggleActive === "true" ? "Đã bật người dùng" : "Đã tắt người dùng");
    return;
  }

  if (noteUser) {
    const currentNote = event.target.dataset.currentNote || "";
    const note = window.prompt("Cập nhật ghi chú người dùng", currentNote);
    if (note === null) return;
    await api(`/admin/users/${noteUser}`, {
      method: "PATCH",
      body: JSON.stringify({note}),
    });
    await refreshAll();
    showToast("Đã cập nhật ghi chú người dùng");
    return;
  }

  if (expiryUser) {
    const expiresAt = window.prompt("Nhập ngày hết hạn người dùng dạng ISO, ví dụ 2026-12-31T23:59:00");
    if (!expiresAt) return;
    await api(`/admin/users/${expiryUser}`, {
      method: "PATCH",
      body: JSON.stringify({expires_at: expiresAt}),
    });
    await refreshAll();
    showToast("Đã cập nhật hạn dùng người dùng");
    return;
  }

  if (deleteUser) {
    const confirmed = window.confirm("Xóa người dùng này và các license liên quan?");
    if (!confirmed) return;
    await api(`/admin/users/${deleteUser}`, {method: "DELETE"});
    await refreshAll();
    showToast("Đã xóa người dùng");
  }
}

async function submitMt5Account(event) {
  event.preventDefault();
  const formElement = event.currentTarget;
  const isEdit = Boolean(state.editingMt5AccountId);
  $("#mt5AccountMessage").textContent = "";
  try {
    const payload = mt5AccountPayloadFromForm(formElement, isEdit);
    const path = isEdit ? `/admin/mt5-accounts/${state.editingMt5AccountId}` : "/admin/mt5-accounts";
    const method = isEdit ? "PATCH" : "POST";
    await api(path, {
      method,
      body: JSON.stringify(payload),
    });
    showToast(isEdit ? "Đã cập nhật tài khoản MT5" : "Đã thêm tài khoản MT5");
    resetMt5AccountForm();
    await refreshAll();
    setView("mt5-accounts");
  } catch (error) {
    $("#mt5AccountMessage").textContent = error.message;
  }
}

async function handleMt5AccountAction(event) {
  const button = event.target.closest("button");
  if (!button) return;
  const commandId = button.dataset.mt5Command;
  const commandAction = button.dataset.mt5Action;
  const editId = button.dataset.mt5Edit;
  const deleteId = button.dataset.mt5Delete;
  const statsId = button.dataset.mt5Stats;

  if (statsId) {
    await loadMt5TradeStats(statsId);
    return;
  }

  if (editId) {
    const account = state.mt5Accounts.find((item) => String(item.id) === String(editId));
    if (account && !account.can_admin_operate) {
      showToast("Account này do user tự thêm, admin không sửa cấu hình", "warn");
      return;
    }
    fillMt5AccountForm(account);
    return;
  }

  if (deleteId) {
    const confirmed = window.confirm("Xóa tài khoản MT5 này khỏi web?");
    if (!confirmed) return;
    await api(`/admin/mt5-accounts/${deleteId}`, {method: "DELETE"});
    showToast("Đã xóa tài khoản MT5");
    await refreshAll();
    return;
  }

  if (commandId && commandAction) {
    const account = state.mt5Accounts.find((item) => String(item.id) === String(commandId));
    if (account && !account.can_admin_operate) {
      showToast("Account này do user tự vận hành, admin không Run/Stop/Restart", "warn");
      return;
    }
    const reason = window.prompt(`Lý do ${commandAction} tài khoản MT5`, `Admin ${commandAction}`);
    if (reason === null) return;
    const data = await api(`/admin/mt5-accounts/${commandId}/command`, {
      method: "POST",
      body: JSON.stringify({action: commandAction, reason}),
    });
    showToast(data.message || "Đã gửi trạng thái tài khoản MT5");
    await refreshAll();
  }
}

async function handleMt5StatsPanelAction(event) {
  const button = event.target.closest("[data-mt5-stats-days]");
  if (!button || !state.mt5TradeStatsAccountId) return;
  await loadMt5TradeStats(state.mt5TradeStatsAccountId, Number(button.dataset.mt5StatsDays || 0));
}

function handleFilterInput(event) {
  const {id, value} = event.target;
  if (id === "botsFilter") {
    state.filters.bots = value;
    renderBots();
  } else if (id === "mt5AccountsFilter") {
    state.filters.mt5Accounts = value;
    renderMt5Accounts();
  } else if (id === "usersFilter") {
    state.filters.users = value;
    renderUsers();
  } else if (id === "licensesFilter") {
    state.filters.licenses = value;
    renderLicenses();
  } else if (id === "sessionsFilter") {
    state.filters.sessions = value;
    renderSessions();
  } else if (id === "tradesFilter") {
    state.filters.trades = value;
    renderTrades();
  } else if (id === "tradeStatusFilter") {
    state.filters.tradeStatus = value;
    renderTrades();
  } else if (id === "tradeSideFilter") {
    state.filters.tradeSide = value;
    renderTrades();
  } else if (id === "mt5StatsTradeSearch") {
    state.filters.mt5StatsTradeSearch = value;
    renderMt5TradeStats();
  } else if (id === "mt5StatsTradeStatus") {
    state.filters.mt5StatsTradeStatus = value;
    renderMt5TradeStats();
  } else if (id === "mt5StatsTradeDirection") {
    state.filters.mt5StatsTradeDirection = value;
    renderMt5TradeStats();
  } else if (id === "commandsFilter") {
    state.filters.commands = value;
    renderCommands();
  }
}

async function copyOnlineLicenses() {
  const online = state.bots.filter((bot) => bot.status === "online").map((bot) => bot.license_key);
  await navigator.clipboard.writeText(online.join("\n"));
  showToast(`Đã copy ${online.length} license online`);
}

function readCommandPayload() {
  const text = ($("#commandPayload")?.value || "").trim();
  if (!text) return {};
  return JSON.parse(text);
}

async function sendBotCommand(body) {
  const data = await api("/admin/commands", {
    method: "POST",
    body: JSON.stringify(body),
  });
  showToast(data.message || "Đã gửi lệnh điều khiển");
  await refreshAll();
  setView("control");
}

async function submitCommand(event) {
  event.preventDefault();
  $("#commandMessage").textContent = "";
  const form = new FormData(event.currentTarget);
  try {
    await sendBotCommand({
      target_license_key: form.get("target_license_key") || null,
      action: form.get("action"),
      symbol: form.get("symbol") || null,
      reason: form.get("reason") || "Lệnh thủ công từ dashboard admin",
      payload: readCommandPayload(),
    });
  } catch (error) {
    $("#commandMessage").textContent = error.message;
  }
}

async function quickCommand(event) {
  const button = event.target.closest("[data-quick-command]");
  if (!button) return;
  const action = button.dataset.quickCommand;
  const symbol = button.dataset.symbol || null;
  const dangerous = action === "pause" || action === "close_all" || action === "close_symbol";
  if (dangerous && !window.confirm(`Gửi lệnh ${action}${symbol ? ` ${symbol}` : ""} tới tất cả bot active?`)) return;
  await sendBotCommand({
    action,
    symbol,
    reason: `Lệnh nhanh ${action}${symbol ? ` ${symbol}` : ""} từ bảng điều khiển`,
    payload: {},
  });
}

async function handleCommandAction(event) {
  const commandId = event.target.dataset.cancelCommand;
  if (!commandId) return;
  if (!window.confirm(`Hủy lệnh điều khiển #${commandId}?`)) return;
  await api(`/admin/commands/${commandId}/cancel`, {method: "PATCH"});
  showToast("Đã hủy lệnh điều khiển");
  await refreshAll();
}

function bindToolActions() {
  $("#exportTradesBtn").addEventListener("click", () => downloadCsv("trades.csv", filteredTrades()));
  $("#exportMt5AccountsBtn").addEventListener("click", () => downloadCsv("mt5_accounts.csv", filteredMt5Accounts()));
  $("#exportUsersBtn").addEventListener("click", () => downloadCsv("users.csv", state.users));
  $("#exportLicensesBtn").addEventListener("click", () => downloadCsv("licenses.csv", state.licenses));
  $("#exportSessionsBtn").addEventListener("click", () => downloadCsv("sessions.csv", state.sessions));
  $("#copyOnlineBotsBtn").addEventListener("click", copyOnlineLicenses);
  $("#clearSeenBtn").addEventListener("click", () => {
    state.seenNotifications = new Set();
    localStorage.removeItem("seen_notifications");
    showToast("Đã reset bộ nhớ thông báo");
  });
  $("#healthCheckBtn").addEventListener("click", async () => {
    await checkHealth();
    $("#toolsMessage").textContent = `Đã kiểm tra server lúc ${new Date().toLocaleTimeString()}`;
  });
}

function updateAlertButtons() {
  $("#soundToggleBtn").textContent = state.soundEnabled ? "Âm: bật" : "Âm: tắt";
  $("#soundToggleBtn").classList.toggle("active-alert", state.soundEnabled);
  $("#desktopNotifyBtn").textContent = state.desktopAlerts ? "Desktop: bật" : "Desktop: tắt";
  $("#desktopNotifyBtn").classList.toggle("active-alert", state.desktopAlerts);
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
  $("#loginForm").addEventListener("submit", login);
  $("#logoutBtn").addEventListener("click", logout);
  $("#refreshBtn").addEventListener("click", () => refreshAll().then(() => showToast("Đã làm mới")));
  $("#notificationJumpBtn").addEventListener("click", () => setView("activity"));
  $("#soundToggleBtn").addEventListener("click", () => {
    state.soundEnabled = !state.soundEnabled;
    localStorage.setItem("sound_enabled", String(state.soundEnabled));
    updateAlertButtons();
    if (state.soundEnabled) playAlertTone("ok");
  });
  $("#desktopNotifyBtn").addEventListener("click", async () => {
    if (!("Notification" in window)) {
      showToast("Trình duyệt không hỗ trợ thông báo desktop");
      return;
    }
    if (Notification.permission !== "granted") {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        showToast("Thông báo desktop đang bị chặn");
        return;
      }
    }
    state.desktopAlerts = !state.desktopAlerts;
    localStorage.setItem("desktop_alerts", String(state.desktopAlerts));
    updateAlertButtons();
    showToast(state.desktopAlerts ? "Đã bật thông báo desktop" : "Đã tắt thông báo desktop");
  });
  $("#createUserForm").addEventListener("submit", createUser);
  $("#createLicenseForm").addEventListener("submit", createLicense);
  $("#mt5AccountForm").addEventListener("submit", submitMt5Account);
  $("#resetMt5AccountFormBtn").addEventListener("click", resetMt5AccountForm);
  $("#commandForm").addEventListener("submit", submitCommand);
  document.querySelector(".command-actions").addEventListener("click", quickCommand);
  $("#aiBotForm").addEventListener("submit", analyzeAiBot);
  $("#generateCandlesBtn").addEventListener("click", fillDemoCandles);
  $("#paperTradeBtn").addEventListener("click", createPaperTrade);
  $("#licensesTable").addEventListener("click", handleLicenseAction);
  $("#mt5AccountsTable").addEventListener("click", handleMt5AccountAction);
  $("#mt5TradeStatsPanel").addEventListener("click", handleMt5StatsPanelAction);
  $("#usersTable").addEventListener("click", handleUserAction);
  $("#commandsTable").addEventListener("click", handleCommandAction);
  [
    "#botsFilter",
    "#mt5AccountsFilter",
    "#usersFilter",
    "#licensesFilter",
    "#sessionsFilter",
    "#tradesFilter",
    "#tradeStatusFilter",
    "#tradeSideFilter",
    "#mt5StatsTradeSearch",
    "#mt5StatsTradeStatus",
    "#mt5StatsTradeDirection",
    "#commandsFilter",
  ].forEach((selector) => $(selector).addEventListener("input", handleFilterInput));
  document.querySelectorAll(".strategy-input").forEach((input) => {
    input.addEventListener("input", renderPnlCalculator);
  });
  bindToolActions();
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
}

async function boot() {
  bindEvents();
  startUiMotion();
  updateAlertButtons();
  setAuthenticated(Boolean(state.token));
  setView("overview");
  fillDemoCandles();
  renderPnlCalculator();
  await checkHealth();

  if (state.token) {
    try {
      await refreshAll();
      startNotificationPolling();
    } catch (error) {
      logout();
      showToast(error.message);
    }
  }
}

boot();
