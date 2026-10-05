#!/usr/bin/env python3
"""A dependency-free RSS/Atom terminal reader."""
import argparse
import base64
import concurrent.futures
import curses
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap
import time
from email.utils import parsedate_to_datetime
from datetime import datetime
import urllib.request
import urllib.error
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value or ""))).strip()


def parse_feed(data, source):
    root = ET.fromstring(data)
    articles = []
    for item in root.iter():
        if item.tag.split("}")[-1] not in ("item", "entry"):
            continue
        fields = {}
        url = ""
        for child in item:
            tag = child.tag.split("}")[-1]
            fields[tag] = "".join(child.itertext())
            if tag == "link" and child.get("rel", "alternate") == "alternate":
                url = child.get("href") or child.text or url
        url = url.strip()
        if not url.startswith(("https://", "http://")):
            continue
        articles.append({
            "id": hashlib.sha256(url.encode()).hexdigest(),
            "source": source, "title": clean(fields.get("title")) or "Untitled",
            "url": url, "date": clean(fields.get("pubDate") or fields.get("published") or fields.get("updated")),
            "summary": clean(fields.get("encoded") or fields.get("content") or fields.get("description") or fields.get("summary")),
        })
    return articles


def download(url, article=False):
    headers = {"User-Agent": "BNews/0.1 news reader"}
    if article:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.7",
        }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=12) as response:
        data = response.read(5_000_001)
    if len(data) > 5_000_000:
        raise ValueError("Feed exceeds 5 MB")
    return data


class HeadlineParser(HTMLParser):
    """Collect article links when a publisher no longer exposes a working feed."""
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.link = None
        self.parts = []
        self.articles = {}

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.link = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data):
        if self.link:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self.link:
            return
        url = urljoin(self.source["website"], self.link)
        path = urlparse(url).path
        title = clean(" ".join(self.parts))
        host = urlparse(url).hostname
        same_host = host == urlparse(self.source["website"]).hostname
        article_path = re.search(r"/a/\d+|/\d{4}/\d{2}/\d{2}/|/[^/]+/[^/]+\.html$", path)
        if same_host and article_path and len(title) >= 20 and url not in self.articles:
            self.articles[url] = {"id": hashlib.sha256(url.encode()).hexdigest(), "source": self.source["name"], "title": title, "url": url, "date": "", "summary": "No abstract available. Press O to fetch the article here."}
        self.link = None


def fetch(source):
    try:
        articles = parse_feed(download(source["url"]), source["name"])
        if articles:
            return articles
        raise ValueError("Feed contains no articles")
    except Exception:
        if not source.get("website"):
            raise
        parser = HeadlineParser(source)
        parser.feed(download(source["website"]).decode("utf-8", errors="replace"))
        if not parser.articles:
            raise ValueError("Publisher returned no accessible headlines")
        return list(parser.articles.values())[:100]


