"""crossbottle command line."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import archive, cefwrap, graphics, launcher, recipes, shortcut
from .bottle import BottleError, Store, WINDOWS_VERSIONS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crossbottle", description="Manage Wine bottles and run Windows programs.")
    p.add_argument("--root", help="bottle directory (default: $CROSSBOTTLE_ROOT or ~/Library/Application Support/CrossBottle/Bottles)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="create a bottle")
    c.add_argument("name")
    c.add_argument("--windows", default="win10", choices=WINDOWS_VERSIONS)
    c.add_argument("--arch", default="win64", choices=("win32", "win64"))
    c.add_argument("--description", default="")

    sub.add_parser("list", help="list bottles")

    i = sub.add_parser("info", help="show bottle metadata")
    i.add_argument("name")

    cp = sub.add_parser("copy", help="copy a bottle")
    cp.add_argument("source")
    cp.add_argument("target")

    d = sub.add_parser("delete", help="delete a bottle")
    d.add_argument("name")
    d.add_argument("--yes", action="store_true", help="skip confirmation")

    u = sub.add_parser("uuid", help="get or change the bottle UUID")
    u.add_argument("name")
    u.add_argument("--new", action="store_true")
    u.add_argument("--set")

    e = sub.add_parser("export", help="export a bottle to .cbarchive")
    e.add_argument("name")
    e.add_argument("dest")

    im = sub.add_parser("import", help="import a .cbarchive")
    im.add_argument("archive")
    im.add_argument("--name", default="")

    cf = sub.add_parser("config", help="change bottle settings")
    cf.add_argument("name")
    cf.add_argument("--wine", help="Wine binary for this bottle")
    cf.add_argument("--clear-wine", action="store_true", help="auto-detect Wine again")
    cf.add_argument("--dll-overrides", help="WINEDLLOVERRIDES value ('' to clear)")
    cf.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    cf.add_argument("--unset-env", action="append", default=[], metavar="KEY")

    a = sub.add_parser("args", help="show or set default arguments for a program")
    a.add_argument("--clear", action="store_true")
    a.add_argument("name")
    a.add_argument("program", nargs="?")
    a.add_argument("args", nargs=argparse.REMAINDER)

    w = sub.add_parser("cefwrap", help="wrap Steam's steamwebhelper.exe (CEF without GPU)")
    w.add_argument("name")
    g = w.add_mutually_exclusive_group()
    g.add_argument("--remove", action="store_true", help="restore the original helper")
    g.add_argument("--status", action="store_true")
    w.add_argument("--wrapper", help="wrapper .exe (default: bundled)")

    gx = sub.add_parser("graphics", help="show or choose the Direct3D 10/11 backend")
    gx.add_argument("name")
    gx.add_argument("backend", nargs="?", choices=graphics.BACKENDS)
    gx.add_argument("--runtime", help="DXVK runtime directory (with x64/ and x32/)")

    sc = sub.add_parser("shortcut", help="create a macOS .app for a program (own Dock name and icon)")
    sc.add_argument("name")
    sc.add_argument("program", help="program to run, e.g. 'C:\\Program Files\\App\\App.exe'")
    sc.add_argument("--app-name", required=True, help="name shown in the Dock and Finder")
    sc.add_argument("--dest", help="folder for the .app (default: ~/Applications/CrossBottle)")
    sc.add_argument("--wine", help="Wine to embed (default: the bottle's)")
    sc.add_argument("--replace", action="store_true", help="rebuild an existing CrossBottle .app")

    st = sub.add_parser("install-steam", help="one command: bottle + Steam + fixes + Dock app")
    st.add_argument("--name", default="Steam", help="bottle name (default: Steam)")
    st.add_argument("--installer", help="use this SteamSetup.exe instead of downloading it")
    st.add_argument("--wine", help="Wine binary (default: the one from install.sh)")
    st.add_argument("--no-app", action="store_true", help="do not create ~/Applications/CrossBottle/Steam.app")
    st.add_argument("--open", action="store_true", help="open Steam when done")

    r = sub.add_parser("run", help="run a Windows program in a bottle")
    r.add_argument("name")
    r.add_argument("program")
    r.add_argument("args", nargs=argparse.REMAINDER)
    r.add_argument("--wine")
    r.add_argument("--workdir")
    r.add_argument("--dry-run", action="store_true", help="print the command and environment, do not run")
    r.add_argument("--exec", dest="exec_", action="store_true", help="replace this process with Wine")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(Path(args.root) if args.root else None)
    try:
        return _dispatch(args, store)
    except BottleError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


def _dispatch(args, store: Store) -> int:
    if args.cmd == "create":
        b = store.create(args.name, args.windows, args.arch, args.description)
        print("created %s (%s)" % (b.name, b.meta.uuid))
    elif args.cmd == "list":
        for b in store.list():
            print("%s\t%s\t%s" % (b.name, b.meta.windows_version, b.meta.uuid))
    elif args.cmd == "info":
        b = store.get(args.name)
        for k, v in sorted(vars(b.meta).items()):
            print("%s: %s" % (k, v))
        print("path: %s" % b.path)
    elif args.cmd == "copy":
        store.copy(args.source, args.target)
        print("copied %s -> %s" % (args.source, args.target))
    elif args.cmd == "delete":
        if not args.yes:
            if input("Delete bottle %r and everything in it? [y/N] " % args.name).lower() != "y":
                print("cancelled")
                return 1
        store.delete(args.name)
        print("deleted %s" % args.name)
    elif args.cmd == "uuid":
        if args.new or args.set:
            print(store.set_uuid(args.name, args.set))
        else:
            print(store.get(args.name).meta.uuid)
    elif args.cmd == "export":
        print(archive.export_bottle(store, args.name, Path(args.dest)))
    elif args.cmd == "import":
        print("imported %s" % archive.import_bottle(store, Path(args.archive), args.name))
    elif args.cmd == "config":
        _config(args, store)
    elif args.cmd == "args":
        _args(args, store)
    elif args.cmd == "cefwrap":
        bottle = store.get(args.name)
        wrapper = Path(args.wrapper) if args.wrapper else None
        if args.status:
            for helper in cefwrap.find_helpers(bottle):
                print("%s: %s" % (helper, cefwrap.status(helper, wrapper or cefwrap.WRAPPER)))
            print("keep applied: %s" % bottle.meta.cefwrap)
            return 0
        results = cefwrap.remove(bottle, wrapper) if args.remove else cefwrap.apply(bottle, wrapper)
        for helper, what in results:
            print("%s: %s" % (helper, what))
        bottle.meta.cefwrap = not args.remove
        bottle.save()
    elif args.cmd == "graphics":
        bottle = store.get(args.name)
        if args.backend:
            for line in graphics.apply(bottle, args.backend, Path(args.runtime) if args.runtime else None):
                print(line)
        print("backend: %s" % graphics.current(bottle))
        if bottle.meta.graphics_runtime:
            print("runtime: %s" % bottle.meta.graphics_runtime)
        print("dll_overrides: %s" % (bottle.meta.dll_overrides or "(none)"))
    elif args.cmd == "shortcut":
        bottle = store.get(args.name)
        app = shortcut.create(store, bottle, args.program, args.app_name,
                              Path(args.dest).expanduser() if args.dest else None, args.wine, args.replace)
        print(app)
    elif args.cmd == "install-steam":
        app = recipes.install_steam(store, args.name, Path(args.installer) if args.installer else None,
                                    args.wine, not args.no_app)
        print("Done. Open Steam from %s" % (app or "`crossbottle run %s '%s'`" % (args.name, recipes.STEAM_EXE)))
        if args.open and app:
            import subprocess
            subprocess.run(["open", str(app)])
    elif args.cmd == "run":
        bottle = store.get(args.name)
        if bottle.meta.cefwrap and not args.dry_run and cefwrap.find_helpers(bottle):
            for helper, what in cefwrap.apply(bottle):
                if what != "already wrapped":
                    print("cefwrap: %s: %s" % (helper, what), file=sys.stderr)
        if args.dry_run:
            try:
                wine = launcher.find_wine(args.wine, bottle)
            except BottleError:
                wine = args.wine or bottle.meta.wine or "wine"
            full = launcher.default_args(bottle, args.program) + args.args
            print(" ".join(launcher.build_command(wine, args.program, full, args.workdir)))
            env = launcher.build_env(bottle, {})
            for k in sorted(env):
                print("%s=%s" % (k, env[k]))
            return 0
        return launcher.run(bottle, args.program, args.args, args.wine, args.workdir,
                            replace_process=args.exec_)
    return 0


def _config(args, store: Store) -> None:
    bottle = store.get(args.name)
    meta = bottle.meta
    if args.wine and args.clear_wine:
        raise BottleError("use either --wine or --clear-wine")
    if args.wine:
        meta.wine = launcher.find_wine(args.wine)
    if args.clear_wine:
        meta.wine = ""
    if args.dll_overrides is not None:
        meta.dll_overrides = args.dll_overrides
    env = dict(meta.env or {})
    for item in args.env:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise BottleError("--env expects KEY=VALUE, got %r" % item)
        env[key] = value
    for key in args.unset_env:
        env.pop(key, None)
    meta.env = env or None
    bottle.save()
    print("wine: %s" % (meta.wine or "(auto)"))
    print("dll_overrides: %s" % (meta.dll_overrides or "(none)"))
    for key in sorted(env):
        print("env %s=%s" % (key, env[key]))


def _args(args, store: Store) -> None:
    bottle = store.get(args.name)
    table = dict(bottle.meta.program_args or {})
    if args.program is None:
        if args.clear:
            table = {}
        for key in sorted(table):
            print("%s: %s" % (key, " ".join(table[key])))
    else:
        key = launcher.program_key(args.program)
        if args.clear:
            table.pop(key, None)
        elif args.args:
            table[key] = list(args.args)
        print("%s: %s" % (key, " ".join(table.get(key, []))))
    if args.clear or args.args:
        bottle.meta.program_args = table or None
        bottle.save()


if __name__ == "__main__":
    sys.exit(main())
