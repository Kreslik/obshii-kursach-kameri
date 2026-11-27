import { element } from "./monitoring.js";

export const requestStatuses = {
  pending: "Ожидает подтверждения",
  active: "Активна",
  closed: "Закрыта",
  rejected: "Отклонена",
};

export function requestFilters() {
  const form = element("form", "request-filters");
  form.setAttribute("aria-label", "Фильтры заявок");
  const search = element("input");
  search.type = "search";
  search.placeholder = "Номер, подстанция или ответственный";
  const station = element("select");
  station.add(new Option("Все подстанции", ""));
  const status = element("select");
  status.add(new Option("Все статусы", ""));
  for (const [value, text] of Object.entries(requestStatuses)) status.add(new Option(text, value));
  const start = element("input");
  const end = element("input");
  start.type = end.type = "date";
  for (const [title, name, field] of [
    ["Поиск", "q", search], ["Подстанция", "substation_id", station], ["Статус", "status", status],
    ["Период с (МСК)", "date_from", start], ["Период по (МСК)", "date_to", end],
  ]) {
    field.name = name;
    const label = element("label", "", title);
    label.append(field);
    form.append(label);
  }
  return form;
}
