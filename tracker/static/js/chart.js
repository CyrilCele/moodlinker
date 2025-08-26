const ctx = document.getElementById("moodChart").getContext("2d");
const chartConfig = {
    type: "line",
    data: { labels: [], datasets: [] },
    options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        stacked: false,
        plugins: { legend: { position: "top" } },
        scales: {
        y: { type: "linear", position: "left", min: 0, max: 5, ticks: { stepSize: 1 }, title: { display: true, text: "Mood (1-5)" } },
        y1: { type: "linear", position: "right", min: 0, max: 100, grid: { drawOnChartArea: false }, title: { display: true, text: "Completion %" } }
        }
    }
};

const moodChart = new Chart(ctx, chartConfig);

async function loadChart(view = "weekly") {
    const response = await fetch(`/api/chart-data/?view=${view}`);
    const json = await response.json();
    moodChart.data.labels = json.labels;
    // decorate styling
    json.datasets[0].borderColor = "#0dcaf0";
    json.datasets[0].backgroundColor = "rgba(13, 202, 240, 0.2)";
    json.datasets[0].tension = 0.35;
    json.datasets[1].borderColor = "#198754";
    json.datasets[1].backgroundColor = "rgba(25, 135, 84, 0.15)";
    json.datasets[1].tension = 0.35;
    moodChart.data.datasets = json.datasets;
    moodChart.update();
}

// initilal load
loadChart("weekly");

document.getElementById("updateChart").addEventListener("click", () => {
    const view = document.getElementById("view_mode").value;
    loadChart(view);
});