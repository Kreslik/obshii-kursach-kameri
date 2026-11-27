export function recordTable(columns) {
  const table = document.createElement("table");
  const header = table.createTHead().insertRow();
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = column;
    header.append(cell);
  }
  table.createTBody();
  return table;
}