class ArticleParser(HTMLParser):
    """Find publisher article bodies while excluding navigation and related stories."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "root", "attrs": {}, "children": []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1]["children"].append(data)

    @staticmethod
    def excluded(node):
        attrs = node["attrs"]
        labels = attrs.get("class", "") + " " + attrs.get("id", "")
        return node["tag"] in {"script", "style", "nav", "footer", "aside", "form", "button"} or "hidden" in attrs or re.search(r"(?:^|[\s_-])(comments?|related|recommend\w*|advert\w*|social|share|newsletter)(?:$|[\s_-])", labels, re.I)

    def text(self, node):
        if isinstance(node, str):
            return node
        if self.excluded(node):
            return ""
        return " ".join(self.text(child) for child in node["children"])

    def paragraphs(self, node):
        if isinstance(node, str) or self.excluded(node):
            return []
        if node["tag"] in {"p", "h2", "h3", "li", "blockquote"}:
            value = clean(self.text(node))
            return [value] if value else []
        return [p for child in node["children"] for p in self.paragraphs(child)]

    def extract(self):
        candidates = []
        structured = []

        def json_bodies(value):
            if isinstance(value, dict):
                if isinstance(value.get("articleBody"), str):
                    body = value["articleBody"]
                    paragraphs = [clean(p) for p in re.split(r"\n+|<br\s*/?>|</p>", body) if clean(p)]
                    structured.append("\n\n".join(paragraphs))
                for child in value.values():
                    json_bodies(child)
            elif isinstance(value, list):
                for child in value:
                    json_bodies(child)

        def visit(node):
            if isinstance(node, str):
                return
            attrs = node["attrs"]
            if node["tag"] == "script" and attrs.get("type", "").lower() == "application/ld+json":
                try:
                    json_bodies(json.loads("".join(c for c in node["children"] if isinstance(c, str))))
                except ValueError:
                    pass
            if self.excluded(node):
                return
            labels = (attrs.get("class", "") + " " + attrs.get("id", "")).lower()
            strength = 3 if attrs.get("itemprop") == "articleBody" else 2 if re.search(r"article[-_ ]?(body|text|content)|story[-_ ]?(body|text|content)|entry[-_ ]?content|news[-_ ]?(body|text|content)|post[-_ ]?content|text[-_ ]?content", labels) else 1 if node["tag"] == "article" else 0
            if strength:
                paragraphs = self.paragraphs(node)
                body = "\n\n".join(paragraphs) or clean(self.text(node))
                if len(body) >= 100:
                    candidates.append((strength, len(body), body))
            for child in node["children"]:
                visit(child)

        visit(self.root)
        # Explicit HTML body containers usually retain better paragraph formatting.
        explicit = [candidate for candidate in candidates if candidate[0] >= 2]
        if explicit:
            return max(explicit)[2]
        if structured and len(max(structured, key=len)) >= 100:
            return max(structured, key=len)
        if candidates:
            return max(candidates)[2]
        raise ValueError("Could not locate accessible article text; the publisher may restrict access")


def fetch_article(url):
    parser = ArticleParser()
    try:
        data = download(url, article=True)
    except urllib.error.HTTPError as error:
        if error.code in (401, 402, 403):
            raise ValueError(f"HTTP {error.code}: publisher blocked article access") from error
        raise
    parser.feed(data.decode("utf-8", errors="replace"))
    return parser.extract()


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def display_time(value):
    if not value:
        return "Time unavailable"
    try:
        try:
            date = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.astimezone().strftime("%d %b %Y · %H:%M")
    except (TypeError, ValueError, OverflowError):
        return value


def copy_link(url):
    for executable, arguments in [("pbcopy", []), ("wl-copy", []), ("xclip", ["-selection", "clipboard"]), ("xsel", ["--clipboard", "--input"])]:
        if shutil.which(executable):
            try:
                subprocess.run([executable, *arguments], input=url.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=True)
                return "Article link copied"
            except (OSError, subprocess.SubprocessError):
                continue
    # OSC 52 lets compatible terminals copy text even over SSH.
    sys.stdout.write("\x1b]52;c;" + base64.b64encode(url.encode()).decode() + "\x07")
    sys.stdout.flush()
    return "Copy requested from terminal (OSC 52); clipboard support required"


class Reader:
    def __init__(self, sources, data_dir, offline=False):
        self.sources, self.data_dir = sources, data_dir
        self.articles = read_json(data_dir / "cache.json", [])
        self.saved = read_json(data_dir / "saved.json", {})
        self.bodies = read_json(data_dir / "articles.json", {})
        self.offline = offline
        self.article_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.article_pending = {}
        self.article_errors = {}
        self.focus = "left"
        self.full_requested = set()
        self.source = 0
        self.selected = 0
        self.query = ""
        self.saved_only = False
        self.scroll = 0
        self.menu = True
        self.menu_selected = 0
        self.status = "Offline: cached articles" if offline else "Fetching feeds…"
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.pending = {}
        self.errors = []
        if not offline:
            self.refresh()

    def refresh(self):
        if self.pending:
            return
        self.errors = []
        self.status = "Fetching feeds…"
        self.pending = {self.pool.submit(fetch, source): source for source in self.sources}

    def poll(self):
        body_changed = False
        for article_id, future in list(self.article_pending.items()):
            if future.done():
                del self.article_pending[article_id]
                try:
                    self.bodies[article_id] = future.result()
                    body_changed = True
                except Exception as error:
                    self.article_errors[article_id] = str(error)
        if body_changed:
            write_json(self.data_dir / "articles.json", self.bodies)
        changed = False
        for future in list(self.pending):
            if not future.done():
                continue
            source = self.pending.pop(future)
            try:
                articles = future.result()
                self.articles = [a for a in self.articles if a["source"] != source["name"]] + articles
                changed = True
            except Exception as error:
                self.errors.append(f'{source["name"]}: {error}')
        if changed:
            write_json(self.data_dir / "cache.json", self.articles)
        if not self.pending and self.status == "Fetching feeds…":
            self.status = " | ".join(self.errors) if self.errors else f"Updated {time.strftime('%H:%M')} · {len(self.articles)} articles"

    def visible(self):
        articles = list(self.saved.values()) if self.saved_only else self.articles
        name = self.sources[self.source - 1]["name"] if self.source else None
        return [a for a in articles if (not name or a["source"] == name) and self.query.casefold() in (a["title"] + " " + a["summary"]).casefold()]

    def load_selected(self, article):
        article_id = article["id"]
        self.full_requested.add(article_id)
        self.article_errors.pop(article_id, None)
        if not self.offline and article_id not in self.bodies and article_id not in self.article_pending:
            self.article_pending[article_id] = self.article_pool.submit(fetch_article, article["url"])

    def article_text(self, article):
        article_id = article["id"]
        if article_id not in self.full_requested:
            summary = article["summary"]
            if summary == "Press o to read the full article in your browser.":
                summary = ""
            return "Abstract · O fetch full text", summary or "No abstract available. Press O to fetch the article."
        if article_id in self.bodies:
            return "Full article", self.bodies[article_id]
        if article_id in self.article_errors:
            return "Full article unavailable: " + self.article_errors[article_id], article["summary"]
        if self.offline:
            return "Offline · full article has not been cached", article["summary"]
        return "Loading full article…", article["summary"]

    def navigate(self, key):
        if key in (ord("j"), curses.KEY_DOWN, ord("k"), curses.KEY_UP):
            direction = 1 if key in (ord("j"), curses.KEY_DOWN) else -1
            if self.focus == "right":
                self.scroll = max(0, self.scroll + direction)
            elif self.focus == "sources":
                if direction > 0:
                    self.focus = "left"
            elif direction < 0 and self.selected == 0:
                self.focus = "sources"
            else:
                self.selected = max(0, self.selected + direction)
                self.scroll = 0
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT):
            if self.focus == "sources":
                self.switch_source(1 if key == curses.KEY_RIGHT else -1)
            else:
                self.focus = "left" if key == curses.KEY_LEFT else "right"
        elif key == 9:
            self.focus = {"sources": "left", "left": "right", "right": "sources"}[self.focus]
        elif key in (ord("["), ord("]")):
            self.switch_source(1 if key == ord("]") else -1)
        elif key in (10, 13, curses.KEY_ENTER) and self.focus == "sources":
            self.focus = "left"
        else:
            return False
        return True

    def switch_source(self, direction):
        self.source = (self.source + direction) % (len(self.sources) + 1)
        self.selected = self.scroll = 0
        self.query = ""
        self.saved_only = False

    def run(self, screen):
        curses.curs_set(0)
        accent = curses.A_BOLD
        selected_style = curses.A_REVERSE
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
            accent = curses.color_pair(1) | curses.A_BOLD
            selected_style = curses.color_pair(2) | curses.A_BOLD
        screen.timeout(100)
        def put(y, x, value, attr=0):
            height, width = screen.getmaxyx()
            if 0 <= y < height and 0 <= x < width - 1:
                try:
                    screen.addnstr(y, x, value, width - x - 1, attr)
                except curses.error:
                    pass
        while True:
            self.poll()
            screen.erase()
            h, w = screen.getmaxyx()
            if self.menu:
                options = [s["name"] for s in self.sources] + ["All sources", "Saved articles"]
                x = max(2, (w - 48) // 2)
                top = max(1, (h - 16) // 2)
                put(top, x, "▰  B N E W S", accent)
                put(top + 2, x, "Bulgarian news. Your choice of perspective.", curses.A_DIM)
                put(top + 4, x, "CHOOSE A SOURCE", accent)
                for i, name in enumerate(options):
                    count = len(self.saved) if i == len(self.sources) + 1 else len(self.articles) if i == len(self.sources) else sum(a["source"] == name for a in self.articles)
                    line = f" {'›' if i == self.menu_selected else ' '}  {name:<24} {count:>3} articles "
                    put(top + 6 + i, x, line, selected_style if i == self.menu_selected else 0)
                put(h - 3, 2, self.status, curses.A_DIM)
                put(h - 2, 2, "↑/↓ or j/k  navigate    Enter  select    r  refresh    q  quit", accent)
                screen.refresh()
                key = screen.getch()
                if key in (ord("q"), 3):
                    break
                if key in (ord("j"), curses.KEY_DOWN, ord("k"), curses.KEY_UP):
                    self.menu_selected = (self.menu_selected + (1 if key in (ord("j"), curses.KEY_DOWN) else -1)) % len(options)
                elif key in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT):
                    self.source = self.menu_selected + 1 if self.menu_selected < len(self.sources) else 0
                    self.saved_only = self.menu_selected == len(self.sources) + 1
                    self.query = ""
                    self.selected = self.scroll = 0
                    self.menu = False
                    self.focus = "left"
                elif key == ord("r"):
                    self.refresh()
                continue
            articles = self.visible()
            self.selected = max(0, min(self.selected, len(articles) - 1))
            put(0, 1, "▰  BNEWS  /  Bulgarian news", accent)
            names = ["All sources"] + [s["name"] for s in self.sources]
            chips = [f" {name} " for name in names]
            chip_start = 0
            while sum(len(c) + 2 for c in chips[chip_start:self.source + 1]) > w - 6 and chip_start < self.source:
                chip_start += 1
            chip_x = 1
            for i in range(chip_start, len(names)):
                if chip_x + len(chips[i]) >= w:
                    break
                style = selected_style if i == self.source and self.focus == "sources" else accent if i == self.source else curses.A_DIM
                put(2, chip_x, chips[i], style)
                chip_x += len(chips[i]) + 2
            put(3, 1, f"{'Saved' if self.saved_only else 'Headlines'} · {len(articles)} articles" + (f" · Search: {self.query}" if self.query else ""))
            split = max(25, w * 45 // 100)
            rows = max(1, h - 8)
            start = max(0, self.selected - rows + 1)
            put(4, 1, "› HEADLINES" if self.focus == "left" else "  HEADLINES", accent if self.focus == "left" else curses.A_DIM)
            for row, article in enumerate([] if w < 65 and self.focus == "right" else articles[start:start + rows]):
                marker = "★" if article["id"] in self.saved else " "
                label = f'{marker} {article["source"]} · {article["title"]}'
                put(5 + row, 1, label[:split - 3].ljust(split - 3), (selected_style if self.focus == "left" else curses.A_REVERSE) if start + row == self.selected else 0)
            if articles and (w >= 65 or self.focus == "right"):
                article = articles[self.selected]
                pane_x = 1 if w < 65 else split + 2
                if w >= 65:
                    for y in range(4, h - 3):
                        put(y, split, "│")
                pane_width = max(10, w - pane_x - 2)
                put(4, pane_x, "› ARTICLE" if self.focus == "right" else "  ARTICLE", accent if self.focus == "right" else curses.A_DIM)
                title_lines = textwrap.wrap(article["title"], pane_width)[:3]
                header = [(line, curses.A_BOLD) for line in title_lines]
                header.append((article["source"] + " · " + display_time(article["date"]), curses.A_DIM))
                header.extend((line, accent) for line in textwrap.wrap(article["url"], pane_width)[:3])
                header.append(("c copy link · O full text · a abstract", curses.A_DIM))
                # Keep title, timestamp and link pinned while only the body scrolls.
                header = header[:max(0, rows - 2)]
                for row, (line, style) in enumerate(header):
                    put(5 + row, pane_x, line, style)
                body_y = 5 + len(header) + 1
                body_rows = max(1, h - 3 - body_y)
                lines = []
                body_status, body = self.article_text(article)
                for paragraph in [body_status, "", *body.split("\n")]:
                    lines.extend(textwrap.wrap(paragraph, pane_width) or [""])
                self.scroll = min(self.scroll, max(0, len(lines) - body_rows))
                for row, line in enumerate(lines[self.scroll:self.scroll + body_rows]):
                    put(body_y + row, pane_x, line)
            elif not articles:
                put(6, 1, "No articles. Press r to refresh, / to search, or Esc to clear filters.")
            put(h - 3, 1, self.status)
            put(h - 2, 1, "Tab / ←→ focus · ↑↓ navigate/scroll · o/O full text · a abstract · c copy · q quit")
            put(h - 1, 1, "←→ switch sources · ↓ or Enter headlines" if self.focus == "sources" else "↑ first headline: sources · [/] source · / search · s save · b saved · r refresh · Esc menu", accent)
            screen.refresh()
            key = screen.getch()
            if key in (ord("q"), 3):
                break
            if self.navigate(key):
                continue
            if key == ord("r"):
                if articles:
                    self.article_errors.pop(articles[self.selected]["id"], None)
                self.refresh()
            elif key == ord("b"):
                self.saved_only = not self.saved_only
                self.selected = self.scroll = 0
            elif key == 27:
                self.menu = True
            elif key in (curses.KEY_NPAGE, curses.KEY_PPAGE):
                direction = 1 if key == curses.KEY_NPAGE else -1
                if self.focus == "right":
                    self.scroll = max(0, self.scroll + direction * body_rows) if articles and (w >= 65 or self.focus == "right") else 0
                else:
                    self.selected += direction * rows
                    self.scroll = 0
            elif key == ord("s") and articles:
                article = articles[self.selected]
                if article["id"] in self.saved:
                    del self.saved[article["id"]]
                else:
                    self.saved[article["id"]] = article
                write_json(self.data_dir / "saved.json", self.saved)
            elif key in (10, 13, curses.KEY_ENTER) and articles:
                self.focus = "right"
                self.scroll = 0
            elif key in (ord("o"), ord("O")) and articles:
                self.load_selected(articles[self.selected])
                self.focus = "right"
                self.scroll = 0
            elif key == ord("a") and articles:
                self.full_requested.discard(articles[self.selected]["id"])
                self.scroll = 0
            elif key == ord("c") and articles:
                self.status = copy_link(articles[self.selected]["url"])
            elif key == ord("/"):
                screen.timeout(-1)
                curses.echo()
                curses.curs_set(1)
                try:
                    screen.move(h - 3, 0)
                    screen.clrtoeol()
                    put(h - 3, 1, "Search: ")
                    self.query = screen.getstr(h - 3, 9, max(1, w - 11)).decode("utf-8", errors="replace")
                    self.selected = self.scroll = 0
                finally:
                    curses.noecho()
                    curses.curs_set(0)
                    screen.timeout(100)
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.article_pool.shutdown(wait=False, cancel_futures=True)


def main():
    parser = argparse.ArgumentParser(prog="bnews", description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path(__file__).with_name("sources.json"))
    parser.add_argument("--offline", action="store_true", help="Read cached news without fetching feeds")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "lynx-news")
    args = parser.parse_args()
    try:
        sources = json.loads(args.sources.read_text())
        if not isinstance(sources, list) or not sources or any(not isinstance(s, dict) or not isinstance(s.get("name"), str) or not isinstance(s.get("url"), str) or not s["url"].startswith(("http://", "https://")) for s in sources):
            raise ValueError("Expected a nonempty list of sources with name and HTTP(S) url")
        if len({s["name"] for s in sources}) != len(sources):
            raise ValueError("Source names must be unique")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    reader = Reader(sources, args.data_dir, args.offline)
    try:
        curses.wrapper(reader.run)
    except KeyboardInterrupt:
        pass
    finally:
        reader.pool.shutdown(wait=False, cancel_futures=True)
        reader.article_pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
