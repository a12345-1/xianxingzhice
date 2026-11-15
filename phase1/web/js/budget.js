/* 预算页 */
const tripId = qs("trip");
document.getElementById("back").href = `/plan.html?trip=${tripId}`;

(async () => {
  try {
    const trip = await API.get(tripId);
    document.getElementById("title").textContent = trip.summary.title;
    renderBudget(document.getElementById("budget"), trip.budget);
  } catch (e) {
    toast(e.message);
  }
})();
