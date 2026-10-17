import io
import os
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crossbottle import archive, cefwrap, drives, graphics, icons, launcher, shortcut  # noqa: E402
from crossbottle.bottle import BottleError, Store  # noqa: E402
from crossbottle.cli import main  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = Store(self.tmp / "bottles")

    def tearDown(self):
        self._tmp.cleanup()


class StoreTests(Base):
    def test_create_list_get(self):
        b = self.store.create("Games", "win11", description="x")
        self.assertTrue(b.prefix.is_dir())
        self.assertEqual([x.name for x in self.store.list()], ["Games"])
        self.assertEqual(self.store.get("Games").meta.windows_version, "win11")

    def test_rejects_bad_names_and_duplicates(self):
        for bad in ("../x", "a/b", "", ".hidden"):
            with self.assertRaises(BottleError):
                self.store.create(bad)
        self.store.create("a")
        with self.assertRaises(BottleError):
            self.store.create("a")

    def test_copy_gets_new_uuid_and_contents(self):
        a = self.store.create("a")
        (a.prefix / "file.txt").write_text("hi")
        b = self.store.copy("a", "b")
        self.assertNotEqual(a.meta.uuid, b.meta.uuid)
        self.assertEqual((b.prefix / "file.txt").read_text(), "hi")
        self.assertEqual(b.name, "b")

    def test_delete_and_uuid(self):
        self.store.create("a")
        old = self.store.get("a").meta.uuid
        self.assertNotEqual(self.store.set_uuid("a"), old)
        self.store.delete("a")
        self.assertFalse(self.store.exists("a"))


class ArchiveTests(Base):
    def test_roundtrip(self):
        b = self.store.create("a")
        (b.prefix / "drive_c").mkdir()
        (b.prefix / "drive_c" / "x.txt").write_text("data")
        out = archive.export_bottle(self.store, "a", self.tmp / "backup")
        self.assertEqual(out.suffix, ".cbarchive")
        name = archive.import_bottle(self.store, out, "restored")
        r = self.store.get(name)
        self.assertEqual((r.prefix / "drive_c" / "x.txt").read_text(), "data")
        self.assertNotEqual(r.meta.uuid, b.meta.uuid)

    def _evil(self, member_name):
        path = self.tmp / "evil.cbarchive"
        with tarfile.open(path, "w:gz") as tar:
            info = tarfile.TarInfo(member_name)
            data = b"x"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        return path

    def test_rejects_path_traversal(self):
        with self.assertRaises(BottleError):
            archive.import_bottle(self.store, self._evil("../escape.txt"))

    def test_allows_prefix_symlinks_but_not_writes_through_them(self):
        b = self.store.create("a")
        (b.prefix / "drive_c").mkdir()
        (b.prefix / "dosdevices").mkdir()
        os.symlink("../drive_c", b.prefix / "dosdevices" / "c:")
        os.symlink("/", b.prefix / "dosdevices" / "z:")
        out = archive.export_bottle(self.store, "a", self.tmp / "b")
        archive.import_bottle(self.store, out, "b")
        self.assertTrue((self.store.get("b").prefix / "dosdevices" / "c:").is_symlink())

        path = self.tmp / "evil2.cbarchive"
        with tarfile.open(path, "w:gz") as tar:
            meta = tarfile.TarInfo("top/bottle.json"); meta.size = 2
            tar.addfile(meta, io.BytesIO(b"{}"))
            link = tarfile.TarInfo("top/l"); link.type = tarfile.SYMTYPE; link.linkname = "/tmp"
            tar.addfile(link)
            f = tarfile.TarInfo("top/l/pwned"); f.size = 1
            tar.addfile(f, io.BytesIO(b"x"))
        with self.assertRaises(BottleError):
            archive.import_bottle(self.store, path)

    def test_rejects_archive_without_metadata(self):
        with self.assertRaises(BottleError):
            archive.import_bottle(self.store, self._evil("top/file"))


