/* 通用：请求封装 + 轻提示 */
async function request(url, options = {}) {
  const opt = { headers: { "Content-Type": "application/json" }, ...options };
  const res = await fetch(url, opt);
  if (!res.ok) {
    let msg = res.status + "";
    try {
      const body = await res.json();
      msg = body.detail || JSON.stringify(body);
    } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

const API = {
  health: () => request("/api/health"),
  parse: (text) => request("/api/parse", { method: "POST", body: JSON.stringify({ text }) }),
  create: (need) => request("/api/trips", { method: "POST", body: JSON.stringify({ need }) }),
  get: (id) => request(`/api/trips/${id}`),
  patchItem: (id, iid, body) => request(`/api/trips/${id}/items/${iid}`, { method: "PATCH", body: JSON.stringify(body) }),
  delItem: (id, iid) => request(`/api/trips/${id}/items/${iid}`, { method: "DELETE" }),
  swap: (id, iid) => request(`/api/trips/${id}/items/${iid}/swap`, { method: "POST" }),
  move: (id, iid, direction) => request(`/api/trips/${id}/items/${iid}/move`, { method: "POST", body: JSON.stringify({ direction }) }),
  regenDay: (id, day) => request(`/api/trips/${id}/days/${day}/regenerate`, { method: "POST" }),
  regenAll: (id, avoid) => request(`/api/trips/${id}/regenerate`, { method: "POST", body: JSON.stringify({ avoid }) }),
  members: (id, members) => request(`/api/trips/${id}/members`, { method: "POST", body: JSON.stringify({ members }) }),
  share: (id) => request(`/api/trips/${id}/share`, { method: "POST" }),
};

let toastTimer = null;
function toast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 1800);
}

function qs(name) {
  return new URLSearchParams(location.search).get(name);
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
