# BNews

A keyboard-driven terminal news reader for Linux and macOS. Requires Python 3.10+. Feed reading uses the Python standard library; optional browser fetching requires Playwright.

```sh
git clone https://github.com/panayotoff/bnews.git
cd bnews
./bnews
```

Dnes.bg, Dnevnik.bg, Frognews, and Offnews are included. The opening screen lists sources: use arrows or j/k and Enter to select one. Esc returns to the source menu. The interface uses a cyan accent and a split headline/reading layout on wider terminals.

To run `bnews` from any directory, run these commands from the project directory:

```sh
mkdir -p "$HOME/.local/bin"
ln -s "$(pwd)/bnews" "$HOME/.local/bin/bnews"
export PATH="$HOME/.local/bin:$PATH"
bnews
```

Add the export line to `~/.zshrc` to retain it in new terminals (or `~/.bashrc` for Bash). Keep the project directory in place so the command's symlink continues to work. The executable resolves its bundled source file regardless of your working directory.

## installation promt

Copy this prompt into your coding agent to install BNews on Linux or macOS:

```text
Install BNews from https://github.com/panayotoff/bnews.git on this computer
and make it available as the shell command bnews from any directory.

1. Check that Python 3.10+ with curses and Git are available. If anything
   is missing, help install it using the appropriate method for this OS.
2. Clone the repository into ~/Applications/bnews. If it already exists,
   check it before reusing it; preserve local changes.
3. Ensure the repository's bnews launcher is executable. It runs directly
   with Python. For browser fetching, create .venv with python3 -m venv
   .venv and install .venv/bin/python -m pip install -e '.[browser]'.
   Ensure Chrome or Chromium is installed. The launcher uses .venv automatically.
4. Create ~/.local/bin if needed and symlink ~/.local/bin/bnews to the
   absolute path of the repository's bnews launcher. Check any existing
   command or symlink first; do not overwrite an unrelated installation.
5. Add ~/.local/bin to PATH for the current shell and persist it in the
   appropriate startup file: ~/.zshrc for Zsh, ~/.bashrc for Bash, or the
   equivalent for my shell. Avoid duplicate PATH entries and preserve
   the rest of my shell configuration.
6. Verify command -v bnews and bnews --help from outside the repository,
   and run python3 -m unittest discover -s tests inside the repository.
7. Tell me what was installed and show the command to launch it: bnews.
   If this environment blocks filesystem or shell configuration changes,
   give me the exact remaining commands to run in my terminal.

Use portable paths based on my home directory. Keep the repository in
place because the shell command points to it. Do not open the interactive
TUI unless you have an interactive terminal available.
```

After installation, open a new terminal and run:

```sh
bnews
```

To read cached news without fetching feeds:

```sh
bnews --offline
```

## Update prompt

Copy this prompt into your coding agent to update an existing installation:

```text
Update my existing BNews installation from
https://github.com/panayotoff/bnews.git and keep the bnews shell command working.

1. Locate the installation using command -v bnews and resolve any symlink.
   Check ~/Applications/bnews as well. Determine whether the command runs
   from a Git checkout or an installed Python package before making changes.
2. For a Git checkout, inspect the remote, current branch, and working tree.
   Preserve local changes and custom source configuration. Fetch origin
   and update main with a fast-forward only. If local changes, a different
   branch, or divergent commits prevent a safe update, explain the issue
   and ask how to proceed; do not reset, clean, or discard files.
3. For a packaged installation, obtain the latest source from the same
   repository, build a new wheel, and install it into the environment used
   by the existing bnews command. Do not install into a different Python
   environment or replace a checkout installation with a packaged one.
4. Preserve cached news, saved articles, custom feeds, and shell settings.
   Keep the command's symlink valid and avoid duplicate PATH entries.
5. Run python3 -m unittest discover -s tests in the updated source checkout.
   Verify command -v bnews and bnews --help from outside the repository.
6. Report the previous and new commit or package version, any unresolved
   issues, and tell me to restart BNews by quitting it and running bnews.
   If this environment blocks changes, give me the exact remaining commands
   to run in my terminal.

Use portable paths based on my home directory. Do not open the interactive
TUI unless you have an interactive terminal available.
```

After updating, quit any running instance with `q` and launch it again:

```sh
bnews
```

Edit the example `sources.json` to add your preferred RSS or Atom feeds, then launch with `bnews --sources sources.json`:

```json
[{"name": "Example", "url": "https://example.com/feed.xml"}]
```

Use `--sources path/to/sources.json` for a different source list. Feed updates run in the background; failures retain cached articles and appear in the status bar. Bundled sources also have a `website` URL: if the feed fails, the reader attempts to extract article headlines from the homepage. Publisher blocking or layout changes may prevent either method from working.

| Key | Action |
| --- | --- |
| ↑/↓ or k/j | Select headlines with left focus; scroll text with right focus |
| Tab | Cycle source row, headlines, and article focus |
| ↑ at first headline | Focus source row |
| ←/→ | Switch sources when source row is focused; otherwise switch panels |
| ↓ or Enter in source row | Return to headlines |
| [ / ] | Cycle sources |
| / | Search titles and feed text |
| s | Save or unsave article |
| b | Toggle saved articles |
| Enter | Focus article panel |
| o / O | Fetch and display full article text inside BNews |
| a | Return to abstract |
| c | Copy article link |
| PgUp/PgDn | Page through headlines or text in the focused panel |
| r | Refresh feeds |
| Esc | Return to sources |
| q | Quit |

