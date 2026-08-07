const DEFAULT_PROJECT_PATH = "/path/to/project";
const projectPathInput = document.querySelector("#project-path");
const resetPathButton = document.querySelector("#reset-path");
const copyStatus = document.querySelector("#copy-status");
const taskFilter = document.querySelector("#task-filter");
const taskCards = [...document.querySelectorAll(".task-card")];
const noResults = document.querySelector("#no-results");

function shellQuote(value) {
  if (/^[A-Za-z0-9_./~:-]+$/.test(value)) {
    return value;
  }
  return "'" + value.replaceAll("'", "'\"'\"'") + "'";
}

function projectName(path) {
  const cleanPath = path.replace(/\/+$/, "");
  return cleanPath.split("/").filter(Boolean).at(-1) || "project";
}

function updateProjectCommands() {
  const rawPath = projectPathInput.value.trim() || DEFAULT_PROJECT_PATH;
  const quotedPath = shellQuote(rawPath);
  const quotedName = shellQuote(projectName(rawPath));

  document.querySelectorAll("[data-project-path]").forEach((element) => {
    element.textContent = quotedPath;
  });
  document.querySelectorAll("[data-project-name]").forEach((element) => {
    element.textContent = quotedName;
  });

  try {
    localStorage.setItem("cmux-factory-project-path", rawPath);
  } catch {
    // The page still works when storage is disabled.
  }
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const temporary = document.createElement("textarea");
  temporary.value = text;
  temporary.setAttribute("readonly", "");
  temporary.style.position = "fixed";
  temporary.style.opacity = "0";
  document.body.append(temporary);
  temporary.select();
  document.execCommand("copy");
  temporary.remove();
}

let statusTimer;
function showCopyStatus(message) {
  copyStatus.textContent = message;
  copyStatus.classList.add("visible");
  window.clearTimeout(statusTimer);
  statusTimer = window.setTimeout(() => copyStatus.classList.remove("visible"), 1500);
}

document.querySelectorAll(".command").forEach((command) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy-button";
  button.textContent = "Copy";
  button.setAttribute("aria-label", "Copy command");
  button.addEventListener("click", async () => {
    const code = command.querySelector("code");
    try {
      await copyText(code.textContent.trim());
      button.textContent = "Copied";
      showCopyStatus("Command copied");
      window.setTimeout(() => {
        button.textContent = "Copy";
      }, 1500);
    } catch {
      showCopyStatus("Copy failed. Select the command text.");
    }
  });
  command.append(button);
});

projectPathInput.addEventListener("input", updateProjectCommands);
resetPathButton.addEventListener("click", () => {
  projectPathInput.value = DEFAULT_PROJECT_PATH;
  updateProjectCommands();
  projectPathInput.focus();
});

taskFilter.addEventListener("input", () => {
  const query = taskFilter.value.trim().toLowerCase();
  let visibleCount = 0;

  taskCards.forEach((card) => {
    const text = card.textContent.toLowerCase();
    const matches = !query || card.dataset.task.includes(query) || text.includes(query);
    card.hidden = !matches;
    if (matches) visibleCount += 1;
  });

  noResults.hidden = visibleCount !== 0;
});

try {
  const savedPath = localStorage.getItem("cmux-factory-project-path");
  if (savedPath) projectPathInput.value = savedPath;
} catch {
  // The default path is enough when storage is disabled.
}

updateProjectCommands();
