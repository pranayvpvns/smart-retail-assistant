/* ══════════════════════════════════════════
   Analytics Dashboard — Smart Retail Assistant
   ══════════════════════════════════════════ */

// ── Chart Instances ──
let analyticsTrendChart = null;
let analyticsCategoryChart = null;
let analyticsProductsChart = null;
let analyticsForecastChart = null;

// ── Cached Data ──
let analyticsData = null;
let currentTrendMetric = "revenue";

// ── Chart Color Palette ──
const CHART_COLORS = {
  primary: "#818cf8",
  primaryLight: "rgba(129, 140, 248, .15)",
  accent: "#06b6d4",
  accentLight: "rgba(6, 182, 212, .15)",
  success: "#34d399",
  successLight: "rgba(52, 211, 153, .15)",
  warning: "#fbbf24",
  warningLight: "rgba(251, 191, 36, .15)",
  danger: "#f87171",
  dangerLight: "rgba(248, 113, 113, .15)",
  purple: "#a78bfa",
  purpleLight: "rgba(167, 139, 250, .15)",
  pink: "#f472b6",
  pinkLight: "rgba(244, 114, 182, .15)",
  text: "#94a3b8",
  grid: "rgba(255, 255, 255, .04)",
};

const CATEGORY_COLORS = [
  "#818cf8", "#06b6d4", "#34d399", "#fbbf24", "#f87171",
  "#a78bfa", "#f472b6", "#fb923c", "#38bdf8", "#4ade80",
];

// ── Chart.js Default Config ──
const chartDefaults = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: false,
    },
    tooltip: {
      backgroundColor: "rgba(17, 24, 39, .95)",
      titleColor: "#f1f5f9",
      bodyColor: "#94a3b8",
      borderColor: "rgba(255,255,255,.08)",
      borderWidth: 1,
      cornerRadius: 8,
      padding: 12,
      titleFont: { family: "Inter", weight: "600" },
      bodyFont: { family: "Inter" },
      displayColors: true,
      boxPadding: 4,
    },
  },
  scales: {
    x: {
      ticks: { color: "#64748b", font: { family: "Inter", size: 11 }, maxRotation: 45 },
      grid: { color: "rgba(255,255,255,.03)", drawBorder: false },
    },
    y: {
      ticks: { color: "#64748b", font: { family: "Inter", size: 11 } },
      grid: { color: "rgba(255,255,255,.04)", drawBorder: false },
      beginAtZero: true,
    },
  },
};


/* ══════════════════════════════════════════
   LOAD ANALYTICS PAGE
   ══════════════════════════════════════════ */

async function loadAnalyticsPage() {
  try {
    // Load analytics data
    analyticsData = await api.getDashboardAnalytics();
    renderKPIs(analyticsData);
    renderSalesTrendChart(analyticsData);
    renderCategoryChart(analyticsData);
    renderTopProductsChart(analyticsData);

    // Load forecast products dropdown
    loadAnalyticsForecastProducts();

    // Load alerts
    loadAnalyticsAlerts();

    lucide.createIcons();
  } catch (err) {
    console.error("Failed to load analytics:", err);
    toast("Failed to load analytics data", "error");
  }
}


/* ══════════════════════════════════════════
   KPI CARDS
   ══════════════════════════════════════════ */

function renderKPIs(data) {
  // Revenue
  const revenue = data.total_revenue || 0;
  document.getElementById("kpi-revenue").textContent = "₹" + formatNumber(revenue);

  // Orders
  document.getElementById("kpi-orders").textContent = formatNumber(data.total_orders || 0);

  // Top Category
  document.getElementById("kpi-top-category").textContent = data.top_category || "N/A";

  // Products Sold
  document.getElementById("kpi-products-sold").textContent = formatNumber(data.total_products_sold || 0);

  // Active Alerts
  const alertsEl = document.getElementById("kpi-active-alerts");
  const alertCount = data.active_alerts || 0;
  alertsEl.textContent = alertCount;
  if (alertCount > 0) {
    alertsEl.classList.add("kpi-alert-active");
  } else {
    alertsEl.classList.remove("kpi-alert-active");
  }

  // Animate KPI values
  animateKPIs();
}

