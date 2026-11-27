import { getCurrentSession } from "./http.js";

export function startAlertStream({onReady, onReconnect, onAlert, onUpdate}) {
  const url = new URL("/ws/alerts", location.href);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const lifetime = new AbortController();
  let socket;
  let timer;
  let delay = 500;

  function scheduleRetry() {
    if (lifetime.signal.aborted) return;
    onReconnect();
    timer = setTimeout(retry, delay);
    delay = Math.min(delay * 2, 10000);
  }

  async function retry() {
    if (lifetime.signal.aborted) return;
    try {
      // Браузер скрывает HTTP-статус отказа при открытии WebSocket.
      await getCurrentSession(lifetime.signal);
    } catch (error) {
      if (error.status === 401 && !lifetime.signal.aborted) {
        window.dispatchEvent(new Event("session-expired"));
        return;
      }
      scheduleRetry();
      return;
    }
    if (!lifetime.signal.aborted) connect();
  }

  function connect() {
    socket = new WebSocket(url);
    socket.onmessage = ({data}) => {
      if (lifetime.signal.aborted) return;
      const event = JSON.parse(data);
      if (event.type === "ready") {
        delay = 500;
        onReady();
      } else if (event.type === "alert") {
        onAlert(event.id, event.substation_id);
      } else if (event.type === "update" || event.type === "sync") {
        onUpdate(event.substation_id);
      }
    };
    socket.onclose = scheduleRetry;
  }

  connect();
  return () => {
    lifetime.abort();
    clearTimeout(timer);
    socket.close();
  };
}
