"""Build portable ZBK worlds from map sources and pinned component checkouts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile


WORLD_ROOTS = ("level.dat", "icon.png", "data", "dimensions", "generated")
PACK_ROOTS = ("pack.mcmeta", "pack.png", "assets")
DATAPACK_ROOTS = ("pack.mcmeta", "pack.png", "data")
LICENSE_FILES = ("LICENSE.md", "NOTICE", "MEDIA_PERMISSION.md")
REPOSITORIES = {"datapacks": "datapacks", "resourcepacks": "resourcepacks"}
VERSION_PLACEHOLDER = "${version}"
DEV_VERSION = "0.0.0-dev"


def is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def copy_safe(source: Path, destination: Path, *, skip_shared_structures: bool = False) -> None:
    # Core now owns these templates; omit obsolete world installations.
    # Omit both real directories and junctions at the former installation path.
    if skip_shared_structures and source.parts[-4:] in (
        ("generated", "minecraft", "structure", "zbk"),
        ("generated", "minecraft", "structures", "zbk"),
    ):
        return
    if is_link(source):
        raise ValueError(f"Refusing to package link: {source}")
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir()):
            if child.name in (".git", ".codex", "AGENTS.md"):
                raise ValueError(f"Local-only content in runtime source: {child}")
            copy_safe(child, destination / child.name, skip_shared_structures=skip_shared_structures)
    elif source.is_file():
        if source.suffix in (".mca", ".mcr"):
            with source.open("rb") as stream:
                if stream.read(48).startswith(b"version https://git-lfs.github.com/spec/v1"):
                    raise ValueError(f"Git LFS object was not downloaded: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    else:
        raise ValueError(f"Unsupported runtime entry: {source}")


def checked_child(parent: Path, name: str) -> Path:
    if not name or name in (".", "..") or Path(name).name != name:
        raise ValueError(f"Invalid path component: {name!r}")
    child = parent / name
    if not child.is_dir() or is_link(child):
        raise ValueError(f"Missing or linked source directory: {child}")
    return child


def load_manifests(maps_root: Path) -> list[dict]:
    manifests = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((maps_root / "manifests").glob("*.json"))]
    if not manifests:
        raise ValueError("No map manifests found")
    ids = set()
    worlds = set()
    reference_revisions = manifests[0]["repositories"]
    for manifest in manifests:
        if manifest["id"] in ids or manifest["world"] in worlds:
            raise ValueError("Duplicate map id or world name")
        ids.add(manifest["id"])
        worlds.add(manifest["world"])
        checked_child(maps_root, manifest["world"])
        if manifest["repositories"] != reference_revisions:
            raise ValueError("Current workflow requires the same pinned component revisions for both maps")
        for repository in REPOSITORIES:
            revision = manifest["repositories"][repository]
            if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
                raise ValueError(f"Invalid {repository} commit in {manifest['id']}")
        for group in ("datapacks", "resourcepacks"):
            if not manifest[group] or len(manifest[group]) != len(set(manifest[group])):
                raise ValueError(f"Empty or duplicate {group} list in {manifest['id']}")
            for name in manifest[group]:
                if Path(name).name != name or name in (".", ".."):
                    raise ValueError(f"Invalid {group} name: {name!r}")
        for name in manifest.get("required_world_files", []):
            relative = PurePosixPath(name)
            if relative.is_absolute() or Path(name).is_absolute() or relative.as_posix() != name or any(part in ("", ".", "..") for part in relative.parts):
                raise ValueError(f"Invalid required world file: {name!r}")
    return manifests


def verify_revisions(manifest: dict, sources_root: Path) -> None:
    for repository in REPOSITORIES:
        source = checked_child(sources_root, REPOSITORIES[repository])
        actual = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
        expected = manifest["repositories"][repository]
        if actual != expected:
            raise ValueError(f"{repository} is at {actual}; {manifest['id']} requires {expected}")
        # Check precisely the component inputs copied into the world, including
        # ignored files: filesystem packaging does not obey Git ignore rules.
        roots = DATAPACK_ROOTS if repository == "datapacks" else PACK_ROOTS
        inputs = [
            f"{pack}/{root}"
            for pack in manifest[repository]
            for root in (*roots, "LICENSES")
        ]
        changes = subprocess.check_output(
            ["git", "-C", str(source), "status", "--porcelain=v1",
             "--untracked-files=all", "--ignored=matching", "--", *inputs],
            text=True,
        ).strip()
        if changes:
            raise ValueError(
                f"{repository} has unpublished runtime inputs for {manifest['id']}:\n"
                f"{changes}\nUse clean inputs at the pinned revision for a verified build; "
                "omit --verify-revisions only for a local development build."
            )


def copy_licenses(source: Path, destination: Path) -> None:
    license_root = source / "LICENSES"
    if not license_root.is_dir() or is_link(license_root):
        raise ValueError(f"Missing LICENSES: {source}")
    for name in LICENSE_FILES:
        if not (license_root / name).is_file():
            raise ValueError(f"Missing {name}: {license_root}")
    copy_safe(license_root, destination)


def stamped_metadata(path: Path, version: str) -> str:
    """Return pack.mcmeta text with the component's ${version} placeholder filled in."""
    text = path.read_text(encoding="utf-8").replace(VERSION_PLACEHOLDER, version)
    json.loads(text)
    return text