class LauncherTests(Base):
    def test_env(self):
        b = self.store.create("a")
        b.meta.dll_overrides = "d3d11=n"
        b.meta.env = {"FOO": "bar"}
        env = launcher.build_env(b, {})
        self.assertEqual(env["WINEPREFIX"], str(b.prefix))
        self.assertEqual(env["WINEDLLOVERRIDES"], "d3d11=n")
        self.assertEqual(env["FOO"], "bar")
        self.assertEqual(env["CROSSBOTTLE_UUID"], b.meta.uuid)

    def test_command_variants(self):
        self.assertEqual(launcher.build_command("w", "a.exe", ["-x"], None), ["w", "a.exe", "-x"])
        self.assertEqual(launcher.build_command("w", "a.msi", [], None), ["w", "msiexec", "/i", "a.msi"])
        self.assertEqual(launcher.build_command("w", "a.bat", [], None), ["w", "cmd", "/c", "a.bat"])

    def test_run_with_fake_wine(self):
        fake = self.tmp / "fakewine"
        log = self.tmp / "log.txt"
        fake.write_text('#!/bin/sh\necho "$@ prefix=$WINEPREFIX" >> "%s"\n'
                        'if [ "$1" = wineboot ]; then touch "$WINEPREFIX/system.reg"; fi\n' % log)
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        b = self.store.create("a")
        rc = launcher.run(b, "app.exe", ["--go"], wine=str(fake))
        self.assertEqual(rc, 0)
        lines = log.read_text().splitlines()
        self.assertTrue(lines[0].startswith("wineboot --init"))
        self.assertTrue(lines[1].startswith("app.exe --go"))
        self.assertIn(str(b.prefix), lines[1])

    def test_missing_wine(self):
        os.environ.pop("OPENBOTTLE_WINE", None)
        os.environ.pop("CROSSBOTTLE_WINE", None)
        with self.assertRaises(BottleError):
            launcher.find_wine("definitely-not-a-wine-binary")


class BottleSettingsTests(Base):
    def _fake_wine(self):
        fake = self.tmp / "fakewine"
        self.log = self.tmp / "log.txt"
        fake.write_text('#!/bin/sh\necho "$@" >> "%s"\n'
                        'if [ "$1" = wineboot ]; then touch "$WINEPREFIX/system.reg"; fi\n' % self.log)
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def test_program_key(self):
        self.assertEqual(launcher.program_key(r"C:\Program Files (x86)\Steam\Steam.exe"), "steam.exe")
        self.assertEqual(launcher.program_key("/x/y/App.EXE"), "app.exe")

    def test_bottle_wine_and_default_args_are_used(self):
        b = self.store.create("a")
        b.meta.wine = str(self._fake_wine())
        b.meta.program_args = {"steam.exe": ["-noverifyfiles"]}
        b.save()
        b = self.store.get("a")
        self.assertEqual(launcher.run(b, r"C:\Steam\Steam.exe", ["-x"]), 0)
        self.assertEqual(self.log.read_text().splitlines()[-1], r"C:\Steam\Steam.exe -noverifyfiles -x")

    def test_old_metadata_still_loads(self):
        b = self.store.create("a")
        meta = (b.path / "bottle.json")
        import json
        data = json.loads(meta.read_text())
        for k in ("wine", "program_args", "cefwrap"):
            data.pop(k)
        meta.write_text(json.dumps(data))
        self.assertEqual(self.store.get("a").meta.wine, "")


