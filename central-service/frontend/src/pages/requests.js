import { request } from "../api/http.js";
import { requestFilters, requestStatuses } from "../components/filters.js";
import { element, timestamp } from "../components/monitoring.js";
import { recordTable } from "../components/recordTable.js";

function action(label, handler) {
  const button = element("button", "monitor-button", label);
  button.type = "button";
  button.addEventListener("click", () => {
    if (button.getAttribute("aria-disabled") !== "true") handler();
  });
  return button;
}

function selectedFilters(form) {
  const params = new URLSearchParams();
  for (const [key, text] of new FormData(form)) {
    if (text.trim()) params.set(key, text.trim());
  }
  return params;
}

function selectionLabel(filters, form) {
  const parts = [];
  for (const [key, value] of filters) {
    const field = form.elements.namedItem(key);
    if (field instanceof HTMLSelectElement) {
      parts.push(Array.from(field.options).find(option => option.value === value)?.text ?? value);
    } else if (key === "q") {
      parts.push("поиск «" + value + "»");
    } else {
      const date = value.split("-").reverse().join(".");
      parts.push((key === "date_from" ? "с " : "по ") + date + " МСК");
    }
  }
  return parts.join(" · ") || "все заявки";
}

function requestRows(items) {
  const rows = document.createDocumentFragment();
  for (const item of items) {
    const row = element("tr");
    const number = element("th", "request-number", "№" + item.id);
    number.scope = "row";
    row.append(number);
    row.insertCell().textContent = item.substation_name;
    row.insertCell().textContent = item.responsible;
    row.insertCell().append(timestamp(item.valid_from));
    row.insertCell().append(timestamp(item.valid_to));
    const status = element("span", "status-badge", requestStatuses[item.status] ?? item.status);
    status.dataset.status = item.status;
    row.insertCell().append(status);
    rows.append(row);
  }
  return rows;
}

