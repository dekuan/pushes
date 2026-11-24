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
    cp "$source_dir/pushes.py" "$task_tmp/pushes"
    cp "$source_dir/completions/_pushes" "$task_tmp/_pushes"
else
    command -v curl >/dev/null 2>&1 || { echo 'curl is required.' >&2; exit 1; }
    base=https://raw.githubusercontent.com/dekuan/pushes/main
    curl -fsSL "$base/pushes.py" -o "$task_tmp/pushes"
    curl -fsSL "$base/completions/_pushes" -o "$task_tmp/_pushes"
fi
mkdir -p "$install_dir" "$completion_dir"
install -m 755 "$task_tmp/pushes" "$install_dir/pushes"
install -m 644 "$task_tmp/_pushes" "$completion_dir/_pushes"
printf 'Installed: %s/pushes\n\nAdd to ~/.zshrc if needed:\n' "$install_dir"
printf 'export PATH="%s:$PATH"\nfpath=("%s" $fpath)\nautoload -Uz compinit && compinit\n' "$install_dir" "$completion_dir"
printf '\nThen open a new terminal and run pushes in any project directory.\n'
