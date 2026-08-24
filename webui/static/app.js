const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const fileListEl = document.getElementById("file-list");
const urlInput = document.getElementById("url-input");
const convertBtn = document.getElementById("convert-btn");
const clearBtn = document.getElementById("clear-btn");
const downloadAllBtn = document.getElementById("download-all-btn");
const downloadFormat = document.getElementById("download-format");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const logoutLink = document.getElementById("logout-link");

let selectedFiles = [];
let lastResults = [];

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

function suggestedFilename(name, extension) {
  try {
    const url = new URL(name);
    name = url.pathname.split("/").filter(Boolean).pop() || url.hostname;
  } catch (_) {
    // not a URL, use as-is
  }
  const base = name.replace(/\.[^./]+$/, "") || "converted";
  return `${base}.${extension}`;
}

function saveBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function downloadMarkdown(name, markdown) {
  saveBlob(new Blob([markdown], { type: "text/markdown" }), suggestedFilename(name, "md"));
}

async function downloadDocx(name, markdown) {
  const formData = new FormData();
  formData.append("markdown", markdown);
  formData.append("name", name);

  const res = await fetch("/api/to-docx", { method: "POST", body: formData });
  if (res.status === 401) {
    location.href = "/login";
    return;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Could not build .docx (${res.status})`);
  }
  saveBlob(await res.blob(), suggestedFilename(name, "docx"));
}

function download(name, markdown, format) {
  return format === "docx"
    ? downloadDocx(name, markdown)
    : Promise.resolve(downloadMarkdown(name, markdown));
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

      const mdBtn = document.createElement("button");
      mdBtn.className = "secondary";
      mdBtn.textContent = "Download .md";
      mdBtn.addEventListener("click", () => downloadMarkdown(r.name, r.markdown));

      const docxBtn = document.createElement("button");
      docxBtn.className = "secondary";
      docxBtn.textContent = "Download .docx";
      docxBtn.addEventListener("click", async () => {
        docxBtn.disabled = true;
        docxBtn.textContent = "Building…";
        try {
          await downloadDocx(r.name, r.markdown);
        } catch (err) {
          statusEl.textContent = err.message || String(err);
          statusEl.className = "status-line error";
        } finally {
          docxBtn.disabled = false;
          docxBtn.textContent = "Download .docx";
        }
      });

      btns.appendChild(copyBtn);
      btns.appendChild(mdBtn);
      btns.appendChild(docxBtn);
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

clearBtn.addEventListener("click", () => {
  selectedFiles = [];
  fileInput.value = "";
  renderFileList();
  urlInput.value = "";
  resultsEl.innerHTML = "";
  lastResults = [];
  downloadAllBtn.disabled = true;
  statusEl.textContent = "";
  statusEl.className = "status-line";
});

downloadAllBtn.addEventListener("click", async () => {
  const format = downloadFormat.value;
  const ok = lastResults.filter((r) => !r.error);

  downloadAllBtn.disabled = true;
  const label = downloadAllBtn.textContent;
  downloadAllBtn.textContent = "Downloading…";

  try {
    for (const r of ok) {
      await download(r.name, r.markdown, format);
      // Browsers drop downloads fired back-to-back; space them out a little.
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
    statusEl.textContent = `Downloaded ${ok.length} .${format} file(s).`;
    statusEl.className = "status-line";
  } catch (err) {
    statusEl.textContent = err.message || String(err);
    statusEl.className = "status-line error";
  } finally {
    downloadAllBtn.textContent = label;
    downloadAllBtn.disabled = ok.length === 0;
  }
});

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
    lastResults = data.results;
    downloadAllBtn.disabled = !data.results.some((r) => !r.error);
    renderResults(data.results);
    statusEl.textContent = `Converted ${data.results.length} item(s).`;
  } catch (err) {
    statusEl.textContent = err.message || String(err);
    statusEl.className = "status-line error";
  } finally {
    setBusy(false);
  }
});
