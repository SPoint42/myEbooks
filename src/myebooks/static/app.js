const searchInput = document.querySelector("[data-search]");
const cards = [...document.querySelectorAll("[data-searchable]")];
const noResults = document.querySelector("[data-no-results]");

if (searchInput) {
  searchInput.addEventListener("input", () => {
    const query = searchInput.value.trim().toLocaleLowerCase("fr");
    let visible = 0;
    for (const card of cards) {
      const matches = card.dataset.searchable.toLocaleLowerCase("fr").includes(query);
      card.hidden = !matches;
      visible += Number(matches);
    }
    if (noResults) noResults.hidden = visible !== 0;
  });
}

const indexForm = document.querySelector("[data-index-form]");
if (indexForm) {
  indexForm.addEventListener("submit", () => {
    const button = indexForm.querySelector("button");
    button.disabled = true;
    button.textContent = "Indexation lancée…";
  });
}

const syncStatus = document.querySelector("[data-sync-status]");
if (syncStatus?.dataset.status === "running") {
  const poll = window.setInterval(async () => {
    try {
      const response = await fetch("/api/index/status", { credentials: "same-origin" });
      const status = await response.json();
      if (status.status !== "running") {
        window.clearInterval(poll);
        window.location.reload();
      }
    } catch (_error) {
      // A transient network error is retried on the next poll.
    }
  }, 1500);
}
