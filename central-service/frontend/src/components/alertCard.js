import { element, statusBadge, timestamp } from "./monitoring.js";

export function alertCard(alert) {
  const card = element("details", "alert-card");
  card.dataset.alertId = alert.id;
  card.dataset.status = alert.status;
  const row = element("summary", "alert-summary");
  const number = element("strong", "alert-number", "Тревога №" + alert.id);
  const site = element("span", "alert-location");
  site.append(element("strong", "", alert.substation_name),
    element("span", "monitor-secondary", "Камера " + alert.camera_id + " · " + alert.camera_name));
  const when = element("span", "alert-time");
  when.append(element("small", "monitor-secondary", "Время обнаружения"), timestamp(alert.detected_at));
  row.append(number, statusBadge(alert.status), site, when);

  const metadata = element("dl", "alert-metadata");
  for (const [label, value] of [
    ["Время обнаружения", timestamp(alert.detected_at)],
    ["Время создания тревоги в центре", timestamp(alert.created_at)],
    ["Связанная детекция", "№" + alert.detection_id],
    ["UUID события", alert.event_uuid],
  ]) {
    const pair = element("div");
    const definition = element("dd");
    definition.append(value);
    pair.append(element("dt", "", label), definition);
    metadata.append(pair);
  }
  card.append(row, metadata);
  return card;
}
