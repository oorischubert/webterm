from openai import OpenAI
import json
import datetime
from utility.agentToolKit import ToolKit #why tf do i need this here? I already imported it in agentToolKit.py

INIT_PROMPT = "The current time is %s, you are a helpful assistant."%datetime.datetime.now()
USER_PROMPT = "What is the coal production output of colombia this year?."

# ─── 1. Initialise toolkit and expose ONLY the toolkit function ────────────
toolkit = ToolKit()
tools = [tool.desc for tool in toolkit.tools]    # GPT sees get_tool_desc and use_tool

def call_toolkit(name: str, args: dict):
    """
    Call the toolkit function by name with the provided arguments.
    """
    tool = next((t for t in toolkit.tools if t.desc["name"] == name), None)
    if not tool:
        raise ValueError(f"Tool '{name}' not found in toolkit.")
    
    # Call the function dynamically
    func = getattr(tool, name, None)
    if not callable(func):
        raise ValueError(f"Function '{name}' is not callable.")
    
    return func(**args)  # type: ignore
# ─── 2. Chat loop ──────────────────────────────────────────────────────────
client = OpenAI()
messages = [ {"role": "user", "content": INIT_PROMPT},{"role": "user", "content": USER_PROMPT} ]

while True:
    resp = client.responses.create(
        model="gpt-4.1",
        input=messages,        # type: ignore
        tools=tools,           # get_tool_desc and use_tool
    )
    print("RESP:",resp,'\n')

    # Stop if GPT answered the user
    if not any(o.type == "function_call" for o in resp.output):
        break
    
    for tool_call in resp.output:
        if tool_call.type != "function_call":
            continue

        # 2) Execute the function locally
        name = tool_call.name
        args = json.loads(tool_call.arguments)

        # 2) Execute the function locally
        result = call_toolkit(name, args)
        print("RESULT:",result,'\n')
        
        # Record the assistant's function call (avoid duplicates)
        if not any(m.get("type") == "function_call" and m.get("call_id") == tool_call.call_id for m in messages):
            messages.append(tool_call.model_dump() if hasattr(tool_call, "model_dump") else dict(tool_call))
        
        # Provide the tool result back (avoid duplicates)
        if not any(m.get("type") == "function_call_output" and m.get("call_id") == tool_call.call_id for m in messages):
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": str(result)
            })
    
# ─── 3. Print GPT's final answer ───────────────────────────────────────────
print(resp.output[0].content[0].text) # type: ignore

