import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

window.addEventListener("DOMContentLoaded", () => {
  const loginBtn = document.getElementById("login-btn")!;
  const startBtn = document.getElementById("start-bot")!;
  const pauseBtn = document.getElementById("pause-bot")!;
  const output = document.getElementById("log-output")!;

  const logLines: string[] = [];
  let paused = false;

  // Stream logs from Rust → UI (max 15 lines)
  listen<string>("bot-log", (event) => {
    const line = event.payload;

    // Check for AdsPower connection failure
    if (line.includes("ECONNREFUSED")) {
      alert("⚠️ Could not connect to AdsPower. Is it running?");
    }

    logLines.push(line);
    if (logLines.length > 15) {
      logLines.shift();
    }
    output.textContent = logLines.join("\n");
    output.scrollTop = output.scrollHeight;
  });

  loginBtn.addEventListener("click", async () => {
    const email = (document.getElementById("email") as HTMLInputElement).value;
    const password = (document.getElementById("password") as HTMLInputElement).value;

    try {
      await invoke("save_login", { email, password });
      output.textContent = "✅ Logged in. Use 'Save Config' to keep changes for the next time";
      startBtn.removeAttribute("disabled");
      pauseBtn.removeAttribute("disabled");
    } catch (e) {
      output.textContent = "❌ Login error: " + e;
    }
  });

  startBtn.addEventListener("click", async () => {
    logLines.length = 0; // clear stored logs
    output.textContent = "⏳ Starting bot...\n";
    try {
      await invoke("start_bot");
    } catch (e) {
      output.textContent += "❌ Failed to launch bot: " + e;
    }
  });

  pauseBtn.addEventListener("click", async () => {
    try {
      if (!paused) {
        await invoke("pause_bot");
        pauseBtn.textContent = "▶️ Resume";
        paused = true;
      } else {
        await invoke("resume_bot");
        pauseBtn.textContent = "⏸️ Pause";
        paused = false;
      }
    } catch (e) {
      output.textContent += "\n❌ Pause/Resume error: " + e;
    }
  });
});