class CefwrapTests(Base):
    def setUp(self):
        super().setUp()
        self.bottle = self.store.create("s")
        self.cef = self.bottle.prefix / "drive_c" / "Program Files (x86)" / "Steam" / "bin" / "cef" / "cef.win64"
        self.cef.mkdir(parents=True)
        self.helper = self.cef / "steamwebhelper.exe"
        self.helper.write_bytes(b"valve-v1")
        self.wrapper = self.tmp / "wrap.exe"
        self.wrapper.write_bytes(b"wrapper CROSSBOTTLE_CEFWRAP_V2")

    def test_apply_status_remove(self):
        self.assertEqual(cefwrap.status(self.helper, self.wrapper), "original")
        cefwrap.apply(self.bottle, self.wrapper)
        self.assertEqual(self.helper.read_bytes(), b"wrapper CROSSBOTTLE_CEFWRAP_V2")
        self.assertEqual((self.cef / "steamwebhelper_real.exe").read_bytes(), b"valve-v1")
        self.assertEqual(cefwrap.apply(self.bottle, self.wrapper)[0][1], "already wrapped")
        cefwrap.remove(self.bottle, self.wrapper)
        self.assertEqual(self.helper.read_bytes(), b"valve-v1")
        self.assertFalse((self.cef / "steamwebhelper_real.exe").exists())

    def test_rewrap_after_steam_update(self):
        cefwrap.apply(self.bottle, self.wrapper)
        self.helper.write_bytes(b"valve-v2")  # Steam update restores its helper
        self.assertEqual(cefwrap.status(self.helper, self.wrapper), "replaced")
        self.assertEqual(cefwrap.apply(self.bottle, self.wrapper)[0][1], "re-wrapped after update")
        self.assertEqual((self.cef / "steamwebhelper_real.exe").read_bytes(), b"valve-v2")

    def test_outdated_wrapper_is_updated_not_treated_as_valve(self):
        cefwrap.apply(self.bottle, self.wrapper)
        self.helper.write_bytes(b"older CROSSBOTTLE_CEFWRAP_V1 build")
        self.assertEqual(cefwrap.status(self.helper, self.wrapper), "outdated")
        self.assertEqual(cefwrap.apply(self.bottle, self.wrapper)[0][1], "wrapper updated")
        self.assertEqual((self.cef / "steamwebhelper_real.exe").read_bytes(), b"valve-v1")
        self.assertEqual(self.helper.read_bytes(), self.wrapper.read_bytes())

    def test_legacy_wrapper_without_marker_is_recognised(self):
        legacy = self.tmp / "legacy.exe"
        legacy.write_bytes(b"legacy")
        import hashlib
        cefwrap.LEGACY_WRAPPERS.add(hashlib.sha256(b"legacy").hexdigest())
        self.assertTrue(cefwrap.is_wrapper(legacy))
        self.assertFalse(cefwrap.is_wrapper(self.helper))

    def test_repairs_swapped_wrapper_and_never_moves_wrapper_to_real(self):
        cefwrap.apply(self.bottle, self.wrapper)
        real = self.cef / "steamwebhelper_real.exe"
        # an older crossbottle moved our wrapper into _real; Steam restored its helper
        real.write_bytes(self.wrapper.read_bytes())
        self.helper.write_bytes(b"valve-v3")
        self.assertEqual(cefwrap.status(self.helper, self.wrapper), "broken")
        cefwrap.apply(self.bottle, self.wrapper)
        self.assertEqual(real.read_bytes(), b"valve-v3")
        self.assertEqual(self.helper.read_bytes(), self.wrapper.read_bytes())
        # both files are wrappers: Valve's helper is gone, refuse instead of guessing
        self.helper.write_bytes(self.wrapper.read_bytes())
        real.write_bytes(self.wrapper.read_bytes())
        with self.assertRaises(BottleError):
            cefwrap.apply(self.bottle, self.wrapper)

    def test_no_steam(self):
        b = self.store.create("empty")
        with self.assertRaises(BottleError):
            cefwrap.apply(b, self.wrapper)

    def test_bundled_wrapper_is_a_pe_file(self):
        self.assertEqual(cefwrap.WRAPPER.read_bytes()[:2], b"MZ")


