(function () {
    "use strict";

    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-input");
    const log = document.getElementById("chat-log");
    const statusDot = document.getElementById("core-status-dot");
    const toastStack = document.getElementById("toast-stack");

    let sessionId = null;
    let lastNotificationTs = 0;

    // Phase 13: renders anything raised via ui.notifications (a core
    // failure in ui/bridge.py, or any other UI surface) as a toast here
    // too, not just in the desktop dashboard/tray/overlay.
    function showToast(level, title, message) {
        if (!toastStack) return;
        const toast = document.createElement("div");
        toast.className = "toast toast--" + (level || "info");
        toast.textContent = message ? title + " - " + message : title;
        toastStack.appendChild(toast);
        window.setTimeout(function () {
            toast.classList.add("toast--hide");
            window.setTimeout(function () { toast.remove(); }, 300);
        }, level === "error" ? 8000 : 4000);
    }

    async function pollNotifications() {
        try {
            const res = await fetch("/notifications?since=" + lastNotificationTs);
            const data = await res.json();
            for (const n of (data.notifications || [])) {
                showToast(n.level, n.title, n.message);
                if (n.timestamp > lastNotificationTs) lastNotificationTs = n.timestamp;
            }
        } catch (err) {
            // Silent - a failed poll for notifications shouldn't itself
            // spawn an error toast, or a network hiccup becomes noisy.
        }
    }

    function appendBubble(role, text) {
        const bubble = document.createElement("div");
        bubble.className = "chat__bubble chat__bubble--" + role;
        bubble.textContent = text;
        log.appendChild(bubble);
        log.scrollTop = log.scrollHeight;
    }

    async function refreshStatus() {
        try {
            const res = await fetch("/status");
            const data = await res.json();
            statusDot.classList.remove("online", "stub");
            if (data.assistant) {
                statusDot.classList.add("online");
                statusDot.title = "Ultron core connected";
            } else {
                statusDot.classList.add("stub");
                statusDot.title = "Running on the UI stub - core.assistant not wired in yet";
            }
        } catch (err) {
            statusDot.title = "Could not reach /status";
        }
    }

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        appendBubble("user", text);
        input.value = "";
        input.disabled = true;

        try {
            const res = await fetch("/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, session_id: sessionId }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                appendBubble("assistant", "Error: " + (err.error || res.statusText));
                return;
            }

            const data = await res.json();
            sessionId = data.session_id;
            appendBubble("assistant", data.reply);
        } catch (err) {
            appendBubble("assistant", "Error: could not reach Ultron (" + err.message + ")");
        } finally {
            input.disabled = false;
            input.focus();
        }
    });

    refreshStatus();
    pollNotifications();
    window.setInterval(pollNotifications, 4000);
})();
