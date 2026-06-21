/* ══════════════════════════════════════════
   Marketplace JS — Smart Retail
   ══════════════════════════════════════════ */

// ── State ──────────────────────────────────
let mpPage = 1;
let mpCategory = "";
let mpSearch = "";
let mpSort = "default";
let mpTotal = 0;
const MP_LIMIT = 20;
let cart = [];          // [{vendorProductId, productName, store, price, quantity}]
try {
  const saved = localStorage.getItem("mp_cart");
  if (saved) cart = JSON.parse(saved);
} catch (e) { console.error("Failed to load cart", e); }

let searchTimer = null;
let ordersPage = 1;
let currentSessionId = null;
let chatBusy = false;

function saveCart() {
  localStorage.setItem("mp_cart", JSON.stringify(cart));
}

// ── Init ───────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  if (!api.isAuthenticated) { window.location.href = "index.html"; return; }
  const user = api.getUser();
  if (user && user.role !== "user") { window.location.href = "index.html"; return; }
  document.getElementById("mp-user-name").textContent = user?.name || user?.email || "Buyer";
  lucide.createIcons();
  loadCategories();
  loadProducts();
  renderCart();
});

// ── Page Switching ─────────────────────────
function showPage(name) {
  document.querySelectorAll(".mp-page").forEach(p => p.classList.remove("active"));
  document.getElementById("mp-page-" + name).classList.add("active");
  document.querySelectorAll(".mp-nav-tab").forEach(t =>
    t.classList.toggle("active", t.dataset.page === name));

  if (name === "orders") loadOrders();
  if (name === "assistant") loadChatSessions();

  lucide.createIcons();
}

// ── Categories ─────────────────────────────
async function loadCategories() {
  try {
    const data = await api.getProductCategories();
    const cats = data.categories || [];
    const nav = document.getElementById("mp-category-list");
    const extras = cats.map(c => `
      <button class="mp-cat-item" data-cat="${esc(c)}" onclick="filterCategory('${esc(c)}')">
        <i data-lucide="tag"></i> ${esc(c)}
      </button>`).join("");
    nav.innerHTML = `
      <button class="mp-cat-item active" data-cat="" onclick="filterCategory('')">
        <i data-lucide="grid-3x3"></i> All Products
      </button>${extras}`;
    lucide.createIcons();
  } catch { }
}

function filterCategory(cat) {
  showPage("shop"); // Always go back to product grid
  mpCategory = cat; mpPage = 1;
  document.querySelectorAll(".mp-cat-item").forEach(b =>
    b.classList.toggle("active", b.dataset.cat === cat));
  loadProducts();
}

// ── Search ─────────────────────────────────
function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    mpSearch = document.getElementById("mp-search-input").value.trim();
    const clr = document.getElementById("mp-search-clear");
    clr.classList.toggle("hidden", !mpSearch);
    mpPage = 1;
    loadProducts();
  }, 350);
}

function clearSearch() {
  document.getElementById("mp-search-input").value = "";
  document.getElementById("mp-search-clear").classList.add("hidden");
  mpSearch = ""; mpPage = 1;
  loadProducts();
}

// ── Sort ───────────────────────────────────
function applySort() {
  mpSort = document.getElementById("mp-sort-select").value;
  loadProducts();
}

