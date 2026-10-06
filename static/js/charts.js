// hover, tap, and keyboard tooltips for every .status-chart on a page, used by the
// status page and the dashboard's server stats. each chart lists its points in data-points
(function () {
    // one tooltip for the whole page, fixed so card overflow can't clip it
    var tooltip = document.createElement("div");
    tooltip.className = "status-tooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    document.body.appendChild(tooltip);
    var activeChart = null;

    function pointsFor(chart) {
        if (!chart.statusPoints) {
            chart.statusPoints = JSON.parse(chart.getAttribute("data-points") || "[]");
        }
        return chart.statusPoints;
    }

    function show(chart, index) {
        var points = pointsFor(chart);
        if (!points.length) return;

        index = Math.max(0, Math.min(points.length - 1, index));
        var point = points[index];
        var x = points.length === 1 ? 50 : (index / (points.length - 1)) * 100;

        if (activeChart && activeChart !== chart) hide();
        activeChart = chart;
        chart.statusIndex = index;


        tooltip.textContent = "";
        var when = document.createElement("div");
        when.className = "status-tooltip-when";
        when.textContent = point.when;
        tooltip.appendChild(when);
        point.rows.forEach(function (row) {
            var line = document.createElement("div");
            var key = document.createElement("span");
            var label = document.createElement("span");
            var value = document.createElement("strong");
            line.className = "status-tooltip-row";
            key.className = "status-tooltip-key is-" + row[2];
            label.className = "status-tooltip-label";
            label.textContent = row[0];
            value.textContent = row[1];
            label.prepend(key);
            line.append(label, value);
            tooltip.appendChild(line);
        });
        tooltip.hidden = false;

        var rect = chart.getBoundingClientRect();
        var left = rect.left + (rect.width * x) / 100;
        tooltip.style.left = left + "px";
        tooltip.style.top = rect.top + (rect.height * point.y) / 100 + "px";

        // keep it on screen near the card edges, with the arrow still on the point
        var tipRect = tooltip.getBoundingClientRect();
        var shift = 0;
        if (tipRect.left < 8) {
            shift = 8 - tipRect.left;
        } else if (tipRect.right > window.innerWidth - 8) {
            shift = window.innerWidth - 8 - tipRect.right;
        }
        tooltip.style.left = left + shift + "px";
        tooltip.style.setProperty("--arrow-shift", -shift + "px");
    }

    function hide() {
        activeChart = null;
        tooltip.hidden = true;
    }

    function indexFromPointer(chart, event) {
        var points = pointsFor(chart);
        var rect = chart.getBoundingClientRect();
        var fraction = (event.clientX - rect.left) / rect.width;
        return Math.round(fraction * (points.length - 1));
    }

    function onPointer(event) {
        var chart = event.target.closest && event.target.closest(".status-chart");
        if (chart) show(chart, indexFromPointer(chart, event));
    }

    document.addEventListener("pointermove", onPointer);
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("pointerout", function (event) {
        var chart = event.target.closest && event.target.closest(".status-chart");
        if (chart && !chart.contains(event.relatedTarget) && document.activeElement !== chart) hide();
    });
    window.addEventListener("scroll", hide, { passive: true });

    document.addEventListener("focusin", function (event) {
        var chart = event.target.closest && event.target.closest(".status-chart");
        if (chart) show(chart, pointsFor(chart).length - 1);
    });
    document.addEventListener("focusout", function (event) {
        if (event.target === activeChart) hide();
    });
    document.addEventListener("keydown", function (event) {
        var chart = document.activeElement;
        if (!chart || !chart.classList.contains("status-chart")) return;
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            show(chart, (chart.statusIndex || 0) + (event.key === "ArrowLeft" ? -1 : 1));
        } else if (event.key === "Escape") {
            hide();
        }
    });

    // lets pages hold off on refreshing while someone is reading a tooltip
    window.melvinCharts = {
        isActive: function () {
            return activeChart !== null;
        }
    };
})();
