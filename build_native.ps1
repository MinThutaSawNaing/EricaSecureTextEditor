#requires -Version 5.1
<#
.SYNOPSIS
Tests and builds the Rust storage and organization DLL using installed tools.
.NOTES
Cargo.lock must already exist. Use -FetchDependencies once on a new machine to
download the locked Rust dependencies. Tests/builds themselves remain offline.
#>
[CmdletBinding()]
param(
    [string] $CargoExe = 'cargo.exe',
    [switch] $FetchDependencies
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-Checked {
    param([string] $Executable, [string[]] $Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit ${LASTEXITCODE}): $Executable $($Arguments -join ' ')"
    }
}

$root = $PSScriptRoot
$crate = Join-Path $root 'native\erica_storage'
$manifest = Join-Path $crate 'Cargo.toml'
$lock = Join-Path $crate 'Cargo.lock'
$target = Join-Path $crate 'target'
$dll = Join-Path $target 'release\erica_storage.dll'
$installedDll = Join-Path $root 'erica_storage.dll'
$cargo = (Get-Command -Name $CargoExe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source

foreach ($file in @($manifest, $lock)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Missing native build input: $file. Restore the native crate and its committed Cargo.lock before running build_native.ps1."
    }
}

Push-Location -LiteralPath $crate
try {
    if ($FetchDependencies) {
        Invoke-Checked $cargo @('fetch', '--manifest-path', $manifest, '--locked')
    }
    $common = @('--manifest-path', $manifest, '--target-dir', $target, '--offline', '--locked')
    Invoke-Checked $cargo (@('test') + $common)

    $commands = Invoke-Checked $cargo @('--list')
    if (($commands -join "`n") -match '(?m)^\s+clippy\s') {
        Invoke-Checked $cargo (@('clippy') + $common + @('--all-targets', '--', '-D', 'warnings'))
    }
    else {
        Write-Warning 'Clippy is not installed; skipping native lint checks.'
    }

    Invoke-Checked $cargo (@('build', '--release') + $common)
    if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) {
        throw "Cargo did not produce $dll. Use a Windows Rust toolchain that builds the erica_storage cdylib."
    }
    if ((Get-Item -LiteralPath $dll).Length -eq 0) {
        throw "Cargo produced an empty DLL: $dll"
    }
    # Windows locks a loaded DLL. Avoid an unnecessary replacement when a
    # running source application already uses exactly the freshly built bytes.
    $unchanged = (Test-Path -LiteralPath $installedDll -PathType Leaf) -and
        ((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -eq
         (Get-FileHash -LiteralPath $installedDll -Algorithm SHA256).Hash)
    if ($unchanged) {
        Write-Host "Native storage DLL already up to date: $installedDll"
    }
    else {
        try {
            Copy-Item -LiteralPath $dll -Destination $installedDll -Force
        }
        catch {
            throw "Cannot update native DLL at $installedDll. Close running Erica instances and retry. $($_.Exception.Message)"
        }
        Write-Host "Native storage DLL installed: $installedDll"
    }
}
finally {
    Pop-Location
}