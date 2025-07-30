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

    // If AUDIO enabled, attach handler
    if (AUDIO) {
      const waveBtn = document.getElementById("wave-btn");
      let recording = false;
      waveBtn.addEventListener("click", (e) => {
        e.stopPropagation();          // don’t toggle chat open/close
        recording = !recording;
        waveBtn.classList.toggle("wf-active", recording);
        console.log("waveform pressed – recording:", recording);
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

        // Assistant response: redirect if link, otherwise bubble
        if (data.reply) addBubble(data.reply, "left", data.link === true, data.button === true);
      })
      .catch(console.error);
    });

    // --- helper to create a chat bubble in the DOM or redirect if link ---
    function addBubble(text, side = "left", link = false, button = false) {

      /* Link protocol */
      if (link && side === "left") {
        const target = text.trim();
        if (window.location.href !== target) window.location.href = target;
        return;
      }

        /* Button-click protocol */
        if (button && side === "left") {
          const selector = text.trim();
          try {
            const el = document.querySelector(selector);
            if (el) {
              el.click();
              addBubble(`[Clicked ${selector}]`, "left");
            } else {
              addBubble(`[Element not found: ${selector}]`, "left");
            }
          } catch (err) {  // invalid CSS selector
            console.error("Bad selector:", selector, err);
            addBubble(`[Bad selector: ${selector}]`, "left");
          }
          return;  // don’t render the original text
        }

        /* Normal bubble rendering */
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