// ── Load Products ──────────────────────────
async function loadProducts() {
  const grid = document.getElementById("mp-product-grid");
  grid.innerHTML = `<div class="mp-loading-state"><div class="mp-spinner"></div><p>Loading…</p></div>`;
  try {
    const data = await api.getMarketplaceProducts(mpSearch, mpCategory, mpPage, MP_LIMIT);
    mpTotal = data.total || 0;
    let products = data.products || [];

    // Client-side sort
    if (mpSort === "price_asc") products.sort((a, b) => (a.min_price || 0) - (b.min_price || 0));
    else if (mpSort === "price_desc") products.sort((a, b) => (b.min_price || 0) - (a.min_price || 0));
    else if (mpSort === "vendors_desc") products.sort((a, b) => (b.vendor_count || 0) - (a.vendor_count || 0));

    document.getElementById("mp-results-info").textContent =
      `${mpTotal} product${mpTotal !== 1 ? "s" : ""} found` + (mpCategory ? ` in "${mpCategory}"` : "");

    if (!products.length) {
      grid.innerHTML = `<div class="mp-empty-state"><i data-lucide="search-x"></i><p>No products found. Try a different search.</p></div>`;
      document.getElementById("mp-pagination").innerHTML = "";
      lucide.createIcons(); return;
    }

    grid.innerHTML = products.map(p => productCard(p)).join("");
    renderPagination(mpTotal, mpPage, MP_LIMIT, "mp-pagination", goProductsPage);
    lucide.createIcons();
  } catch (err) {
    grid.innerHTML = `<div class="mp-empty-state"><i data-lucide="alert-circle"></i><p>Failed to load products.</p></div>`;
    lucide.createIcons();
  }
}

function goProductsPage(p) { mpPage = p; loadProducts(); window.scrollTo(0, 0); }

// ── Product Card ───────────────────────────
function productCard(p) {
  const price = p.price != null ? `₹${Number(p.price).toLocaleString("en-IN")}` : "—";
  const inStock = (p.stock ?? 0) > 0;
  const stockLbl = !inStock ? "Out of stock" : p.stock < 10 ? `Only ${p.stock} left` : "In stock";
  return `
  <div class="mp-product-card" onclick="openProductModal('${esc(p.product_id)}')">
    <div class="mp-product-img">
      ${p.image_url
      ? `<img src="${esc(p.image_url)}" alt="${esc(p.product_name)}" loading="lazy"/>`
      : `<div class="mp-product-img-placeholder"><i data-lucide="package"></i></div>`}
    </div>
    <div class="mp-product-info">
      <span class="mp-product-cat">${esc(p.category || "General")}</span>
      <h3 class="mp-product-name">${esc(p.product_name)}</h3>
      <p class="mp-product-store"><i data-lucide="store"></i> ${esc(p.store_name || "")}</p>
      <div class="mp-product-price-row">
        <span class="mp-product-price">${price}</span>
        <span class="mp-sellers-badge ${inStock ? "" : "out-of-stock-badge"}">${stockLbl}</span>
      </div>
    </div>
    <button class="mp-quick-add" onclick="event.stopPropagation(); openProductModal('${esc(p.product_id)}')">
      <i data-lucide="plus"></i>
    </button>
  </div>`;
}

// ── Product Detail Modal ───────────────────
async function openProductModal(productId) {
  document.getElementById("mp-modal-content").innerHTML =
    `<div class="mp-modal-loading"><div class="mp-spinner"></div></div>`;
  document.getElementById("mp-product-modal").classList.remove("hidden");
  try {
    const p = await api.getProductDetail(productId);
    document.getElementById("mp-modal-content").innerHTML = productDetailHTML(p);
    lucide.createIcons();
  } catch {
    document.getElementById("mp-modal-content").innerHTML =
      `<div class="mp-empty-state"><i data-lucide="alert-circle"></i><p>Failed to load product.</p></div>`;
    lucide.createIcons();
  }
}

function closeProductModal() {
  document.getElementById("mp-product-modal").classList.add("hidden");
}

