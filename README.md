# ZBK Maps

Finished Minecraft Java maps built with [Zombies Build Kit](https://github.com/Stews-Creations/zombies-build-kit), with download links, installation instructions, and compatibility details.

No finished maps have been published here yet.

## Download and install

Finished world downloads will be available under [Releases](https://github.com/Stews-Creations/zbk_maps/releases). GitHub's **Code > Download ZIP** downloads the repository documentation, not a playable map.

1. Choose a map release and check its required Minecraft version, ZBK components, and client mods. Each map's guide will identify what is bundled and what must be installed separately.
2. Close Minecraft and back up any existing world before extracting the downloaded world folder into your instance's `saves` directory. With the default Windows launcher, this is `%APPDATA%\.minecraft\saves\`. The world's `level.dat` should sit directly inside its world folder.
3. Follow the map's guide for resource packs, datapacks, structures, and server setup, then open the world using the documented versions.

Use the installation guide attached to the selected map version; the latest core components are not automatically compatible with every finished map.

## Repository layout and releases

Add each finished map's guide and screenshots under `catalog/<map-id>/`, then link its guide from this README. A map guide must identify its release download, Minecraft version, compatible ZBK component versions or commits, required mods, installation steps, credits, and any known limitations.

Publish playable world ZIPs as release assets. Keep editable worlds, test servers, backups, player data, and packaged downloads outside Git. Before publishing a world, remove private player/server data and test a fresh installation. Include the applicable license files, attribution, media permission, and third-party notices with each download.

This repository owns finished-map documentation and distribution. Shared gameplay remains in [zbk_datapacks](https://github.com/Stews-Creations/zbk_datapacks), shared presentation in [zbk_resourcepacks](https://github.com/Stews-Creations/zbk_resourcepacks), and reusable placement templates in [zbk_structures](https://github.com/Stews-Creations/zbk_structures). Map-specific dependencies must be identified in the map guide rather than added to the shared core.

## Contributions and feedback

We are not currently accepting outside development help or pull/merge requests. Forks and [issues](https://github.com/Stews-Creations/zbk_maps/issues) for bugs, suggestions, and questions are welcome.

## License and credit

Free noncommercial use, modification, and sharing are allowed with credit to [MiniStew](https://www.youtube.com/@MiniStew). Monetized videos and streams are allowed under the [media permission](MEDIA_PERMISSION.md). See [licensing and attribution](LICENSE.md) for the code and asset licenses, their scope, and redistribution requirements. Third-party material retains its own terms.
