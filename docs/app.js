const WORKER_URL = "https://instatomdnotes-worker.yogiswagger28.workers.dev";
const BATCH_DELAY_MS = 30000;

const form = document.getElementById("submit-form");
const btn = document.getElementById("submit-btn");
const status = document.getElementById("status");
const passphraseInput = document.getElementById("passphrase");
const passphraseGroup = document.getElementById("passphrase-group");
const passphraseSaved = document.getElementById("passphrase-saved");

// On load — restore saved passphrase from sessionStorage
if (sessionStorage.getItem("passphrase")) {
  showPassphraseSaved();
}

// Collapse field on blur if a value was typed
passphraseInput.addEventListener("blur", () => {
  if (passphraseInput.value.trim()) {
    sessionStorage.setItem("passphrase", passphraseInput.value.trim());
    showPassphraseSaved();
  }
});

document.getElementById("change-passphrase").addEventListener("click", () => {
  sessionStorage.removeItem("passphrase");
  passphraseInput.value = "";
  passphraseSaved.classList.add("hidden");
  passphraseGroup.classList.remove("hidden");
  passphraseInput.focus();
});

function showPassphraseSaved() {
  passphraseGroup.classList.add("hidden");
  passphraseSaved.classList.remove("hidden");
}

function getPassphrase() {
  return passphraseInput.value.trim() || sessionStorage.getItem("passphrase") || "";
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const passphrase = getPassphrase();
  const raw = document.getElementById("urls").value;

  if (!passphrase) {
    showStatus("Passphrase is required.", "error");
    return;
  }

  const urls = raw
    .split("\n")
    .map(u => u.trim())
    .filter(u => u.includes("instagram.com/p/"));

  if (urls.length === 0) {
    showStatus("No valid Instagram post URLs found.", "error");
    return;
  }
  if (urls.length > 10) {
    showStatus("Max 10 URLs at once. Please remove some and try again.", "error");
    return;
  }

  btn.disabled = true;
  status.className = "status hidden";

  if (urls.length === 1) {
    await submitSingle(urls[0], passphrase);
  } else {
    await submitBatch(urls, passphrase);
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
      showStatus("Processing... checking status in 20s.", "success");
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