function animateKPIs() {
  document.querySelectorAll(".analytics-kpi-card").forEach((card, i) => {
    card.style.animationDelay = `${i * 0.08}s`;
    card.classList.add("kpi-animate-in");
  });
}


/* ══════════════════════════════════════════
   SALES TREND CHART
   ══════════════════════════════════════════ */

function renderSalesTrendChart(data) {
  const ctx = document.getElementById("analytics-trend-chart").getContext("2d");
  if (analyticsTrendChart) analyticsTrendChart.destroy();

  const salesByDate = data.sales_by_date || [];
  const labels = salesByDate.map(d => formatDateLabel(d.date));
  const revenueData = salesByDate.map(d => d.revenue);
  const quantityData = salesByDate.map(d => d.quantity);

  const isRevenue = currentTrendMetric === "revenue";
  const chartData = isRevenue ? revenueData : quantityData;

  // Create gradient
  const gradient = ctx.createLinearGradient(0, 0, 0, 320);
  gradient.addColorStop(0, isRevenue ? "rgba(129, 140, 248, .25)" : "rgba(6, 182, 212, .25)");
  gradient.addColorStop(1, "rgba(0, 0, 0, 0)");

  analyticsTrendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: isRevenue ? "Revenue (₹)" : "Quantity Sold",
        data: chartData,
        borderColor: isRevenue ? CHART_COLORS.primary : CHART_COLORS.accent,
        backgroundColor: gradient,
        fill: true,
        tension: 0.4,
        pointRadius: salesByDate.length > 30 ? 0 : 3,
        pointHoverRadius: 6,
        pointBackgroundColor: isRevenue ? CHART_COLORS.primary : CHART_COLORS.accent,
        pointBorderColor: "#0a0e1a",
        pointBorderWidth: 2,
        borderWidth: 2.5,
      }],
    },
    options: {
      ...chartDefaults,
      plugins: {
        ...chartDefaults.plugins,
        tooltip: {
          ...chartDefaults.plugins.tooltip,
          callbacks: {
            label: (ctx) => isRevenue ? `₹${formatNumber(ctx.parsed.y)}` : `${ctx.parsed.y} units`,
          },
        },
      },
      interaction: {
        intersect: false,
        mode: "index",
      },
    },
  });
}

function toggleSalesTrendMetric(metric, btn) {
  currentTrendMetric = metric;
  document.querySelectorAll(".chart-toggle-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  if (analyticsData) renderSalesTrendChart(analyticsData);
}


/* ══════════════════════════════════════════
   CATEGORY DOUGHNUT CHART
   ══════════════════════════════════════════ */

function renderCategoryChart(data) {
  const ctx = document.getElementById("analytics-category-chart").getContext("2d");
  if (analyticsCategoryChart) analyticsCategoryChart.destroy();

  const categories = data.sales_by_category || [];
  if (!categories.length) return;

  const labels = categories.map(c => c.category);
  const revenues = categories.map(c => c.revenue);
  const colors = categories.map((_, i) => CATEGORY_COLORS[i % CATEGORY_COLORS.length]);

  analyticsCategoryChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: revenues,
        backgroundColor: colors.map(c => c + "cc"),
        borderColor: colors,
        borderWidth: 2,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: {
        legend: { display: false },
        tooltip: {
          ...chartDefaults.plugins.tooltip,
          callbacks: {
            label: (ctx) => `${ctx.label}: ₹${formatNumber(ctx.parsed)}`,
          },
        },
      },
    },
  });

  // Render custom legend
  const legendEl = document.getElementById("analytics-category-legend");
  legendEl.innerHTML = categories.map((c, i) => `
    <div class="cat-legend-item">
      <span class="cat-legend-dot" style="background:${CATEGORY_COLORS[i % CATEGORY_COLORS.length]}"></span>
      <span class="cat-legend-label">${escHtml(c.category)}</span>
      <span class="cat-legend-value">₹${formatNumber(c.revenue)}</span>
    </div>
  `).join("");
}


/* ══════════════════════════════════════════
   TOP PRODUCTS BAR CHART
   ══════════════════════════════════════════ */

