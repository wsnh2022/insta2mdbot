const WORKER_URL = "https://instatomdnotes-worker.yogiswagger28.workers.dev";

const form = document.getElementById("submit-form");
const btn = document.getElementById("submit-btn");
const status = document.getElementById("status");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = document.getElementById("url").value.trim();
  const passphrase = document.getElementById("passphrase").value;

  if (!passphrase) {
    showStatus("Passphrase is required.", "error");
    return;
  }

  if (!url.includes("instagram.com/p/")) {
    showStatus("Please enter a valid Instagram post URL.", "error");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Submitting...";
  status.className = "status hidden";

  try {
    const resp = await fetch(WORKER_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Access-Key": passphrase,
      },
      body: JSON.stringify({ instagram_url: url }),
    });

    const data = await resp.json();

    if (resp.ok && data.status === "triggered") {
      showStatus("Processing... checking status in 20s.", "success");
      document.getElementById("url").value = "";
      pollStatus(passphrase);
    } else if (resp.status === 401) {
      showStatus("Wrong passphrase.", "error");
    } else if (resp.status === 429) {
      showStatus("Too many requests. Wait a minute and try again.", "error");
    } else {
      showStatus(data.error || "Something went wrong. Try again.", "error");
    }
  } catch (err) {
    showStatus("Network error. Check your connection.", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Convert";
  }
});

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
