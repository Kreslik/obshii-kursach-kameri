import { element, emptyState, statusBadge, timestamp } from "./monitoring.js";

function equipmentRow(label, name, status) {
  const row = element("li", "equipment-row");
  const title = element("div", "equipment-name");
  title.append(element("small", "monitor-secondary", label), element("span", "", name));
  row.append(title, statusBadge(status));
  return row;
}

export function cameraGrid(stations) {
  const grid = element("div", "equipment-groups");
  if (!stations.length) grid.append(emptyState("Подстанций нет."));
  for (const station of stations) {
    const group = element("div", "equipment-group");
    group.append(element("h3", "", station.name));
    const list = element("ul");
    for (const node of station.nodes) {
      const row = equipmentRow("Узел " + node.id, node.name, node.status);
      const heartbeat = element("small", "heartbeat monitor-secondary");
      if (node.last_heartbeat_at) heartbeat.append("Последний heartbeat · ", timestamp(node.last_heartbeat_at));
      else heartbeat.textContent = "Heartbeat ещё не поступал";
      row.append(heartbeat);
      list.append(row);
    }
    for (const camera of station.cameras) {
      list.append(equipmentRow("Камера " + camera.camera_id, camera.name, camera.status));
    }
    group.append(list.childElementCount ? list : emptyState("Оборудование не зарегистрировано."));
    grid.append(group);
  }
  return grid;
}
