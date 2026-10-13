#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
package_source="$repo_root/plasma6/io.github.geequlim.quotaglance"
data_root="$HOME/.local/share"
backup_root="$HOME/.local/state/quota-glance/backups"
if [[ -v XDG_DATA_HOME && -n "$XDG_DATA_HOME" ]]; then
    data_root="$XDG_DATA_HOME"
fi
if [[ -v XDG_STATE_HOME && -n "$XDG_STATE_HOME" ]]; then
    backup_root="$XDG_STATE_HOME/quota-glance/backups"
fi
package_target="$data_root/plasma/plasmoids/io.github.geequlim.quotaglance"
timestamp="$(date +%Y%m%d-%H%M%S)"

if [[ ! -f "$package_source/metadata.json" ]]; then
    printf 'Plasma package not found: %s\n' "$package_source" >&2
    exit 1
fi

if [[ -d "$package_target" ]]; then
    backup_path="$backup_root/$timestamp-before-plasma-update"
    mkdir -p "$backup_root"
    cp -a "$package_target" "$backup_path"
    printf 'Saved previous Plasma widget to %s\n' "$backup_path"
fi

mkdir -p "$package_target"
cp -a "$package_source/." "$package_target/"
chmod 755 "$package_target/contents/code/fetch.py"

if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null
fi

printf 'Installed Quota Glance Plasma widget to %s\n' "$package_target"
