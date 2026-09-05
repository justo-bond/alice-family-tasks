class AliceFamilyTasksCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._lists = [];
    this._loading = true;
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Укажите sensor интеграции Alice Family Tasks");
    this.config = { show_completed: true, ...config };
  }

  set hass(hass) {
    this._hass = hass;
    const summary = hass.states[this.config.entity];
    const recipients = summary?.attributes?.recipients || [];
    const stamp = [
      summary?.last_updated,
      ...recipients.map((item) => hass.states[item.todo_entity]?.last_updated),
    ].join("|");
    if (stamp !== this._stamp) {
      this._stamp = stamp;
      this._load(recipients);
    } else if (!this.shadowRoot.innerHTML) {
      this._render();
    }
  }

  async _load(recipients) {
    if (!this._hass || this._fetching) return;
    this._fetching = true;
    try {
      this._lists = await Promise.all(
        recipients.map(async (recipient) => {
          const result = await this._hass.connection.sendMessagePromise({
            type: "call_service",
            domain: "todo",
            service: "get_items",
            service_data: { status: ["needs_action", "completed"] },
            target: { entity_id: recipient.todo_entity },
            return_response: true,
          });
          const response = result?.response || result?.service_response || result || {};
          return {
            ...recipient,
            items: response?.[recipient.todo_entity]?.items || [],
          };
        })
      );
      this._error = "";
    } catch (error) {
      console.error("alice-family-tasks-card", error);
      this._error = "Не удалось загрузить задачи";
    } finally {
      this._loading = false;
      this._fetching = false;
      this._render();
    }
  }

  _today() {
    const value = new Date();
    return [
      value.getFullYear(),
      String(value.getMonth() + 1).padStart(2, "0"),
      String(value.getDate()).padStart(2, "0"),
    ].join("-");
  }

  _visible(items) {
    const today = this._today();
    return items
      .filter(
        (item) =>
          (this.config.show_completed && item.status === "completed") ||
          (item.status === "needs_action" &&
            (!item.due || String(item.due).slice(0, 10) <= today))
      )
      .sort((left, right) => {
        if (left.status !== right.status) return left.status === "completed" ? 1 : -1;
        const leftDue = left.due ? String(left.due).slice(0, 10) : "9999-12-31";
        const rightDue = right.due ? String(right.due).slice(0, 10) : "9999-12-31";
        return leftDue.localeCompare(rightDue) || left.summary.localeCompare(right.summary, "ru");
      });
  }

  _dueLabel(item) {
    if (!item.due) return "";
    const due = String(item.due).slice(0, 10);
    const pretty = `${due.slice(8, 10)}.${due.slice(5, 7)}`;
    if (due < this._today()) return `Просрочено · ${pretty}`;
    return due === this._today() ? "Сегодня" : pretty;
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async _toggle(entityId, uid, status) {
    await this._hass.callService(
      "todo",
      "update_item",
      { item: uid, status: status === "completed" ? "needs_action" : "completed" },
      { entity_id: entityId }
    );
    this._stamp = "";
    await this._load(this._lists);
  }

  _row(entityId, item) {
    const done = item.status === "completed";
    const due = this._dueLabel(item);
    return `
      <button class="task ${done ? "done" : ""}"
        data-entity="${this._escape(entityId)}"
        data-uid="${this._escape(item.uid)}"
        data-status="${this._escape(item.status)}">
        <span class="check"><ha-icon icon="${done ? "mdi:check" : "mdi:checkbox-blank-circle-outline"}"></ha-icon></span>
        <span class="copy">
          <span class="summary">${this._escape(item.summary)}</span>
          ${due ? `<span class="due ${due.startsWith("Просрочено") ? "overdue" : ""}">${this._escape(due)}</span>` : ""}
        </span>
      </button>`;
  }

  _render() {
    if (!this.config) return;
    const cards = this._lists
      .map((list) => {
        const rows = this._visible(list.items)
          .map((item) => this._row(list.todo_entity, item))
          .join("");
        return `
          <ha-card class="recipient">
            <div class="title">${this._escape(list.name)}</div>
            <div class="tasks">${rows || '<div class="empty">На сегодня задач нет</div>'}</div>
          </ha-card>`;
      })
      .join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; min-width: 0; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 8px; }
        .recipient { min-height: 150px; overflow: hidden; border: 1px solid rgba(255,255,255,.08); border-radius: 8px; background: var(--ha-card-background, #151e29); box-shadow: 0 8px 24px rgba(0,0,0,.16); }
        .title { padding: 20px 20px 10px; font-size: 20px; line-height: 26px; font-weight: 700; }
        .tasks { padding: 0 10px 12px; }
        .task { width: 100%; min-height: 58px; display: flex; align-items: center; gap: 12px; padding: 9px 10px; border: 0; border-top: 1px solid rgba(255,255,255,.06); background: transparent; color: var(--primary-text-color); text-align: left; font: inherit; cursor: pointer; }
        .task:first-child { border-top: 0; }
        .task:active { background: rgba(255,255,255,.06); }
        .check { width: 34px; height: 34px; flex: 0 0 34px; display: grid; place-items: center; border-radius: 50%; color: var(--secondary-text-color); }
        .check ha-icon { --mdc-icon-size: 28px; }
        .done .check { color: #4caf50; background: rgba(76,175,80,.16); }
        .copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
        .summary { font-size: 17px; line-height: 22px; font-weight: 600; overflow-wrap: anywhere; }
        .done .summary { color: var(--secondary-text-color); text-decoration: line-through; }
        .due { color: var(--secondary-text-color); font-size: 13px; line-height: 18px; }
        .due.overdue, .error { color: #ff7b83; font-weight: 650; }
        .empty, .error { padding: 16px 10px 24px; font-size: 16px; color: var(--secondary-text-color); }
      </style>
      <div class="grid">
        ${this._loading ? '<ha-card><div class="empty">Загрузка...</div></ha-card>' : this._error ? `<ha-card><div class="error">${this._escape(this._error)}</div></ha-card>` : cards || '<ha-card><div class="empty">Получатели не настроены</div></ha-card>'}
      </div>`;

    this.shadowRoot.querySelectorAll(".task").forEach((row) => {
      row.addEventListener("click", () =>
        this._toggle(row.dataset.entity, row.dataset.uid, row.dataset.status)
      );
    });
  }

  getCardSize() { return 3; }
  static getStubConfig() { return { entity: "sensor.alice_family_tasks_current_tasks" }; }
}

if (!customElements.get("alice-family-tasks-card")) {
  customElements.define("alice-family-tasks-card", AliceFamilyTasksCard);
}
window.customCards = window.customCards || [];
window.customCards.push({
  type: "alice-family-tasks-card",
  name: "Alice Family Tasks",
  description: "Актуальные семейные задачи по получателям",
});
