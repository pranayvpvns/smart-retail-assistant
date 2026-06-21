/* ══════════════════════════════════════════
   App Logic — Smart Retail Assistant
   ══════════════════════════════════════════ */

let currentPage = "dashboard";
let selectedFile = null;
let recordsPage = 1;
let forecastChart = null;

/* ── Init — check for active session ── */
document.addEventListener("DOMContentLoaded", () => {
  if (api.isAuthenticated) {
    showApp();
    navigateTo("dashboard");
  } else {
    showAuth();
  }
  lucide.createIcons();
});

/* ══════════ Navigation ══════════ */
function showAuth() {
  document.getElementById("auth-screen").classList.remove("hidden");
  document.getElementById("app-shell").classList.add("hidden");
  lucide.createIcons();
}

function showApp() {
  document.getElementById("auth-screen").classList.add("hidden");
  document.getElementById("app-shell").classList.remove("hidden");
  const user = api.getUser();
  if (user) {
    document.getElementById("sidebar-store-name").textContent = user.store_name || "Dashboard";
    document.getElementById("sidebar-user-email").textContent = user.email || "";
  }
  lucide.createIcons();
  checkHealth();
}

function navigateTo(page) {
  currentPage = page;
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.getElementById("page-" + page).classList.add("active");
  document.querySelectorAll(".nav-item").forEach(n => n.classList.toggle("active", n.dataset.page === page));
  const titles = {
    dashboard: "Dashboard",
    analytics: "Retail Analytics",
    insights:  "AI Insight Synthesis",
    data:      "Data Manager",
    forecast:  "Demand Forecast",
    anomaly:   "Anomaly Alerts",
    assistant: "AI Assistant",
    products:  "Inventory",
    orders:    "Orders",
  };
  document.getElementById("page-title").textContent = titles[page] || "Dashboard";
  if (page === "dashboard") loadDashboard();
  else if (page === "analytics") loadAnalyticsPage();
  else if (page === "data")      loadRecords();
  else if (page === "forecast")  loadProducts();
  else if (page === "anomaly")   loadAlerts();
  else if (page === "assistant") loadAssistantPage();
  else if (page === "products")  loadOwnerProducts();
  else if (page === "orders")    loadOwnerOrders();
  document.getElementById("sidebar").classList.remove("open");
}

function toggleSidebar() {
  document.getElementById("sidebar").classList.toggle("open");
}

/* ══════════ Auth ══════════ */
function showAuthTab(tab) {
  document.getElementById("tab-login").classList.toggle("active", tab === "login");
  document.getElementById("tab-register").classList.toggle("active", tab === "register");
  document.getElementById("login-form").classList.toggle("hidden", tab !== "login");
  document.getElementById("register-form").classList.toggle("hidden", tab !== "register");
  document.getElementById("auth-error").classList.add("hidden");
  lucide.createIcons();
}

/** Visual-only login role tabs — just changes the hint text */
function setLoginRole(role) {
  document.getElementById("login-role-owner").classList.toggle("active", role === "owner");
  document.getElementById("login-role-user").classList.toggle("active", role === "user");
  const hint = document.getElementById("login-role-hint");
  hint.textContent = role === "owner"
    ? "Sign in to your owner account to access the analytics dashboard."
    : "Sign in as a buyer to browse and order from our marketplace.";
}

function showRoleTab(role) {
  document.getElementById("role-tab-owner").classList.toggle("active", role === "owner");
  document.getElementById("role-tab-user").classList.toggle("active", role === "user");
  document.getElementById("owner-register-form").classList.toggle("hidden", role !== "owner");
  document.getElementById("buyer-register-form").classList.toggle("hidden", role !== "user");
  document.getElementById("auth-error").classList.add("hidden");
  lucide.createIcons();
}

