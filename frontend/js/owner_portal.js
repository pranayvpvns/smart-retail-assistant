/* ══════════════════════════════════════════
   Owner Portal — Products & Orders
   owner_portal.js
   ══════════════════════════════════════════ */

// ── State ──────────────────────────────────
let _editingProductId = null;
let _allOrdersPage = 1;
let _inventoryFile = null;       // staged CSV file for import

// ════════════════════════════════════════════
// INVENTORY CSV IMPORT
// ════════════════════════════════════════════

function toggleInventoryImport() {
  const panel = document.getElementById("inventory-import-panel");
  const isHidden = panel.classList.toggle("hidden");
  if (!isHidden) {
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    lucide.createIcons();
  }
}

function handleInventoryFileSelect(e) {
  _stageInventoryFile(e.target.files[0]);
}

function handleInventoryDrop(e) {
  e.preventDefault();
  document.getElementById("inv-upload-zone").classList.remove("dragging");
  const file = e.dataTransfer.files[0];
  if (file) _stageInventoryFile(file);
}

function _stageInventoryFile(file) {
  if (!file || !file.name.toLowerCase().endsWith(".csv")) {
    toast("Please select a .csv file", "error");
    return;
  }
  _inventoryFile = file;
  document.getElementById("inv-filename").textContent = `📄 ${file.name}  (${(file.size / 1024).toFixed(1)} KB)`;
  document.getElementById("inv-import-btn").disabled = false;
  document.getElementById("inv-import-result").classList.add("hidden");
}

async function handleInventoryImport() {
  if (!_inventoryFile) return;
  const btn = document.getElementById("inv-import-btn");
  const result = document.getElementById("inv-import-result");
  const mode = document.querySelector("input[name='inv-mode']:checked")?.value || "upsert";

  btn.disabled = true;
  btn.innerHTML = `<div class="spinner" style="width:16px;height:16px;border-width:2px;margin:0 auto;"></div> Importing…`;
  result.classList.add("hidden");

  try {
    const data = await api.importProductsCSV(_inventoryFile, mode);

    result.classList.remove("hidden");
    if (data.success) {
      const hasErrors = data.errors && data.errors.length;
      result.className = `inv-import-result ${hasErrors ? "result-warn" : "result-success"}`;
      result.innerHTML = `
        <div class="inv-result-stats">
          <span class="inv-stat inv-stat-created">✅ ${data.created} created</span>
          <span class="inv-stat inv-stat-updated">🔄 ${data.updated} updated</span>
          <span class="inv-stat inv-stat-skipped">⏭ ${data.skipped} skipped</span>
          ${data.failed ? `<span class="inv-stat inv-stat-failed">❌ ${data.failed} failed</span>` : ""}
        </div>
        <div class="inv-result-msg">${data.total_rows} rows processed from <strong>${esc(_inventoryFile.name)}</strong></div>
        ${hasErrors ? `
        <details class="inv-errors-detail">
          <summary>${data.errors.length} row error${data.errors.length > 1 ? "s" : ""}</summary>
          <ul>${data.errors.map(e => `<li>${esc(e)}</li>`).join("")}</ul>
        </details>` : ""}`;

      toast(`Import complete: ${data.created} created, ${data.updated} updated`, "success");
      // Reset state and reload grid
      _inventoryFile = null;
      document.getElementById("inv-filename").textContent = "";
      document.getElementById("inv-file-input").value = "";
      btn.disabled = true;
      loadOwnerProducts();
    } else {
      result.className = "inv-import-result result-error";
      result.innerHTML = `<span>❌ ${esc(data.error || "Import failed")}</span>`;
    }
  } catch (err) {
    result.classList.remove("hidden");
    result.className = "inv-import-result result-error";
    result.innerHTML = `<span>❌ ${esc(err.error || "Unexpected error")}</span>`;
  } finally {
    btn.disabled = !_inventoryFile;
    btn.innerHTML = `<i data-lucide="upload"></i> Import Products`;
    lucide.createIcons();
  }
}

