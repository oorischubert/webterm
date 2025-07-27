from flask import Flask, request, jsonify
import sys
import re
import random
import threading, os, json
import requests
import logging
import time
import argparse
from urllib.parse import urlparse

from utility.agentToolKit import SiteScannerTool, SiteTree

app = Flask(__name__)
responses = []  # in-memory list of response items
responses_lock = threading.Lock()
PROGRESS_STEP = 0.1       # amount to increase per tick (0..1), two decimals
PROGRESS_INTERVAL = 0.5    # seconds between ticks

# Silence Flask/Werkzeug request logs
app.logger.disabled = True
logging.getLogger('werkzeug').disabled = True
logging.getLogger('werkzeug.serving').disabled = True

#SiteScanner setup
site_scanner_tool = SiteScannerTool()

# Keep only a single current tree to simplify state
current_tree: SiteTree | None = None
current_root_url: str | None = None

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
    root = getattr(tree, "root", None)
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

    if not branches:
        # No children found; still expose a single branch at root
        title = site_label if not root_segs else " ".join([site_label, '›', " › ".join(root_segs)])
        items.append({"root": root_url, "url": root_url, "text": title, "progress": 0.0})
        return items

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

@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return resp

@app.route('/run', methods=['POST', 'OPTIONS'])
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

    # 2) Build a SiteTree (source of truth)
    try:
        tree = site_scanner_tool.sitePropogator(url,n=1)
    except Exception:
        # Scanner failed: record a single entry so the UI reflects the failure
        failed = {'root': url, 'url': url, 'text': f'Scan failed for {url}', 'progress': 0.0}
        with responses_lock:
            responses.append(failed)
            items = list(responses)
        return jsonify({'ok': True, 'items': items})

    # 3) Store single current tree and convert branches to response items (transport/UX only)
    global current_tree, current_root_url
    current_tree = tree
    current_root_url = url
    items_from_tree = tree_to_response_items(tree, url)

    # Replace any existing items with the new tree's branches
    with responses_lock:
        responses[:] = items_from_tree
        items = list(responses)
    return jsonify({'ok': True, 'items': items})


# List all items endpoint
@app.route('/list', methods=['GET'])
def list_items():
    with responses_lock:
        items = list(responses)
    return jsonify({'ok': True, 'items': items})

@app.route('/_shutdown', methods=['POST'])
def _shutdown():
    """Stop the dev server immediately without Python teardown warnings."""
    os._exit(0)

def progress_updater():
    while True:
        time.sleep(PROGRESS_INTERVAL)
        with responses_lock:
            for it in responses:
                try:
                    p = float(it.get('progress', 0))
                except (TypeError, ValueError):
                    p = 0.0
                if p < 1.0:
                    newp = p + PROGRESS_STEP
                    if newp > 1.0:
                        newp = 1.0
                    it['progress'] = round(newp, 2)

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

def console_loop():
    welcome = (
        "\n[WebTerm] Console controls:\n"
        f"  (progress step={PROGRESS_STEP}, interval={PROGRESS_INTERVAL}s)\n"
        "  c, clear  - clear current list and tree\n"
        "  l, list   - print current list (ordered)\n"
        "  t, tree   - print the current SiteTree\n"
        "  q, quit   - stop server\n"
    )
    print(welcome, flush=True)
    for line in sys.stdin:
        cmd = (line or '').strip().lower()
        if cmd in ('c', 'clear'):
            global current_tree, current_root_url
            with responses_lock:
                removed = len(responses)
                responses.clear()
            current_tree = None
            current_root_url = None
            print(f"[WebTerm] List and tree cleared (removed {removed} items).", flush=True)
        elif cmd in ('l', 'list'):
            _print_items()
        elif cmd in ('t', 'tree'):
            _print_tree()
        elif cmd in ('q', 'quit'):
            print('[WebTerm] Quitting...', flush=True)
            os._exit(0)
        else:
            if cmd:
                print("[WebTerm] Unknown command. Use 'c'/'clear', 'l'/'list', or 'q'/'quit'.", flush=True)

if __name__ == '__main__':
    # Parse CLI arguments for progress step and interval
    parser = argparse.ArgumentParser(description='WebTerm progress server')
    parser.add_argument('--step', '-s', type=float, default=PROGRESS_STEP,
                        help='Progress increment per tick (0..1). Default: %(default)s')
    parser.add_argument('--interval', '-i', type=float, default=PROGRESS_INTERVAL,
                        help='Seconds between progress updates. Default: %(default)s')
    parser.add_argument('--port', '-p', type=int, default=5050,
                        help='Port to run the server on. Default: %(default)s')
    args = parser.parse_args()

    # Clamp/normalize values
    PROGRESS_STEP = max(0.0, min(1.0, float(args.step)))
    PROGRESS_INTERVAL = max(0.01, float(args.interval))
    port = int(args.port)

    print(f"[WebTerm] Starting with step={PROGRESS_STEP} and interval={PROGRESS_INTERVAL}s on port {port}", flush=True)

    # Run console + progress threads, then Flask without reloader for stdin
    threading.Thread(target=console_loop, daemon=True).start()
    threading.Thread(target=progress_updater, daemon=True).start()
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)