import unittest
from lynx_news.reader import ArticleParser, HeadlineParser, Reader, display_time, download, fetch_article, parse_feed
from pathlib import Path
from tempfile import TemporaryDirectory


class FeedTests(unittest.TestCase):
    def test_browser_check_bypasses_http_fetch_and_article_extraction(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from lynx_news.reader import main
        output = io.StringIO()
        with patch("sys.argv", ["bnews", "--check-browser", "https://example.com"]), patch("lynx_news.reader.render_page", return_value='<html><title>Example Domain</title><body>Example</body></html>') as render, patch("lynx_news.reader.fetch_article") as fetch, redirect_stdout(output):
            main()
        render.assert_called_once_with("https://example.com", dump_path=None)
        fetch.assert_not_called()
        self.assertIn("Page title: Example Domain", output.getvalue())

    def test_source_row_navigation_and_panel_focus(self):
        import curses
        with TemporaryDirectory() as directory:
            reader = Reader([{"name": "One"}, {"name": "Two"}], Path(directory), offline=True)
            try:
                reader.source = 1
                reader.navigate(curses.KEY_UP)
                self.assertEqual(reader.focus, "sources")
                reader.query = "old search"
                reader.navigate(curses.KEY_RIGHT)
                self.assertEqual(reader.source, 2)
                self.assertEqual(reader.query, "")
                reader.navigate(curses.KEY_LEFT)
                self.assertEqual(reader.source, 1)
                reader.navigate(curses.KEY_DOWN)
                self.assertEqual(reader.focus, "left")
                reader.navigate(curses.KEY_DOWN)
                self.assertEqual(reader.selected, 1)
                reader.navigate(curses.KEY_RIGHT)
                reader.navigate(curses.KEY_DOWN)
                self.assertEqual((reader.selected, reader.scroll), (1, 1))
                reader.navigate(9)
                self.assertEqual(reader.focus, "sources")
            finally:
                reader.pool.shutdown()
                reader.article_pool.shutdown()

    def test_article_request_uses_html_and_bulgarian_headers(self):
        from unittest.mock import patch, MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"article"
        with patch("lynx_news.reader.urllib.request.urlopen", return_value=response) as open_url:
            self.assertEqual(download("https://www.dnevnik.bg/story", article=True), b"article")
        request = open_url.call_args.args[0]
        self.assertIn("Mozilla", request.get_header("User-agent"))
        self.assertIn("text/html", request.get_header("Accept"))
        self.assertIn("bg-BG", request.get_header("Accept-language"))

    def test_forbidden_article_has_actionable_message(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        error = HTTPError("https://example.com/story", 403, "Forbidden", {}, None)
        with patch("lynx_news.reader.download", side_effect=error):
            with self.assertRaisesRegex(ValueError, "HTTP 403: publisher blocked article access"):
                fetch_article("https://example.com/story")

    def test_dnevnik_403_uses_browser_and_extracts_paragraphs(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        url = "https://www.dnevnik.bg/story"
        page = '<title>News</title><div itemprop="articleBody"><p>' + 'Първи абзац. ' * 12 + '</p><p>Втори абзац.</p></div>'
        with patch("lynx_news.reader.download", side_effect=HTTPError(url, 403, "Forbidden", {}, None)), patch("lynx_news.reader.render_page", return_value=page) as render:
            body = fetch_article(url)
        render.assert_called_once_with(url)
        self.assertIn("\n\nВтори абзац.", body)

    def test_dnevnik_browser_challenge_is_not_article_text(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        url = "https://www.dnevnik.bg/story"
        with patch("lynx_news.reader.download", side_effect=HTTPError(url, 403, "Forbidden", {}, None)), patch("lynx_news.reader.render_page", return_value='<title>Just a moment...</title><article>' + 'Challenge ' * 30 + '</article>'):
            with self.assertRaisesRegex(ValueError, "also blocked the browser"):
                fetch_article(url)

    def test_debug_html_is_saved_when_extraction_fails(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        url = "https://www.dnevnik.bg/story"
        page = '<html><title>Dnevnik verification</title><main>Waiting for verification</main></html>'
        with TemporaryDirectory() as directory:
            target = Path(directory) / "debug.html"
            with patch("lynx_news.reader.download", side_effect=HTTPError(url, 403, "Forbidden", {}, None)), patch("lynx_news.reader.render_page", return_value=page):
                with self.assertRaisesRegex(ValueError, "Dnevnik verification"):
                    fetch_article(url, dump_path=target)
            self.assertEqual(target.read_text(), page)

    def test_cloudflare_challenge_without_playwright_points_to_browser(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        url = "https://www.dnevnik.bg/story"
        error = HTTPError(url, 403, "Forbidden", {"cf-mitigated": "challenge"}, None)
        with patch("lynx_news.reader.download", side_effect=error), patch("lynx_news.reader.importlib.util.find_spec", return_value=None), patch("lynx_news.reader.render_page") as render:
            with self.assertRaisesRegex(ValueError, "browser check .Cloudflare.*press c to copy the link"):
                fetch_article(url)
        render.assert_not_called()

    def test_dnevnik_payment_error_does_not_launch_browser(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        url = "https://www.dnevnik.bg/story"
        with patch("lynx_news.reader.download", side_effect=HTTPError(url, 402, "Payment Required", {}, None)), patch("lynx_news.reader.render_page") as render:
            with self.assertRaisesRegex(ValueError, "HTTP 402"):
                fetch_article(url)
        render.assert_not_called()

    def test_dnevnik_success_does_not_launch_browser(self):
        from unittest.mock import patch
        page = ('<article><p>' + 'Article text. ' * 20 + '</p></article>').encode()
        with patch("lynx_news.reader.download", return_value=page), patch("lynx_news.reader.render_page") as render:
            self.assertIn("Article text.", fetch_article("https://www.dnevnik.bg/story"))
        render.assert_not_called()

    def test_missing_browser_has_installation_hint(self):
        from unittest.mock import patch
        from lynx_news.browser import find_browser
        with patch.dict("os.environ", {}, clear=True), patch("lynx_news.browser.shutil.which", return_value=None), patch("lynx_news.browser.Path.is_file", return_value=False):
            with self.assertRaisesRegex(ValueError, "Install Chrome/Chromium"):
                find_browser()

    def test_rss_content_and_safe_links(self):
        data = b'<rss><channel><item><title>A &amp; B</title><link>https://example.com/a</link><description>&lt;p&gt;Hello&lt;/p&gt;</description></item><item><link>javascript:alert(1)</link></item></channel></rss>'
        articles = parse_feed(data, "Test")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "A & B")
        self.assertEqual(articles[0]["summary"], "Hello")

    def test_atom_namespace_and_alternate_link(self):
        data = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom</title><link rel="self" href="https://example.com/feed"/><link href="https://example.com/story"/><content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">Article text</div></content><updated>2026-10-05</updated></entry></feed>'
        article = parse_feed(data, "Test")[0]
        self.assertEqual(article["url"], "https://example.com/story")
        self.assertEqual(article["summary"], "Article text")
        self.assertEqual(article["date"], "2026-10-05")

    def test_homepage_deduplication_and_external_links(self):
        parser = HeadlineParser({"name": "Dnes.bg", "website": "https://www.dnes.bg/"})
        parser.feed('<a href="/a/2-svyat/123-title">Български новини от днес</a><a href="/a/2-svyat/123-title">Български новини от днес</a><a href="https://other.bg/a/123">External article title</a>')
        self.assertEqual(len(parser.articles), 1)
        self.assertEqual(next(iter(parser.articles.values()))["title"], "Български новини от днес")

    def test_saved_articles_remain_searchable_without_cache(self):
        with TemporaryDirectory() as directory:
            reader = Reader([{"name": "Test"}], Path(directory), offline=True)
            try:
                reader.saved = {"one": {"source": "Test", "title": "България", "summary": "Новини"}}
                reader.saved_only = True
                reader.query = "българия"
                self.assertEqual(len(reader.visible()), 1)
            finally:
                reader.pool.shutdown()
                reader.article_pool.shutdown()

    def test_article_paragraphs_exclude_related_stories(self):
        parser = ArticleParser()
        first = "Първи абзац на новината. " * 5
        second = "Втори абзац с подробности. " * 5
        parser.feed(f'<nav>Menu</nav><article><h1>Title</h1><div class="article-content"><p>{first}<strong>Акцент</strong></p><p>{second}</p><div class="related"><p>Other stories</p></div></div><aside>Advertising</aside></article>')
        body = parser.extract()
        self.assertIn("Акцент\n\nВтори", body)
        self.assertNotIn("Other stories", body)
        self.assertNotIn("Advertising", body)

    def test_json_ld_graph_article_body(self):
        import json
        parser = ArticleParser()
        text = "Full article paragraph. " * 8 + "\n\nSecond paragraph."
        parser.feed('<script type="application/ld+json">' + json.dumps({"@graph": [{"@type": "NewsArticle", "articleBody": text}]}) + '</script>')
        self.assertIn("\n\nSecond paragraph.", parser.extract())

    def test_missing_body_does_not_use_navigation(self):
        parser = ArticleParser()
        parser.feed('<nav><p>Menu</p></nav><main><p>Subscribe to read</p></main>')
        with self.assertRaises(ValueError):
            parser.extract()

    def test_background_article_fetch_persists_for_offline_reading(self):
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            reader = Reader([{"name": "Test"}], Path(directory), offline=True)
            article = {"id": "one", "url": "https://example.com/story", "summary": "Summary"}
            try:
                reader.offline = False
                with patch("lynx_news.reader.fetch_article", return_value="Whole article\n\nMore text"):
                    reader.load_selected(article)
                    reader.article_pending["one"].result(timeout=2)
                    reader.poll()
                self.assertEqual(reader.article_text(article), ("Full article", "Whole article\n\nMore text"))
                self.assertTrue((Path(directory) / "articles.json").exists())
            finally:
                reader.pool.shutdown()
                reader.article_pool.shutdown()

    def test_abstract_is_default_even_with_cached_full_text(self):
        with TemporaryDirectory() as directory:
            reader = Reader([{"name": "Test"}], Path(directory), offline=True)
            article = {"id": "one", "url": "https://example.com/story", "summary": "Abstract"}
            try:
                reader.bodies["one"] = "Complete story"
                self.assertEqual(reader.article_text(article)[1], "Abstract")
                self.assertFalse(reader.article_pending)
                reader.load_selected(article)
                self.assertEqual(reader.article_text(article), ("Full article", "Complete story"))
                self.assertFalse(reader.article_pending)
                reader.full_requested.discard("one")
                self.assertEqual(reader.article_text(article)[1], "Abstract")
            finally:
                reader.pool.shutdown()
                reader.article_pool.shutdown()

    def test_publication_time_accepts_rss_and_atom(self):
        self.assertIn("2026", display_time("Mon, 05 Oct 2026 18:00:00 GMT"))
        self.assertIn("2026", display_time("2026-10-05T18:00:00Z"))
        self.assertEqual(display_time(""), "Time unavailable")


if __name__ == "__main__":
    unittest.main()
