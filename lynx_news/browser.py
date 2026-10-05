"""Optional Playwright-backed rendering for pages that reject HTTP clients."""
import json
import os
from pathlib import Path
import shutil


def find_browser():
    configured = os.environ.get("BNEWS_BROWSER")
    if configured:
        executable = shutil.which(configured) or str(Path(configured).expanduser())
        if Path(executable).is_file() and os.access(executable, os.X_OK):
            return executable
        raise ValueError("BNEWS_BROWSER must name an executable Chrome or Chromium binary")
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        executable = shutil.which(name)
        if executable:
            # Debian/Raspberry Pi's shell launcher loads /etc/chromium.d and
            # injects desktop extensions, accessibility and GL flags. Use the
            # packaged binary for our isolated headless session when available.
            native_candidates = {
                "/usr/bin/chromium": "/usr/lib/chromium/chromium",
                "/usr/bin/chromium-browser": "/usr/lib/chromium-browser/chromium-browser",
            }
            native = native_candidates.get(executable)
            if native and Path(native).is_file() and os.access(native, os.X_OK):
                return native
            return executable
    for root in (Path("/Applications"), Path.home() / "Applications"):
        for app, binary in (("Google Chrome", "Google Chrome"), ("Chromium", "Chromium")):
            executable = root / f"{app}.app" / "Contents/MacOS" / binary
            if executable.is_file() and os.access(executable, os.X_OK):
                return str(executable)
    raise ValueError("Dnevnik returned HTTP 403. Install Chrome/Chromium for browser fetching, or set BNEWS_BROWSER to its executable")


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright, Error, TimeoutError
    except ImportError as error:
        raise ValueError("Browser fetching requires Playwright. From the project directory run: python3 -m venv .venv && .venv/bin/python -m pip install playwright") from error
    return sync_playwright, Error, TimeoutError


def render_page(url, dump_path=None):
    factory, browser_error, browser_timeout = _load_playwright()
    executable = find_browser()
    trace = {"engine": "playwright", "browser": executable, "stage": "launch", "network": []}
    debug_path = Path(str(dump_path) + ".json") if dump_path is not None else None
    def save_trace():
        if debug_path is not None:
            debug_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    args = ["--disable-extensions"]
    if dump_path is not None:
        netlog = str(Path(str(dump_path) + ".netlog.json").resolve())
        args.append(f"--log-net-log={netlog}")
        trace["netlog"] = netlog
    save_trace()
    browser = None
    with factory() as driver:
        try:
            browser = driver.chromium.launch(
                executable_path=executable, headless=True, chromium_sandbox=True,
                timeout=15000, args=args,
            )
            trace["stage"] = "create page"
            context = browser.new_context(locale="bg-BG", accept_downloads=False)
            page = context.new_page()
            page.set_default_timeout(5000)
            def response_received(response):
                if response.request.is_navigation_request() and response.frame == page.main_frame:
                    trace["network"].append({"url": response.url, "status": response.status})
                    trace["network"] = trace["network"][-20:]
                    save_trace()
            def request_failed(request):
                if request.is_navigation_request():
                    trace["network"].append({"url": request.url, "failure": request.failure})
                    trace["network"] = trace["network"][-20:]
                    save_trace()
            page.on("response", response_received)
            page.on("requestfailed", request_failed)
            trace["stage"] = "navigation"
            save_trace()
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            trace["url"] = page.url
            trace["status"] = response.status if response is not None else None
            trace["stage"] = "read page"
            save_trace()
            page.wait_for_function("document.body && document.body.innerText.trim().length > 0", timeout=5000)
            html = page.content()
            if len(html.encode()) > 5_000_000:
                raise ValueError("Rendered article exceeds 5 MB")
            trace["stage"] = "complete"
            trace["title"] = page.title()
            trace["html_length"] = len(html)
            if dump_path is not None:
                Path(dump_path).write_text(html, encoding="utf-8")
            save_trace()
            return html
        except browser_timeout as error:
            trace["failure"] = str(error)
            save_trace()
            raise ValueError(f"Browser timed out during {trace['stage']}: {str(error)[:1000]}") from error
        except browser_error as error:
            trace["failure"] = str(error)
            save_trace()
            raise ValueError(f"Browser failed during {trace['stage']}: {str(error)[:1000]}") from error
        finally:
            if browser is not None:
                try:
                    browser.close()
                except browser_error:
                    pass
