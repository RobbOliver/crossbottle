# openbottle

A small, dependency-free Wine bottle manager and launcher for macOS, written in Python (3.9+).
It runs Windows programs (including the current Steam client) on Apple Silicon using open-source
Wine and DXVK builds.

Clean-room project: written from observed, documented behavior only. It contains no code from, and is
not affiliated with, CodeWeavers/CrossOver, Valve or the Wine project. Steam is a trademark of Valve.

A bottle is a directory: `bottle.json` (name, UUID, Windows version, Wine path, env, DLL overrides,
per-program flags, graphics backend) and `prefix/` (the Wine prefix).

## Quick start (macOS on Apple Silicon)

Requirements: macOS 14+, Rosetta 2 (`softwareupdate --install-rosetta`), Python 3.9+.

```bash
git clone https://github.com/RobbOliver/openbottle && cd openbottle
pip3 install --user -e .        # or: export PYTHONPATH=src and use `python3 -m openbottle`

# 1. Wine: Gcenx's macOS builds (Homebrew's wine casks were disabled in 2026-09)
mkdir -p ~/Library/Application\ Support/OpenBottle/Wine && cd ~/Library/Application\ Support/OpenBottle/Wine
curl -fLO https://github.com/Gcenx/macOS_Wine_builds/releases/download/11.18/wine-devel-11.18-osx64.tar.xz
tar -xf wine-devel-11.18-osx64.tar.xz && rm wine-devel-11.18-osx64.tar.xz
WINE="$PWD/Wine Devel.app/Contents/Resources/wine/bin/wine"

# 2. DXVK-macOS (optional, for Direct3D 10/11 games)
mkdir -p ../Runtimes && cd ../Runtimes
curl -fL https://github.com/Gcenx/DXVK-macOS/releases/download/v1.10.3-20230507/dxvk-macOS-async-v1.10.3-20230507.tar.gz | tar -xz
mv dxvk-macOS-async-v1.10.3-20230507 dxvk-macos-1.10.3

# 3. A bottle with Steam (download SteamSetup.exe from store.steampowered.com first)
openbottle create Steam --windows win10
openbottle config Steam --wine "$WINE"
openbottle run Steam ~/Downloads/SteamSetup.exe /S
openbottle args Steam Steam.exe -noverifyfiles -no-cef-sandbox
openbottle cefwrap Steam
openbottle graphics Steam dxvk
openbottle run Steam 'C:\Program Files (x86)\Steam\Steam.exe'

# 4. Optional: a real Mac app, so the Dock shows "Steam" (not "wine")
openbottle shortcut Steam 'C:\Program Files (x86)\Steam\Steam.exe' --app-name Steam
open ~/Applications/OpenBottle/Steam.app
```

These downloads are unsigned third-party builds; macOS may ask you to allow them on first run.
Builds tested: Wine devel 11.18 (Gcenx), DXVK-macOS v1.10.3-20230507, macOS 27, Apple M1.

## Commands

```bash
export PYTHONPATH=src            # or: pip install -e .
python3 -m openbottle create Games --windows win11
python3 -m openbottle list
python3 -m openbottle run Games 'C:\path\setup.exe'      # needs Wine (OPENBOTTLE_WINE or --wine)
python3 -m openbottle run --dry-run Games app.exe        # show command + env only
python3 -m openbottle export Games ~/Games                # -> Games.obarchive (tar.gz)
python3 -m openbottle import ~/Games.obarchive --name Games2
python3 -m openbottle copy Games Games-test
python3 -m openbottle delete Games-test --yes
```

Bottles live in `~/Library/Application Support/OpenBottle/Bottles` (override with `--root` or `OPENBOTTLE_ROOT`).
Import rejects path traversal, hard links, devices and unsafe symlinks, and assigns a fresh UUID.

Tests: `python3 -m unittest discover -s tests`

## Per-bottle settings

```bash
python3 -m openbottle config Games --wine "/path/to/wine" --env DXVK_HUD=1 --dll-overrides "d3d11=n"
python3 -m openbottle args Games Steam.exe -noverifyfiles -no-cef-sandbox   # default flags for Steam.exe
python3 -m openbottle args Games                                              # list
python3 -m openbottle args --clear Games steam.exe
```

`run` uses, in order: `--wine`, the bottle's `wine`, `OPENBOTTLE_WINE`, then `wine64`/`wine` on PATH.
Default program flags (matched by executable basename) come before the arguments passed to `run`.

## Steam (tested 2026-10-16, Wine devel 11.18, Apple Silicon)

