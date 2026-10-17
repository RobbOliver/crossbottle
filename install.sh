#!/bin/bash
# CrossBottle installer: installs the `crossbottle` command and downloads
# open-source Wine (Gcenx macOS builds) and DXVK-macOS.
#   ./install.sh            install / update
set -euo pipefail

WINE_VERSION="11.18"
WINE_URL="https://github.com/Gcenx/macOS_Wine_builds/releases/download/${WINE_VERSION}/wine-devel-${WINE_VERSION}-osx64.tar.xz"
DXVK_TAG="v1.10.3-20230507"
DXVK_URL="https://github.com/Gcenx/DXVK-macOS/releases/download/${DXVK_TAG}/dxvk-macOS-async-${DXVK_TAG}.tar.gz"

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || die "CrossBottle runs on macOS only."
if [ "$(uname -m)" = arm64 ] && ! /usr/bin/arch -x86_64 /usr/bin/true 2>/dev/null; then
  die "Rosetta 2 is required. Install it with: softwareupdate --install-rosetta --agree-to-license"
fi
command -v python3 >/dev/null || die "python3 not found. Install it with: xcode-select --install"

SUPPORT="$HOME/Library/Application Support"
DATA="$SUPPORT/CrossBottle"
if [ -d "$SUPPORT/OpenBottle" ] && [ ! -e "$DATA" ]; then DATA="$SUPPORT/OpenBottle"; fi
mkdir -p "$DATA/Wine" "$DATA/Runtimes"

say "Installing the crossbottle command"
VENV="$DATA/python"
[ -x "$VENV/bin/python3" ] || python3 -m venv "$VENV"
"$VENV/bin/python3" -m pip install --quiet --upgrade pip
"$VENV/bin/python3" -m pip install --quiet --upgrade "$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.local/bin"
ln -sf "$VENV/bin/crossbottle" "$HOME/.local/bin/crossbottle"

if ls "$DATA/Wine/"*.app/Contents/Resources/wine/bin/wine >/dev/null 2>&1; then
  say "Wine already installed"
else
  say "Downloading Wine ${WINE_VERSION} (~190 MB)"
  curl -fL --progress-bar "$WINE_URL" | tar -xJ -C "$DATA/Wine"
  xattr -dr com.apple.quarantine "$DATA/Wine" 2>/dev/null || true
fi

if [ -f "$DATA/Runtimes/dxvk-macos-1.10.3/x64/d3d11.dll" ]; then
  say "DXVK already installed"
else
  say "Downloading DXVK-macOS (~7 MB)"
  tmp="$(mktemp -d)"
  curl -fL --progress-bar "$DXVK_URL" | tar -xz -C "$tmp"
  rm -rf "$DATA/Runtimes/dxvk-macos-1.10.3"
  mv "$tmp/dxvk-macOS-async-${DXVK_TAG}" "$DATA/Runtimes/dxvk-macos-1.10.3"
  rm -rf "$tmp"
fi

say "Done"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "Add the command to your PATH (then open a new terminal):"
     echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc" ;;
esac
echo "Next: crossbottle install-steam --open"
