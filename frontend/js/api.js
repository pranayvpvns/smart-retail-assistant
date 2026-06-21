/* ══════════════════════════════════════════
   API Client — Smart Retail Assistant
   ══════════════════════════════════════════ */


const API_BASE = "https://smart-retail-api.orangesky-9e3884f9.koreacentral.azurecontainerapps.io/api/v1";
// const API_BASE = "http://localhost:5000/api/v1";
class ApiClient {
  constructor() {
    this._token = localStorage.getItem("sra_token") || null;
  }

  get token() { return this._token; }
  set token(t) {
    this._token = t;
    t ? localStorage.setItem("sra_token", t) : localStorage.removeItem("sra_token");
  }

  get isAuthenticated() { return !!this._token; }

  _headers(json = true) {
    const h = {};
    if (json) h["Content-Type"] = "application/json";
    if (this._token) h["Authorization"] = "Bearer " + this._token;
    return h;
  }

  async _request(method, path, body, isFormData = false) {
    this._token = localStorage.getItem("sra_token") || null;
    const opts  = { method, headers: this._headers(!isFormData) };
    if (body) opts.body = isFormData ? body : JSON.stringify(body);
    const res  = await fetch(API_BASE + path, opts);
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
      this.logout();
      if (typeof showAuth === "function") showAuth();
      if (typeof toast    === "function") toast(data.error || "Session expired. Please log in again.", "error");
      if (typeof mpToast  === "function") mpToast(data.error || "Session expired.", "error");
      throw { status: 401, error: data.error || "Session expired" };
    }
    if (!res.ok) {
      throw { 
        status: res.status, 
        error: data.error || data.message || `Server error (${res.status})` 
      };
    }
    return data;
  }

  /* ════════════════════════════════════════
     AUTH
  ════════════════════════════════════════ */

  /** Register a new store owner */
  async register(email, password, store_name) {
    const data = await this._request("POST", "/auth/register", { email, password, store_name });
    this.token = data.access_token;
    localStorage.setItem("sra_user", JSON.stringify({
      email:      data.email,
      store_id:   data.store_id,
      store_name: data.store_name,
      role:       data.role || "owner",
      name:       data.name || data.store_name,
    }));
    return data;
  }

  /** Register a new marketplace buyer */
  async registerUser(email, password, name) {
    const data = await this._request("POST", "/auth/user/register", { email, password, name });
    this.token = data.access_token;
    localStorage.setItem("sra_user", JSON.stringify({
      email:      data.email,
      user_id:    data.user_id,
      name:       data.name,
      role:       data.role || "user",
      store_id:   "",
      store_name: "",
    }));
    return data;
  }

  /** Login for both owners and buyers — backend returns the role */
  async login(email, password) {
    const data = await this._request("POST", "/auth/login", { email, password });
    this.token = data.access_token;
    localStorage.setItem("sra_user", JSON.stringify({
      email:      data.email,
      store_id:   data.store_id   || "",
      store_name: data.store_name || "",
      user_id:    data.user_id    || "",
      name:       data.name       || data.store_name || "",
      role:       data.role       || "owner",
    }));
    return data;
  }

  /** Token introspection — validate current session */
  async whoami() {
    return this._request("GET", "/auth/me");
  }

  logout() {
    this.token = null;
    localStorage.removeItem("sra_user");
  }

  getUser() {
    try { return JSON.parse(localStorage.getItem("sra_user")); } catch { return null; }
  }

  /* ════════════════════════════════════════
     HEALTH
  ════════════════════════════════════════ */

  async health() {
    try {
      const res = await fetch("http://127.0.0.1:5000/health", { mode: "cors" });
      return await res.json();
    } catch {
      return { status: "unknown", database: "unknown" };
    }
  }

  /* ════════════════════════════════════════
     ANALYTICS DATA  (CSV Upload / Records)
  ════════════════════════════════════════ */

  /** Upload a sales CSV for analytics. Auto-registers it as a named dataset. */
  async uploadCSV(file) {
    const fd = new FormData();
    fd.append("file", file);
    return this._request("POST", "/data/upload", fd, true);
  }

  async getRecords(page = 1, limit = 50) {
    return this._request("GET", `/data/records?page=${page}&limit=${limit}`);
  }

  async deleteRecords() {
    return this._request("DELETE", "/data/records?confirm=true");
  }

  /* ════════════════════════════════════════
     DATASETS  (owner analytics CSV registry)
  ════════════════════════════════════════ */

  /** Owner: list all uploaded analytics datasets */
  async getDatasetRegistry() {
    return this._request("GET", "/datasets");
  }

  async getDatasets() {
    return this.getDatasetRegistry();
  }

  /** Owner: remove dataset registry entry (physical CSV kept on disk) */
  async deleteDataset(datasetId) {
    return this._request("DELETE", `/datasets/${encodeURIComponent(datasetId)}`);
  }

  /**
   * Owner: scan data/owners/<store_id>/ for unregistered CSVs and register them.
   * Call this when the inject modal shows no datasets.
   */
  async scanDatasets() {
    return this._request("POST", "/datasets/scan");
  }

  /** Owner: Register a local CSV by absolute path (e.g. from Desktop) */
  async linkDataset(filePath) {
    return this._request("POST", "/datasets/link", { file_path: filePath });
  }

  /* ════════════════════════════════════════
     FORECAST
  ════════════════════════════════════════ */

  async getForecast(productId, days = 14) {
    return this._request("GET", `/forecast/${encodeURIComponent(productId)}?days=${days}`);
  }

  /** Products available in trained ML models (for forecast dropdown) */
  async getForecastProducts() {
    return this._request("GET", "/forecast/products");
  }

  /** @deprecated alias — use getForecastProducts() */
  async getProducts() { return this.getForecastProducts(); }

  async retrain() {
    return this._request("POST", "/forecast/retrain");
  }

  /* ════════════════════════════════════════
     ANOMALY
  ════════════════════════════════════════ */

  async getAlerts(severity = "") {
    const q = severity ? `?severity=${severity}` : "";
    return this._request("GET", "/anomaly/alerts" + q);
  }

  async runDetection() {
    return this._request("POST", "/anomaly/run");
  }

  /* ════════════════════════════════════════
     CHAT / AI ASSISTANT
  ════════════════════════════════════════ */

  async sendMessage(message, sessionId = null) {
    const body = { message };
    if (sessionId) body.session_id = sessionId;
    return this._request("POST", "/chat", body);
  }

  async getChatHistory(sessionId) {
    return this._request("GET", `/chat/history/${encodeURIComponent(sessionId)}`);
  }

  async getChatSessions() {
    return this._request("GET", "/chat/sessions");
  }

  async embedRecords() {
    return this._request("POST", "/chat/embed");
  }

  async deleteChatSession(sessionId) {
    return this._request("DELETE", `/chat/sessions/${encodeURIComponent(sessionId)}`);
  }

  /* ════════════════════════════════════════
     DASHBOARD ANALYTICS
  ════════════════════════════════════════ */

  async getDashboardAnalytics() {
    return this._request("GET", "/dashboard/analytics");
  }

  async getAIRecommendations() {
    return this._request("POST", "/dashboard/ai-recommendations");
  }

  async getInsights() {
    return this._request("POST", "/dashboard/insights");
  }

  /* ════════════════════════════════════════
     PRODUCT CATALOG  (owner-managed)
  ════════════════════════════════════════ */

  /**
   * Owner: add a new product to the catalog.
   * Body: { product_name, category, price, stock, description, image_url, cost }
   */
  async addProduct(product) {
    return this._request("POST", "/products", product);
  }

  /**
   * Owner: update an existing product.
   * Allowed fields: product_name, category, price, stock, description, image_url, cost
   */
  async updateProduct(productId, updates) {
    return this._request("PUT", `/products/${encodeURIComponent(productId)}`, updates);
  }

  /** Owner: delete a product from catalog */
  async deleteProduct(productId) {
    return this._request("DELETE", `/products/${encodeURIComponent(productId)}`);
  }

  /** Owner: list their own products */
  async getMyProducts() {
    return this._request("GET", "/products/mine");
  }

  /**
   * Owner: bulk-import products from a CSV file.
   * @param {File} file  - CSV file
   * @param {string} mode - "upsert" (default) | "insert_new"
   */
  async importProductsCSV(file, mode = "upsert") {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mode", mode);
    return this._request("POST", "/products/import-csv", fd, true);
  }

  /** Owner: trigger browser download of starter CSV template */
  downloadProductTemplate() {
    const token = localStorage.getItem("sra_token") || "";
    // Create invisible link and click it to trigger download
    const a = document.createElement("a");
    a.href = `${API_BASE}/products/template`;
    a.setAttribute("download", "products_template.csv");
    // For auth header we fetch manually and create an object URL
    fetch(`${API_BASE}/products/template`, {
      headers: { "Authorization": "Bearer " + token }
    })
    .then(r => r.blob())
    .then(blob => {
      const url = URL.createObjectURL(blob);
      a.href = url;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  /* ════════════════════════════════════════
     MARKETPLACE BROWSING  (buyers + owners)
  ════════════════════════════════════════ */

  /**
   * Browse all products across all owners.
   * @param {string} search    — partial name search
   * @param {string} category  — exact category filter
   * @param {number} page
   * @param {number} limit
   */
  async getMarketplaceProducts(search = "", category = "", page = 1, limit = 20) {
    const params = new URLSearchParams({ page, limit });
    if (search)   params.set("search",   search);
    if (category) params.set("category", category);
    return this._request("GET", `/products?${params}`);
  }

  /** Single product detail page */
  async getProductDetail(productId) {
    return this._request("GET", `/products/${encodeURIComponent(productId)}`);
  }

  /** All distinct product categories */
  async getProductCategories() {
    return this._request("GET", "/products/categories");
  }

  /* ════════════════════════════════════════
     ORDERS  (buyers)
  ════════════════════════════════════════ */

  /**
   * Buyer: place an order.
   * Stock reduced immediately. Status stays "pending" until owner injects.
   */
  async placeOrder(productId, quantity) {
    return this._request("POST", "/orders", { product_id: productId, quantity });
  }

  /** Buyer: personal order history */
  async getMyOrders(page = 1, limit = 20) {
    return this._request("GET", `/orders?page=${page}&limit=${limit}`);
  }

  /* ════════════════════════════════════════
     ORDERS  (owners)
  ════════════════════════════════════════ */

  /**
   * Owner: pending orders — the notification feed.
   * Returns all orders with status="pending" for this owner's store.
   */
  async getPendingOrders() {
    return this._request("GET", "/orders/pending");
  }

  /** Owner: full paginated order history for their store */
  async getAllStoreOrders(page = 1, limit = 50) {
    return this._request("GET", `/orders/all?page=${page}&limit=${limit}`);
  }

  /**
   * Owner: inject a pending order into a selected analytics dataset.
   * Appends a row to the chosen CSV + upserts MongoDB sales_records.
   * @param {string} orderId    — the ORD-... id
   * @param {string} datasetId  — the DS-... id from getDatasets()
   */
  async injectOrder(orderId, datasetId) {
    return this._request(
      "POST",
      `/orders/${encodeURIComponent(orderId)}/inject`,
      { dataset_id: datasetId }
    );
  }

  async injectOrderExternal(orderId) {
    return this._request("POST", `/orders/${encodeURIComponent(orderId)}/inject-external`);
  }

  /**
   * Owner: reject a pending order.
   * Restores the product stock automatically.
   */
  async rejectOrder(orderId) {
    return this._request("POST", `/orders/${encodeURIComponent(orderId)}/reject`);
  }
}

const api = new ApiClient();
