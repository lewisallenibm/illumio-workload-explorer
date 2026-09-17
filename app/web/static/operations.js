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

// ── Reconciliation grouped-hostname expand/collapse ──
(() => {
  document.addEventListener("DOMContentLoaded", () => {
    // Toggle a host group open/closed when its header row is clicked.
    document.addEventListener("click", (e) => {
      const hostRow = e.target.closest(".recon-host-row");
      if (!hostRow) return;
      // Clicking the "Select All" checkbox should not toggle the row.
      if (e.target.classList.contains("recon-select-all")) return;
      const targetId = hostRow.dataset.target;
      const detailRow = document.getElementById(targetId);
      if (!detailRow) return;
      const open = detailRow.classList.toggle("open");
      hostRow.classList.toggle("open", open);
    });

    // "Select All" checkbox for a group toggles every result_ids checkbox in that group.
    document.addEventListener("change", (e) => {
      if (!e.target.classList.contains("recon-select-all")) return;
      const group = e.target.dataset.group;
      const detailRow = document.getElementById(group);
      if (!detailRow) return;
      detailRow.querySelectorAll(".recon-row-cb").forEach((cb) => {
        cb.checked = e.target.checked;
      });
    });

    // Keep each group's "Select All" in sync when individual checkboxes change.
    document.addEventListener("change", (e) => {
      if (!e.target.classList.contains("recon-row-cb")) return;
      const group = e.target.dataset.group;
      const detailRow = document.getElementById(group);
      if (!detailRow) return;
      const all = detailRow.querySelectorAll(".recon-row-cb");
      const checked = detailRow.querySelectorAll(".recon-row-cb:checked");
      const selectAll = document.querySelector(`.recon-select-all[data-group="${group}"]`);
      if (!selectAll) return;
      selectAll.indeterminate = checked.length > 0 && checked.length < all.length;
      selectAll.checked = checked.length === all.length;
    });
  });
})();

// ── Inline detail drawer ──
(() => {
  document.addEventListener("DOMContentLoaded", () => {
    // Open drawer when a .detail-link is clicked.
    document.addEventListener("click", (e) => {
      const link = e.target.closest(".detail-link");
      if (!link) return;
      e.preventDefault();
      const url = link.dataset.panelUrl;
      if (!url) return;
      const drawer = document.getElementById("detail-drawer");
      if (!drawer) return;
      drawer.innerHTML = '<p class="muted" style="padding:16px">Loading…</p>';
      drawer.removeAttribute("hidden");
      drawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
      fetch(url, { credentials: "same-origin" })
        .then((r) => {
          if (!r.ok) throw new Error(r.status);
          return r.text();
        })
        .then((html) => { drawer.innerHTML = html; })
        .catch(() => { drawer.innerHTML = '<p class="error" style="padding:16px">Could not load details.</p>'; });
    });

    // Close drawer on close button click (event delegation — button is injected).
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".detail-panel-close")) return;
      const drawer = document.getElementById("detail-drawer");
      if (drawer) { drawer.setAttribute("hidden", ""); drawer.innerHTML = ""; }
    });
  });
})();
