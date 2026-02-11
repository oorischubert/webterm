from __future__ import annotations

import base64
import datetime
import json
import os
import copy
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from openai import OpenAI

try:
    from .agentToolKit import SiteTree
except ImportError:
    from agentToolKit import SiteTree


MODEL = os.getenv("WEBTERM_ASSISTANT_MODEL", os.getenv("WEBTERM_MODEL", "gpt-5.2"))
STT_MODEL = os.getenv("WEBTERM_STT_MODEL", "gpt-4o-mini-transcribe")
TTS_MODEL = os.getenv("WEBTERM_TTS_MODEL", "tts-1")


class Assistant:
    """Website-grounded assistant with optional audio I/O."""

    def __init__(self, tree: Optional[SiteTree] = None, model: str = MODEL) -> None:
        self.model = model
        self.client = OpenAI()
        self._use_responses_api = hasattr(self.client, "responses")
        self.tree: Optional[SiteTree] = tree
        self.messages: List[Dict[str, Any]] = []
        self.functions = self._sanitize_tool_schemas([LinkTool().desc, ClickTool().desc])
        self.reset(tree)

    @staticmethod
    def _site_name_from_tree(tree: SiteTree) -> str:
        root = (tree.root_url or "").strip()
        if not root:
            return "this site"
        parsed = urlparse(root)
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return root
        parts = [p for p in host.split(".") if p]
        if parts and parts[0] == "www":
            parts = parts[1:]
        if len(parts) >= 2:
            return parts[-2]
        return parts[0] if parts else host

    def _system_prompt(self, tree: SiteTree) -> str:
        site_name = self._site_name_from_tree(tree)
        return (
            f"The current time is {datetime.datetime.now().isoformat()}. "
            "You are a website assistant. Answer using only the provided SiteTree data. "
            "Keep a natural conversational tone and answer the user's exact question first. "
            "Do not list all available links, buttons, pages, or options unless the user explicitly asks for them. "
            "If listing options is requested, include only the most relevant options and keep the list short. "
            "If the user asks something unrelated, reply exactly: "
            f"\"Sorry, I can only discuss content related to {site_name}.\" "
            "When navigation is requested, call tools instead of writing instructions. "
            "Keep answers concise and precise."
            f"\n\nSiteTree JSON:\n{tree.get_json()}"
        )

    def reset(self, tree: Optional[SiteTree] = None) -> None:
        if tree is not None:
            self.tree = tree
        self.messages = []
        if self.tree is not None:
            self.messages.append({"role": "system", "content": self._system_prompt(self.tree)})

    def STT(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""

        def detect_audio_format(data: bytes) -> str:
            if data.startswith(b"RIFF") and b"WAVE" in data[:12]:
                return ".wav"
            if data.startswith(b"OggS"):
                return ".ogg"
            if data.startswith(b"\x1a\x45\xdf\xa3"):
                return ".webm"
            if data.startswith(b"ID3") or data.startswith((b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
                return ".mp3"
            return ".mp3"

        suffix = detect_audio_format(audio_bytes)

        with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            try:
                with open(tmp.name, "rb") as audio_file:
                    transcript = self.client.audio.transcriptions.create(
                        model=STT_MODEL,
                        file=audio_file,
                        response_format="text",
                    )
                return str(transcript)
            except Exception as exc:
                print(f"STT Error: {exc}")
                return ""

    def TTS(self, text: str, voice: str = "alloy", audio_format: str = "mp3") -> bytes:
        if not text:
            return b""
        valid_formats = {"mp3", "opus", "aac", "flac", "wav", "pcm"}
        fmt = audio_format if audio_format in valid_formats else "mp3"

        try:
            response = self.client.audio.speech.create(
                model=TTS_MODEL,
                voice=voice,  # type: ignore[arg-type]
                input=text,
                response_format=fmt,  # type: ignore[arg-type]
            )
            return response.content
        except Exception as exc:
            print(f"TTS Error: {exc}")
            return b""

    @staticmethod
    def _extract_assistant_text_from_responses(resp: Any) -> str:
        for item in getattr(resp, "output", []):
            item_type = getattr(item, "type", None)
            if item_type in {"reasoning", "function_call"}:
                continue
            content = getattr(item, "content", None)
            if not content:
                continue
            for chunk in content:
                text = getattr(chunk, "text", None)
                if text:
                    return text
        return ""

    @staticmethod
    def _extract_navigation_from_responses(resp: Any) -> str:
        for item in getattr(resp, "output", []):
            if getattr(item, "type", None) != "function_call":
                continue

            name = getattr(item, "name", "")
            if name not in {"send_link", "click_element"}:
                continue

            try:
                args = json.loads(getattr(item, "arguments", "{}") or "{}")
            except Exception:
                args = {}

            if name == "send_link" and args.get("url"):
                return f"send_link:{args.get('url')}"
            if name == "click_element" and args.get("element"):
                return f"click_element:{args.get('element')}"
        return ""

    @staticmethod
    def _extract_assistant_text_from_chat(message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: List[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    chunks.append(str(part.get("text", "")))
            return "".join(chunks).strip()
        return ""

    @staticmethod
    def _extract_navigation_from_chat(message: Any) -> str:
        for call in getattr(message, "tool_calls", []) or []:
            fn = getattr(call, "function", None)
            if fn is None:
                continue

            name = str(getattr(fn, "name", ""))
            if name not in {"send_link", "click_element"}:
                continue

            try:
                args = json.loads(str(getattr(fn, "arguments", "{}")) or "{}")
            except Exception:
                args = {}

            if name == "send_link" and args.get("url"):
                return f"send_link:{args.get('url')}"
            if name == "click_element" and args.get("element"):
                return f"click_element:{args.get('element')}"
        return ""

    @staticmethod
    def _sanitize_tool_schemas(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sanitized: List[Dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            entry = copy.deepcopy(tool)
            params = entry.get("parameters")
            if isinstance(params, dict):
                props = params.get("properties")
                if isinstance(props, dict):
                    required = params.get("required")
                    required_list = list(required) if isinstance(required, list) else []
                    for key in props.keys():
                        if key not in required_list:
                            required_list.append(key)
                    params["required"] = required_list
                    if "additionalProperties" not in params:
                        params["additionalProperties"] = False
            sanitized.append(entry)
        return sanitized

    @staticmethod
    def _tools_for_chat_completions(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted: List[Dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue

            if "function" in tool and isinstance(tool.get("function"), dict):
                converted.append(tool)
                continue

            if tool.get("type") != "function":
                continue

            function_payload: Dict[str, Any] = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
            }
            if "strict" in tool:
                function_payload["strict"] = tool.get("strict")

            converted.append({"type": "function", "function": function_payload})
        return converted

    def _request_model(self, messages: List[Dict[str, Any]], use_tools: bool) -> Tuple[str, str]:
        if self._use_responses_api:
            resp = self.client.responses.create(
                model=self.model,
                tools=self.functions if use_tools else [],
                input=messages,
            )
            text = self._extract_assistant_text_from_responses(resp)
            nav = self._extract_navigation_from_responses(resp) if use_tools else ""
            return text, nav

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if use_tools:
            payload["tools"] = self._tools_for_chat_completions(self.functions)

        resp = self.client.chat.completions.create(**payload)
        message = resp.choices[0].message
        text = self._extract_assistant_text_from_chat(message)
        nav = self._extract_navigation_from_chat(message) if use_tools else ""
        return text, nav

    def message(
        self,
        question: Optional[str] = None,
        use_tools: bool = True,
        dense: bool = False,
        current_url: Optional[str] = None,
    ) -> str:
        if not self.tree:
            return "SiteTree not found. Please scan a site first."

        user_question = (question or "").strip()
        if not user_question:
            return "Please provide a question."

        if current_url:
            user_question += f" (User currently on page: {current_url})"
        if dense:
            user_question += " (If not using a tool call, answer in one sentence.)"

        self.messages.append({"role": "user", "content": user_question})

        text, nav_call = self._request_model(messages=self.messages, use_tools=use_tools)
        assistant_text = nav_call or text or "No response from model."

        self.messages.append({"role": "assistant", "content": assistant_text})
        return assistant_text

    def audio(
        self,
        audio_bytes: bytes,
        tts: bool = False,
        voice: str = "alloy",
        use_tools: bool = True,
        dense: bool = True,
        current_url: Optional[str] = None,
    ) -> Dict[str, object]:
        transcript = self.STT(audio_bytes)
        if not transcript.strip():
            reply = "I couldn't transcribe that audio. Please try again with a clearer recording."
            return {"ok": True, "transcript": "", "reply": reply, "reply_audio_b64": None}

        try:
            reply_text = self.message(
                question=transcript,
                use_tools=use_tools,
                dense=dense,
                current_url=current_url,
            )
        except Exception as exc:
            reply_text = f"Sorry, I ran into an error while answering: {exc}"

        if reply_text.startswith("send_link:") or reply_text.startswith("click_element:"):
            tts = False

        reply_audio_b64 = None
        if tts and reply_text:
            audio = self.TTS(reply_text, voice=voice)
            if audio:
                reply_audio_b64 = base64.b64encode(audio).decode("utf-8")

        return {
            "ok": True,
            "transcript": transcript,
            "reply": reply_text,
            "reply_audio_b64": reply_audio_b64,
        }


class LinkTool:
    def __init__(self) -> None:
        self.desc = {
            "type": "function",
            "name": "send_link",
            "description": "Navigate user to a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to."}
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            "strict": True,
        }


class ClickTool:
    def __init__(self) -> None:
        self.desc = {
            "type": "function",
            "name": "click_element",
            "description": "Click a UI element by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element": {
                        "type": "string",
                        "description": "CSS selector to click.",
                    }
                },
                "required": ["element"],
                "additionalProperties": False,
            },
            "strict": True,
        }


if __name__ == "__main__":
    tree = SiteTree().load("./tests/oorischubert.json")
    assistant = Assistant(tree)
    print(assistant.message("What projects does Oori have?"))