function productDetailHTML(p) {
  const inStock = (p.stock ?? 0) > 0;
  return `
  <div class="mp-modal-product">
    <div class="mp-modal-product-img">
      ${p.image_url
      ? `<img src="${esc(p.image_url)}" alt="${esc(p.product_name)}"/>`
      : `<div class="mp-product-img-placeholder large"><i data-lucide="package"></i></div>`}
    </div>
    <div class="mp-modal-product-details">
      <span class="mp-product-cat">${esc(p.category || "General")}</span>
      <h2>${esc(p.product_name)}</h2>
      <p class="mp-vendor-store"><i data-lucide="store"></i> ${esc(p.store_name || "Store")}</p>
      ${p.description ? `<p class="mp-modal-desc">${esc(p.description)}</p>` : ""}
      <div style="margin-top:16px;">
        <span class="mp-product-price" style="font-size:1.4rem;">₹${Number(p.price).toLocaleString("en-IN")}</span>
        <span class="mp-vendor-stock ${inStock ? "in-stock" : "no-stock"}" style="margin-left:12px;">
          ${inStock ? `${p.stock} in stock` : "Out of stock"}
        </span>
      </div>
      ${inStock ? `
      <div class="mp-vendor-qty-row" style="margin-top:16px;">
        <input type="number" min="1" max="${p.stock}" value="1" id="qty-${esc(p.product_id)}" class="mp-qty-input"/>
        <button class="mp-btn mp-btn-primary"
          onclick="addToCart('${esc(p.product_id)}','${esc(p.product_name)}','${esc(p.store_name || '')}',${p.price}, parseInt(document.getElementById('qty-${esc(p.product_id)}').value)||1)">
          <i data-lucide="shopping-cart"></i> Add to Cart
        </button>
      </div>` : `<p style="color:#f87171;margin-top:16px;">Currently unavailable</p>`}
    </div>
  </div>`;
}

// ── Cart ───────────────────────────────────
function addToCart(productId, productName, storeName, price, qty = 1) {
  const existing = cart.find(c => c.productId === productId);
  if (existing) existing.quantity += qty;
  else cart.push({ productId, productName, store: storeName, price, quantity: qty });
  saveCart();
  renderCart();
  closeProductModal();
  mpToast(`${productName} added to cart`, "success");
}

function removeFromCart(idx) {
  cart.splice(idx, 1);
  saveCart();
  renderCart();
}

function updateCartQty(idx, qty) {
  if (qty < 1) { removeFromCart(idx); return; }
  cart[idx].quantity = qty;
  saveCart();
  renderCart();
}

