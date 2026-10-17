# CrossBottle: free CrossOver alternative for Mac

**Run Steam and Windows games and apps on macOS (Apple Silicon M1, M2, M3, M4), free and open source.**

[Português (Brasil)](README.pt-BR.md) · [Quick start](#quick-start) · [Commands](#commands) · [How it works](#how-it-works) · [FAQ](#faq)

CrossBottle is a small, free Wine bottle manager for macOS. It installs open-source Wine and DXVK,
keeps each Windows program in its own "bottle", and creates real Mac apps for them, so **Steam
shows up as "Steam" in the Dock**, with its own icon, instead of "wine".

- **One command for Steam**: `crossbottle install-steam`, including the fix for the black Steam window on Wine 11.
- **Direct3D 11 games** through DXVK on Metal (MoltenVK): feature level 11_0 on the real Apple GPU.
- **Mac apps per program**: own name, icon and Dock entry.
- **Bottles**: create, copy, back up and restore Windows environments.
- No dependencies besides Python 3, MIT licensed, tested on macOS 27 with an Apple M1.

> CrossBottle is an independent project. It is **not affiliated with CodeWeavers or CrossOver®**, Valve,
> or the Wine project; those names are used only to describe compatibility. If CrossOver works for you,
> consider supporting CodeWeavers: they fund much of Wine's development.

## Quick start

You need a Mac with macOS 14 or later. Open **Terminal** and paste one line at a time:

```bash
softwareupdate --install-rosetta --agree-to-license      # Apple Silicon only, once
git clone https://github.com/RobbOliver/crossbottle.git
cd crossbottle && ./install.sh                            # installs crossbottle + Wine + DXVK
crossbottle install-steam --open                          # installs Steam and opens it
```

That's all. Next time, open **Steam** from `~/Applications/CrossBottle` (or Launchpad/Spotlight),
or drag it to the Dock. Games you install in Steam live inside the same bottle.

If the terminal says `crossbottle: command not found`, run the `export PATH` line printed by
`install.sh` and open a new Terminal window.

### Any other Windows program

```bash
crossbottle create MyApp                                   # a new bottle (Windows 10)
crossbottle run MyApp ~/Downloads/setup.exe                # run the installer
crossbottle shortcut MyApp 'C:\Program Files\MyApp\MyApp.exe' --app-name "MyApp"
open ~/Applications/CrossBottle/MyApp.app
```

## Recommended upgrade: CrossOver's open-source Wine + DXMT

CodeWeavers publishes the Wine used by CrossOver under the LGPL. Built from those sources, Wine's mac
driver exports `macdrv_functions`, so [DXMT](https://github.com/3Shain/dxmt) (Direct3D 10/11 → Metal,
what CrossOver uses) works, and its mac-driver patches make Steam's interface far lighter:

| Steam web UI (software rendering), M1 8 GB | Gcenx Wine 11.18 | CrossOver Wine 26.3 (open source) |
|---|---|---|
| web helper CPU with the store open | ~90–100% | ~25% |

```bash
tools/build-crossover-wine.sh        # ~1 hour: downloads sources, builds Wine x86_64, adds DXMT
crossbottle config Steam --wine "$HOME/Library/Application Support/CrossBottle/Wine/CrossOver-Wine-26.3/bin/wine"
crossbottle graphics Steam dxmt      # Direct3D 10/11 games on Metal
crossbottle shortcut --replace Steam 'C:\Program Files (x86)\Steam\Steam.exe' --app-name Steam
```

After switching Wine, Steam may ask to reinstall its service ("Steam Service Error"): click
*Install service*; it is installed inside the bottle. GPU rendering of Steam's UI through DXMT also works
on this Wine (`CROSSBOTTLE_CEF_FLAGS="--no-sandbox --single-process"`), but it used more CPU and memory
than software rendering in our test, so software stays the default.

## Commands

| Command | What it does |
|---|---|
| `crossbottle install-steam [--open]` | Bottle + Steam + black-window fix + DXVK + `Steam.app` |
| `crossbottle create NAME [--windows win10\|win11\|win7]` | New bottle |
| `crossbottle list` / `info NAME` | Show bottles |
| `crossbottle run NAME PROGRAM [ARGS...]` | Run a `.exe`, `.msi` or `.bat` (`--dry-run` prints the command) |
| `crossbottle shortcut NAME PROGRAM --app-name "Name"` | Mac app with its own Dock name and icon (`--replace` to rebuild) |
| `crossbottle graphics NAME [dxmt\|dxvk\|wined3d]` | Direct3D 10/11 backend (`dxmt` needs the CrossOver-source Wine) |
| `crossbottle drive NAME E: /Volumes/Disk` | Map a drive letter to a Mac folder or external disk (`--remove`) |
| `crossbottle config NAME --wine PATH --env K=V --dll-overrides S` | Per-bottle settings |
| `crossbottle args NAME PROGRAM [FLAGS...]` | Default flags for a program |
| `crossbottle cefwrap NAME [--status\|--remove]` | Steam web helper fix |
| `crossbottle export NAME FILE` / `import FILE` | Back up / restore a bottle (`.cbarchive`) |
| `crossbottle copy SRC DST` / `delete NAME` / `uuid NAME` | Manage bottles |

Data lives in `~/Library/Application Support/CrossBottle` (`Bottles/`, `Wine/`, `Runtimes/`), apps in
`~/Applications/CrossBottle`, logs in `~/Library/Logs/CrossBottle`. Environment overrides:
`CROSSBOTTLE_ROOT`, `CROSSBOTTLE_WINE`, `CROSSBOTTLE_DXVK`.

## How it works

**Wine.** `install.sh` downloads Gcenx's macOS Wine build (devel 11.18), since Homebrew's Wine casks
were disabled in September 2026 for failing Gatekeeper checks. Wine 7.7 (Game Porting Toolkit 1.1,
Whisky) is too old for the current Steam client, which crashes after its self-update.

**Steam's black window.** On Wine 11, Steam's embedded Chromium (CEF 126) draws a black window, and
Steam's own `-cef-disable-gpu` flags don't help. `crossbottle cefwrap` replaces `steamwebhelper.exe`
with a tiny wrapper ([tools/cefwrap/cefwrap.c](tools/cefwrap/cefwrap.c)) that starts the real helper
with `--disable-gpu --disable-gpu-compositing --single-process`. If a Steam update restores Valve's
file, `crossbottle run` re-applies the wrapper. The switches can be changed per bottle with
`crossbottle config Steam --env CROSSBOTTLE_CEF_FLAGS="..."`. GPU rendering (`--no-sandbox` only) was
tested on Wine 11.18 with DXVK and does not work: ANGLE fails with `SwapChain11 ... EGL_BAD_ALLOC` and
the web helper crashes; ANGLE on OpenGL loops on "Failed to create GLES3 context" at ~150% CPU.
ANGLE on **Vulkan** starts and draws through MoltenVK, but the store's content area stays black for
minutes (in an A/B test on an M1 it was still black 75 s after the page had loaded, while software mode
showed it). Software rendering stays the default and is the recommended setting. Idea credit:
[steam-on-m1-wine](https://github.com/notpop/steam-on-m1-wine).

**Direct3D.** Wine's built-in D3D reports a fake "GeForce 6800" at feature level 9_3 on macOS.
`crossbottle graphics NAME dxvk` installs DXVK-macOS (Vulkan → MoltenVK → Metal): feature level 11_0
on the real GPU. Check it with [tools/d3d11test](tools/d3d11test/d3d11test.c). DXMT (D3D11 → Metal, as
used by CrossOver) needs a Wine whose `winemac.so` exports `macdrv_*` symbols, which Gcenx builds don't.

**Dock name and icon.** macOS names a process after the bundle whose *main executable* it runs; Wine's
loader has an embedded Info.plist saying "Wine". A CrossBottle app contains an inner bundle whose main
executable is a hard link of Wine's unix loader, next to hard links of its libraries (Wine computes
every path from the real location of `ntdll.so`). Wine and every process it starts then run as that
app. Both bundles are marked `LSUIElement` (as Wine's own Info.plist is), so only processes that show a
window get a Dock icon: one Steam icon, not one per helper process. Vulkan ICD manifests are rewritten
with absolute paths so MoltenVK still loads. ~5 MB per app.

## FAQ

**Is this a CrossOver crack or copy?** No. It contains no CrossOver code. It is a small manager built
on public open-source projects (Wine, DXVK, MoltenVK), written from scratch.

**Which games work?** Many DirectX 9/10/11 games that run on Wine. DirectX 12 games, and games with
kernel anti-cheat (Valorant, many online shooters), do not work. Results vary by game.

**Intel Mac?** Not tested. The Wine build supports x86_64; DXVK on Intel GPUs may be limited.

**Install Steam games on an external disk.** `crossbottle drive Steam E: /Volumes/YourDisk`, restart
Steam, then Steam → Settings → Storage → Add Drive → `E:`. The command also marks the drive as a fixed
disk in Wine; without that, Steam reports the library as "not mounted" and Add Drive does nothing.

**Steam's interface is slow.** It is drawn by the CPU (GPU paths were tested; see above) and runs
through Rosetta. The store page alone keeps the UI near 100% of one core (animated capsules, trailers);
starting Steam in the Library and turning off store video autoplay helps. A running game download also slows the store a lot. In Steam,
turn on Settings → Library → *Low Performance Mode*, turn off Settings → Interface → *Smooth scrolling*,
or use View → *Small Mode*. Close other heavy apps on 8 GB Macs. Games are not affected: they use the GPU.

**Steam updated and the window is black again.** Open Steam through its CrossBottle app (it re-applies
the fix automatically) or run `crossbottle cefwrap Steam`.

**Uninstall.** Delete `~/Applications/CrossBottle`, `~/Library/Application Support/CrossBottle`,
`~/Library/Logs/CrossBottle` and `~/.local/bin/crossbottle`.

## Development

```bash
python3 -m unittest discover -s tests       # no Wine needed
brew install mingw-w64                      # only to rebuild the .exe helpers in tools/
x86_64-w64-mingw32-gcc -municode -mwindows -O2 -s -o src/crossbottle/data/cefwrap.exe tools/cefwrap/cefwrap.c
```

Contributions and test reports (game, Mac model, macOS version) are welcome in Issues.

## License

MIT, see [LICENSE](LICENSE). Wine (LGPL), DXVK (zlib), MoltenVK (Apache 2.0) and Steam are separate
projects under their own licenses and are downloaded from their sources, not redistributed here.

*Keywords: CrossOver alternative, free CrossOver, CrossOver free alternative Mac, run Windows apps on Mac,
Steam on Mac M1, Windows games on Mac, Wine for macOS, Whisky alternative, Game Porting Toolkit, DXVK macOS.*
