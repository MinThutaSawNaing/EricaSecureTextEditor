#requires -Version 5.1
<#
.SYNOPSIS
Tests and packages Erica using already-installed Windows build tools.
.EXAMPLE
& 'D:\Erica Text Editor\EricaSecureTextEditor\build_windows.ps1'
.NOTES
No dependencies are installed. Use a 64-bit Python environment containing
PyQt6, cryptography and PyInstaller. No installer is executed or uploaded.
#>
[CmdletBinding()]
param(
    [string] $PythonExe = 'python.exe',
    [string] $IsccExe = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
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

function Assert-Artifact {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing artifact: $Path"
    }
    if ((Get-Item -LiteralPath $Path).Length -eq 0) {
        throw "Empty artifact: $Path"
    }
}

$root = $PSScriptRoot
$installerSource = Join-Path $root 'erica_secure_text_editor.iss'
$spec = Join-Path $root 'erica_secure_text_editor.spec'
$nativeBuild = Join-Path $root 'build_native.ps1'
$release = Join-Path $root 'release'
$portable = Join-Path $root 'dist\EricaSecureTextEditor.exe'
$manifest = Join-Path $release 'SHA256SUMS.txt'

# A failed attempt must not leave a previous release-success marker behind.
if (Test-Path -LiteralPath $manifest) {
    Remove-Item -LiteralPath $manifest -Force
}

# Resolve commands once; all subsequent tool/file paths are absolute.
$python = (Get-Command -Name $PythonExe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$iscc = (Get-Command -Name $IsccExe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
foreach ($file in @($installerSource, $spec, $nativeBuild,
    (Join-Path $root 'erica_secure_text_editor.py'),
    (Join-Path $root 'test_erica_secure_text_editor.py'),
    (Join-Path $root 'icon.ico'), (Join-Path $root 'closebutton.png'),
    (Join-Path $root 'LICENSE'))) {
    Assert-Artifact $file
}

# Read the installer version instead of maintaining a second version constant.
$sourceText = [IO.File]::ReadAllText($installerSource)
$versionMatch = [regex]::Match($sourceText, '(?m)^#define MyAppVersion "(?<version>\d+\.\d+)"\s*$')
if (-not $versionMatch.Success) {
    throw 'Expected a major.minor installer version.'
}
$version = $versionMatch.Groups['version'].Value
$appSource = [IO.File]::ReadAllText((Join-Path $root 'erica_secure_text_editor.py'))
$appVersion = [regex]::Match($appSource, '(?m)^APP_VERSION = "(?<version>\d+\.\d+)"\s*$')
if (-not $appVersion.Success -or $appVersion.Groups['version'].Value -ne $version) {
    throw 'Application and installer versions must match.'
}
$installerName = "EricaSecureTextEditorSetup_$version.exe"
$sourceHash = (Get-FileHash -LiteralPath $installerSource -Algorithm SHA256).Hash
$stage = Join-Path $root ('build\windows-' + [guid]::NewGuid().ToString('N'))

$oldQtPlatform = [Environment]::GetEnvironmentVariable('QT_QPA_PLATFORM', 'Process')
$buildSucceeded = $false
Push-Location -LiteralPath $root
try {
    Invoke-Checked $python @('-c', "import struct, sys; import PyQt6, cryptography, PyInstaller; sys.exit(0 if sys.platform == 'win32' and struct.calcsize('P') == 8 else '64-bit Windows Python is required')")
    & $nativeBuild
    Assert-Artifact (Join-Path $root 'erica_storage.dll')
    $env:QT_QPA_PLATFORM = 'offscreen'
    Invoke-Checked $python @('-B', '-m', 'unittest', 'discover', '-s', $root, '-p', 'test_*.py', '-v')

    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    # Do not allow a stale portable executable to pass the artifact check.
    if (Test-Path -LiteralPath $portable) {
        Remove-Item -LiteralPath $portable -Force
    }
    Invoke-Checked $python @('-m', 'PyInstaller', '--noconfirm', '--clean',
        '--distpath', (Join-Path $root 'dist'), '--workpath', (Join-Path $stage 'pyinstaller'), $spec)
    Assert-Artifact $portable

    # Only the real compiler invocation builds; /O is an output path, not lint.
    Invoke-Checked $iscc @('/Qp', "/O$stage", $installerSource)
    $installer = Join-Path $stage $installerName
    Assert-Artifact $installer
    if ((Get-FileHash -LiteralPath $installerSource -Algorithm SHA256).Hash -ne $sourceHash) {
        throw 'Installer source changed during the build; refusing to publish.'
    }

    New-Item -ItemType Directory -Path $release -Force | Out-Null
    Copy-Item -LiteralPath $portable -Destination (Join-Path $release 'EricaSecureTextEditor.exe') -Force
    Copy-Item -LiteralPath $installer -Destination (Join-Path $release $installerName) -Force
    Copy-Item -LiteralPath $installerSource -Destination (Join-Path $release 'erica_secure_text_editor.iss') -Force
    $names = @('EricaSecureTextEditor.exe', $installerName, 'erica_secure_text_editor.iss')
    $sums = foreach ($name in $names) {
        $artifact = Join-Path $release $name
        Assert-Artifact $artifact
        $hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($name -eq 'erica_secure_text_editor.iss' -and $hash -ne $sourceHash.ToLowerInvariant()) {
            throw 'Published installer source does not match the compiled source.'
        }
        '{0}  {1}' -f $hash, $name
    }
    # Written last: contains only the three artifacts produced by this build.
    [IO.File]::WriteAllLines($manifest, [string[]] $sums, [Text.Encoding]::ASCII)
    # Keep only the current installer in the checked-in download folder.
    Get-ChildItem -LiteralPath $release -Filter 'EricaSecureTextEditorSetup_*.exe' -File |
        Where-Object { $_.Name -ne $installerName } |
        Remove-Item -Force
    $buildSucceeded = $true
    Write-Host "Release $version ready in $release (SHA256SUMS.txt generated)."
}
finally {
    [Environment]::SetEnvironmentVariable('QT_QPA_PLATFORM', $oldQtPlatform, 'Process')
    Pop-Location
    # release/ is the canonical download location. Do not accumulate duplicate
    # executables or GUID-named PyInstaller staging directories after success.
    if ($buildSucceeded) {
        Remove-Item -LiteralPath $stage -Recurse -Force
        Remove-Item -LiteralPath $portable -Force
        $dist = Join-Path $root 'dist'
        if (-not (Get-ChildItem -LiteralPath $dist -Force | Select-Object -First 1)) {
            Remove-Item -LiteralPath $dist -Force
        }
    }
}