// ════════════════════════════════════════════
// PRODUCT MANAGEMENT
// ════════════════════════════════════════════

async function loadOwnerProducts() {
  const grid = document.getElementById("owner-products-grid");
  grid.innerHTML = `<div class="page-loading"><div class="spinner"></div></div>`;
  try {
    const data = await api.getMyProducts();
    const products = data.products || [];
    document.getElementById("products-count-label").textContent =
      `${products.length} product${products.length !== 1 ? "s" : ""} in your catalog`;

    if (!products.length) {
      grid.innerHTML = `
        <div class="portal-empty-state">
          <i data-lucide="package-open"></i>
          <h4>No products yet</h4>
          <p>Add your first product to start selling on the marketplace.</p>
          <button class="btn btn-primary" onclick="openProductModal()">
            <i data-lucide="plus"></i> Add Product
          </button>
        </div>`;
      lucide.createIcons(); return;
    }

    grid.innerHTML = products.map(p => productCard(p)).join("");
    lucide.createIcons();
  } catch (err) {
    grid.innerHTML = `<div class="portal-empty-state"><i data-lucide="alert-circle"></i><p>Failed to load products.</p></div>`;
    lucide.createIcons();
  }
}

function productCard(p) {
  const stock = p.stock ?? 0;
  const stockCls = stock === 0 ? "stock-out" : stock < 10 ? "stock-low" : "stock-ok";
  const stockLbl = stock === 0 ? "Out of stock" : stock < 10 ? `Low (${stock})` : `${stock} in stock`;
  return `
  <div class="owner-product-card" id="opc-${esc(p.product_id)}">
    <div class="opc-img">
      ${p.image_url
      ? `<img src="${esc(p.image_url)}" alt="${esc(p.product_name)}" loading="lazy" />`
      : `<div class="opc-img-placeholder"><i data-lucide="package"></i></div>`}
    </div>
    <div class="opc-body">
      <span class="opc-category">${esc(p.category || "General")}</span>
      <h4 class="opc-name">${esc(p.product_name)}</h4>
      <div class="opc-meta-row">
        <span class="opc-price">₹${fmtNum(p.price)}</span>
        <span class="opc-stock-badge ${stockCls}">${stockLbl}</span>
      </div>
      ${p.description ? `<p class="opc-desc">${esc(p.description)}</p>` : ""}
    </div>
    <div class="opc-actions">
      <button class="btn btn-outline btn-sm" onclick="openProductModal('${esc(p.product_id)}')">
        <i data-lucide="edit-3"></i> Edit
      </button>
      <button class="btn btn-danger btn-sm" onclick="confirmDeleteProduct('${esc(p.product_id)}', '${esc(p.product_name)}')">
        <i data-lucide="trash-2"></i>
      </button>
    </div>
  </div>`;
}

// ── Product Modal ──────────────────────────
async function openProductModal(productId = null) {
  _editingProductId = productId;
  const titleEl = document.getElementById("product-modal-title");
  const saveEl = document.getElementById("product-save-btn").querySelector("span");

  // Reset form
  document.getElementById("product-form").reset();

  if (productId) {
    titleEl.innerHTML = `<i data-lucide="edit-3"></i> Edit Product`;
    saveEl.textContent = "Update Product";
    // Pre-fill form from existing data
    try {
      const data = await api.getProductDetail(productId);
      if (data) {
        document.getElementById("pf-name").value = data.product_name || "";
        document.getElementById("pf-category").value = data.category || "";
        document.getElementById("pf-price").value = data.price || "";
        document.getElementById("pf-cost").value = data.cost || "";
        document.getElementById("pf-stock").value = data.stock ?? "";
        document.getElementById("pf-image").value = data.image_url || "";
        document.getElementById("pf-description").value = data.description || "";
      }
    } catch { /* use empty form */ }
  } else {
    titleEl.innerHTML = `<i data-lucide="package"></i> Add Product`;
    saveEl.textContent = "Save Product";
  }

  document.getElementById("product-modal").classList.remove("hidden");
  lucide.createIcons();
}

