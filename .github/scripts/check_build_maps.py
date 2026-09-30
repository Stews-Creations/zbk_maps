"""Regression checks for pinned component inputs; uses disposable local Git repos."""

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from build_maps import REPOSITORIES, verify_revisions, copy_safe, verify_archive, write_resourcepack


class RevisionVerificationTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / ".codex"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="build-tests-", dir=scratch)
        self.root = Path(self.temporary.name).resolve()
        assert self.root.is_relative_to(scratch.resolve())
        self.addCleanup(self.temporary.cleanup)
        self.manifest = {
            "id": "test", "repositories": {},
            "datapacks": ["core"], "resourcepacks": ["core"],
        }
        for repository in REPOSITORIES:
            source = self.root / REPOSITORIES[repository]
            source.mkdir()
            self.git(source, "init", "--quiet")
            inputs = [
                "core/pack.mcmeta", "core/LICENSES/NOTICE",
                "core/data/test.json" if repository == "datapacks" else "core/assets/test.json",
            ]
            for name in [*inputs, "README.md", ".gitignore"]:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("*.tmp\noutput/\n" if name == ".gitignore" else "{}\n")
            self.git(source, "add", ".")
            self.git(source, "-c", "user.name=Build test", "-c", "user.email=test@example.invalid",
                     "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Fixture")
            self.manifest["repositories"][repository] = self.git(source, "rev-parse", "HEAD").strip()

    def git(self, source, *args):
        # All mutations belong to isolated fixture repositories, never the workspace.
        source = source.resolve()
        assert source.parent == self.root and source.is_dir()
        if args[0] != "init":
            actual = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=source, text=True)
            assert Path(actual.strip()).resolve() == source
        return subprocess.check_output(["git", *args], cwd=source, text=True, stderr=subprocess.STDOUT)

    def verify(self):
        verify_revisions(self.manifest, self.root)

    def test_clean_inputs_and_unrelated_edits_pass(self):
        self.verify()
        source = self.root / "datapacks"
        (source / "README.md").write_text("changed\n")
        (source / "output").mkdir()
        (source / "output/pack.tmp").write_text("output")
        (source / "other-pack").mkdir()
        (source / "other-pack/local.json").write_text("{}")
        self.verify()

    def test_wrong_revision_fails(self):
        self.manifest["repositories"]["datapacks"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "requires"):
            self.verify()

    def test_modified_and_staged_runtime_fail(self):
        source = self.root / "datapacks"
        (source / "core/data/test.json").write_text('{"changed": true}\n')
        with self.assertRaisesRegex(ValueError, "unpublished runtime"):
            self.verify()
        self.git(source, "add", "core/data/test.json")
        with self.assertRaisesRegex(ValueError, "unpublished runtime"):
            self.verify()

    def test_deleted_license_fails(self):
        (self.root / "datapacks/core/LICENSES/NOTICE").unlink()
        with self.assertRaisesRegex(ValueError, "datapacks has unpublished runtime"):
            self.verify()

    def test_untracked_asset_fails(self):
        (self.root / "resourcepacks/core/assets/new.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "resourcepacks has unpublished runtime"):
            self.verify()

    def test_ignored_runtime_file_fails(self):
        (self.root / "datapacks/core/data/local.tmp").write_text("local")
        with self.assertRaisesRegex(ValueError, "unpublished runtime"):
            self.verify()

    def test_ignored_runtime_directory_fails(self):
        directory = self.root / "resourcepacks/core/assets/output"
        directory.mkdir()
        (directory / "local.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "unpublished runtime"):
            self.verify()

    def test_unpublished_bundled_template_fails(self):
        template = self.root / "datapacks/core/data/zbk/structure/barriers/barrier.nbt"
        template.parent.mkdir(parents=True)
        template.write_bytes(b"changed template")
        with self.assertRaisesRegex(ValueError, "datapacks has unpublished runtime"):
            self.verify()

    def test_old_world_templates_excluded_map_templates_preserved(self):
        source = self.root / "world/generated"
        for folder in ("structure", "structures"):
            old = source / "minecraft" / folder / "zbk/barriers/barrier.nbt"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"stale override")
        custom = source / "custom/structure/room.nbt"
        custom.parent.mkdir(parents=True)
        custom.write_bytes(b"map-owned template")
        destination = self.root / "stage/generated"
        copy_safe(source, destination, skip_shared_structures=True)
        self.assertFalse((destination / "minecraft/structure/zbk").exists())
        self.assertFalse((destination / "minecraft/structures/zbk").exists())
        self.assertEqual((destination / "custom/structure/room.nbt").read_bytes(),
                         b"map-owned template")


    def archive(self, *extra, metadata="{}"):
        pack = io.BytesIO()
        with ZipFile(pack, "w") as resourcepack:
            resourcepack.writestr("pack.mcmeta", metadata)
            resourcepack.writestr("assets/zbk/test.json", "{}")
        path = self.root / "world.zip"
        with ZipFile(path, "w") as archive:
            archive.writestr("World/resourcepacks/resources.zip", pack.getvalue())
            for name in ("level.dat", "LICENSES/maps/LICENSE.md",
                         "LICENSES/datapacks/zombies_build_kit/NOTICE",
                         "datapacks/zombies_build_kit/pack.mcmeta",
                         "datapacks/zombies_build_kit/data/zbk/structure/barriers/barrier.nbt",
                         "datapacks/zombies_build_kit/data/zbk/structure/pack_a_punch/pack_a_punch.nbt",
                         *extra):
                archive.writestr("World/" + name, "{}")
        return path

    def test_datapack_players_folder_allowed_world_players_rejected(self):
        manifest = {"world": "World", "datapacks": ["zombies_build_kit"]}
        verify_archive(self.archive(
            "datapacks/zombies_build_kit/data/zbk/function/game/spawn_points/players/assign.mcfunction"),
            manifest)
        with self.assertRaisesRegex(ValueError, "Local-only archive entries"):
            verify_archive(self.archive("players/data/player.dat"), manifest)

    def test_bundled_pack_version_is_stamped(self):
        metadata = self.root / "resourcepacks/core/pack.mcmeta"
        metadata.write_text('{"pack": {"description": "Core v${version}"}, "zbk": {"version": "${version}"}}\n')
        destination = self.root / "stage/resources.zip"
        write_resourcepack(self.manifest, self.root, destination, version="1.2.3")
        with ZipFile(destination) as archive:
            stamped = json.loads(archive.read("pack.mcmeta"))
        self.assertEqual(stamped["zbk"]["version"], "1.2.3")
        self.assertEqual(stamped["pack"]["description"], "Core v1.2.3")
        manifest = {"world": "World", "datapacks": ["zombies_build_kit"]}
        with self.assertRaisesRegex(ValueError, "not stamped"):
            verify_archive(self.archive(metadata='{"zbk": {"version": "${version}"}}'), manifest)


if __name__ == "__main__":
    unittest.main()
