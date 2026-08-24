const BILL_TRACKER_VERSION = "0.4.4";

class BillTrackerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._data = null;
    this._loading = false;
    this._editing = null;
    this._formOpen = false;
    this._error = null;
    this._chartMode = "cashflow";
    this._allBillsOpen = false;
    this._allBillsCategory = "all";
    this._unsubscribe = null;
  }

  static getStubConfig() {
    return {
      title: "Bollette di casa",
      columns: "full",
      recent: 10,
      history_months: 12,
      forecast_months: 12,
    };
  }

  static getConfigElement() {
    return document.createElement("bill-tracker-card-editor");
  }

  setConfig(config) {
    const rawColumns = config.columns ?? "full";
    const columns = rawColumns === "full"
      ? "full"
      : Math.max(1, Math.min(12, Number(rawColumns || 12)));
    this._config = {
      title: config.title || "Bollette di casa",
      columns,
      recent: Math.max(1, Math.min(50, Number(config.recent ?? 10))),
      history_months: Math.max(3, Math.min(36, Number(config.history_months ?? 12))),
      forecast_months: Math.max(1, Math.min(24, Number(config.forecast_months ?? 12))),
    };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._subscribeEvents();
      if (!this._data) this._load();
    }
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    const configured = this._config.columns ?? "full";
    return {
      columns: configured === "full" ? "full" : Math.max(1, Math.min(12, Number(configured || 12))),
      min_columns: 6,
    };
  }

  async _subscribeEvents() {
    if (!this._hass || this._unsubscribe) return;
    try {
      this._unsubscribe = await this._hass.connection.subscribeEvents(
        () => this._load(),
        "bill_tracker_updated"
      );
    } catch (_err) {
      // Local writes still trigger an explicit reload.
    }
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      this._data = await this._hass.callWS({
        type: "bill_tracker/list",
        forecast_months: this._config.forecast_months || 12,
      });
      this._error = null;
    } catch (err) {
      this._error = String(err?.message || err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _monthNames() {
    return [
      "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
      "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
    ];
  }

  _monthShort() {
    return ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];
  }

  _intervalLabel(months) {
    return ({
      1: "Mensile",
      2: "Bimestrale",
      3: "Trimestrale",
      4: "Quadrimestrale",
      6: "Semestrale",
      12: "Annuale",
    })[Number(months)] || `Ogni ${months} mesi`;
  }

  _defaultDate() {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  }

  _money(value) {
    return new Intl.NumberFormat("it-IT", {
      style: "currency",
      currency: "EUR",
    }).format(Number(value || 0));
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _safeColor(value) {
    const text = String(value || "").trim();
    return /^#[0-9a-fA-F]{6}$/.test(text) ? text : "#A0A7B4";
  }

  _monthValue(year, month) {
    return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}`;
  }

  _parseMonth(value) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(value || ""));
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    if (!Number.isInteger(year) || month < 1 || month > 12) return null;
    return { year, month };
  }

  _addMonths(year, month, delta) {
    const absolute = year * 12 + (month - 1) + delta;
    return { year: Math.floor(absolute / 12), month: ((absolute % 12) + 12) % 12 + 1 };
  }

  _activeCategories() {
    return (this._data?.active_categories || []).slice().sort((a, b) =>
      String(a.name).localeCompare(String(b.name), "it")
    );
  }

  _activePayers() {
    return (this._data?.active_payers || []).slice().sort((a, b) =>
      String(a.name).localeCompare(String(b.name), "it")
    );
  }

  _categoryById(id) {
    return (this._data?.categories || []).find((x) => x.id === id) || null;
  }

  _payerById(id) {
    return (this._data?.payers || []).find((x) => x.id === id) || null;
  }

  _categoryByName(name) {
    return (this._data?.categories || []).find((x) => x.name === name) || null;
  }

  _splitMap(split) {
    const result = {};
    for (const part of split || []) result[part.payer_id] = Number(part.percentage || 0);
    return result;
  }

  _chart() {
    const normalized = this._chartMode === "normalized";
    const actualSource = normalized ? this._data?.normalized_monthly : this._data?.monthly;
    const forecastSource = normalized ? this._data?.normalized_forecast : this._data?.forecast;
    const actual = (actualSource || []).slice(-this._config.history_months);
    const forecast = (forecastSource || []).slice(0, this._config.forecast_months);

    if (!actual.length) {
      return '<div class="empty-chart">Inserisci almeno una bolletta per visualizzare andamento e previsione.</div>';
    }

    const rows = [
      ...actual.map((x) => ({ ...x, kind: "actual" })),
      ...forecast.map((x) => ({ ...x, kind: "forecast" })),
    ];
    const maxValue = Math.max(1, ...rows.map((x) => Number(x.total || 0))) * 1.15;
    const width = Math.max(860, rows.length * 52 + 80);
    const height = 300;
    const left = 60;
    const right = 18;
    const top = 18;
    const bottom = 48;
    const plotW = width - left - right;
    const plotH = height - top - bottom;
    const step = plotW / Math.max(1, rows.length);
    const barW = Math.max(10, Math.min(34, step * 0.64));
    const y = (v) => top + plotH - (Number(v || 0) / maxValue) * plotH;
    const x = (i) => left + step * i + step / 2;

    const grid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
      const gy = top + plotH * (1 - ratio);
      const val = maxValue * ratio;
      return `<line x1="${left}" y1="${gy}" x2="${width - right}" y2="${gy}" class="grid" />
        <text x="${left - 8}" y="${gy + 4}" text-anchor="end" class="axis-value">${Math.round(val)}€</text>`;
    }).join("");

    const bars = actual.map((row, i) => {
      const bx = x(i) - barW / 2;
      const total = Math.max(0, Number(row.total || 0));
      let cursor = top + plotH;
      const parts = [];
      const entries = Object.entries(row.categories || {}).filter(([, value]) => Number(value) > 0);
      for (const [name, rawValue] of entries) {
        const value = Number(rawValue || 0);
        const h = Math.max(0, value / maxValue * plotH);
        cursor -= h;
        const category = this._categoryByName(name);
        const color = this._safeColor(category?.color);
        const percentage = total > 0 ? value / total * 100 : 0;
        parts.push(`<rect x="${bx}" y="${cursor}" width="${barW}" height="${h}" fill="${color}" class="stack-segment">
          <title>${this._monthNames()[row.month - 1]} ${row.year} · ${this._escape(name)}: ${this._money(value)} (${percentage.toFixed(1)}%)</title>
        </rect>`);
      }
      return parts.join("");
    }).join("");

    const forecastOffset = actual.length;
    const forecastPoints = [];
    if (forecast.length) {
      const lastActual = actual[actual.length - 1];
      forecastPoints.push([x(actual.length - 1), y(lastActual.total)]);
      forecast.forEach((row, idx) => forecastPoints.push([x(forecastOffset + idx), y(row.total)]));
    }
    const forecastPath = forecastPoints.length
      ? `M ${forecastPoints.map((p) => `${p[0]} ${p[1]}`).join(" L ")}`
      : "";
    const forecastDots = forecast.map((row, idx) => {
      const px = x(forecastOffset + idx);
      const py = y(row.total);
      const breakdown = Object.entries(row.categories || {})
        .map(([name, amount]) => `${name}: ${this._money(amount)}`)
        .join(" · ");
      return `<circle cx="${px}" cy="${py}" r="4" class="forecast-dot">
        <title>${this._monthNames()[row.month - 1]} ${row.year}: stima ${this._money(row.total)}${breakdown ? ` · ${this._escape(breakdown)}` : ""}</title>
      </circle>`;
    }).join("");

    const labelEvery = rows.length > 22 ? 3 : rows.length > 14 ? 2 : 1;
    const labels = rows.map((row, i) => {
      if (i % labelEvery !== 0 && i !== rows.length - 1) return "";
      return `<text x="${x(i)}" y="${height - 18}" text-anchor="middle" class="axis-label">${this._monthShort()[row.month - 1]} '${String(row.year).slice(-2)}</text>`;
    }).join("");

    const dividerX = forecast.length ? left + step * forecastOffset : null;
    const divider = dividerX
      ? `<line x1="${dividerX}" y1="${top}" x2="${dividerX}" y2="${top + plotH}" class="forecast-divider" />`
      : "";

    return `<div class="chart-scroll">
      <svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Grafico stacked delle bollette reali e previste">
        ${grid}
        ${bars}
        ${divider}
        ${forecastPath ? `<path d="${forecastPath}" class="forecast-line" />` : ""}
        ${forecastDots}
        ${labels}
      </svg>
    </div>`;
  }

  _chartLegend() {
    const normalized = this._chartMode === "normalized";
    const source = normalized ? this._data?.normalized_monthly : this._data?.monthly;
    const rows = (source || []).slice(-this._config.history_months);
    const used = new Set();
    for (const row of rows) {
      for (const name of Object.keys(row.categories || {})) used.add(name);
    }
    const categoryLegend = [...used].map((name) => {
      const category = this._categoryByName(name);
      return `<span><i class="legend-square" style="background:${this._safeColor(category?.color)}"></i>${this._escape(name)}</span>`;
    }).join("");
    return `${categoryLegend}<span><i class="legend-line"></i>Stima totale</span>`;
  }

  _periodText(item) {
    const start = this._monthValue(item.period_start_year, item.period_start_month);
    const end = this._monthValue(item.period_end_year, item.period_end_month);
    if (start === end) return this._monthLabel(item.period_end_year, item.period_end_month);
    return `${this._monthLabel(item.period_start_year, item.period_start_month)} → ${this._monthLabel(item.period_end_year, item.period_end_month)}`;
  }

  _monthLabel(year, month) {
    return `${this._monthShort()[Number(month) - 1]} ${year}`;
  }

  _splitText(item) {
    const parts = (item.split || []).filter((x) => Number(x.percentage) > 0);
    if (!parts.length) return "Non divisa";
    return parts.map((x) => `${x.name} ${Number(x.percentage).toFixed(Number(x.percentage) % 1 ? 1 : 0)}%`).join(" · ");
  }

  _expenseFormPayers(editing) {
    if (!editing) return this._activePayers();
    const ids = new Set([editing.payer_id, ...(editing.split || []).map((x) => x.payer_id)].filter(Boolean));
    return (this._data?.payers || []).filter((p) => p.enabled || ids.has(p.id));
  }

  _renderDebts() {
    const payers = this._data?.payers || [];
    if (payers.length < 2) {
      return `<div class="settle-empty">Configura almeno due paganti nelle impostazioni per usare la divisione delle spese.</div>`;
    }
    const debts = this._data?.debts || [];
    if (!debts.length) {
      return `<div class="settle-empty ok">✓ Nessun saldo da regolare</div>`;
    }
    return `<div class="debt-list">${debts.map((debt) => `
      <div class="debt-row">
        <div><strong>${this._escape(debt.from_name)} → ${this._escape(debt.to_name)}</strong><span>Saldo netto da rimborsare</span></div>
        <b>${this._money(debt.amount)}</b>
        <div class="debt-actions">
          ${debt.paypal_url ? `<a class="paypal" href="${this._escape(debt.paypal_url)}" target="_blank" rel="noopener noreferrer">Paga con PayPal</a>` : `<button class="secondary small" type="button" disabled title="Aggiungi il PayPal.Me del creditore nelle impostazioni">PayPal.Me non configurato</button>`}
          <button class="primary small settle" type="button" data-from="${this._escape(debt.from_payer_id)}" data-to="${this._escape(debt.to_payer_id)}" data-amount="${Number(debt.amount)}">Segna saldato</button>
        </div>
      </div>`).join("")}</div>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    if (!this._data) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:20px">${this._loading ? "Caricamento Billy…" : this._escape(this._error || "Bill Tracker non ancora disponibile")}</div></ha-card>`;
      return;
    }

    const summary = this._data.summary || {};
    const activeCategories = this._activeCategories();
    const activePayers = this._activePayers();
    const editing = this._editing;
    const selectedCategoryId = editing?.category_id || activeCategories[0]?.id || "";
    const selectedCategory = this._categoryById(selectedCategoryId);
    const now = this._defaultDate();
    const selectedPaid = editing
      ? this._monthValue(editing.paid_year, editing.paid_month)
      : this._monthValue(now.year, now.month);
    const paidParsed = this._parseMonth(selectedPaid) || now;
    const interval = Math.max(1, Number(selectedCategory?.interval_months || 1));
    const startAuto = this._addMonths(paidParsed.year, paidParsed.month, -(interval - 1));
    const defaultStart = editing
      ? this._monthValue(editing.period_start_year, editing.period_start_month)
      : this._monthValue(startAuto.year, startAuto.month);
    const defaultEnd = editing
      ? this._monthValue(editing.period_end_year, editing.period_end_month)
      : selectedPaid;
    const formPayers = this._expenseFormPayers(editing);
    const defaultPayerId = editing?.payer_id || selectedCategory?.default_payer_id || activePayers[0]?.id || "";
    const splitMap = this._splitMap(editing?.split?.length ? editing.split : this._data.default_split || []);
    const allExpenses = this._data.expenses || [];
    const expenses = allExpenses.slice(0, this._config.recent);
    const allBillCategories = (this._data.categories || []).slice().sort((a, b) => String(a.name).localeCompare(String(b.name), "it"));
    const filteredAllExpenses = this._allBillsCategory === "all"
      ? allExpenses
      : allExpenses.filter((x) => x.category_id === this._allBillsCategory);
    const settlements = (this._data.settlements || []).slice(0, 5);
    const upcoming = (this._data.upcoming || []).slice(0, 8);

    const expenseFormHtml = `<form id="expense-form">
          <label>Tipo
            <select id="category" required>
              ${activeCategories.map((c) => `<option value="${this._escape(c.id)}" ${c.id === selectedCategoryId ? "selected" : ""}>${this._escape(c.name)} · ${this._escape(this._intervalLabel(c.interval_months))}</option>`).join("")}
              ${editing && selectedCategory && !selectedCategory.enabled ? `<option value="${this._escape(selectedCategory.id)}" selected>${this._escape(selectedCategory.name)} · disattivata</option>` : ""}
            </select>
          </label>
          <label>Mese pagamento<input id="paid-month" type="month" required value="${this._escape(selectedPaid)}"></label>
          <label>Importo (€)<input id="amount" type="number" min="0" step="0.01" inputmode="decimal" required value="${editing ? this._escape(editing.amount) : ""}" placeholder="0,00"></label>
          <label class="paid-check"><input id="paid-status" type="checkbox" ${editing?.paid ? "checked" : ""}><div><strong>Bolletta pagata</strong><span>Attiva il check solo quando la bolletta è stata effettivamente saldata.</span></div></label>
          ${formPayers.length ? `<label>Pagata da
            <select id="payer" required>
              ${formPayers.map((p) => `<option value="${this._escape(p.id)}" ${p.id === defaultPayerId ? "selected" : ""}>${this._escape(p.name)}${p.enabled ? "" : " · disattivato"}</option>`).join("")}
            </select>
          </label>` : ""}
          <label>Fine competenza<input id="period-end" type="month" required value="${this._escape(defaultEnd)}"></label>
          <label>Inizio competenza<input id="period-start" type="month" required value="${this._escape(defaultStart)}"></label>
          <label class="wide">Nota (opzionale)<input id="note" type="text" maxlength="120" value="${editing ? this._escape(editing.note || "") : ""}" placeholder="Es. conguaglio, rata, periodo fatturato..."></label>
          ${formPayers.length ? `<div class="split-box">
            <div class="split-head"><strong>Divisione della spesa</strong><span id="split-total" class="split-total"></span></div>
            <div class="split-grid">
              ${formPayers.map((p) => `<label>${this._escape(p.name)} (%)<input class="split-input" data-payer="${this._escape(p.id)}" type="number" min="0" max="100" step="0.01" value="${Number(splitMap[p.id] || 0)}"></label>`).join("")}
            </div>
          </div>` : '<div class="form-help">Nessun pagante configurato: la bolletta verrà salvata senza divisione. Puoi aggiungere i paganti dalle impostazioni.</div>'}
          <div class="form-help">La periodicità precompila il periodo di competenza. “Pagata da” indica chi anticipa la spesa; il check “Bolletta pagata” decide se il pagamento è realmente avvenuto e solo le bollette pagate entrano nei saldi tra persone.</div>
          <div class="buttons"><button class="secondary" id="cancel" type="button">Annulla</button><button class="primary" type="submit">${editing ? "Salva modifiche" : "Aggiungi"}</button></div>
        </form>`;

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding:18px; overflow:hidden; }
        .head { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:14px; flex-wrap:wrap; }
        .title { font-size:20px; font-weight:600; }
        .head-actions,.debt-actions { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
        button,a.paypal { min-height:42px; border:0; border-radius:10px; padding:0 14px; cursor:pointer; font-weight:600; box-sizing:border-box; display:inline-flex; align-items:center; justify-content:center; text-decoration:none; }
        button:disabled { opacity:.55; cursor:not-allowed; }
        .primary { background:var(--primary-color); color:var(--text-primary-color,white); }
        .secondary { background:transparent; border:1px solid var(--divider-color); color:var(--primary-text-color); }
        .paypal { background:#0070ba; color:white; }
        .small { min-height:36px; font-size:12px; padding:0 11px; }
        .stats { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:8px; margin-bottom:14px; }
        .stat { border:1px solid var(--divider-color); border-radius:12px; padding:11px; min-width:0; }
        .stat span { display:block; color:var(--secondary-text-color); font-size:11px; line-height:1.25; }
        .stat strong { display:block; font-size:18px; margin-top:4px; overflow-wrap:anywhere; }
        form { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; padding:14px; margin-bottom:14px; border:1px solid var(--divider-color); border-radius:12px; }
        .edit-modal { position:fixed; inset:0; z-index:1000; display:flex; align-items:center; justify-content:center; padding:24px; background:rgba(0,0,0,.52); box-sizing:border-box; }
        .edit-modal-shell { width:min(820px,100%); max-height:calc(100vh - 48px); overflow:auto; background:var(--card-background-color); color:var(--primary-text-color); border-radius:16px; box-shadow:0 16px 50px rgba(0,0,0,.35); }
        .edit-modal-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 16px; border-bottom:1px solid var(--divider-color); position:sticky; top:0; z-index:2; background:var(--card-background-color); }
        .edit-modal-head strong { font-size:16px; }
        .edit-modal-head span { display:block; margin-top:2px; color:var(--secondary-text-color); font-size:12px; }
        .edit-modal-close { min-width:42px; width:42px; padding:0; font-size:22px; }
        .edit-modal form { margin:0; border:0; border-radius:0; padding:16px; }
        label { display:flex; flex-direction:column; gap:5px; font-size:12px; color:var(--secondary-text-color); min-width:0; }
        .wide,.split-box,.form-help,.buttons { grid-column:1 / -1; }
        select,input { box-sizing:border-box; width:100%; min-height:44px; border-radius:10px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); padding:8px 10px; font-size:16px; }
        .paid-check { grid-column:1 / -1; display:flex; flex-direction:row; align-items:center; gap:10px; min-height:44px; color:var(--primary-text-color); font-size:13px; }
        .paid-check input { width:20px; min-height:20px; height:20px; margin:0; padding:0; accent-color:var(--success-color,#43a047); }
        .paid-check span { color:var(--secondary-text-color); font-size:12px; }
        .paid-status { width:28px; height:28px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-size:17px; font-weight:700; }
        .paid-status.yes { color:var(--success-color,#43a047); background:color-mix(in srgb,var(--success-color,#43a047) 14%,transparent); }
        .paid-status.no { visibility:hidden; }
        .split-box { border-top:1px solid var(--divider-color); padding-top:10px; }
        .split-head { display:flex; justify-content:space-between; gap:8px; align-items:center; margin-bottom:8px; }
        .split-head strong { color:var(--primary-text-color); font-size:13px; }
        .split-total { font-size:12px; color:var(--secondary-text-color); }
        .split-total.bad { color:var(--error-color); font-weight:600; }
        .split-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; }
        .buttons { display:flex; justify-content:flex-end; gap:8px; flex-wrap:wrap; }
        .form-help { color:var(--secondary-text-color); font-size:12px; }
        .msg { margin:10px 0; font-size:13px; }
        .error { color:var(--error-color); }
        .warning { padding:10px 12px; border-radius:10px; border:1px solid var(--warning-color,#f0ad4e); margin-bottom:12px; }
        .section { margin-top:16px; }
        .section-title { font-size:15px; font-weight:600; margin-bottom:8px; }
        .section-head { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap; }
        .section-head .section-title { margin-bottom:0; }
        .all-bills-panel { margin-top:14px; padding:14px; border:1px solid var(--divider-color); border-radius:12px; background:var(--card-background-color); }
        .all-bills-toolbar { display:flex; gap:10px; align-items:end; justify-content:space-between; margin-bottom:8px; flex-wrap:wrap; }
        .all-bills-toolbar label { min-width:220px; }
        .all-bills-count { color:var(--secondary-text-color); font-size:12px; }
        .all-bills-list { max-height:620px; overflow:auto; padding-right:3px; }
        .all-row { display:grid; grid-template-columns:42px 125px minmax(180px,1fr) 120px auto; gap:10px; align-items:center; padding:10px 0; border-bottom:1px solid var(--divider-color); }
        .all-row:last-child { border-bottom:0; }
        .paid-toggle { display:flex; align-items:center; justify-content:center; cursor:pointer; }
        .paid-toggle input { position:absolute; opacity:0; pointer-events:none; }
        .paid-toggle-mark { width:28px; height:28px; border-radius:8px; border:2px solid var(--divider-color); display:inline-flex; align-items:center; justify-content:center; box-sizing:border-box; font-weight:800; font-size:18px; color:transparent; transition:background .15s,border-color .15s,color .15s; }
        .paid-toggle input:checked + .paid-toggle-mark { background:var(--success-color,#43a047); border-color:var(--success-color,#43a047); color:white; }
        .paid-toggle input:focus-visible + .paid-toggle-mark { outline:2px solid var(--primary-color); outline-offset:2px; }
        .paid-toggle input:disabled + .paid-toggle-mark { opacity:.5; cursor:wait; }
        .settle-box { border:1px solid var(--divider-color); border-radius:12px; padding:12px; }
        .settle-empty { color:var(--secondary-text-color); padding:8px 2px; }
        .settle-empty.ok { color:var(--success-color,#43a047); font-weight:600; }
        .debt-list { display:grid; gap:8px; }
        .debt-row { display:grid; grid-template-columns:minmax(160px,1fr) auto auto; gap:12px; align-items:center; padding:9px 0; border-bottom:1px solid var(--divider-color); }
        .debt-row:last-child { border-bottom:0; }
        .debt-row span { display:block; color:var(--secondary-text-color); font-size:11px; margin-top:3px; }
        .chart-panel { padding:14px 0 6px; border-top:1px solid var(--divider-color); border-bottom:1px solid var(--divider-color); margin-top:16px; }
        .chart-head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:6px; flex-wrap:wrap; }
        .chart-copy strong { display:block; font-size:15px; }
        .chart-copy span { color:var(--secondary-text-color); font-size:12px; }
        .mode { display:flex; border:1px solid var(--divider-color); border-radius:10px; overflow:hidden; }
        .mode button { min-height:34px; border-radius:0; background:transparent; color:var(--primary-text-color); font-size:12px; }
        .mode button.active { background:var(--primary-color); color:var(--text-primary-color,white); }
        .legend { display:flex; gap:12px; align-items:center; margin:8px 0 0; color:var(--secondary-text-color); font-size:11px; flex-wrap:wrap; }
        .legend span { display:flex; gap:5px; align-items:center; }
        .legend-square { width:10px; height:10px; border-radius:2px; display:inline-block; }
        .legend-line { width:18px; border-top:2px dashed var(--warning-color,#f0ad4e); display:inline-block; }
        .chart-scroll { width:100%; overflow-x:auto; }
        .chart { width:100%; min-width:760px; height:auto; overflow:visible; }
        .grid { stroke:var(--divider-color); stroke-width:1; opacity:.7; }
        .axis-value,.axis-label { fill:var(--secondary-text-color); font-size:10px; }
        .stack-segment { opacity:.86; stroke:var(--card-background-color); stroke-width:.6; }
        .forecast-line { fill:none; stroke:var(--warning-color,#f0ad4e); stroke-width:3; stroke-dasharray:7 6; stroke-linecap:round; stroke-linejoin:round; }
        .forecast-dot { fill:var(--card-background-color); stroke:var(--warning-color,#f0ad4e); stroke-width:2; }
        .forecast-divider { stroke:var(--secondary-text-color); stroke-width:1; stroke-dasharray:3 5; opacity:.5; }
        .empty-chart { color:var(--secondary-text-color); padding:24px 4px; text-align:center; }
        .upcoming-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; }
        .upcoming-item { border:1px solid var(--divider-color); border-radius:10px; padding:10px; display:grid; gap:4px; }
        .upcoming-item span { color:var(--secondary-text-color); font-size:12px; }
        .upcoming-item strong { display:flex; justify-content:space-between; gap:8px; }
        .list { margin-top:4px; }
        .row { display:grid; grid-template-columns:125px minmax(180px,1fr) 120px auto; gap:10px; align-items:center; padding:10px 0; border-bottom:1px solid var(--divider-color); }
        .date,.note,.competence,.payer-line { color:var(--secondary-text-color); font-size:12px; }
        .amount { text-align:right; font-weight:600; }
        .actions { display:flex; gap:6px; }
        .icon { min-width:34px; min-height:34px; padding:0 8px; background:transparent; border:1px solid var(--divider-color); color:var(--primary-text-color); }
        .settlement { display:grid; grid-template-columns:1fr auto auto; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid var(--divider-color); }
        .settlement span { color:var(--secondary-text-color); font-size:12px; }
        @media (max-width:1000px) { .stats { grid-template-columns:repeat(3,minmax(0,1fr)); } .debt-row { grid-template-columns:1fr auto; } .debt-actions { grid-column:1 / -1; } }
        @media (max-width:760px) { .stats { grid-template-columns:repeat(2,minmax(0,1fr)); } form { grid-template-columns:1fr 1fr; } .wide,.split-box,.form-help,.buttons { grid-column:1 / -1; } .all-row { grid-template-columns:42px 110px 1fr auto; } .all-row .amount { grid-column:3; text-align:left; } .all-row .actions { grid-column:4; grid-row:1 / span 2; } }
        @media (max-width:560px) { ha-card { padding:13px; } .edit-modal { padding:8px; align-items:flex-end; } .edit-modal-shell { max-height:calc(100vh - 16px); border-radius:16px 16px 8px 8px; } .stats { grid-template-columns:1fr; } form { grid-template-columns:1fr; } .wide,.split-box,.form-help,.buttons { grid-column:1; } .row { grid-template-columns:1fr auto; } .row .amount { grid-column:1; text-align:left; } .row .actions { grid-column:2; grid-row:1 / span 2; } .debt-row { grid-template-columns:1fr; } .debt-actions { grid-column:1; } .settlement { grid-template-columns:1fr auto; } .all-bills-toolbar label { min-width:100%; } .all-row { grid-template-columns:36px 1fr auto; } .all-row .all-date { grid-column:2; } .all-row .all-main { grid-column:2; } .all-row .amount { grid-column:2; text-align:left; } .all-row .actions { grid-column:3; grid-row:1 / span 3; } }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${this._escape(this._config.title || "Bollette di casa")}</div>
          <div class="head-actions">
            <button class="secondary" id="settings" type="button">⚙ Impostazioni</button>
            <button class="primary" id="open-form" type="button" ${activeCategories.length ? "" : "disabled"}>+ Aggiungi bolletta</button>
          </div>
        </div>
        <div class="stats">
          <div class="stat"><span>Pagato questo mese</span><strong>${this._money(summary.current_month)}</strong></div>
          <div class="stat"><span>Media pagamenti 6 mesi</span><strong>${this._money(summary.average_6_months)}</strong></div>
          <div class="stat"><span>Stima prossimo mese</span><strong>${this._money(summary.next_month_estimate)}</strong></div>
          <div class="stat"><span>Costo mensile normalizzato</span><strong>${this._money(summary.normalized_current_month)}</strong></div>
          <div class="stat"><span>Bollette da pagare</span><strong>${this._money(summary.unpaid_total ?? summary.outstanding_total)}</strong></div>
        </div>
        ${!activeCategories.length ? '<div class="warning">Nessun tipo di bolletta attivo. Apri <strong>Impostazioni</strong> e abilita o aggiungi almeno una voce.</div>' : ""}
        ${editing ? `<div class="edit-modal" id="edit-modal" role="presentation">
          <div class="edit-modal-shell" role="dialog" aria-modal="true" aria-labelledby="edit-modal-title">
            <div class="edit-modal-head">
              <div><strong id="edit-modal-title">Modifica bolletta</strong><span>${this._escape(editing.category)} · ${this._monthLabel(editing.paid_year, editing.paid_month)}</span></div>
              <button class="secondary edit-modal-close" id="modal-close" type="button" aria-label="Chiudi modifica">×</button>
            </div>
            ${expenseFormHtml}
          </div>
        </div>` : (this._formOpen ? expenseFormHtml : "")}
        ${this._error ? `<div class="msg error">${this._escape(this._error)}</div>` : ""}

        <div class="section"><div class="section-title">Rimborsi tra paganti</div><div class="settle-box">${this._renderDebts()}</div></div>

        <div class="chart-panel">
          <div class="chart-head">
            <div class="chart-copy"><strong>Andamento e previsione</strong><span>${this._chartMode === "cashflow" ? "Colonne colorate per tipo di spesa + prossime scadenze stimate" : "Costo distribuito sui mesi di competenza"}</span></div>
            <div class="mode"><button type="button" data-mode="cashflow" class="${this._chartMode === "cashflow" ? "active" : ""}">Pagamenti</button><button type="button" data-mode="normalized" class="${this._chartMode === "normalized" ? "active" : ""}">Costo mensile</button></div>
          </div>
          <div class="legend">${this._chartLegend()}</div>
          ${this._chart()}
        </div>

        <div class="section"><div class="section-title">Prossime bollette stimate</div>
          ${upcoming.length ? `<div class="upcoming-grid">${upcoming.map((x) => `<div class="upcoming-item"><span>${this._monthNames()[Number(x.month) - 1]} ${x.year}</span><strong><b>${this._escape(x.category)}</b><b>${this._money(x.amount)}</b></strong></div>`).join("")}</div>` : '<div class="msg">Servono bollette storiche per calcolare le prossime scadenze.</div>'}
        </div>

        ${settlements.length ? `<div class="section"><div class="section-title">Rimborsi recenti</div>${settlements.map((x) => `<div class="settlement"><div><strong>${this._escape(x.from_name)} → ${this._escape(x.to_name)}</strong><span>${new Date(x.created_at).toLocaleString("it-IT")}${x.note ? ` · ${this._escape(x.note)}` : ""}</span></div><b>${this._money(x.amount)}</b><button class="icon delete-settlement" type="button" data-id="${this._escape(x.id)}" title="Annulla rimborso">×</button></div>`).join("")}</div>` : ""}

        <div class="section">
          <div class="section-head"><div class="section-title">Ultime bollette</div><button class="secondary small" id="open-all-bills" type="button">${this._allBillsOpen ? "Chiudi elenco completo" : `Tutte le bollette (${allExpenses.length})`}</button></div>
          <div class="list">
            ${expenses.length ? expenses.map((x) => `<div class="row">
              <div><strong>${this._monthLabel(x.paid_year, x.paid_month)}</strong><div class="date">${this._escape(this._periodText(x))}</div></div>
              <div><strong>${this._escape(x.category)}</strong><div class="payer-line">${x.payer ? `Pagatore: ${this._escape(x.payer)} · ` : ""}${this._escape(this._splitText(x))}</div>${x.note ? `<div class="note">${this._escape(x.note)}</div>` : ""}</div>
              <div class="amount"><span class="paid-status ${x.paid ? "yes" : "no"}" title="${x.paid ? "Bolletta pagata" : "Bolletta non pagata"}" aria-label="${x.paid ? "Bolletta pagata" : "Bolletta non pagata"}">✓</span> ${this._money(x.amount)}</div>
              <div class="actions"><button class="icon edit" type="button" data-id="${this._escape(x.id)}" title="Modifica">✎</button><button class="icon delete" type="button" data-id="${this._escape(x.id)}" title="Elimina">×</button></div>
            </div>`).join("") : '<div class="msg">Nessuna bolletta inserita.</div>'}
          </div>
          ${this._allBillsOpen ? `<div class="all-bills-panel">
            <div class="all-bills-toolbar">
              <label>Filtra per tipo
                <select id="all-bills-category">
                  <option value="all" ${this._allBillsCategory === "all" ? "selected" : ""}>Tutti i tipi</option>
                  ${allBillCategories.map((c) => `<option value="${this._escape(c.id)}" ${c.id === this._allBillsCategory ? "selected" : ""}>${this._escape(c.name)}</option>`).join("")}
                </select>
              </label>
              <div class="all-bills-count">${filteredAllExpenses.length} ${filteredAllExpenses.length === 1 ? "bolletta" : "bollette"}</div>
            </div>
            <div class="all-bills-list">
              ${filteredAllExpenses.length ? filteredAllExpenses.map((x) => `<div class="all-row">
                <label class="paid-toggle" title="${x.paid ? "Segna come non pagata" : "Segna come pagata"}">
                  <input class="bill-paid-toggle" type="checkbox" data-id="${this._escape(x.id)}" ${x.paid ? "checked" : ""} aria-label="${x.paid ? "Bolletta pagata" : "Bolletta non pagata"}">
                  <span class="paid-toggle-mark">✓</span>
                </label>
                <div class="all-date"><strong>${this._monthLabel(x.paid_year, x.paid_month)}</strong><div class="date">${this._escape(this._periodText(x))}</div></div>
                <div class="all-main"><strong>${this._escape(x.category)}</strong><div class="payer-line">${x.payer ? `Pagatore: ${this._escape(x.payer)} · ` : ""}${this._escape(this._splitText(x))}</div>${x.note ? `<div class="note">${this._escape(x.note)}</div>` : ""}</div>
                <div class="amount">${this._money(x.amount)}</div>
                <div class="actions"><button class="icon edit" type="button" data-id="${this._escape(x.id)}" title="Modifica">✎</button><button class="icon delete" type="button" data-id="${this._escape(x.id)}" title="Elimina">×</button></div>
              </div>`).join("") : '<div class="msg">Nessuna bolletta per questo filtro.</div>'}
            </div>
          </div>` : ""}
        </div>
      </ha-card>`;

    this.shadowRoot.getElementById("open-form")?.addEventListener("click", () => {
      this._editing = null;
      this._formOpen = true;
      this._render();
    });
    this.shadowRoot.getElementById("settings")?.addEventListener("click", () => this._openSettings());
    this.shadowRoot.getElementById("expense-form")?.addEventListener("submit", (e) => this._submit(e));
    this.shadowRoot.getElementById("cancel")?.addEventListener("click", () => {
      this._editing = null;
      this._formOpen = false;
      this._render();
    });
    this.shadowRoot.getElementById("modal-close")?.addEventListener("click", () => this._closeEditModal());
    this.shadowRoot.getElementById("edit-modal")?.addEventListener("click", (event) => {
      if (event.target?.id === "edit-modal") this._closeEditModal();
    });
    this.shadowRoot.getElementById("edit-modal")?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") this._closeEditModal();
    });
    this.shadowRoot.getElementById("category")?.addEventListener("change", () => this._applyCategoryDefaults());
    this.shadowRoot.getElementById("paid-month")?.addEventListener("change", () => this._autoPeriod());
    this.shadowRoot.querySelectorAll(".split-input").forEach((input) => input.addEventListener("input", () => this._updateSplitTotal()));
    this._updateSplitTotal();
    this.shadowRoot.querySelectorAll(".mode button").forEach((btn) => btn.addEventListener("click", () => {
      this._chartMode = btn.dataset.mode === "normalized" ? "normalized" : "cashflow";
      this._render();
    }));
    this.shadowRoot.getElementById("open-all-bills")?.addEventListener("click", () => {
      this._allBillsOpen = !this._allBillsOpen;
      this._render();
    });
    this.shadowRoot.getElementById("all-bills-category")?.addEventListener("change", (event) => {
      this._allBillsCategory = event.target.value || "all";
      this._render();
    });
    this.shadowRoot.querySelectorAll(".bill-paid-toggle").forEach((input) => input.addEventListener("change", () => this._togglePaid(input)));
    this.shadowRoot.querySelectorAll(".edit").forEach((btn) => btn.addEventListener("click", () => this._startEdit(btn.dataset.id)));
    this.shadowRoot.querySelectorAll(".delete").forEach((btn) => btn.addEventListener("click", () => this._delete(btn.dataset.id)));
    this.shadowRoot.querySelectorAll(".settle").forEach((btn) => btn.addEventListener("click", () => this._settle(btn)));
    this.shadowRoot.querySelectorAll(".delete-settlement").forEach((btn) => btn.addEventListener("click", () => this._deleteSettlement(btn.dataset.id)));
  }

  _updateSplitTotal() {
    const label = this.shadowRoot.getElementById("split-total");
    if (!label) return;
    const total = [...this.shadowRoot.querySelectorAll(".split-input")].reduce((sum, input) => sum + (Number(input.value) || 0), 0);
    label.textContent = `Totale ${total.toFixed(2)}%`;
    label.classList.toggle("bad", Math.abs(total - 100) > 0.05);
  }

  _applyCategoryDefaults() {
    this._autoPeriod();
    const category = this._categoryById(this.shadowRoot.getElementById("category")?.value);
    const payer = this.shadowRoot.getElementById("payer");
    if (payer && category?.default_payer_id && [...payer.options].some((x) => x.value === category.default_payer_id)) {
      payer.value = category.default_payer_id;
    }
  }

  _autoPeriod() {
    const categoryId = this.shadowRoot.getElementById("category")?.value;
    const paid = this._parseMonth(this.shadowRoot.getElementById("paid-month")?.value);
    const category = this._categoryById(categoryId);
    if (!paid || !category) return;
    const interval = Math.max(1, Number(category.interval_months || 1));
    const start = this._addMonths(paid.year, paid.month, -(interval - 1));
    const endInput = this.shadowRoot.getElementById("period-end");
    const startInput = this.shadowRoot.getElementById("period-start");
    if (endInput) endInput.value = this._monthValue(paid.year, paid.month);
    if (startInput) startInput.value = this._monthValue(start.year, start.month);
  }

  _openSettings() {
    history.pushState(null, "", "/config/integrations/integration/bill_tracker");
    window.dispatchEvent(new Event("location-changed"));
  }

  async _submit(event) {
    event.preventDefault();
    if (!this._hass) return;
    const categoryId = this.shadowRoot.getElementById("category")?.value;
    const paid = this._parseMonth(this.shadowRoot.getElementById("paid-month")?.value);
    const start = this._parseMonth(this.shadowRoot.getElementById("period-start")?.value);
    const end = this._parseMonth(this.shadowRoot.getElementById("period-end")?.value);
    const amount = Number(this.shadowRoot.getElementById("amount")?.value);
    const note = this.shadowRoot.getElementById("note")?.value.trim() || "";
    const payerId = this.shadowRoot.getElementById("payer")?.value || undefined;
    const paidFlag = Boolean(this.shadowRoot.getElementById("paid-status")?.checked);
    const split = [...this.shadowRoot.querySelectorAll(".split-input")]
      .map((input) => ({ payer_id: input.dataset.payer, percentage: Number(input.value || 0) }))
      .filter((x) => x.payer_id && x.percentage > 0);
    if (!categoryId || !paid || !start || !end || !Number.isFinite(amount) || amount < 0) {
      this._error = "Controlla i dati inseriti.";
      this._render();
      return;
    }
    if (split.length && Math.abs(split.reduce((sum, x) => sum + x.percentage, 0) - 100) > 0.05) {
      this._error = "Le quote della divisione devono sommare al 100%.";
      this._render();
      return;
    }
    const payload = {
      year: paid.year,
      month: paid.month,
      category_id: categoryId,
      amount,
      note,
      period_start_year: start.year,
      period_start_month: start.month,
      period_end_year: end.year,
      period_end_month: end.month,
      paid: paidFlag,
    };
    if (payerId) payload.payer_id = payerId;
    if (split.length) payload.split = split;
    try {
      if (this._editing) {
        await this._hass.callWS({ type: "bill_tracker/update", expense_id: this._editing.id, ...payload });
      } else {
        await this._hass.callWS({ type: "bill_tracker/add", ...payload });
      }
      this._editing = null;
      this._formOpen = false;
      this._error = null;
      await this._load();
    } catch (err) {
      this._error = String(err?.message || err);
      this._render();
    }
  }

  async _togglePaid(input) {
    if (!this._hass || !input) return;
    const id = input.dataset.id;
    const paid = Boolean(input.checked);
    input.disabled = true;
    try {
      await this._hass.callWS({ type: "bill_tracker/set_paid", expense_id: id, paid });
      this._error = null;
      await this._load();
    } catch (err) {
      input.checked = !paid;
      input.disabled = false;
      this._error = String(err?.message || err);
      this._render();
    }
  }

  _startEdit(id) {
    this._editing = (this._data?.expenses || []).find((x) => x.id === id) || null;
    this._formOpen = false;
    this._render();
    const modal = this.shadowRoot?.getElementById("edit-modal");
    if (modal) {
      modal.tabIndex = -1;
      modal.focus();
    }
  }

  _closeEditModal() {
    this._editing = null;
    this._formOpen = false;
    this._error = null;
    this._render();
  }

  async _delete(id) {
    if (!this._hass || !confirm("Eliminare questa bolletta?")) return;
    try {
      await this._hass.callWS({ type: "bill_tracker/delete", expense_id: id });
      await this._load();
    } catch (err) {
      this._error = String(err?.message || err);
      this._render();
    }
  }

  async _settle(button) {
    if (!this._hass) return;
    const amount = Number(button.dataset.amount || 0);
    const from = button.dataset.from;
    const to = button.dataset.to;
    const fromName = this._payerById(from)?.name || "Il debitore";
    const toName = this._payerById(to)?.name || "il creditore";
    if (!confirm(`Segnare come saldato il rimborso di ${this._money(amount)} da ${fromName} a ${toName}?`)) return;
    try {
      await this._hass.callWS({
        type: "bill_tracker/settlement/add",
        from_payer_id: from,
        to_payer_id: to,
        amount,
        note: "Saldo registrato da Billy",
      });
      await this._load();
    } catch (err) {
      this._error = String(err?.message || err);
      this._render();
    }
  }

  async _deleteSettlement(id) {
    if (!this._hass || !confirm("Annullare questo rimborso? Il saldo verrà ricalcolato.")) return;
    try {
      await this._hass.callWS({ type: "bill_tracker/settlement/delete", settlement_id: id });
      await this._load();
    } catch (err) {
      this._error = String(err?.message || err);
      this._render();
    }
  }
}

class BillTrackerCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = BillTrackerCard.getStubConfig();
  }

  setConfig(config) {
    this._config = { ...BillTrackerCard.getStubConfig(), ...config };
    this._render();
  }

  set hass(_hass) {}

  _render() {
    if (!this.shadowRoot) return;
    const columns = this._config.columns ?? "full";
    this.shadowRoot.innerHTML = `
      <style>
        .editor { display:grid; gap:14px; padding:8px 0; }
        label { display:grid; gap:6px; color:var(--primary-text-color); }
        span { font-size:13px; color:var(--secondary-text-color); }
        input,select { min-height:44px; box-sizing:border-box; width:100%; border:1px solid var(--divider-color); border-radius:10px; padding:8px 10px; background:var(--card-background-color); color:var(--primary-text-color); font-size:16px; }
        .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
        @media (max-width:520px) { .grid { grid-template-columns:1fr; } }
      </style>
      <div class="editor">
        <label><span>Titolo</span><input data-key="title" type="text" value="${this._escape(this._config.title || "")}"></label>
        <div class="grid">
          <label><span>Larghezza predefinita</span><select data-key="columns">
            <option value="full" ${columns === "full" ? "selected" : ""}>Tutta la sezione</option>
            ${[4,6,8,10,12].map((n) => `<option value="${n}" ${Number(columns) === n ? "selected" : ""}>${n} colonne</option>`).join("")}
          </select></label>
          <label><span>Ultime bollette mostrate</span><input data-key="recent" type="number" min="1" max="50" step="1" value="${Number(this._config.recent || 10)}"></label>
          <label><span>Mesi di storico nel grafico</span><input data-key="history_months" type="number" min="3" max="36" step="1" value="${Number(this._config.history_months || 12)}"></label>
          <label><span>Mesi di previsione</span><input data-key="forecast_months" type="number" min="1" max="24" step="1" value="${Number(this._config.forecast_months || 12)}"></label>
        </div>
      </div>`;
    this.shadowRoot.querySelectorAll("input,select").forEach((input) => input.addEventListener("change", () => this._changed(input)));
  }

  _changed(input) {
    const key = input.dataset.key;
    if (!key) return;
    let value = input.value;
    if (["recent", "history_months", "forecast_months"].includes(key)) value = Number(value);
    if (key === "columns" && value !== "full") value = Number(value);
    const config = { ...this._config, [key]: value };
    if (key === "recent") config.recent = Math.max(1, Math.min(50, Number(value || 10)));
    if (key === "history_months") config.history_months = Math.max(3, Math.min(36, Number(value || 12)));
    if (key === "forecast_months") config.forecast_months = Math.max(1, Math.min(24, Number(value || 12)));
    this._config = config;
    const event = new Event("config-changed", { bubbles: true, composed: true });
    event.detail = { config };
    this.dispatchEvent(event);
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }
}

if (!customElements.get("bill-tracker-card")) customElements.define("bill-tracker-card", BillTrackerCard);
if (!customElements.get("bill-tracker-card-editor")) customElements.define("bill-tracker-card-editor", BillTrackerCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "bill-tracker-card")) {
  window.customCards.push({
    type: "bill-tracker-card",
    name: "Billy - Bill Tracker",
    description: "Bollette ricorrenti, divisione spese, saldi e previsioni",
    preview: false,
    documentationURL: "https://github.com/robin994/billy",
  });
}

console.info(`Billy / Bill Tracker card v${BILL_TRACKER_VERSION} loaded`);
