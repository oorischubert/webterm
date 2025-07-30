from flask import Flask, request, jsonify, send_file
import sys
import re
import threading, os
import socket
import requests
import logging
import time
import argparse
from urllib.parse import urlparse
import webbrowser
from utility.agentToolKit import SiteScannerTool, SiteTree
from utility.agent import Agent
from utility.assistant import Assistant
from functools import wraps

app = Flask(__name__)
responses = []  # in-memory list of response items
responses_lock = threading.Lock()
API_KEY = "012245"

# Silence Flask/Werkzeug request logs
app.logger.disabled = True
logging.getLogger('werkzeug').disabled = True
logging.getLogger('werkzeug.serving').disabled = True

#SiteScanner setup
site_scanner_tool = SiteScannerTool()
agent = Agent()
assistant = Assistant()

# Keep only a single current tree to simplify state
current_tree: SiteTree | None = None
current_root_url: str | None = None

# --- Agent worker state ---
agent_busy = False               # True while Agent is scanning
agent_lock = threading.Lock()    # protects agent_busy

# ---------- Chatbot storage ----------
chat_history: list[dict] = [{"role": "assistant", "text": "Hi! Ask me anything…"}]             # [{'role':'user'|'assistant', 'text': str}]
chat_lock = threading.Lock()

def is_site_reachable(url: str, timeout: float = 6.0) -> bool:
    """Return True if the URL returns a successful response (HEAD/GET)."""
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        # Some servers disallow HEAD or return 405/4xx; fall back to GET
        if r.status_code >= 400 or r.status_code == 405:
            r = requests.get(url, timeout=timeout, stream=True)
        return r.status_code < 400
    except Exception:
        return False


def _iter_branches(tree: SiteTree):
    """Yield branches as lists of URLs from root to each leaf."""
    root = getattr(tree, "root_url", None)
    children = getattr(tree, "children", None)
    if not root or children is None:
        return []
    branches = []
    def walk(u: str, path: list[str]):
        kids = list(children.get(u, set()))
        if not kids:
            branches.append(path + [u])
            return
        for v in kids:
            walk(v, path + [u])
    walk(root, [])
    return branches

# --- Helper functions for site label and path segments ---
def site_label_from_url(url: str) -> str:
    """Return a concise site label (e.g., 'squidgo' for https://squidgo.com)."""
    try:
        host = (urlparse(url).hostname or '').lower()
    except Exception:
        return url
    if not host:
        return url
    # Strip port if any
    if ':' in host:
        host = host.split(':', 1)[0]
    parts = [p for p in host.split('.') if p]
    if parts and parts[0] == 'www':
        parts = parts[1:]
    label = ''
    if len(parts) >= 2:
        tld = parts[-1]
        sld = parts[-2]
        # Handle ccTLD like example.co.uk -> 'example'
        if len(tld) == 2 and sld in ('co', 'com', 'org', 'net', 'edu', 'gov', 'ac'):
            if len(parts) >= 3:
                label = parts[-3]
            else:
                label = sld
        else:
            label = sld
    elif parts:
        label = parts[0]
    else:
        label = host
    return label

def path_segments(u: str) -> list[str]:
    try:
        path = urlparse(u).path
    except Exception:
        return []
    return [s for s in (path or '').split('/') if s]

def tree_to_response_items(tree: SiteTree, root_url: str):
    """Convert a SiteTree into transport-friendly response items with progress.
    Title format: <site-label> › <root-path-part?> › <subpaths>
    Examples:
      root=https://squidgo.com          -> "squidgo"
      leaf=https://squidgo.com/shop     -> "squidgo › shop"
      root=https://squidgo.com/shop     -> "squidgo › shop"
      leaf=https://squidgo.com/shop/x   -> "squidgo › shop › x"
    """
    items = []
    branches = _iter_branches(tree)
    site_label = site_label_from_url(root_url)
    root_segs = path_segments(root_url)

    # --- always add the root/homepage pill first ---
    root_title = site_label if not root_segs else " › ".join([site_label] + root_segs)
    root_progress = 0.0
    try:
        root_node = tree.nodes.get(site_scanner_tool.normalize(root_url))  # type: ignore
        if root_node and getattr(root_node, "desc", ""):
            root_progress = 1.0
    except Exception:
        pass

    items.append({
        "root": root_url,
        "url": root_url,
        "text": root_title,
        "progress": root_progress
    })

    for branch in branches:
        leaf = branch[-1]
        leaf_segs = path_segments(leaf)
        rel = leaf_segs
        if root_segs and leaf_segs[:len(root_segs)] == root_segs:
            rel = leaf_segs[len(root_segs):]
        label_parts = [site_label] + (root_segs if not root_segs else [])  # site label only if root has no path
        # If root has a path, we include it only once at the front
        if root_segs:
            label_parts = [site_label] + root_segs
        label_parts += rel
        title = " › ".join([p for p in label_parts if p]) if label_parts else site_label

        items.append({
            "root": root_url,
            "url": leaf,
            "text": title,
            "progress": 0.0
        })
    return items