def write_resourcepack(manifest: dict, sources_root: Path, destination: Path, version: str = DEV_VERSION) -> None:
    entries: dict[str, Path] = {}
    for name in manifest["resourcepacks"]:
        pack = checked_child(sources_root / "resourcepacks", name)
        for root_name in PACK_ROOTS:
            root = pack / root_name
            if not root.exists():
                if root_name == "pack.mcmeta":
                    raise ValueError(f"Missing pack.mcmeta: {pack}")
                continue
            if is_link(root):
                raise ValueError(f"Linked pack entry: {root}")
            if root.is_file():
                entries[root_name] = root
            else:
                for path in root.rglob("*"):
                    if is_link(path):
                        raise ValueError(f"Linked pack entry: {path}")
                    if path.is_file():
                        entries[path.relative_to(pack).as_posix()] = path
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for name, path in sorted(entries.items()):
                if name == "pack.mcmeta":
                    archive.writestr(name, stamped_metadata(path, version))
                else:
                    archive.write(path, name)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def build_world(manifest: dict, maps_root: Path, sources_root: Path, output: Path, version: str = DEV_VERSION) -> Path:
    with tempfile.TemporaryDirectory(prefix="zbk-map-") as temp:
        stage = Path(temp) / manifest["world"]
        source_world = checked_child(maps_root, manifest["world"])
        for name in WORLD_ROOTS:
            source = source_world / name
            if not source.exists():
                if name == "level.dat":
                    raise ValueError(f"Missing level.dat: {source_world}")
                continue
            copy_safe(source, stage / name, skip_shared_structures=name == "generated")
        for name in manifest.get("required_world_files", []):
            if not (stage / name).is_file():
                raise ValueError(f"Missing required world file: {source_world / name}")

        for name in manifest["datapacks"]:
            pack = checked_child(sources_root / "datapacks", name)
            if not (pack / "pack.mcmeta").is_file():
                raise ValueError(f"Missing datapack metadata: {pack}")
            destination = stage / "datapacks" / name
            for runtime_name in DATAPACK_ROOTS:
                source = pack / runtime_name
                if source.exists():
                    copy_safe(source, destination / runtime_name)
            (destination / "pack.mcmeta").write_bytes(
                stamped_metadata(pack / "pack.mcmeta", version).encode("utf-8")
            )
            copy_licenses(pack, stage / "LICENSES" / "datapacks" / name)

        for name in manifest["resourcepacks"]:
            pack = checked_child(sources_root / "resourcepacks", name)
            copy_licenses(pack, stage / "LICENSES" / "resourcepacks" / name)
        copy_licenses(maps_root, stage / "LICENSES" / "maps")
        write_resourcepack(manifest, sources_root, stage / "resourcepacks" / "resources.zip", version)

        output.mkdir(parents=True, exist_ok=True)
        archive_path = output / f"{manifest['id']}.zip"
        with ZipFile(archive_path, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage.parent).as_posix())
        verify_archive(archive_path, manifest)
        return archive_path


def verify_archive(path: Path, manifest: dict) -> None:
    root = manifest["world"] + "/"
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        required = {
            root + "level.dat",
            root + "resourcepacks/resources.zip",
            root + "datapacks/zombies_build_kit/data/zbk/structure/barriers/barrier.nbt",
            root + "datapacks/zombies_build_kit/data/zbk/structure/pack_a_punch/pack_a_punch.nbt",
            root + "LICENSES/maps/LICENSE.md",
            root + "LICENSES/datapacks/zombies_build_kit/NOTICE",
        }
        required.update(root + f"datapacks/{name}/pack.mcmeta" for name in manifest["datapacks"])
        required.update(root + name for name in manifest.get("required_world_files", []))
        if missing := required - names:
            raise ValueError(f"Missing archive entries: {sorted(missing)}")
        legacy = (root + "generated/minecraft/structure/zbk/",
                  root + "generated/minecraft/structures/zbk/")
        if any(name.startswith(legacy) for name in names):
            raise ValueError("Obsolete world-installed Core templates remain in the archive")
        # Player records live at the world root; datapacks may own folders named players.
        forbidden = ("AGENTS.md", "/.codex/", "session.lock", "level.dat_old")
        if leaked := [name for name in names
                      if name.startswith(root + "players/") or any(part in name for part in forbidden)]:
            raise ValueError(f"Local-only archive entries: {leaked[:5]}")
        for name in manifest["datapacks"]:
            if VERSION_PLACEHOLDER in archive.read(root + f"datapacks/{name}/pack.mcmeta").decode("utf-8"):
                raise ValueError(f"Datapack {name} version was not stamped")
        with ZipFile(archive.open(root + "resourcepacks/resources.zip")) as resourcepack:
            pack_names = set(resourcepack.namelist())
            if "pack.mcmeta" not in pack_names or not any(name.startswith("assets/") for name in pack_names):
                raise ValueError("World resource pack is missing metadata or assets")
            if VERSION_PLACEHOLDER in resourcepack.read("pack.mcmeta").decode("utf-8"):
                raise ValueError("World resource pack version was not stamped")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--sources-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resourcepacks-only", action="store_true")
    parser.add_argument("--verify-revisions", action="store_true")
    parser.add_argument("--version", default=DEV_VERSION,
                        help="Version stamped into bundled pack.mcmeta files; the release tag without its v prefix")
    args = parser.parse_args()
    maps_root = args.maps_root.resolve()
    sources_root = (args.sources_root or maps_root.parent).resolve()
    manifests = load_manifests(maps_root)
    for manifest in manifests:
        if args.verify_revisions:
            verify_revisions(manifest, sources_root)
        if args.resourcepacks_only:
            destination = (
                args.output.resolve() / manifest["id"] / "resources.zip"
                if args.output is not None
                else maps_root / manifest["world"] / "resourcepacks" / "resources.zip"
            )
            write_resourcepack(manifest, sources_root, destination, args.version)
            print(destination)
        else:
            if args.output is None:
                parser.error("--output is required unless --resourcepacks-only is set")
            print(build_world(manifest, maps_root, sources_root, args.output.resolve(), args.version))


if __name__ == "__main__":
    main()
