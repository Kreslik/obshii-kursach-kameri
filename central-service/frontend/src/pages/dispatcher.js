import { request } from "../api/http.js";
import { alertFeed } from "../components/alertFeed.js";
import { cameraGrid } from "../components/cameraGrid.js";
import { detectionTable } from "../components/detectionTable.js";
import { element, timestamp } from "../components/monitoring.js";

function button(label, action) {
  const control = element("button", "monitor-button", label);
  control.type = "button";
  control.addEventListener("click", action);
  return control;
}

function panel(id, title) {
  const section = element("section", "monitor-panel " + id);
  const heading = element("h2", "panel-heading", title);
  heading.id = id + "-heading";
  section.setAttribute("aria-labelledby", heading.id);
  const body = element("div", "panel-body");
  section.append(heading, body);
  return { section, body };
}

function pager(title, onChange) {
  let current = 1;
  const bar = element("div", "monitor-pager");
  const label = element("span", "monitor-secondary");
  const back = button("Назад", () => onChange(current - 1));
  const next = button("Далее", () => onChange(current + 1));
  back.setAttribute("aria-label", title + " · Предыдущая страница");
  next.setAttribute("aria-label", title + " · Следующая страница");
  bar.append(label, back, next);
  bar.hidden = true;
  return { bar, update(page) {
    current = page.page;
    label.textContent = "Страница " + current;
    back.disabled = current <= 1;
    next.disabled = !page.has_more;
    bar.hidden = current === 1 && !page.has_more;
  } };
}

function listUrl(resource, station, page) {
  const search = new URLSearchParams({ page, per_page: 10 });
  if (station) search.set("substation_id", station);
  return resource + "?" + search;
}

function updateAlerts(container, items) {
  const openIds = new Set(Array.from(container.querySelectorAll("details[open]"), row => row.dataset.alertId));
  const focusedId = container.contains(document.activeElement)
    ? document.activeElement.closest("details")?.dataset.alertId : null;
  const feed = alertFeed(items);
  let restoreFocus;
  for (const row of feed.querySelectorAll("details")) {
    row.open = openIds.has(row.dataset.alertId);
    if (row.dataset.alertId === focusedId) restoreFocus = row.querySelector("summary");
  }
  container.replaceChildren(feed);
  restoreFocus?.focus({ preventScroll: true });
}