def normalize_url(u: str) -> str:
    u = (u or '').strip()
    if not u:
        return u
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', u):
        return u
    if u.startswith('//'):
        return 'https:' + u
    return 'https://' + u

def require_api_key(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        # Allow CORS pre-flight without auth
        if request.method == "OPTIONS":
            return ('', 204)

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
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-API-Key'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return resp


@app.route('/webterm.js')
@require_api_key
def serve_webterm_js():
    return send_file('webterm.js', mimetype='application/javascript')

@app.route('/run', methods=['POST', 'OPTIONS'])
@require_api_key
def run():
    if request.method == 'OPTIONS':
        return ('', 204)
    data = request.get_json(silent=True) or {}
    orig = (data.get('url') or '').strip()
    url = normalize_url(orig)

    # 1) Verify the site is reachable
    if not is_site_reachable(url):
        print(f"[WebTerm] Site unreachable: {url}", flush=True)
        # Do not modify current responses or tree; return current list as-is
        with responses_lock:
            items = list(responses)
        return jsonify({'ok': True, 'items': items})

    # 2) Kick off Agent worker if not already running
    with agent_lock:
        global agent_busy
        if agent_busy:
            print("[WebTerm] Agent is still working on previous task.", flush=True)
            with responses_lock:
                items = list(responses)
            return jsonify({"ok": False, "busy": True, "items": items})

        _clear(quiet=True)
        agent_busy = True
        threading.Thread(target=agent_worker, args=(url, max_tool_calls, debug_mode), daemon=True).start()

    # Immediately return current items (may be empty) so UI can poll
    with responses_lock:
        items = list(responses)
    return jsonify({"ok": True, "busy": False, "items": items})


# List all items endpoint
@app.route('/list', methods=['GET'])
@require_api_key
def list_items():
    with responses_lock:
        items = list(responses)
    return jsonify({'ok': True, 'items': items})

@app.route('/chat/send', methods=['POST', 'OPTIONS'])
@require_api_key
def chat_send():
    if request.method == 'OPTIONS':          # CORS pre-flight
        return ('', 204)

    data = request.get_json(silent=True) or {}
    user_text = (data.get('message') or '').strip()
    page_url = data.get("link", "") 
    if debug_mode:
        print(f"[DEBUG] (chat_send) User message: {user_text} from: {page_url}", flush=True)

    if not user_text:
        return jsonify({'ok': False, 'error': 'Empty message.'}), 400

    with chat_lock:
        tree_exists = (current_tree is not None and getattr(current_tree, "nodes", None) is not None)
        link_flag = False  # Will be set to True if this message is a link
        button_flag = False
        if not tree_exists:
            chat_history.clear()
            assistant_text = "SiteTree not found. Please scan a site first."
            chat_history.append({'role': 'assistant', 'text': assistant_text})
        else:
            chat_history.append({'role': 'user', 'text': user_text})
            try:
                assistant_text = assistant.answer(question=user_text + (f" (User currently on page: {page_url})" if page_url else ""))
            except Exception as e:
                assistant_text = f"Sorry, I encountered an error: {e}"
            # Detect link-type assistant message
            if isinstance(assistant_text, str) and assistant_text.strip().startswith("send_link:"):
                # Example protocol: assistant returns "send_link:<url>"
                url = assistant_text.strip()[len("send_link:"):].strip()
                if debug_mode:
                    print(f"[DEBUG] (chat_send) Link message injected ({url})")
                link_flag = True
                assistant_text = url  # Only send URL to frontend
            elif isinstance(assistant_text, str) and assistant_text.strip().startswith("click_element:"):
                # Example protocol: assistant returns "click_element:<selector>"
                selector = assistant_text.strip()[len("click_element:"):].strip()
                if debug_mode:
                    print(f"[DEBUG] (chat_send) Click message injected ({selector})")
                button_flag = True
                assistant_text = selector # Only send selector to frontend
            else:
                chat_history.append({'role': 'assistant', 'text': assistant_text})
        # Now send link flag to frontend:
        return jsonify({'ok': True, 'reply': assistant_text, 'link': link_flag, 'button': button_flag, 'tree_exists': tree_exists})

@app.route('/chat/history', methods=['GET'])
@require_api_key
def chat_history_endpoint():
    with chat_lock:
        hist_copy = list(chat_history)
    return jsonify({'ok': True, 'messages': hist_copy})

@app.route('/_shutdown', methods=['POST'])
@require_api_key
def _shutdown():
    """Stop the dev server immediately without Python teardown warnings."""
    os._exit(0)

def progress_updater(debug: bool = False):
    """
    Continuously synchronise each response item's progress with the SiteTree.

    * If `current_tree` is None but the Agent has produced a tree (`agent.tree`),
      adopt it immediately so the UI can start showing progress.
    * Every 0.5 s set progress = 1.0 when the corresponding SiteNode.desc is not empty.
    """
    global current_tree, current_root_url
    while True:
        time.sleep(0.5)
        # 1) Adopt a freshly‑built tree from the Agent as soon as it exists
        if current_tree is None:
            agent_tree = getattr(agent, "tree", None)
            if isinstance(agent_tree, SiteTree) and agent_tree.root_url:
                current_tree = agent_tree
                current_root_url = agent_tree.root_url
                # Populate responses if still empty
                if not responses:
                    with responses_lock:
                        responses[:] = tree_to_response_items(current_tree, current_root_url)
                if debug:
                    print(f"[DEBUG] (progress_updater) adopted new SiteTree for {current_root_url}.", flush=True)
        # 2) Update progress for each known item
        if current_tree is None:
            continue
        with responses_lock:
            for item in responses:
                raw_url = item.get("url")
                norm_url = site_scanner_tool.normalize(raw_url) if raw_url else ""
                node = current_tree.nodes.get(norm_url)
                item["progress"] = 1.0 if node and node.desc else 0.0

def agent_worker(root_url: str, max_tool_calls: int, debug: bool = False, temp: bool = True):
    """Background thread: ask the Agent to build the SiteTree with descriptions."""
    if temp:  # non-temp version not integrated yet, progress_updater will not update progress
        agent.reset()
        if debug:
            print("[DEBUG] (agent_worker) Agent state reset.")
    global agent_busy, current_tree, current_root_url
    print(f"[WebTerm] Agent worker started for {root_url}.", flush=True)
    try:
        task_prompt = (
            f"Scan {root_url}, build a SiteTree of all sub-pages, and store a short description for each page. "
            f"For every page, also list all visible clickable buttons and links (such as <button>, <input type='button'>, and prominent <a> elements) with a precise CSS selector and their visible text or label. "
            f"Save these under a `buttons` array for each node. "
            f"Example: If a page has two buttons, one with text 'Submit' and selector '#submitBtn', and another with no text but a title 'Email', and selector 'a[href=\"mailto:oorischubert@gmail.com\"]', then its buttons array should be: "
            f"`buttons: [{{'selector': '#submitBtn', 'text': 'Submit'}}, {{'selector': 'a[href=\"mailto:oorischubert@gmail.com\"]', 'text': 'Email'}}]` "
            f"Update both descriptions and button lists as soon as you scan each page."
        )
        agent.spin(task_prompt, temp=False, use_tools=True, debug=debug, max_tool_calls=max_tool_calls)
        # Agent.tree should now be populated
        tree = getattr(agent, "tree", None)
        if isinstance(tree, SiteTree):
            current_tree = tree
            current_root_url = root_url
            # Convert to response items (0/1 progress based on desc presence)
            new_items = tree_to_response_items(tree, root_url)
            with responses_lock:
                responses[:] = new_items
            print(f"[WebTerm] Agent finished scanning {root_url}.", flush=True)
            # --- Dynamic script URL print block ---
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                server_ip = s.getsockname()[0]
                s.close()
            except Exception:
                server_ip = "localhost"
            server_url = f"http://{server_ip}:{port}/webterm.js"
            print("[Webterm] paste below line into your webpage after <head> :", flush=True)
            print(f"<script src=\"{server_url}?api_key={API_KEY}\" defer></script>", flush=True)
            with chat_lock:
                chat_history.clear()
                assistant.reset(tree=tree)  # Reset assistant context with the new tree
    except Exception as e:
        print(f"[WebTerm] Agent error: {e}", flush=True)
    finally:
        with agent_lock:
            agent_busy = False

def _print_items():
    with responses_lock:
        snapshot = list(responses)
    print("\n[WebTerm] Current items (ordered):", flush=True)
    for i, it in enumerate(snapshot, 1):
        print(f"  {i:02d}. {it.get('text','')}  (progress: {it.get('progress')})", flush=True)
    if not snapshot:
        print("  <empty>", flush=True)
    print("", flush=True)

def _print_tree():
    """Print the current SiteTree if available."""
    if current_tree:
        print(f"\n[WebTerm] SiteTree for {current_root_url}:\n", flush=True)
        print(current_tree, flush=True)
        print("", flush=True)
    else:
        print("\n[WebTerm] No SiteTree available yet. Submit a URL first.\n", flush=True)

def _save_tree(quiet: bool = False):
    """Save the current SiteTree to a JSON file named after the root URL."""
    if not current_tree or not current_root_url:
        if not quiet:
            print("[WebTerm] No SiteTree available to save.", flush=True)
        return
    try:
        parsed_host = urlparse(current_root_url).hostname or "site"
        base_name = parsed_host.split('.')[0] if '.' in parsed_host else parsed_host
        current_tree.save(f"{base_name}.json")
        if not quiet:
            print(f"[WebTerm] SiteTree saved to {base_name}.json", flush=True)
    except Exception as e:
        print(f"[WebTerm] Error saving SiteTree: {e}", flush=True)

def _open_ui_html(quiet: bool = False):
    """Open webterm.html in the default browser."""
    html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'webterm.html'))
    if os.path.exists(html_path):
        webbrowser.open(f'file://{html_path}', new=2)  # new tab if possible
        if not quiet:
            print(f"[WebTerm] UI refreshed.", flush=True)
    else:
        print(f"[WebTerm] UI file not found at {html_path}", flush=True)
        
