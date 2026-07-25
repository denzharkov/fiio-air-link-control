"use strict";

const state = {
  document: null,
  forms: new Map(),
  busy: false,
  polling: false,
};

const app = document.querySelector("#app");
const startupStartedAt = performance.now();
const minimumStartupDuration = 1400;
let startupStatusPriority = 0;
let startupLocale = localStorage.getItem("falc.locale") === "ru" ? "ru" : "en";
const startupMessages = {
  en: {
    initialize: "Initializing interface",
    prepare: "Preparing application",
    connect: "Connecting to device",
    data: "Loading data",
    ready: "Ready",
    error: "Startup error",
  },
  ru: {
    initialize: "Инициализация интерфейса",
    prepare: "Подготовка приложения",
    connect: "Подключение к устройству",
    data: "Загрузка данных",
    ready: "Готово",
    error: "Ошибка запуска",
  },
};

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function setStartupStatus(message, priority) {
  const status = document.querySelector("#startup-status");
  if (!status || priority < startupStatusPriority) return;
  startupStatusPriority = priority;
  status.textContent = message;
}

setStartupStatus(startupMessages[startupLocale].initialize, 0);
window.setTimeout(() => setStartupStatus(startupMessages[startupLocale].prepare, 1), 280);
window.setTimeout(() => setStartupStatus(startupMessages[startupLocale].connect, 2), 680);

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function childrenInto(parent, children, context = {}) {
  for (const child of children || []) {
    parent.append(renderNode(child, context));
  }
  return parent;
}

function renderNode(node, context = {}) {
  if (!node || typeof node !== "object") return document.createTextNode("");

  switch (node.type) {
    case "stack": {
      const target = element("div", `stack gap-${node.gap || "medium"}`);
      return childrenInto(target, node.children, context);
    }
    case "row": {
      const classes = ["row"];
      if (node.align) classes.push(`align-${node.align}`);
      if (node.justify) classes.push(`justify-${node.justify}`);
      if (node.wrap) classes.push("wrap");
      if (node.variant) classes.push(`row-${node.variant}`);
      return childrenInto(element("div", classes.join(" ")), node.children, context);
    }
    case "grid": {
      const target = element("div", "grid");
      target.style.setProperty("--grid-min", `${node.minimum || 300}px`);
      return childrenInto(target, node.children, context);
    }
    case "card": {
      const target = element("section", "card");
      target.append(element("h2", "card-title", node.title || ""));
      return childrenInto(target, node.children, context);
    }
    case "hero": {
      const target = element("section", "hero");
      target.append(element("div", "eyebrow", node.eyebrow || ""));
      target.append(element("h1", "hero-title", node.title || ""));
      target.append(element("p", "hero-description", node.description || ""));
      target.append(renderNode(node.action, context));
      return target;
    }
    case "text":
      return element("div", `text text-${node.variant || "body"}`, node.value || "");
    case "badge":
      return element("span", `badge badge-${node.tone || "muted"}`, node.value || "");
    case "button":
      return renderButton(node, context);
    case "form":
      return renderForm(node);
    case "checkbox":
      return renderCheckbox(node, context);
    case "segmented":
      return renderSegmented(node, context);
    case "tabs":
      return renderTabs(node, context);
    case "table":
      return renderTable(node);
    case "copy":
      return renderCopy(node);
    case "select":
      return renderSelect(node);
    case "status": {
      const target = element("footer", `status status-${node.tone || "muted"}`);
      target.append(element("span", "status-message", node.value || ""));
      if (node.badge) target.append(renderNode(node.badge, context));
      return target;
    }
    default:
      return element("div", "render-error", `Неизвестный компонент: ${node.type || "undefined"}`);
  }
}

function renderForm(node) {
  const initial = structuredClone(node.initial || {});
  state.forms.set(node.id, { initial, values: structuredClone(initial) });

  const target = element("div", "form");
  const fields = element("div", "form-fields");
  childrenInto(fields, node.children, { formId: node.id });
  target.append(fields);
  if (node.submit) target.append(renderButton(node.submit, { formId: node.id, submit: true }));
  return target;
}

