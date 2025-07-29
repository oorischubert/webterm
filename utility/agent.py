from openai import OpenAI
import json
import datetime
from agentToolKit import ToolKit

MODEL = "gpt-4.1"
INIT_PROMPT = "The current time is %s, you are a helpful assistant."%datetime.datetime.now()

class Agent:
    def __init__(self):
        self.toolkit = ToolKit()
        self.tools = [tool.desc for tool in self.toolkit.tools]
        self.client = OpenAI()
        self.messages = [{"role": "user", "content": INIT_PROMPT}]

    def call_toolkit(self, name: str, args: dict):
        """
        Call the toolkit function by name with the provided arguments.
        """
        tool = next((t for t in self.toolkit.tools if t.desc["name"] == name), None)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in toolkit.")
        
        func = getattr(tool, name, None)
        if not callable(func):
            raise ValueError(f"Function '{name}' is not callable.")

        return func(**args)  # type: ignore

    def spin(self, message: str, temp: bool = False, use_tools: bool = True, debug: bool = False) -> str:
        """
        Run an interactive loop with the model until it completes the task.

        Args:
            message: initial user instruction for the task.
            temp: if False, persist the conversation in self.messages; if True, use a
                  temporary copy that does not modify self.messages.
            use_tools: whether to allow the model to invoke the ToolKit.

        Returns:
            The final text response from the model after all tool calls are resolved.
        """
        # Decide which message buffer to use
        if temp:
            messages = list(self.messages)  # work on a copy
        else:
            messages = self.messages  # in‑place (persistent)

        # Add the initial user instruction
        user_msg = {"role": "user", "content": message}
        messages.append(user_msg)

        # Initial model response
        resp = self.client.responses.create(
            model=MODEL,
            input=messages,           # type: ignore
            tools=self.tools if use_tools else [],
        )

        while True:
            if debug:
                print("[DEBUG] Entering loop; function calls:" , [o.name for o in resp.output if o.type == 'function_call'])

            # If the model produced normal content (no function_call), we're done
            if not any(o.type == "function_call" for o in resp.output):
                break

            # Iterate through each tool call in the response
            for tool_call in resp.output:
                if tool_call.type != "function_call":
                    continue

                name = tool_call.name
                try:
                    args = json.loads(tool_call.arguments)
                except Exception:
                    args = {}

                if debug:
                    print(f"[DEBUG] Executing tool {name} with args {args}")
                # Execute the tool locally and capture the result
                try:
                    result = self.call_toolkit(name, args)
                except Exception as e:
                    result = f"[Tool error: {e}]"
                if debug:
                    print(f"[DEBUG] Result from {name} received.\n")

                # 1) Record the assistant's function call (avoid duplicates)
                if not any(
                    m.get("type") == "function_call" and m.get("call_id") == tool_call.call_id
                    for m in messages
                ):
                    messages.append(
                        tool_call.model_dump()  # type: ignore
                        if hasattr(tool_call, "model_dump")
                        else dict(tool_call)
                    )

                # 2) Provide the tool result back to the model (avoid duplicates)
                if not any(
                    m.get("type") == "function_call_output" and m.get("call_id") == tool_call.call_id
                    for m in messages
                ):
                    messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": str(result),
                        }
                    )

            # New model response after tool outputs
            resp = self.client.responses.create(
                model=MODEL,
                input=messages,           # type: ignore
                tools=self.tools if use_tools else [],
            )
            if debug:
                print("[DEBUG] Model response complete.")

        # Return the final textual answer
        if debug:
                print("[DEBUG] Agent task complete, returning final response.\n")
        final_text = resp.output[0].content[0].text  # type: ignore
        return final_text

    def message(self, message: str, temp: bool = True, use_tools: bool = False) -> str:
        """
        Send a user message to the model. If the model responds with a tool call
        (when use_tools=True), automatically invoke the toolkit and return the
        tool's result. Otherwise return the plain text content.

        Args:
            message: user message
            temp: if False, add message to permanent history
            use_tools: allow the model to call functions

        Returns:
            A string containing either the model's text response or the result
            of the invoked tool.
        """
        user_msg = {"role": "user", "content": message}
        if not temp:
            self.messages.append(user_msg)

        resp = self.client.responses.create(
            model=MODEL,
            tools=self.tools if use_tools else [],
            input=[user_msg] if temp else self.messages,  # type: ignore
        )

        # The first element in resp.output can be either:
        # - a normal text response (with .content)
        # - a ResponseFunctionToolCall (with .name / .arguments)
        out0 = resp.output[0]

        # 1) Plain text response
        if hasattr(out0, "content"):
            # It's a list of message chunks; take first
            return out0.content[0].text  # type: ignore

        # 2) Tool call
        if hasattr(out0, "name") and hasattr(out0, "arguments"):
            tool_name: str = out0.name  # type: ignore
            try:
                tool_args = json.loads(out0.arguments)  # type: ignore
            except Exception:
                tool_args = {}
            try:
                tool_result = self.call_toolkit(tool_name, tool_args)
            except Exception as e:
                tool_result = f"[Tool error: {e}]"
            return str(tool_result)

        # 3) Fallback: stringify the unknown response type
        return str(out0)
        
if __name__ == "__main__":
    agent = Agent()
    print(agent.spin("please describe page contents of oorischubert.com. If subpages exist go to them as well and explain their contents.",debug=True))