class GraphicsTests(Base):
    def setUp(self):
        super().setUp()
        self.bottle = self.store.create("g")
        self.win = self.bottle.prefix / "drive_c" / "windows"
        for d in ("system32", "syswow64"):
            (self.win / d).mkdir(parents=True)
            for n in graphics.DXVK_DLLS:
                (self.win / d / (n + ".dll")).write_bytes(b"wine-" + d.encode())
        self.rt = self.tmp / "dxvk"
        for arch in ("x64", "x32"):
            (self.rt / arch).mkdir(parents=True)
            for n in graphics.DXVK_DLLS + ("d3d9",):
                (self.rt / arch / (n + ".dll")).write_bytes(b"dxvk-" + arch.encode())

    def test_overrides_roundtrip(self):
        t = graphics.parse_overrides("dcomp=d; d3d11,dxgi=n,b")
        self.assertEqual(t, {"dcomp": "d", "d3d11": "n,b", "dxgi": "n,b"})
        self.assertEqual(graphics.format_overrides(t), "d3d11=n,b;dcomp=d;dxgi=n,b")
        with self.assertRaises(BottleError):
            graphics.parse_overrides("oops")

    def test_dxvk_then_wined3d_restores_files_and_keeps_other_overrides(self):
        self.bottle.meta.dll_overrides = "dcomp=d"
        graphics.apply(self.bottle, "dxvk", self.rt)
        self.assertEqual((self.win / "system32" / "d3d11.dll").read_bytes(), b"dxvk-x64")
        self.assertEqual((self.win / "syswow64" / "dxgi.dll").read_bytes(), b"dxvk-x32")
        self.assertFalse((self.win / "system32" / "d3d9.dll").exists())
        self.assertEqual(self.bottle.meta.dll_overrides, "d3d10core=n,b;d3d11=n,b;dcomp=d;dxgi=n,b")
        graphics.apply(self.bottle, "dxvk", self.rt)  # re-apply must not back up DXVK files
        graphics.apply(self.bottle, "wined3d")
        self.assertEqual((self.win / "system32" / "d3d11.dll").read_bytes(), b"wine-system32")
        self.assertEqual((self.win / "syswow64" / "dxgi.dll").read_bytes(), b"wine-syswow64")
        self.assertEqual(self.bottle.meta.dll_overrides, "dcomp=d")
        self.assertEqual(self.store.get("g").meta.graphics, "wined3d")

    def _wine(self, with_dxmt):
        root = self.tmp / ("wine-dxmt" if with_dxmt else "wine-plain")
        for d in ("bin", "lib/wine/x86_64-unix", "lib/wine/x86_64-windows", "lib/wine/i386-windows"):
            (root / d).mkdir(parents=True, exist_ok=True)
        (root / "bin" / "wine").write_text("#!/bin/sh\n")
        (root / "bin" / "wine").chmod(0o755)
        (root / "lib/wine/x86_64-unix/wine").write_bytes(b"x")
        if with_dxmt:
            (root / "lib/wine/x86_64-unix/winemetal.so").write_bytes(b"so")
            for arch in ("x86_64-windows", "i386-windows"):
                (root / "lib/wine" / arch / "winemetal.dll").write_bytes(arch.encode())
                (root / "lib/wine" / arch / "d3d11.dll").write_bytes(b"dxmt")
        return root

    def test_dxmt_from_dxvk(self):
        graphics.apply(self.bottle, "dxvk", self.rt)
        self.bottle.meta.wine = str(self._wine(True) / "bin" / "wine")
        log = graphics.apply(self.bottle, "dxmt")
        self.assertEqual((self.win / "system32" / "d3d11.dll").read_bytes(), b"wine-system32")
        self.assertEqual((self.win / "system32" / "winemetal.dll").read_bytes(), b"x86_64-windows")
        self.assertEqual((self.win / "syswow64" / "winemetal.dll").read_bytes(), b"i386-windows")
        self.assertEqual(self.bottle.meta.dll_overrides, "")
        self.assertEqual(self.store.get("g").meta.graphics, "dxmt")
        self.assertTrue(any("winemetal" in line for line in log))

    def test_dxmt_needs_a_dxmt_wine(self):
        self.bottle.meta.wine = str(self._wine(False) / "bin" / "wine")
        with self.assertRaises(BottleError):
            graphics.apply(self.bottle, "dxmt")

    def test_errors(self):
        with self.assertRaises(BottleError):
            graphics.apply(self.bottle, "dxvk", self.tmp / "missing")
        with self.assertRaises(BottleError):
            graphics.apply(self.store.create("empty"), "dxvk", self.rt)
        with self.assertRaises(BottleError):
            graphics.apply(self.bottle, "metal")


