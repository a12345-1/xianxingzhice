/* 贴士页 */
const tripId = qs("trip");
document.getElementById("back").href = `/plan.html?trip=${tripId}`;

(async () => {
  try {
    const trip = await API.get(tripId);
    document.getElementById("title").textContent = trip.summary.title;
    renderTips(document.getElementById("tips"), trip.tips);
  } catch (e) {
    toast(e.message);
  }
})();
