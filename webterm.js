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
  const MAX_AUDIO_LEN = 10;
  const DEFAULT_API_KEY = "012345";

  const WAVEFORM_SVG = `
    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor">
      <rect x="3"  y="9"  width="2" height="6"  rx="1"></rect>
      <rect x="7"  y="6"  width="2" height="12" rx="1"></rect>
      <rect x="11" y="3"  width="2" height="18" rx="1"></rect>
      <rect x="15" y="6"  width="2" height="12" rx="1"></rect>
      <rect x="19" y="9"  width="2" height="6"  rx="1"></rect>
    </svg>
  `;

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
      [...document.querySelectorAll("script")].find((candidate) =>
        /webterm\.js(\?|$)/.test(candidate.src),
      );

    if (!script || !script.src) {
      return {
        apiBase: "http://127.0.0.1:5050",
        apiKey: DEFAULT_API_KEY,
        position: "right",
        audioEnabled: true,
      };
    }

    const scriptUrl = new URL(script.src, window.location.href);
    const apiBase = scriptUrl.searchParams.get("api_base") || scriptUrl.origin;
    const apiKey = scriptUrl.searchParams.get("api_key") || DEFAULT_API_KEY;
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
  ensureScript(TAILWIND_SCRIPT);
  ensureStylesheet(FA_CSS);

  const rootPosition = config.position === "right" ? "right-4" : "left-4";
  const template = `
  <style>
    #wt-root * { box-sizing: border-box; }

    #wt-root .wt-scroll::-webkit-scrollbar { width: 6px; }
    #wt-root .wt-scroll::-webkit-scrollbar-track { background: transparent; }
    #wt-root .wt-scroll::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.35);
      border-radius: 9999px;
    }
    #wt-root .wt-scroll {
      scrollbar-width: thin;
      scrollbar-color: rgba(255, 255, 255, 0.35) transparent;
    }

    #wt-root .wt-wave-recording {
      background: rgba(255, 0, 0, 0.35) !important;
      border-color: rgba(255, 0, 0, 0.45) !important;
    }
    #wt-root .wt-wave-playing {
      background: rgba(15, 92, 192, 0.35) !important;
      border-color: rgba(15, 92, 192, 0.45) !important;
    }
  </style>

  <div id="wt-root" class="fixed bottom-4 ${rootPosition} z-[2147483000] text-white">
    <div id="wt-launcher" class="flex cursor-pointer items-center gap-2 rounded-full border border-white/30 bg-white/20 px-4 py-2 shadow-lg backdrop-blur-md transition hover:bg-white/30">
      ${
        config.audioEnabled
          ? `
        <button id="wt-wave" type="button" class="-ml-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-white/40 bg-white/25 transition hover:bg-white/35">
          ${WAVEFORM_SVG}
        </button>
      `
          : ""
      }
      <span class="font-semibold">WebTerm</span>
    </div>

    <section id="wt-panel" class="hidden mt-3 flex max-h-[70vh] w-80 max-w-[calc(100vw-2rem)] translate-y-4 flex-col overflow-hidden rounded-2xl border border-white/20 bg-white/10 opacity-0 shadow-xl backdrop-blur-lg transition-all duration-200 sm:w-96">
      <header class="relative border-b border-white/10 px-4 py-3">
        <h2 class="text-center text-lg font-bold">WebTerm</h2>
        <button id="wt-close" type="button" class="absolute right-4 top-1/2 -translate-y-1/2 text-white/70 transition hover:text-white">
          <i class="fa-solid fa-xmark text-xl"></i>
        </button>
      </header>

      <div id="wt-messages" class="wt-scroll flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm leading-relaxed"></div>

      <form id="wt-form" class="border-t border-white/10">
        <div class="flex items-center gap-2 px-3 py-2">
          <input id="wt-input" type="text" placeholder="Type your message..." class="flex-1 bg-transparent outline-none placeholder-white/40" />
          ${
            config.audioEnabled
              ? `
          <button id="wt-audio" type="button" class="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full border border-white/35 bg-white/20 transition hover:bg-white/30">
            <i class="fa-solid fa-microphone text-xs"></i>
          </button>
          `
              : ""
          }
          <button id="wt-send" type="submit" class="rounded-full border border-white/30 bg-white/20 px-4 py-1.5 font-medium transition hover:bg-white/30">
            Send
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
    const messagesEl = document.getElementById("wt-messages");
    const form = document.getElementById("wt-form");
    const input = document.getElementById("wt-input");
    const sendBtn = document.getElementById("wt-send");
    const waveBtn = document.getElementById("wt-wave");
    const panelAudioBtn = document.getElementById("wt-audio");
    const audioButtons = [waveBtn, panelAudioBtn].filter(Boolean);

    let awaitingReply = false;
    let historySignature = "";
    let mediaStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let recordTimer = null;

    function openPanel() {
      launcher.classList.add("hidden");
      panel.classList.remove("hidden");
      requestAnimationFrame(() => {
        panel.classList.remove("opacity-0", "translate-y-4");
        input.focus();
      });
    }

    function closePanel() {
      panel.classList.add("opacity-0", "translate-y-4");
      setTimeout(() => {
        panel.classList.add("hidden");
        launcher.classList.remove("hidden");
      }, 200);
    }

    function addAudioState(className) {
      audioButtons.forEach((button) => button.classList.add(className));
    }

    function removeAudioState(className) {
      audioButtons.forEach((button) => button.classList.remove(className));
    }

    function hasAudioState(className) {
      return audioButtons.some((button) => button.classList.contains(className));
    }

    launcher.addEventListener("click", () => {
      if (panel.classList.contains("hidden")) openPanel();
      else closePanel();
    });

    closeBtn.addEventListener("click", closePanel);

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
        "max-w-[80%] rounded-lg bg-white/10 p-3 whitespace-pre-line break-words " +
        (side === "right" ? "ml-auto" : "");
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
      if (hasAudioState("wt-wave-recording") || hasAudioState("wt-wave-playing")) {
        return;
      }

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
        if (!response.ok) return;

        const data = await response.json();
        if (!data.ok || !Array.isArray(data.messages)) return;

        const signature = JSON.stringify(data.messages);
        if (signature !== historySignature) {
          historySignature = signature;
          awaitingReply = false;
          input.disabled = false;
          sendBtn.disabled = false;
          renderHistory(data.messages);
        }
      } catch {
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

        if (data.reply_audio_b64 && audioButtons.length > 0) {
          const audio = new Audio(`data:audio/mp3;base64,${data.reply_audio_b64}`);
          const clearPlaying = () => removeAudioState("wt-wave-playing");
          addAudioState("wt-wave-playing");
          audio.addEventListener("ended", clearPlaying, { once: true });
          audio.addEventListener("pause", clearPlaying, { once: true });
          try {
            await audio.play();
          } catch {
            clearPlaying();
          }
        }
      } catch (error) {
        console.error("[WebTerm] chat/audio failed", error);
      } finally {
        removeAudioState("wt-wave-recording");
      }
    }

    async function startRecording() {
      if (audioButtons.length === 0) return;
      if (hasAudioState("wt-wave-playing")) return;
      if (mediaRecorder && mediaRecorder.state === "recording") return;

      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(mediaStream, { mimeType: "audio/webm" });
      } catch (error) {
        console.error("[WebTerm] getUserMedia failed", error);
        removeAudioState("wt-wave-recording");
        return;
      }

      audioChunks = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) audioChunks.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        try {
          mediaStream && mediaStream.getTracks().forEach((track) => track.stop());
        } catch {
        }
        const blob = new Blob(audioChunks, { type: "audio/webm" });
        await sendAudio(blob);
      };

      mediaRecorder.start();
      addAudioState("wt-wave-recording");

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
      removeAudioState("wt-wave-recording");
    }

    async function toggleAudio(event) {
      if (event) event.stopPropagation();
      if (!mediaRecorder || mediaRecorder.state !== "recording") {
        await startRecording();
      } else {
        stopRecording();
      }
    }

    if (waveBtn) {
      waveBtn.addEventListener("click", async (event) => {
        await toggleAudio(event);
      });
    }

    if (panelAudioBtn) {
      panelAudioBtn.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        await toggleAudio(event);
      });
    }

    pollHistory();
    setInterval(pollHistory, 2000);
  });
})();