function closeProductModal() {
  document.getElementById("product-modal").classList.add("hidden");
  _editingProductId = null;
}

async function handleProductSave(e) {
  e.preventDefault();
  const btn = document.getElementById("product-save-btn");
  btn.disabled = true;

  const payload = {
    product_name: document.getElementById("pf-name").value.trim(),
    category: document.getElementById("pf-category").value.trim() || "General",
    price: parseFloat(document.getElementById("pf-price").value),
    cost: parseFloat(document.getElementById("pf-cost").value || "0"),
    stock: parseInt(document.getElementById("pf-stock").value || "0"),
    image_url: document.getElementById("pf-image").value.trim(),
    description: document.getElementById("pf-description").value.trim(),
  };

  try {
    if (_editingProductId) {
      await api.updateProduct(_editingProductId, payload);
      toast("Product updated successfully!", "success");
    } else {
      await api.addProduct(payload);
      toast("Product added to catalog!", "success");
    }
    closeProductModal();
    loadOwnerProducts();
  } catch (err) {
    toast(err.error || "Failed to save product", "error");
  } finally {
    btn.disabled = false;
  }
}

function confirmDeleteProduct(productId, productName) {
  showConfirmModal(
    "Delete Product",
    `Are you sure you want to delete "${productName}"? This cannot be undone.`,
    async () => {
      try {
        await api.deleteProduct(productId);
        toast("Product deleted.", "success");
        loadOwnerProducts();
      } catch (err) {
        toast(err.error || "Failed to delete product", "error");
      }
    }
  );
}

// ════════════════════════════════════════════
// ORDER MANAGEMENT
// ════════════════════════════════════════════

async function loadOwnerOrders() {
  switchOrderTab("pending");   // always start on pending tab
}

function switchOrderTab(tab) {
  const isPending = tab === "pending";
  document.getElementById("otab-pending").classList.toggle("active", isPending);
  document.getElementById("otab-all").classList.toggle("active", !isPending);
  document.getElementById("orders-pending-panel").classList.toggle("hidden", !isPending);
  document.getElementById("orders-all-panel").classList.toggle("hidden", isPending);
  if (isPending) loadPendingOrders();
  else loadAllOrders(1);
}

// ── Pending Orders ─────────────────────────
async function loadPendingOrders() {
  const list = document.getElementById("pending-orders-list");
  list.innerHTML = `<div class="page-loading"><div class="spinner"></div></div>`;
  try {
    const data = await api.getPendingOrders();
    const orders = data.pending || [];

    // Update badge
    const badgeEl = document.getElementById("pending-orders-badge");
    const countEl = document.getElementById("otab-pending-count");
    badgeEl.textContent = orders.length;
    badgeEl.classList.toggle("hidden", orders.length === 0);
    countEl.textContent = orders.length;

    if (!orders.length) {
      list.innerHTML = `
        <div class="portal-empty-state">
          <i data-lucide="check-circle-2"></i>
          <h4>No pending orders</h4>
          <p>All caught up! New orders will appear here when buyers place them.</p>
        </div>`;
      lucide.createIcons(); return;
    }

    list.innerHTML = orders.map(o => pendingOrderCard(o)).join("");
    lucide.createIcons();
  } catch {
    list.innerHTML = `<div class="portal-empty-state"><i data-lucide="alert-circle"></i><p>Failed to load orders.</p></div>`;
    lucide.createIcons();
  }
}