function renderTopProductsChart(data) {
  const ctx = document.getElementById("analytics-products-chart").getContext("2d");
  if (analyticsProductsChart) analyticsProductsChart.destroy();

  const products = data.top_products || [];
  if (!products.length) return;

  const labels = products.map(p => p.product_name || p.product_id);
  const revenues = products.map(p => p.revenue);

  // Create gradient bars
  const barColors = products.map((_, i) => {
    const hue = 230 + (i * 25);
    return `hsla(${hue}, 70%, 65%, 0.85)`;
  });

  analyticsProductsChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Revenue (₹)",
        data: revenues,
        backgroundColor: barColors,
        borderColor: barColors.map(c => c.replace("0.85", "1")),
        borderWidth: 1,
        borderRadius: 6,
        borderSkipped: false,
        barPercentage: 0.7,
      }],
    },
    options: {
      ...chartDefaults,
      indexAxis: "y",
      plugins: {
        ...chartDefaults.plugins,
        tooltip: {
          ...chartDefaults.plugins.tooltip,
          callbacks: {
            label: (ctx) => `Revenue: ₹${formatNumber(ctx.parsed.x)}`,
          },
        },
      },
      scales: {
        x: {
          type: "logarithmic",
          min: 1,
          ticks: {
            callback: (v) => "₹" + formatCompact(v),
            color: "#64748b",
            font: { family: "Inter", size: 10 },
          },
          grid: { color: "rgba(255,255,255,.03)" },
        },
        y: {
          ...chartDefaults.scales.x,
          ticks: {
            ...chartDefaults.scales.x.ticks,
            font: { family: "Inter", size: 11, weight: "500" },
          },
        },
      },
    },
  });
}


/* ══════════════════════════════════════════
   FORECAST PREVIEW
   ══════════════════════════════════════════ */

async function loadAnalyticsForecastProducts() {
  const sel = document.getElementById("analytics-forecast-product");
  try {
    const data = await api.getProducts();
    const products = data.products || [];
    if (!products.length) {
      sel.innerHTML = '<option value="">No products found</option>';
      return;
    }
    sel.innerHTML = '<option value="">Select Product</option>' +
      products.map(p => `<option value="${escHtml(p.id)}">${escHtml(p.name)}</option>`).join("");
  } catch {
    sel.innerHTML = '<option value="">Unable to load products</option>';
  }
}

async function loadAnalyticsForecast() {
  const productId = document.getElementById("analytics-forecast-product").value;
  const summaryEl = document.getElementById("analytics-forecast-summary");

  if (!productId) {
    summaryEl.innerHTML = `
      <div class="forecast-summary-empty">
        <i data-lucide="line-chart"></i>
        <span>Select a product to view forecast</span>
      </div>`;
    if (analyticsForecastChart) { analyticsForecastChart.destroy(); analyticsForecastChart = null; }
    lucide.createIcons();
    return;
  }

  try {
    const data = await api.getForecast(productId, 14);
    renderAnalyticsForecastChart(data);
    renderForecastSummary(data, summaryEl);
    lucide.createIcons();
  } catch (err) {
    summaryEl.innerHTML = `<div class="forecast-summary-error"><i data-lucide="alert-circle"></i> ${escHtml(err.error || "Forecast unavailable")}</div>`;
    lucide.createIcons();
  }
}

function renderAnalyticsForecastChart(data) {
  const ctx = document.getElementById("analytics-forecast-chart").getContext("2d");
  if (analyticsForecastChart) analyticsForecastChart.destroy();

  const forecast = data.forecast || [];
  const labels = forecast.map(f => formatDateLabel(f.date));

  const gradient = ctx.createLinearGradient(0, 0, 0, 250);
  gradient.addColorStop(0, "rgba(52, 211, 153, .2)");
  gradient.addColorStop(1, "rgba(0, 0, 0, 0)");

  analyticsForecastChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Predicted Sales",
          data: forecast.map(f => f.predicted_sales),
          borderColor: CHART_COLORS.success,
          backgroundColor: gradient,
          fill: true,
          tension: 0.4,
          pointRadius: 3,
          pointHoverRadius: 6,
          borderWidth: 2.5,
          pointBackgroundColor: CHART_COLORS.success,
          pointBorderColor: "#0a0e1a",
          pointBorderWidth: 2,
        },
        {
          label: "Upper Bound",
          data: forecast.map(f => f.upper_bound),
          borderColor: "rgba(129, 140, 248, .4)",
          borderDash: [5, 5],
          fill: false,
          tension: 0.4,
          pointRadius: 0,
          borderWidth: 1.5,
        },
        {
          label: "Lower Bound",
          data: forecast.map(f => f.lower_bound),
          borderColor: "rgba(248, 113, 113, .4)",
          borderDash: [5, 5],
          fill: false,
          tension: 0.4,
          pointRadius: 0,
          borderWidth: 1.5,
        },
      ],
    },
    options: {
      ...chartDefaults,
      plugins: {
        ...chartDefaults.plugins,
        legend: {
          display: true,
          position: "top",
          labels: {
            color: "#94a3b8",
            font: { family: "Inter", size: 10 },
            boxWidth: 12,
            padding: 10,
          },
        },
      },
    },
  });
}

