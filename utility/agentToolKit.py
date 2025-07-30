from bs4 import BeautifulSoup, Comment, Tag
from urllib.parse import urljoin, urlparse
from typing import Optional, Dict, Set, List
import requests
from collections import deque
import json

class ToolKit:
    _faiss_index = None
    def __init__(self):
        # instantiate each tool and keep them in a list
        self.tools = [
            SiteScannerTool(),
            SetPageDescriptionTool(),
            SetPageButtonsTool(),
        ]
    
class SiteScannerTool:
    def __init__(self):
        self.tree = SiteTree()
        self.desc = [{
            "type": "function",
            "name": "pageScanner",
            "description": "Fetch UI content of a web page from a URL and return a JSON object with the cleaned visible HTML (`content`) and a list of clickable button elements (`buttons`).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the web page to fetch."}
                },
                "required": ["url"],
                "additionalProperties": False
            },
            "strict": True
        },{
            "type": "function",
            "name": "sitePropagator",
            "description": "Build a tree of subpages starting from `url`. Considers only links that belong to the same site and are subpages of the original URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the web page to fetch."}
                },
                "required": ["url"],
                "additionalProperties": False
            },
            "strict": True
        }]
        
    def pageScanner(self, url: str, timeout: int = 8):
        """
        Fetch a single web page, strip non-visible / backend HTML elements
        using `get_page_content`, and return the filtered HTML as text.

        Args:
            url: URL of the page to fetch.
            timeout: network timeout in seconds (default 8).

        Returns:
            A dict:
              {
                "content": "<cleaned visible HTML>",
                "buttons": [ { "selector": "...", "text": "..." }, ... ]
              }
            If the request fails, returns an empty dict {}.
        """
        clean_url = self.normalize(url)
        if not clean_url:
            return {}

        headers = {"User-Agent": "WebTerm-PageScanner/1.0"}
        try:
            resp = requests.get(clean_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except Exception:
            return {}  # unreachable or error

        raw_html = resp.text
        try:
            content = self.get_page_content(raw_html)
            # `get_page_content` stores button metadata in self.latest_buttons
            buttons = getattr(self, "latest_buttons", [])
            return {
                "content": content,
                "buttons": buttons,
            }
        except Exception:
            return {}

    def get_page_content(self, html: str) -> str:
        """Filter HTML to show only frontend/visible elements."""
        if BeautifulSoup is None:
            raise RuntimeError(
                "The 'beautifulsoup4' package is required for --frontend-only. Install with: pip install beautifulsoup4"
            )
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove backend/non-visible elements
        backend_tags = [
            'script', 'style', 'meta', 'link', 'title', 'head',
            'noscript', 'template', 'svg', 'path', 'defs', 'clipPath',
            'linearGradient', 'radialGradient', 'pattern', 'mask'
        ]
        
        for tag_name in backend_tags:
            for tag in list(soup.find_all(tag_name)):
                if tag is not None:
                    tag.decompose()
        
        # Remove comments
        for comment in list(soup.find_all(string=lambda text: isinstance(text, Comment))):
            if comment is not None:
                comment.extract()
        
        # Remove elements with display:none or visibility:hidden
        for element in list(soup.find_all(True)):
            if not isinstance(element, Tag):
                continue
            # Be defensive: in rare cases element.attrs can be None; Tag.get() is safe.
            try:
                style = element.get('style')  # BeautifulSoup Tag.get returns attribute or None
            except Exception:
                style = None
            if style:
                style_str = str(style)
                compact = style_str.replace(' ', '')
                if 'display:none' in compact or 'visibility:hidden' in compact:
                    element.decompose()
        
        # Remove common hidden/utility classes
        hidden_classes = ['hidden', 'sr-only', 'visually-hidden', 'd-none', 'invisible']
        for class_name in hidden_classes:
            for element in list(soup.find_all(class_=class_name)):
                if isinstance(element, Tag):
                    element.decompose()
        
        html = str(soup)
        html = '\n'.join([line for line in html.splitlines() if line.strip()]) #remove all empty lines
        # -------- Button Extraction ---------------------------------
        buttons_info: List[Dict[str, str]] = []
        clickable_defs = [
            ("button", {}),
            ("a", {}),
            ("input", {"type": ["button", "submit"]}),
        ]
        for tag_name, attr_require in clickable_defs:
            for el in soup.find_all(tag_name):
                # Ensure we're working with a Tag element (not NavigableString, etc.)
                if not isinstance(el, Tag):
                    continue
                    
                # match required attributes (if any)
                ok = True
                for k, v in attr_require.items():
                    val = (el.get(k) or "")
                    # Handle different attribute value types
                    if isinstance(val, list):
                        val = " ".join(str(item) for item in val)
                    val = str(val).lower()
                    
                    if isinstance(v, list):
                        if val not in v:
                            ok = False
                            break
                    else:
                        if val != v:
                            ok = False
                            break
                if not ok:
                    continue
                # Skip hidden (extra guard)
                if el.get("hidden") is not None:
                    continue

                # Build best selector: id > classes > href for <a> > nth-of-type
                if el.get("id"):
                    el_id = el.get("id")
                    if isinstance(el_id, list):
                        selector = f"#{' '.join(str(x) for x in el_id)}"
                    else:
                        selector = f"#{el_id}"
                elif el.get("class"):
                    el_classes = el.get("class")
                    if isinstance(el_classes, list):
                        selector = "." + ".".join(str(cls) for cls in el_classes)
                    else:
                        selector = f".{el_classes}"
                elif tag_name == "a" and el.get("href"):
                    # Use href selector for anchor links that lack id/class
                    href_val = el.get("href")
                    selector = f'a[href="{href_val}"]'
                else:
                    nth = sum(1 for _ in el.find_previous_siblings(tag_name)) + 1
                    selector = f"{tag_name}:nth-of-type({nth})"

                # -------- Text fallback handling --------
                try:
                    text_content = el.get_text(strip=True) or ""
                except Exception:
                    text_content = ""
                
                text_content = text_content.strip()

                if not text_content:
                    value_attr = el.get("value")
                    if value_attr is not None:
                        if isinstance(value_attr, list):
                            text_content = " ".join(str(v) for v in value_attr)
                        else:
                            text_content = str(value_attr)
                    text_content = text_content.strip()

                if not text_content:
                    title_attr = el.get("title") or ""
                    aria_label = el.get("aria-label") or ""
                    text_content = str(title_attr or aria_label).strip()

                buttons_info.append({
                    "selector": selector,
                    "text": text_content
                })

        # expose for callers
        self.latest_buttons = buttons_info 
        return html

    def normalize(self, u: str) -> str:
            # Ensure scheme and strip URL fragments; keep queries (allowed)
            u = (u or "").strip()
            if not u:
                return u
            parsed = urlparse(u)
            if not parsed.scheme:
                # default to https
                u = "https://" + u
                parsed = urlparse(u)
            # remove fragment (#...)
            u = parsed._replace(fragment="").geturl()
            return u.rstrip("/") if u != parsed.scheme + "://" + parsed.netloc + "/" else u  # keep single trailing slash for root

    def sitePropagator(self, url: str, n: Optional[int] = 1, restrict_to_subpath: bool = True) -> "SiteTree":
        """
        Build a tree of subpages starting from `url`.
        - Considers only links that belong to the same site and are *subpages* of the original URL.
        - Uses `get_page_content` to filter out non-visible HTML before finding links.
        - Stops when encountering an already-seen URL or when the depth reaches `n` (if provided).
        
        Args:
            url: The starting page URL (root of the tree).
            n: Max branch length (depth, counting root as depth 0). If None, no explicit depth limit.
            restrict_to_subpath: If True (default), only scan links under the start URL's path (i.e., require base_prefix).
                                 If False, scan any same-site link regardless of path.

        Returns:
            SiteTree containing the discovered structure.
        """

        start = self.normalize(url)
        if not start:
            raise ValueError("sitePropogator requires a non-empty URL")

        base_parsed = urlparse(start)
        base_root = f"{base_parsed.scheme}://{base_parsed.netloc}"
        base_prefix = start.rstrip("/") + "/"

        # Initialize / reset tree
        self.tree = SiteTree(root_url=start)

        visited: Set[str] = set([start])
        stack = deque([(start, 0)])  # BFS queue: (url, depth)

        headers = {"User-Agent": "WebTerm-SiteScanner/1.0"}

        while stack:
            current, depth = stack.popleft()  # BFS
            if n is not None and depth >= n:
                # Depth limit reached for this branch
                continue

            # Fetch and filter current page
            try:
                resp = requests.get(current, headers=headers, timeout=8)
                resp.raise_for_status()
                html = resp.text
            except Exception:
                # Skip on fetch errors
                continue

            filtered = self.get_page_content(html)
            try:
                soup = BeautifulSoup(filtered, 'html.parser')
            except Exception:
                continue

            links = soup.find_all('a', href=True)
            for a in links:
                href = a.get('href', '').strip() # type: ignore
                if not href:
                    continue
                # Resolve relative URLs against the current page
                child = urljoin(current, href)
                child = self.normalize(child)
                if not child:
                    continue

                parsed = urlparse(child)
                # Only http/https
                if parsed.scheme not in ('http', 'https'):
                    continue

                # Same site constraint. Optionally restrict to subpath under the start URL.
                if restrict_to_subpath:
                    if not (child.startswith(base_root) and child.startswith(base_prefix)):
                        continue
                else:
                    if not child.startswith(base_root):
                        continue

                if child in visited:
                    continue

                # Add to tree and continue scan
                self.tree.add(current, child)
                visited.add(child)

                # Next depth (stop if would exceed n)
                next_depth = depth + 1
                if n is None or next_depth <= n:
                    stack.append((child, next_depth))
        return self.tree
    
class SetPageDescriptionTool:
    def __init__(self):
        self.desc = [{
            "type": "function",
            "name": "set_page_description",
            "description": "Set or update the description of a page node in the Site Tree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL of the page whose node description should be updated."},
                    "description": {"type": "string", "description": "New description text for the page."}
                },
                "required": ["url", "description"],
                "additionalProperties": False
            },
            "strict": True
        }]

    def set_page_description(self, url: str, description: str, tree: "SiteTree") -> "SiteTree":
        """
        Update the .desc field of the SiteNode that matches `url` in `tree`.
        Returns the modified tree (in-place update).

        Args:
            url: URL of the page whose description should be updated.
            description: New description text.
            tree: The SiteTree instance containing the node.

        Returns:
            The same SiteTree instance after modification.

        Raises:
            ValueError if the URL node is not present in the tree.
        """
        # Normalize URL similar to SiteScannerTool.normalize to avoid mismatches
        normalized_url = SiteScannerTool().normalize(url)

        node = tree.nodes.get(normalized_url)
        if not node:
            raise ValueError(f"URL '{url}' not found in provided SiteTree.")

        node.desc = description
        return tree

