export const admin = {
  title: "Администрирование",
  render() {
    const sections = document.createElement("ul");
    for (const name of ["Пользователи и роли", "Подстанции и узлы", "Камеры и зоны", "Типы заявок"]) {
      const item = document.createElement("li");
      item.textContent = name;
      sections.append(item);
    }
    return sections;
  },
};
