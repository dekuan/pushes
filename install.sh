#!/bin/sh
set -eu

# Works both from a checkout and via curl | sh. No sudo or shell config edits.
command -v git >/dev/null 2>&1 || { echo 'Install Git first: xcode-select --install' >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo 'Install Python 3.9+ from https://www.python.org/downloads/macos/' >&2; exit 1; }
python3 -c 'import curses, sys; sys.exit(sys.version_info < (3, 9))' || {
    echo 'Python 3.9+ with curses is required.' >&2; exit 1;
}
install_dir=${PUSHES_BIN_DIR:-"$HOME/.local/bin"}
completion_dir=${PUSHES_COMPLETION_DIR:-"$HOME/.local/share/zsh/site-functions"}
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
task_tmp=$(mktemp -d)
trap 'rm -rf "$task_tmp"' EXIT HUP INT TERM
if [ -f "$source_dir/pushes.py" ] && [ -f "$source_dir/completions/_pushes" ]; then
    version_source=$source_dir
else
    # Full main-branch history provides the revision count without commit hooks.
    # Source files and their version come from the same checkout.
    git clone --quiet --single-branch --no-tags --branch main \
        https://github.com/dekuan/pushes.git "$task_tmp/source"
    version_source=$task_tmp/source
fi
cp "$version_source/pushes.py" "$task_tmp/pushes"
cp "$version_source/completions/_pushes" "$task_tmp/_pushes"
installed_version=$(python3 - "$version_source" "$task_tmp/pushes" <<'PY'
from pathlib import Path
import subprocess
import sys

source, target = map(Path, sys.argv[1:])
version = "dev"
if (source / ".git").exists():
    count = subprocess.check_output(["git", "-C", str(source), "rev-list", "--count", "HEAD"], text=True).strip()
    if not count.isdigit():
        raise SystemExit("Invalid Git revision count")
    if subprocess.check_output(["git", "-C", str(source), "rev-parse", "--is-shallow-repository"], text=True).strip() == "true":
        raise SystemExit("Full Git history required for versioning; run git fetch --unshallow first")
    version = f"r{count}"
text = target.read_text(encoding="utf-8")
marker = 'BUILD_VERSION = ""'
if text.count(marker) != 1:
    raise SystemExit("Could not embed the Pushes version")
target.write_text(text.replace(marker, f'BUILD_VERSION = "{version}"', 1), encoding="utf-8")
print(version)
PY
)
mkdir -p "$install_dir" "$completion_dir"
install -m 755 "$task_tmp/pushes" "$install_dir/pushes"
install -m 644 "$task_tmp/_pushes" "$completion_dir/_pushes"
printf 'Installed: %s/pushes (%s)\n\nAdd to ~/.zshrc if needed:\n' "$install_dir" "$installed_version"
printf 'export PATH="%s:$PATH"\nfpath=("%s" $fpath)\nautoload -Uz compinit && compinit\n' "$install_dir" "$completion_dir"
printf '\nThen open a new terminal and run pushes in any project directory.\n'