- Wine 7.7 (GPTK 1.1) is too old: the current client crashes after self-update.
- On Wine 11 the Steam window is black: CEF 126's GPU path does not present on winemac.
- Fix: `openbottle cefwrap NAME` replaces each `steamwebhelper.exe` with a small wrapper
  (`tools/cefwrap/cefwrap.c`, bundled as `src/openbottle/data/cefwrap.exe`) that relaunches
  `steamwebhelper_real.exe` with `--disable-gpu --disable-gpu-compositing --single-process --no-sandbox`.
  The bottle remembers this, and `run` re-applies it if a Steam update restored Valve's helper.
  `--status` shows the state, `--remove` restores the original.

```bash
python3 -m openbottle create Steam --windows win10
python3 -m openbottle config Steam --wine "$HOME/Library/Application Support/OpenBottle/Wine/Wine Devel.app/Contents/Resources/wine/bin/wine"
python3 -m openbottle run Steam ~/Downloads/SteamSetup.exe /S
python3 -m openbottle args Steam Steam.exe -noverifyfiles -no-cef-sandbox
python3 -m openbottle cefwrap Steam
python3 -m openbottle run Steam 'C:\Program Files (x86)\Steam\Steam.exe'
```

Rebuild the wrapper: `x86_64-w64-mingw32-gcc -municode -mwindows -O2 -s -o src/openbottle/data/cefwrap.exe tools/cefwrap/cefwrap.c`

## App shortcuts (Dock name and icon)

Without a shortcut, every Windows program shows up in the Dock and menu bar as **wine**.

```bash
openbottle shortcut Games 'C:\Games\Game.exe' --app-name "My Game"   # -> ~/Applications/OpenBottle/My Game.app
openbottle shortcut --replace Games 'C:\Games\Game.exe' --app-name "My Game"   # rebuild (e.g. after a Wine update)
```

macOS names a process after the bundle whose *main executable* it runs. The shortcut holds an inner
bundle whose main executable is a hard link of Wine's unix loader, next to hard links of Wine's unix
libraries (Wine derives all its paths from the real location of `ntdll.so`). Wine and every process it
starts then run as that app: own name in the Dock and menu bar, icon extracted from the `.exe`.
It costs ~5 MB per app (hard links, plus a copy of openbottle, since apps opened from Finder cannot
read `~/Documents`). Launcher output goes to `~/Library/Logs/OpenBottle/<app>.log`.

Known limits: programs started by the app (e.g. games launched from Steam) also show its name;
each Wine process with windows gets its own Dock icon; rebuild shortcuts after changing Wine.

## Direct3D 10/11 backend

```bash
python3 -m openbottle graphics Games            # show current backend
python3 -m openbottle graphics Games dxvk       # DXVK-macOS (Vulkan via MoltenVK)
python3 -m openbottle graphics Games wined3d    # back to Wine's built-in D3D (restores its DLLs)
```

`dxvk` copies `d3d11`, `d3d10core`, `dxgi` from the runtime (`x64/` → `system32`, `x32/` → `syswow64`),
backs up Wine's files under `<bottle>/openbottle-backup/` and sets `n,b` overrides; other overrides are kept.
Default runtime: `~/Library/Application Support/OpenBottle/Runtimes/dxvk-macos-1.10.3`
(Gcenx/DXVK-macOS v1.10.3-20230507), or `--runtime` / `OPENBOTTLE_DXVK`.

`tools/d3d11test` is a smoke test (clears to a colour, reads the pixel back, presents frames):

| backend | feature level | adapter | result |
|---|---|---|---|
| wined3d (Wine 11.18) | 9_3 | fake "NVIDIA GeForce 6800" | PASS |
| dxvk-macOS 1.10.3 | 11_0 | Apple M1 | PASS |

Build: `x86_64-w64-mingw32-gcc -O2 -s -o d3d11test.exe tools/d3d11test/d3d11test.c -ld3d11 -ldxgi -luuid`

DXMT (D3D11 → Metal, what CrossOver ships) is not usable with the Gcenx Wine builds: their
`winemac.so` exports no `macdrv_*` symbols, which DXMT needs. It requires a Wine built without
`-fvisibility=hidden` for winemac.

## Not done yet
DXMT (needs a custom Wine build), D3D12/D3D9 backends, app recipes, Windows-version registry settings and the GUI are future work.

## Development

```bash
python3 -m unittest discover -s tests
brew install mingw-w64   # only to rebuild the .exe helpers in tools/
```

## License

MIT, see [LICENSE](LICENSE). Wine, DXVK and Steam are separate projects under their own licenses
and are not redistributed here.
