(() => {
  const themeKey = "illumio.theme";

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme === "light" ? "light" : "dark";
  }

  document.addEventListener("DOMContentLoaded", () => {
    const theme = localStorage.getItem(themeKey) || "dark";
    applyTheme(theme);
    const themeSelect = document.querySelector("#theme-select");
    if (themeSelect) {
      themeSelect.value = theme;
      document.querySelector("#appearance-settings").addEventListener("submit", (event) => {
        event.preventDefault();
        localStorage.setItem(themeKey, themeSelect.value);
        applyTheme(themeSelect.value);
        document.querySelector("#appearance-status").textContent = `${themeSelect.value[0].toUpperCase()}${themeSelect.value.slice(1)} appearance applied.`;
      });
    }

    const addRecipient = document.querySelector("#add-recipient");
    if (addRecipient) {
      const status = document.querySelector("#recipient-slot-status");
      const cards = [...document.querySelectorAll("[data-recipient-slot]")];
      const showOnly = (slot) => {
        cards.forEach((card) => { card.hidden = Number(card.dataset.recipientSlot) !== slot; });
        const selected = document.querySelector(`#recipient-${slot}`);
        if (selected) selected.scrollIntoView({ behavior: "smooth", block: "center" });
      };
      addRecipient.addEventListener("click", () => {
        const available = cards.find((card) => card.dataset.recipientSaved === "false");
        if (!available) {
          status.textContent = "All 10 pilot recipient slots are in use.";
          return;
        }
        showOnly(Number(available.dataset.recipientSlot));
        status.textContent = "New recipient editor opened.";
      });

      const directory = document.querySelector("#recipient-directory");
      if (directory) {
        directory.addEventListener("change", () => {
          const slot = Number(directory.value);
          if (!slot) return;
          showOnly(slot);
          status.textContent = "Selected recipient editor opened.";
        });
      }
      const search = document.querySelector("#recipient-search");
      if (search && directory) {
        search.addEventListener("input", () => {
          const query = search.value.trim().toLowerCase();
          [...directory.options].forEach((option, index) => {
            option.hidden = index > 0 && !!query && !option.text.toLowerCase().includes(query);
          });
        });
      }

      // Handle delete recipient confirmation safely without inline event handlers (M-7 / CSP compliant).
      document.querySelectorAll("[data-confirm-delete]").forEach((form) => {
        form.addEventListener("submit", (event) => {
          const name = form.dataset.confirmDelete || "this recipient";
          if (!window.confirm(`Delete ${name} and their delivery settings?`)) {
            event.preventDefault();
          }
        });
      });
    }
  });
})();
