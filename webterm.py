from __future__ import annotations

import argparse
import logging
import os
import re
import socket
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from functools import wraps
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, request, send_file

from utility.agent import Agent
from utility.agentToolKit import SiteScannerTool, SiteTree
from utility.assistant import Assistant


app = Flask(__name__)

# Silence Flask/Werkzeug request logs
app.logger.disabled = True
logging.getLogger("werkzeug").disabled = True
logging.getLogger("werkzeug.serving").disabled = True


def parse_bool(raw: object, default: bool = False) -> bool:
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def normalize_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        return value
    if value.startswith("//"):
        return "https:" + value
    return "https://" + value


def is_site_reachable(url: str, timeout: float = 6.0) -> bool:
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code >= 400 or response.status_code == 405:
            response = requests.get(url, timeout=timeout, stream=True)
        return response.status_code < 400
    except Exception:
        return False


def detect_server_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def site_label_from_url(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return url
    if not host:
        return url

    if ":" in host:
        host = host.split(":", 1)[0]

    parts = [part for part in host.split(".") if part]
    if parts and parts[0] == "www":
        parts = parts[1:]

    if len(parts) >= 2:
        tld = parts[-1]
        sld = parts[-2]
        if len(tld) == 2 and sld in {"co", "com", "org", "net", "edu", "gov", "ac"}:
            return parts[-3] if len(parts) >= 3 else sld
        return sld
    return parts[0] if parts else host


def path_segments(url: str) -> List[str]:
    try:
        path = urlparse(url).path
    except Exception:
        return []
    return [segment for segment in (path or "").split("/") if segment]


def iter_branches(tree: SiteTree) -> List[List[str]]:
    root = getattr(tree, "root_url", None)
    children = getattr(tree, "children", None)
    if not root or children is None:
        return []

    branches: List[List[str]] = []

    def walk(url: str, prefix: List[str]) -> None:
        kids = list(children.get(url, set()))
        if not kids:
            branches.append(prefix + [url])
            return
        for child in kids:
            walk(child, prefix + [url])

    walk(root, [])
    return branches


def tree_to_response_items(tree: SiteTree, root_url: str, scanner: SiteScannerTool) -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []
    branches = iter_branches(tree)
    site_label = site_label_from_url(root_url)
    root_parts = path_segments(root_url)

    root_title = site_label if not root_parts else " › ".join([site_label] + root_parts)
    root_progress = 0.0
    try:
        root_node = tree.nodes.get(scanner.normalize(root_url))
        if root_node and getattr(root_node, "desc", ""):
            root_progress = 1.0
    except Exception:
        root_progress = 0.0

    items.append({"root": root_url, "url": root_url, "text": root_title, "progress": root_progress})

    seen_urls = {root_url}
    for branch in branches:
        leaf = branch[-1]
        if leaf in seen_urls:
            continue
        seen_urls.add(leaf)

        leaf_parts = path_segments(leaf)
        rel = leaf_parts
        if root_parts and leaf_parts[: len(root_parts)] == root_parts:
            rel = leaf_parts[len(root_parts) :]

        label_parts = [site_label] + root_parts + rel
        title = " › ".join([part for part in label_parts if part]) if label_parts else site_label
        items.append({"root": root_url, "url": leaf, "text": title, "progress": 0.0})

    return items


@dataclass
class AppState:
    responses: List[Dict[str, object]] = field(default_factory=list)
    responses_lock: threading.Lock = field(default_factory=threading.Lock)
    chat_history: List[Dict[str, str]] = field(
        default_factory=lambda: [{"role": "assistant", "text": "Hi! Ask me anything."}]
    )
    chat_lock: threading.Lock = field(default_factory=threading.Lock)
    current_tree: Optional[SiteTree] = None
    current_root_url: Optional[str] = None
    agent_busy: bool = False
    agent_lock: threading.Lock = field(default_factory=threading.Lock)


# Runtime configuration (override using env or CLI)
API_KEY = os.getenv("WEBTERM_API_KEY", "dev-webterm-key")
AUTH_DISABLED = parse_bool(os.getenv("WEBTERM_DISABLE_AUTH", "false"), default=False)
PUBLIC_BASE_URL = os.getenv("WEBTERM_PUBLIC_BASE_URL", "").rstrip("/")

port = int(os.getenv("WEBTERM_PORT", "5050"))
debug_mode = parse_bool(os.getenv("WEBTERM_DEBUG", "false"), default=False)
max_tool_calls = int(os.getenv("WEBTERM_MAX_TOOL_CALLS", "2"))

site_scanner_tool = SiteScannerTool()
agent = Agent()
assistant = Assistant()
state = AppState()


def get_public_base_url() -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    return f"http://{detect_server_ip()}:{port}"


def build_embed_script() -> str:
    script_url = f"{get_public_base_url()}/webterm.js"
    return f'<script src="{script_url}?api_key={API_KEY}" defer></script>'


def get_status_payload() -> Dict[str, object]:
    with state.responses_lock:
        items = list(state.responses)

    tree_available = state.current_tree is not None
    node_count = state.current_tree.node_count() if state.current_tree else 0

    return {
        "ok": True,
        "busy": state.agent_busy,
        "root_url": state.current_root_url,
        "tree_available": tree_available,
        "node_count": node_count,
        "items_count": len(items),
        "embed_script": build_embed_script(),
        "public_base_url": get_public_base_url(),
    }


def extract_protocol_flags(reply_text: str) -> Tuple[str, bool, bool]:
    if not isinstance(reply_text, str):
        return str(reply_text), False, False

    clean = reply_text.strip()
    if clean.startswith("send_link:"):
        return clean[len("send_link:") :].strip(), True, False
    if clean.startswith("click_element:"):
        return clean[len("click_element:") :].strip(), False, True
    return reply_text, False, False


def require_api_key(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if request.method == "OPTIONS":
            return ("", 204)
        if AUTH_DISABLED:
            return view_func(*args, **kwargs)

        key = (
            request.headers.get("X-API-Key")
            or request.args.get("api_key")
            or ((request.get_json(silent=True) or {}).get("api_key") if request.is_json else None)
        )

        if key != API_KEY:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return view_func(*args, **kwargs)

    return wrapped


@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/webterm.js")
@require_api_key
def serve_webterm_js():
    return send_file("webterm.js", mimetype="application/javascript")


@app.route("/state", methods=["GET"])
@require_api_key
def get_state():
    return jsonify(get_status_payload())


@app.route("/embed", methods=["GET"])
@require_api_key
def get_embed():
    return jsonify({"ok": True, "embed_script": build_embed_script(), "public_base_url": get_public_base_url()})


@app.route("/tree", methods=["GET"])
@require_api_key
def get_tree():
    if not state.current_tree:
        return jsonify({"ok": False, "error": "No SiteTree available yet."}), 404

    return jsonify(
        {
            "ok": True,
            "root_url": state.current_root_url,
            "node_count": state.current_tree.node_count(),
            "tree_text": str(state.current_tree),
            "tree_json": state.current_tree.to_dict(),
        }
    )


@app.route("/run", methods=["POST", "OPTIONS"])
@require_api_key
def run_scan():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    url = normalize_url((data.get("url") or "").strip())
    if not url:
        return jsonify({"ok": False, "error": "Missing URL."}), 400

    if not is_site_reachable(url):
        return jsonify({"ok": False, "error": f"Site unreachable: {url}"}), 400

    with state.agent_lock:
        if state.agent_busy:
            with state.responses_lock:
                items = list(state.responses)
            return jsonify({"ok": False, "busy": True, "items": items})

        clear_state(quiet=True)
        state.agent_busy = True
        threading.Thread(
            target=agent_worker,
            args=(url, max_tool_calls, debug_mode),
            daemon=True,
        ).start()

    with state.responses_lock:
        items = list(state.responses)
    return jsonify({"ok": True, "busy": False, "items": items})


@app.route("/list", methods=["GET"])
@require_api_key
def list_items():
    with state.responses_lock:
        items = list(state.responses)
    return jsonify({"ok": True, "items": items})


@app.route("/clear", methods=["POST", "OPTIONS"])
@require_api_key
def clear_endpoint():
    if request.method == "OPTIONS":
        return ("", 204)
    clear_state(quiet=True)
    return jsonify({"ok": True})


@app.route("/save", methods=["POST", "OPTIONS"])
@require_api_key
def save_endpoint():
    if request.method == "OPTIONS":
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    filename = str(payload.get("filename", "")).strip() or None
    saved_file = save_tree(filename=filename, quiet=True)
    if not saved_file:
        return jsonify({"ok": False, "error": "No SiteTree available to save."}), 400
    return jsonify({"ok": True, "filename": saved_file})


@app.route("/load", methods=["POST", "OPTIONS"])
@require_api_key
def load_endpoint():
    if request.method == "OPTIONS":
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    filename = str(payload.get("filename", "")).strip()
    if not filename:
        return jsonify({"ok": False, "error": "Missing filename."}), 400

    ok = load_tree(filename, quiet=True, debug=debug_mode)
    if not ok:
        return jsonify({"ok": False, "error": f"Failed to load tree: {filename}"}), 400
    return jsonify({"ok": True, "status": get_status_payload()})


@app.route("/chat/send", methods=["POST", "OPTIONS"])
@require_api_key
def chat_send():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    user_text = (data.get("message") or "").strip()
    page_url = (data.get("link") or "").strip()

    if not user_text:
        return jsonify({"ok": False, "error": "Empty message."}), 400

    with state.chat_lock:
        tree_exists = state.current_tree is not None and state.current_tree.nodes is not None
        if not tree_exists:
            state.chat_history.clear()
            assistant_text = "SiteTree not found. Please scan a site first."
            state.chat_history.append({"role": "assistant", "text": assistant_text})
            return jsonify(
                {
                    "ok": True,
                    "reply": assistant_text,
                    "link": False,
                    "button": False,
                    "tree_exists": False,
                }
            )

        state.chat_history.append({"role": "user", "text": user_text})
        try:
            raw_reply = assistant.message(question=user_text, current_url=page_url)
        except Exception as exc:
            raw_reply = f"Sorry, I encountered an error: {exc}"

        assistant_text, link_flag, button_flag = extract_protocol_flags(raw_reply)
        if not (link_flag or button_flag):
            state.chat_history.append({"role": "assistant", "text": assistant_text})

        return jsonify(
            {
                "ok": True,
                "reply": assistant_text,
                "link": link_flag,
                "button": button_flag,
                "tree_exists": True,
            }
        )


@app.route("/chat/audio", methods=["POST", "OPTIONS"])
@require_api_key
def chat_audio():
    if request.method == "OPTIONS":
        return ("", 204)

    if "audio" not in request.files:
        return jsonify({"ok": False, "error": "No 'audio' file uploaded."}), 400

    file_obj = request.files["audio"]
    if not file_obj or file_obj.filename == "":
        return jsonify({"ok": False, "error": "Empty 'audio' upload."}), 400

    try:
        audio_bytes = file_obj.read()
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Failed to read audio: {exc}"}), 400

    page_url = request.form.get("link", "").strip()
    make_tts = parse_bool(request.args.get("tts", "false"), default=False)
    voice = request.args.get("voice", "alloy")

    with state.chat_lock:
        try:
            result = assistant.audio(audio_bytes=audio_bytes, tts=make_tts, voice=voice, current_url=page_url)
        except Exception as exc:
            return jsonify({"ok": False, "error": f"Audio handling error: {exc}"}), 500

        transcript = str(result.get("transcript", ""))
        raw_reply = str(result.get("reply", ""))
        reply_audio_b64 = result.get("reply_audio_b64", None)

        if transcript:
            state.chat_history.append({"role": "user", "text": transcript})

        assistant_text, link_flag, button_flag = extract_protocol_flags(raw_reply)
        if assistant_text and not (link_flag or button_flag):
            state.chat_history.append({"role": "assistant", "text": assistant_text})

        return jsonify(
            {
                "ok": True,
                "transcript": transcript,
                "reply": assistant_text,
                "reply_audio_b64": reply_audio_b64,
                "link": link_flag,
                "button": button_flag,
            }
        )


@app.route("/chat/history", methods=["GET"])
@require_api_key
def chat_history_endpoint():
    with state.chat_lock:
        history = list(state.chat_history)
    return jsonify({"ok": True, "messages": history})


@app.route("/_shutdown", methods=["POST"])
@require_api_key
def shutdown():
    os._exit(0)


def progress_updater(debug: bool = False) -> None:
    while True:
        time.sleep(0.5)

        if state.current_tree is None:
            candidate_tree = getattr(agent, "tree", None)
            if isinstance(candidate_tree, SiteTree) and candidate_tree.root_url:
                state.current_tree = candidate_tree
                state.current_root_url = candidate_tree.root_url
                with state.responses_lock:
                    if not state.responses:
                        state.responses[:] = tree_to_response_items(candidate_tree, candidate_tree.root_url, site_scanner_tool)
                if debug:
                    print(f"[DEBUG] (progress_updater) adopted SiteTree for {state.current_root_url}", flush=True)

        if state.current_tree is None:
            continue

        with state.responses_lock:
            for item in state.responses:
                raw_url = str(item.get("url", ""))
                normalized_url = site_scanner_tool.normalize(raw_url) if raw_url else ""
                node = state.current_tree.nodes.get(normalized_url)
                item["progress"] = 1.0 if node and node.desc else 0.0


def agent_worker(root_url: str, tool_call_limit: int, debug: bool = False) -> None:
    agent.reset()
    print(f"[WebTerm] Agent worker started for {root_url}.", flush=True)

    try:
        task_prompt = (
            "Scan the website and build a SiteTree of all relevant sub-pages. "
            "For each page: set a concise description and store clickable elements under `buttons` "
            "as objects with `selector` and `text`. "
            f"Start from: {root_url}."
        )

        agent.spin(
            task_prompt,
            temp=False,
            use_tools=True,
            debug=debug,
            max_tool_calls=tool_call_limit,
        )

        tree = getattr(agent, "tree", None)
        if isinstance(tree, SiteTree):
            state.current_tree = tree
            state.current_root_url = root_url
            with state.responses_lock:
                state.responses[:] = tree_to_response_items(tree, root_url, site_scanner_tool)

            print(f"[WebTerm] Agent finished scanning {root_url}.", flush=True)
            print("[WebTerm] Embed this snippet in your site after <head>:", flush=True)
            print(build_embed_script(), flush=True)

            with state.chat_lock:
                state.chat_history.clear()
                assistant.reset(tree=tree)
    except Exception as exc:
        print(f"[WebTerm] Agent error: {exc}", flush=True)
    finally:
        with state.agent_lock:
            state.agent_busy = False


def print_items() -> None:
    with state.responses_lock:
        snapshot = list(state.responses)

    print("\n[WebTerm] Current items:", flush=True)
    if not snapshot:
        print("  <empty>", flush=True)
    for idx, item in enumerate(snapshot, 1):
        print(f"  {idx:02d}. {item.get('text', '')} (progress={item.get('progress')})", flush=True)
    print("", flush=True)


def print_tree() -> None:
    if state.current_tree is None:
        print("\n[WebTerm] No SiteTree available yet. Submit a URL first.\n", flush=True)
        return

    print(f"\n[WebTerm] SiteTree for {state.current_root_url}:\n", flush=True)
    print(state.current_tree, flush=True)
    print("", flush=True)


def print_embed_script() -> None:
    print("\n[WebTerm] Embed script:\n", flush=True)
    print(build_embed_script(), flush=True)
    print("", flush=True)


def save_tree(filename: Optional[str] = None, quiet: bool = False) -> Optional[str]:
    if not state.current_tree or not state.current_root_url:
        if not quiet:
            print("[WebTerm] No SiteTree available to save.", flush=True)
        return None

    try:
        target = filename
        if not target:
            host = urlparse(state.current_root_url).hostname or "site"
            target = (host.split(".")[0] if "." in host else host) + ".json"

        state.current_tree.save(target)
        if not quiet:
            print(f"[WebTerm] SiteTree saved to {target}", flush=True)
        return target
    except Exception as exc:
        if not quiet:
            print(f"[WebTerm] Error saving SiteTree: {exc}", flush=True)
        return None


def clear_state(quiet: bool = False) -> None:
    if state.agent_busy and not quiet:
        print("[WebTerm] Agent is busy, cannot reset right now.", flush=True)
        return

    with state.chat_lock:
        state.chat_history.clear()
        assistant.reset()

    with state.responses_lock:
        removed = len(state.responses)
        state.responses.clear()

    state.current_tree = None
    state.current_root_url = None
    agent.reset()

    if not quiet:
        print(f"[WebTerm] Cleared state (removed {removed} items).", flush=True)


def load_tree(tree_file: str, quiet: bool = False, debug: bool = False) -> bool:
    filename = (tree_file or "").strip()
    if not filename:
        if debug:
            print("[DEBUG] (load_tree) no filename provided", flush=True)
        return False

    if not os.path.exists(filename):
        if not quiet:
            print(f"[WebTerm] Tree file not found: {filename}", flush=True)
        return False

    try:
        loaded_tree = SiteTree.load(filename)
        if not loaded_tree.root_url:
            if not quiet:
                print(f"[WebTerm] Invalid tree file: {filename}", flush=True)
            return False

        state.current_tree = loaded_tree
        state.current_root_url = loaded_tree.root_url

        with state.responses_lock:
            state.responses[:] = tree_to_response_items(loaded_tree, loaded_tree.root_url, site_scanner_tool)

        with state.chat_lock:
            state.chat_history.clear()
            assistant.reset(tree=loaded_tree)

        if not quiet:
            print(f"[WebTerm] Loaded tree from {filename} (root={loaded_tree.root_url})", flush=True)
        return True
    except Exception as exc:
        if not quiet:
            print(f"[WebTerm] Error loading tree from {filename}: {exc}", flush=True)
        return False


def open_ui_html(quiet: bool = False) -> None:
    html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "webterm.html"))
    if os.path.exists(html_path):
        webbrowser.open(f"file://{html_path}", new=2)
        if not quiet:
            print("[WebTerm] UI refreshed.", flush=True)
        return
    print(f"[WebTerm] UI file not found at {html_path}", flush=True)


