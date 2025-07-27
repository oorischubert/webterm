#!/usr/bin/env python3
"""
webParser.py — Print the raw HTML of a web page.

Usage examples:
  # From a local file
  python webParser.py --file page.html

  # From a URL
  python webParser.py --url https://example.com

  # Save to file
  python webParser.py --url https://example.com --out page.html
  
  # Show only frontend content (removes scripts, styles, meta tags, etc.)
  python webParser.py --url https://example.com --frontend-only

  # Disable compression (keep empty lines)
  python webParser.py --url https://example.com --no-compress
"""
import argparse
import sys
import traceback
from typing import Optional
from bs4 import BeautifulSoup, Comment, Tag
import requests


def load_html_from_file(path: str) -> str:
    """Load HTML content from a local file."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def load_html_from_url(url: str, timeout: float = 20.0) -> str:
    """Load HTML content from a URL."""
    if requests is None:
        raise RuntimeError(
            "The 'requests' package is required for --url. Install with: pip install requests"
        )
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "html-fetcher/1.0"})
    resp.raise_for_status()
    return resp.text


def filter_frontend_content(html: str) -> str:
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
    
    return str(soup)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print raw HTML from file or URL")
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--file", "-f", help="Path to a local HTML file")
    source.add_argument("--url", "-u", help="URL to fetch HTML from", default="https://squidgo.com/shop/")
    parser.add_argument("--out", "-o", help="Output file path (defaults to stdout)")
    parser.add_argument("--frontend-only", action="store_true", default=True,
                       help="Filter out backend elements (scripts, styles, meta tags, etc.) and show only visible frontend content")
    parser.add_argument("--debug", action="store_true", help="Print a full traceback on errors")
    parser.add_argument("--compress", action="store_true", default=True,
                       help="Remove all empty lines from the output HTML (default: True)")
    parser.add_argument("--no-compress", dest="compress", action="store_false",
                       help="Disable compression (do not remove empty lines)")
    
    args = parser.parse_args()
    
    try:
        if args.file:
            html = load_html_from_file(args.file)
        else:
            html = load_html_from_url(args.url)
        
        # Apply frontend filter if requested
        if args.frontend_only:
            html = filter_frontend_content(html)
        
        if args.compress:
            html = '\n'.join([line for line in html.splitlines() if line.strip()])
        
        # Output the HTML
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"HTML saved to {args.out}")
        else:
            print(html)
            
    except Exception as e:
        if getattr(args, 'debug', False):
            traceback.print_exc()
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
