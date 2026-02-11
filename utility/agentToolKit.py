from __future__ import annotations

from bs4 import BeautifulSoup, Comment, Tag
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
import json
import requests


class ToolKit:
    """Container for all tools exposed to the Agent."""

    def __init__(self) -> None:
        self.tools = [
            SiteScannerTool(),
            SetPageDescriptionTool(),
            SetPageButtonsTool(),
        ]


class SiteScannerTool:
    """Scan pages and propagate a site graph into a SiteTree."""

    DEFAULT_TIMEOUT = 8
    DEFAULT_MAX_PAGES = 40

    def __init__(self) -> None:
        self.tree = SiteTree()
        self.latest_buttons: List[Dict[str, str]] = []
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "WebTerm-SiteScanner/2.0"})
        self.desc = [
            {
                "type": "function",
                "name": "pageScanner",
                "description": "Fetch UI content for one page and return cleaned HTML and clickable elements.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Page URL."},
                        "timeout": {
                            "type": ["integer", "null"],
                            "description": "Request timeout in seconds (default 8).",
                        },
                    },
                    "required": ["url", "timeout"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "sitePropagator",
                "description": "Build a same-site page tree from a root URL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Root URL."},
                        "n": {
                            "type": ["integer", "null"],
                            "description": "Maximum crawl depth, root at 0 (default 1).",
                        },
                        "restrict_to_subpath": {
                            "type": ["boolean", "null"],
                            "description": "When true, only crawl URLs under the root path.",
                        },
                        "max_pages": {
                            "type": ["integer", "null"],
                            "description": "Maximum number of pages to include (default 40).",
                        },
                    },
                    "required": ["url", "n", "restrict_to_subpath", "max_pages"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def normalize(self, url: str) -> str:
        """Normalize URL by adding scheme and stripping fragments/trailing slash."""
        raw = (url or "").strip()
        if not raw:
            return ""

        parsed = urlparse(raw)
        if not parsed.scheme:
            raw = "https://" + raw
            parsed = urlparse(raw)

        normalized = parsed._replace(fragment="").geturl()
        root = f"{parsed.scheme}://{parsed.netloc}/"
        return normalized if normalized == root else normalized.rstrip("/")

    def pageScanner(self, url: str, timeout: Optional[int] = DEFAULT_TIMEOUT) -> Dict[str, object]:
        """Fetch and parse one page into cleaned HTML + button metadata."""
        clean_url = self.normalize(url)
        if not clean_url:
            return {}

        timeout_value = self.DEFAULT_TIMEOUT if timeout is None else max(1, int(timeout))
        html = self._fetch_html(clean_url, timeout=timeout_value)
        if html is None:
            return {}

        content, buttons = self._clean_html_and_extract_buttons(html)
        self.latest_buttons = buttons
        return {"content": content, "buttons": buttons}

    def get_page_content(self, html: str) -> str:
        """Backward compatible API used by older call paths."""
        content, buttons = self._clean_html_and_extract_buttons(html)
        self.latest_buttons = buttons
        return content

    def sitePropagator(
        self,
        url: str,
        n: Optional[int] = 1,
        restrict_to_subpath: Optional[bool] = True,
        max_pages: Optional[int] = DEFAULT_MAX_PAGES,
    ) -> "SiteTree":
        """Breadth-first crawl that returns a SiteTree."""
        start = self.normalize(url)
        if not start:
            raise ValueError("sitePropagator requires a non-empty URL")

        depth_limit = 1 if n is None else max(0, int(n))
        page_limit = max(1, int(max_pages or self.DEFAULT_MAX_PAGES))
        restrict = True if restrict_to_subpath is None else bool(restrict_to_subpath)

        self.tree = SiteTree(root_url=start)
        visited: Set[str] = {start}
        queue = deque([(start, 0)])

        base_parsed = urlparse(start)
        base_root = f"{base_parsed.scheme}://{base_parsed.netloc}"
        base_path = (base_parsed.path or "").rstrip("/")

        while queue and len(visited) < page_limit:
            current, depth = queue.popleft()
            if depth >= depth_limit:
                continue

            html = self._fetch_html(current, timeout=self.DEFAULT_TIMEOUT)
            if html is None:
                continue

            filtered_html = self.get_page_content(html)
            try:
                soup = BeautifulSoup(filtered_html, "html.parser")
            except Exception:
                continue

            for anchor in soup.find_all("a", href=True):
                href = str(anchor.get("href", "")).strip()
                if not href:
                    continue

                child = self.normalize(urljoin(current, href))
                if not child:
                    continue
                if not self._is_crawlable_http_url(child):
                    continue
                if not self._is_same_site(child, base_root):
                    continue
                if restrict and not self._is_under_base_path(child, base_path):
                    continue
                if child in visited:
                    continue

                self.tree.add(current, child)
                visited.add(child)

                if len(visited) >= page_limit:
                    break
                queue.append((child, depth + 1))

        return self.tree

    # Backward-compatible typo alias used in README/examples.
    def sitePropogator(
        self,
        url: str,
        n: Optional[int] = 1,
        restrict_to_subpath: Optional[bool] = True,
        max_pages: Optional[int] = DEFAULT_MAX_PAGES,
    ) -> "SiteTree":
        return self.sitePropagator(
            url=url,
            n=n,
            restrict_to_subpath=restrict_to_subpath,
            max_pages=max_pages,
        )

    def _fetch_html(self, url: str, timeout: int) -> Optional[str]:
        try:
            response = self._session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except Exception:
            return None

    @staticmethod
    def _is_crawlable_http_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"}

    @staticmethod
    def _is_same_site(url: str, base_root: str) -> bool:
        parsed = urlparse(url)
        this_root = f"{parsed.scheme}://{parsed.netloc}"
        return this_root == base_root

    @staticmethod
    def _is_under_base_path(url: str, base_path: str) -> bool:
        if not base_path:
            return True
        parsed = urlparse(url)
        path = (parsed.path or "").rstrip("/")
        return path == base_path or path.startswith(base_path + "/")

    def _clean_html_and_extract_buttons(self, html: str) -> tuple[str, List[Dict[str, str]]]:
        soup = BeautifulSoup(html, "html.parser")

        removable_tags = [
            "script",
            "style",
            "meta",
            "link",
            "title",
            "head",
            "noscript",
            "template",
            "svg",
            "path",
            "defs",
            "clipPath",
            "linearGradient",
            "radialGradient",
            "pattern",
            "mask",
        ]

        for tag_name in removable_tags:
            for tag in list(soup.find_all(tag_name)):
                if isinstance(tag, Tag):
                    tag.decompose()

        for comment in list(soup.find_all(string=lambda text: isinstance(text, Comment))):
            comment.extract()

        hidden_classes = {"hidden", "sr-only", "visually-hidden", "d-none", "invisible"}

        for element in list(soup.find_all(True)):
            if not isinstance(element, Tag):
                continue
            style = str(element.get("style", ""))
            compact_style = style.replace(" ", "").lower()
            if "display:none" in compact_style or "visibility:hidden" in compact_style:
                element.decompose()
                continue

            class_list = element.get("class") or []
            if isinstance(class_list, str):
                class_list = class_list.split()
            if hidden_classes.intersection({str(c) for c in class_list}):
                element.decompose()

        buttons = self._extract_clickable_elements(soup)
        compact_html = "\n".join(line for line in str(soup).splitlines() if line.strip())
        return compact_html, buttons

    def _extract_clickable_elements(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        buttons: List[Dict[str, str]] = []
        seen_pairs: Set[tuple[str, str]] = set()

        selectors: List[tuple[str, Dict[str, List[str] | str]]] = [
            ("button", {}),
            ("a", {}),
            ("input", {"type": ["button", "submit"]}),
            ("[role='button']", {}),
        ]

        for query, attr_req in selectors:
            elements = soup.select(query) if query.startswith("[") else soup.find_all(query)
            for element in elements:
                if not isinstance(element, Tag):
                    continue
                if element.get("hidden") is not None:
                    continue
                if not self._matches_required_attrs(element, attr_req):
                    continue

                selector = self._build_selector(element)
                text = self._extract_clickable_text(element)
                key = (selector, text)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                buttons.append({"selector": selector, "text": text})

        return buttons

    @staticmethod
    def _matches_required_attrs(element: Tag, requirements: Dict[str, List[str] | str]) -> bool:
        for attr_name, expected in requirements.items():
            value = element.get(attr_name, "")
            if isinstance(value, list):
                value_str = " ".join(str(v).lower() for v in value)
            else:
                value_str = str(value).lower()

            if isinstance(expected, list):
                expected_set = {str(v).lower() for v in expected}
                if value_str not in expected_set:
                    return False
            else:
                if value_str != str(expected).lower():
                    return False
        return True

    @staticmethod
    def _escape_css_value(value: str) -> str:
        return value.replace('"', '\\"')

    def _build_selector(self, element: Tag) -> str:
        if element.get("id"):
            return f"#{element.get('id')}"

        classes = element.get("class")
        if classes:
            class_list = classes if isinstance(classes, list) else str(classes).split()
            if class_list:
                return f"{element.name}." + ".".join(str(c) for c in class_list)

        if element.name == "a" and element.get("href"):
            href = self._escape_css_value(str(element.get("href")))
            return f'a[href="{href}"]'

        if element.name == "input" and element.get("name"):
            name = self._escape_css_value(str(element.get("name")))
            return f'input[name="{name}"]'

        nth = sum(1 for _ in element.find_previous_siblings(element.name)) + 1
        return f"{element.name}:nth-of-type({nth})"

    @staticmethod
    def _extract_clickable_text(element: Tag) -> str:
        text = element.get_text(strip=True) if hasattr(element, "get_text") else ""
        if text:
            return text

        for attr in ("value", "title", "aria-label", "alt"):
            value = element.get(attr)
            if value:
                if isinstance(value, list):
                    return " ".join(str(v) for v in value).strip()
                return str(value).strip()
        return ""


class SetPageDescriptionTool:
    def __init__(self) -> None:
        self.desc = [
            {
                "type": "function",
                "name": "set_page_description",
                "description": "Set or update the description for a URL node in the SiteTree.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Node URL."},
                        "description": {"type": "string", "description": "Page summary."},
                    },
                    "required": ["url", "description"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ]

    def set_page_description(self, url: str, description: str, tree: "SiteTree") -> "SiteTree":
        normalized_url = SiteScannerTool().normalize(url)
        node = tree.nodes.get(normalized_url)
        if node is None:
            raise ValueError(f"URL '{url}' not found in provided SiteTree.")
        node.desc = description
        return tree


class SetPageButtonsTool:
    def __init__(self) -> None:
        self.desc = [
            {
                "type": "function",
                "name": "set_page_buttons",
                "description": "Set or update clickable elements for a URL node in the SiteTree.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Node URL."},
                        "buttons": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "selector": {
                                        "type": "string",
                                        "description": "CSS selector for the element.",
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "Visible label for the element.",
                                    },
                                },
                                "required": ["selector", "text"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["url", "buttons"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ]

    def set_page_buttons(self, url: str, buttons: list, tree: "SiteTree") -> "SiteTree":
        normalized_url = SiteScannerTool().normalize(url)
        node = tree.nodes.get(normalized_url)
        if node is None:
            raise ValueError(f"URL '{url}' not found in provided SiteTree.")
        node.buttons = list(buttons)
        return tree


class SiteTree:
    """Tree of SiteNode objects, addressed by URL strings."""

    def __init__(self, root_url: Optional[str] = None) -> None:
        self.nodes: Dict[str, SiteNode] = {}
        self.children: Dict[str, Set[str]] = {}
        self.root_url: Optional[str] = None
        if root_url:
            self.set_root(root_url)

    def _get_or_create_node(self, url: str) -> "SiteNode":
        if url not in self.nodes:
            self.nodes[url] = SiteNode(url=url)
        return self.nodes[url]

    def set_root(self, root_url: str) -> None:
        self.root_url = root_url
        root_node = self._get_or_create_node(root_url)
        self.children.setdefault(root_node.url, set())

    def add(self, parent_url: str, child_url: str) -> None:
        parent = self._get_or_create_node(parent_url)
        child = self._get_or_create_node(child_url)
        self.children.setdefault(parent.url, set()).add(child.url)
        self.children.setdefault(child.url, set())

    def exists(self, url: str) -> bool:
        return url in self.nodes

    def is_empty(self) -> bool:
        return not self.nodes

    def node_count(self) -> int:
        return len(self.nodes)

    def longest_branch_len(self) -> int:
        if not self.root_url:
            return 0

        def dfs(url: str) -> int:
            kids = self.children.get(url, set())
            if not kids:
                return 0
            return 1 + max(dfs(child) for child in kids)

        return dfs(self.root_url)

    def to_dict(self) -> Dict[str, object]:
        return {
            "root_url": self.root_url,
            "nodes": {
                url: {"desc": node.desc, "buttons": node.buttons}
                for url, node in self.nodes.items()
            },
            "children": {parent: sorted(list(kids)) for parent, kids in self.children.items()},
        }

    def get_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save(self, filename: str) -> None:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(self.to_dict(), file, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filename: str) -> "SiteTree":
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)

        tree = cls(root_url=data.get("root_url"))

        for url, meta in (data.get("nodes") or {}).items():
            node = SiteNode(url=url, desc=str(meta.get("desc", "")))
            node.buttons = list(meta.get("buttons", []))
            tree.nodes[url] = node

        for parent, children in (data.get("children") or {}).items():
            tree.children[parent] = set(children)

        for url in tree.nodes:
            tree.children.setdefault(url, set())

        if tree.root_url and tree.root_url not in tree.nodes:
            tree.nodes[tree.root_url] = SiteNode(url=tree.root_url)
            tree.children.setdefault(tree.root_url, set())

        return tree

    def __str__(self) -> str:
        if not self.root_url:
            return "<empty SiteTree>"

        lines: List[str] = [self.root_url]

        def build(url: str, prefix: str) -> None:
            children = sorted(self.children.get(url, set()))
            for i, child in enumerate(children):
                connector = "└─ " if i == len(children) - 1 else "├─ "
                lines.append(f"{prefix}{connector}{child}")
                extension = "   " if i == len(children) - 1 else "│  "
                build(child, prefix + extension)

        build(self.root_url, "")
        return "\n".join(lines)


@dataclass
class SiteNode:
    url: str
    desc: str = ""
    buttons: List[Dict[str, str]] | None = None

    def __post_init__(self) -> None:
        if self.buttons is None:
            self.buttons = []

    def __hash__(self) -> int:
        return hash(self.url)

    def __str__(self) -> str:
        return self.url


if __name__ == "__main__":
    scanner = SiteScannerTool()
    output = scanner.pageScanner("https://oorischubert.com/contact.html")
    print(output)