Articles show their feed abstract by default, including when full text is already cached. Press uppercase O to fetch and display full text in the background. The reader extracts article body containers or structured article text, preserves paragraphs, and caches the result for offline reading. The pane displays “Loading full article…” while fetching, or an error with the feed summary if the page is inaccessible or its text cannot be extracted. Press O again to retry a failed fetch. Publisher access restrictions still apply.

### Dnevnik article fetching

If Dnevnik returns HTTP 403, BNews tries loading the article with a locally installed Chrome or Chromium in headless mode. The rendered article text appears inside BNews; no browser window opens. This fallback only runs when you request full text with o/O, and successful results are cached.

Dnevnik currently serves every page except its RSS feed behind a Cloudflare browser check (`cf-mitigated: challenge`). Without Playwright installed, BNews reports the check immediately and keeps the abstract; press c to copy the link and read the article in your browser. The headless fallback below is not guaranteed to pass that check.

Install Chrome or Chromium and the optional Playwright dependency if you want this fallback. From the repository directory, run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[browser]'
```

The repository's `bnews` launcher automatically uses `.venv`, including through your shell symlink. For a packaged installation, install `bnews-tui[browser]` into its existing environment. BNews uses your installed browser, so a separate Playwright browser download is unnecessary.

 Linux executables on PATH and standard macOS application locations are detected automatically. For another installation location, provide the browser executable:

```sh
BNEWS_BROWSER="/path/to/chromium" bnews
```

On Debian and Raspberry Pi, BNews prefers the installed Chromium binary over the desktop shell launcher, which can inject system extension and graphics settings. Extensions are disabled in the temporary browser session. An explicit `BNEWS_BROWSER` setting takes precedence over automatic detection.

The browser uses a temporary profile rather than your existing browser session. Playwright controls navigation and waits for readable content after the document loads. Launching has a 15-second timeout, navigation a 30-second timeout, and readable content a 5-second timeout. If Dnevnik also blocks the browser, requires authentication, or does not expose article text, BNews retains the abstract.

To diagnose a specific article without opening the TUI, copy its URL with c and run:

```sh
bnews --check-article 'https://www.dnevnik.bg/path/to/article/'
```

This prints the extracted character count and a short preview, or the fetch error. It does not modify the article cache.

If extraction fails, save the HTML returned by the HTTP client or hidden browser for inspection:

```sh
bnews --check-article 'https://www.dnevnik.bg/path/to/article/' --dump-page dnevnik-debug.html
```

The HTML is saved before article extraction, including when the loaded page is an access screen. A browser navigation timeout produces diagnostics but no HTML file. Diagnostic files are excluded from Git.

Browser diagnostics also produce `dnevnik-debug.html.json`, containing the Playwright fetch stage, document request status, failed requests, and detailed browser errors, plus `dnevnik-debug.html.netlog.json` with Chromium network events. These files are excluded from Git as well.

To distinguish a publisher-specific problem from a general Chromium networking problem, test a simple page directly through the browser:

```sh
bnews --check-browser 'https://example.com' --dump-page browser-debug.html
```

This bypasses the ordinary HTTP fetcher and article extraction, and reports the loaded page title. It produces the same HTML, Playwright trace, and network-log diagnostics. The example diagnostic filenames are excluded from Git.

The article title, publication time, and URL stay at the top while the text scrolls. Tab or left/right arrows switch panel focus; the active panel has a cyan label. Enter focuses the article. Below 65 columns, focusing the article displays it at full width. Esc returns to the source menu.

Copying links uses `pbcopy` on macOS, or `wl-copy`, `xclip`, or `xsel` when available, otherwise the terminal's OSC 52 clipboard protocol. OSC 52 support depends on terminal settings. Both o and O fetch text inside BNews and focus the article panel.

Articles and bookmarks are stored in `$XDG_DATA_HOME/lynx-news` (default `~/.local/share/lynx-news`). Use `--data-dir PATH` to change this, or `--offline` to read cached articles without network requests. Saved articles remain available after they disappear from a feed.

```sh
python3 -m unittest discover -s tests
```


## Install on another computer

Requires Python 3.10+ on Linux or macOS. Build a portable wheel:

```sh
python3 -m pip wheel . --no-deps --wheel-dir dist
```

Copy `dist/bnews_tui-0.1.0-py3-none-any.whl` to your MacBook (for example via AirDrop). On the Mac, install into a dedicated environment and create the command:

```sh
python3 -m venv ~/.local/share/bnews-venv
~/.local/share/bnews-venv/bin/python -m pip install --no-index ~/Downloads/bnews_tui-0.1.0-py3-none-any.whl
mkdir -p ~/.local/bin
ln -s ~/.local/share/bnews-venv/bin/bnews ~/.local/bin/bnews
```

Ensure `~/.local/bin` is on PATH. Add this line to `~/.zshrc` if needed, then open a new terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Run `bnews`. Bundled feeds install with the package; custom feeds can be supplied using `--sources PATH`. Each computer keeps its own cache and saved articles. Package installation does not change publisher access restrictions.

For an update, rebuild and transfer the wheel, then install it using the same environment with `pip install --no-index --force-reinstall PATH_TO_WHEEL`.
