#!/usr/bin/env python3
"""A small, dependency-free Git push dashboard for macOS and Unix terminals."""
import argparse
import concurrent.futures
import curses
import datetime as dt
import locale
import os
from pathlib import Path
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field


class GitError(Exception):
    pass


def git(path, *args, timeout=15):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    # Background authentication must never hold the terminal waiting for input.
    env.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes -oConnectTimeout=10")
    try:
        result = subprocess.run(["git", "-C", str(path), *args], env=env,
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(str(exc)) from exc
    if result.returncode:
        raise GitError((result.stderr or result.stdout).strip() or "Git command failed")
    return result.stdout.strip()


def optional(path, *args):
    try:
        return git(path, *args)
    except GitError:
        return ""


def discover(root):
    """Current repository wins; otherwise inspect immediate children only."""
    top = optional(root, "rev-parse", "--show-toplevel")
    if top:
        return [Path(top)]
    found = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if child.is_dir() and (child / ".git").exists():
            top = optional(child, "rev-parse", "--show-toplevel")
            if top and Path(top).resolve() == child.resolve():
                found.append(child)
    return found


@dataclass
class Repo:
    path: Path
    branch: str = "…"
    upstream: str = ""
    ahead: object = None
    behind: int = 0
    dirty: bool = False
    total: str = "0"
    last: str = "No commits"
    remotes: str = "No remote configured"
    status: str = "CHECKING"
    detail: str = ""
    branches: list = field(default_factory=list)
    fetched: str = "Never"
    network_error: str = ""

    @property
    def icon(self):
        if self.dirty:
            return "🧨"
        if self.status in ("ERROR", "DETACHED", "NO UPSTREAM", "EMPTY", "BEHIND", "DIVERGED"):
            return "!"
        if self.ahead:
            return "🟡"
        return "✓" if self.status == "SYNCED" else "·"


def inspect(path):
    repo = Repo(path)
    repo.branch = optional(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = optional(path, "rev-parse", "--verify", "HEAD")
    repo.dirty = bool(git(path, "status", "--porcelain", "--untracked-files=normal"))
    remote_lines = git(path, "remote", "-v").splitlines()
    repo.remotes = ", ".join(dict.fromkeys(
        line.rsplit(" ", 1)[0].replace("\t", " ") for line in remote_lines
    )) or repo.remotes
    repo.branches = [(b, False) for b in git(path, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()]
    remote_refs = git(path, "for-each-ref", "--format=%(refname:short)\t%(symref)", "refs/remotes")
    repo.branches += [(line.partition("\t")[0], True) for line in remote_refs.splitlines()
                      if not line.partition("\t")[2] and not line.partition("\t")[0].endswith("/HEAD")]
    if head:
        repo.total = git(path, "rev-list", "--count", "HEAD")
        repo.last = git(path, "log", "-1", "--format=%h, %ai, %s")
    repo.upstream = optional(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if not head:
        repo.status, repo.detail = "EMPTY", "Create a commit outside pushes first"
    elif not repo.branch:
        repo.branch = "(detached)"
        repo.status, repo.detail = "DETACHED", "Select a branch with B"
    elif not repo.upstream:
        repo.status, repo.detail = "NO UPSTREAM", "Unpushed count unknown; configure an upstream"
    else:
        counts = git(path, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
        repo.ahead, repo.behind = map(int, counts)
        repo.status = ("DIVERGED" if repo.ahead and repo.behind else "BEHIND" if repo.behind
                       else "READY" if repo.ahead else "SYNCED")
        repo.detail = f"↑{repo.ahead} ↓{repo.behind} vs {repo.upstream}"
    if repo.dirty:
        repo.detail = "Uncommitted changes; " + repo.detail
        if repo.status in ("READY", "SYNCED"):
            repo.status = "DIRTY"
    return repo


def operate(path, action, expected_branch, target=None):
    current = optional(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    if current != expected_branch:
        raise GitError("Branch changed outside pushes; refresh and try again")
    if action == "commit":
        if not current:
            raise GitError("Select a branch before committing")
        if not target or not target.strip():
            raise GitError("Commit message cannot be empty")
        git(path, "add", ".", timeout=120)
        return git(path, "commit", "-m", target, timeout=120)
    if action == "push":
        if not current:
            raise GitError("Select a branch before pushing")
        return git(path, "push", timeout=120) or "Push completed"
    # Refuse even safe carry-over of changes, so switching never moves dirty work.
    if git(path, "status", "--porcelain", "--untracked-files=normal"):
        raise GitError("Working tree has uncommitted changes; commit or stash first")
    name, remote = target
    if remote:
        return git(path, "switch", "--track", "-c", name.split("/", 1)[1], name)
    return git(path, "switch", "--", name)


def update(old, fetch=False, action=None, progress=None):
    message = ""
    def phase(status):
        if progress is not None:
            progress(status)
    try:
        if action:
            phase({"push": "PUSHING", "commit": "COMMITTING", "switch": "SWITCHING"}[action[0]])
            message = operate(old.path, *action)
        if fetch:
            phase("FETCHING")
            try:
                git(old.path, "fetch", "--all", "--quiet", timeout=30)
                old.fetched = dt.datetime.now().astimezone().strftime("%H:%M:%S %z")
                old.network_error = ""
            except GitError as exc:
                old.network_error = str(exc)
        phase(None)
        new = inspect(old.path)
        new.fetched, new.network_error = old.fetched, old.network_error
        return new, message
    except GitError as exc:
        old.status, old.detail = "ERROR", str(exc)
        return old, str(exc)


def clean(value):
    return "".join(char if char.isprintable() else " " for char in str(value))


def clip(value, width):
    result, used = "", 0
    for char in clean(value):
        size = 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if used + size > width:
            break
        result += char
        used += size
    return result + " " * max(0, width - used)


@dataclass
class CommitDraft:
    path: Path
    branch: str
    text: str = ""
    cursor: int = 0


def cell_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def should_fetch(repo, interval, now, deadline, manual=False):
    return manual or (interval > 0 and repo.ahead is not None and repo.ahead > 0 and now >= deadline)


def draw(screen, repos, selected, root, message, busy, popup, ascii_icons, draft=None):
    screen.erase()
    height, width = screen.getmaxyx()

    def put(y, x, value, attr=0, span=None):
        if 0 <= y < height and 0 <= x < width - 1:
            try:
                rendered = clip(value, min(span, width - x - 1) if span is not None else width - x - 1)
                screen.addstr(y, x, rendered if span is not None else rendered.rstrip(), attr)
            except curses.error:
                pass

    if height < 16 or width < 64:
        put(0, 0, "pushes: please resize terminal to at least 64 × 16 (Q exits)")
        screen.refresh()
        return
    title = curses.color_pair(1) | curses.A_BOLD
    clock = dt.datetime.now().astimezone().isoformat(sep=" ", timespec="seconds")
    put(0, 1, "Pushes for Git", title)
    put(0, max(20, width - len(clock) - 2), clock, title)
    put(1, 1, f"Local → {root}", title)
    put(2, 0, "─" * (width - 1))
    repo_w = min(34, max(17, width // 4))
    branch_w = min(24, max(12, width // 6))
    def row(name, branch, commits, status, details):
        return f"{clip(name, repo_w)} {clip(branch, branch_w)} {clip(commits, 7)} {clip(status, 11)} {details}"
    put(3, 1, row("Repo", "Branch", "Commits", "Status", "Details"), title)
    visible = height - 14
    start = max(0, selected - visible + 1)
    for i, repo in enumerate(repos[start:start + visible], start):
        icon = repo.icon
        if ascii_icons:
            icon = {"🧨": "*", "🟡": "+", "✓": "v", "·": "."}.get(icon, icon)
        status = busy.get(repo.path, repo.status)
        attr = curses.A_REVERSE if i == selected else curses.color_pair(3 if repo.dirty or repo.network_error else 2 if repo.ahead or repo.behind else 4 if repo.status == "SYNCED" else 0)
        put(4 + i - start, 1, row(f"{icon} {repo.path.name}", repo.branch,
            "?" if repo.ahead is None else str(repo.ahead), status,
            ("Fetch failed; " if repo.network_error else "") + repo.detail), attr)
    if not repos:
        put(4, 1, "No Git repositories here or in immediate child directories.")
    base = height - 10
    put(base, 0, "─" * (width - 1))
    if repos:
        repo = repos[selected]
        put(base + 1, 1, "Remote: " + repo.remotes)
        put(base + 2, 1, "Last: " + repo.last)
        put(base + 3, 1, f"History: {repo.total} {'commit' if repo.total == '1' else 'commits'}, Fetched: {repo.fetched}")
        put(base + 4, 1, f"Upstream: {repo.upstream or 'unset'}")
        put(base + 5, 1, "Fetch: " + repo.network_error if repo.network_error else repo.detail)
    put(height - 3, 1, "Message: " + message, title)
    put(height - 1, 1, "↑/↓ select  Enter push  C commit  B branches  F fetch  Q quit", title)
    if popup is not None:
        entries, choice = popup
        box_h = min(len(entries) + 3, height - 4)
        box_w = min(width - 4, 70)
        y, x = (height - box_h) // 2, (width - box_w) // 2
        for n in range(box_h):
            put(y + n, x, " " * box_w, curses.A_NORMAL, span=box_w)
        put(y, x + 1, "Branches · Enter switch · Esc cancel", title)
        offset = max(0, choice - (box_h - 3))
        for n, (name, remote) in enumerate(entries[offset:offset + box_h - 2], offset):
            put(y + n - offset + 1, x + 1, clip(name + (" [remote]" if remote else ""), box_w - 2),
                curses.A_REVERSE if n == choice else curses.A_NORMAL)
    if draft is not None:
        prefix = "Commit: "
        available = width - len(prefix) - 2
        start = 0
        while cell_width(draft.text[start:draft.cursor]) >= available:
            start += 1
        put(height - 3, 1, prefix + clip(draft.text[start:], available), title, span=width - 2)
        put(height - 2, 1, message)
        put(height - 1, 1, "Enter: git add . + commit ALL changes  Esc cancel", title, span=width - 2)
        screen.move(height - 3, 1 + len(prefix) + cell_width(draft.text[start:draft.cursor]))
    try:
        curses.curs_set(1 if draft is not None else 0)
    except curses.error:
        pass
    screen.refresh()


def tui(screen, args, root):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        for n, color in enumerate((curses.COLOR_YELLOW, curses.COLOR_YELLOW, curses.COLOR_RED, curses.COLOR_GREEN), 1):
            curses.init_pair(n, color, -1)
    screen.timeout(100)
    repos = [Repo(p) for p in discover(root)]
    selected, popup, message = 0, None, "Checking repositories…"
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    pending, next_scan, next_fetch = {}, {}, {}
    activities = {}
    requested_fetch = set()
    draft = None
    committing = {}

    def submit(repo, fetch=False, action=None):
        path = repo.path
        def report(status):
            if status is None:
                activities.pop(path, None)
            else:
                activities[path] = status
        report({"push": "PUSHING", "commit": "COMMITTING", "switch": "SWITCHING"}[action[0]] if action else "FETCHING" if fetch else None)
        pending[path] = pool.submit(update, repo, fetch, action, report)

    try:
        while True:
            now = time.monotonic()
            for path, future in list(pending.items()):
                if future.done():
                    result, note = future.result()
                    repos = [result if r.path == path else r for r in repos]
                    if note:
                        message = note
                    del pending[path]
                    activities.pop(path, None)
                    if path in committing:
                        previous_draft = committing.pop(path)
                        if result.status == "ERROR":
                            draft = previous_draft
                            popup = None
                            selected = next(i for i, r in enumerate(repos) if r.path == path)
            for repo in repos:
                if draft is not None and repo.path == draft.path:
                    continue
                fetch = should_fetch(repo, args.fetch_interval, now,
                                     next_fetch.get(repo.path, 0), repo.path in requested_fetch)
                if repo.path not in pending and (now >= next_scan.get(repo.path, 0) or fetch):
                    requested_fetch.discard(repo.path)
                    submit(repo, fetch)
                    next_scan[repo.path] = now + args.interval
                    if fetch:
                        next_fetch[repo.path] = now + args.fetch_interval
            draw(screen, repos, selected, root, message, activities, popup, args.ascii, draft)
            try:
                pressed = screen.get_wch()
            except curses.error:
                continue
            key = ord(pressed) if isinstance(pressed, str) else pressed
            if draft is not None:
                if key == 27:
                    draft = None
                    message = "Commit cancelled"
                elif key in (10, 13, curses.KEY_ENTER):
                    if not draft.text.strip():
                        message = "Commit message cannot be empty"
                    else:
                        repo = next(r for r in repos if r.path == draft.path)
                        committing[repo.path] = draft
                        submit(repo, action=("commit", draft.branch, draft.text))
                        draft = None
                        message = "Staging all changes and committing…"
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    if draft.cursor:
                        draft.text = draft.text[:draft.cursor - 1] + draft.text[draft.cursor:]
                        draft.cursor -= 1
                elif key == curses.KEY_DC:
                    draft.text = draft.text[:draft.cursor] + draft.text[draft.cursor + 1:]
                elif key == curses.KEY_LEFT:
                    draft.cursor = max(0, draft.cursor - 1)
                elif key == curses.KEY_RIGHT:
                    draft.cursor = min(len(draft.text), draft.cursor + 1)
                elif key in (curses.KEY_HOME, 1):
                    draft.cursor = 0
                elif key in (curses.KEY_END, 5):
                    draft.cursor = len(draft.text)
                elif isinstance(pressed, str) and pressed.isprintable():
                    draft.text = draft.text[:draft.cursor] + pressed + draft.text[draft.cursor:]
                    draft.cursor += 1
                continue
            if key in (ord('q'), ord('Q')):
                break
            if popup is not None:
                entries, choice = popup
                if key == 27:
                    popup = None
                elif key in (curses.KEY_DOWN, ord('j')):
                    popup = (entries, min(len(entries) - 1, choice + 1))
                elif key in (curses.KEY_UP, ord('k')):
                    popup = (entries, max(0, choice - 1))
                elif key in (10, 13, curses.KEY_ENTER) and entries:
                    repo = repos[selected]
                    if repo.path not in pending:
                        submit(repo, action=("switch", repo.branch, entries[choice]))
                        message = "Switching branch…"
                        popup = None
                continue
            if key in (curses.KEY_DOWN, ord('j')):
                selected = min(max(0, len(repos) - 1), selected + 1)
            elif key in (curses.KEY_UP, ord('k')):
                selected = max(0, selected - 1)
            elif key in (ord('f'), ord('F')):
                if repos:
                    repo = repos[selected]
                    requested_fetch.add(repo.path)
                    message = f"Fetch requested for {repo.path.name}"
                else:
                    message = "No repository selected"
            elif repos and key in (ord('b'), ord('B'), ord('c'), ord('C'), 10, 13, curses.KEY_ENTER):
                repo = repos[selected]
                if repo.path in pending:
                    message = f"Repository busy ({activities.get(repo.path, 'local refresh')}); try again when it finishes"
                elif key in (ord('c'), ord('C')):
                    if committing:
                        message = "A commit is already in progress; wait for it to finish"
                    else:
                        draft = CommitDraft(repo.path, repo.branch)
                        message = "Enter runs git add . + commit: ALL changes, respects .gitignore"
                elif key in (ord('b'), ord('B')):
                    popup = (repo.branches, 0) if repo.branches else None
                    if popup is None:
                        message = "No branches available"
                else:
                    submit(repo, action=("push", repo.branch))
                    message = f"Pushing {repo.path.name}…"
    finally:
        # Running Git processes are bounded by timeouts; restore terminal immediately.
        pool.shutdown(wait=False, cancel_futures=True)


def positive(value):
    number = float(value)
    if not 0.2 <= number <= 86400:
        raise argparse.ArgumentTypeError("must be between 0.2 and 86400 seconds")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default=".", type=Path)
    parser.add_argument("--interval", type=positive, default=5, help="local refresh seconds (default: 5)")
    parser.add_argument("--fetch-interval", type=int, default=30, help="automatic fetch seconds when ahead > 0 (default: 30); 0 disables")
    parser.add_argument("--ascii", action="store_true", help="use plain status icons")
    parser.add_argument("--once", action="store_true", help="print local status and exit without fetching")
    args = parser.parse_args()
    if args.fetch_interval < 0:
        parser.error("--fetch-interval must be nonnegative")
    try:
        root = args.directory.expanduser().resolve(strict=True)
        if not root.is_dir():
            parser.error("directory must be a directory")
        git(root, "--version")
        if args.once:
            for path in discover(root):
                repo = inspect(path)
                print(f"{repo.icon} {path.name}\t{repo.branch}\t{repo.ahead if repo.ahead is not None else '?'}\t{repo.status}\t{repo.detail}")
        else:
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                parser.error("TUI requires a terminal; use --once for plain output")
            locale.setlocale(locale.LC_ALL, "")
            curses.wrapper(tui, args, root)
    except KeyboardInterrupt:
        return 130
    except (GitError, OSError, curses.error) as exc:
        print(f"pushes: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
