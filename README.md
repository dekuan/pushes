# Pushes for Git

A lightweight Git TUI focused on **pushing**, with one-step staging and committing of all changes. Built primarily for macOS; also works in Linux terminals with Python curses support. Free and open source under the MIT license. Works with GitHub and other Git remotes, without GitHub Desktop or the GitHub API.

## Installation and usage

Requires Git and **Python 3.9+** with the standard-library `curses` module. No pip packages are needed. macOS may not include a usable Python 3 installation; you can install it from [python.org](https://www.python.org/downloads/macos/). To install Git on macOS, run `xcode-select --install`.

Install from the URL:

```sh
curl -fsSL https://raw.githubusercontent.com/dekuan/pushes/main/install.sh | sh
```

Or install from a local clone:

```sh
sh install.sh
```

The script installs the command to `~/.local/bin/pushes` without sudo. It prints the PATH and zsh completion settings to add to `~/.zshrc`. After adding them, open a new terminal and run `pushes` from any directory. Tab completion supports the command name, options, and directory paths. Set `PUSHES_BIN_DIR` and `PUSHES_COMPLETION_DIR` to customize the installation locations.

You can also run the Python script directly:

```sh
python3 pushes.py
python3 pushes.py /path/to/projects
python3 pushes.py --fetch-interval 120
python3 pushes.py --fetch-interval 0 --ascii
python3 pushes.py --once
python3 pushes.py --version
```

## Application version

The title displays Pushes' own revision, such as `Pushes for Git r12`. Run `pushes --version` to check the installed version. The number comes from the commit count of the **Pushes source repository**, not the repositories shown in the dashboard.

No special commit command, version-file edit, or Git hook is needed. Each ordinary new commit on the same linear branch increases the count by one. Publish your changes and rerun the URL installer to update an installed copy; for a local checkout, rerun `sh install.sh`. The installer embeds the revision into the installed script, so it works from any directory without contacting GitHub at runtime. URL installation temporarily clones the full `main` history to obtain matching source files and their revision. Direct execution from a source checkout reads that checkout's count at startup. A source archive without Git history displays `dev`; local installation from a shallow clone requires `git fetch --unshallow` first.

This is a simple revision counter, not a semantic version or a globally unique commit identifier. Merges, branch changes, or rewritten history can cause skipped, repeated, or lower numbers. Uncommitted edits do not increase the number, and an installed copy keeps its embedded version until reinstalled.

## Interface and controls

The header shows the application name, the system's local time updated every second, the UTC offset, and the directory being scanned. The table contains `Repo / Branch / Commits / Status / Details`. The details area shows the selected repository's remote address, latest commit hash, timestamp and message, history count, upstream, and last successful fetch time.

The selected repository is marked with a left-side `▶` and bold text, preserving its status color and the terminal background. With `--ascii`, the marker is `>`.

Headings and regular messages use muted blue, with light-gray details and slightly darker gray separators and shortcuts. Status colors remain red, yellow, and green. The palette adapts to the terminal's color capabilities, using an approximate blue on fixed 256-color palettes and cyan on basic color terminals; the terminal background is preserved.

| Key | Action |
| --- | --- |
| ↑ / ↓ or K / J | Select a repository or branch |
| Enter | Run `git push` for the selected repository; confirm a selection in the branch menu |
| B | Open the list of local and remote branches |
| C | Enter a commit message at the bottom; Enter stages and commits all changes, Esc cancels |
| Esc | Close the branch menu or cancel commit input |
| F | Fetch only the selected repository, regardless of its commit count |
| T | Move the selected repository to the top, keeping it selected, and save the complete order to `.pushes` |
| Q | Quit |

Status icons use compact text symbols: red `!` for uncommitted changes, including untracked files; yellow `↑` for commits ahead of the upstream; green `✓` for a clean working tree matching the upstream. `!` also marks other states requiring attention, such as being behind, diverged, or missing an upstream; the Status and Details columns distinguish them. The uncommitted-changes icon takes priority, while the commit count is shown independently. Use `--ascii` for `!` / `+` / `v` icons.

Repository order is loaded from `.pushes` in the launch directory (or the directory passed on the command line). Each press of T saves the complete current order there as JSON using relative repository paths. Repositories missing from the saved list appear at the end in discovery order; saved entries for repositories that no longer exist are ignored. The file is created only when you press T, and starting or quitting the application does not create or rewrite it. If saving fails, the order still changes for the current session and an error is displayed.

Local refreshes keep the repository's status visible without flashing an operation label. Remote fetches display `FETCHING`; other operations display `PUSHING`, `COMMITTING`, or `SWITCHING`. While pushing, the repository icon animates through `| / - \` at eight frames per second, then returns to its regular status icon when the push finishes.

## Git behavior and limits

- When launched inside a repository, only that repository is shown, including when launched from one of its subdirectories. Otherwise, only immediate child directories are scanned, without recursion. Worktrees using a `.git` file are supported.
- `Commits` counts commits by which `HEAD` is ahead of `@{upstream}`. It is neither the total history count nor the number of uncommitted files. If no upstream can be resolved, the count is `?`. Behind and diverged states are shown separately. The history count includes all commits reachable from the current HEAD.
- Local status is checked every 5 seconds by default. Automatic `git fetch --all --quiet` runs only when the detected unpushed commit count is greater than zero, with a default interval of 30 seconds. Uncommitted file changes alone do not trigger a fetch. A count of zero or an unknown count (`?`, such as when no upstream is configured) disables automatic fetches for that repository. Press F to fetch only the selected repository regardless of its count, even with `--fetch-interval 0`; other repositories and their refresh schedules are unaffected. Without automatic fetches, remote-only changes are not discovered until you fetch manually or the local count becomes positive. Local checks preserve the displayed status while running; remote fetches display `FETCHING`. The clock updates every second independently. Background tasks keep the clock and keyboard responsive. Tasks run serially within each repository, with up to four repositories processed concurrently. Remote information is updated after a successful fetch; local status and fetch errors remain visible when offline.
- Enter runs the native `git push` command, honoring the repository's existing remote, pushRemote, push refspec, and push.default settings. Depending on your Git configuration, this may push more than the current branch. `Commits` compares against the upstream; if the push destination differs from the upstream, this count does not describe the difference at that destination. The application does not choose a remote for you when no upstream is configured. If Git is not configured to set one up automatically, its error is displayed.
- If a push fails, the selected repository is fetched once automatically, regardless of the commit count or automatic-fetch setting, then its local status is refreshed. The original push error and the fetch outcome remain in Message. This does not retry the push, pull, or merge; fetching alone cannot resolve authentication, connectivity, or branch conflicts.
- C opens a single-line commit input supporting Unicode, left/right navigation, Home/End, and Backspace/Delete. Letters such as Q are treated as text while editing. The input area explicitly states that Enter will run `git add .` at the selected repository's root, followed by `git commit -m`. This includes all added, modified, and deleted files, respects `.gitignore`, and does not push automatically. Pressing C only opens the input; Esc cancels without changing the index. Empty messages are rejected. If there is nothing to commit or a Git hook fails, the message is preserved for editing and retrying. If staging succeeds but the commit fails, changes remain staged. The status shows `COMMITTING` during the operation; the commit count and Last details update after success.
- The application does not pull, merge, rebase, force-push, or resolve conflicts automatically. Existing commits can be pushed from a dirty working tree. Branch switching is refused when the working tree has uncommitted changes, without automatically stashing them. Selecting a remote branch creates a local tracking branch. If a local branch with that name already exists, Git refuses the operation; select the existing local branch instead.
- Git uses your existing SSH agent or credential manager. Background commands do not allow terminal password prompts, so complete Git authentication in a regular terminal first. Fetch operations time out after 30 seconds; push, staging, and commit operations time out after 120 seconds each. Quitting restores the terminal immediately; any running Git tasks finish or time out before the process exits. Git hooks and credential programs follow your local configuration.
- A terminal width of at least 100 columns is recommended; the minimum size is 64×16. Long information is truncated to fit. Native Windows terminals are not currently supported; WSL can be used instead.

To uninstall, delete `pushes` from the installation directory and `_pushes` from the completion directory, then remove any shell configuration you added if no longer needed.

## Development checks

```sh
python3 -m unittest discover -s tests -v
python3 pushes.py --once
```

See [docs/requirements.md](docs/requirements.md) for the detailed requirements and implementation tradeoffs (in Chinese).