async function handleLogin(e) {
  e.preventDefault();
  const email    = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;
  const btn      = document.getElementById("login-btn");
  
  // Check which role is currently active in the UI
  const isOwnerTab = document.getElementById("login-role-owner").classList.contains("active");
  const expectedRole = isOwnerTab ? "owner" : "user";

  btn.disabled   = true;
  try {
    const data = await api.login(email, password);
    
    // Optional: Role enforcement check
    if (data.role !== expectedRole) {
      const roleName = expectedRole === "owner" ? "Owner" : "Buyer";
      throw { error: `This account is not registered as a ${roleName}. Please switch tabs.` };
    }

    if (data.role === "user") {
      // Buyers → marketplace
      window.location.href = "marketplace.html";
    } else {
      showApp();
      navigateTo("dashboard");
      toast("Welcome back!", "success");
    }
  } catch (err) {
    console.error("Login Error:", err);
    const msg = err.error || err.message || "Connection to server failed. Is the backend running?";
    showAuthError(msg);
  } finally { btn.disabled = false; }
}

async function handleRegister(e) {
  e.preventDefault();
  const store_name = document.getElementById("reg-store").value;
  const email      = document.getElementById("reg-email").value;
  const password   = document.getElementById("reg-password").value;
  const btn        = document.getElementById("register-btn");
  btn.disabled     = true;
  try {
    // We register but DO NOT auto-login anymore.
    // api.register returns the account info but we won't set the token here.
    await api._request("POST", "/auth/register", { email, password, store_name });
    
    // Switch to login tab
    showAuthTab('login');
    setLoginRole('owner');
    
    // Clear registration form
    document.getElementById("owner-register-form").reset();
    
    toast("Owner account created! Please sign in.", "success");
  } catch (err) {
    showAuthError(err.error || "Registration failed");
  } finally { btn.disabled = false; }
}

async function handleUserRegister(e) {
  e.preventDefault();
  const name     = document.getElementById("buyer-name").value;
  const email    = document.getElementById("buyer-email").value;
  const password = document.getElementById("buyer-password").value;
  const btn      = document.getElementById("buyer-register-btn");
  btn.disabled   = true;
  try {
    // We register but DO NOT auto-login
    await api._request("POST", "/auth/user/register", { email, password, name });
    
    // Switch to login tab
    showAuthTab('login');
    setLoginRole('user');
    
    // Clear registration form
    document.getElementById("buyer-register-form").reset();

    toast("Buyer account created! Please sign in.", "success");
  } catch (err) {
    showAuthError(err.error || "Registration failed");
  } finally { btn.disabled = false; }
}

function handleLogout() {
  api.logout();
  showAuth();
  toast("Logged out", "info");
}

function showAuthError(msg) {
  const el = document.getElementById("auth-error");
  el.textContent = typeof msg === "string" ? msg : JSON.stringify(msg);
  el.classList.remove("hidden");
}


/* ══════════ Health Check ══════════ */
async function checkHealth() {
  const indicator = document.getElementById("health-indicator");
  try {
    const data = await api.health();
    const dot = indicator.querySelector(".health-dot");
    const text = indicator.querySelector(".health-text");
    if (data.status === "ok") {
      dot.className = "health-dot ok";
      text.textContent = "All Systems Online";
    } else if (data.status === "unknown") {
      dot.className = "health-dot";
      text.textContent = "Status Unavailable";
    } else {
      dot.className = "health-dot degraded";
      text.textContent = "Degraded";
    }
  } catch {
    indicator.querySelector(".health-dot").className = "health-dot";
    indicator.querySelector(".health-text").textContent = "Backend Offline";
  }
}

