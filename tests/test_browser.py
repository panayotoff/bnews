import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, Mock, patch

from lynx_news.browser import find_browser, render_page


class BrowserError(Exception):
    pass


class BrowserTimeout(BrowserError):
    pass


class BrowserTests(unittest.TestCase):
    def test_debian_browser_uses_binary_without_desktop_launcher_flags(self):
        with patch.dict(os.environ, {}, clear=True), patch('lynx_news.browser.shutil.which', return_value='/usr/bin/chromium'), patch('lynx_news.browser.Path.is_file', return_value=True), patch('lynx_news.browser.os.access', return_value=True):
            self.assertEqual(find_browser(), '/usr/lib/chromium/chromium')

    def test_explicit_browser_override_is_preserved(self):
        with patch.dict(os.environ, {'BNEWS_BROWSER': '/usr/bin/chromium'}), patch('lynx_news.browser.shutil.which', return_value='/usr/bin/chromium'), patch('lynx_news.browser.Path.is_file', return_value=True), patch('lynx_news.browser.os.access', return_value=True):
            self.assertEqual(find_browser(), '/usr/bin/chromium')

    def test_launcher_is_used_if_native_binary_is_not_available(self):
        with patch.dict(os.environ, {}, clear=True), patch('lynx_news.browser.shutil.which', return_value='/usr/bin/chromium'), patch('lynx_news.browser.Path.is_file', return_value=False):
            self.assertEqual(find_browser(), '/usr/bin/chromium')

    def setup_driver(self):
        factory = MagicMock()
        driver = factory.return_value.__enter__.return_value
        browser = driver.chromium.launch.return_value
        page = browser.new_context.return_value.new_page.return_value
        page.goto.return_value.status = 200
        page.url = 'https://example.com/'
        page.content.return_value = '<html><title>Example</title><body>Article text</body></html>'
        page.title.return_value = 'Example'
        return factory, driver, browser, page

    def test_page_saved_and_browser_closed_after_success(self):
        factory, driver, browser, page = self.setup_driver()
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'debug.html'
            with patch('lynx_news.browser._load_playwright', return_value=(factory, BrowserError, BrowserTimeout)), patch('lynx_news.browser.find_browser', return_value='/usr/lib/chromium/chromium'):
                html = render_page('https://example.com', dump_path=target)
            self.assertEqual(target.read_text(), html)
            trace = json.loads(Path(str(target) + '.json').read_text())
            self.assertEqual(trace['engine'], 'playwright')
            self.assertEqual(trace['stage'], 'complete')
            self.assertEqual(trace['status'], 200)
        browser.close.assert_called_once()
        self.assertTrue(driver.chromium.launch.call_args.kwargs['chromium_sandbox'])
        page.goto.assert_called_once_with('https://example.com', wait_until='domcontentloaded', timeout=30000)

    def test_navigation_failure_is_saved_and_browser_closed(self):
        factory, driver, browser, page = self.setup_driver()
        page.goto.side_effect = BrowserTimeout('Timeout 30000ms exceeded at https://example.com')
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'debug.html'
            with patch('lynx_news.browser._load_playwright', return_value=(factory, BrowserError, BrowserTimeout)), patch('lynx_news.browser.find_browser', return_value='chromium'):
                with self.assertRaisesRegex(ValueError, 'timed out during navigation'):
                    render_page('https://example.com', dump_path=target)
            trace = json.loads(Path(str(target) + '.json').read_text())
            self.assertEqual(trace['stage'], 'navigation')
            self.assertIn('30000ms', trace['failure'])
        browser.close.assert_called_once()
        page.content.assert_not_called()

    def test_launch_failure_has_stage_and_detail(self):
        factory, driver, browser, page = self.setup_driver()
        driver.chromium.launch.side_effect = BrowserError('Chromium startup failed')
        with patch('lynx_news.browser._load_playwright', return_value=(factory, BrowserError, BrowserTimeout)), patch('lynx_news.browser.find_browser', return_value='chromium'):
            with self.assertRaisesRegex(ValueError, 'failed during launch.*Chromium startup failed'):
                render_page('https://example.com')

    def test_network_response_events_are_recorded(self):
        factory, driver, browser, page = self.setup_driver()
        callbacks = {}
        page.on.side_effect = lambda name, callback: callbacks.__setitem__(name, callback)
        response = Mock(url='https://example.com', status=403, frame=page.main_frame)
        response.request.is_navigation_request.return_value = True
        def navigate(*args, **kwargs):
            callbacks['response'](response)
            return response
        page.goto.side_effect = navigate
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'debug.html'
            with patch('lynx_news.browser._load_playwright', return_value=(factory, BrowserError, BrowserTimeout)), patch('lynx_news.browser.find_browser', return_value='chromium'):
                render_page('https://example.com', dump_path=target)
            trace = json.loads(Path(str(target) + '.json').read_text())
            self.assertEqual(trace['network'][0]['status'], 403)


if __name__ == '__main__':
    unittest.main()
