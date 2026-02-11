from __future__ import annotations

import datetime
import json

from openai import OpenAI

from utility.agentToolKit import ToolKit


MODEL = "gpt-5.2"
INIT_PROMPT = f"The current time is {datetime.datetime.now().isoformat()}. You are a helpful assistant."
USER_PROMPT = "What is the coal production output of Colombia this year?"


def call_toolkit(toolkit: ToolKit, name: str, args: dict):
    for tool in toolkit.tools:
        descs = tool.desc if isinstance(tool.desc, list) else [tool.desc]
        if any(desc.get("name") == name for desc in descs):
            fn = getattr(tool, name, None)
            if callable(fn):
                return fn(**args)
    raise ValueError(f"Tool '{name}' not found or not callable.")


def main() -> None:
    toolkit = ToolKit()
    tools = [desc for tool in toolkit.tools for desc in tool.desc]

    client = OpenAI()
    messages = [
        {"role": "system", "content": INIT_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]

    while True:
        response = client.responses.create(model=MODEL, input=messages, tools=tools)

        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            break

        for call in calls:
            args = json.loads(getattr(call, "arguments", "{}") or "{}")
            result = call_toolkit(toolkit, getattr(call, "name", ""), args)

            messages.append(
                {
                    "type": "function_call",
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
            )
            messages.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": str(result),
                }
            )

    final_text = ""
    for item in response.output:
        content = getattr(item, "content", None)
        if content and getattr(content[0], "text", None):
            final_text = content[0].text
            break
    print(final_text)


if __name__ == "__main__":
    main()
