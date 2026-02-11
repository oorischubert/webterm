from __future__ import annotations

import datetime
import json
import os
import copy
from typing import Any, Dict, List, Tuple

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
        raw_tools = [desc for tool in self.toolkit.tools for desc in tool.desc]
        self.tools = self._sanitize_tool_schemas(raw_tools)
        self.client = OpenAI()
        self._use_responses_api = hasattr(self.client, "responses")
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
    def _extract_output_text_from_responses(resp: Any) -> str:
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
    def _extract_calls_from_responses(resp: Any) -> List[Dict[str, str]]:
        calls: List[Dict[str, str]] = []
        for item in getattr(resp, "output", []):
            if getattr(item, "type", None) != "function_call":
                continue
            calls.append(
                {
                    "call_id": str(getattr(item, "call_id", "")),
                    "name": str(getattr(item, "name", "")),
                    "arguments": str(getattr(item, "arguments", "{}")),
                }
            )
        return calls

    @staticmethod
    def _extract_text_from_chat_completion(message: Any) -> str:
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
    def _extract_calls_from_chat_completion(message: Any) -> List[Dict[str, str]]:
        calls: List[Dict[str, str]] = []
        for call in getattr(message, "tool_calls", []) or []:
            fn = getattr(call, "function", None)
            if fn is None:
                continue
            calls.append(
                {
                    "call_id": str(getattr(call, "id", "")),
                    "name": str(getattr(fn, "name", "")),
                    "arguments": str(getattr(fn, "arguments", "{}")),
                }
            )
        return calls

    @staticmethod
    def _sanitize_tool_schemas(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ensure tool schemas are strict-compatible by making `required` include all properties.
        This prevents recurring schema errors from strict function definitions.
        """
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
        """
        Convert Responses API tool schema into Chat Completions schema.
        Responses shape:
          {"type":"function","name":"...","description":"...","parameters":{...}}
        Chat shape:
          {"type":"function","function":{"name":"...","description":"...","parameters":{...}}}
        """
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

    def _request_model(self, messages: List[Dict[str, Any]], use_tools: bool) -> Tuple[str, List[Dict[str, str]], str]:
        if self._use_responses_api:
            resp = self.client.responses.create(
                model=self.model,
                input=messages,
                tools=self.tools if use_tools else [],
            )
            text = self._extract_output_text_from_responses(resp)
            calls = self._extract_calls_from_responses(resp) if use_tools else []
            return text, calls, "responses"

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if use_tools:
            payload["tools"] = self._tools_for_chat_completions(self.tools)

        resp = self.client.chat.completions.create(**payload)
        message = resp.choices[0].message
        text = self._extract_text_from_chat_completion(message)
        calls = self._extract_calls_from_chat_completion(message) if use_tools else []
        return text, calls, "chat"

    @staticmethod
    def _parse_call_arguments(raw_args: str) -> dict:
        try:
            parsed = json.loads(raw_args or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _execute_tool_call(self, name: str, raw_arguments: str, debug: bool = False) -> Any:
        args = self._parse_call_arguments(raw_arguments)

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

        max_iterations = max(1, tool_budget * 3 + 2)

        for _ in range(max_iterations):
            text, function_calls, backend = self._request_model(messages=messages, use_tools=use_tools)

            if not function_calls or not use_tools:
                final_text = text or "No response from model."
                if not temp:
                    self.messages.append({"role": "assistant", "content": final_text})
                return final_text

            processed_this_round = 0

            if backend == "responses":
                for call in function_calls:
                    if tool_budget <= 0:
                        break

                    name = call.get("name", "")
                    call_id = call.get("call_id", "")
                    raw_args = call.get("arguments", "{}")

                    try:
                        result = self._execute_tool_call(name=name, raw_arguments=raw_args, debug=debug)
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
            else:
                executed_calls: List[Dict[str, str]] = []
                tool_outputs: List[Dict[str, str]] = []

                for idx, call in enumerate(function_calls):
                    if tool_budget <= 0:
                        break

                    name = call.get("name", "")
                    call_id = call.get("call_id", "") or f"call_{idx}"
                    raw_args = call.get("arguments", "{}")

                    try:
                        result = self._execute_tool_call(name=name, raw_arguments=raw_args, debug=debug)
                    except Exception as exc:
                        result = f"[Tool error: {exc}]"

                    executed_calls.append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": raw_args},
                        }
                    )
                    tool_outputs.append({"tool_call_id": call_id, "content": str(result)})

                    processed_this_round += 1
                    tool_budget -= 1

                if executed_calls:
                    messages.append({"role": "assistant", "content": "", "tool_calls": executed_calls})
                    for output in tool_outputs:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": output["tool_call_id"],
                                "content": output["content"],
                            }
                        )

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

        text, function_calls, _ = self._request_model(messages=messages, use_tools=use_tools)

        if use_tools and function_calls:
            first = function_calls[0]
            try:
                result = self._execute_tool_call(
                    name=first.get("name", ""),
                    raw_arguments=first.get("arguments", "{}"),
                )
                output_text = str(result)
            except Exception as exc:
                output_text = f"[Tool error: {exc}]"
        else:
            output_text = text or "No response from model."

        if not temp:
            self.messages.append({"role": "assistant", "content": output_text})
        return output_text


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
