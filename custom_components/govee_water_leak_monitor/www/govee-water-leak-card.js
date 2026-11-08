/* Govee Water Leak Monitor — standalone Lovelace card. */
class GoveeWaterLeakCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = undefined;
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Please configure the water sensor entity (entity: binary_sensor....)");
    }
    this._config = { show_details: true, ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return this._config.show_details === false ? 2 : 3; }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }

  _entityFor(role, candidates, domain) {
    const explicit = this._config[`${role}_entity`];
    if (explicit) return explicit;
    if (!this._hass) return undefined;
    const source = this._hass.entities?.[this._config.entity];
    const deviceId = source?.device_id;
    if (!deviceId) return undefined;
    const matches = [];
    for (const [entityId, registry] of Object.entries(this._hass.entities || {})) {
      if (registry.device_id !== deviceId || (domain && !entityId.startsWith(`${domain}.`))) continue;
      const state = this._hass.states[entityId];
      const name = (state?.attributes?.friendly_name || entityId).toLowerCase();
      if (candidates.some((candidate) => name === candidate)) return entityId;
      if (candidates.some((candidate) => name.includes(candidate))) matches.push(entityId);
    }
    return matches[0];
  }

  _relative(value) {
    if (!value) return "Never";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Unknown";
    const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    const units = [[31536000, "year"], [2592000, "month"], [604800, "week"], [86400, "day"], [3600, "hour"], [60, "minute"]];
    for (const [size, label] of units) {
      const amount = Math.floor(seconds / size);
      if (amount >= 1) return `${amount} ${label}${amount === 1 ? "" : "s"} ago`;
    }
    return "just now";
  }

  _timestamp(entityId) {
    const state = entityId && this._hass?.states?.[entityId];
    return state && !["unknown", "unavailable", "none"].includes(state.state)
      ? this._relative(state.state) : "Never";
  }

  async _call(domain, service, entityId) {
    if (!entityId || !this._hass) return;
    await this._hass.callService(domain, service, { entity_id: entityId });
  }

  _render() {
    if (!this.shadowRoot || !this._hass || !this._config.entity) return;
    const entityId = this._config.entity;
    const state = this._hass.states[entityId];
    if (!state) {
      this.shadowRoot.innerHTML = `<ha-card><div class="message">Entity not found: ${this._escape(entityId)}</div></ha-card>`;
      return;
    }
    const wet = state.state === "on";
    const available = !["unavailable", "unknown"].includes(state.state);
    const battery = this._entityFor("battery", ["battery"], "sensor");
    const ack = this._entityFor("acknowledged", ["leak acknowledged", "acknowledged"], "switch");
    const reset = this._entityFor("reset_button", ["reset to dry"], "button");
    const lastWet = this._entityFor("last_wet_event", ["last wet event"], "sensor");
    const batteryState = battery && this._hass.states[battery];
    const batteryValue = batteryState && !["unknown", "unavailable", "none"].includes(batteryState.state)
      ? Number.parseFloat(batteryState.state) : Number.NaN;
    const batteryKnown = Number.isFinite(batteryValue);
    const batteryIcon = !batteryKnown ? "" : batteryValue <= 5 ? "mdi:battery-alert"
      : batteryValue <= 10 ? "mdi:battery-10"
      : batteryValue <= 20 ? "mdi:battery-20"
      : batteryValue <= 30 ? "mdi:battery-30"
      : batteryValue <= 40 ? "mdi:battery-40"
      : batteryValue <= 50 ? "mdi:battery-50"
      : batteryValue <= 60 ? "mdi:battery-60"
      : batteryValue <= 70 ? "mdi:battery-70"
      : batteryValue <= 80 ? "mdi:battery-80"
      : batteryValue <= 90 ? "mdi:battery-90" : "mdi:battery";
    const ackState = ack && this._hass.states[ack];
    const title = state.attributes.friendly_name || entityId;
    const secondary = wet ? "Wet" : (available ? "Dry" : "Unavailable");
    const wetTime = this._timestamp(lastWet);
    const showWetTime = wetTime.toLowerCase() !== "never";
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block} ha-card{padding:14px 16px;border-radius:var(--ha-card-border-radius,12px);overflow:hidden}
        .top{display:flex;align-items:center;gap:14px}.symbol{width:44px;height:44px;display:grid;place-items:center;background:transparent;color:${wet ? "var(--error-color)" : "var(--secondary-text-color)"}}
        .symbol ha-icon{--mdc-icon-size:40px}.heading{min-width:0;flex:1}.name{font-size:16px;font-weight:600;overflow-wrap:anywhere}
        .status-line{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:4px}.status{display:inline-flex;align-items:center;font-size:14px;color:${wet ? "var(--error-color)" : "var(--secondary-text-color)"}}.wet-time{font-size:12px;color:var(--secondary-text-color)}
        .battery{display:flex;align-items:center;gap:4px;font-size:13px;color:var(--secondary-text-color);white-space:nowrap}.battery ha-icon{--mdc-icon-size:18px}
        .details{display:grid;grid-template-columns:1fr;gap:12px;margin-top:14px;padding-top:12px;border-top:1px solid var(--divider-color)}.details div{display:flex;flex-direction:column;gap:3px;min-width:0}.details span{font-size:11px;color:var(--secondary-text-color)}.details b{font-size:12px;font-weight:500;overflow-wrap:anywhere}
        .controls{display:flex;gap:8px;justify-content:flex-end;margin-top:14px;flex-wrap:wrap}.controls button{display:inline-flex;align-items:center;gap:6px;border:0;border-radius:18px;padding:8px 13px;background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit;font-size:12px;cursor:pointer}.controls button ha-icon{--mdc-icon-size:16px}.controls button:disabled{opacity:.45;cursor:default}.ack{color:${ackState?.state === "on" ? "var(--warning-color)" : "var(--error-color)"}!important}
        .message{padding:16px;color:var(--secondary-text-color)}
      </style>
      <ha-card>
        <div class="top">
          <div class="symbol"><ha-icon icon="${wet ? "mdi:water" : "mdi:water-off"}"></ha-icon></div>
          <div class="heading">
            <div class="name">${this._escape(title)}</div>
            <div class="status-line">
              <span class="status">${secondary}</span>
              ${showWetTime ? `<span class="wet-time">Water last detected ${this._escape(wetTime)}</span>` : ""}
            </div>
          </div>
          ${batteryKnown ? `<div class="battery"><ha-icon icon="${batteryIcon}"></ha-icon>${this._escape(batteryState.state)}${this._escape(batteryState.attributes.unit_of_measurement || "%")}</div>` : ""}
        </div>
        ${wet ? `<div class="controls">
          ${ack ? `<button class="ack" data-action="ack"><ha-icon icon="mdi:alert"></ha-icon>${ackState?.state === "on" ? "Alert Acknowledged" : "Alert Active"}</button>` : ""}
          ${reset ? `<button data-action="reset"><ha-icon icon="mdi:water-off"></ha-icon>Reset to Dry</button>` : ""}
        </div>` : ""}
      </ha-card>`;
    this.shadowRoot.querySelector('[data-action="ack"]')?.addEventListener("click", async () => {
      await this._call("switch", ackState?.state === "on" ? "turn_off" : "turn_on", ack);
    });
    this.shadowRoot.querySelector('[data-action="reset"]')?.addEventListener("click", () => this._call("button", "press", reset));
  }

  static getConfigElement() { return document.createElement("govee-water-leak-card-editor"); }
  static getStubConfig() { return { entity: "binary_sensor.your_govee_water_sensor" }; }
}

class GoveeWaterLeakCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = undefined;
    this._optionsKey = undefined;
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass) return;
    const options = Object.keys(this._hass.states).filter((id) =>
      id.startsWith("binary_sensor.") &&
      (this._hass.states[id].attributes.device_class === "moisture" ||
       this._hass.states[id].attributes.friendly_name?.toLowerCase().includes("water sensor"))
    ).sort();
    const optionsKey = options.join("|");
    let select = this.querySelector("select");

    // Do not replace the select on every Home Assistant state update: doing so
    // closes its native dropdown as soon as the user moves the pointer to it.
    if (!select || optionsKey !== this._optionsKey) {
      this.innerHTML = `<div class="card-config"><label for="govee-water-entity">Water sensor</label><select id="govee-water-entity"></select><p>Select the rtl_433 moisture sensor for this Govee device. Related monitor entities are detected automatically.</p></div><style>.card-config{padding:8px 0}label{display:block;margin-bottom:8px}select{width:100%;padding:8px;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:4px}p{color:var(--secondary-text-color);font-size:12px}</style>`;
      select = this.querySelector("select");
      select.innerHTML = options.map((id) =>
        `<option value="${this._escape(id)}">${this._escape(this._hass.states[id].attributes.friendly_name || id)}</option>`
      ).join("");
      select.addEventListener("change", (ev) => {
        this._config = { ...this._config, entity: ev.target.value };
        this.dispatchEvent(new CustomEvent("config-changed", {
          detail: { config: this._config }, bubbles: true, composed: true
        }));
      });
      this._optionsKey = optionsKey;
    }

    if (select && this._config.entity && select.value !== this._config.entity) {
      select.value = this._config.entity;
    }
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }
}

if (!customElements.get("govee-water-leak-card")) customElements.define("govee-water-leak-card", GoveeWaterLeakCard);
if (!customElements.get("govee-water-leak-card-editor")) customElements.define("govee-water-leak-card-editor", GoveeWaterLeakCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "govee-water-leak-card")) {
  window.customCards.push({ type: "govee-water-leak-card", name: "Govee Water Leak Monitor", description: "A standalone card for one Govee water sensor." });
}
