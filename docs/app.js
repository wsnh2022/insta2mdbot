const WORKER_URL = "https://instatomdnotes-worker.yogiswagger28.workers.dev";

const form = document.getElementById("submit-form");
const btn = document.getElementById("submit-btn");
const status = document.getElementById("status");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = document.getElementById("url").value.trim();

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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instagram_url: url }),
    });

    const data = await resp.json();

    if (resp.ok && data.status === "triggered") {
      showStatus("Submitted. Your markdown note will be ready in ~2 minutes.\nCheck your /notes folder on GitHub.", "success");
      form.reset();
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