function pendingOrderCard(o) {
  // Use Intl.DateTimeFormat for robust timezone handling (forcing IST as requested)
  const date = new Intl.DateTimeFormat('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
    timeZone: 'Asia/Kolkata'
  }).format(new Date(o.ordered_at));
  return `
  <div class="order-card order-card-pending" id="oc-${esc(o.order_id)}">
    <div class="order-card-header">
      <div class="order-card-id-row">
        <span class="order-id-tag">${esc(o.order_id)}</span>
        <span class="order-status-badge pending">Pending</span>
      </div>
      <span class="order-date">${date}</span>
    </div>
    <div class="order-card-body">
      <div class="order-product-info">
        <i data-lucide="package"></i>
        <div>
          <strong>${esc(o.product_name)}</strong>
          <span class="order-cat">${esc(o.category)}</span>
        </div>
      </div>
      <div class="order-buyer-info">
        <i data-lucide="user"></i>
        <span>${esc(o.user_email)}</span>
      </div>
      <div class="order-figures">
        <div class="order-fig"><span class="fig-label">Qty</span><strong>${o.quantity}</strong></div>
        <div class="order-fig"><span class="fig-label">Unit Price</span><strong>₹${fmtNum(o.price_per_unit)}</strong></div>
        <div class="order-fig total"><span class="fig-label">Total</span><strong>₹${fmtNum(o.total_price)}</strong></div>
      </div>
    </div>
    <div class="order-card-actions">
      <button class="btn btn-primary btn-sm" onclick="openInjectModal('${esc(o.order_id)}')">
        <i data-lucide="database"></i> Inject to Dataset
      </button>
      <button class="btn btn-danger btn-sm" onclick="handleRejectOrder('${esc(o.order_id)}')">
        <i data-lucide="x-circle"></i> Reject
      </button>
    </div>
  </div>`;
}

// ── All Orders ─────────────────────────────
async function loadAllOrders(page = 1) {
  _allOrdersPage = page;
  const list = document.getElementById("all-orders-list");
  list.innerHTML = `<div class="page-loading"><div class="spinner"></div></div>`;
  try {
    const data = await api.getAllStoreOrders(page, 20);
    const orders = data.orders || [];
    if (!orders.length) {
      list.innerHTML = `<div class="portal-empty-state"><i data-lucide="shopping-bag"></i><p>No orders yet.</p></div>`;
      document.getElementById("all-orders-pagination").innerHTML = "";
      lucide.createIcons(); return;
    }
    list.innerHTML = orders.map(o => allOrderRow(o)).join("");
    renderOrdersPagination(data.total, page, 20);
    lucide.createIcons();
  } catch {
    list.innerHTML = `<div class="portal-empty-state"><i data-lucide="alert-circle"></i><p>Failed to load orders.</p></div>`;
    lucide.createIcons();
  }
}

function allOrderRow(o) {
  const date = new Intl.DateTimeFormat('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
    timeZone: 'Asia/Kolkata'
  }).format(new Date(o.ordered_at));
  const statusCls = { pending: "pending", injected: "injected", rejected: "rejected" }[o.order_status] || "pending";
  return `
  <div class="order-row">
    <div class="order-row-left">
      <span class="order-id-tag">${esc(o.order_id)}</span>
      <span class="order-status-badge ${statusCls}">${esc(o.order_status)}</span>
    </div>
    <div class="order-row-mid">
      <strong>${esc(o.product_name)}</strong>
      <span>${esc(o.user_email)}</span>
    </div>
    <div class="order-row-right">
      <span>Qty: ${o.quantity}</span>
      <strong>₹${fmtNum(o.total_price)}</strong>
      <span class="order-date">${date}</span>
    </div>
  </div>`;
}

