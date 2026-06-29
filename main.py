#!/usr/bin/env python3
"""
Create an EPUB from a list of web links using Pandoc or Calibre.

Features:
- Accepts links from a text file or command-line arguments
- Downloads each page
- Extracts the main readable content when possible
- Bundles pages into a single EPUB with a table of contents
- Can use Pandoc (default) or Calibre's ebook-convert

Examples:
  python3 create_epub_from_links.py \
      --input links.txt \
      --output mybook.epub \
      --title "My Book"

  python3 create_epub_from_links.py \
      --output mybook.epub \
      --title "Collected Articles" \
      https://example.com/page1 https://example.com/page2

Requirements:
- Python packages: requests, beautifulsoup4
- External tools: pandoc and/or ebook-convert
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


def slugify(value: str, fallback: str = "chapter") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or fallback


def read_links(args_links: List[str], input_file: str | None) -> List[str]:
    links = []

    if input_file:
        with open(input_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                links.append(line)

    links.extend(args_links)

    seen = set()
    deduped = []
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)

    if not deduped:
        raise ValueError("No links provided. Use --input or pass URLs as arguments.")

    return deduped


def fetch_html(url: str, timeout: int = 30) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def extract_title(soup: BeautifulSoup, url: str) -> str:
    for selector in [
        "meta[property='og:title']",
        "meta[name='twitter:title']",
        "title",
        "h1",
    ]:
        tag = soup.select_one(selector)
        if not tag:
            continue
        if tag.name == "meta":
            content = tag.get("content", "").strip()
            if content:
                return content
        else:
            text = tag.get_text(" ", strip=True)
            if text:
                return text

    parsed = urlparse(url)
    return parsed.path.strip("/") or parsed.netloc or url


def score_candidate(tag) -> int:
    score = 0
    text = tag.get_text(" ", strip=True)
    score += min(len(text) // 50, 200)
    score += len(tag.find_all(["p", "li"])) * 8
    score += len(tag.find_all("img")) * 2

    classes = " ".join(tag.get("class", [])) + " " + (tag.get("id") or "")
    classes = classes.lower()
    positive = ["content", "article", "post", "main", "entry", "body", "markdown"]
    negative = ["nav", "menu", "footer", "header", "sidebar", "comment", "share", "ads"]
    for p in positive:
        if p in classes:
            score += 20
    for n in negative:
        if n in classes:
            score -= 25
    return score


def extract_main_content(html_text: str, url: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    title = extract_title(soup, url)

    for bad in soup(["script", "style", "noscript", "iframe", "svg", "form"]):
        bad.decompose()

    candidates = []
    selectors = ["article", "main", "[role='main']", ".content", ".post", ".entry-content"]
    for selector in selectors:
        candidates.extend(soup.select(selector))

    if not candidates:
        candidates = soup.find_all(["div", "section", "article", "main"], limit=200)

    if candidates:
        best = max(candidates, key=score_candidate)
    else:
        best = soup.body or soup

    for bad in best.select("nav, footer, header, aside, .sidebar, .comments, .comment, .share, .social"):
        bad.decompose()

    body_html = str(best)
    return title, body_html


def make_xhtml(title: str, body_html: str, source_url: str) -> str:
    safe_title = html.escape(title)
    safe_url = html.escape(source_url)
    return f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
<!DOCTYPE html>
<html xmlns=\"http://www.w3.org/1999/xhtml\">
<head>
  <meta charset=\"utf-8\" />
  <title>{safe_title}</title>
  <style>
    body {{ font-family: serif; line-height: 1.5; margin: 5%; }}
    h1, h2, h3 {{ line-height: 1.2; }}
    img {{ max-width: 100%; height: auto; }}
    pre, code {{ white-space: pre-wrap; }}
    blockquote {{ margin-left: 1em; padding-left: 1em; border-left: 3px solid #ccc; }}
    .source {{ margin-top: 2em; font-size: 0.9em; color: #666; }}
  </style>
</head>
<body>
  <h1>{safe_title}</h1>
  {body_html}
  <p class=\"source\">Source: <a href=\"{safe_url}\">{safe_url}</a></p>
</body>
</html>
"""


