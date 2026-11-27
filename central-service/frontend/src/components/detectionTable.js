import { recordTable } from "./recordTable.js";
import { element, emptyState, timestamp } from "./monitoring.js";

export function detectionTable(detections) {
  if (!detections.length) return emptyState("Детекций нет.");
  const table = recordTable(["Время обнаружения", "Подстанция", "Камера", "Зона", "Результат обработки"]);
  table.setAttribute("aria-labelledby", "detections-heading");
  const region = element("div", "monitor-table-scroll");
  region.tabIndex = 0;
  region.setAttribute("role", "region");
  region.setAttribute("aria-labelledby", "detections-heading");
  for (const item of detections) {
    const row = table.tBodies[0].insertRow();
    row.insertCell().append(timestamp(item.detected_at));
    row.insertCell().textContent = item.substation_name;
    row.insertCell().textContent = "№" + item.camera_id + " · " + item.camera_name;
    row.insertCell().textContent = item.roi_name ?? "Не указана";
    const result = row.insertCell();
    if (item.alert_id != null) {
      result.textContent = "Тревога №" + item.alert_id;
      result.className = "detection-alert";
    } else if (item.matched_request_id != null) {
      result.textContent = "Заявка №" + item.matched_request_id;
    } else {
      result.textContent = "Без тревоги";
    }
  }
  region.append(table);
  return region;
}
