/* Govee Water Leak Monitor — aggregate Lovelace card. */
class GoveeWaterLeakCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = undefined;
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    const count = this._monitorEntities().length;
    return Math.max(2, count * 2);
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }

  _entityFor(sourceEntityId, role, candidates, domain) {
    if (!this._hass) return undefined;
    const source = this._hass.entities?.[sourceEntityId];
    const deviceId = source?.device_id;
    if (!deviceId) return undefined;
    const matches = [];
    for (const [entityId, registry] of Object.entries(this._hass.entities || {})) {
      if (registry.device_id !== deviceId || (domain && !entityId.startsWith(`${domain}.`))) continue;
      const name = (this._hass.states[entityId]?.attributes?.friendly_name || entityId).toLowerCase();
      if (candidates.some((candidate) => name === candidate)) return entityId;
      if (candidates.some((candidate) => name.includes(candidate))) matches.push(entityId);
    }
    return matches[0];
  }

  _monitorEntities() {
    if (!this._hass) return [];
    return Object.keys(this._hass.states)
      .filter((id) => {
        if (!id.startsWith("binary_sensor.")) return false;
        const state = this._hass.states[id];
        if (state.attributes.device_class !== "moisture") return false;
        // Only include moisture sensors that have been paired with this integration.
        return Boolean(
          this._entityFor(id, "acknowledged", ["leak acknowledged", "acknowledged"], "switch") ||
          this._entityFor(id, "reset_button", ["reset to dry"], "button")
        );
      })
      .sort((a, b) => {
        const an = this._hass.states[a]?.attributes?.friendly_name || a;
        const bn = this._hass.states[b]?.attributes?.friendly_name || b;
        return an.localeCompare(bn);
      });
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

  _batteryMarkup(sourceId) {
    const sourceDeviceId = this._hass.entities?.[sourceId]?.device_id;
    const batteryCandidates = Object.entries(this._hass.entities || {})
      .filter(([entityId, registry]) => {
        if (registry.device_id !== sourceDeviceId || !entityId.startsWith("sensor.")) return false;
        const name = (this._hass.states[entityId]?.attributes?.friendly_name || entityId).toLowerCase();
        return name === "battery" || (name.includes("battery") && !/(last|report|mv|voltage|ok)/.test(name));
      })
      .map(([entityId]) => entityId);
    const battery = batteryCandidates.find((id) =>
      (this._hass.states[id]?.attributes?.friendly_name || id).toLowerCase() === "battery"
    ) || batteryCandidates[0];
    const batteryState = battery && this._hass.states[battery];
    const value = batteryState && !["unknown", "unavailable", "none"].includes(batteryState.state)
      ? Number.parseFloat(batteryState.state) : Number.NaN;
    if (!Number.isFinite(value)) return "";
    const icon = value <= 5 ? "mdi:battery-alert"
      : value <= 10 ? "mdi:battery-10" : value <= 20 ? "mdi:battery-20"
      : value <= 30 ? "mdi:battery-30" : value <= 40 ? "mdi:battery-40"
      : value <= 50 ? "mdi:battery-50" : value <= 60 ? "mdi:battery-60"
      : value <= 70 ? "mdi:battery-70" : value <= 80 ? "mdi:battery-80"
      : value <= 90 ? "mdi:battery-90" : "mdi:battery";
    const unit = batteryState.attributes.unit_of_measurement || "%";
    return `<div class="battery"><ha-icon icon="${icon}"></ha-icon><span>${this._escape(batteryState.state)}${this._escape(unit)}</span></div>`;
  }

  _cardMarkup(sourceId) {
    const state = this._hass.states[sourceId];
    const wet = state.state === "on";
    const available = !["unavailable", "unknown"].includes(state.state);
    const title = state.attributes.friendly_name || sourceId;
    const ack = this._entityFor(sourceId, "acknowledged", ["leak acknowledged", "acknowledged"], "switch");
    const reset = this._entityFor(sourceId, "reset_button", ["reset to dry"], "button");
    const lastWet = this._entityFor(sourceId, "last_wet_event", ["last wet event"], "sensor");
    const ackState = ack && this._hass.states[ack];
    const status = wet ? "Wet" : (available ? "Dry" : "Unavailable");
    const wetTime = this._timestamp(lastWet);
    const showWetTime = wetTime.toLowerCase() !== "never";
    return `
      <ha-card class="monitor-card">
        <div class="top">
          <div class="symbol ${wet ? "wet" : "dry"}"><ha-icon icon="${wet ? "mdi:water" : "mdi:water-off"}"></ha-icon></div>
          <div class="heading">
            <div class="name">${this._escape(title)}</div>
            <div class="status-line">
              <span class="status ${wet ? "wet-text" : ""}">${status}</span>
              ${showWetTime ? `<span class="wet-time">Water last detected ${this._escape(wetTime)}</span>` : ""}
            </div>
          </div>
          ${this._batteryMarkup(sourceId)}
        </div>
        ${wet ? `<div class="controls">
          ${ack ? `<button class="ack ${ackState?.state === "on" ? "acknowledged" : "active"}" data-action="ack" data-entity="${this._escape(ack)}"><ha-icon icon="mdi:alert"></ha-icon>${ackState?.state === "on" ? "Alert Acknowledged" : "Alert Active"}</button>` : ""}
          ${reset ? `<button data-action="reset" data-entity="${this._escape(reset)}"><ha-icon icon="mdi:water-off"></ha-icon>Reset to Dry</button>` : ""}
        </div>` : ""}
      </ha-card>`;
  }

  _render() {
    if (!this.shadowRoot || !this._hass) return;
    const monitors = this._monitorEntities();
    const style = `
      <style>
        :host{display:block}.monitor-card{padding:9px 14px;border-radius:var(--ha-card-border-radius,12px);overflow:hidden;margin:0 0 8px}
        .monitor-card:last-child{margin-bottom:0}.top{display:flex;align-items:center;gap:11px}
        .symbol{width:30px;height:30px;flex:0 0 30px;display:grid;place-items:center;background:transparent}
        .symbol ha-icon{--mdc-icon-size:27px}.symbol.wet{color:var(--error-color)}.symbol.dry{color:var(--secondary-text-color)}
        .heading{min-width:0;flex:1}.name{font-size:14px;line-height:1.25;font-weight:600;overflow-wrap:anywhere;color:var(--primary-text-color)}
        .status-line{display:flex;align-items:baseline;flex-wrap:wrap;margin-top:2px;line-height:1.25;font-size:14px}
        .status{font-size:14px;line-height:1.25;color:var(--secondary-text-color)}.wet-text{color:var(--error-color)}
        .wet-time{font-size:14px;line-height:1.25;color:var(--secondary-text-color);margin-left:6px}.wet-time:before{content:"-";margin-right:6px}
        .battery{display:flex;align-items:center;justify-content:center;gap:4px;font-size:14px;line-height:1;color:var(--primary-text-color);white-space:nowrap;align-self:center}
        .battery ha-icon{--mdc-icon-size:18px;display:block;flex:0 0 auto}.battery span{display:flex;align-items:center;line-height:1;min-height:18px}
        .controls{display:flex;gap:8px;justify-content:flex-end;margin-top:8px;flex-wrap:wrap}
        .controls button{display:inline-flex;align-items:center;gap:6px;border:0;border-radius:18px;padding:6px 11px;background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit;font-size:12px;line-height:1.2;cursor:pointer}
        .controls button ha-icon{--mdc-icon-size:16px}.ack.active{color:var(--error-color)}.ack.acknowledged{color:var(--warning-color)}
        .empty{padding:12px 14px;color:var(--secondary-text-color);font-size:14px;background:var(--card-background-color);border-radius:var(--ha-card-border-radius,12px)}
      </style>`;
    this.shadowRoot.innerHTML = style + (monitors.length
      ? monitors.map((id) => this._cardMarkup(id)).join("")
      : `<div class="empty">No Govee leak monitors are currently discovered.</div>`);

    this.shadowRoot.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.action;
        const entityId = button.dataset.entity;
        if (action === "reset") {
          await this._call("button", "press", entityId);
        } else if (action === "ack") {
          const current = this._hass.states[entityId]?.state === "on";
          await this._call("switch", current ? "turn_off" : "turn_on", entityId);
        }
      });
    });
  }

  static getStubConfig() { return {}; }
}

if (!customElements.get("govee-water-leak-card")) customElements.define("govee-water-leak-card", GoveeWaterLeakCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "govee-water-leak-card")) {
  window.customCards.push({ type: "govee-water-leak-card", name: "Govee Water Leak Monitor", description: "Displays all discovered Govee water leak monitors in individual compact sections." });
}
