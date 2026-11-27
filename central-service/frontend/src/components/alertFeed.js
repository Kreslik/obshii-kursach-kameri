import { alertCard } from "./alertCard.js";
import { element, emptyState } from "./monitoring.js";

export function alertFeed(alerts) {
  const list = element("div", "alert-list");
  if (!alerts.length) list.append(emptyState("Тревог нет."));
  const seen = new Set();
  for (const alert of alerts) {
    if (seen.has(alert.id)) continue;
    seen.add(alert.id);
    list.append(alertCard(alert));
  }
  return list;
}
