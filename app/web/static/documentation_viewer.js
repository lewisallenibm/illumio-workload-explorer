document.addEventListener("DOMContentLoaded", () => {
  const opener = document.getElementById("open-documentation");
  const dialog = document.getElementById("documentation-viewer");
  if (!opener || !dialog) return;

  const pageImage = document.getElementById("documentation-page");
  const pageCount = document.getElementById("documentation-page-count");
  const previous = document.getElementById("documentation-previous");
  const next = document.getElementById("documentation-next");
  const close = document.getElementById("close-documentation");
  const pages = JSON.parse(dialog.dataset.pages || "[]");
  let index = 0;

  function updatePage() {
    pageImage.src = pages[index];
    pageImage.alt = `Page ${index + 1} of the Illumio and CMDB Working Guide`;
    pageCount.textContent = `Page ${index + 1} of ${pages.length}`;
    previous.disabled = index === 0;
    next.disabled = index === pages.length - 1;
  }

  opener.addEventListener("click", () => {
    index = 0;
    updatePage();
    dialog.showModal();
  });
  previous.addEventListener("click", () => { if (index > 0) { index -= 1; updatePage(); } });
  next.addEventListener("click", () => { if (index < pages.length - 1) { index += 1; updatePage(); } });
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  updatePage();
});