/* ══════════ Dashboard ══════════ */
async function loadDashboard() {
  try {
    const [recordsData, alertsData, analyticsData] = await Promise.allSettled([
      api.getRecords(1, 1),
      api.getAlerts(),
      api.getDashboardAnalytics()
    ]);

    if (analyticsData.status === "fulfilled") {
      const data = analyticsData.value;
      document.getElementById("stat-records-val").textContent = data.total_records ?? 0;
      document.getElementById("stat-products-val").textContent = data.total_products_tracked ?? 0;
      if (alertsData.status === "fulfilled") {
          const alerts = alertsData.value.alerts || [];
          const warnings = alerts.filter(a => a.severity === "warning").length;
          const criticals = alerts.filter(a => a.severity === "critical").length;
          document.getElementById("stat-warnings-val").textContent = warnings;
          document.getElementById("stat-critical-val").textContent = criticals;
          renderRecentAlerts(alerts.slice(0, 5));
      }
    }
  } catch (err) {
    console.error("Dashboard load error:", err);
    document.getElementById("stat-products-val").textContent = "—";
  }
}

function renderRecentAlerts(alerts) {
  const el = document.getElementById("recent-alerts-list");
  if (!alerts.length) { el.innerHTML = '<div class="empty-state-mini">No alerts yet</div>'; return; }
  el.innerHTML = alerts.map(a => `
    <div class="alert-mini-item">
      <span class="sev-dot ${a.severity}"></span>
      <span class="alert-text">${escHtml(a.message || a.product_id)}</span>
    </div>`).join("");
}

/* ══════════ Data Upload ══════════ */
function handleDragOver(e) { e.preventDefault(); document.getElementById("upload-zone").classList.add("drag-over"); }
function handleDragLeave(e) { document.getElementById("upload-zone").classList.remove("drag-over"); }
function handleFileDrop(e) {
  e.preventDefault();
  document.getElementById("upload-zone").classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) setSelectedFile(file);
}
function handleFileSelect(e) { if (e.target.files[0]) setSelectedFile(e.target.files[0]); }
function setSelectedFile(file) {
  selectedFile = file;
  document.getElementById("upload-filename").textContent = file.name;
  document.getElementById("upload-btn").disabled = false;
}

async function handleUpload() {
  if (!selectedFile) return;
  showLoading(true);
  try {
    const data = await api.uploadCSV(selectedFile);
    const r = data.report || {};
    const retrain = data.models_retrained || {};
    let retrainMsg = "";
    if (retrain.success) {
      retrainMsg = "<br>🤖 Models auto-retrained successfully — forecast & anomaly detection ready!";
    } else if (retrain.error) {
      retrainMsg = `<br>⚠️ Auto-retrain note: ${escHtml(retrain.error)}`;
    }
    document.getElementById("upload-result").className = "upload-result success";
    document.getElementById("upload-result").innerHTML = `
      ✅ <strong>Upload successful!</strong><br>
      Records in file: ${r.records_in_file ?? "—"} · Loaded: ${r.records_loaded ?? "—"}<br>
      Duplicates removed: ${r.duplicates_removed ?? 0} · Nulls imputed: ${r.nulls_imputed ?? 0} · Invalid dropped: ${r.invalid_rows_dropped ?? 0}${retrainMsg}`;
    document.getElementById("upload-result").classList.remove("hidden");
    selectedFile = null;
    document.getElementById("upload-btn").disabled = true;
    document.getElementById("upload-filename").textContent = "";
    loadRecords();
    loadProducts();  // refresh forecast product dropdown
    toast("CSV uploaded & models retrained", "success");
  } catch (err) {
    document.getElementById("upload-result").className = "upload-result error";
    document.getElementById("upload-result").innerHTML = `❌ ${escHtml(err.error || err.message || JSON.stringify(err.errors || err))}`;
    document.getElementById("upload-result").classList.remove("hidden");
    toast("Upload failed", "error");
  } finally { showLoading(false); }
}
async function handleLinkDataset() {
  const pathInput = document.getElementById("link-file-path");
  const resultEl  = document.getElementById("link-result");
  const path      = pathInput.value.trim();

  if (!path) {
    toast("Please enter a file path", "warning");
    return;
  }

  showLoading(true);
  resultEl.classList.add("hidden");

  try {
    const data = await api.linkDataset(path);
    resultEl.className = "upload-result success";
    resultEl.innerHTML = `✅ <strong>File linked successfully!</strong><br>
      "${escHtml(data.dataset.dataset_name)}" is now registered for direct updates.<br>
      It contains ${data.dataset.row_count} records.`;
    resultEl.classList.remove("hidden");
    pathInput.value = "";
    loadRecords();
    toast("Dataset linked", "success");
  } catch (err) {
    resultEl.className = "upload-result error";
    resultEl.innerHTML = `❌ <strong>Link failed:</strong> ${escHtml(err.error || "Server error")}`;
    resultEl.classList.remove("hidden");
    toast("Linking failed", "error");
  } finally {
    showLoading(false);
  }
}

