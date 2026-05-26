const WORKER_URL = "https://instatomdnotes-worker.yogiswagger28.workers.dev";
const BATCH_DELAY_MS = 30000;

function updateModeBadge() {
  const raw = document.getElementById("urls").value.trim();
  const badge = document.getElementById("mode-badge");
  const toggleRow = document.getElementById("extract-toggle-row");
  const toggle = document.getElementById("extract-text-toggle");
  if (!raw) {
    badge.className = "mode-badge hidden";
    toggleRow.classList.add("hidden");
    return;
  }

  const { mode, lines } = detectMode(raw);
  const count = lines.length;

  if (mode === "instagram") {
    const igCount = lines.filter(l => l.includes("instagram.com/p/")).length;
    badge.textContent = igCount === 1
      ? "📸 Instagram carousel → note"
      : `📸 ${igCount} Instagram URLs → ${igCount} notes (batch)`;
    badge.className = "mode-badge mode-ig";
    toggleRow.classList.remove("hidden");
  } else if (mode === "urls") {
    badge.textContent = count === 1
      ? "🔗 Plain URL → reading list"
      : `🔗 ${count} URLs → reading list`;
    badge.className = "mode-badge mode-url";
    toggleRow.classList.add("hidden");
    toggle.checked = true;
    document.getElementById("toggle-hint").textContent = "Full note + GitHub backup";
  } else {
    badge.textContent = "✏️ Raw text → AI-generated note";
    badge.className = "mode-badge mode-text";
    toggleRow.classList.add("hidden");
    toggle.checked = true;
    document.getElementById("toggle-hint").textContent = "Full note + GitHub backup";
  }
}

const form = document.getElementById("submit-form");
const btn = document.getElementById("submit-btn");
const status = document.getElementById("status");
const passphraseInput = document.getElementById("passphrase");
const passphraseGroup = document.getElementById("passphrase-group");
const passphraseLock = document.getElementById("passphrase-lock");

document.getElementById("urls").addEventListener("input", updateModeBadge);

document.getElementById("extract-text-toggle").addEventListener("change", function () {
  document.getElementById("toggle-hint").textContent = this.checked
    ? "Full note + GitHub backup"
    : "Metadata · 1 AI call";
});

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
    if (igUrls.length === 1) { await submitSingle(igUrls[0], passphrase, igUrls[0]); }
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

async function submitSingle(url, passphrase, submittedUrl) {
  const extractText = document.getElementById("extract-text-toggle").checked;
  btn.textContent = "Submitting...";
  try {
    const resp = await fetch(WORKER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Access-Key": passphrase },
      body: JSON.stringify({ instagram_url: url, push_to_notion: true, extract_text: extractText }),
    });
    const data = await resp.json();
    if (resp.ok && data.status === "triggered") {
      showStatus("Processing carousel... checking status in 20s.", "success");
      document.getElementById("urls").value = ""; updateModeBadge();
      pollStatus(passphrase, submittedUrl);
    } else if (resp.ok && data.status === "duplicate") {
      showStatus(`Already saved — ${data.shortcode} was processed before.`, "success");
      document.getElementById("urls").value = ""; updateModeBadge();
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
  const extractText = document.getElementById("extract-text-toggle").checked;
  let failed = 0;
  let duplicates = 0;
  let triggered = 0;

  for (let i = 0; i < urls.length; i++) {
    btn.textContent = `Submitting ${i + 1}/${urls.length}...`;
    let isDuplicate = false;
    try {
      const resp = await fetch(WORKER_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Access-Key": passphrase },
        body: JSON.stringify({ instagram_url: urls[i], push_to_notion: true, extract_text: extractText }),
      });
      if (resp.status === 401) {
        showStatus("Wrong passphrase.", "error");
        return;
      }
      if (resp.ok) {
        const data = await resp.json();
        if (data.status === "duplicate") {
          duplicates++;
          isDuplicate = true;
        } else if (data.status === "triggered") {
          triggered++;
        } else {
          failed++;
        }
      } else {
        failed++;
      }
    } catch {
      failed++;
    }

    // Skip the delay after duplicates — no workflow was triggered, no need to wait
    if (i < urls.length - 1 && !isDuplicate) {
      await sleep(BATCH_DELAY_MS);
    }
  }

  const estMin = triggered * 2;
  const parts = [];
  if (triggered > 0) parts.push(`${triggered} submitted`);
  if (duplicates > 0) parts.push(`${duplicates} already saved`);
  if (failed > 0) parts.push(`${failed} failed`);

  if (triggered === 0 && duplicates > 0 && failed === 0) {
    showStatus(`All ${duplicates} already saved — nothing new to process.`, "success");
  } else if (triggered > 0) {
    const suffix = estMin > 0 ? `. Notes ready in ~${estMin} min.` : ".";
    showStatus(parts.join(", ") + suffix, failed > 0 ? "error" : "success");
  } else {
    showStatus("All submissions failed. Check your connection and try again.", "error");
  }

  if (failed === 0 || triggered > 0) {
    document.getElementById("urls").value = ""; updateModeBadge();
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
      document.getElementById("urls").value = ""; updateModeBadge();
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

async function pollStatus(passphrase, submittedUrl) {
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
            if (data.duplicate) {
              const shortcode = submittedUrl ? submittedUrl.split("/p/")[1]?.replace(/\/$/, "") : "";
              showStatus(`Already saved — ${shortcode || "this post"} was processed before.`, "success");
            } else {
              showStatus("Done! Your note is saved.", "success");
            }
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

// PWA service worker registration
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/insta2mdbot/sw.js');
}

// Android Share Target — handle ?url= / ?text= injected by the OS share sheet
(function handleShareTarget() {
  const params = new URLSearchParams(window.location.search);
  const shared = (params.get('url') || params.get('text') || '').trim();
  if (!shared) return;

  // Strip query params so a refresh doesn't re-trigger
  history.replaceState(null, '', window.location.pathname);

  const textarea = document.getElementById('urls');
  textarea.value = shared;
  updateModeBadge();

  // Auto-submit only if passphrase is already saved — otherwise show pre-filled form
  const passphrase = getPassphrase();
  if (passphrase) {
    showStatus('Shared URL detected — submitting...', 'success');
    setTimeout(() => form.requestSubmit(), 800);
  } else {
    showStatus('URL pre-filled. Enter your passphrase and hit Convert.', 'success');
    passphraseGroup.classList.remove('hidden');
    passphraseInput.focus();
  }
}());
