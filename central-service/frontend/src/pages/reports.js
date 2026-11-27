import { recordTable } from "../components/recordTable.js";

export const reports = {
  title: "Отчёты",
  render: () => recordTable(["Подстанция", "Тревоги за период", "Ложные срабатывания", "Доля ложных срабатываний"]),
};