def _clear(quiet: bool = False):
    global current_tree, current_root_url
    if agent_busy:
        print("[WebTerm] Agent is busy, cannot reset right now.", flush=True)
    else:
        with chat_lock:
            chat_history.clear()
            assistant.reset()
        with responses_lock:
            removed = len(responses)
            responses.clear()
        current_tree = None
        current_root_url = None
        agent.reset()
        if not quiet:
            print(f"[WebTerm] List and tree cleared (removed {removed} items).", flush=True)

def _load_tree(tree_file: str, quiet: bool = False, debug: bool = False) -> bool:
    """
    Load a SiteTree from a JSON file and initialize the application state (ie. ./tests/oorischubert.json).
    
    Args:
        tree_file: Path to the JSON file containing the saved SiteTree
        
    Returns:
        bool: True if tree was loaded successfully, False otherwise
    """
    global current_tree, current_root_url
    
    if not tree_file.strip():
        if debug:
            print("[DEBUG] (_load_tree) No tree file specified, skipping load.", flush=True)
        return False
        
    try:
        if not os.path.exists(tree_file):
            if not quiet:
                print(f"[WebTerm] Tree file not found: {tree_file}", flush=True)
            return False
            
        loaded_tree = SiteTree.load(tree_file)
        if not loaded_tree or not loaded_tree.root_url:
            if not quiet:
                print(f"[WebTerm] Invalid tree file: {tree_file}", flush=True)
            return False
            
        # Set global state
        current_tree = loaded_tree
        current_root_url = loaded_tree.root_url
        
        # Populate responses with the loaded tree
        with responses_lock:
            if debug:
                print(f"[DEBUG] (_load_tree) Converting loaded tree to response items.", flush=True)
            responses[:] = tree_to_response_items(current_tree, current_root_url)
        
        # Initialize assistant with the loaded tree
        with chat_lock:
            if debug:
                print(f"[DEBUG] (_load_tree) Initializing assistant with loaded tree for {current_root_url}", flush=True)
            assistant.reset(tree=current_tree)

        if not quiet:
            print(f"[WebTerm] Loaded tree from {tree_file} with root: {current_root_url}", flush=True)
        if debug:
            print(f"[Debug] (_load_tree) Tree contains {len(loaded_tree.nodes)} pages", flush=True)
        return True
        
    except Exception as e:
        if not quiet:
            print(f"[WebTerm] Error loading tree from {tree_file}: {e}", flush=True)
        return False

