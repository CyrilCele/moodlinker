document.addEventListener("DOMContentLoaded", () => {
    const htmlElement = document.documentElement;
    const button = document.getElementById("theme-toggle");

    // Set default theme to dark
    if (!htmlElement.hasAttribute("data-bs-theme")) {
        htmlElement.setAttribute("data-bs-theme", "dark");
    }

    // Set button text based on current theme
    const currentTheme = htmlElement.getAttribute("data-bs-theme");
    button.textContent = currentTheme === "dark" ? "Light" : "Dark";

    // Toggle theme and update button text
    button.addEventListener("click", () => {
        const current = htmlElement.getAttribute("data-bs-theme");
        const next = current === "dark" ? "light" : "dark";
        htmlElement.setAttribute("data-bs-theme", next);
        button.textContent = next === "dark" ? "Light" : "Dark";
    });
});

// Show button only when scrolled down
window.onscroll = function () {
    const btn = document.getElementById("scrollBtn");
    if (document.body.scrollTop > 200 || document.documentElement.scrollTop > 200) {
        btn.style.display = "block";
    } else {
        btn.style.display = "none";
    }
};

// Smooth scroll to top
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}

// Real-time clock
function updateClock() {
    const now = new Date();
    let hours = now.getHours();
    let minutes = now.getMinutes();
    let seconds = now.getSeconds();

    hours = hours < 10 ? "0" + hours : hours;
    minutes = minutes < 10 ? "0" + minutes : minutes;
    seconds = seconds < 10 ? "0" + seconds : seconds;

    document.getElementById("clock").innerText = `${hours}:${minutes}:${seconds}`;
}

// Update clock every second
setInterval(updateClock, 1000);
updateClock();