function renderForecastSummary(data, el) {
  const forecast = data.forecast || [];
  if (!forecast.length) return;

  const avgPredicted = forecast.reduce((s, f) => s + f.predicted_sales, 0) / forecast.length;
  const maxDay = forecast.reduce((max, f) => f.predicted_sales > max.predicted_sales ? f : max, forecast[0]);
  const trend = forecast[forecast.length - 1].predicted_sales > forecast[0].predicted_sales ? "increase" : "decrease";
  const trendIcon = trend === "increase" ? "trending-up" : "trending-down";
  const trendClass = trend === "increase" ? "forecast-trend-up" : "forecast-trend-down";

  el.innerHTML = `
    <div class="forecast-summary-cards">
      <div class="forecast-mini-card">
        <span class="forecast-mini-label">Avg. Daily Sales</span>
        <span class="forecast-mini-value">${avgPredicted.toFixed(1)}</span>
      </div>
      <div class="forecast-mini-card">
        <span class="forecast-mini-label">Peak Day</span>
        <span class="forecast-mini-value">${formatDateLabel(maxDay.date)}</span>
      </div>
      <div class="forecast-mini-card ${trendClass}">
        <span class="forecast-mini-label">14-Day Trend</span>
        <span class="forecast-mini-value"><i data-lucide="${trendIcon}"></i> ${trend === "increase" ? "Rising" : "Falling"}</span>
      </div>
    </div>
    <div class="forecast-insight">
      <i data-lucide="lightbulb"></i>
      <span>${escHtml(data.product_id)} sales expected to <strong>${trend}</strong> over the next ${data.days} days. Average predicted: <strong>${avgPredicted.toFixed(1)} units/day</strong>.</span>
    </div>
  `;
}


/* ══════════════════════════════════════════
   ANOMALY ALERTS
   ══════════════════════════════════════════ */

async function loadAnalyticsAlerts() {
  try {
    const data = await api.getAlerts();
    const alerts = data.alerts || [];
    const grid = document.getElementById("analytics-alerts-grid");

    if (!alerts.length) {
      grid.innerHTML = `
        <div class="analytics-empty-state">
          <i data-lucide="check-circle"></i>
          <span>No anomaly alerts detected — all clear!</span>
        </div>`;
      lucide.createIcons();
      return;
    }

    // Show latest 8 alerts
    grid.innerHTML = alerts.slice(0, 8).map(a => {
      const isCritical = a.severity === "critical";
      const icon = isCritical ? "alert-octagon" : "alert-triangle";
      const colorClass = isCritical ? "alert-card-critical" : "alert-card-warning";

      return `
        <div class="analytics-alert-card ${colorClass}">
          <div class="alert-card-header">
            <i data-lucide="${icon}"></i>
            <span class="alert-severity-tag ${a.severity}">${a.severity}</span>
          </div>
          <div class="alert-card-product">${escHtml(a.product_name || a.product_id || "Unknown")}</div>
          <div class="alert-card-message">${escHtml(a.message || "Anomaly detected")}</div>
          <div class="alert-card-meta">
            <span><i data-lucide="calendar"></i> ${escHtml(a.date || "—")}</span>
            <span><i data-lucide="hash"></i> Score: ${a.anomaly_score ?? "—"}</span>
          </div>
        </div>`;
    }).join("");

    if (alerts.length > 8) {
      grid.innerHTML += `
        <div class="analytics-alert-more" onclick="navigateTo('anomaly')">
          <i data-lucide="arrow-right"></i>
          <span>View all ${alerts.length} alerts</span>
        </div>`;
    }

    lucide.createIcons();
  } catch (err) {
    console.error("Failed to load analytics alerts:", err);
  }
}


