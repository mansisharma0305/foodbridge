/* Renders every <canvas data-chart="bar|line|doughnut" data-source="jsonScriptId">.
   Chart data is passed as JSON in a <script type="application/json"> block (CSP friendly). */
(function () {
  var PALETTE = ["#2e7d32", "#66bb6a", "#a5d6a7", "#f9a825", "#26a69a", "#8d6e63", "#78909c", "#c0ca33"];

  document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
    var holder = canvas.closest(".card-body") || canvas.parentElement;
    var fallback = holder ? holder.querySelector(".chart-fallback") : null;
    function showFallback() {
      canvas.style.display = "none";
      if (fallback) fallback.hidden = false;
    }
    var source = document.getElementById(canvas.getAttribute("data-source"));
    if (typeof Chart === "undefined" || !source) { showFallback(); return; }

    var cfg, type = canvas.getAttribute("data-chart");
    try { cfg = JSON.parse(source.textContent); } catch (e) { showFallback(); return; }

    var datasets = cfg.datasets.map(function (ds, i) {
      return Object.assign({
        backgroundColor: type === "doughnut" ? PALETTE : (type === "line" ? "rgba(46,125,50,.15)" : PALETTE[i % PALETTE.length]),
        borderColor: PALETTE[i % PALETTE.length],
        borderWidth: type === "line" ? 3 : 0,
        borderRadius: type === "bar" ? 6 : 0,
        fill: type === "line",
        tension: 0.3
      }, ds);
    });

    new Chart(canvas, {
      type: type,
      data: { labels: cfg.labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: type === "doughnut" || datasets.length > 1 } },
        scales: type === "doughnut" ? {} : { y: { beginAtZero: true, ticks: { precision: 0 } } }
      }
    });
  });
})();