function renderOrdersPagination(total, page, limit) {
  const pages = Math.ceil(total / limit);
  const el = document.getElementById("all-orders-pagination");
  if (pages <= 1) { el.innerHTML = ""; return; }
  let html = `<button class="page-btn" ${page <= 1 ? "disabled" : ""} onclick="loadAllOrders(${page - 1})">‹</button>`;
  for (let i = Math.max(1, page - 2); i <= Math.min(pages, page + 2); i++)
    html += `<button class="page-btn ${i === page ? "active" : ""}" onclick="loadAllOrders(${i})">${i}</button>`;
  html += `<button class="page-btn" ${page >= pages ? "disabled" : ""} onclick="loadAllOrders(${page + 1})">›</button>`;
  el.innerHTML = html;
}

// ── Inject Modal ───────────────────────────
let _cachedDatasets = [];

/** Shared helper — populates the dataset <select> from a list */
function _populateDatasetSelect(datasets) {
  const sel = document.getElementById("inject-dataset-select");
  const metaEl = document.getElementById("inject-dataset-meta");
  const confirmBtn = document.getElementById("inject-confirm-btn");
  const countEl = document.getElementById("inject-dataset-count");

  _cachedDatasets = datasets;
  countEl.textContent = datasets.length ? `(${datasets.length})` : "";

  if (!datasets.length) {
    sel.innerHTML = `<option value="">No datasets found</option>`;
    confirmBtn.disabled = true;
    metaEl.innerHTML = `
      <div class="inject-no-dataset">
        <strong>No analytics datasets registered.</strong><br>
        Upload a sales CSV via Data Manager, then click <strong>Refresh</strong>.
      </div>`;
    return;
  }

  sel.innerHTML = `<option value="">— Choose a dataset —</option>` +
    datasets.map(d => {
      const updated = d.last_updated
        ? new Date(d.last_updated).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })
        : "unknown date";
      return `<option value="${esc(d.dataset_id)}">${esc(d.dataset_name)}  ·  ${d.row_count} rows  ·  updated ${updated}</option>`;
    }).join("");

  // Reset confirmBtn and meta
  confirmBtn.disabled = true;
  metaEl.textContent = "";

  sel.onchange = () => {
    const chosen = _cachedDatasets.find(d => d.dataset_id === sel.value);
    if (chosen) {
      const updated = chosen.last_updated
        ? new Date(chosen.last_updated).toLocaleDateString("en-IN")
        : "—";
      const path = chosen.file_path
        ? `<span class="inject-ds-path" title="${esc(chosen.file_path)}">📁 ${esc(chosen.file_path.split(/[\\/]/).slice(-3).join("/"))}</span>`
        : "";
      metaEl.innerHTML = `
        <div class="inject-ds-selected-info">
          <span>📊 ${chosen.row_count} rows</span>
          <span>🕒 Last updated: ${updated}</span>
          ${path}
        </div>`;
      confirmBtn.disabled = false;
    } else {
      metaEl.textContent = "";
      confirmBtn.disabled = true;
    }
  };
}

/** Opens the inject modal and loads+scans datasets every time */
/**
 * ─── RELIABLE UPLOAD & INJECT ───
 * Standard file upload flow:
 * 1. User selects file (Browser Picker)
 * 2. Upload to server (registers it as dataset)
 * 3. Inject order into that dataset
 */
async function handleInjectUpload(e) {
  const file = e.target.files[0];
  if (!file) return;

  const orderId = document.getElementById("inject-order-id").value;
  const statusEl = document.getElementById("inject-status");
  const zoneEl = document.getElementById("inject-upload-zone");
  const filenameEl = document.getElementById("inject-filename");

  filenameEl.textContent = `Selected: ${file.name}`;
  zoneEl.classList.add("hidden");
  statusEl.classList.remove("hidden");

  try {
    // 1. Upload & Register (Fail-safe)
    document.getElementById("inject-status-text").textContent = "Uploading & processing data...";
    const uploadRes = await api.uploadCSV(file);
    const datasetId = uploadRes.dataset_registered.dataset_id;

    // 2. Inject order
    document.getElementById("inject-status-text").textContent = "Injecting sale record...";
    const injectRes = await api.injectOrder(orderId, datasetId);

    if (injectRes.success) {
      toast("Success! Order injected into " + file.name, "success");
      closeInjectModal();
      loadOwnerOrders();
    } else {
      throw injectRes;
    }
  } catch (err) {
    console.error(err);
    toast("Injection failed: " + (err.error || "Upload error"), "error");
    zoneEl.classList.remove("hidden");
    statusEl.classList.add("hidden");
    filenameEl.textContent = "";
  }
}