function renderCart() {
  const countEl = document.getElementById("mp-cart-count");
  const itemsEl = document.getElementById("mp-cart-items");
  const footerEl = document.getElementById("mp-cart-footer");
  const totalEl = document.getElementById("mp-cart-total-amount");
  const total = cart.reduce((s, c) => s + c.price * c.quantity, 0);
  const count = cart.reduce((s, c) => s + c.quantity, 0);

  countEl.textContent = count;
  countEl.classList.toggle("hidden", count === 0);

  if (!cart.length) {
    itemsEl.innerHTML = `<div class="mp-empty-state"><i data-lucide="shopping-cart"></i><p>Your cart is empty</p></div>`;
    footerEl.style.display = "none";
    lucide.createIcons(); return;
  }

  itemsEl.innerHTML = cart.map((c, i) => `
    <div class="mp-cart-item">
      <div class="mp-cart-item-info">
        <span class="mp-cart-item-name">${esc(c.productName)}</span>
        <span class="mp-cart-item-store">${esc(c.store)}</span>
        <span class="mp-cart-item-price">₹${Number(c.price).toLocaleString("en-IN")} × ${c.quantity}</span>
      </div>
      <div class="mp-cart-item-actions">
        <button class="mp-qty-btn" onclick="updateCartQty(${i}, ${c.quantity - 1})"><i data-lucide="minus"></i></button>
        <span>${c.quantity}</span>
        <button class="mp-qty-btn" onclick="updateCartQty(${i}, ${c.quantity + 1})"><i data-lucide="plus"></i></button>
        <button class="mp-qty-btn danger" onclick="removeFromCart(${i})"><i data-lucide="trash-2"></i></button>
      </div>
    </div>`).join("");

  totalEl.textContent = `₹${total.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
  footerEl.style.display = "block";
  lucide.createIcons();
}

function toggleCart() {
  document.getElementById("mp-cart-drawer").classList.toggle("hidden");
  document.getElementById("mp-cart-overlay").classList.toggle("hidden");
  closePaymentModal(); 
  lucide.createIcons();
}

// ── Checkout & Payment Flow ────────────────
function handleCheckout() {
  if (!cart.length) return;
  const total = cart.reduce((s, c) => s + c.price * c.quantity, 0);
  document.getElementById("mp-payment-total").textContent = `₹${total.toLocaleString("en-IN", {minimumFractionDigits: 2})}`;
  document.getElementById("mp-payment-modal").classList.remove("hidden");
  lucide.createIcons();
}

function closePaymentModal() {
  document.getElementById("mp-payment-modal").classList.add("hidden");
  // Reset to card method for next time
  setPaymentMethod('card');
}

let selectedPaymentMethod = 'card';

function setPaymentMethod(method) {
  selectedPaymentMethod = method;
  
  // Update tabs
  document.querySelectorAll('.method-tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`tab-${method}`).classList.add('active');
  
  // Update sections
  document.querySelectorAll('.method-section').forEach(s => s.classList.remove('active'));
  document.getElementById(`method-section-${method}`).classList.add('active');
  
  // Update button text
  const btn = document.getElementById("mp-confirm-payment-btn");
  if (method === 'cash') {
    btn.innerHTML = `<i data-lucide="truck"></i> Confirm Order (COD)`;
  } else {
    btn.innerHTML = `<i data-lucide="shield-check"></i> Confirm & Pay`;
  }
  lucide.createIcons();
}

async function confirmPayment() {
  const btn = document.getElementById("mp-confirm-payment-btn");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  
  if (selectedPaymentMethod === 'cash') {
    btn.innerHTML = `<div class="mp-spinner-sm"></div> Confirming Order…`;
  } else {
    btn.innerHTML = `<div class="mp-spinner-sm"></div> Processing Payment…`;
  }

  let succeeded = 0, failed = 0;
  for (const item of cart) {
    try {
      await api.placeOrder(item.productId, item.quantity);
      succeeded++;
    } catch { failed++; }
  }

  btn.disabled = false;
  btn.innerHTML = originalText;
  lucide.createIcons();

  if (succeeded > 0) {
    cart = [];
    saveCart();
    renderCart();
    closePaymentModal();
    
    if (!document.getElementById("mp-cart-drawer").classList.contains("hidden")) {
      toggleCart();
    }

    const title = selectedPaymentMethod === 'cash' ? "Order Confirmed!" : "Payment Successful!";
    const body = selectedPaymentMethod === 'cash' 
      ? `${succeeded} order${succeeded > 1 ? "s" : ""} placed. Please keep cash ready at the time of delivery.`
      : `${succeeded} order${succeeded > 1 ? "s" : ""} placed successfully. Your payment has been processed securely.`;

    document.getElementById("mp-order-modal-title").textContent = title;
    document.getElementById("mp-order-modal-body").textContent = body;
    document.getElementById("mp-order-modal").classList.remove("hidden");
    
    lucide.createIcons();
    loadProducts();
  } else {
    mpToast("Failed to process your request. Please try again.", "error");
  }
}

function closeOrderModal() {
  document.getElementById("mp-order-modal").classList.add("hidden");
}

// ── Orders ─────────────────────────────────
async function loadOrders() {
  const el = document.getElementById("mp-orders-list");
  el.innerHTML = `<div class="mp-loading-state"><div class="mp-spinner"></div><p>Loading orders…</p></div>`;
  try {
    const data = await api.getMyOrders(ordersPage, 20);
    const orders = data.orders || [];
    if (!orders.length) {
      el.innerHTML = `<div class="mp-empty-state"><i data-lucide="shopping-bag"></i><p>No orders yet.</p><button class="mp-btn mp-btn-primary" onclick="showPage('shop')">Browse Products</button></div>`;
      lucide.createIcons(); return;
    }
    el.innerHTML = orders.map(o => {
      const statusMap = { pending: "Pending", injected: "Confirmed", rejected: "Rejected" };
      const statusLabel = statusMap[o.order_status] || o.order_status || "—";
      const date = o.ordered_at
        ? new Intl.DateTimeFormat('en-IN', {
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit', hour12: true,
            timeZone: 'Asia/Kolkata'
          }).format(new Date(o.ordered_at))
        : "—";
      return `
      <div class="mp-order-card">
        <div class="mp-order-header">
          <span class="mp-order-id">${esc(o.order_id)}</span>
          <span class="mp-order-status ${esc(o.order_status || '')}"><b>${statusLabel}</b></span>
          <span class="mp-order-date">${date}</span>
        </div>
        <div class="mp-order-body">
          <div class="mp-order-product">
            <i data-lucide="package"></i>
            <div>
              <strong>${esc(o.product_name)}</strong>
              <span>from ${esc(o.store_name || "Store")}</span>
            </div>
          </div>
          <div class="mp-order-meta">
            <span>Qty: <strong>${o.quantity}</strong></span>
            <span>₹${Number(o.price_per_unit).toLocaleString("en-IN")} each</span>
          </div>
        </div>
        <div class="mp-order-footer">
          <span class="mp-order-total">Total: <strong>₹${Number(o.total_price).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong></span>
          <span class="mp-order-cat">${esc(o.category || "")}</span>
        </div>
      </div>`;
    }).join("");
    renderPagination(data.total, ordersPage, 20, "mp-orders-pagination", p => { ordersPage = p; loadOrders(); });
    lucide.createIcons();
  } catch {
    el.innerHTML = `<div class="mp-empty-state"><i data-lucide="alert-circle"></i><p>Failed to load orders.</p></div>`;
    lucide.createIcons();
  }
}

// ── Pagination ─────────────────────────────
function renderPagination(total, page, limit, containerId, onPage) {
  const pages = Math.ceil(total / limit);
  const el = document.getElementById(containerId);
  if (pages <= 1) { el.innerHTML = ""; return; }
  let html = `<button class="mp-page-btn" ${page <= 1 ? "disabled" : ""} onclick="(${onPage})(${page - 1})">‹</button>`;
  const s = Math.max(1, page - 2), e = Math.min(pages, page + 2);
  for (let i = s; i <= e; i++)
    html += `<button class="mp-page-btn ${i === page ? "active" : ""}" onclick="(${onPage})(${i})">${i}</button>`;
  html += `<button class="mp-page-btn" ${page >= pages ? "disabled" : ""} onclick="(${onPage})(${page + 1})">›</button>`;
  el.innerHTML = html;
}

// ── View Toggle ────────────────────────────
function setView(v) {
  document.getElementById("view-grid").classList.toggle("active", v === "grid");
  document.getElementById("view-list").classList.toggle("active", v === "list");
  document.getElementById("mp-product-grid").classList.toggle("mp-list-view", v === "list");
}

// ── Logout ─────────────────────────────────
function handleMpLogout() {
  api.logout();
  window.location.href = "index.html";
}

// ── Helpers ────────────────────────────────
function esc(s) {
  if (s == null) return "";
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── AI ASSISTANT (CHAT) ────────────────────

async function loadChatSessions() {
  try {
    const data = await api.getChatSessions();
    const list = document.getElementById("sessions-list");
    if (!data.sessions || !data.sessions.length) {
      list.innerHTML = '<div class="empty-state-mini">No conversations yet</div>';
      return;
    }
    list.innerHTML = data.sessions.map(s => `
      <div class="session-item ${currentSessionId === s.session_id ? 'active' : ''}" 
           onclick="loadSession('${s.session_id}')">
        <div class="session-info">
          <span class="session-date">${new Date(s.last_message).toLocaleDateString()}</span>
          <span class="session-id">${s.session_id.slice(0, 8)}...</span>
        </div>
        <button class="session-delete" onclick="event.stopPropagation(); handleDeleteSession('${s.session_id}')">
          <i data-lucide="trash-2"></i>
        </button>
      </div>`).join("");
    lucide.createIcons();
  } catch (err) {
    console.error("Failed to load sessions:", err);
  }
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
    mpToast("Failed to load history", "error");
  }
}

function startNewSession() {
  currentSessionId = null;
  const messagesEl = document.getElementById("chat-messages");
  messagesEl.innerHTML = `
    <div class="chat-welcome" id="chat-welcome">
      <div class="chat-welcome-icon"><i data-lucide="sparkles"></i></div>
      <h3>Smart Shopping Assistant</h3>
      <p>I can help you find products, compare prices, or track your recent orders.</p>
      <div class="chat-suggestions">
        <button class="suggestion-chip" onclick="sendSuggestion('Recommend some top electronics')">
          <i data-lucide="smartphone"></i> Top electronics?
        </button>
        <button class="suggestion-chip" onclick="sendSuggestion('What items are available under ₹1000?')">
          <i data-lucide="banknote"></i> Items under ₹1000?
        </button>
        <button class="suggestion-chip" onclick="sendSuggestion('Track my recent orders')">
          <i data-lucide="package"></i> Track my orders
        </button>
      </div>
    </div>`;
  lucide.createIcons();
  document.querySelectorAll(".session-item").forEach(s => s.classList.remove("active"));
  document.getElementById("chat-agent-info").textContent = "";
}

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

  const welcome = document.getElementById("chat-welcome");
  if (welcome) welcome.remove();

  const messagesEl = document.getElementById("chat-messages");
  messagesEl.insertAdjacentHTML("beforeend", renderChatBubble("user", message));
  input.value = "";
  input.style.height = "auto";

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
    document.getElementById(thinkingId)?.remove();

    messagesEl.insertAdjacentHTML("beforeend", renderChatBubble("assistant", data.response, {
      intent: data.intent,
      agents_used: data.agents_used
    }));

    const agentInfo = document.getElementById("chat-agent-info");
    const agentNames = (data.agents_used || []).map(a => a.replace("_", " ")).join(", ");
    agentInfo.textContent = agentNames ? `Agents: ${agentNames}` : "";

    messagesEl.scrollTop = messagesEl.scrollHeight;
    lucide.createIcons();
    loadChatSessions();
  } catch (err) {
    document.getElementById(thinkingId)?.remove();
    messagesEl.insertAdjacentHTML("beforeend", renderChatBubble("assistant", `⚠️ Error: ${err.error || "Something went wrong."}`));
    messagesEl.scrollTop = messagesEl.scrollHeight;
  } finally {
    chatBusy = false;
    sendBtn.disabled = false;
  }
}

function renderChatBubble(role, content, metadata = null) {
  const isUser = role === "user";
  const avatarIcon = isUser ? "user" : "bot";
  const formatted = formatChatContent(content);
  return `
    <div class="chat-bubble ${role}">
      <div class="bubble-avatar"><i data-lucide="${avatarIcon}"></i></div>
      <div class="bubble-content">
        <div class="bubble-text">${formatted}</div>
      </div>
    </div>`;
}

function formatChatContent(text) {
  if (!text) return "";
  let html = esc(text);
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\n/g, '<br>');
  html = html.replace(/(₹[\d,\.]+)/g, '<span class="currency-highlight">$1</span>');
  return html;
}

function autoResizeTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

async function handleDeleteSession(sessionId) {
  if (!confirm("Delete this conversation?")) return;
  try {
    await api.deleteChatSession(sessionId);
    if (currentSessionId === sessionId) startNewSession();
    loadChatSessions();
  } catch (err) {
    mpToast("Failed to delete session", "error");
  }
}