function renderCheckbox(node, context) {
  const form = state.forms.get(context.formId);
  const label = element("label", `checkbox${node.disabled ? " disabled" : ""}`);
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = Boolean(form?.values[node.name]);
  input.disabled = Boolean(node.disabled);
  input.addEventListener("change", () => {
    if (!form) return;
    form.values[node.name] = input.checked;
    updateFormState(context.formId);
  });
  label.append(input, element("span", "checkbox-box"), element("span", "checkbox-label", node.label || node.name));
  return label;
}

function renderButton(node, context) {
  const button = element("button", `button button-${node.variant || "secondary"}`, node.label || "Выполнить");
  button.type = "button";
  button.dataset.label = node.label || "Выполнить";
  button.dataset.pendingLabel = node.pendingLabel || "Выполнение...";
  button.dataset.baseDisabled = node.disabled ? "true" : "false";
  if (context.submit) {
    button.dataset.formSubmit = context.formId;
    button.disabled = true;
  } else {
    button.disabled = Boolean(node.disabled);
  }
  button.addEventListener("click", () => {
    const payload = context.formId
      ? state.forms.get(context.formId)?.values || {}
      : node.payload || null;
    dispatch(node.action, payload, button);
  });
  return button;
}

function renderSegmented(node, context) {
  const target = element("div", "segmented");
  for (const option of node.options || []) {
    const selected = option.value === node.value;
    target.append(renderButton({
      type: "button",
      label: option.label,
      action: node.action,
      payload: { value: option.value },
      variant: selected ? "segment-active" : "segment",
      disabled: Boolean(node.disabled || selected),
    }, context));
  }
  return target;
}

function renderTabs(node, context) {
  const target = element("section", "tabs");
  const navigation = element("div", "tab-navigation");
  const panel = element("div", "tab-panel");
  const tabs = node.tabs || [];

  function activate(index) {
    for (const [buttonIndex, button] of [...navigation.children].entries()) {
      button.classList.toggle("active", buttonIndex === index);
      button.setAttribute("aria-selected", String(buttonIndex === index));
    }
    panel.replaceChildren(renderNode(tabs[index]?.content, context));
  }

  tabs.forEach((tab, index) => {
    const button = element("button", "tab-button", tab.label || `Вкладка ${index + 1}`);
    button.type = "button";
    button.setAttribute("role", "tab");
    button.addEventListener("click", () => activate(index));
    navigation.append(button);
  });
  target.append(navigation, panel);
  if (tabs.length) activate(0);
  return target;
}

function renderTable(node) {
  const wrapper = element("div", "table-wrapper");
  const table = element("table", "data-table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const column of node.columns || []) {
    headRow.append(element("th", "", column.label || column.key));
  }
  head.append(headRow);
  table.append(head);

  const body = document.createElement("tbody");
  const rows = node.rows || [];
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = element("td", "table-empty", node.empty || "Нет данных");
    cell.colSpan = Math.max(1, (node.columns || []).length);
    row.append(cell);
    body.append(row);
  }
  for (const item of rows) {
    const row = document.createElement("tr");
    for (const column of node.columns || []) {
      const value = item[column.key];
      row.append(element("td", column.key === "packet" ? "packet-cell" : "", value == null ? "—" : String(value)));
    }
    body.append(row);
  }
  table.append(body);
  wrapper.append(table);
  return wrapper;
}

function renderCopy(node) {
  const target = element("div", "copy-field");
  target.append(element("div", "text text-label", node.label || "Значение"));
  const row = element("div", "copy-row");
  row.append(element("code", "copy-value", node.value || ""));
  const button = element("button", "copy-button", "Копировать");
  button.type = "button";
  button.addEventListener("click", async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(node.value || "");
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = node.value || "";
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
      button.textContent = "Скопировано";
      window.setTimeout(() => { button.textContent = "Копировать"; }, 1200);
    } catch (error) {
      button.textContent = "Ошибка";
    }
  });
  row.append(button);
  target.append(row);
  return target;
}