/** Opens the inject modal and resets state. Defaults to upload tab. */
async function openInjectModal(orderId) {
  document.getElementById("inject-order-id").value = orderId;
  document.getElementById("inject-modal").classList.remove("hidden");
  switchInjectTab("upload"); // reset to first tab
  lucide.createIcons();
}

/** Toggles between Upload New and Choose Existing dataset in the inject modal */
async function switchInjectTab(tab) {
  const isUpload = tab === "upload";
  document.getElementById("itab-upload").classList.toggle("active", isUpload);
  document.getElementById("itab-existing").classList.toggle("active", !isUpload);
  document.getElementById("inject-upload-panel").classList.toggle("hidden", !isUpload);
  document.getElementById("inject-existing-panel").classList.toggle("hidden", isUpload);

  if (!isUpload) {
    // Load datasets if switching to existing tab
    const sel = document.getElementById("inject-dataset-select");
    sel.innerHTML = `<option value="">Loading datasets...</option>`;
    try {
      const data = await api.getDatasetRegistry();
      _populateDatasetSelect(data.datasets || []);
    } catch (err) {
      sel.innerHTML = `<option value="">Error loading datasets</option>`;
      toast("Failed to load dataset list", "error");
    }
  }
}

function closeInjectModal() {
  document.getElementById("inject-modal").classList.add("hidden");
  document.getElementById("inject-upload-zone").classList.remove("hidden");
  document.getElementById("inject-status").classList.add("hidden");
  document.getElementById("inject-filename").textContent = "";
  document.getElementById("inject-file-input").value = "";
}

async function confirmInject() {
  const orderId = document.getElementById("inject-order-id").value;
  const datasetId = document.getElementById("inject-dataset-select").value;
  if (!datasetId) { toast("Please select a dataset", "error"); return; }

  const btn = document.getElementById("inject-confirm-btn");
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div> Injecting…`;

  try {
    await api.injectOrder(orderId, datasetId);
    toast("Sale injected into dataset successfully!", "success");
    closeInjectModal();
    loadPendingOrders();
  } catch (err) {
    toast(err.error || "Injection failed", "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="upload"></i> Inject Sale`;
    lucide.createIcons();
  }
}

// ── Reject Order ───────────────────────────
function handleRejectOrder(orderId) {
  showConfirmModal(
    "Reject Order",
    "Reject this order? The product stock will be restored automatically.",
    async () => {
      try {
        await api.rejectOrder(orderId);
        toast("Order rejected and stock restored.", "success");
        loadPendingOrders();
      } catch (err) {
        toast(err.error || "Failed to reject order", "error");
      }
    }
  );
}

// ── Pending badge on load ──────────────────
async function refreshPendingBadge() {
  try {
    const data = await api.getPendingOrders();
    const count = (data.pending || []).length;
    const badge = document.getElementById("pending-orders-badge");
    badge.textContent = count;
    badge.classList.toggle("hidden", count === 0);
  } catch { }
}

// ════════════════════════════════════════════
// HELPERS
// ════════════════════════════════════════════

function fmtNum(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function esc(s) {
  if (s == null) return "";
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Reuse the existing confirm modal from index.html */
function showConfirmModal(title, message, onConfirm) {
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-message").textContent = message;
  document.getElementById("confirm-modal").classList.remove("hidden");
  const btn = document.getElementById("confirm-action-btn");
  btn.onclick = async () => {
    closeConfirmModal();
    await onConfirm();
  };
}
