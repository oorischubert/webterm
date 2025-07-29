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
            PageDescriptionTool()
        ]
    
class SiteScannerTool:
    def __init__(self):
        self.tree = SiteTree()
        self.desc = {
            "type": "function",
            "name": "pageScanner",
            "description": "Fetch ui content of a web page from a URL and return its plain text. Includes features such as links, buttons and descriptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the web page to fetch."}
                },
                "required": ["url"],
                "additionalProperties": False
            },
            "strict": True
        }
        
    def pageScanner(self, url: str, timeout: int = 8) -> str:
        """
        Fetch a single web page, strip non-visible / backend HTML elements
        using `get_page_content`, and return the filtered HTML as text.

        Args:
            url: URL of the page to fetch.
            timeout: network timeout in seconds (default 8).

        Returns:
            A string containing the cleaned, visible HTML of the page.
            If the request fails or content cannot be parsed, returns an
            empty string.
        """
        clean_url = self.normalize(url)
        if not clean_url:
            return ""

        headers = {"User-Agent": "WebTerm-PageScanner/1.0"}
        try:
            resp = requests.get(clean_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except Exception:
            return ""  # unreachable or error

        raw_html = resp.text
        try:
            return self.get_page_content(raw_html)
        except Exception:
            return ""

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

    def sitePropagator(self, url: str, n: Optional[int] = None, restrict_to_subpath: bool = True) -> "SiteTree":
        """
        Build a tree of subpages starting from `url`.
        - Considers only links that belong to the same site and are *subpages* of the original URL.
        - Uses `get_page_content` to filter out non-visible HTML before finding links.
        - Stops when encountering an already-seen URL or when the depth reaches `n` (if provided).
        
        Args:
            url: The starting page URL (root of the tree).
            n: Max branch length (depth, counting root as depth 0). If None, no explicit depth limit.
            restrict_to_subpath: If True (default), only crawl links under the start URL's path (i.e., require base_prefix).
                                 If False, crawl any same-site link regardless of path.
        
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

                # Add to tree and continue crawl
                self.tree.add(current, child)
                visited.add(child)

                # Next depth (stop if would exceed n)
                next_depth = depth + 1
                if n is None or next_depth <= n:
                    stack.append((child, next_depth))

        return self.tree
    
class PageDescriptionTool:
    def __init__(self):
        self.desc = {
            "type": "function",
            "name": "set_page_description",
            "description": "Used to set the description of a web page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "definition": {"type": "string", "description": "The definition of the web page to set."}
                },
                "required": ["definition"],
                "additionalProperties": False
            },
            "strict": True
        }
        def set_page_description(self, html: str) -> str:
            #lets agent set page description, work in progress...
            return ""


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
            "nodes": {url: {"desc": node.desc} for url, node in self.nodes.items()},
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
            tree.nodes[url] = SiteNode(url=url, desc=meta.get("desc", ""))
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

class SiteNode:
    """Represents a single page in the SiteTree."""

    __slots__ = ("url", "desc")

    def __init__(self, url: str, desc: str = "") -> None:
        self.url: str = url
        self.desc: str = desc  # Node description

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
    tree = scanner.sitePropagator("https://squidgo.com",n=1,restrict_to_subpath=True)
    print(tree.longest_branch_len())
    print(tree)