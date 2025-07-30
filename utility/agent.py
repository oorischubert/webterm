from openai import OpenAI
import json
import datetime
from .agentToolKit import ToolKit, SiteTree

MODEL = "gpt-4.1-mini"
MAX_TOOL_CALLS = 3
INIT_PROMPT = "The current time is %s, you are a helpful assistant."%datetime.datetime.now()

class Agent:
    def __init__(self):
        self.toolkit = ToolKit()
        self.tools = [desc for tool in self.toolkit.tools for desc in tool.desc]
        self.client = OpenAI()
        self.tree = SiteTree()
        self.messages = [{"role": "user", "content": INIT_PROMPT}]

    def reset(self):
        """
        Reset the agent's state, clearing the conversation history and tree.
        """
        self.tree = SiteTree()
        self.messages = [{"role": "user", "content": INIT_PROMPT}]
        
    def call_toolkit(self, name: str, args: dict, debug: bool = False):
        """
        Look up a toolkit function by name and execute it with args.

        `tool.desc` may now be a *list* of description dicts, so we must
        search inside that list to match the function name.
        """
        tool_obj = None
        for t in self.toolkit.tools:
            descs = t.desc if isinstance(t.desc, list) else [t.desc]
            if any(d.get("name") == name for d in descs):
                tool_obj = t
                break

        if not tool_obj:
            if debug:
                print(f"[DEBUG] (call_toolkit) ERROR: Tool '{name}' not found\n")
            raise ValueError(f"Tool '{name}' not found in toolkit.")

        func = getattr(tool_obj, name, None)
        if not callable(func):
            if debug:
                print(f"[DEBUG] (call_toolkit) ERROR: Function '{name}' not callable on {tool_obj}\n")
            raise ValueError(f"Function '{name}' is not callable.")

        # Call the function with the provided arguments
        try:
            result = func(**args)  # type: ignore
        except TypeError as e:
            # Surface argument mismatch clearly
            raise ValueError(f"Argument error for {name}: {e}") from e

        return result

    def spin(self, message: str, temp: bool = False, use_tools: bool = True, debug: bool = False, max_tool_calls: int = MAX_TOOL_CALLS) -> str:
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
                print("[DEBUG] (spin) Entering loop; function calls:" , [o.name for o in resp.output if o.type == 'function_call'])

            # If the model produced normal content (no function_call), we're done
            if not any(o.type == "function_call" for o in resp.output):
                break

            # Iterate through each tool call in the response, limited by MAX_TOOL_CALLS
            tool_calls_processed = 0
            for tool_call in resp.output:
                if tool_call.type != "function_call":
                    continue
                if tool_calls_processed >= max_tool_calls:
                    if debug:
                        print(f"[DEBUG] (spin) Tool call limit ({max_tool_calls}) reached for this iteration.\n")
                    break
                tool_calls_processed += 1
                name = tool_call.name
                try:
                    args = json.loads(tool_call.arguments)
                except Exception:
                    args = {}

                if debug:
                    print(f"[DEBUG] (spin) Executing tool {name} with args {args}")
                # Inject or capture SiteTree as needed
                try:
                    if name == "set_page_description" or name == "set_page_buttons":
                        # LLM provides url & description; we inject the current tree
                        args = dict(args)  # shallow copy
                        args["tree"] = self.tree
                        result = self.call_toolkit(name, args, debug=debug)
                        # keep any updates returned
                        if isinstance(result, SiteTree):
                            self.tree = result
                    else:
                        result = self.call_toolkit(name, args, debug=debug)
                        if name == "sitePropagator" and isinstance(result, SiteTree):
                            self.tree = result
                except Exception as e:
                    result = f"[Tool error: {e}]"
                if debug:
                    print(f"[DEBUG] (spin) Result from {name} received.\n")

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
                print("[DEBUG] (spin) Model response complete.")

        # Return the final textual answer
        if debug:
                print("[DEBUG] (spin) Agent task complete, returning final response.\n")
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
                if tool_name == "set_page_description":
                    tool_args = dict(tool_args)
                    tool_args["tree"] = self.tree
                    tool_result = self.call_toolkit(tool_name, tool_args)
                    if isinstance(tool_result, SiteTree):
                        self.tree = tool_result
                else:
                    tool_result = self.call_toolkit(tool_name, tool_args)
                    if tool_name == "sitePropagator" and isinstance(tool_result, SiteTree):
                        self.tree = tool_result
            except Exception as e:
                tool_result = f"[Tool error: {e}]"
            return str(tool_result)

        # 3) Fallback: stringify the unknown response type
        return str(out0)
        
if __name__ == "__main__":
    agent = Agent()
    site = "oorischubert.com"
    print(agent.spin(f"please describe page contents of {site}. Create a tree of the subpages and set their descriptions.",debug=True))
    print(agent.tree)
    agent.tree.save("oorischubert_tree.json")