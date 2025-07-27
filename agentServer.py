from flask import Flask, request, jsonify
import sys
import re
import random
import threading, os, json
import requests
import logging
import time


app = Flask(__name__)
responses = []  # in-memory list of response items
responses_lock = threading.Lock()
PROGRESS_STEP = 0.05       # amount to increase per tick (0..1), two decimals
PROGRESS_INTERVAL = 0.5    # seconds between ticks

# Silence Flask/Werkzeug request logs
app.logger.disabled = True
logging.getLogger('werkzeug').disabled = True
logging.getLogger('werkzeug.serving').disabled = True

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
    progress = 0.0  # start at 0, will auto-increment in background
    text = f"buttonTest response for {url}"
    item = {'url': url, 'text': text, 'progress': progress}
    with responses_lock:
        responses.append(item)
    # print(f"[WebText] URL received: {orig} -> {url}", file=sys.stdout, flush=True)
    return jsonify({'ok': True, 'items': responses})


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
    print("\n[WebText] Current items (ordered):", flush=True)
    for i, it in enumerate(snapshot, 1):
        print(f"  {i:02d}. {it.get('text','')}  (progress: {it.get('progress')})", flush=True)
    if not snapshot:
        print("  <empty>", flush=True)
    print("", flush=True)

def console_loop():
    welcome = (
        "\n[WebText] Console controls:\n"
        "  c, clear  - clear current list\n"
        "  l, list   - print current list (ordered)\n"
        "  q, quit   - stop server\n"
    )
    print(welcome, flush=True)
    for line in sys.stdin:
        cmd = (line or '').strip().lower()
        if cmd in ('c', 'clear'):
            with responses_lock:
                removed = len(responses)
                responses.clear()
            print(f"[WebText] List cleared (removed {removed} items).", flush=True)
        elif cmd in ('l', 'list'):
            _print_items()
        elif cmd in ('q', 'quit'):
            print('[WebText] Quitting...', flush=True)
            os._exit(0)
        else:
            if cmd:
                print("[WebText] Unknown command. Use 'c'/'clear', 'l'/'list', or 'q'/'quit'.", flush=True)

if __name__ == '__main__':
    # Run console thread and start Flask without reloader for stdin
    threading.Thread(target=console_loop, daemon=True).start()
    threading.Thread(target=progress_updater, daemon=True).start()
    app.run(host='127.0.0.1', port=5050, debug=False, use_reloader=False)