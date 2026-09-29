# ZBK Maps

This repository contains editable Minecraft Java 26.2 worlds. Each world is built with tested revisions of the [ZBK datapacks](https://github.com/Stews-Creations/zbk_datapacks) and [resource packs](https://github.com/Stews-Creations/zbk_resourcepacks). GitHub Actions creates portable world ZIPs on every push.

| World | Datapacks | World resource pack |
| --- | --- | --- |
| `Nacht Der Untoten` | Base pack and Nacht | Base pack assets with Nacht overrides |
| `ZBK Template` | Base pack and template provider | Base pack assets |

The matching files and exact component commits are recorded in [manifests/](manifests/). Change a component revision there only after testing the map with it. Both maps currently use one shared revision of each component repository. The base pack supplies all shared structure templates inside its datapack under the `zbk:<category>/<template>` identifiers. There is no separate structures dependency.

## Local editing on Windows

Clone the [ZBK workspace](https://github.com/Stews-Creations/zombies-build-kit) with submodules, install Git LFS, and fetch the world region files:

```powershell
git -C maps lfs install
git -C maps lfs pull
powershell -ExecutionPolicy Bypass -File .\maps\tools\link-local.ps1 -WhatIf
powershell -ExecutionPolicy Bypass -File .\maps\tools\link-local.ps1
```

Run these from the workspace root while Minecraft is closed. The script refuses to replace an existing save, pack folder, or junction pointing elsewhere. It links each world into `%APPDATA%\.minecraft\saves`, then links the required source datapacks inside the world. It also links the source resource packs into `%APPDATA%\.minecraft\resourcepacks` for editing.

Minecraft Java 26.2 loads a world pack from `resourcepacks/resources.zip`. The script builds one merged ZIP per world from the current component checkouts in ignored `output/local-resourcepacks/` and makes the world's `resourcepacks` directory a junction to that generated folder. Run the script again after changing resource assets. The manifests pin revisions for GitHub builds; local editing can use unpublished component changes. The ZIP is a file; a directory junction named `resources.zip` is not a substitute.

These save junctions point directly at editable source worlds. Changes made while playing affect the map source. Back up a world before destructive testing, and close Minecraft before rerunning the setup or committing world files. The setup accepts `-MinecraftDirectory` for a different launcher instance.

When upgrading an existing checkout, remove the old `generated/minecraft/structure/zbk` junction inside each world while Minecraft is closed. Back up any real directory at that location before removing it, and check the older plural `structures` path too. The base pack now supplies those templates. The builder excludes these legacy shared-template paths while preserving unrelated map structures.

## Build portable worlds

From the workspace root:

```powershell
python maps/tools/build_maps.py --maps-root maps --sources-root . --output maps/output/worlds --verify-revisions
```

Each output ZIP contains a single world folder. The builder copies `level.dat`, the world data and dimensions, the selected datapacks with bundled shared templates, one merged world resource pack, and license/notice files from every included component. Nacht assets override the base pack assets in its merged pack. The builder does not include player data, session locks, editor settings, local instructions, Git metadata, or junctions. It stops if a required source or tested revision is missing.

[Build map worlds](.github/workflows/build-maps.yml) runs on every push and can also be started manually. It checks out the exact revisions in the manifests, downloads Git LFS world files, validates each ZIP, and uploads each world ZIP as its own workflow artifact. Each download is the world ZIP itself, with no outer archive to extract. A GitHub source download is not a built world.

`--verify-revisions` requires the exact component commits in the manifests and clean runtime inputs in those components. It rejects staged, unstaged, untracked, and ignored files that would change the selected packs or included licenses. Changes outside those inputs, such as component documentation and local build output, do not block verification. The editable world state is copied as it stands; this option verifies component dependencies, not whether world edits are committed. Omit the option only when intentionally building with local development dependencies. Close Minecraft and stop editing inputs while building.

Run the dependency-verification regression checks from the workspace root with `python -B -m unittest discover -s maps/tools -p check_build_maps.py`. They use disposable repositories under the maps checkout's ignored `.codex/` directory and also run in the build workflow.

To install a built world, close Minecraft and extract its world folder into `%APPDATA%\.minecraft\saves` or the saves folder of the chosen launcher instance. Move or rename any existing world of the same name first. The world folder must contain `level.dat` directly. The ZIP includes the required datapacks with bundled structures and the singleplayer resource pack. Optional client mods and Vivecraft overlays remain separate.

## Source files and releases

World regions (`*.mca`) use Git LFS. The repository tracks the editable map state, including `level.dat`, dimension regions, shared world data, and icon files. Nacht's `zbk:door_storage` region contains the saved blocks needed to open and reset its custom doors; keep it with the world. The repository ignores player records, locks, backups, generated dependency links, and built ZIPs. Review any new world files before staging; Git ignore rules alone do not protect release archives.

The workflow artifacts are development builds. Test a fresh extracted world in Minecraft before publishing a release. Include the applicable license files, attribution, media permission, and third-party notices; the builder places these under each world's `LICENSES/` directory. A dedicated release workflow can be added after both maps pass installation and gameplay checks.

## License and credit

Free noncommercial use, modification, and sharing are allowed with credit to [MiniStew](https://www.youtube.com/@MiniStew). Monetized videos and streams are allowed under the [media permission](LICENSES/MEDIA_PERMISSION.md). See [licensing and attribution](LICENSES/LICENSE.md) for the code and asset licenses, their scope, and redistribution requirements. Third-party material retains its own terms.