function renderSelect(node) {
  const select = element("select", "select-control");
  select.setAttribute("aria-label", node.ariaLabel || "Select");
  for (const option of node.options || []) {
    const item = element("option", "", option.label || option.value);
    item.value = option.value;
    item.selected = option.value === node.value;
    select.append(item);
  }
  select.addEventListener("change", async () => {
    localStorage.setItem("falc.locale", select.value);
    select.disabled = true;
    await dispatch(node.action, { value: select.value }, null);
    select.disabled = false;
  });
  return select;
}

function updateFormState(formId) {
  const form = state.forms.get(formId);
  const submit = document.querySelector(`[data-form-submit="${CSS.escape(formId)}"]`);
  if (!form || !submit) return;
  const dirty = JSON.stringify(form.initial) !== JSON.stringify(form.values);
  submit.disabled = state.busy || submit.dataset.baseDisabled === "true" || !dirty;
}

function setBusy(busy, sourceButton) {
  state.busy = busy;
  for (const button of document.querySelectorAll("button[data-label]")) {
    button.disabled = busy || button.dataset.baseDisabled === "true";
    button.textContent = busy && button === sourceButton
      ? button.dataset.pendingLabel
      : button.dataset.label;
  }
  if (!busy) {
    for (const formId of state.forms.keys()) updateFormState(formId);
  }
  document.body.classList.toggle("busy", busy);
}

async function dispatch(action, payload, sourceButton) {
  if (state.busy || !action) return;
  setBusy(true, sourceButton);
  try {
    const nextDocument = await window.pywebview.api.dispatch(action, payload);
    renderDocument(nextDocument);
  } catch (error) {
    showRuntimeError(String(error));
  } finally {
    setBusy(false, null);
  }
}

async function synchronizeDocument() {
  if (state.busy || state.polling || !window.pywebview?.api || !state.document) return;
  state.polling = true;
  try {
    const revision = await window.pywebview.api.get_revision();
    if (revision !== state.document.revision) {
      renderDocument(await window.pywebview.api.get_ui());
    }
  } catch (error) {
    showRuntimeError(String(error));
  } finally {
    state.polling = false;
  }
}

function renderDocument(documentModel) {
  state.document = documentModel;
  if (documentModel.locale) {
    localStorage.setItem("falc.locale", documentModel.locale);
    document.documentElement.lang = documentModel.locale;
  }
  state.forms.clear();
  const shell = element("div", "shell");
  shell.append(
    renderNode(documentModel.header),
    element("main", "content"),
    renderNode(documentModel.footer),
  );
  shell.querySelector("main").append(renderNode(documentModel.content));
  app.replaceChildren(shell);
}

function showRuntimeError(message) {
  const status = document.querySelector(".status");
  if (status) {
    status.className = "status status-error";
    status.textContent = `Ошибка renderer: ${message}`;
  }
}

window.addEventListener("pywebviewready", async () => {
  try {
    startupLocale = await window.pywebview.api.get_language();
    localStorage.setItem("falc.locale", startupLocale);
    setStartupStatus(startupMessages[startupLocale].data, 3);
    const documentModel = await window.pywebview.api.get_ui();
    const remaining = minimumStartupDuration - (performance.now() - startupStartedAt);
    if (remaining > 0) await wait(remaining);
    setStartupStatus(startupMessages[startupLocale].ready, 4);
    await wait(120);
    const startup = document.querySelector(".startup");
    if (startup) {
      startup.classList.add("startup-exit");
      await wait(280);
    }
    renderDocument(documentModel);
    window.setInterval(synchronizeDocument, 750);
  } catch (error) {
    const startup = document.querySelector(".startup");
    const status = document.querySelector("#startup-status");
    if (startup && status) {
      startup.classList.add("startup-error");
      status.textContent = `${startupMessages[startupLocale].error}: ${error}`;
    } else {
      app.replaceChildren(element("div", "boot error", `Не удалось загрузить UI: ${error}`));
    }
  }
});
