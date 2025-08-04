/* Chatbot Widget v1.0
   Drop a single line into any page below <head>:
   <script src="webterm.js" defer></script>
   Tailwind CDN + FontAwesome CDN are injected automatically if not present.
*/

(() => {
  // --- Config ---
  const TAILWIND_CSS = "https://cdnjs.cloudflare.com/ajax/libs/tailwindcss/3.4.4/tailwind.min.css";
  const FA_CSS       = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css";

  // Set to "right" or "left" for the corner the widget should dock to
  const POSITION = "right";
  const posClass = POSITION === "right" ? "right-4" : "left-4";

  // Base URL of your Flask backend (""
  // means same origin).
  // If you're serving the HTML on :5500 and the API on :5050, set:
  //   const API_BASE = "http://127.0.0.1:5050";
  const API_BASE = "http://127.0.0.1:5050";
  const API_KEY = "012245";

  // Enable/disable the in‑toggle waveform button
  const AUDIO = true; // set to false to hide audio button

  // Max audio recording length (seconds)
  const MAX_AUDIO_LEN = 10;

  // Re‑usable macOS‑style 5‑bar waveform SVG (rounded bars)
  const WAVEFORM_SVG = `
    <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="currentColor">
      <rect x="3"  y="9"  width="2" height="6"  rx="1"></rect>
      <rect x="7"  y="6"  width="2" height="12" rx="1"></rect>
      <rect x="11" y="3"  width="2" height="18" rx="1"></rect>
      <rect x="15" y="6"  width="2" height="12" rx="1"></rect>
      <rect x="19" y="9"  width="2" height="6"  rx="1"></rect>
    </svg>`;

  // --- inject external CSS/JS once ---
  function ensureLink(href) {
    if ([...document.querySelectorAll("link")].some(l => l.href.includes(href))) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }
  function ensureScript(src) {
    if ([...document.scripts].some(s => s.src.includes(src))) return;
    const script = document.createElement("script");
    script.src = src;
    script.crossOrigin = "anonymous";
    document.head.appendChild(script);
  }
  ensureLink(TAILWIND_CSS);
  ensureLink(FA_CSS);

  // --- widget HTML ---
  const tpl = /*html*/`
  <style>
    /* Frosted custom scrollbar */
    .chat-scroll::-webkit-scrollbar{
      width:6px
    }
    .chat-scroll::-webkit-scrollbar-track{
      background:transparent
    }
    .chat-scroll::-webkit-scrollbar-thumb{
      background:rgba(255,255,255,.35);
      border-radius:9999px;
      backdrop-filter:blur(4px)
    }
    .chat-scroll{
      scrollbar-width:thin;
      scrollbar-color:rgba(255,255,255,.35) transparent
    }
    /* Waveform active (recording) state */
    .wf-active{
      background:rgba(255,0,0,.35) !important;
      border-color:rgba(255,0,0,.45) !important;
      transition:background .25s ease,border-color .25s ease;
    }
    /* Waveform playback (assistant speaking) */
    .wf-play{
      background: rgba(15, 92, 192, 0.35) !important; /* blue at 35% opacity to match the red's 35% */
      border-color: rgba(15, 92, 192, 0.45) !important; /* blue at 45% opacity to match the red's 45% */
      transition: background .25s ease, border-color .25s ease;
    }
  </style>
  <div id="chat-root" class="fixed bottom-4 ${posClass} z-50">
    <div id="chat-toggle" class="flex items-center gap-2 px-4 py-2 rounded-full shadow-lg bg-white/20 backdrop-blur-md border border-white/30 text-white font-semibold hover:bg-white/30 focus:outline-none transition cursor-pointer">
      <!-- optional waveform circle -->
      ${AUDIO ? `
        <button id="wave-btn" class="-ml-1 flex-shrink-0 w-7 h-7 flex items-center justify-center rounded-full bg-white/25 border border-white/40 hover:bg-white/35 transition">
          ${WAVEFORM_SVG}
        </button>
      ` : ''}
      <i class="fa-solid fa-message"></i><span>Chat</span>
    </div>
    <div id="chat-panel" class="hidden mt-3 w-80 sm:w-96 max-h-[70vh] flex flex-col bg-white/10 backdrop-blur-lg border border-white/20 text-white rounded-2xl shadow-xl overflow-hidden translate-y-4 opacity-0 transition-all">
      <div class="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <h2 class="font-bold text-lg">WebTerm</h2>
        <button id="chat-close" class="text-white/70 hover:text-white"><i class="fa-solid fa-xmark text-xl"></i></button>
      </div>
      <div id="chat-messages" class="flex-1 px-4 py-3 space-y-3 overflow-y-auto chat-scroll text-sm leading-relaxed">
      </div>
      <form id="chat-form" class="border-t border-white/10">
        <div class="flex items-center gap-2 px-3 py-2">
          <input id="chat-input" type="text" placeholder="Type your message…" class="flex-1 bg-transparent outline-none placeholder-white/40">
          <button type="submit" class="px-3 py-1.5 rounded-md bg-white/20 backdrop-blur-md border border-white/30 hover:bg-white/30 transition">
            <i class="fa-solid fa-paper-plane text-sm"></i>
          </button>
        </div>
      </form>
    </div>
  </div>`;

  document.addEventListener("DOMContentLoaded", () => {
    // Inject widget
    document.body.insertAdjacentHTML("beforeend", tpl.trim());

    const toggle   = document.getElementById("chat-toggle");
    const panel    = document.getElementById("chat-panel");
    const closeBtn = document.getElementById("chat-close");

    // expose waveBtn for other handlers (e.g., form submit)
    let waveBtn = null;

    // If AUDIO enabled, attach handler
    if (AUDIO) {
      waveBtn = document.getElementById("wave-btn");
      let recording = false;

      // --- Audio capture state ---
      let mediaStream = null;
      let mediaRecorder = null;
      let audioChunks = [];
      let recordTimer = null;

      async function startRecording() {
        if (mediaRecorder && mediaRecorder.state === "recording") return;
        try {
          mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          mediaRecorder = new MediaRecorder(mediaStream, { mimeType: "audio/webm" });
        } catch (err) {
          console.error("[audio] getUserMedia failed:", err);
          waveBtn.classList.remove("wf-active");
          return;
        }

        audioChunks = [];
        mediaRecorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) audioChunks.push(e.data);
        };
        mediaRecorder.onstop = async () => {
          // Stop tracks
          try { mediaStream.getTracks().forEach(t => t.stop()); } catch {}
          // Build Blob and send to backend
          const blob = new Blob(audioChunks, { type: "audio/webm" });
          await sendAudio(blob);
        };

        mediaRecorder.start();
        waveBtn.classList.add("wf-active"); // red while recording

        // Safety auto‑stop at MAX_AUDIO_LEN
        if (recordTimer) clearTimeout(recordTimer);
        recordTimer = setTimeout(() => {
          if (mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
            waveBtn.classList.remove("wf-active");
          }
        }, MAX_AUDIO_LEN * 1000);
      }

      function stopRecording() {
        if (recordTimer) { clearTimeout(recordTimer); recordTimer = null; }
        if (mediaRecorder && mediaRecorder.state === "recording") {
          mediaRecorder.stop();
        }
        waveBtn.classList.remove("wf-active");
      }

      async function sendAudio(blob) {
        // Build multipart/form-data
        const fd = new FormData();
        fd.append("audio", blob, "clip.webm");  // filename hint; server writes temp with suffix
        fd.append("link", window.location.href);  // current page URL
        
        try {
          const resp = await fetch(`${API_BASE}/chat/audio?tts=true&voice=alloy`, {
            method: "POST",
            headers: { "X-API-Key": API_KEY },
            body: fd
          });
          const data = await resp.json();
          if (!data.ok) {
            console.error("[audio] server error:", data.error || data);
            return;
          }
          
          // Debug: Log the full response to see what we're getting
          console.log("[DEBUG] Audio response data:", data);
          console.log("[DEBUG] data.reply:", data.reply);
          console.log("[DEBUG] data.link:", data.link);
          console.log("[DEBUG] data.button:", data.button);
          
          // Show transcript (user bubble) if present
          if (data.transcript) addBubble(data.transcript, "right");
          // If link, redirect; if button, click; otherwise show bubble
          if (data.reply) addBubble(data.reply, "left", data.link === true, data.button === true);

          // If reply audio present, play it and show blue state while playing
          if (data.reply_audio_b64) {
            try {
              const audio = new Audio(`data:audio/mp3;base64,${data.reply_audio_b64}`);
              waveBtn.classList.add("wf-play");
              await audio.play();
              audio.addEventListener("ended", () => waveBtn.classList.remove("wf-play"), { once: true });
              audio.addEventListener("pause", () => waveBtn.classList.remove("wf-play"), { once: true });
            } catch (e) {
              waveBtn.classList.remove("wf-play");
              console.error("[audio] playback failed:", e);
            }
          }
        } catch (err) {
          console.error("[audio] network error:", err);
        } finally {
          // Ensure flags reset
          waveBtn.classList.remove("wf-active");
        }
      }

      waveBtn.addEventListener("click", async (e) => {
        e.stopPropagation(); // don’t toggle chat open/close
        try {
          // If currently playing, ignore clicks
          if (waveBtn.classList.contains("wf-play")) return;

          // Toggle recording
          if (!mediaRecorder || mediaRecorder.state !== "recording") {
            await startRecording();  // turns red
          } else {
            stopRecording();         // stops + sends; removes red
          }
        } catch (err) {
          console.error("[audio] click error:", err);
        }
      });
    }

    let awaitingReply = false;      // blocks sending until assistant responds
    const inputField  = document.getElementById("chat-input");
    const sendButton  = document.querySelector("#chat-form button[type=submit]");

    function openChat() {
      toggle.classList.add("hidden");                                  // hide button
      panel.classList.remove("hidden", "opacity-0", "translate-y-4");  // show panel
    }
    function closeChat() {
      panel.classList.add("opacity-0", "translate-y-4");               // start fade
      setTimeout(() => {
        panel.classList.add("hidden");                                 // hide panel
        toggle.classList.remove("hidden");                             // show button
      }, 200); // match transition
    }
    toggle.addEventListener("click", () => {
      panel.classList.contains("hidden") ? openChat() : closeChat();
    });
    closeBtn.addEventListener("click", closeChat);

    // Placeholder send handler (calls backend then shows both bubbles)
    document.getElementById("chat-form").addEventListener("submit", e => {
      e.preventDefault();
      if (awaitingReply) return;                    // prevent double‑send
      // Prevent sending while **recording or playing back**
      if (AUDIO && waveBtn && (waveBtn.classList.contains("wf-active") || waveBtn.classList.contains("wf-play"))) {
        return;
      }

      const msg = inputField.value.trim();
      if (!msg) return;

      // --- ADD THIS: Show user bubble instantly
      addBubble(msg, "right");

      awaitingReply = true;
      inputField.value = "";
      inputField.disabled = true;
      sendButton.disabled = true;

      fetch(`${API_BASE}/chat/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": API_KEY},
        body: JSON.stringify({ message: msg, link: window.location.href})
      })
      .then(r => r.json())
      .then(data => {
        awaitingReply = false;
        inputField.disabled = false;
        sendButton.disabled = false;

        if (!data.ok) return;
        // Debug: Log the full response to see what we're getting
          console.log("[DEBUG] Assistant response data:", data);
          console.log("[DEBUG] data.reply:", data.reply);
          console.log("[DEBUG] data.link:", data.link);
          console.log("[DEBUG] data.button:", data.button);
        // Assistant response: redirect if link, otherwise bubble
        if (data.reply) addBubble(data.reply, "left", data.link === true, data.button === true);
      })
      .catch(console.error);
    });

    // --- navigation helpers (avoid Safari popup blocking) ---
    function _extractUrlFromElement(el){
      if (!el) return null;
      // 1) Direct anchor
      if (el.tagName === 'A' && el.href) return el.href;
      // 2) Closest anchor parent
      const a = el.closest && el.closest('a[href]');
      if (a && a.href) return a.href;
      // 3) Common data attributes
      const attrNames = ['data-url','data-href','href'];
      for (const name of attrNames){
        if (!el.getAttribute) continue;
        const v = el.getAttribute(name);
        if (v && /^https?:\/\//i.test(v)) return v;
      }
      // 4) Try inline onclick with a URL
      if (el.getAttribute){
        const onclick = el.getAttribute('onclick');
        if (onclick){
          const m = onclick.match(/https?:\/\/[^'"\)\s]+/i);
          if (m) return m[0];
        }
      }
      return null;
    }

    function _navigateSameTab(url){
      try{
        if (url && typeof url === 'string'){
          if (window.location.href !== url) window.location.assign(url);
          return true;
        }
      }catch(e){ console.warn('navigateSameTab failed', e); }
      return false;
    }

    function _tryClickWithFallback(selector, attempts=5){
      const el = document.querySelector(selector);
      if (!el){
        if (attempts > 0){
          setTimeout(() => _tryClickWithFallback(selector, attempts-1), 200);
        } else {
          addBubble(`[Element not found: ${selector}]`, 'left');
        }
        return;
      }
      // Prefer navigation if we can determine a URL
      const url = _extractUrlFromElement(el);
      if (url){
        if (_navigateSameTab(url)) return; // avoids popup block
      }
      // As a last resort, attempt a real click
      try{
        el.click();
        addBubble(`[Clicked ${selector}]`, 'left');
      }catch(err){
        console.error('Programmatic click failed:', err);
        addBubble(`[Could not click: ${selector}]`, 'left');
      }
    }

    // --- helper to create a chat bubble in the DOM or redirect if link ---
    function addBubble(text, side = "left", link = false, button = false) {

      /* Link protocol */
      if (link && side === "left") {
        const target = text.trim();
        if (window.location.href !== target) window.location.href = target;
        return;
      }

      /* Button-click protocol (navigate same tab if link-like to avoid popup block) */
      if (button && side === "left") {
        const selector = text.trim();
        // Validate selector first to avoid throwing on querySelector
        try { document.querySelector(selector); }
        catch(err){
          console.error("Bad selector:", selector, err);
          addBubble(`[Bad selector: ${selector}]`, "left");
          return;
        }
        _tryClickWithFallback(selector, 5);
        return;  // don’t render the original text
      }

      /* Normal bubble rendering */
      console.log("Adding bubble:", text, "side:", side);
      const wrap = document.createElement("div");
      wrap.className =
        `p-3 rounded-lg max-w-[80%] bg-white/10 whitespace-pre-line break-words ` +
        `${side === "right" ? "ml-auto" : ""}`;
      wrap.textContent = text;
      const box = document.getElementById("chat-messages");
      box.appendChild(wrap);
      box.scrollTop = box.scrollHeight;
    }

    // Clears message box and re-renders all messages
    function renderHistory(historyArray) {
      const box = document.getElementById("chat-messages");
      box.innerHTML = "";
      historyArray.forEach(m => {
        const side = m.role === "user" ? "right" : "left";
        addBubble(m.text, side, m.link === true, m.button === true);
      });
    }

    /* --- live sync w/ backend history --- */
    let lastSignature = "";   // JSON string of last seen history
    function pollHistory() {
      fetch(`${API_BASE}/chat/history`, {
        headers: {
          "X-API-Key": API_KEY
        }
      })
        .then(r => r.json())
        .then(data => {
          if (!data.ok || !Array.isArray(data.messages)) return;
          const sig = JSON.stringify(data.messages);
          if (sig !== lastSignature) {     // changed (new or cleared)
            lastSignature = sig;
            awaitingReply = false;            // assistant has responded externally
            inputField.disabled = false;
            sendButton.disabled = false;
            renderHistory(data.messages);
          }
        })
        .catch(console.error);
    }

    // Initial load & start polling every 2 s
    pollHistory();
    setInterval(pollHistory, 2000);
  });
})();