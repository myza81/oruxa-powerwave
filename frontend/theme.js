// Powerwave appearance (Light/Dark) preference -- a general application
// setting, not scoped to any single page (see
// docs/project-memory/DECISIONS.md DEC-023). Shared, static, no-build-step
// file included by every frontend page via <script src="theme.js"></script>,
// the same pattern already used for config.js.
//
// Loaded synchronously, early in <head>, deliberately BEFORE <body> paints
// -- applyTheme() runs immediately at load time so the correct
// [data-theme] attribute is already on <html> before the first frame,
// avoiding a flash of the wrong theme.
(function () {
    "use strict";

    var STORAGE_KEY = "powerwave.theme";
    var VALID_THEMES = ["light", "dark"];
    var DEFAULT_THEME = "light"; // owner-preferred default -- see DEC-023

    function isValidTheme(value) {
        return VALID_THEMES.indexOf(value) !== -1;
    }

    function getStoredTheme() {
        try {
            var value = localStorage.getItem(STORAGE_KEY);
            return isValidTheme(value) ? value : null;
        } catch (error) {
            // localStorage can throw in some private-browsing/sandboxed
            // contexts -- fall back to the default rather than erroring.
            return null;
        }
    }

    function currentTheme() {
        return getStoredTheme() || DEFAULT_THEME;
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
    }

    function setTheme(theme) {
        if (!isValidTheme(theme)) return;
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (error) {
            // Preference simply won't persist this session -- theme still
            // applies for the current page view.
        }
        applyTheme(theme);
        document.dispatchEvent(new CustomEvent("powerwave:theme-change", { detail: { theme: theme } }));
    }

    // Apply immediately (this script runs synchronously, before <body>).
    applyTheme(currentTheme());

    // Cross-tab sync: index.html and waveform-prototype.html are typically
    // open in separate tabs (the waveform link opens in a new tab) but
    // share one localStorage origin -- if the preference changes in one
    // tab, reflect it in any other already-open tab too, consistent with
    // this being one shared, general application preference rather than a
    // per-page setting.
    window.addEventListener("storage", function (event) {
        if (event.key === STORAGE_KEY && isValidTheme(event.newValue)) {
            applyTheme(event.newValue);
            document.dispatchEvent(new CustomEvent("powerwave:theme-change", { detail: { theme: event.newValue } }));
        }
    });

    // Builds and wires a small Light/Dark segmented control into
    // `container` (an existing DOM element). Kept here, not duplicated per
    // page, so every page's control looks and behaves identically.
    function mountThemeToggle(container) {
        if (!container) return;
        container.innerHTML = "";
        container.className = (container.className ? container.className + " " : "") + "theme-toggle";
        container.setAttribute("role", "group");
        container.setAttribute("aria-label", "Appearance");

        var labels = { light: "Light", dark: "Dark" };
        var buttons = {};

        VALID_THEMES.forEach(function (theme) {
            var button = document.createElement("button");
            button.type = "button";
            button.textContent = labels[theme];
            button.addEventListener("click", function () {
                setTheme(theme);
            });
            buttons[theme] = button;
            container.appendChild(button);
        });

        function syncPressedState() {
            var active = currentTheme();
            VALID_THEMES.forEach(function (theme) {
                buttons[theme].setAttribute("aria-pressed", String(theme === active));
            });
        }

        syncPressedState();
        document.addEventListener("powerwave:theme-change", syncPressedState);
    }

    window.PowerwaveTheme = {
        STORAGE_KEY: STORAGE_KEY,
        DEFAULT_THEME: DEFAULT_THEME,
        getTheme: currentTheme,
        setTheme: setTheme,
        mountThemeToggle: mountThemeToggle,
    };
})();