class SetPageButtonsTool:
    def __init__(self):
        """
        Tool to set or update the buttons of a page node in the SiteTree.
        """
        self.desc = [{
                "type": "function",
                "name": "set_page_buttons",
                "description": "Set or update the buttons of a page node in the Site Tree.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL of the page whose buttons should be updated."},
                        "buttons": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "selector": {"type": "string", "description": "CSS selector for the button."},
                                    "text": {"type": "string", "description": "Visible text of the button."}
                                },
                                "required": ["selector", "text"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["url", "buttons"],
                    "additionalProperties": False
                },
                "strict": True
            }]

    def set_page_buttons(self, url: str, buttons: list, tree: "SiteTree") -> "SiteTree":
        """
        Update the buttons of the SiteNode that matches `url` in `tree`.
        Returns the modified tree (in-place update).

        Args:
            url: URL of the page whose buttons should be updated.
            buttons: List of button definitions to set.
            tree: The SiteTree instance containing the node.

        Returns:
            The same SiteTree instance after modification.

        Raises:
            ValueError if the URL node is not present in the tree.
        """
        # Normalize URL similar to SiteScannerTool.normalize to avoid mismatches
        normalized_url = SiteScannerTool().normalize(url)

        node = tree.nodes.get(normalized_url)
        if not node:
            raise ValueError(f"URL '{url}' not found in provided SiteTree.")

        node.buttons = buttons
        return tree

