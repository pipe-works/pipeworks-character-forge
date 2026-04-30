// Light/dark theme toggle, persisted to localStorage. Mirrors
// pipeworks-image-generator's `pw-theme` key so a user's preference
// follows them across the PipeWorks app suite.

const STORAGE_KEY = "pw-theme";

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme === "light" ? "light" : "");
  const button = document.getElementById("btn-theme-toggle");
  if (button) {
    button.textContent = theme === "light" ? "◑ Dark" : "◑ Light";
  }
  localStorage.setItem(STORAGE_KEY, theme);
}

function currentTheme() {
  return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
}

export function initThemeToggle() {
  applyTheme(currentTheme());
  const button = document.getElementById("btn-theme-toggle");
  if (!button) return;
  button.addEventListener("click", () => {
    applyTheme(currentTheme() === "light" ? "dark" : "light");
  });
}
