import { request } from "../api/http.js";

export const login = {
  title: "Вход в панель диспетчера",
  render(onSuccess) {
    const form = document.querySelector("#login-form").content.firstElementChild.cloneNode(true);
    const error = form.querySelector(".form-error");
    const button = form.querySelector("button");
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (button.disabled) return;
      error.textContent = "";
      button.disabled = true;
      button.textContent = "Входим…";
      try {
        const response = await request("auth/login", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify(Object.fromEntries(new FormData(form))),
        });
        onSuccess(await response.json());
      } catch (failure) {
        error.textContent = failure.status === 401 ? "Не удалось войти. Проверьте логин и пароль."
          : "Сервис недоступен. Попробуйте войти ещё раз.";
      } finally {
        button.disabled = false;
        button.textContent = "Войти";
      }
    });
    return form;
  },
};