/* ══════════ Records ══════════ */
async function loadRecords() {
  try {
    const data = await api.getRecords(recordsPage, 50);
    const tbody = document.getElementById("records-tbody");
    if (!data.records || !data.records.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">No records found</td></tr>';
      document.getElementById("records-pagination").innerHTML = "";
      return;
    }
    tbody.innerHTML = data.records.map(r => `<tr>
      <td>${escHtml(r.date || "—")}</td>
      <td>${escHtml(r.product_id || "—")}</td>
      <td>${escHtml(r.store_id || "—")}</td>
      <td>${r.quantity_sold ?? "—"}</td>
      <td>${r.revenue != null ? "$" + Number(r.revenue).toFixed(2) : "—"}</td>
    </tr>`).join("");
    renderPagination(data.total, data.page, data.limit);
    // Auto-refresh dataset list to show updated counts/paths
    loadDatasetRegistry();
  } catch (err) {
    toast("Failed to load records", "error");
  }
}

async function loadDatasetRegistry() {
  try {
    const data = await api.getDatasets();
    const tbody = document.getElementById("datasets-tbody");
    if (!tbody) return;
    if (!data.datasets || !data.datasets.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">No datasets registered</td></tr>';
      return;
    }
    tbody.innerHTML = data.datasets.map(d => `<tr>
      <td><strong>${escHtml(d.dataset_name)}</strong></td>
      <td>${d.row_count}</td>
      <td><code class="path-chip">${escHtml(d.file_path)}</code></td>
      <td>${d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString() : "—"}</td>
    </tr>`).join("");
  } catch (err) {
    console.error("Dataset registry load failed:", err);
  }
}

function renderPagination(total, page, limit) {
  const pages = Math.ceil(total / limit);
  const el = document.getElementById("records-pagination");
  if (pages <= 1) { el.innerHTML = ""; return; }
  let html = `<button ${page <= 1 ? "disabled" : ""} onclick="goPage(${page - 1})">‹ Prev</button>`;
  const start = Math.max(1, page - 2), end = Math.min(pages, page + 2);
  for (let i = start; i <= end; i++) {
    html += `<button class="${i === page ? "active" : ""}" onclick="goPage(${i})">${i}</button>`;
  }
  html += `<button ${page >= pages ? "disabled" : ""} onclick="goPage(${page + 1})">Next ›</button>`;
  el.innerHTML = html;
}

function goPage(p) { recordsPage = p; loadRecords(); }

function handleDeleteRecords() {
  openConfirmModal("Delete All Records?", "This will permanently remove all sales records, trained models, and alerts for your store.", async () => {
    showLoading(true);
    try {
      const data = await api.deleteRecords();
      toast(`Deleted ${data.records_deleted ?? 0} records. Models & alerts cleared.`, "success");
      loadRecords();
      loadDashboard();
      // Reset forecast product dropdown
      const forecastSel = document.getElementById("forecast-product");
      if (forecastSel) forecastSel.innerHTML = '<option value="">No models trained yet</option>';
      // Reset forecast chart
      if (typeof forecastChart !== 'undefined' && forecastChart) { forecastChart.destroy(); forecastChart = null; }
      const fcc = document.getElementById("forecast-chart-card");
      if (fcc) fcc.style.display = "none";
      // Reset analytics KPIs if on that page
      resetAnalyticsUI();
    } catch (err) { toast(err.error || "Delete failed", "error"); }
    finally { showLoading(false); }
  });
}

