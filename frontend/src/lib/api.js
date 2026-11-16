const readError = async (response) => {
  try {
    const body = await response.json();
    return body.detail || JSON.stringify(body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
};

const request = async (path, options = {}, headers = {}) => {
  const response = await fetch(path, {
    ...options,
    headers: { "X-Tenant-ID": headers.tenantId, "X-User-ID": headers.userId, ...options.headers },
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
};

export const api = {
  health: () => fetch("/health").then((response) => response.json()),
  readiness: () => fetch("/ready").then(async (response) => {
    if (!response.ok) throw new Error(await readError(response));
    return response.json();
  }),
  createTender: ({ title, reference, files, headers }) => {
    const body = new FormData();
    body.append("title", title);
    if (reference) body.append("external_reference", reference);
    files.forEach((file) => body.append("files", file));
    return request("/v1/tenders", { method: "POST", body }, headers);
  },
  startRun: (tenderId, headers) => request(`/v1/tenders/${encodeURIComponent(tenderId)}/runs`, { method: "POST" }, headers),
  getRun: (threadId, headers) => request(`/v1/tenders/runs/${encodeURIComponent(threadId)}`, {}, headers),
  pauseRun: (threadId, headers) => request(`/v1/tenders/runs/${encodeURIComponent(threadId)}/pause`, { method: "POST" }, headers),
  resumeRun: (threadId, headers) => request(`/v1/tenders/runs/${encodeURIComponent(threadId)}/resume`, { method: "POST" }, headers),
  cancelRun: (threadId, headers) => request(`/v1/tenders/runs/${encodeURIComponent(threadId)}/cancel`, { method: "POST" }, headers),
  getReview: (threadId, headers) => request(`/v1/tenders/runs/${encodeURIComponent(threadId)}/review`, {}, headers),
  submitReview: (threadId, payload, headers) => request(`/v1/tenders/runs/${encodeURIComponent(threadId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, headers),
};