def build_pandoc_epub(chapter_files: List[Path], output_epub: Path, title: str, author: str | None, language: str) -> None:
    if not shutil.which("pandoc"):
        raise RuntimeError("pandoc not found in PATH")

    cmd = [
        "pandoc",
        "--toc",
        "--standalone",
        "--metadata", f"title={title}",
        "--metadata", f"lang={language}",
        "-o", str(output_epub),
    ]
    if author:
        cmd.extend(["--metadata", f"author={author}"])

    cmd.extend(str(p) for p in chapter_files)
    subprocess.run(cmd, check=True)


def build_calibre_epub(chapter_files: List[Path], output_epub: Path, title: str, author: str | None, language: str, workdir: Path) -> None:
    if not shutil.which("ebook-convert"):
        raise RuntimeError("ebook-convert not found in PATH")

    combined_html = workdir / "combined.html"
    parts = [
        "<html><head><meta charset='utf-8'><title>{}</title></head><body>".format(html.escape(title))
    ]
    for chapter in chapter_files:
        parts.append(chapter.read_text(encoding="utf-8"))
    parts.append("</body></html>")
    combined_html.write_text("\n".join(parts), encoding="utf-8")

    cmd = [
        "ebook-convert",
        str(combined_html),
        str(output_epub),
        "--title", title,
        "--language", language,
        "--level1-toc", "//h:h1",
        "--max-toc-links", "1000",
    ]
    if author:
        cmd.extend(["--authors", author])

    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an EPUB from a list of links.")
    parser.add_argument("links", nargs="*", help="URLs to include in the EPUB")
    parser.add_argument("--input", "-i", help="Text file containing one URL per line")
    parser.add_argument("--output", "-o", required=True, help="Output EPUB path")
    parser.add_argument("--title", "-t", required=True, help="Book title")
    parser.add_argument("--author", "-a", default=None, help="Book author")
    parser.add_argument("--language", "-l", default="en", help="Language code, e.g. en, de")
    parser.add_argument("--engine", choices=["pandoc", "calibre"], default="pandoc", help="Conversion backend")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files for debugging")
    args = parser.parse_args()

    try:
        links = read_links(args.links, args.input)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    output_epub = Path(args.output).resolve()

    tmp_ctx = tempfile.TemporaryDirectory(prefix="epub_links_")
    workdir = Path(tmp_ctx.name)

    try:
        chapter_files = []
        for idx, url in enumerate(links, start=1):
            print(f"Fetching {idx}/{len(links)}: {url}", file=sys.stderr)
            try:
                raw_html = fetch_html(url)
                chapter_title, body_html = extract_main_content(raw_html, url)
                chapter_name = f"{idx:03d}-{slugify(chapter_title)}.xhtml"
                chapter_path = workdir / chapter_name
                chapter_path.write_text(
                    make_xhtml(chapter_title, body_html, url),
                    encoding="utf-8",
                )
                chapter_files.append(chapter_path)
            except Exception as e:
                print(f"Warning: failed to process {url}: {e}", file=sys.stderr)

        if not chapter_files:
            raise RuntimeError("No chapters were successfully created.")

        output_epub.parent.mkdir(parents=True, exist_ok=True)

        if args.engine == "pandoc":
            build_pandoc_epub(chapter_files, output_epub, args.title, args.author, args.language)
        else:
            build_calibre_epub(chapter_files, output_epub, args.title, args.author, args.language, workdir)

        print(f"EPUB created: {output_epub}")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    finally:
        if args.keep_temp:
            print(f"Temporary files kept at: {workdir}", file=sys.stderr)
            tmp_ctx.cleanup = lambda: None
        else:
            tmp_ctx.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