def console_loop():
    welcome = (
        "\n[WebTerm] Console controls:\n"
        "  c, clear   - clear current list and tree\n"
        "  l, list    - print current page list\n"
        "  t, tree    - print the current SiteTree\n"
        "  s, save    - save current SiteTree to <root_url>.json\n"
        "  o, load    - load a SiteTree from JSON file\n"
        "  r, refresh - refresh the web UI\n"
        "  q, quit    - stop server\n"
    )
    print(welcome, flush=True)
    for line in sys.stdin:
        cmd = (line or '').strip().lower()
        if cmd in ('c', 'clear'):
            _clear()
        elif cmd in ('l', 'list'):
            _print_items()
        elif cmd in ('t', 'tree'):
            _print_tree()
        elif cmd in ('s', 'save'):
            _save_tree()
        elif cmd in ('o', 'load'):
            file = input("Enter SiteTree file to load: ").strip()
            if file:
                _load_tree(file, debug=debug_mode)
        elif cmd in ('r', 'refresh'):
            _open_ui_html()
        elif cmd in ('h', 'help'):
            print(welcome, flush=True)
        elif cmd in ('q', 'quit'):
            print('[WebTerm] Quitting...', flush=True)
            os._exit(0)
        else:
            if cmd:
                print("[WebTerm] Unknown command. Use 'h'/'help' for command list.", flush=True)

