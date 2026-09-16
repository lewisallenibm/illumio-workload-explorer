(() => {
  document.addEventListener("DOMContentLoaded", () => {
    const panel = document.querySelector("[data-operation-id]");
    if (!panel) return;
    const operationId = panel.dataset.operationId;
    const message = panel.querySelector("[data-operation-message]");
    const progress = panel.querySelector("[data-operation-progress]");
    const percent = panel.querySelector("[data-operation-percent]");
    const refresh = async () => {
      try {
        const response = await fetch(`/operations/${operationId}`, { credentials: "same-origin" });
        if (!response.ok) return;
        const operation = await response.json();
        message.textContent = operation.message;
        if (operation.progress_total) {
          progress.max = operation.progress_total;
          progress.value = operation.progress_current;
          progress.classList.remove("indeterminate");
          percent.textContent = `${Math.round((operation.progress_current / operation.progress_total) * 100)}%`;
        }
        if (operation.status === "FAILED") { panel.classList.add("operation-failed"); percent.textContent = operation.error || "Failed"; return; }
        if (operation.status === "SUCCESS") {
          panel.classList.add("operation-complete");
          percent.textContent = "Completed — refreshing data…";
          window.setTimeout(() => {
            const url = new URL(window.location.href);
            url.searchParams.delete("operation_id");
            window.location.assign(url.toString());
          }, 750);
          return;
        }
        window.setTimeout(refresh, 900);
      } catch (_) { window.setTimeout(refresh, 1800); }
    };
    refresh();
  });
})();