/* ══════════ Forecast ══════════ */
async function loadProducts() {
  const sel = document.getElementById("forecast-product");
  try {
    const data = await api.getProducts();
    const products = data.products || [];
    if (!products.length) {
      sel.innerHTML = '<option value="">No products found</option>';
      return;
    }
    sel.innerHTML = products.map(p => `<option value="${escHtml(p.id)}">${escHtml(p.name)}</option>`).join("");
  } catch {
    sel.innerHTML = '<option value="">Unable to load products</option>';
  }
}

async function runForecast() {
  const productId = document.getElementById("forecast-product").value;
  const days = parseInt(document.getElementById("forecast-days").value);
  if (!productId) { toast("Select a product first", "error"); return; }
  showLoading(true);
  try {
    const data = await api.getForecast(productId, days);
    renderForecastChart(data);
    renderForecastTable(data.forecast || []);
    document.getElementById("forecast-chart-card").style.display = "block";
    document.getElementById("forecast-product-badge").textContent = productId + " — " + days + " days";
    toast("Forecast generated", "success");
  } catch (err) { toast(err.error || "Forecast failed", "error"); }
  finally { showLoading(false); }
}

function renderForecastChart(data) {
  const ctx = document.getElementById("forecast-chart").getContext("2d");
  if (forecastChart) forecastChart.destroy();
  const forecast = data.forecast || [];
  const labels = forecast.map(f => f.date);
  forecastChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Predicted Sales", data: forecast.map(f => f.predicted_sales), borderColor: "#818cf8", backgroundColor: "rgba(129,140,248,.1)", fill: true, tension: .4, pointRadius: 3 },
        { label: "Upper Bound", data: forecast.map(f => f.upper_bound), borderColor: "rgba(52,211,153,.5)", borderDash: [5, 5], fill: false, tension: .4, pointRadius: 0 },
        { label: "Lower Bound", data: forecast.map(f => f.lower_bound), borderColor: "rgba(248,113,113,.5)", borderDash: [5, 5], fill: false, tension: .4, pointRadius: 0 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#94a3b8", font: { family: "Inter" } } } },
      scales: {
        x: { ticks: { color: "#64748b", font: { family: "Inter" } }, grid: { color: "rgba(255,255,255,.04)" } },
        y: { ticks: { color: "#64748b", font: { family: "Inter" } }, grid: { color: "rgba(255,255,255,.04)" }, beginAtZero: true }
      }
    }
  });
}

function renderForecastTable(forecast) {
  document.getElementById("forecast-tbody").innerHTML = forecast.map(f => `<tr>
    <td>${f.date}</td><td>${f.predicted_sales}</td><td>${f.lower_bound}</td><td>${f.upper_bound}</td>
  </tr>`).join("");
}

async function handleRetrain() {
  showLoading(true);
  try {
    await api.retrain();
    toast("Models retrained & reloaded successfully", "success");
    // Refresh relevant data
    if (currentPage === "dashboard") loadDashboard();
    if (currentPage === "analytics") loadAnalyticsPage();
    if (currentPage === "forecast") loadProducts();
  } catch (err) {
    toast(err.error || "Retrain failed", "error");
  } finally {
    showLoading(false);
  }
}

