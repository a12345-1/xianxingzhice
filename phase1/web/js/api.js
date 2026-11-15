/* 接口封装 —— 严格对应 docs/接口数据字段说明.md */
async function request(url, options = {}) {
  const opt = { headers: { "Content-Type": "application/json" }, ...options };
  const res = await fetch(url, opt);
  if (!res.ok) {
    let msg = `请求失败（${res.status}）`;
    try {
      const body = await res.json();
      const d = body.detail || body;
      if (Array.isArray(d)) msg = d.map((x) => x.msg || String(x)).join("；");
      else msg = d.message || d.detail || msg;
    } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

const API = {
  health: () => request("/api/health"),
  generate: (raw_text, day_count, budget_limit, city) =>
    request("/api/trips/generate", {
      method: "POST",
      body: JSON.stringify({ raw_text, day_count, budget_limit, city: city || null }),
    }),
  get: (tripId) => request(`/api/trips/${tripId}`),
  patch: (tripId, itemId, action, patch = {}) =>
    request(`/api/trips/${tripId}/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ action, patch }),
    }),
  save: (tripId) => request(`/api/trips/${tripId}/save`, { method: "POST" }),
  list: () => request("/api/trips"),
  detail: (tripId, itemId) => request(`/api/trips/${tripId}/items/${itemId}`),
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
