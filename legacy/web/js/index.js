/* 首页：一句话 → 需求确认 → 建行程 */
const TAGS = ["自然", "美食", "拍照", "人文", "夜景", "购物", "亲子"];
const AVOID = ["爬山", "人多", "早起", "长距离步行", "商业化"];

const state = { need: null, interests: [], avoid: [] };

function renderPickers() {
  const box0 = document.getElementById("pick-interests");
  const box1 = document.getElementById("pick-avoid");
  box0.innerHTML = TAGS.map((t) => `<button class="chip ${state.interests.includes(t) ? "on" : ""}" data-tag="${t}">${t}</button>`).join("");
  box1.innerHTML = AVOID.map((t) => `<button class="chip ${state.avoid.includes(t) ? "on" : ""}" data-tag="${t}">${t}</button>`).join("");

  box0.querySelectorAll(".chip").forEach((b) => b.onclick = () => toggle(state.interests, b.dataset.tag, 3, renderPickers));
  box1.querySelectorAll(".chip").forEach((b) => b.onclick = () => toggle(state.avoid, b.dataset.tag, 5, renderPickers));
}

function toggle(arr, tag, max, rerender) {
  const i = arr.indexOf(tag);
  if (i >= 0) arr.splice(i, 1);
  else {
    if (arr.length >= max) return toast(`最多选 ${max} 个`);
    arr.push(tag);
  }
  rerender();
}

async function onParse() {
  const text = document.getElementById("text").value.trim();
  if (!text) return toast("先说一句想去哪");
  const btn = document.getElementById("btn-parse");
  btn.disabled = true;
  btn.textContent = "正在理解…";
  try {
    const need = await API.parse(text);
    state.need = need;
    state.interests = [...(need.interests || [])];
    state.avoid = [...(need.avoid || [])];

    document.getElementById("step-input").style.display = "none";
    document.getElementById("step-confirm").style.display = "block";
    document.getElementById("f-city").value = need.city || "";
    document.getElementById("f-days").value = need.days || 2;
    document.getElementById("f-budget").value = typeof need.budget === "number" ? need.budget : "";
    document.getElementById("f-companions").value = need.companions || 1;
    document.getElementById("f-pace").value = need.pace || "normal";
    renderPickers();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) {
    toast("解析失败：" + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "帮我理解需求";
  }
}

async function onCreate() {
  const need = {
    ...state.need,
    city: document.getElementById("f-city").value.trim() || "长沙",
    days: Number(document.getElementById("f-days").value) || 2,
    budget: document.getElementById("f-budget").value ? Number(document.getElementById("f-budget").value) : null,
    companions: Number(document.getElementById("f-companions").value) || 1,
    pace: document.getElementById("f-pace").value,
    interests: state.interests,
    avoid: state.avoid,
  };
  const btn = document.getElementById("btn-create");
  btn.disabled = true;
  btn.textContent = "正在生成行程…";
  try {
    const trip = await API.create(need);
    location.href = `/plan.html?trip=${trip.id}`;
  } catch (e) {
    toast("生成失败：" + e.message);
    btn.disabled = false;
    btn.textContent = "生成行程";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-parse").onclick = onParse;
  document.getElementById("btn-create").onclick = onCreate;
  document.getElementById("btn-back").onclick = () => {
    document.getElementById("step-confirm").style.display = "none";
    document.getElementById("step-input").style.display = "block";
  };
  document.querySelectorAll("[data-fill]").forEach((b) => {
    b.onclick = () => { document.getElementById("text").value = b.dataset.fill; };
  });
  document.getElementById("text").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) onParse();
  });
});