/* ══════════ Anomaly ══════════ */
async function loadAlerts() {
  const severity = document.getElementById("severity-filter")?.value || "";
  try {
    const data = await api.getAlerts(severity);
    const alerts = data.alerts || [];
    const tbody = document.getElementById("alerts-tbody");
    if (!alerts.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No alerts found</td></tr>';
    } else {
      tbody.innerHTML = alerts.map(a => `<tr>
        <td><span class="badge badge-${a.severity === "critical" ? "danger" : "warning"}">${a.severity}</span></td>
        <td>${escHtml(a.product_id || "—")}</td>
        <td>${escHtml(a.date || "—")}</td>
        <td>${a.quantity_sold ?? "—"}</td>
        <td>${a.anomaly_score ?? "—"}</td>
        <td>${escHtml(a.message || "—")}</td>
        <td>${a.detected_at ? new Date(a.detected_at).toLocaleString() : "—"}</td>
      </tr>`).join("");
    }
    document.getElementById("alert-count-bar").textContent = `Showing ${alerts.length} alert(s)`;
  } catch (err) { toast("Failed to load alerts", "error"); }
}

async function handleRunDetection() {
  showLoading(true);
  const resultEl = document.getElementById("anomaly-run-result");
  try {
    const data = await api.runDetection();
    resultEl.className = "upload-result success";
    resultEl.innerHTML = `✅ Scanned ${data.products_scanned ?? 0} products — ${data.alerts_generated ?? 0} alerts generated`;
    resultEl.classList.remove("hidden");
    
    // Refresh relevant data
    if (currentPage === "dashboard") loadDashboard();
    if (currentPage === "anomaly") loadAlerts();
    if (currentPage === "analytics") loadAnalyticsPage();

    toast("Anomaly detection complete", "success");
  } catch (err) {
    resultEl.className = "upload-result error";
    resultEl.innerHTML = `❌ ${escHtml(err.error || "Detection failed")}`;
    resultEl.classList.remove("hidden");
    toast("Detection failed", "error");
  } finally { showLoading(false); }
}

/* ══════════ Utilities ══════════ */
function escHtml(s) {
  const d = document.createElement("div"); d.textContent = s; return d.innerHTML;
}

