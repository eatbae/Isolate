# Builds the zip people download: dist\StemSplitter-v<version>.zip
# Run from this folder:  powershell -ExecutionPolicy Bypass -File make_release.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$version = (Get-Content "$root\config.json" -Raw | ConvertFrom-Json).version
$files = @(
    "Stem Splitter.bat", "setup.bat", "app.py", "engine.py", "config.json",
    "requirements.txt", "README.md", "LICENSE", "static\index.html"
)

$dist = Join-Path $root "dist"
$zip = Join-Path $dist "StemSplitter-v$version.zip"
New-Item -ItemType Directory -Force $dist | Out-Null
if (Test-Path $zip) { Remove-Item $zip -Force }

# Entries are written by hand so paths use "/" (Windows PowerShell's zip tools write "\",
# which some unzip programs mishandle). Everything goes inside a "Stem Splitter" folder.
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($zip, "Create")
try {
    foreach ($f in $files) {
        $entry = "Stem Splitter/" + ($f -replace "\\", "/")
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, (Join-Path $root $f), $entry, "Optimal") | Out-Null
    }
} finally {
    $archive.Dispose()
}

$size = "{0:N0} KB" -f ((Get-Item $zip).Length / 1KB)
Write-Host "Built $zip ($size)"
