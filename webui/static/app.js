const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const fileListEl = document.getElementById("file-list");
const urlInput = document.getElementById("url-input");
const convertBtn = document.getElementById("convert-btn");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const logoutLink = document.getElementById("logout-link");

let selectedFiles = [];

function renderFileList() {
  if (selectedFiles.length === 0) {
    fileListEl.textContent = "";
    return;
  }
  fileListEl.textContent = selectedFiles.map((f) => f.name).join(", ");
}

dropzone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  selectedFiles = Array.from(fileInput.files);
  renderFileList();
});

["dragenter", "dragover"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (e) => {
  const dropped = Array.from(e.dataTransfer.files || []);
  if (dropped.length) {
    selectedFiles = dropped;
    renderFileList();
  }
});

logoutLink.addEventListener("click", async (e) => {
  e.preventDefault();
  await fetch("/logout", { method: "POST" });
  location.href = "/login";
});

function setBusy(busy) {
  convertBtn.disabled = busy;
  convertBtn.textContent = busy ? "Converting…" : "Convert";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function suggestedFilename(name) {
  try {
    const url = new URL(name);
    name = url.pathname.split("/").filter(Boolean).pop() || url.hostname;
  } catch (_) {
    // not a URL, use as-is
  }
  const base = name.replace(/\.[^./]+$/, "") || "converted";
  return `${base}.md`;
}

function renderResults(results) {
  resultsEl.innerHTML = "";
  for (const r of results) {
    const card = document.createElement("div");
    card.className = "result-card";

    const header = document.createElement("header");
    const nameEl = document.createElement("div");
    nameEl.className = "name";
    nameEl.textContent = r.name;
    header.appendChild(nameEl);

    if (!r.error) {
      const btns = document.createElement("div");
      btns.className = "btns";

      const copyBtn = document.createElement("button");
      copyBtn.className = "secondary";
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", async () => {
        await navigator.clipboard.writeText(r.markdown);
        copyBtn.textContent = "Copied!";
        setTimeout(() => (copyBtn.textContent = "Copy"), 1500);
      });

      const downloadBtn = document.createElement("button");
      downloadBtn.className = "secondary";
      downloadBtn.textContent = "Download .md";
      downloadBtn.addEventListener("click", () => {
        const blob = new Blob([r.markdown], { type: "text/markdown" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = suggestedFilename(r.name);
        a.click();
        URL.revokeObjectURL(a.href);
      });

      btns.appendChild(copyBtn);
      btns.appendChild(downloadBtn);
      header.appendChild(btns);
    }

    card.appendChild(header);

    if (r.error) {
      const err = document.createElement("div");
      err.className = "error";
      err.textContent = r.error;
      card.appendChild(err);
    } else {
      const textarea = document.createElement("textarea");
      textarea.readOnly = true;
      textarea.value = r.markdown;
      card.appendChild(textarea);
    }

    resultsEl.appendChild(card);
  }
}

convertBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (selectedFiles.length === 0 && !url) {
    statusEl.textContent = "Choose one or more files, or enter a URL.";
    statusEl.className = "status-line error";
    return;
  }

  const formData = new FormData();
  for (const f of selectedFiles) {
    formData.append("files", f);
  }
  if (url) {
    formData.append("url", url);
  }

  setBusy(true);
  statusEl.textContent = "";
  statusEl.className = "status-line";

  try {
    const res = await fetch("/api/convert", { method: "POST", body: formData });
    if (res.status === 401) {
      location.href = "/login";
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${res.status})`);
    }
    const data = await res.json();
    renderResults(data.results);
    statusEl.textContent = `Converted ${data.results.length} item(s).`;
  } catch (err) {
    statusEl.textContent = err.message || String(err);
    statusEl.className = "status-line error";
  } finally {
    setBusy(false);
  }
});
