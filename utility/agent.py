from __future__ import annotations

import datetime
import json
import os
from typing import Any, Dict, List

from openai import OpenAI

try:
    from .agentToolKit import SiteTree, ToolKit
except ImportError:
    from agentToolKit import SiteTree, ToolKit


DEFAULT_MODEL = os.getenv("WEBTERM_AGENT_MODEL", os.getenv("WEBTERM_MODEL", "gpt-5.2"))
DEFAULT_MAX_TOOL_CALLS = int(os.getenv("WEBTERM_MAX_TOOL_CALLS", "5"))
INIT_PROMPT = f"The current time is {datetime.datetime.now().isoformat()}. You are a helpful assistant."


class Agent:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self.toolkit = ToolKit()
        self.tools = [desc for tool in self.toolkit.tools for desc in tool.desc]
        self.client = OpenAI()
        self.tree = SiteTree()
        self.messages: List[Dict[str, Any]] = [{"role": "system", "content": INIT_PROMPT}]

    def reset(self) -> None:
        self.tree = SiteTree()
        self.messages = [{"role": "system", "content": INIT_PROMPT}]

    def call_toolkit(self, name: str, args: dict, debug: bool = False) -> Any:
        tool_obj = None
        for tool in self.toolkit.tools:
            descs = tool.desc if isinstance(tool.desc, list) else [tool.desc]
            if any(desc.get("name") == name for desc in descs):
                tool_obj = tool
                break

        if tool_obj is None:
            raise ValueError(f"Tool '{name}' not found in toolkit.")

        fn = getattr(tool_obj, name, None)
        if not callable(fn):
            raise ValueError(f"Function '{name}' is not callable.")

        if debug:
            print(f"[DEBUG] (call_toolkit) {name}({args})")

        return fn(**args)

    @staticmethod
    def _extract_output_text(resp: Any) -> str:
        for item in getattr(resp, "output", []):
            if getattr(item, "type", None) == "reasoning":
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
    def _extract_function_calls(resp: Any) -> List[Any]:
        return [
            item
            for item in getattr(resp, "output", [])
            if getattr(item, "type", None) == "function_call"
        ]

    @staticmethod
    def _parse_call_arguments(raw_args: str) -> dict:
        try:
            parsed = json.loads(raw_args or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _execute_tool_call(self, call: Any, debug: bool = False) -> Any:
        name = getattr(call, "name", "")
        args = self._parse_call_arguments(getattr(call, "arguments", ""))

        if name in {"set_page_description", "set_page_buttons"}:
            args = dict(args)
            args["tree"] = self.tree

        result = self.call_toolkit(name=name, args=args, debug=debug)

        if name == "sitePropagator" and isinstance(result, SiteTree):
            self.tree = result
        if name in {"set_page_description", "set_page_buttons"} and isinstance(result, SiteTree):
            self.tree = result

        return result

    def spin(
        self,
        message: str,
        temp: bool = False,
        use_tools: bool = True,
        debug: bool = False,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ) -> str:
        if not (message or "").strip():
            return ""

        tool_budget = max(0, int(max_tool_calls))
        messages = list(self.messages) if temp else self.messages
        messages.append({"role": "user", "content": message})

        # hard cap to avoid infinite loops even if model keeps requesting tools.
        max_iterations = max(1, tool_budget * 3 + 2)

        for _ in range(max_iterations):
            resp = self.client.responses.create(
                model=self.model,
                input=messages,
                tools=self.tools if use_tools else [],
            )

            function_calls = self._extract_function_calls(resp)
            if not function_calls or not use_tools:
                final_text = self._extract_output_text(resp) or "No response from model."
                if not temp:
                    self.messages.append({"role": "assistant", "content": final_text})
                return final_text

            processed_this_round = 0
            for call in function_calls:
                if tool_budget <= 0:
                    break

                name = getattr(call, "name", "")
                call_id = getattr(call, "call_id", None)
                raw_args = getattr(call, "arguments", "{}")

                try:
                    result = self._execute_tool_call(call, debug=debug)
                except Exception as exc:
                    result = f"[Tool error: {exc}]"

                messages.append(
                    {
                        "type": "function_call",
                        "call_id": call_id,
                        "name": name,
                        "arguments": raw_args,
                    }
                )
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": str(result),
                    }
                )

                processed_this_round += 1
                tool_budget -= 1

            if processed_this_round == 0:
                break

        fallback = "Stopped after reaching tool-call limits."
        if not temp:
            self.messages.append({"role": "assistant", "content": fallback})
        return fallback

    def message(self, message: str, temp: bool = True, use_tools: bool = False) -> str:
        if not (message or "").strip():
            return ""

        messages = list(self.messages) if temp else self.messages
        messages.append({"role": "user", "content": message})

        resp = self.client.responses.create(
            model=self.model,
            tools=self.tools if use_tools else [],
            input=messages,
        )

        function_calls = self._extract_function_calls(resp)
        if use_tools and function_calls:
            call = function_calls[0]
            try:
                result = self._execute_tool_call(call)
                text = str(result)
            except Exception as exc:
                text = f"[Tool error: {exc}]"
        else:
            text = self._extract_output_text(resp) or "No response from model."

        if not temp:
            self.messages.append({"role": "assistant", "content": text})
        return text


if __name__ == "__main__":
    agent = Agent()
    site = "oorischubert.com"
    print(
        agent.spin(
            f"Please scan {site}, build a site tree, and describe each page.",
            debug=True,
        )
    )
    print(agent.tree)
    agent.tree.save("oorischubert_tree.json")
