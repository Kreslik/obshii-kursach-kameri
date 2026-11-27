import { login } from "./pages/login.js";
import { dispatcher } from "./pages/dispatcher.js";
import { requests } from "./pages/requests.js";
import { admin } from "./pages/admin.js";
import { audit } from "./pages/audit.js";
import { reports } from "./pages/reports.js";
import { getCurrentSession, request } from "./api/http.js";
import { startAlertStream } from "./api/alertsSocket.js";

const pages = new Map([
  ["dispatcher", dispatcher], ["requests", requests], ["reports", reports],
  ["audit", audit], ["admin", admin],
]);
const nav = document.querySelector("nav");
const account = document.querySelector(".account");
const heading = document.querySelector("h1");
const content = document.querySelector("#page");
const shellError = document.querySelector("#shell-error");
let operator;
let current;

function show(page, ...args) {
  current?.dispose?.();
  current = page;
  document.title = page.title + " | Мониторинг подстанций";
  heading.textContent = page.title;
  content.replaceChildren(page.render(...args));
  shellError.textContent = "";
  heading.focus({preventScroll: true});
}

function navigate() {
  if (!operator) return;
  const id = location.hash.slice(1);
  const active = pages.has(id) && (id !== "admin" || operator.role === "admin") ? id : "dispatcher";
  nav.replaceChildren();
  for (const [key, page] of pages) {
    if (key === "admin" && operator.role !== "admin") continue;
    const link = document.createElement("a");
    link.href = "#" + key;
    link.textContent = page.title;
    if (active === key) link.setAttribute("aria-current", "page");
    nav.append(link);
  }
  show(pages.get(active));
  if (current === dispatcher) dispatcher.attachStream(startAlertStream);
}

function setOperator(user) {
  operator = user;
  document.body.classList.toggle("session-view", !user);
  nav.hidden = account.hidden = !user;
  document.querySelector("#operator").textContent = user?.name ?? "";
  history.replaceState(null, "", user ? "#dispatcher" : location.pathname + location.search);
  if (user) navigate();
  else show(login, setOperator);
}

async function restoreSession() {
  try {
    setOperator(await getCurrentSession());
  } catch (error) {
    if (error.status === 401) return setOperator(null);
    heading.textContent = "Не удалось проверить сессию";
    const retry = document.createElement("button");
    retry.textContent = "Повторить";
    retry.addEventListener("click", () => {
      retry.disabled = true;
      restoreSession();
    });
    content.replaceChildren(retry);
  }
}

document.querySelector("#logout").addEventListener("click", async () => {
  try {
    await request("auth/logout", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
    });
    setOperator(null);
  } catch {
    shellError.textContent = "Не удалось завершить сессию. Попробуйте ещё раз.";
  }
});
window.addEventListener("session-expired", () => { if (operator) setOperator(null); });
window.addEventListener("hashchange", navigate);
window.addEventListener("pageshow", event => { if (event.persisted) location.reload(); });
restoreSession();
