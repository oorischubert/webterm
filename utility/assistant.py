from openai import OpenAI
import json, datetime
from .agentToolKit import SiteTree

MODEL = "gpt-4.1"

class Assistant:
    """Conversation helper that always stays grounded in a SiteTree."""

    def __init__(self, tree: SiteTree | None = None) -> None:
        self.client = OpenAI()
        self.tree: SiteTree | None = tree
        self.messages: list[dict] = []
        self.reset(tree)

    # ---------------- internal helpers ----------------
    def _system_prompt(self, tree: SiteTree) -> str:
        """Craft a single system / user primer that embeds the tree JSON."""
        return (
            f"The current time is {datetime.datetime.now()}. "
            "You are a helpful assistant whose goal is to help users find information "
            "on a specific website. The site structure is provided below in JSON SiteTree "
            "format (all pages + metadata). "
            "When the user asks a question, rely ONLY on that SiteTree to answer. "
            "If the user asks about anything unrelated to the site, respond with: "
            "\"Sorry, I can only discuss content related to <site name>.\" "
            f"\n\nSiteTree JSON:\n{tree.get_json()}"
        )

    # ---------------- public API ----------------
    def reset(self, tree: SiteTree | None = None) -> None:
        """Clear history and (optionally) switch to a new SiteTree."""
        if tree is not None:
            self.tree = tree
        self.messages = []
        if self.tree:
            self.messages.append(
                {"role": "user", "content": self._system_prompt(self.tree)}
            )

    def answer(self, question: str| None = None) -> str:
        """
        High-level helper:
        • If a new SiteTree is supplied, reset context first.
        • If no SiteTree, refuse politely.
        • Append the user's question, call the model, return assistant reply.
        """

        # Append user question
        self.messages.append({"role": "user", "content": question})

        resp = self.client.responses.create(
            model=MODEL,
            tools=[LinkTool().desc, ClickTool().desc], # type: ignore
            input=self.messages,  # keeps full thread for context # type: ignore
        )
        
        # Handle tool calls (function_call)
        out0 = resp.output[0]
        if hasattr(out0, "type") and out0.type == "function_call":
            if out0.name == "send_link" or out0.name == "click_element":
                # Parse the arguments (should be a dict with a "url" key)
                args = json.loads(out0.arguments)
                url = args.get("url", "")
                element = args.get("element", "")
                # Your convention: reply with special prefix (or just the URL if your frontend expects)
                assistant_text = f"send_link:{url}" if url else f"click_element:{element}" if element else ""
                self.messages.append({"role": "assistant", "content": assistant_text})
                return assistant_text
            
        # Fallback to text output
        assistant_text = (
            resp.output[0].content[0].text # type: ignore
            if resp.output and getattr(resp.output[0], "content", None)
            else "No response from model."
        )

        self.messages.append({"role": "assistant", "content": assistant_text})
        return assistant_text

class LinkTool:
    def __init__(self):
        self.desc = {
            "type": "function",
            "name": "send_link",
            "description": "Sends user to specified link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the web page to go to."}
                },
                "required": ["url"],
                "additionalProperties": False
            },
            "strict": True
        }
        
class ClickTool:
      def __init__(self):
        self.desc = {
            "type": "function",
            "name": "click_element",
            "description": "Simulates a click on a specified UI element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element": {"type": "string", "description": "The identifier of the UI element to click."}
                },
                "required": ["element"],
                "additionalProperties": False
            },
            "strict": True
        }

# Demo
if __name__ == "__main__":
    tree = SiteTree().load("./tests/oorischubert.json")
    assistant = Assistant(tree)
    print(assistant.answer("What projects does he have?"))