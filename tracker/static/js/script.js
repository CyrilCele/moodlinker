/**
 * UI helpers for:
 * - toggling a Bootstrap data-bs-theme attribute (dark / light),
 * - showing a "scroll to top" button when the page is scrolled,
 * - smooth scrolling to top, and
 * - a real-time digital clock updated every second.
 * 
 * Notes:
 * - This file assumes the following DOM elements exist:
 *      * #theme-toggle -> a button to toggle theme
 *      * #scrollBtn    -> a button to scroll to top
 *      * #clock        -> an element to display HH:MM:SS
 * - If any of these elements are missing the current code will throw a runtime
 *   error when attempting to access properties (see inline comments).
 * - See the "Potential improvements" section below for defensive patterns.
 */

/**
 * Initialize the toggle button and default theme once DOM is ready.
 * 
 * - Set default `data-bs-theme="dark"` on <html> if not already present.
 * - Updates the theme toggle button label to reflect the *opposite* theme,
 *   because button text indicates the action (e.g. "Light" when in dark mode).
 * 
 * No parameters
 * @returns {void}
 */

document.addEventListener("DOMContentLoaded", () => {
    // document.documentElement is the <html> element
    const htmlElement = document.documentElement;

    // Button that toggles the theme. ASSUMPTION: element exists in DOM.
    const button = document.getElementById("theme-toggle");

    // --- Default theme setup ---
    // If no theme attribute present, choose dark by default.
    // Note: uses HTML attribute `data-bs-theme` which Bootstrap 5.3+ uses to
    // support color-scheme switching.
    if (!htmlElement.hasAttribute("data-bs-theme")) {
        htmlElement.setAttribute("data-bs-theme", "dark");
    }

    // Read curent theme string (e.g., "dark" or "light")
    const currentTheme = htmlElement.getAttribute("data-bs-theme");

    // ASSUMPTION: button is present. If button is null, the next line will throw.
    // Recommendation: wrap the following section in `if (button) { ... }` in production.
    button.textContent = currentTheme === "dark" ? "Light" : "Dark";

    // Toggle theme on click
    button.addEventListener("click", () => {
        // Read current theme and compute the next theme
        const current = htmlElement.getAttribute("data-bs-theme");
        const next = current === "dark" ? "light" : "dark";

        // Apply the next theme to the <html> element
        htmlElement.setAttribute("data-bs-theme", next);

        // Update button text to indicate the action (i.e., switch to opposite)
        // Again, ASSUMPTION: `button` exists. If not, this line will throw.
        button.textContent = next === "dark" ? "Light" : "Dark";
    });
});

/**
 * Window scroll handler: show/hide "scroll to top" button when scrolled down.
 * 
 * The handler toggles display: block/none on the element with id "scrollBtn".
 * This assignment uses the simpler `window.onscroll = function () {...}` approach.
 * 
 * No parameters.
 * @returns {void}
 */
window.onscroll = function () {
    // Grab the button. If element is not present, btn will be null and the next
    // property access (btn.style) will throw. Consider guarding: if (!btn) return;
    const btn = document.getElementById("scrollBtn");

    // If scrolled more than 200px vertically, show the button; otherwise hide it.
    // We check both document.body.scrollTop and document.documentElement.ScrollTop
    // for cross-browser compatibility (legacy reasons).
    if (document.body.scrollTop > 200 || document.documentElement.scrollTop > 200) {
        btn.style.display = "block";
    } else {
        btn.style.display = "none";
    }
};

/**
 * Smooth scroll to top helper.
 * 
 * Call this from an onclick handler on the #scrollBtn, e.g.:
 *  <button id="scrollBtn" onclick="ScrollToTop()">Top</button>
 * 
 * No parameters
 * @returns {void}
 */
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}

/**
 * Update digital clock element with current local time formatted HH:MM:SS.
 * 
 * - Pads hour/minutes/seconds to two digits.
 * - Writes the result to the element with id "clock".
 * 
 * No parameters.
 * @returns {void}
 */
function updateClock() {
    const now = new Date();
    // Get hours/minutes/seconds as numbers
    let hours = now.getHours();
    let minutes = now.getMinutes();
    let seconds = now.getSeconds();

    // Pad single digits with leading zero
    hours = hours < 10 ? "0" + hours : hours;
    minutes = minutes < 10 ? "0" + minutes : minutes;
    seconds = seconds < 10 ? "0" + seconds : seconds;

    // ASSUMPTION: element with id "clock" exists. If not, getElementById will return null
    // and .innerText will throw.
    document.getElementById("clock").innerText = `${hours}:${minutes}:${seconds}`;
}

// Start the clock: call every 1000ms (1 second) and also immediately update once.
setInterval(updateClock, 1000);
updateClock();