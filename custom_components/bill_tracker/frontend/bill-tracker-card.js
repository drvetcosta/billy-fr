const BILL_TRACKER_VERSION = "0.3.0";

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
    this._unsubscribe = null;
  }

  static getStubConfig() {
    return {
      title: "Bollette di casa",
      columns: 12,
      recent: 10,
      history_months: 12,
      forecast_months: 12,
    };
  }

  static getConfigElement() {
    return document.createElement("bill-tracker-card-editor");
  }

  setConfig(config) {
    const columns = Math.max(1, Math.min(12, Number(config.columns ?? 12)));
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
    return 10;
  }

  getGridOptions() {
    return {
      columns: Math.max(1, Math.min(12, Number(this._config.columns || 12))),
      min_columns: 3,
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
      // The card still refreshes after local writes if event subscription is unavailable.
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

  _categoryById(id) {
    return (this._data?.categories || []).find((x) => x.id === id) || null;
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
    const values = rows.map((x) => Number(x.total || 0));
    const maxValue = Math.max(1, ...values) * 1.15;
    const width = Math.max(820, rows.length * 48 + 74);
    const height = 270;
    const left = 56;
    const right = 18;
    const top = 18;
    const bottom = 46;
    const plotW = width - left - right;
    const plotH = height - top - bottom;
    const step = plotW / Math.max(1, rows.length);
    const barW = Math.max(8, Math.min(30, step * 0.58));
    const y = (v) => top + plotH - (Number(v || 0) / maxValue) * plotH;
    const x = (i) => left + step * i + step / 2;

    const grid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
      const gy = top + plotH * (1 - ratio);
      const val = maxValue * ratio;
      return `<line x1="${left}" y1="${gy}" x2="${width - right}" y2="${gy}" class="grid" />
        <text x="${left - 8}" y="${gy + 4}" text-anchor="end" class="axis-value">${Math.round(val)}€</text>`;
    }).join("");

    const bars = actual.map((row, i) => {
      const value = Number(row.total || 0);
      const h = Math.max(0, top + plotH - y(value));
      const bx = x(i) - barW / 2;
      return `<rect x="${bx}" y="${y(value)}" width="${barW}" height="${h}" rx="4" class="actual-bar">
        <title>${this._monthNames()[row.month - 1]} ${row.year}: ${this._money(value)}</title>
      </rect>`;
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
      return `<circle cx="${px}" cy="${py}" r="4" class="forecast-dot">
        <title>${this._monthNames()[row.month - 1]} ${row.year}: stima ${this._money(row.total)}</title>
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
      <svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Grafico delle bollette reali e previste">
        ${grid}
        ${bars}
        ${divider}
        ${forecastPath ? `<path d="${forecastPath}" class="forecast-line" />` : ""}
        ${forecastDots}
        ${labels}
      </svg>
    </div>`;
  }

  _periodText(item) {
    const start = this._monthValue(item.period_start_year, item.period_start_month);
    const end = this._monthValue(item.period_end_year, item.period_end_month);
    if (start === end) return `${this._monthShort()[item.period_start_month - 1]} ${item.period_start_year}`;
    return `${this._monthShort()[item.period_start_month - 1]} ${item.period_start_year} – ${this._monthShort()[item.period_end_month - 1]} ${item.period_end_year}`;
  }

  _render() {
    if (!this.shadowRoot) return;
    const now = this._defaultDate();
    const editing = this._editing;
    const activeCategories = this._activeCategories();
    const selectedCategoryId = editing?.category_id || activeCategories[0]?.id || "";
    const selectedCategory = this._categoryById(selectedCategoryId) || activeCategories[0] || null;
    const selectedPaid = editing
      ? this._monthValue(editing.paid_year, editing.paid_month)
      : this._monthValue(now.year, now.month);

    let defaultEnd = editing
      ? this._monthValue(editing.period_end_year, editing.period_end_month)
      : selectedPaid;
    let defaultStart;
    if (editing) {
      defaultStart = this._monthValue(editing.period_start_year, editing.period_start_month);
    } else {
      const parsedPaid = this._parseMonth(selectedPaid) || now;
      const start = this._addMonths(parsedPaid.year, parsedPaid.month, -(Math.max(1, Number(selectedCategory?.interval_months || 1)) - 1));
      defaultStart = this._monthValue(start.year, start.month);
    }

    const summary = this._data?.summary || {};
    const recent = (this._data?.expenses || []).slice(0, this._config.recent || 10);
    const upcoming = (this._data?.upcoming || []).slice(0, 8);

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-width:0; }
        ha-card { padding:16px; overflow:hidden; }
        .head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:14px; flex-wrap:wrap; }
        .head-actions { display:flex; gap:8px; flex-wrap:wrap; }
        .title { font-size:20px; font-weight:600; }
        .stats { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:16px; }
        .stat { padding:12px; border:1px solid var(--divider-color); border-radius:12px; background:var(--ha-card-background,var(--card-background-color)); min-width:0; }
        .stat span { display:block; color:var(--secondary-text-color); font-size:12px; margin-bottom:5px; }
        .stat strong { font-size:18px; overflow-wrap:anywhere; }
        form { display:grid; grid-template-columns:1.1fr 1.25fr 1fr 1fr; gap:8px; align-items:end; padding:12px; border:1px solid var(--divider-color); border-radius:12px; margin-bottom:16px; }
        label { display:flex; flex-direction:column; gap:5px; font-size:12px; color:var(--secondary-text-color); min-width:0; }
        .note-field { grid-column:1 / -1; }
        select,input { box-sizing:border-box; width:100%; min-height:44px; border-radius:10px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); padding:8px 10px; font-size:16px; }
        button { min-height:42px; border:0; border-radius:10px; padding:0 14px; cursor:pointer; font-weight:600; }
        .primary { background:var(--primary-color); color:var(--text-primary-color,white); }
        .secondary { background:transparent; border:1px solid var(--divider-color); color:var(--primary-text-color); }
        .buttons { grid-column:1 / -1; display:flex; justify-content:flex-end; gap:8px; flex-wrap:wrap; }
        .form-help { grid-column:1 / -1; color:var(--secondary-text-color); font-size:12px; margin-top:-2px; }
        .chart-panel { padding:14px 0 6px; border-top:1px solid var(--divider-color); border-bottom:1px solid var(--divider-color); }
        .chart-head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:6px; flex-wrap:wrap; }
        .chart-copy strong { display:block; font-size:15px; }
        .chart-copy span { color:var(--secondary-text-color); font-size:12px; }
        .mode { display:flex; border:1px solid var(--divider-color); border-radius:10px; overflow:hidden; }
        .mode button { min-height:34px; border-radius:0; background:transparent; color:var(--primary-text-color); font-size:12px; }
        .mode button.active { background:var(--primary-color); color:var(--text-primary-color,white); }
        .legend { display:flex; gap:12px; align-items:center; margin:8px 0 0; color:var(--secondary-text-color); font-size:12px; flex-wrap:wrap; }
        .legend span { display:flex; gap:6px; align-items:center; }
        .legend-bar { width:10px; height:10px; border-radius:2px; background:var(--primary-color); display:inline-block; }
        .legend-line { width:18px; border-top:2px dashed var(--warning-color,#f0ad4e); display:inline-block; }
        .chart-scroll { width:100%; overflow-x:auto; }
        .chart { width:100%; min-width:700px; height:auto; overflow:visible; }
        .grid { stroke:var(--divider-color); stroke-width:1; opacity:.7; }
        .axis-value,.axis-label { fill:var(--secondary-text-color); font-size:10px; }
        .actual-bar { fill:var(--primary-color); opacity:.78; }
        .forecast-line { fill:none; stroke:var(--warning-color,#f0ad4e); stroke-width:3; stroke-dasharray:7 6; stroke-linecap:round; stroke-linejoin:round; }
        .forecast-dot { fill:var(--card-background-color); stroke:var(--warning-color,#f0ad4e); stroke-width:2; }
        .forecast-divider { stroke:var(--secondary-text-color); stroke-width:1; stroke-dasharray:3 5; opacity:.5; }
        .empty-chart { color:var(--secondary-text-color); padding:24px 4px; text-align:center; }
        .section-title { margin-top:16px; font-size:15px; font-weight:600; }
        .upcoming-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; margin-top:8px; }
        .upcoming-item { border:1px solid var(--divider-color); border-radius:10px; padding:10px; display:grid; gap:4px; }
        .upcoming-item span { color:var(--secondary-text-color); font-size:12px; }
        .upcoming-item strong { display:flex; justify-content:space-between; gap:8px; }
        .list { margin-top:6px; }
        .row { display:grid; grid-template-columns:125px minmax(150px,1fr) 120px auto; gap:10px; align-items:center; padding:10px 0; border-bottom:1px solid var(--divider-color); }
        .date,.note,.competence { color:var(--secondary-text-color); font-size:12px; }
        .amount { text-align:right; font-weight:600; }
        .actions { display:flex; gap:6px; }
        .icon { min-width:34px; min-height:34px; padding:0 8px; background:transparent; border:1px solid var(--divider-color); color:var(--primary-text-color); }
        .msg { margin:10px 0; font-size:13px; }
        .error { color:var(--error-color); }
        .warning { padding:10px 12px; border-radius:10px; border:1px solid var(--warning-color,#f0ad4e); margin-bottom:12px; }
        @media (max-width:900px) {
          .stats { grid-template-columns:repeat(2,minmax(0,1fr)); }
          form { grid-template-columns:1fr 1fr; }
          .note-field,.buttons,.form-help { grid-column:1 / -1; }
        }
        @media (max-width:620px) {
          .stats { grid-template-columns:1fr; }
          form { grid-template-columns:1fr; }
          .note-field,.buttons,.form-help { grid-column:1; }
          .row { grid-template-columns:1fr auto; }
          .row .amount { grid-column:1; text-align:left; }
          .row .actions { grid-column:2; grid-row:1 / span 2; }
        }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${this._escape(this._config.title || "Bollette di casa")}</div>
          <div class="head-actions">
            <button class="secondary" id="settings" type="button">⚙ Tipi bolletta</button>
            <button class="primary" id="open-form" type="button" ${activeCategories.length ? "" : "disabled"}>+ Aggiungi bolletta</button>
          </div>
        </div>
        <div class="stats">
          <div class="stat"><span>Pagato questo mese</span><strong>${this._money(summary.current_month)}</strong></div>
          <div class="stat"><span>Media pagamenti 6 mesi</span><strong>${this._money(summary.average_6_months)}</strong></div>
          <div class="stat"><span>Stima prossimo mese</span><strong>${this._money(summary.next_month_estimate)}</strong></div>
          <div class="stat"><span>Costo mensile normalizzato</span><strong>${this._money(summary.normalized_current_month)}</strong></div>
        </div>
        ${!activeCategories.length ? '<div class="warning">Nessun tipo di bolletta attivo. Apri <strong>Tipi bolletta</strong> e abilita o aggiungi almeno una voce.</div>' : ""}
        ${(this._formOpen || editing) ? `<form id="expense-form">
          <label>Tipo
            <select id="category" required>
              ${activeCategories.map((c) => `<option value="${this._escape(c.id)}" ${c.id===selectedCategoryId?"selected":""}>${this._escape(c.name)} · ${this._escape(this._intervalLabel(c.interval_months))}</option>`).join("")}
              ${editing && selectedCategory && !selectedCategory.enabled ? `<option value="${this._escape(selectedCategory.id)}" selected>${this._escape(selectedCategory.name)} · disattivata</option>` : ""}
            </select>
          </label>
          <label>Mese pagamento
            <input id="paid-month" type="month" required value="${this._escape(selectedPaid)}">
          </label>
          <label>Importo (€)
            <input id="amount" type="number" min="0" step="0.01" inputmode="decimal" required value="${editing ? this._escape(editing.amount) : ""}" placeholder="0,00">
          </label>
          <label>Fine competenza
            <input id="period-end" type="month" required value="${this._escape(defaultEnd)}">
          </label>
          <label>Inizio competenza
            <input id="period-start" type="month" required value="${this._escape(defaultStart)}">
          </label>
          <label class="note-field">Nota (opzionale)
            <input id="note" type="text" maxlength="120" value="${editing ? this._escape(editing.note || "") : ""}" placeholder="Es. conguaglio, rata, periodo fatturato...">
          </label>
          <div class="form-help">La periodicità del tipo precompila automaticamente il periodo di competenza; puoi comunque correggerlo.</div>
          <div class="buttons">
            <button class="secondary" id="cancel" type="button">Annulla</button>
            <button class="primary" type="submit">${editing ? "Salva modifiche" : "Aggiungi"}</button>
          </div>
        </form>` : ""}
        ${this._error ? `<div class="msg error">${this._escape(this._error)}</div>` : ""}
        <div class="chart-panel">
          <div class="chart-head">
            <div class="chart-copy"><strong>Andamento e previsione</strong><span>${this._chartMode === "cashflow" ? "Pagamenti reali e prossime scadenze stimate" : "Costo distribuito sui mesi di competenza"}</span></div>
            <div class="mode">
              <button type="button" data-mode="cashflow" class="${this._chartMode === "cashflow" ? "active" : ""}">Pagamenti</button>
              <button type="button" data-mode="normalized" class="${this._chartMode === "normalized" ? "active" : ""}">Costo mensile</button>
            </div>
          </div>
          <div class="legend"><span><i class="legend-bar"></i>Reale</span><span><i class="legend-line"></i>Stima</span></div>
          ${this._chart()}
        </div>
        <div class="section-title">Prossime bollette stimate</div>
        ${upcoming.length ? `<div class="upcoming-grid">${upcoming.map((x) => `
          <div class="upcoming-item">
            <span>${this._monthNames()[Number(x.month)-1]} ${x.year}</span>
            <strong><b>${this._escape(x.category)}</b><b>${this._money(x.amount)}</b></strong>
          </div>`).join("")}</div>` : '<div class="msg">Servono almeno una bolletta storica per tipo per calcolare le prossime scadenze.</div>'}
        <div class="section-title">Ultime bollette</div>
        <div class="list">
          ${recent.length ? recent.map((x) => `
            <div class="row">
              <div class="date">Pagata: ${this._monthNames()[Number(x.paid_month)-1]} ${x.paid_year}</div>
              <div><strong>${this._escape(x.category)}</strong><div class="competence">Competenza: ${this._escape(this._periodText(x))}</div>${x.note ? `<div class="note">${this._escape(x.note)}</div>` : ""}</div>
              <div class="amount">${this._money(x.amount)}</div>
              <div class="actions">
                <button class="icon edit" type="button" data-id="${this._escape(x.id)}" title="Modifica">✎</button>
                <button class="icon delete" type="button" data-id="${this._escape(x.id)}" title="Elimina">×</button>
              </div>
            </div>`).join("") : '<div class="msg">Nessuna bolletta inserita.</div>'}
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
    this.shadowRoot.getElementById("category")?.addEventListener("change", () => this._autoPeriod());
    this.shadowRoot.getElementById("paid-month")?.addEventListener("change", () => this._autoPeriod());
    this.shadowRoot.querySelectorAll(".mode button").forEach((btn) => btn.addEventListener("click", () => {
      this._chartMode = btn.dataset.mode === "normalized" ? "normalized" : "cashflow";
      this._render();
    }));
    this.shadowRoot.querySelectorAll(".edit").forEach((btn) => btn.addEventListener("click", () => this._startEdit(btn.dataset.id)));
    this.shadowRoot.querySelectorAll(".delete").forEach((btn) => btn.addEventListener("click", () => this._delete(btn.dataset.id)));
  }

  _autoPeriod() {
    const categoryId = this.shadowRoot.getElementById("category")?.value;
    const paidValue = this.shadowRoot.getElementById("paid-month")?.value;
    const paid = this._parseMonth(paidValue);
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
    // Navigate using Home Assistant's SPA route; the integration exposes a native Configure flow.
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

    if (!categoryId || !paid || !start || !end || !Number.isFinite(amount) || amount < 0) {
      this._error = "Controlla i dati inseriti.";
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
    };

    try {
      if (this._editing) {
        await this._hass.callWS({
          type: "bill_tracker/update",
          expense_id: this._editing.id,
          ...payload,
        });
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

  _startEdit(id) {
    this._editing = (this._data?.expenses || []).find((x) => x.id === id) || null;
    this._formOpen = true;
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
    this.shadowRoot.innerHTML = `
      <style>
        .editor { display:grid; gap:14px; padding:8px 0; }
        label { display:grid; gap:6px; color:var(--primary-text-color); }
        span { font-size:13px; color:var(--secondary-text-color); }
        input { min-height:44px; box-sizing:border-box; width:100%; border:1px solid var(--divider-color); border-radius:10px; padding:8px 10px; background:var(--card-background-color); color:var(--primary-text-color); font-size:16px; }
        .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
        @media (max-width:520px) { .grid { grid-template-columns:1fr; } }
      </style>
      <div class="editor">
        <label><span>Titolo</span><input data-key="title" type="text" value="${this._escape(this._config.title || "")}"></label>
        <div class="grid">
          <label><span>Colonne occupate (1–12)</span><input data-key="columns" type="number" min="1" max="12" step="1" value="${Number(this._config.columns || 12)}"></label>
          <label><span>Ultime bollette mostrate</span><input data-key="recent" type="number" min="1" max="50" step="1" value="${Number(this._config.recent || 10)}"></label>
          <label><span>Mesi di storico nel grafico</span><input data-key="history_months" type="number" min="3" max="36" step="1" value="${Number(this._config.history_months || 12)}"></label>
          <label><span>Mesi di previsione</span><input data-key="forecast_months" type="number" min="1" max="24" step="1" value="${Number(this._config.forecast_months || 12)}"></label>
        </div>
      </div>`;

    this.shadowRoot.querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", () => this._changed(input));
    });
  }

  _changed(input) {
    const key = input.dataset.key;
    if (!key) return;
    let value = input.value;
    if (["columns", "recent", "history_months", "forecast_months"].includes(key)) {
      value = Number(value);
    }
    const config = { ...this._config, [key]: value };
    if (key === "columns") config.columns = Math.max(1, Math.min(12, Number(value || 12)));
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

if (!customElements.get("bill-tracker-card")) {
  customElements.define("bill-tracker-card", BillTrackerCard);
}
if (!customElements.get("bill-tracker-card-editor")) {
  customElements.define("bill-tracker-card-editor", BillTrackerCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "bill-tracker-card")) {
  window.customCards.push({
    type: "bill-tracker-card",
    name: "Bill Tracker",
    description: "Bollette ricorrenti con storico, competenza e previsione",
    preview: false,
    documentationURL: "https://github.com/robin994/HomeAssistant-Bill-Tracker",
  });
}

console.info(`Bill Tracker card v${BILL_TRACKER_VERSION} loaded`);