/* ══════════════════════════════════════════
   AI INSIGHT SYNTHESIS
   ══════════════════════════════════════════ */

const INSIGHT_CATEGORY_META = {
  inventory:  { icon: "package",       color: "#fbbf24", label: "Inventory" },
  demand:     { icon: "trending-up",   color: "#818cf8", label: "Demand" },
  revenue:    { icon: "indian-rupee",  color: "#34d399", label: "Revenue" },
  anomaly:    { icon: "shield-alert",  color: "#f87171", label: "Anomaly" },
  operations: { icon: "settings",      color: "#06b6d4", label: "Operations" },
};

const INSIGHT_PRIORITY_META = {
  critical: { class: "priority-critical", label: "Critical", icon: "alert-octagon" },
  high:     { class: "priority-high",     label: "High",     icon: "alert-triangle" },
  medium:   { class: "priority-medium",   label: "Medium",   icon: "info" },
  low:      { class: "priority-low",      label: "Low",      icon: "circle" },
};

async function loadInsightSynthesis() {
  const container = document.getElementById("insight-cards-container");
  const summaryEl = document.getElementById("insight-executive-summary");
  const btn = document.getElementById("insight-generate-btn");

  btn.disabled = true;
  btn.innerHTML = `<span class="insight-btn-spinner"></span><span>Synthesizing...</span>`;
  summaryEl.style.display = "none";

  container.innerHTML = `
    <div class="insight-loading">
      <div class="insight-loading-grid">
        <div class="insight-loading-card"><div class="insight-shimmer"></div><div class="insight-shimmer insight-shimmer-short"></div><div class="insight-shimmer insight-shimmer-long"></div></div>
        <div class="insight-loading-card"><div class="insight-shimmer"></div><div class="insight-shimmer insight-shimmer-short"></div><div class="insight-shimmer insight-shimmer-long"></div></div>
        <div class="insight-loading-card"><div class="insight-shimmer"></div><div class="insight-shimmer insight-shimmer-short"></div><div class="insight-shimmer insight-shimmer-long"></div></div>
        <div class="insight-loading-card"><div class="insight-shimmer"></div><div class="insight-shimmer insight-shimmer-short"></div><div class="insight-shimmer insight-shimmer-long"></div></div>
      </div>
      <div class="insight-loading-status">
        <div class="insight-loading-pulse"></div>
        <div class="insight-loading-text">
          <span class="insight-loading-title">Analyzing ML Signals...</span>
          <span class="insight-loading-sub">Collecting forecasts, anomalies, and sales data → Synthesizing business insights</span>
        </div>
      </div>
    </div>`;

  try {
    const data = await api.getInsights();

    if (!data.success) {
      renderInsightError(container, data.error || "No insights available.");
      summaryEl.style.display = "none";
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="sparkles"></i><span>Synthesize Insights</span>`;
      lucide.createIcons();
      return;
    }

    // Render executive summary
    renderExecutiveSummary(data);

    // Render insight cards
    renderInsightCards(data.insights || []);

    toast("AI insights synthesized successfully", "success");
  } catch (err) {
    renderInsightError(container, err.error || "Insight synthesis failed. Please try again.");
    summaryEl.style.display = "none";
    toast("Insight synthesis failed", "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="sparkles"></i><span>Synthesize Insights</span>`;
    lucide.createIcons();
  }
}

function renderExecutiveSummary(data) {
  const summaryEl = document.getElementById("insight-executive-summary");
  const textEl = document.getElementById("insight-summary-text");
  const signalsEl = document.getElementById("insight-signals-used");

  textEl.textContent = data.executive_summary || "";
  summaryEl.style.display = data.executive_summary ? "flex" : "none";

  // Signal source badges
  const signals = data.signals_used || {};
  const signalChips = [];
  if (signals.sales_data) signalChips.push(`<span class="signal-chip signal-active"><i data-lucide="database"></i> Sales Data</span>`);
  if (signals.forecasts) signalChips.push(`<span class="signal-chip signal-active"><i data-lucide="trending-up"></i> Forecasts</span>`);
  if (signals.anomalies) signalChips.push(`<span class="signal-chip signal-active"><i data-lucide="shield-alert"></i> Anomalies</span>`);

  signalsEl.innerHTML = `
    <span class="signal-label">Signals used:</span>
    ${signalChips.join("")}
    <span class="signal-time"><i data-lucide="clock"></i> ${new Date(data.generated_at || Date.now()).toLocaleString()}</span>
  `;
}

function renderInsightCards(insights) {
  const container = document.getElementById("insight-cards-container");

  if (!insights.length) {
    container.innerHTML = `
      <div class="insight-empty">
        <i data-lucide="search-x"></i>
        <span>No insights generated. Ensure you have sales data uploaded and models trained.</span>
      </div>`;
    lucide.createIcons();
    return;
  }

  container.innerHTML = `<div class="insight-cards-grid">
    ${insights.map((insight, i) => renderSingleInsight(insight, i)).join("")}
  </div>
  <div class="insight-footer">
    <div class="insight-count">
      <i data-lucide="layers"></i>
      <span>${insights.length} insights generated from ${_countSignalSources(insights)} data sources</span>
    </div>
    <button class="btn btn-outline btn-sm" onclick="loadInsightSynthesis()">
      <i data-lucide="refresh-cw"></i> Regenerate
    </button>
  </div>`;

  lucide.createIcons();

  // Staggered animation
  container.querySelectorAll(".insight-card").forEach((card, i) => {
    card.style.animationDelay = `${i * 0.08}s`;
    card.classList.add("insight-card-animate");
  });
}

function renderSingleInsight(insight, index) {
  const cat = INSIGHT_CATEGORY_META[insight.category] || INSIGHT_CATEGORY_META.operations;
  const pri = INSIGHT_PRIORITY_META[insight.priority] || INSIGHT_PRIORITY_META.medium;
  const products = (insight.products || []).slice(0, 4);
  const confidence = insight.confidence || 0;

  return `
    <div class="insight-card insight-cat-${insight.category}" style="--card-accent: ${cat.color}">
      <div class="insight-card-top">
        <div class="insight-card-badges">
          <span class="insight-category-badge" style="--cat-color: ${cat.color}">
            <i data-lucide="${cat.icon}"></i> ${cat.label}
          </span>
          <span class="insight-priority-badge ${pri.class}">
            <i data-lucide="${pri.icon}"></i> ${pri.label}
          </span>
        </div>
        ${insight.metric_value ? `
          <div class="insight-metric-highlight" style="--accent: ${cat.color}">
            <span class="insight-metric-value">${escHtml(insight.metric_value)}</span>
            <span class="insight-metric-label">${escHtml(insight.metric_label || "Key Metric")}</span>
          </div>` : ""}
      </div>

      <h4 class="insight-card-title">${escHtml(insight.title || "Insight")}</h4>
      <p class="insight-card-desc">${escHtml(insight.description || "")}</p>

      <div class="insight-card-action">
        <div class="insight-action-icon"><i data-lucide="zap"></i></div>
        <span>${escHtml(insight.action || "No action specified")}</span>
      </div>

      <div class="insight-card-bottom">
        ${products.length ? `
          <div class="insight-products">
            ${products.map(p => `<span class="insight-product-chip">${escHtml(p)}</span>`).join("")}
            ${(insight.products || []).length > 4 ? `<span class="insight-product-chip insight-product-more">+${insight.products.length - 4}</span>` : ""}
          </div>` : ""}
        <div class="insight-confidence">
          <div class="insight-confidence-bar">
            <div class="insight-confidence-fill" style="width: ${confidence}%; background: ${cat.color}"></div>
          </div>
          <span class="insight-confidence-label">${confidence}%</span>
        </div>
      </div>
    </div>`;
}

function renderInsightError(container, message) {
  container.innerHTML = `
    <div class="insight-error">
      <div class="insight-error-icon"><i data-lucide="alert-circle"></i></div>
      <span>${escHtml(message)}</span>
      <button class="btn btn-outline btn-sm" onclick="loadInsightSynthesis()">
        <i data-lucide="refresh-cw"></i> Retry
      </button>
    </div>`;
  lucide.createIcons();
}

function _countSignalSources(insights) {
  const cats = new Set(insights.map(i => i.category));
  return Math.max(cats.size, 1);
}


/* ══════════════════════════════════════════
   UTILITY FUNCTIONS
   ══════════════════════════════════════════ */

function formatNumber(num) {
  if (num === null || num === undefined) return "0";
  return Number(num).toLocaleString("en-IN");
}

function formatCompact(num) {
  if (num >= 100000) return (num / 100000).toFixed(1) + "L";
  if (num >= 1000) return (num / 1000).toFixed(1) + "K";
  return num.toString();
}

function formatDateLabel(dateStr) {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  } catch {
    return dateStr;
  }
}


