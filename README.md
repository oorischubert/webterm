# WebTerm

AI-powered website scanner + assistant runtime.

WebTerm scans a website, builds a structured `SiteTree`, and serves a drop-in chat widget that can answer site-specific questions and perform navigation actions (`send_link`, `click_element`).

## What Changed (Revamp)

- Cleaner backend state management and endpoint surface.
- Cleaner agent/tooling loops with better tool-call handling.
- Model defaults switched to `gpt-5.2`.
- Refactored scanner with better crawl controls and deduplicated clickable extraction.
- New control-panel UI (`webterm.html`) with:
  - scan controls
  - live progress list
  - tree viewer (text + JSON)
  - embed snippet viewer/copy
  - save/load/clear actions
- Widget (`webterm.js`) now auto-configures API base/key from script URL query params.

## Project Structure

```text
webterm/
├── webterm.py           # Flask server + orchestration + console controls
├── webterm.html         # Admin/control UI
├── webterm.js           # Drop-in chatbot widget
├── utility/
│   ├── __init__.py
│   ├── agent.py         # Agent tool-call loop (site scanning orchestration)
│   ├── assistant.py     # Site-grounded chat + audio pipeline
│   ├── agentToolKit.py  # Site scanner + SiteTree + tool descriptors
│   ├── terminal.py      # Placeholder terminal abstraction
│   └── notification.py  # macOS notification utility
└── tests/
    ├── toolKitTest.py
    ├── webparser.py
    └── oorischubert.json
```

## Requirements

- Python 3.11+
- `flask`, `requests`, `beautifulsoup4`, `openai`
- OpenAI API key available to your environment (`OPENAI_API_KEY`)

## Run

```bash
python webterm.py
```

Optional flags:

```bash
python webterm.py \
  --port 5050 \
  --ui true \
  --debug false \
  --max_tool_calls 2 \
  --tree mysite.json \
  --api-key dev-webterm-key \
  --public-base-url https://your-server.example.com
```

## Model Configuration

Default LLM used by agent + assistant: `gpt-5.2`.

Override via env vars:

```bash
export WEBTERM_MODEL=gpt-5.2
export WEBTERM_AGENT_MODEL=gpt-5.2
export WEBTERM_ASSISTANT_MODEL=gpt-5.2
export WEBTERM_STT_MODEL=gpt-4o-mini-transcribe
export WEBTERM_TTS_MODEL=tts-1
```

## Auth / Runtime Config

```bash
export WEBTERM_API_KEY=dev-webterm-key
export WEBTERM_DISABLE_AUTH=false
export WEBTERM_PUBLIC_BASE_URL=https://your-server.example.com
```

## Main Endpoints

- `POST /run` start scan
- `GET /list` scan progress items
- `GET /state` runtime status summary
- `GET /tree` current `SiteTree` (text + JSON)
- `GET /embed` generated script tag
- `POST /clear` clear runtime state
- `POST /save` save tree JSON
- `POST /load` load tree JSON
- `POST /chat/send` text chat
- `POST /chat/audio` voice chat
- `GET /chat/history` chat transcript

All protected routes require `X-API-Key` unless `WEBTERM_DISABLE_AUTH=true`.

## Embedding the Widget

```html
<script src="https://your-server.example.com/webterm.js?api_key=YOUR_API_KEY" defer></script>
```

Optional query params:

- `api_base=https://your-server.example.com`
- `position=left|right`
- `audio=true|false`

## Console Commands (server stdin)

- `c` / `clear`
- `l` / `list`
- `t` / `tree`
- `e` / `embed`
- `s` / `save`
- `o` / `load`
- `r` / `refresh`
- `h` / `help`
- `q` / `quit`

## Notes

- `pytest -q` currently reports no collected tests in this repository.
- The control panel now exposes key operational state and tree visibility directly, replacing the earlier minimal UI.