function toast(msg, type = "info") {
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.textContent = msg;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function showLoading(show) {
  document.getElementById("loading-overlay").classList.toggle("hidden", !show);
}

function openConfirmModal(title, message, onConfirm) {
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-message").textContent = message;
  document.getElementById("confirm-modal").classList.remove("hidden");
  const btn = document.getElementById("confirm-action-btn");
  btn.onclick = () => { closeConfirmModal(); onConfirm(); };
  lucide.createIcons();
}

function closeConfirmModal() {
  document.getElementById("confirm-modal").classList.add("hidden");
}

/* ══════════ AI Assistant ══════════ */
let currentSessionId = null;
let chatBusy = false;

async function loadAssistantPage() {
  loadChatSessions();
  lucide.createIcons();
}

/* ── Sessions ── */
async function loadChatSessions() {
  try {
    const data = await api.getChatSessions();
    const sessions = data.sessions || [];
    const el = document.getElementById("sessions-list");
    if (!sessions.length) {
      el.innerHTML = '<div class="empty-state-mini">No conversations yet</div>';
      return;
    }
    el.innerHTML = sessions.map(s => {
      const isActive = s.session_id === currentSessionId;
      const date = s.last_message ? new Date(s.last_message).toLocaleDateString() : '';
      return `
        <button class="session-item ${isActive ? 'active' : ''}" onclick="loadSession('${escHtml(s.session_id)}')">
          <div class="session-item-info">
            <span class="session-id">${escHtml(s.session_id.substring(0, 8))}...</span>
            <span class="session-meta">${s.message_count || 0} msgs · ${date}</span>
          </div>
          <span class="session-delete-btn" onclick="event.stopPropagation(); handleDeleteSession('${escHtml(s.session_id)}')" title="Delete session">
            <i data-lucide="trash-2"></i>
          </span>
        </button>`;
    }).join("");
    lucide.createIcons();
  } catch (err) {
    console.error("Failed to load sessions", err);
  }
}

function handleDeleteSession(sessionId) {
  openConfirmModal(
    "Delete Conversation?",
    "This will permanently delete all messages in this chat session.",
    async () => {
      showLoading(true);
      try {
        const data = await api.deleteChatSession(sessionId);
        toast(`Deleted session (${data.deleted || 0} messages removed)`, "success");
        // If the deleted session was the currently viewed one, reset the view
        if (currentSessionId === sessionId) {
          startNewSession();
        }
        loadChatSessions();
      } catch (err) {
        toast(err.error || "Failed to delete session", "error");
      } finally {
        showLoading(false);
      }
    }
  );
}

function startNewSession() {
  currentSessionId = null;
  const messagesEl = document.getElementById("chat-messages");
  messagesEl.innerHTML = `
    <div class="chat-welcome" id="chat-welcome">
      <div class="chat-welcome-icon"><i data-lucide="sparkles"></i></div>
      <h3>Smart Retail AI Assistant</h3>
      <p>Ask me anything about your store's sales, forecasts, anomalies, or get inventory recommendations.</p>
      <div class="chat-suggestions">
        <button class="suggestion-chip" onclick="sendSuggestion('Which products need restocking?')">
          <i data-lucide="package"></i> Which products need restocking?
        </button>
        <button class="suggestion-chip" onclick="sendSuggestion('What are the forecast sales for next week?')">
          <i data-lucide="trending-up"></i> Forecast sales for next week?
        </button>
        <button class="suggestion-chip" onclick="sendSuggestion('Show me the top selling products')">
          <i data-lucide="bar-chart-3"></i> Top selling products
        </button>
        <button class="suggestion-chip" onclick="sendSuggestion('Are there any unusual sales patterns?')">
          <i data-lucide="scan-search"></i> Unusual sales patterns?
        </button>
      </div>
    </div>`;
  lucide.createIcons();
  document.querySelectorAll(".session-item").forEach(s => s.classList.remove("active"));
  document.getElementById("chat-agent-info").textContent = "";
}

async function loadSession(sessionId) {
  currentSessionId = sessionId;
  const messagesEl = document.getElementById("chat-messages");
  messagesEl.innerHTML = '<div class="chat-loading"><div class="spinner"></div></div>';
  try {
    const data = await api.getChatHistory(sessionId);
    const messages = data.messages || [];
    if (!messages.length) {
      messagesEl.innerHTML = '<div class="empty-state-mini">No messages in this session</div>';
    } else {
      messagesEl.innerHTML = messages.map(m => renderChatBubble(m.role, m.content, m.metadata)).join("");
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
    lucide.createIcons();
    loadChatSessions();
  } catch (err) {
    messagesEl.innerHTML = '<div class="empty-state-mini">Failed to load history</div>';
    toast("Failed to load chat history", "error");
  }
}

/* ── Sending Messages ── */
function sendSuggestion(text) {
  document.getElementById("chat-input").value = text;
  handleSendMessage();
}

function handleChatKeyDown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSendMessage();
  }
}