function dashboard() {
  const view = element("div", "dispatcher");
  const toolbar = element("div", "monitor-toolbar");
  const filter = element("search", "station-filter");
  const select = element("select");
  select.id = "station-filter";
  select.add(new Option("Все подстанции", ""));
  const label = element("label", "", "Подстанция");
  label.htmlFor = select.id;
  filter.append(label, select);
  const connection = element("span", "stream-state");
  connection.setAttribute("role", "status");
  const fetchedAt = element("span", "monitor-secondary");
  const status = element("div", "monitor-status");
  status.append(connection, fetchedAt);
  toolbar.append(filter, status);
  const message = element("p", "monitor-message");
  message.setAttribute("role", "status");
  const retry = button("Повторить запрос", () => load(failedSelection ?? displayed));
  retry.hidden = true;
  const feedback = element("div", "monitor-feedback");
  feedback.append(message, retry);

  const alerts = panel("alerts", "Лента тревог");
  const equipment = panel("equipment", "Оборудование");
  const detections = panel("detections", "Последние детекции");
  const top = element("div", "monitor-grid");
  top.append(alerts.section, equipment.section);
  view.append(toolbar, feedback, top, detections.section);
  let displayed = { station: "", alerts: 1, detections: 1 };
  let hasSnapshot = false;
  let failedSelection;
  let loadingSelection;
  let catalogKey;
  let currentLoad;
  const queuedUpdates = new Map();
  let stopStream;
  let disposed = false;
  let alertIds = new Set();

  function changePage(resource, page) {
    load({ ...displayed, [resource]: page });
  }
  const alertPages = pager("Тревоги", page => changePage("alerts", page));
  const detectionPages = pager("Детекции", page => changePage("detections", page));
  alerts.section.append(alertPages.bar);
  detections.section.append(detectionPages.bar);

  select.addEventListener("change", () => {
    const target = { station: select.value, alerts: 1, detections: 1 };
    select.value = displayed.station;
    load(target);
  });

  function describe(selection) {
    const station = Array.from(select.options).find(option => option.value === selection.station);
    return (station?.text ?? "Подстанция №" + selection.station)
      + " · тревоги, стр. " + selection.alerts + " · детекции, стр. " + selection.detections;
  }

  function showFailure() {
    message.textContent = hasSnapshot
      ? "Не удалось загрузить «" + describe(failedSelection) + "». Показаны последние полученные данные."
      : "Не удалось загрузить данные центра. Проверьте соединение.";
    retry.hidden = false;
  }

  async function load(selection, background = false) {
    currentLoad?.abort();
    const controller = new AbortController();
    currentLoad = controller;
    loadingSelection = selection;
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]);
    const json = async url => (await request(url, { signal, cache: "no-store" })).json();
    if (!background) {
      failedSelection = undefined;
      message.textContent = hasSnapshot ? "Загружаем «" + describe(selection) + "»…" : "Загружаем данные центра…";
      retry.hidden = true;
    }
    try {
      const [catalog, alertPage, detectionPage] = await Promise.all([
        json("catalog/equipment"),
        json(listUrl("alerts", selection.station, selection.alerts)),
        json(listUrl("detections", selection.station, selection.detections)),
      ]);
      if (controller.signal.aborted) return;
      const stations = catalog.items;
      const key = JSON.stringify(stations.map(({id, name}) => [id, name]));
      if (catalogKey !== key) {
        select.replaceChildren(new Option("Все подстанции", ""),
          ...stations.map(station => new Option(station.name, station.id)));
        catalogKey = key;
      }
      select.value = selection.station;
      updateAlerts(alerts.body, alertPage.items);
      alertIds = new Set(alertPage.items.map(alert => String(alert.id)));
      const visibleStations = stations.filter(station => !selection.station || String(station.id) === selection.station);
      equipment.body.replaceChildren(cameraGrid(visibleStations));
      detections.body.replaceChildren(detectionTable(detectionPage.items));
      alertPages.update(alertPage);
      detectionPages.update(detectionPage);
      displayed = selection;
      hasSnapshot = true;
      fetchedAt.replaceChildren("Данные получены ", timestamp(new Date().toISOString()));
      if (failedSelection?.station === selection.station && failedSelection.alerts === selection.alerts
        && failedSelection.detections === selection.detections) failedSelection = undefined;
      if (failedSelection) showFailure();
      else {
        message.textContent = "";
        retry.hidden = true;
      }
    } catch {
      if (controller.signal.aborted) return;
      select.value = displayed.station;
      failedSelection ??= selection;
      showFailure();
    } finally {
      if (currentLoad === controller) {
        currentLoad = null;
        loadingSelection = undefined;
        const relevant = Array.from(queuedUpdates).filter(([station]) => matches(displayed, station));
        queuedUpdates.clear();
        if (relevant.length && !disposed) reconcile(null, relevant.some(([, first]) => first));
      }
    }
  }

  // Finish the current snapshot before fetching another one during an event burst.
  function matches(selection, stationId) {
    return selection && (!selection.station || stationId == null || selection.station === String(stationId));
  }

  function reconcile(stationId, firstAlertPage = false) {
    if (disposed) return;
    if (!matches(displayed, stationId) && !matches(loadingSelection, stationId)) return;
    if (currentLoad) {
      queuedUpdates.set(stationId, firstAlertPage || queuedUpdates.get(stationId));
      return;
    }
    load(firstAlertPage ? { ...displayed, alerts: 1 } : displayed, true);
  }

  load(displayed);
  return {
    view,
    attachStream(startStream) {
      stopStream?.();
      connection.textContent = "Подключение…";
      stopStream = startStream({
        onReady() {
          connection.textContent = "Связь установлена";
          connection.dataset.state = "online";
          reconcile(null, true);
        },
        onReconnect() {
          connection.textContent = "Переподключение…";
          connection.dataset.state = "offline";
        },
        onAlert(id, stationId) {
          if (!alertIds.has(String(id))) reconcile(stationId, true);
        },
        onUpdate(stationId) {
          reconcile(stationId);
        },
      });
    },
    dispose() {
      disposed = true;
      currentLoad?.abort();
      stopStream?.();
    },
  };
}

let active;
export const dispatcher = {
  title: "Панель диспетчера",
  render() {
    this.dispose();
    active = dashboard();
    return active.view;
  },
  attachStream(startStream) { active?.attachStream(startStream); },
  dispose() { active?.dispose(); active = undefined; },
};