def console_loop() -> None:
    logo = "\033[36m\033[1m" + r""" __      __          __       ______                             
/\ \  __/\ \        /\ \     /\__  _\                            
\ \ \/\ \ \ \     __\ \ \____\/_/\ \/    __   _ __    ___ ___    
 \ \ \ \ \ \ \  /'__`\ \ '__`\  \ \ \  /'__`\/\`'__\/' __` __`\  
  \ \ \_/ \_\ \/\  __/\ \ \_\ \  \ \ \/\  __/\ \ \/ /\ \/\ \/\ \ 
   \ `\___x___/\ \____\\ \_,__/   \ \_\ \____\\ \_\ \ \_\ \_\ \_\
    '\/__//__/  \/____/ \/___/     \/_/\/____/ \/_/  \/_/\/_/\/_/""" + "\033[0m"

    help_text = (
        "\n[WebTerm] Console controls:\n"
        "  c, clear    - clear current list and tree\n"
        "  l, list     - print current page list\n"
        "  t, tree     - print the current SiteTree\n"
        "  e, embed    - print the embed script\n"
        "  s, save     - save current SiteTree\n"
        "  o, load     - load a SiteTree from JSON file\n"
        "  r, refresh  - refresh the web UI\n"
        "  h, help     - show this help\n"
        "  q, quit     - stop server\n"
    )

    print(logo, flush=True)
    print(help_text, flush=True)

    for line in sys.stdin:
        cmd = (line or "").strip().lower()
        if cmd in {"c", "clear"}:
            clear_state()
        elif cmd in {"l", "list"}:
            print_items()
        elif cmd in {"t", "tree"}:
            print_tree()
        elif cmd in {"e", "embed"}:
            print_embed_script()
        elif cmd in {"s", "save"}:
            save_tree()
        elif cmd in {"o", "load"}:
            filename = input("Enter SiteTree file to load: ").strip()
            if filename:
                load_tree(filename, debug=debug_mode)
        elif cmd in {"r", "refresh"}:
            open_ui_html()
        elif cmd in {"h", "help"}:
            print(help_text, flush=True)
        elif cmd in {"q", "quit"}:
            print("[WebTerm] Quitting...", flush=True)
            os._exit(0)
        elif cmd:
            print("[WebTerm] Unknown command. Use 'h'/'help' for command list.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebTerm development server")
    parser.add_argument("--port", "-p", type=int, default=port, help="Server port (default: %(default)s)")
    parser.add_argument(
        "--ui",
        "-ui",
        type=str,
        default="true",
        help="Open webterm.html in browser on startup (true/false).",
    )
    parser.add_argument("--debug", "-d", type=str, default="false", help="Enable debug mode (true/false).")
    parser.add_argument(
        "--max_tool_calls",
        "-mtc",
        type=int,
        default=max_tool_calls,
        help="Maximum tool calls per agent iteration (default: %(default)s)",
    )
    parser.add_argument("--tree", "-t", type=str, default="", help="Load SiteTree JSON on startup.")
    parser.add_argument("--api-key", type=str, default="", help="Override API key for this run.")
    parser.add_argument(
        "--public-base-url",
        type=str,
        default="",
        help="Public base URL used for embed snippet (e.g. https://example.com).",
    )

    args = parser.parse_args()

    port = int(args.port)
    debug_mode = parse_bool(args.debug, default=False)
    max_tool_calls = int(args.max_tool_calls)
    open_ui = parse_bool(args.ui, default=True)

    if args.api_key:
        API_KEY = args.api_key.strip()
    if args.public_base_url:
        PUBLIC_BASE_URL = args.public_base_url.strip().rstrip("/")

    tree_file = (args.tree or "").strip()

    print(
        f"[WebTerm] Starting on port {port} "
        f"({'UI auto-open' if open_ui else 'UI auto-open disabled'}) "
        f"({'Debug mode on' if debug_mode else 'Debug mode off'})",
        flush=True,
    )

    if tree_file:
        load_tree(tree_file, debug=debug_mode)

    if open_ui:
        open_ui_html(quiet=True)

    threading.Thread(target=console_loop, daemon=True).start()
    threading.Thread(target=progress_updater, args=(debug_mode,), daemon=True).start()

    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
