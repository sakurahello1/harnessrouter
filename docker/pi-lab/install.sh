#!/usr/bin/env bash
# Pi Lab runtime: immutable Git commit for SoL-Pi; npm lockfile integrity for registry tarballs,
# including the MCP adapter and transitive packages. No floating runtime deps.
set -euo pipefail
target="${1:?usage: install.sh ABSOLUTE_RUNTIME_DIRECTORY}"
case "$target" in /*) ;; *) echo 'Pi Lab runtime path must be absolute'; exit 1 ;; esac
manifest_dir="$(cd "$(dirname "$0")" && pwd)"
digest="$(cat "$manifest_dir/package-lock.json" "$manifest_dir/source.sha256" | sha256sum | cut -d ' ' -f1)"
if [ -x "$target/bin/pi" ] && [ "$(cat "$target/lock.sha256" 2>/dev/null)" = "$digest" ] \
    && [ "$("$target/bin/pi" --version)" = '0.85.1' ] \
    && (cd "$target/node_modules/sol-pi" && sha256sum --check --status "$manifest_dir/source.sha256"); then
  # Session processes use a different uid from the installer. The runtime contains
  # packages only; credentials live in each session's separate agent directory.
  chmod -R a+rX "$target"
  echo 'Pi Lab already installed and source verified'
  exit 0
fi
mkdir -p "$(dirname "$target")"
stage="$(mktemp -d "${target}.stage.XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
cp "$manifest_dir/package.json" "$manifest_dir/package-lock.json" "$stage/"
npm ci --prefix "$stage" --ignore-scripts --no-audit --no-fund
mkdir -p "$stage/bin" "$stage/lib"
ln -s ../node_modules/.bin/pi "$stage/bin/pi"
ln -s ../node_modules "$stage/lib/node_modules"
test -f "$stage/node_modules/sol-pi/src/sol-pi/index.ts"
test -f "$stage/node_modules/pi-mcp-adapter/package.json"
(cd "$stage/node_modules/sol-pi"; sha256sum --check --strict "$manifest_dir/source.sha256")
test "$("$stage/bin/pi" --version)" = '0.85.1'
printf '%s' "$digest" > "$stage/lock.sha256"
# mktemp makes the staging root 0700. Published packages must be readable and
# traversable by the isolated session uid, without granting it write access.
chmod -R a+rX "$stage"
# Preserve an existing installation on failure. Publish only after the executable
# and extension entrypoints have passed validation; backup is intentionally retained.
if [ -e "$target" ]; then
  backup="${target}.previous.$(date +%s).$$"
  mv -- "$target" "$backup"
  if ! mv -- "$stage" "$target"; then mv -- "$backup" "$target"; exit 1; fi
else
  mv -- "$stage" "$target"
fi
echo "Pi Lab installed: Pi 0.85.1 with SoL-Pi, lockfile SHA256 $digest"