if __name__ == '__main__':
    # Parse CLI arguments for progress step and interval
    parser = argparse.ArgumentParser(description='WebTerm progress server')
    parser.add_argument('--port', '-p', type=int, default=5050,
                        help='Port to run the server on. Default: %(default)s')
    parser.add_argument('--ui', '-ui', type=str, default='true',
                        help='Open webterm.html in the default browser (true/false). Default: %(default)s')
    parser.add_argument('--debug', '-d', type=str, default='false',
                        help='Enable debug mode (true/false). Default: %(default)s')
    parser.add_argument('--max_tool_calls', '-mtc', type=int, default=1,
                        help='Maximum number of tool calls to allow per request. Default: %(default)s')
    parser.add_argument('--tree', '-t', type=str, default="",
                        help='Load tree on launch.')
    args = parser.parse_args()

    port = int(args.port)
    open_ui = str(args.ui).lower() not in ('false', '0', 'no', 'off')
    debug_mode = str(args.debug).lower() in ('true', '1', 'yes')
    max_tool_calls = int(args.max_tool_calls)
    tree_file = args.tree.strip() if args.tree else ""

    print(f"[WebTerm] Starting on port {port} "
          f"({'UI auto-open' if open_ui else 'UI auto-open disabled'})",
          f"({'Debug mode on' if debug_mode else 'Debug mode off'})", flush=True)

    # Load tree if specified
    if tree_file:
        _load_tree(tree_file, debug=debug_mode)

    if open_ui:
        _open_ui_html(quiet=True)

    # Run console + progress threads, then Flask without reloader for stdin
    threading.Thread(target=console_loop, daemon=True).start()
    threading.Thread(target=progress_updater, args=(debug_mode,), daemon=True).start()
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)