function requestsPage() {
  const view = element("div", "requests-page");
  const search = element("search");
  const form = requestFilters();
  search.append(form);
  const fields = form.elements;
  const catalogError = element("p", "request-catalog-error");
  catalogError.setAttribute("role", "status");
  const catalogRetry = action("Повторить загрузку подстанций", loadStations);
  catalogRetry.hidden = true;
  const catalogFeedback = element("div", "request-feedback");
  catalogFeedback.append(catalogError, catalogRetry);

  const progress = element("span");
  const message = element("span");
  message.id = "request-list-feedback";
  message.setAttribute("role", "status");
  const retry = action("Повторить запрос", () => load(failedPage));
  retry.hidden = true;
  const feedback = element("div", "request-feedback");
  feedback.append(progress, message, retry);
  const pane = element("div", "requests-pane");
  const region = element("div", "monitor-table-scroll");
  region.tabIndex = 0;
  region.setAttribute("role", "region");
  region.setAttribute("aria-labelledby", "request-table-title");
  const table = recordTable(["Номер", "Подстанция", "Ответственный", "Начало действия", "Окончание действия", "Статус"]);
  const caption = table.createCaption();
  caption.id = "request-table-title";
  caption.className = "request-caption";
  caption.textContent = "Список заявок";
  const empty = element("p", "monitor-empty");
  empty.setAttribute("role", "status");
  empty.tabIndex = -1;
  empty.hidden = true;
  region.append(table);
  const pager = element("div", "monitor-pager");
  const pageLabel = element("span", "monitor-secondary");
  const back = action("Назад", () => load(displayed.page - 1));
  const next = action("Далее", () => load(displayed.page + 1));
  pager.append(pageLabel, back, next);
  pager.hidden = true;
  pane.append(region, empty, pager);
  const fetchedAt = element("p", "request-timestamp monitor-secondary");
  view.append(search, catalogFeedback, feedback, pane, fetchedAt);

  const lifetime = new AbortController();
  let currentLoad;
  let typingTimer;
  let displayed;
  let failedPage = 1;

  function updatePager(busy) {
    if (busy) {
      // Native disabled would drop keyboard focus during every page request.
      for (const control of [back, next]) control.setAttribute("aria-disabled", "true");
      return;
    }
    const focused = document.activeElement;
    const differentFilters = displayed?.filters.toString() !== selectedFilters(form).toString();
    for (const control of [back, next]) control.removeAttribute("aria-disabled");
    back.disabled = differentFilters || !(displayed?.page > 1);
    next.disabled = differentFilters || !displayed?.hasMore;
    pager.hidden = !displayed || (displayed.page === 1 && !displayed.hasMore);
    if ((focused === back || focused === next) && (focused.disabled || pager.hidden)) {
      const available = [back, next].find(control => !control.disabled && !pager.hidden);
      (available ?? (region.hidden ? empty : region)).focus({ preventScroll: true });
    }
  }

  function previousRowsNote() {
    if (!displayed) return "";
    return " Сохранена выборка «" + selectionLabel(displayed.filters, form) + "», стр. " + displayed.page + ".";
  }

  async function loadStations() {
    catalogRetry.hidden = true;
    catalogError.textContent = "";
    try {
      const signal = AbortSignal.any([lifetime.signal, AbortSignal.timeout(15000)]);
      const response = await request("catalog/equipment", { signal, cache: "no-store" });
      const { items } = await response.json();
      if (lifetime.signal.aborted) return;
      for (const station of items) fields.substation_id.add(new Option(station.name, station.id));
    } catch {
      if (lifetime.signal.aborted) return;
      catalogError.textContent = "Не удалось загрузить список подстанций.";
      catalogRetry.hidden = false;
    }
  }

  function prepare() {
    clearTimeout(typingTimer);
    currentLoad?.abort();
    if (document.activeElement === retry) retry.setAttribute("aria-disabled", "true");
    else retry.hidden = true;
    updatePager(true);
    const { date_from: start, date_to: end } = fields;
    const reversed = start.value && end.value && start.value > end.value;
    for (const field of [start, end]) {
      const invalid = field.validity.badInput || (field === end && reversed);
      field.setAttribute("aria-invalid", invalid ? "true" : "false");
      if (invalid) field.setAttribute("aria-describedby", message.id);
      else field.removeAttribute("aria-describedby");
    }
    let error = "";
    if (start.validity.badInput || end.validity.badInput) error = "Введите день, месяц и год полностью.";
    else if (reversed) error = "Дата окончания периода должна быть не раньше даты начала.";
    message.textContent = error ? error + previousRowsNote() : "";
    progress.textContent = error ? "" : "Загружаем заявки…";
    pane.setAttribute("aria-busy", error ? "false" : "true");
    return !error;
  }

  async function load(page = 1) {
    if (!prepare()) return;
    const filters = selectedFilters(form);
    const params = new URLSearchParams(filters);
    params.set("page", page);
    params.set("per_page", "10");
    const controller = new AbortController();
    currentLoad = controller;
    try {
      const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]);
      const response = await request("requests?" + params, { signal, cache: "no-store" });
      const result = await response.json();
      if (controller.signal.aborted) return;
      table.tBodies[0].replaceChildren(requestRows(result.items));
      displayed = { page: result.page, hasMore: result.has_more, filters };
      region.hidden = !result.items.length;
      empty.hidden = !region.hidden;
      empty.textContent = filters.size ? "По выбранным фильтрам заявок нет." : "Заявок нет.";
      pageLabel.textContent = "Страница " + result.page;
      fetchedAt.replaceChildren("Данные получены ", timestamp(new Date().toISOString()));
      message.textContent = "";
      const focusFromRetry = document.activeElement === retry;
      retry.hidden = true;
      if (focusFromRetry) (region.hidden ? empty : region).focus({ preventScroll: true });
    } catch {
      if (controller.signal.aborted) return;
      failedPage = page;
      message.textContent = "Не удалось загрузить заявки." + previousRowsNote();
      retry.removeAttribute("aria-disabled");
      retry.hidden = false;
    } finally {
      if (!controller.signal.aborted) {
        progress.textContent = "";
        pane.setAttribute("aria-busy", "false");
        updatePager(false);
      }
    }
  }

  function scheduleLoad() {
    if (prepare()) typingTimer = setTimeout(() => load(), 250);
  }
  fields.q.addEventListener("input", event => { if (!event.isComposing) scheduleLoad(); });
  fields.q.addEventListener("compositionend", scheduleLoad);
  for (const field of [fields.date_from, fields.date_to]) {
    let value = field.value;
    let incomplete = field.validity.badInput;
    function dateEdited() {
      if (field.value === value && field.validity.badInput === incomplete) return;
      value = field.value;
      incomplete = field.validity.badInput;
      scheduleLoad();
    }
    // Segment edits can change badInput while the native control's value stays empty.
    for (const event of ["input", "change", "keyup", "blur"]) field.addEventListener(event, dateEdited);
  }
  form.addEventListener("change", event => { if (event.target instanceof HTMLSelectElement) load(); });
  form.addEventListener("submit", event => { event.preventDefault(); load(); });
  loadStations();
  load();
  return { view, dispose() {
    clearTimeout(typingTimer);
    currentLoad?.abort();
    lifetime.abort();
  } };
}

let active;
export const requests = {
  title: "Заявки",
  render() {
    this.dispose();
    active = requestsPage();
    return active.view;
  },
  dispose() { active?.dispose(); active = undefined; },
};