async function handleSendMessage() {
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message || chatBusy) return;

  chatBusy = true;
  const sendBtn = document.getElementById("chat-send-btn");
  sendBtn.disabled = true;

  // Remove welcome state if present
  const welcome = document.getElementById("chat-welcome");
  if (welcome) welcome.remove();

  const messagesEl = document.getElementById("chat-messages");

  // Add user bubble
  messagesEl.insertAdjacentHTML("beforeend", renderChatBubble("user", message));
  input.value = "";
  input.style.height = "auto";

  // Add thinking indicator
  const thinkingId = "thinking-" + Date.now();
  messagesEl.insertAdjacentHTML("beforeend", `
    <div class="chat-bubble assistant thinking" id="${thinkingId}">
      <div class="bubble-avatar"><i data-lucide="bot"></i></div>
      <div class="bubble-content">
        <div class="typing-dots"><span></span><span></span><span></span></div>
      </div>
    </div>`);
  lucide.createIcons();
  messagesEl.scrollTop = messagesEl.scrollHeight;

  try {
    const data = await api.sendMessage(message, currentSessionId);
    currentSessionId = data.session_id;

    // Remove thinking indicator
    document.getElementById(thinkingId)?.remove();

    // Add assistant response
    messagesEl.insertAdjacentHTML("beforeend", renderChatBubble("assistant", data.response, {
      intent: data.intent,
      agents_used: data.agents_used
    }));

    // Update agent info
    const agentInfo = document.getElementById("chat-agent-info");
    const agentNames = (data.agents_used || []).map(a => a.replace("_", " ")).join(", ");
    agentInfo.textContent = agentNames ? `Agents: ${agentNames}` : "";

    messagesEl.scrollTop = messagesEl.scrollHeight;
    lucide.createIcons();
    loadChatSessions();
    toast("Response received", "success");
  } catch (err) {
    document.getElementById(thinkingId)?.remove();
    messagesEl.insertAdjacentHTML("beforeend", renderChatBubble("assistant", `⚠️ Error: ${err.error || err.message || "Something went wrong. Please try again."}`));
    messagesEl.scrollTop = messagesEl.scrollHeight;
    toast(err.error || "Chat failed", "error");
  } finally {
    chatBusy = false;
    sendBtn.disabled = false;
  }
}

/* ── Render Chat Bubble ── */
function renderChatBubble(role, content, metadata = null) {
  const isUser = role === "user";
  const avatarIcon = isUser ? "user" : "bot";
  const intentBadge = (!isUser && metadata && metadata.intent)
    ? `<span class="chat-intent-badge">${escHtml(metadata.intent)}</span>`
    : "";
  const agentsBadge = (!isUser && metadata && metadata.agents_used && metadata.agents_used.length)
    ? `<div class="chat-agents-used">${metadata.agents_used.map(a => `<span class="agent-tag">${escHtml(a.replace('_', ' '))}</span>`).join("")}</div>`
    : "";

  // Simple markdown-ish formatting
  const formatted = formatChatContent(content);

  return `
    <div class="chat-bubble ${role}">
      <div class="bubble-avatar"><i data-lucide="${avatarIcon}"></i></div>
      <div class="bubble-content">
        <div class="bubble-text">${formatted}</div>
        ${intentBadge}${agentsBadge}
      </div>
    </div>`;
}

function formatChatContent(text) {
  if (!text) return "";
  let html = escHtml(text);
  // Bold **text**
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Bullet points
  html = html.replace(/^[\-\*]\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  // Line breaks
  html = html.replace(/\n/g, '<br>');
  // Currency highlighting
  html = html.replace(/(₹[\d,\.]+)/g, '<span class="currency-highlight">$1</span>');
  return html;
}

/* ── Embed Records ── */
async function handleEmbedRecords() {
  const btn = document.getElementById("embed-btn");
  btn.disabled = true;
  showLoading(true);
  try {
    const data = await api.embedRecords();
    toast(data.message || "Records embedded successfully", "success");
  } catch (err) {
    toast(err.error || "Embedding failed", "error");
  } finally {
    btn.disabled = false;
    showLoading(false);
  }
}

/* ── Textarea Auto-Resize ── */
function autoResizeTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

/* ── UI Helpers ── */
function escHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function toast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const t = document.createElement("div");
  t.className = `toast toast-${type}`;
  t.innerHTML = `
    <div class="toast-content">
      <i data-lucide="${type === 'success' ? 'check-circle' : (type === 'error' ? 'x-circle' : 'info')}"></i>
      <span>${escHtml(message)}</span>
    </div>`;
  container.appendChild(t);
  lucide.createIcons();
  setTimeout(() => { t.classList.add("show"); }, 10);
  setTimeout(() => {
    t.classList.remove("show");
    setTimeout(() => { t.remove(); }, 300);
  }, 4000);
}
