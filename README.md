# BNews

A keyboard-driven terminal news reader for Linux and macOS. Requires Python 3.10+; no third-party packages.

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
   with Python and requires no third-party runtime packages.
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
