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
            input=self.messages,  # keeps full thread for context # type: ignore
        )

        assistant_text = (
            resp.output[0].content[0].text # type: ignore
            if resp.output and getattr(resp.output[0], "content", None)
            else "No response from model."
        )

        self.messages.append({"role": "assistant", "content": assistant_text})
        return assistant_text


# Demo
if __name__ == "__main__":
    tree = SiteTree().load("./tests/oorischubert.json")
    assistant = Assistant(tree)
    print(assistant.answer("What projects does he have?"))