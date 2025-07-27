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
            PageDescriptionTool
        ]
    
class SiteScannerTool:
    def __init__(self):
        self.tree = SiteTree()
        self.desc = {
            "type": "function",
            "name": "get_page_content",
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

    def sitePropogator(self, url: str, n: Optional[int] = None, restrict_to_subpath: bool = True) -> "SiteTree":
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
        def normalize(u: str) -> str:
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

        start = normalize(url)
        if not start:
            raise ValueError("sitePropogator requires a non-empty URL")

        base_parsed = urlparse(start)
        base_root = f"{base_parsed.scheme}://{base_parsed.netloc}"
        base_prefix = start.rstrip("/") + "/"

        # Initialize / reset tree
        self.tree = SiteTree(root_url=start)

        visited: Set[str] = set([start])
        stack = deque([(start, 0)])  # BFS queue: (url, depth)

        headers = {"User-Agent": "WebText-SiteScanner/1.0"}

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
                child = normalize(child)
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
    def __init__(self, root_url: Optional[str] = None):
        self.root: Optional[str] = root_url
        self.children: Dict[str, Set[str]] = {}
        self.nodes: Set[str] = set()
        if root_url:
            self.nodes.add(root_url)
            self.children.setdefault(root_url, set())

    def set_root(self, root_url: str) -> None:
        self.root = root_url
        self.nodes.add(root_url)
        self.children.setdefault(root_url, set())

    def add(self, parent: str, child: str) -> None:
        """Add an edge parent -> child to the tree."""
        self.nodes.update([parent, child])
        if parent not in self.children:
            self.children[parent] = set()
        self.children[parent].add(child)
        # Ensure the child exists in mapping even if it currently has no children
        self.children.setdefault(child, set())

    def exists(self, url: str) -> bool:
        return url in self.nodes

    def longest_branch_len(self) -> int:
        """Return the maximum depth (in edges) from root. Root only -> 0."""
        if not self.root:
            return 0

        def dfs(u: str) -> int:
            kids = self.children.get(u, set())
            if not kids:
                return 0
            return 1 + max(dfs(v) for v in kids)

        return dfs(self.root)

    def save(self, filename: str) -> None:
        """Save the tree to a local JSON file."""
        data = {
            "root": self.root,
            "children": {parent: sorted(list(children)) for parent, children in self.children.items()},
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filename: str) -> "SiteTree":
        """Load a tree from a local JSON file and return a new SiteTree instance."""
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        root = data.get("root")
        tree = cls(root_url=root)
        for parent, kids in (data.get("children") or {}).items():
            for child in kids:
                tree.add(parent, child)
        return tree

    def __str__(self) -> str:
        if not self.root:
            return "<empty SiteTree>"

        lines: List[str] = []

        def walk(u: str, prefix: str = "") -> None:
            lines.append(prefix + u)
            kids = sorted(self.children.get(u, set()))
            for i, v in enumerate(kids):
                connector = "└─ " if i == len(kids) - 1 else "├─ "
                next_prefix = prefix + ("   " if i == len(kids) - 1 else "│  ")
                lines.append(prefix + connector + v)
                walk(v, next_prefix)

        walk(self.root)
        return "\n".join(lines)
    

if __name__ == "__main__":
    scanner = SiteScannerTool()
    tree = scanner.sitePropogator("https://squidgo.com", n=1)
    print(tree.longest_branch_len())
    print(tree)
 