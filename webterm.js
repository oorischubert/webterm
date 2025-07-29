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
    .chat-scroll::-webkit-scrollbar{width:8px}
    .chat-scroll::-webkit-scrollbar-thumb{background:rgba(255,255,255,.25);border-radius:9999px}
    .chat-scroll{scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.25) transparent}
  </style>
  <div id="chat-root" class="fixed bottom-4 ${posClass} z-50">
    <button id="chat-toggle" class="flex items-center gap-2 px-4 py-2 rounded-full shadow-lg bg-white/20 backdrop-blur-md border border-white/30 text-white font-semibold hover:bg-white/30 focus:outline-none transition">
      <i class="fa-solid fa-message"></i><span>Chat</span>
    </button>
    <div id="chat-panel" class="hidden mt-3 w-80 sm:w-96 max-h-[70vh] flex flex-col bg-white/10 backdrop-blur-lg border border-white/20 text-white rounded-2xl shadow-xl overflow-hidden translate-y-4 opacity-0 transition-all">
      <div class="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <h2 class="font-bold text-lg">WebTerm</h2>
        <button id="chat-close" class="text-white/70 hover:text-white"><i class="fa-solid fa-xmark text-xl"></i></button>
      </div>
      <div id="chat-messages" class="flex-1 px-4 py-3 space-y-3 overflow-y-auto chat-scroll text-sm leading-relaxed">
        <div class="bg-white/10 p-3 rounded-lg max-w-[80%]">Hi! Ask me anything…</div>
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

    // Placeholder send handler
    document.getElementById("chat-form").addEventListener("submit", e => {
      e.preventDefault();
      const input = document.getElementById("chat-input");
      const msg   = input.value.trim();
      if (!msg) return;
      addBubble(msg, "right");
      input.value = "";
      // TODO: send to backend
    });

    function addBubble(text, side="left") {
      const wrap = document.createElement("div");
      // Use frosted style for both sides; right bubbles are aligned right (ml-auto)
      wrap.className = `p-3 rounded-lg max-w-[80%] bg-white/10 ${side==="right"?"ml-auto":""}`;
      wrap.textContent = text;
      document.getElementById("chat-messages").appendChild(wrap);
      const box = document.getElementById("chat-messages");
      box.scrollTop = box.scrollHeight;
    }
  });
})();