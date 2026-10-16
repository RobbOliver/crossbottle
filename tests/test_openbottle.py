import io
import os
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openbottle import archive, cefwrap, graphics, launcher  # noqa: E402
from openbottle.bottle import BottleError, Store  # noqa: E402
from openbottle.cli import main  # noqa: E402


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
        self.assertEqual(out.suffix, ".obarchive")
        name = archive.import_bottle(self.store, out, "restored")
        r = self.store.get(name)
        self.assertEqual((r.prefix / "drive_c" / "x.txt").read_text(), "data")
        self.assertNotEqual(r.meta.uuid, b.meta.uuid)

    def _evil(self, member_name):
        path = self.tmp / "evil.obarchive"
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

        path = self.tmp / "evil2.obarchive"
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
        self.assertEqual(env["OPENBOTTLE_UUID"], b.meta.uuid)

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
        self.wrapper.write_bytes(b"wrapper")

    def test_apply_status_remove(self):
        self.assertEqual(cefwrap.status(self.helper, self.wrapper), "original")
        cefwrap.apply(self.bottle, self.wrapper)
        self.assertEqual(self.helper.read_bytes(), b"wrapper")
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

    def test_errors(self):
        with self.assertRaises(BottleError):
            graphics.apply(self.bottle, "dxvk", self.tmp / "missing")
        with self.assertRaises(BottleError):
            graphics.apply(self.store.create("empty"), "dxvk", self.rt)
        with self.assertRaises(BottleError):
            graphics.apply(self.bottle, "metal")


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
