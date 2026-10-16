#requires -Version 5.1
<#
.SYNOPSIS
Tests and builds the dependency-free Rust storage DLL using installed tools.
.NOTES
No dependencies are installed or downloaded. Cargo.lock must already exist.
#>
[CmdletBinding()]
param(
    [string] $CargoExe = 'cargo.exe'
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
    Copy-Item -LiteralPath $dll -Destination $installedDll -Force
    Write-Host "Native storage DLL installed: $installedDll"
}
finally {
    Pop-Location
}