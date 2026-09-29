param(
    [string]$MinecraftDirectory = (Join-Path $env:APPDATA '.minecraft'),
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$mapsRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$sourcesRoot = (Resolve-Path -LiteralPath (Join-Path $mapsRoot '..')).Path
$localPacks = Join-Path $mapsRoot 'output/local-resourcepacks'
$manifests = Get-ChildItem -LiteralPath (Join-Path $mapsRoot 'manifests') -Filter '*.json' |
    Sort-Object Name | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json }
$links = [System.Collections.Generic.List[object]]::new()

function Add-Link([string]$Path, [string]$Target) {
    if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
        throw "Missing junction target: $Target"
    }
    $links.Add([pscustomobject]@{ Path = $Path; Target = $Target })
}

foreach ($map in $manifests) {
    $world = Join-Path $mapsRoot $map.world
    $packOutput = Join-Path $localPacks $map.id
    if (-not $WhatIf) { New-Item -ItemType Directory -Path $packOutput -Force | Out-Null }
    Add-Link (Join-Path $MinecraftDirectory "saves/$($map.world)") $world
    foreach ($name in $map.datapacks) {
        Add-Link (Join-Path $world "datapacks/$name") (Join-Path $sourcesRoot "datapacks/$name")
    }
    if ($WhatIf) {
        $links.Add([pscustomobject]@{ Path = (Join-Path $world 'resourcepacks'); Target = $packOutput })
    } else {
        Add-Link (Join-Path $world 'resourcepacks') $packOutput
    }
    foreach ($name in $map.resourcepacks) {
        $globalPack = Join-Path $MinecraftDirectory "resourcepacks/$name"
        if (-not ($links | Where-Object Path -EQ $globalPack)) {
            Add-Link $globalPack (Join-Path $sourcesRoot "resourcepacks/$name")
        }
    }
}

# Validate every destination before making any junction. Never replace an existing save or pack.
foreach ($link in $links) {
    $existing = Get-Item -LiteralPath $link.Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $existing) { continue }
    if ($existing.LinkType -ne 'Junction') {
        throw "Path already exists and is not a junction: $($link.Path)"
    }
    $actualTarget = [System.IO.Path]::GetFullPath([string]$existing.Target).TrimEnd('\')
    $expectedTarget = [System.IO.Path]::GetFullPath($link.Target).TrimEnd('\')
    if ($actualTarget -ne $expectedTarget) {
        throw "Junction points elsewhere: $($link.Path) -> $actualTarget"
    }
}

if ($WhatIf) {
    $links | ForEach-Object { Write-Output "$($_.Path) -> $($_.Target)" }
    Write-Output 'Would rebuild each world resourcepacks/resources.zip from the manifests.'
    exit 0
}

$builder = Join-Path $PSScriptRoot 'build_maps.py'
& python $builder --maps-root $mapsRoot --sources-root $sourcesRoot --output $localPacks --resourcepacks-only
if ($LASTEXITCODE -ne 0) { throw 'World resource pack build failed.' }

foreach ($link in $links) {
    if ($null -ne (Get-Item -LiteralPath $link.Path -Force -ErrorAction SilentlyContinue)) { continue }
    $parent = Split-Path -Parent $link.Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    New-Item -ItemType Junction -Path $link.Path -Target $link.Target | Out-Null
    Write-Output "Linked $($link.Path)"
}
