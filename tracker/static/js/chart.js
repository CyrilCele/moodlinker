/**
 * chart.js
 * 
 * Loads analytics data from `/api/chart-data/?view=<view>` and renders it into a Chart.js line chart.
 * 
 * Expected server response JSON shape:
 * {
 *  labels: ["Monday", "Tuesday", ...],
 *  datasets: [
 *      { label: "Mood (weekly)", data: [3,4,2,...], yAxisID: "y" },
 *      { label: "Habit Completion %", data: [20,40,60,...], yAxisID: "y1" }
 *  ]
 * }
 * 
 * Assumptions:
 * - Chart.js is loaded and available globally as `Chart`
 * - An element with id "moodChart" exists (a <canvas>)
 * - The API returns valid JSON with `labels` and `datasets`
 */

/** @type {CanvasRenderingContext2D} Canvas 2D context for Chart.js */
const ctx = document.getElementById("moodChart").getContext("2d");

/** @type {import("chart.js").chartConfiguration} Base chart configuration */
const chartConfig = {
    type: "line",
    data: { labels: [], datasets: [] },
    options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        stacked: false,
        plugins: { legend: { position: "top" } },
        scales: {
            // left axis for mood scores (1-5)
            y: {
                type: "linear",
                position: "left",
                min: 0,
                max: 5,
                ticks: { stepSize: 1 },
                title: { display: true, text: "Mood (1-5)" }
            },
            // right axis for completion percentage (0-100)
            y1: {
                type: "linear",
                position: "right",
                min: 0,
                max: 100,
                grid: { drawOnChartArea: false }, // avoid cluttering background grid
                title: { display: true, text: "Completion %" }
            }
        }
    }
};

/** Create Chart.js instance once and reuse it (better performance than re-creating) */
const moodChart = new Chart(ctx, chartConfig);

/**
 * Fetch chart data from the server and update the Chart.js instance.
 * 
 * @param {string} [view="weekly"] - Which aggregation to request ("daily", "weekly", "monthly")
 * @returns {Promise<void>} Resolves when the chart has been updated. May reject on network/parse errors.
 * 
 * @throws {Error} If `fetch` fails or the response is not valid JSON; chart.update() may also throw if data invalid.
 */
async function loadChart(view = "weekly") {
    // Build endpoint URL (server expects a 'view' query param)
    const response = await fetch(`/api/chart-data/?view=${encodeURIComponent(view)}`);

    // NOTE: This code assumes response is OK. In production you may want to check response.ok
    const json = await response.json();

    // Replace labels for the chart
    moodChart.data.labels = json.labels;

    // ---------- Styling of datasets (presentation layer) ----------
    // The API provides the raw datasets; here we decorate with colors/tension for a nicer look.
    // IMPORTANT: we assume json.datasets[0] is the mood dataset and [1] is completion %.
    // If the API changes the ordering/number of datasets, this will throw or produce wrong styling.
    json.datasets[0].borderColor = "#0dcaf0";
    json.datasets[0].backgroundColor = "rgba(13, 202, 240, 0.2)";
    json.datasets[0].tension = 0.35;

    json.datasets[1].borderColor = "#198754";
    json.datasets[1].backgroundColor = "rgba(25, 135, 84, 0.15)";
    json.datasets[1].tension = 0.35;

    // Apply the datasets and request Chart.js to redraw
    moodChart.data.datasets = json.datasets;
    moodChart.update();
}

// initilal load with default view
loadChart("weekly");

// Wire up manual "update" button - pulls selected view from a select input with id="view_mode"
document.getElementById("updateChart").addEventListener("click", () => {
    const view = document.getElementById("view_mode").value;
    loadChart(view);
});