class ShortcutTests(Base):
    def _fake_wine_root(self):
        root = self.tmp / "wine"
        unix = root / "lib" / "wine" / "x86_64-unix"
        (unix / "vulkan" / "icd.d").mkdir(parents=True)
        (root / "lib" / "wine" / "x86_64-windows").mkdir()
        (root / "bin").mkdir()
        (root / "share" / "wine").mkdir(parents=True)
        for name in ("wine", "ntdll.so", "win32u.so"):
            (unix / name).write_bytes(b"x")
        (unix / "wine").chmod(0o755)
        (root / "bin" / "wine").write_text("#!/bin/sh\n")
        (root / "bin" / "wine").chmod(0o755)
        (root / "lib" / "libMoltenVK.dylib").write_bytes(b"x")
        (unix / "vulkan" / "icd.d" / "MoltenVK_icd.json").write_text(
            '{"ICD": {"library_path": "../../../../libMoltenVK.dylib"}}')
        return root

    def test_windows_to_unix(self):
        b = self.store.create("w")
        p = shortcut.windows_to_unix(b, r"C:\Program Files\App\App.exe")
        self.assertTrue(str(p).endswith("Program Files/App/App.exe"))
        self.assertIsNone(shortcut.windows_to_unix(b, "relative.exe"))

    def test_create_bundle_layout(self):
        root = self._fake_wine_root()
        b = self.store.create("w")
        b.meta.wine = str(root / "bin" / "wine")
        b.save()
        old = shortcut.LSREGISTER
        shortcut.LSREGISTER = str(self.tmp / "no-lsregister")
        try:
            app = shortcut.create(self.store, b, r"C:\App\App.exe", "My App", self.tmp / "apps")
            with self.assertRaises(BottleError):
                shortcut.create(self.store, b, r"C:\App\App.exe", "My App", self.tmp / "apps")
            shortcut.create(self.store, b, r"C:\App\App.exe", "My App", self.tmp / "apps", replace=True)
        finally:
            shortcut.LSREGISTER = old
        import plistlib
        inner = app / "Contents" / "Resources" / "My App.app"
        macos = inner / "Contents" / "MacOS"
        outer_info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
        inner_info = plistlib.loads((inner / "Contents" / "Info.plist").read_bytes())
        self.assertEqual(outer_info["CFBundleExecutable"], shortcut.LAUNCHER)
        self.assertEqual(inner_info["CFBundleExecutable"], "wine")
        self.assertEqual(inner_info["CFBundleDisplayName"], "My App")
        self.assertTrue(inner_info["LSUIElement"] and outer_info["LSUIElement"])
        unix = root / "lib" / "wine" / "x86_64-unix"
        self.assertEqual((macos / "ntdll.so").stat().st_ino, (unix / "ntdll.so").stat().st_ino)
        self.assertFalse((macos / "ntdll.so").is_symlink())
        self.assertTrue((macos / "x86_64-windows").is_symlink())
        self.assertTrue((macos / "libMoltenVK.dylib").is_symlink())
        self.assertEqual(os.readlink(macos / "x86_64-unix"), ".")
        self.assertTrue((inner / "bin").is_symlink() and (inner / "share").is_symlink())
        import json
        icd = json.loads((macos / "vulkan" / "icd.d" / "MoltenVK_icd.json").read_text())
        self.assertEqual(icd["ICD"]["library_path"], os.path.normpath(str(root.resolve() / "lib" / "libMoltenVK.dylib")))
        script = (app / "Contents" / "MacOS" / shortcut.LAUNCHER).read_text()
        self.assertIn("VK_ICD_FILENAMES", script)
        self.assertIn("run --exec", script)
        self.assertIn("/dosdevices/*:", script)
        self.assertIn("import crossbottle' 2>/dev/null || export PYTHONPATH", script)
        self.assertTrue((app / "Contents" / "Resources" / "python" / "crossbottle" / "cli.py").is_file())

    def test_refuses_foreign_app(self):
        root = self._fake_wine_root()
        b = self.store.create("w")
        b.meta.wine = str(root / "bin" / "wine")
        (self.tmp / "apps" / "Other.app").mkdir(parents=True)
        with self.assertRaises(BottleError):
            shortcut.create(self.store, b, "C:\\x.exe", "Other", self.tmp / "apps", replace=True)

    def test_icon_extraction_without_icon(self):
        self.assertIsNone(icons.extract_ico(cefwrap.WRAPPER))
        with self.assertRaises(icons.IconError):
            notpe = self.tmp / "x.exe"
            notpe.write_bytes(b"hello")
            icons.extract_ico(notpe)


