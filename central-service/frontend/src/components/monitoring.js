const clock = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow", day: "2-digit", month: "2-digit", year: "numeric",
  hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "short",
});

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function timestamp(value) {
  const time = element("time", "monitor-time", clock.format(new Date(value)));
  time.dateTime = value;
  return time;
}

const labels = {
  new: "Новая", confirmed: "Подтверждена", false_positive: "Ложная",
  linked: "Связана с заявкой", online: "В сети", offline: "Нет связи",
};

export function statusBadge(status) {
  const badge = element("span", "status-badge", labels[status] ?? status);
  badge.dataset.status = status;
  return badge;
}

export function emptyState(text) {
  return element("p", "monitor-empty", text);
}
