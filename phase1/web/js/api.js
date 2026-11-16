/* 接口封装 —— 严格对应 docs/接口数据字段说明.md */
async function request(url, options = {}) {
  const opt = { headers: { "Content-Type": "application/json" }, ...options };
  const res = await fetch(url, opt);
  if (!res.ok) {
    let msg = `请求失败（${res.status}）`;
    let detail = null;
    try {
      const body = await res.json();
      const d = body.detail || body;
      detail = d;
      if (Array.isArray(d)) msg = d.map((x) => x.msg || String(x)).join("；");
      else msg = d.message || d.detail || msg;
    } catch (e) { /* ignore */ }
    const err = new Error(msg);
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return res.json();
}

const API = {
  health: () => request("/api/health"),
  generate: (raw_text, day_count, budget_limit, city, force, daysFromUi, startDate) =>
    request("/api/trips/generate", {
      method: "POST",
      body: JSON.stringify({
        raw_text, day_count, budget_limit,
        city: city || null, force: !!force, days_from_ui: !!daysFromUi,
        start_date: startDate || null,
      }),
    }),
  get: (tripId) => request(`/api/trips/${tripId}`),
  patch: (tripId, itemId, action, patch = {}) =>
    request(`/api/trips/${tripId}/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ action, patch }),
    }),
  save: (tripId) => request(`/api/trips/${tripId}/save`, { method: "POST" }),
  list: (limit) => request(`/api/trips${limit ? "?limit=" + limit : ""}`),
  detail: (tripId, itemId) => request(`/api/trips/${tripId}/items/${itemId}`),
  candidates: (tripId, itemId) =>
    request(`/api/trips/${tripId}/items/${itemId}/candidates`),
  addCandidates: (tripId, day, type) =>
    request(`/api/trips/${tripId}/candidates?day=${day}&type=${encodeURIComponent(type)}`),
  addItem: (tripId, day, poiId) =>
    request(`/api/trips/${tripId}/items`, {
      method: "POST",
      body: JSON.stringify({ day_index: day, poi_id: poiId }),
    }),
  duplicate: (tripId) => request(`/api/trips/${tripId}/duplicate`, { method: "POST" }),
  remove: (tripId) => request(`/api/trips/${tripId}`, { method: "DELETE" }),
  reroute: (tripId, mode, item_id = null, extra_min = 60) =>
    request(`/api/trips/${tripId}/reroute`, {
      method: "POST",
      body: JSON.stringify({ mode, item_id, extra_min }),
    }),
  chat: (raw_text, answers = {}, known = {}) =>
    request("/api/chat", { method: "POST", body: JSON.stringify({ raw_text, answers, known }) }),
  cities: () => request("/api/cities"),
  refreshCity: (city) =>
    request(`/api/cities/${encodeURIComponent(city)}/refresh`, { method: "POST" }),
  command: (tripId, text) =>
    request(`/api/trips/${tripId}/command`, { method: "POST", body: JSON.stringify({ text }) }),
};

let toastTimer = null;
function toast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2000);
}

function qs(name) {
  return new URLSearchParams(location.search).get(name);
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/* 字段为 null 时统一显示「—」，不显示 null */
function orDash(v) {
  return (v === null || v === undefined || v === "") ? "—" : v;
}
