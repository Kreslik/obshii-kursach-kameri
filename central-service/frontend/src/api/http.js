// Ресурс задаётся относительно /api/v1/, например «alerts».
export async function request(resource, { token, headers, ...options } = {}) {
  const requestHeaders = new Headers(headers);
  if (token) requestHeaders.set("Authorization", "Bearer " + token);
  const response = await fetch("/api/v1/" + resource, { ...options, headers: requestHeaders });
  if (!response.ok) {
    if (response.status === 401 && !resource.startsWith("auth/") && !options.signal?.aborted) {
      window.dispatchEvent(new Event("session-expired"));
    }
    const error = new Error("Код ошибки HTTP: " + response.status);
    error.status = response.status;
    throw error;
  }
  return response;
}

export async function getCurrentSession(cancelSignal) {
  const deadline = AbortSignal.timeout(10000);
  const signal = cancelSignal ? AbortSignal.any([cancelSignal, deadline]) : deadline;
  const response = await request("auth/session", {signal});
  return response.json();
}
