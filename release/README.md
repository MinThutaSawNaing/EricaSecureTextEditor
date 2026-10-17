# Erica 3.6 — Windows downloads

This folder contains only the current Windows x64 release. The Python runtime
and native backend are included; no development tools are required to run it.

| Artifact | Purpose |
| --- | --- |
| [Windows installer](./EricaSecureTextEditorSetup_3.6.exe?raw=true) | Recommended installation and upgrades |
| [Standalone executable](./EricaSecureTextEditor.exe?raw=true) | Run without installation |
| [SHA-256 checksums](./SHA256SUMS.txt?raw=true) | Hashes for both executables and the matching installer source |
| [Installer source](./erica_secure_text_editor.iss) | Inno Setup script used for this release |

## Release highlights

Version 3.6 adds Rust-backed organization-token security and a compact,
theme-aware setup dialog. Each token requires exactly 16 digits. Five-digit checks
are generated automatically, read-only, and optionally copied; invalid input shows
an inline warning. Generated tokens are shown immediately—keep the screen private.
Existing password files and organization version-1 encrypted files remain compatible.

Organization mode is software shared-key encryption, **not a hardware HSM**.
Read the [setup instructions and security limitations](../README.md) before use.

## Installation and verification

Fresh installations default to the current user; all-users installation and a
desktop shortcut are optional. Upgrades retain the existing scope and directory.
The installer registers `.erica` **Open with** support without changing the default app.

**Binaries are unsigned.** Windows may display an unknown-publisher warning.
Compare downloaded file hashes with `SHA256SUMS.txt`, for example:

```powershell
Get-FileHash .\EricaSecureTextEditorSetup_3.6.exe -Algorithm SHA256
```

A matching hash verifies bytes, not publisher identity. Trust in the checksum
depends on trust in the repository and the downloaded manifest.

## Rebuild

See [source prerequisites and packaging commands](../README.md#package-windows-builds).
`build_windows.ps1` tests the native and Python code, packages both executables,
copies the matching installer source, and generates checksums for those artifacts.
It does not install, sign, upload, or push anything. Supply `-IsccExe` with the
actual installed Inno Setup compiler path if it differs from the script default.

Successful builds keep only the current installer here and remove temporary
packaging output. **Old binaries remain in Git history**, not as live downloads
in this folder. Source is distributed under the [MIT License](../LICENSE).