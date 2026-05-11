const WORKER_URL = "https://instatomdnotes-worker.yogiswagger28.workers.dev";
const BATCH_DELAY_MS = 30000;

const form = document.getElementById("submit-form");
const btn = document.getElementById("submit-btn");
const status = document.getElementById("status");
const passphraseInput = document.getElementById("passphrase");
const passphraseGroup = document.getElementById("passphrase-group");
const passphraseLock = document.getElementById("passphrase-lock");

// On load — if passphrase already saved, hide the field
if (sessionStorage.getItem("passphrase")) {
  showPassphraseSaved();
}

// Enter key → save and collapse
passphraseInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    collapsePassphrase();
  }
});

// Tab / click away → collapse
passphraseInput.addEventListener("blur", () => {
  collapsePassphrase();
});

// Lock button → reveal passphrase field to update it
passphraseLock.addEventListener("click", () => {
  if (!passphraseGroup.classList.contains("hidden")) return;
  passphraseLock.classList.remove("active");
  passphraseGroup.classList.remove("hidden");
  passphraseInput.focus();
});

function showPassphraseSaved() {
  passphraseGroup.classList.add("hidden");
  passphraseLock.classList.add("active");
}

function collapsePassphrase() {
  const val = passphraseInput.value.trim();
  if (!val) return;
  sessionStorage.setItem("passphrase", val);
  showPassphraseSaved();
  document.getElementById("urls").focus();
}

function getPassphrase() {
  return passphraseInput.value.trim() || sessionStorage.getItem("passphrase") || "";
}

function isUrl(s) {
  return /^https?:\/\/\S+/.test(s);
}

function detectMode(raw) {
  const lines = raw.split("\n").map(l => l.trim()).filter(l => l.length > 0);
  if (lines.length === 0) return { mode: null, lines };
  if (lines.some(l => l.includes("instagram.com/p/"))) return { mode: "instagram", lines };
  if (lines.every(l => isUrl(l))) return { mode: "urls", lines };
  return { mode: "text", lines };
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const passphrase = getPassphrase();
  const raw = document.getElementById("urls").value.trim();

  if (!passphrase) { showStatus("Passphrase is required.", "error"); return; }
  if (!raw) { showStatus("Nothing to process — paste a URL or some text.", "error"); return; }

  const { mode, lines } = detectMode(raw);
  if (mode === null) { showStatus("Nothing to process — paste a URL or some text.", "error"); return; }

  btn.disabled = true;
  status.className = "status hidden";

  if (mode === "instagram") {
    const igUrls = lines.filter(l => l.includes("instagram.com/p/"));
    if (igUrls.length > 10) {
      showStatus("Max 10 Instagram URLs at once. Please remove some and try again.", "error");
      btn.disabled = false; return;
    }
    if (igUrls.length === 1) { await submitSingle(igUrls[0], passphrase); }
    else { await submitBatch(igUrls, passphrase); }
  } else if (mode === "urls") {
    if (lines.length > 10) {
      showStatus("Max 10 URLs at once. Please remove some and try again.", "error");
      btn.disabled = false; return;
    }
    await submitContent("urls", lines.join("\n"), passphrase);
  } else {
    if (raw.length > 10000) {
      showStatus("Text is too long. Max 10,000 characters.", "error");
      btn.disabled = false; return;
    }
    await submitContent("text", raw, passphrase);
  }

  btn.disabled = false;
  btn.textContent = "Convert";
});

async function submitSingle(url, passphrase) {
  btn.textContent = "Submitting...";
  try {
    const resp = await fetch(WORKER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Access-Key": passphrase },
      body: JSON.stringify({ instagram_url: url }),
    });
    const data = await resp.json();
    if (resp.ok && data.status === "triggered") {
      showStatus("Processing carousel... checking status in 20s.", "success");
      document.getElementById("urls").value = "";
      pollStatus(passphrase);
    } else if (resp.status === 401) {
      showStatus("Wrong passphrase.", "error");
    } else if (resp.status === 429) {
      showStatus("Too many requests. Wait a minute and try again.", "error");
    } else {
      showStatus(data.error || "Something went wrong. Try again.", "error");
    }
  } catch {
    showStatus("Network error. Check your connection.", "error");
  }
}

async function submitBatch(urls, passphrase) {
  let failed = 0;

  for (let i = 0; i < urls.length; i++) {
    btn.textContent = `Submitting ${i + 1}/${urls.length}...`;
    try {
      const resp = await fetch(WORKER_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Access-Key": passphrase },
        body: JSON.stringify({ instagram_url: urls[i] }),
      });
      if (resp.status === 401) {
        showStatus("Wrong passphrase.", "error");
        return;
      }
      if (!resp.ok) failed++;
    } catch {
      failed++;
    }

    if (i < urls.length - 1) {
      await sleep(BATCH_DELAY_MS);
    }
  }

  const submitted = urls.length - failed;
  const estMin = submitted * 2;

  if (failed === 0) {
    showStatus(`All ${submitted} submitted. Notes ready in ~${estMin} min.`, "success");
    document.getElementById("urls").value = "";
  } else if (submitted > 0) {
    showStatus(`${submitted} submitted, ${failed} failed. Notes ready in ~${estMin} min.`, "success");
  } else {
    showStatus("All submissions failed. Check your connection and try again.", "error");
  }
}

async function submitContent(mode, content, passphrase) {
  btn.textContent = mode === "urls" ? "Saving to reading list..." : "Generating note...";
  try {
    const resp = await fetch(WORKER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Access-Key": passphrase },
      body: JSON.stringify({ mode, content }),
    });
    const data = await resp.json();
    if (resp.ok && data.status === "triggered") {
      if (mode === "urls") {
        showStatus("URLs saved to reading list. Note updated in ~30s.", "success");
      } else {
        showStatus("Processing text... note ready in ~1 min.", "success");
        pollStatus(passphrase);
      }
      document.getElementById("urls").value = "";
    } else if (resp.status === 401) {
      showStatus("Wrong passphrase.", "error");
    } else if (resp.status === 429) {
      showStatus("Too many requests. Wait a minute and try again.", "error");
    } else {
      showStatus(data.error || "Something went wrong. Try again.", "error");
    }
  } catch {
    showStatus("Network error. Check your connection.", "error");
  }
}

function showStatus(msg, type) {
  status.textContent = msg;
  status.className = `status ${type}`;
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function pollStatus(passphrase) {
  const deadline = Date.now() + 8 * 60 * 1000;
  await sleep(20000);

  async function check() {
    if (Date.now() > deadline) {
      showStatus("Check your notes repo — processing may still be running.", "success");
      return;
    }
    try {
      const resp = await fetch(WORKER_URL, {
        method: "GET",
        headers: { "X-Access-Key": passphrase },
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data.status === "completed") {
          if (data.conclusion === "success") {
            showStatus("Done! Your note is saved.", "success");
          } else {
            showStatus("Processing failed. Try submitting again.", "error");
          }
          return;
        }
        if (data.status === "in_progress") {
          showStatus("Still processing...", "success");
        }
      }
    } catch { /* silent — keep polling */ }
    setTimeout(check, 10000);
  }

  check();
}
