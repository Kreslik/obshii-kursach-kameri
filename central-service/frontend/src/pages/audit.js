import { recordTable } from "../components/recordTable.js";

export const audit = {
  title: "Журнал действий",
  render: () => recordTable(["Время", "Автор или узел", "IP-адрес", "Операция", "Объект"]),
};