/* ══════════════════════════════════════════
   RESET ANALYTICS UI (after data deletion)
   ══════════════════════════════════════════ */

function resetAnalyticsUI() {
  // Reset cached data
  analyticsData = null;

  // Destroy all chart instances
  if (analyticsTrendChart) { analyticsTrendChart.destroy(); analyticsTrendChart = null; }
  if (analyticsCategoryChart) { analyticsCategoryChart.destroy(); analyticsCategoryChart = null; }
  if (analyticsProductsChart) { analyticsProductsChart.destroy(); analyticsProductsChart = null; }
  if (analyticsForecastChart) { analyticsForecastChart.destroy(); analyticsForecastChart = null; }

  // Reset KPI values
  const kpiDefaults = {
    "kpi-revenue": "₹0",
    "kpi-orders": "0",
    "kpi-top-category": "N/A",
    "kpi-products-sold": "0",
    "kpi-active-alerts": "0",
  };
  for (const [id, val] of Object.entries(kpiDefaults)) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = val;
      el.classList.remove("kpi-alert-active");
    }
  }

  // Clear category legend
  const legendEl = document.getElementById("analytics-category-legend");
  if (legendEl) legendEl.innerHTML = "";

  // Reset forecast dropdown
  const fSel = document.getElementById("analytics-forecast-product");
  if (fSel) fSel.innerHTML = '<option value="">No models trained yet</option>';

  // Reset forecast summary
  const fSummary = document.getElementById("analytics-forecast-summary");
  if (fSummary) fSummary.innerHTML = `
    <div class="forecast-summary-empty">
      <i data-lucide="line-chart"></i>
      <span>Select a product to view forecast</span>
    </div>`;

  // Reset alerts grid
  const alertsGrid = document.getElementById("analytics-alerts-grid");
  if (alertsGrid) alertsGrid.innerHTML = `
    <div class="analytics-empty-state">
      <i data-lucide="check-circle"></i>
      <span>No anomaly alerts detected</span>
    </div>`;

  // Reset AI Insight Synthesis panel
  const insightContainer = document.getElementById("insight-cards-container");
  if (insightContainer) insightContainer.innerHTML = `
    <div class="insight-placeholder">
      <div class="insight-placeholder-visual">
        <div class="insight-orbit">
          <div class="insight-orbit-ring"></div>
          <div class="insight-orbit-dot insight-dot-1"><i data-lucide="trending-up"></i></div>
          <div class="insight-orbit-dot insight-dot-2"><i data-lucide="shield-alert"></i></div>
          <div class="insight-orbit-dot insight-dot-3"><i data-lucide="package"></i></div>
          <div class="insight-orbit-dot insight-dot-4"><i data-lucide="indian-rupee"></i></div>
          <div class="insight-orbit-core"><i data-lucide="brain"></i></div>
        </div>
      </div>
      <h4>Intelligent Business Insights</h4>
      <p>Click <strong>"Synthesize Insights"</strong> to transform your ML forecasts, anomaly alerts, and sales data into prioritized, actionable business intelligence.</p>
      <div class="insight-feature-tags">
        <span class="insight-tag"><i data-lucide="trending-up"></i> Demand Forecasts</span>
        <span class="insight-tag"><i data-lucide="shield-alert"></i> Anomaly Signals</span>
        <span class="insight-tag"><i data-lucide="package"></i> Inventory Risks</span>
        <span class="insight-tag"><i data-lucide="indian-rupee"></i> Revenue Patterns</span>
        <span class="insight-tag"><i data-lucide="settings"></i> Operations</span>
      </div>
    </div>`;

  const insightSummary = document.getElementById("insight-executive-summary");
  if (insightSummary) insightSummary.style.display = "none";

  // Re-render icons
  try { lucide.createIcons(); } catch {}
}
