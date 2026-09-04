(() => {
  "use strict";

  const GAUGE_CIRCUMFERENCE = 2 * Math.PI * 52; // r=52, matches dashboard.html

  const el = (id) => document.getElementById(id);

  const cpuRing = el("cpu-ring");
  const ramRing = el("ram-ring");
  const cpuValue = el("cpu-value");
  const ramValue = el("ram-value");
  const ramUsed = el("ram-used");
  const diskUsed = el("disk-used");
  const batteryRow = el("battery-row");
  const batteryValue = el("battery-value");
  const tickerBattery = el("ticker-battery");
  const tickerBatteryVal = el("ticker-battery-val");

  const statePill = el("state-pill");
  const stateLabel = el("state-label");
  const coreWrap = el("core-wrap");
  const coreLabel = el("core-label");
  const coreSub = el("core-sub");
  const waveform = el("waveform");

  const uptimeValue = el("uptime-value");
  const connIndicator = el("conn-indicator");
  const connLabel = el("conn-label");

  const feed = el("feed");
  const feedEmpty = el("feed-empty");
  const activityLog = el("activity-log");

  const commandForm = el("command-form");
  const commandInput = el("command-input");
  const commandSend = el("command-send");

  const imageEmpty = el("image-empty");
  const dashboardImage = el("dashboard-image");
  const imageCaption = el("image-caption");
  const imageSourceLink = el("image-source-link");

  // -------- waveform bars (ambient, brightens while speaking) --------

  for (let i = 0; i < 40; i++) {
    const bar = document.createElement("span");
    const h = 6 + Math.abs(Math.sin(i * 0.5)) * 18;
    bar.style.height = h + "px";
    bar.style.animationDelay = (i * 0.04) + "s";
    waveform.appendChild(bar);
  }

  // -------- gauges --------

  function setGauge(ringEl, valueEl, percent) {
    const pct = Math.max(0, Math.min(100, percent || 0));
    const offset = GAUGE_CIRCUMFERENCE * (1 - pct / 100);
    ringEl.style.strokeDashoffset = offset;
    valueEl.textContent = `${Math.round(pct)}%`;

    // Colour ramps toward red under heavy load - a glance should tell you
    // if something's actually under load, not just a static gauge.
    if (pct >= 85) {
      ringEl.style.stroke = "#ff5566";
    } else if (pct >= 60) {
      ringEl.style.stroke = "#ffb020";
    } else {
      ringEl.style.stroke = ringEl.id === "ram-ring" ? "#a675ff" : "#4ce0ff";
    }
  }

  // -------- mini history charts --------

  class MiniChart {
    constructor(canvasId, color, maxPoints = 60) {
      this.canvas = el(canvasId);
      this.ctx = this.canvas.getContext("2d");
      this.color = color;
      this.maxPoints = maxPoints;
      this.data = [];
      this._resize();
      window.addEventListener("resize", () => this._resize());
    }

    _resize() {
      const rect = this.canvas.getBoundingClientRect();
      this.canvas.width = Math.max(1, rect.width * devicePixelRatio);
      this.canvas.height = Math.max(1, rect.height * devicePixelRatio);
      this.draw();
    }

    push(value) {
      this.data.push(value);
      if (this.data.length > this.maxPoints) this.data.shift();
      this.draw();
    }

    draw() {
      const { ctx, canvas, data, color } = this;
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      if (data.length < 2) return;

      const stepX = w / (this.maxPoints - 1);
      const offsetX = w - (data.length - 1) * stepX;

      ctx.beginPath();
      data.forEach((v, i) => {
        const x = offsetX + i * stepX;
        const y = h - (v / 100) * h;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5 * devicePixelRatio;
      ctx.lineJoin = "round";
      ctx.stroke();

      ctx.lineTo(offsetX + (data.length - 1) * stepX, h);
      ctx.lineTo(offsetX, h);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, color + "55");
      grad.addColorStop(1, color + "00");
      ctx.fillStyle = grad;
      ctx.fill();
    }
  }

  const cpuChart = new MiniChart("cpu-chart", "#4ce0ff");
  const ramChart = new MiniChart("ram-chart", "#a675ff");

  // -------- state (idle / listening / thinking / speaking / error) --------

  const STATE_LABELS = {
    idle: "Idle",
    listening: "Listening…",
    thinking: "Thinking…",
    speaking: "Speaking…",
    error: "Error",
  };

  const CORE_TEXT = {
    idle: ["IDLE", "waiting for wake word"],
    listening: ["LISTENING", "voice input active"],
    thinking: ["THINKING", "routing to model"],
    speaking: ["SPEAKING", "reply in progress"],
    error: ["ERROR", "check activity log"],
  };

  function setState(state) {
    const s = state || "idle";
    statePill.className = `state-pill ${s}`;
    stateLabel.textContent = STATE_LABELS[s] || s;
    coreWrap.className = `core-wrap ${s}`;
    const [label, sub] = CORE_TEXT[s] || [s.toUpperCase(), ""];
    coreLabel.textContent = label;
    coreSub.textContent = sub;
    waveform.classList.toggle("active", s === "speaking" || s === "listening");
  }

  // -------- uptime --------

  let uptimeBase = null;
  function tickUptime() {
    if (uptimeBase == null) return;
    const elapsed = Math.floor((Date.now() - uptimeBase) / 1000);
    const hh = String(Math.floor(elapsed / 3600)).padStart(2, "0");
    const mm = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
    const ss = String(elapsed % 60).padStart(2, "0");
    uptimeValue.textContent = `${hh}:${mm}:${ss}`;
  }
  setInterval(tickUptime, 1000);

  fetch("/api/uptime").then(r => r.json()).then(d => {
    uptimeBase = Date.now() - (d.uptime_seconds || 0) * 1000;
    tickUptime();
  }).catch(() => {});

  // -------- conversation feed --------

  function addTurn(role, text) {
    if (feedEmpty && feedEmpty.parentNode) feedEmpty.remove();
    const bubble = document.createElement("div");
    bubble.className = `bubble ${role === "user" ? "user" : "ultron"}`;
    const roleLabel = document.createElement("span");
    roleLabel.className = "role";
    roleLabel.textContent = role === "user" ? "You" : "Ultron";
    const body = document.createElement("div");
    body.textContent = text;
    const ts = document.createElement("span");
    ts.className = "ts";
    ts.textContent = new Date().toLocaleTimeString();
    bubble.appendChild(roleLabel);
    bubble.appendChild(body);
    bubble.appendChild(ts);
    feed.appendChild(bubble);
    feed.scrollTop = feed.scrollHeight;

    while (feed.children.length > 200) feed.removeChild(feed.firstChild);
  }

  function addActivity(name, args) {
    const empty = activityLog.querySelector(".feed-empty");
    if (empty) empty.remove();
    const item = document.createElement("div");
    item.className = "activity-item";
    const time = new Date().toLocaleTimeString();
    item.innerHTML = `[${time}] <span class="tool-name">${escapeHtml(name)}</span>(${escapeHtml(args || "")})`;
    activityLog.appendChild(item);
    activityLog.scrollTop = activityLog.scrollHeight;
    while (activityLog.children.length > 150) activityLog.removeChild(activityLog.firstChild);
  }

  // -------- image panel ("show me a photo of X") --------
  // Always a REAL photo (Wikipedia/Wikimedia, via ai/image_display_tools.py's
  // show_image tool) - this panel never renders a generated/fake image,
  // it only ever shows whatever URL that tool verified and sent.
  function showImage(msg) {
    if (imageEmpty && imageEmpty.parentNode) imageEmpty.remove();
    dashboardImage.src = msg.url;
    dashboardImage.alt = msg.title || "";
    dashboardImage.style.display = "block";
    if (msg.title || msg.description) {
      imageCaption.textContent = msg.title ? `${msg.title}${msg.description ? " — " + msg.description : ""}` : msg.description;
      imageCaption.style.display = "block";
    } else {
      imageCaption.style.display = "none";
    }
    if (msg.source_url) {
      imageSourceLink.href = msg.source_url;
      imageSourceLink.style.display = "inline-block";
    } else {
      imageSourceLink.style.display = "none";
    }
  }

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  // -------- stats --------

  function applyStats(d) {
    if (d.error) return;
    setGauge(cpuRing, cpuValue, d.cpu_percent);
    setGauge(ramRing, ramValue, d.memory_percent);
    cpuChart.push(d.cpu_percent || 0);
    ramChart.push(d.memory_percent || 0);
    ramUsed.textContent = `${d.memory_used_gb ?? "-"} / ${d.memory_total_gb ?? "-"} GB`;
    diskUsed.textContent = `${d.disk_used_gb ?? "-"} / ${d.disk_total_gb ?? "-"} GB (${Math.round(d.disk_percent || 0)}%)`;
    if (d.battery_percent != null) {
      const plug = d.battery_plugged ? "charging" : "on battery";
      batteryRow.style.display = "flex";
      batteryValue.textContent = `${Math.round(d.battery_percent)}% (${plug})`;
      tickerBattery.style.display = "inline";
      tickerBatteryVal.textContent = `${Math.round(d.battery_percent)}%`;
    }
  }

  fetch("/api/stats").then(r => r.json()).then(applyStats).catch(() => {});

  // -------- SSE stream --------

  function connect() {
    const src = new EventSource("/api/stream");

    src.onopen = () => {
      connIndicator.classList.add("live");
      connLabel.textContent = "Live";
    };

    src.onerror = () => {
      connIndicator.classList.remove("live");
      connLabel.textContent = "Reconnecting…";
    };

    src.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (!msg || !msg.type) return;

      switch (msg.type) {
        case "stats":
          applyStats(msg);
          break;
        case "state":
          setState(msg.state);
          break;
        case "turn":
          addTurn(msg.role, msg.text);
          break;
        case "tool":
          addActivity(msg.name, msg.args);
          break;
        case "image":
          showImage(msg);
          break;
      }
    };
  }

  connect();
  setState("idle");

  // -------- typed command box --------
  // Sends the command to the SAME live Assistant instance the wake-word/
  // tray path uses (see ui/web_dashboard/app.py's /api/command) - the
  // reply doesn't come back in this fetch response, it shows up in the
  // conversation feed above the normal way, over the SSE stream, exactly
  // like a voice command would.
  if (commandForm && commandInput) {
    commandForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = commandInput.value.trim();
      if (!text) return;

      commandInput.disabled = true;
      commandSend.disabled = true;

      fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      })
        .then(async (r) => {
          if (!r.ok) {
            const body = await r.json().catch(() => ({}));
            addTurn("ultron", body.error || "Couldn't send that command.");
          } else {
            commandInput.value = "";
          }
        })
        .catch(() => {
          addTurn("ultron", "Couldn't reach Ultron - is it still running?");
        })
        .finally(() => {
          commandInput.disabled = false;
          commandSend.disabled = false;
          commandInput.focus();
        });
    });
  }
})();
