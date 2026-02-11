/*
  WebTerm Widget
  Example:
  <script src="https://your-server/webterm.js?api_key=YOUR_KEY" defer></script>

  Optional query params:
  - api_base=https://your-server
  - position=left|right
  - audio=true|false
*/

(() => {
  const TAILWIND_SCRIPT = "https://cdn.tailwindcss.com";
  const FA_CSS = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css";

  function ensureStylesheet(href) {
    if ([...document.querySelectorAll("link")].some((link) => link.href.includes(href))) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }

  function ensureScript(src) {
    if ([...document.querySelectorAll("script")].some((script) => script.src.includes(src))) return;
    const script = document.createElement("script");
    script.src = src;
    document.head.appendChild(script);
  }

  function getWidgetScriptConfig() {
    const script =
      document.currentScript ||
      [...document.querySelectorAll("script")].find((s) => /webterm\.js(\?|$)/.test(s.src));

    if (!script || !script.src) {
      return {
        apiBase: "http://127.0.0.1:5050",
        apiKey: "",
        position: "right",
        audioEnabled: true,
      };
    }

    const scriptUrl = new URL(script.src, window.location.href);
    const apiBase = scriptUrl.searchParams.get("api_base") || scriptUrl.origin;
    const apiKey = scriptUrl.searchParams.get("api_key") || "";
    const position = scriptUrl.searchParams.get("position") === "left" ? "left" : "right";
    const audioParam = scriptUrl.searchParams.get("audio");

    return {
      apiBase: apiBase.replace(/\/$/, ""),
      apiKey,
      position,
      audioEnabled: audioParam == null ? true : audioParam.toLowerCase() !== "false",
    };
  }

  const config = getWidgetScriptConfig();
  const MAX_AUDIO_LEN = 10;

  ensureScript(TAILWIND_SCRIPT);
  ensureStylesheet(FA_CSS);

  const rootPosition = config.position === "right" ? "right-5" : "left-5";

  const template = `
  <style>
    #wt-root * { box-sizing: border-box; }
    #wt-root .wt-scroll::-webkit-scrollbar { width: 7px; }
    #wt-root .wt-scroll::-webkit-scrollbar-thumb {
      background: rgba(255,255,255,.25);
      border-radius: 9999px;
    }
    #wt-root .wt-fade-in {
      animation: wtFade .18s ease;
    }
    @keyframes wtFade {
      from { opacity: .25; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>

  <div id="wt-root" class="fixed ${rootPosition} bottom-5 z-[2147483000] text-white">
    <button id="wt-launcher" class="group flex items-center gap-2 rounded-full border border-sky-300/30 bg-slate-900/85 px-4 py-2 shadow-2xl backdrop-blur-lg transition hover:-translate-y-0.5 hover:bg-slate-800/90">
      <span class="inline-flex h-2 w-2 rounded-full bg-emerald-400"></span>
      <span class="font-semibold tracking-wide">WebTerm</span>
      <i class="fa-solid fa-comment-dots text-sky-300"></i>
    </button>

    <section id="wt-panel" class="hidden mt-3 w-[360px] max-w-[calc(100vw-2.5rem)] overflow-hidden rounded-2xl border border-white/15 bg-gradient-to-b from-slate-900/95 to-slate-950/95 shadow-2xl backdrop-blur-xl">
      <header class="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <div class="text-sm font-semibold tracking-wide">WebTerm Assistant</div>
          <div id="wt-conn" class="text-[11px] text-slate-300">Connecting...</div>
        </div>
        <button id="wt-close" class="rounded-md px-2 py-1 text-slate-300 transition hover:bg-white/10 hover:text-white">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </header>

      <div id="wt-messages" class="wt-scroll h-80 space-y-3 overflow-y-auto px-4 py-3 text-sm"></div>

      <form id="wt-form" class="border-t border-white/10 px-3 py-3">
        <div class="flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-2 py-2">
          <input id="wt-input" type="text" placeholder="Ask about this website..." class="w-full bg-transparent px-2 text-sm text-white placeholder:text-slate-400 focus:outline-none" />
          ${
            config.audioEnabled
              ? '<button id="wt-audio" type="button" class="h-8 w-8 shrink-0 rounded-lg border border-white/20 text-slate-200 transition hover:bg-white/10"><i class="fa-solid fa-wave-square"></i></button>'
              : ""
          }
          <button id="wt-send" type="submit" class="h-8 w-8 shrink-0 rounded-lg bg-sky-500 text-white transition hover:bg-sky-400">
            <i class="fa-solid fa-paper-plane"></i>
          </button>
        </div>
      </form>
    </section>
  </div>
  `;

  document.addEventListener("DOMContentLoaded", () => {
    document.body.insertAdjacentHTML("beforeend", template.trim());

    const launcher = document.getElementById("wt-launcher");
    const panel = document.getElementById("wt-panel");
    const closeBtn = document.getElementById("wt-close");
    const connLabel = document.getElementById("wt-conn");
    const messagesEl = document.getElementById("wt-messages");
    const form = document.getElementById("wt-form");
    const input = document.getElementById("wt-input");
    const sendBtn = document.getElementById("wt-send");
    const audioBtn = document.getElementById("wt-audio");

    let awaitingReply = false;
    let historySignature = "";
    let mediaStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let recordTimer = null;

    function setConn(text, good = false) {
      connLabel.textContent = text;
      connLabel.className = good ? "text-[11px] text-emerald-300" : "text-[11px] text-slate-300";
    }

    function openPanel() {
      panel.classList.remove("hidden");
      panel.classList.add("wt-fade-in");
      input.focus();
    }

    function closePanel() {
      panel.classList.add("hidden");
    }

    launcher.addEventListener("click", () => {
      if (panel.classList.contains("hidden")) openPanel();
      else closePanel();
    });
    closeBtn.addEventListener("click", closePanel);

    function appendBubble(text, side = "left", link = false, button = false) {
      if (!text) return;

      if (link && side === "left") {
        const target = text.trim();
        if (target && window.location.href !== target) window.location.assign(target);
        return;
      }

      if (button && side === "left") {
        const selector = text.trim();
        if (!selector) return;
        clickElementWithFallback(selector);
        return;
      }

      const bubble = document.createElement("div");
      bubble.className =
        "max-w-[82%] rounded-xl border px-3 py-2 whitespace-pre-wrap break-words " +
        (side === "right"
          ? "ml-auto border-sky-300/35 bg-sky-400/15"
          : "border-white/20 bg-white/8");
      bubble.textContent = text;
      messagesEl.appendChild(bubble);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function renderHistory(messages) {
      messagesEl.innerHTML = "";
      messages.forEach((msg) => {
        const side = msg.role === "user" ? "right" : "left";
        appendBubble(msg.text, side, msg.link === true, msg.button === true);
      });
    }

    function getElementNavigationUrl(el) {
      if (!el) return null;
      if (el.tagName === "A" && el.href) return el.href;
      const anchor = el.closest && el.closest("a[href]");
      if (anchor && anchor.href) return anchor.href;
      const attrs = ["data-url", "data-href", "href"];
      for (const attr of attrs) {
        const value = el.getAttribute && el.getAttribute(attr);
        if (value && /^https?:\/\//i.test(value)) return value;
      }
      return null;
    }

    function clickElementWithFallback(selector, retries = 5) {
      let target;
      try {
        target = document.querySelector(selector);
      } catch {
        appendBubble(`[Bad selector: ${selector}]`, "left");
        return;
      }

      if (!target) {
        if (retries > 0) {
          setTimeout(() => clickElementWithFallback(selector, retries - 1), 200);
        } else {
          appendBubble(`[Element not found: ${selector}]`, "left");
        }
        return;
      }

      const url = getElementNavigationUrl(target);
      if (url) {
        if (window.location.href !== url) window.location.assign(url);
        return;
      }

      try {
        target.click();
        appendBubble(`[Clicked ${selector}]`, "left");
      } catch {
        appendBubble(`[Could not click: ${selector}]`, "left");
      }
    }

    async function postMessage(text) {
      awaitingReply = true;
      input.disabled = true;
      sendBtn.disabled = true;

      try {
        const response = await fetch(`${config.apiBase}/chat/send`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": config.apiKey,
          },
          body: JSON.stringify({ message: text, link: window.location.href }),
        });
        const data = await response.json();
        if (!data.ok) return;

        if (data.reply) {
          appendBubble(data.reply, "left", data.link === true, data.button === true);
        }
      } catch (error) {
        console.error("[WebTerm] chat/send failed", error);
      } finally {
        awaitingReply = false;
        input.disabled = false;
        sendBtn.disabled = false;
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (awaitingReply) return;

      const text = (input.value || "").trim();
      if (!text) return;

      appendBubble(text, "right");
      input.value = "";
      await postMessage(text);
    });

    async function pollHistory() {
      try {
        const response = await fetch(`${config.apiBase}/chat/history`, {
          headers: { "X-API-Key": config.apiKey },
        });

        if (!response.ok) {
          setConn("Offline");
          return;
        }

        const data = await response.json();
        if (!data.ok || !Array.isArray(data.messages)) {
          setConn("Connected", true);
          return;
        }

        setConn("Connected", true);

        const signature = JSON.stringify(data.messages);
        if (signature !== historySignature) {
          historySignature = signature;
          awaitingReply = false;
          input.disabled = false;
          sendBtn.disabled = false;
          renderHistory(data.messages);
        }
      } catch {
        setConn("Offline");
      }
    }

    async function sendAudio(blob) {
      const formData = new FormData();
      formData.append("audio", blob, "clip.webm");
      formData.append("link", window.location.href);

      try {
        const response = await fetch(`${config.apiBase}/chat/audio?tts=true&voice=alloy`, {
          method: "POST",
          headers: { "X-API-Key": config.apiKey },
          body: formData,
        });

        const data = await response.json();
        if (!data.ok) return;

        if (data.transcript) appendBubble(data.transcript, "right");
        if (data.reply) appendBubble(data.reply, "left", data.link === true, data.button === true);

        if (data.reply_audio_b64) {
          const audio = new Audio(`data:audio/mp3;base64,${data.reply_audio_b64}`);
          audioBtn && audioBtn.classList.add("bg-sky-400/40");
          try {
            await audio.play();
          } finally {
            audioBtn && audioBtn.classList.remove("bg-sky-400/40");
          }
        }
      } catch (error) {
        console.error("[WebTerm] chat/audio failed", error);
      } finally {
        audioBtn && audioBtn.classList.remove("bg-red-500/40");
      }
    }

    async function startRecording() {
      if (!audioBtn) return;
      if (mediaRecorder && mediaRecorder.state === "recording") return;

      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(mediaStream, { mimeType: "audio/webm" });
      } catch (error) {
        console.error("[WebTerm] getUserMedia failed", error);
        return;
      }

      audioChunks = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) audioChunks.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        try {
          mediaStream && mediaStream.getTracks().forEach((track) => track.stop());
        } catch {}
        const blob = new Blob(audioChunks, { type: "audio/webm" });
        await sendAudio(blob);
      };

      mediaRecorder.start();
      audioBtn.classList.add("bg-red-500/40");

      if (recordTimer) clearTimeout(recordTimer);
      recordTimer = setTimeout(() => {
        if (mediaRecorder && mediaRecorder.state === "recording") {
          mediaRecorder.stop();
        }
      }, MAX_AUDIO_LEN * 1000);
    }

    function stopRecording() {
      if (recordTimer) {
        clearTimeout(recordTimer);
        recordTimer = null;
      }
      if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
      }
      audioBtn && audioBtn.classList.remove("bg-red-500/40");
    }

    if (audioBtn) {
      audioBtn.addEventListener("click", async () => {
        if (!mediaRecorder || mediaRecorder.state !== "recording") {
          await startRecording();
        } else {
          stopRecording();
        }
      });
    }

    pollHistory();
    setInterval(pollHistory, 2000);
  });
})();