class SiteTree:
    """Tree of SiteNode objects, addressed by URL strings for compatibility."""

    def __init__(self, root_url: Optional[str] = None):
        # Map URL -> SiteNode
        self.nodes: Dict[str, SiteNode] = {}
        # Children relationship by URL (kept as str for backward compatibility)
        self.children: Dict[str, Set[str]] = {}
        self.root_url: Optional[str] = None
        if root_url:
            self.set_root(root_url)

    # ---------- Node helpers ----------
    def _get_or_create_node(self, url: str) -> "SiteNode":
        if url not in self.nodes:
            self.nodes[url] = SiteNode(url=url)
        return self.nodes[url]

    # ---------- Public API ----------
    def set_root(self, root_url: str) -> None:
        self.root_url = root_url
        root_node = self._get_or_create_node(root_url)
        self.children.setdefault(root_node.url, set())

    def add(self, parent_url: str, child_url: str) -> None:
        """Add an edge parent -> child to the tree (URLs)."""
        parent_node = self._get_or_create_node(parent_url)
        child_node = self._get_or_create_node(child_url)
        # Maintain string‑based child mapping for compatibility
        self.children.setdefault(parent_node.url, set()).add(child_node.url)
        # Ensure child key exists
        self.children.setdefault(child_node.url, set())

    def exists(self, url: str) -> bool:
        return url in self.nodes

    def longest_branch_len(self) -> int:
        """Return maximum depth (edges) from root. Root only -> 0."""
        if not self.root_url:
            return 0

        def dfs(u: str) -> int:
            kids = self.children.get(u, set())
            if not kids:
                return 0
            return 1 + max(dfs(v) for v in kids)

        return dfs(self.root_url)

    # ---------- Persistence ----------
    def save(self, filename: str) -> None:
        """Save tree to JSON with basic node metadata."""
        data = {
            "root_url": self.root_url,
            "nodes": {url: {"desc": node.desc, "buttons": node.buttons} for url, node in self.nodes.items()},
            "children": {p: sorted(list(c)) for p, c in self.children.items()},
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filename: str) -> "SiteTree":
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        tree = cls(root_url=data.get("root_url"))
        # Restore nodes
        for url, meta in (data.get("nodes") or {}).items():
            node = SiteNode(url=url, desc=meta.get("desc", ""))
            node.buttons = meta.get("buttons", [])
            tree.nodes[url] = node
        # Restore children
        for parent, kids in (data.get("children") or {}).items():
            tree.children[parent] = set(kids)
        return tree

    # ---------- String representation ----------
    def __str__(self) -> str:
        if not self.root_url:
            return "<empty SiteTree>"

        lines: List[str] = [self.root_url]

        def build(u: str, prefix: str) -> None:
            kids = sorted(self.children.get(u, set()))
            for i, v in enumerate(kids):
                connector = "└─ " if i == len(kids) - 1 else "├─ "
                lines.append(f"{prefix}{connector}{v}")
                extension = "   " if i == len(kids) - 1 else "│  "
                build(v, prefix + extension)

        build(self.root_url, "")
        return "\n".join(lines)
    
    def get_json(self) -> str:
        """Return a JSON representation of the SiteTree."""
        return json.dumps({
            "root_url": self.root_url,
            "nodes": {url: {"desc": node.desc, "buttons": node.buttons} for url, node in self.nodes.items()},
            "children": {parent: list(children) for parent, children in self.children.items()}
        }, ensure_ascii=False, indent=2)
        
    def is_empty(self) -> bool:
        """Check if the tree is empty (no nodes)."""
        return not self.nodes

class SiteNode:
    """Represents a single page in the SiteTree."""

    __slots__ = ("url", "desc", "buttons")

    def __init__(self, url: str, desc: str = "") -> None:
        self.url: str = url
        self.desc: str = desc  # Node description
        self.buttons: List[Dict[str, str]] = []

    # Treat nodes with the same URL as identical for sets / dicts.
    def __hash__(self) -> int:
        return hash(self.url)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SiteNode) and self.url == other.url

    def __str__(self) -> str:
        return self.url

    def __repr__(self) -> str:
        return f"SiteNode(url={self.url!r}, desc={self.desc!r})"
    

if __name__ == "__main__":
    scanner = SiteScannerTool()
    #tree = scanner.sitePropagator("https://squidgo.com",n=1,restrict_to_subpath=True)
    # print(tree.longest_branch_len())
    # print(tree)
    output = scanner.pageScanner("https://oorischubert.com/contact.html")
    print(output)