class LegacyPathTests(Base):
    def test_legacy_folders_and_env(self):
        from crossbottle import paths
        old_home = paths.HOME
        paths.HOME = self.tmp
        try:
            support = self.tmp / "Library" / "Application Support"
            self.assertEqual(paths.data_dir(), support / "CrossBottle")
            (support / "OpenBottle").mkdir(parents=True)
            self.assertEqual(paths.data_dir(), support / "OpenBottle")
            (support / "CrossBottle").mkdir()
            self.assertEqual(paths.data_dir(), support / "CrossBottle")
        finally:
            paths.HOME = old_home
        os.environ["OPENBOTTLE_DXVK"] = "/legacy"
        try:
            self.assertEqual(paths.env("DXVK"), "/legacy")
            os.environ["CROSSBOTTLE_DXVK"] = "/new"
            self.assertEqual(paths.env("DXVK"), "/new")
        finally:
            os.environ.pop("OPENBOTTLE_DXVK", None)
            os.environ.pop("CROSSBOTTLE_DXVK", None)

    def test_legacy_graphics_backup_is_restored(self):
        b = self.store.create("g")
        win = b.prefix / "drive_c" / "windows" / "system32"
        win.mkdir(parents=True)
        (win / "d3d11.dll").write_bytes(b"dxvk")
        legacy = b.path / "openbottle-backup" / "graphics" / "system32"
        legacy.mkdir(parents=True)
        (legacy / "d3d11.dll").write_bytes(b"wine")
        b.meta.graphics = "dxvk"
        graphics.apply(b, "wined3d")
        self.assertEqual((win / "d3d11.dll").read_bytes(), b"wine")


class DriveTests(Base):
    def test_add_list_remove(self):
        b = self.store.create("d")
        (b.prefix / "dosdevices").mkdir(parents=True)
        os.symlink("../drive_c", b.prefix / "dosdevices" / "c:")
        disk = self.tmp / "disk"
        disk.mkdir()
        calls = []
        drives.add(b, "E:", disk, lambda k, v: calls.append((k, v)))
        self.assertEqual(calls, [("e:", "hd")])
        self.assertEqual(drives.list_drives(b)["E:"], str(disk))
        with self.assertRaises(BottleError):
            drives.add(b, "e", disk)
        for bad in ("C:", "Z:", "1:", "EE"):
            with self.assertRaises(BottleError):
                drives.add(b, bad, disk)
        with self.assertRaises(BottleError):
            drives.add(b, "F:", self.tmp / "missing")
        drives.remove(b, "E:")
        self.assertNotIn("E:", drives.list_drives(b))


class CliTests(Base):
    def test_config_and_args(self):
        root = ["--root", str(self.tmp / "b")]
        main(root + ["create", "x"])
        self.assertEqual(main(root + ["config", "x", "--env", "A=1", "--dll-overrides", "dcomp=d"]), 0)
        self.assertEqual(main(root + ["args", "x", "Steam.exe", "-noverifyfiles", "-no-cef-sandbox"]), 0)
        meta = Store(self.tmp / "b").get("x").meta
        self.assertEqual(meta.env, {"A": "1"})
        self.assertEqual(meta.program_args, {"steam.exe": ["-noverifyfiles", "-no-cef-sandbox"]})
        self.assertEqual(main(root + ["args", "--clear", "x", "steam.exe"]), 0)
        self.assertIsNone(Store(self.tmp / "b").get("x").meta.program_args)
        self.assertEqual(main(root + ["config", "x", "--wine", "definitely-not-wine"]), 1)


    def test_create_and_list(self):
        root = ["--root", str(self.tmp / "b")]
        self.assertEqual(main(root + ["create", "x"]), 0)
        self.assertEqual(main(root + ["info", "x"]), 0)
        self.assertEqual(main(root + ["run", "--dry-run", "x", "a.exe", "-flag"]), 0)
        self.assertEqual(main(root + ["delete", "x", "--yes"]), 0)
        self.assertEqual(main(root + ["info", "x"]), 1)


if __name__ == "__main__":
    unittest.main()
