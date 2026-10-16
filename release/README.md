# Erica 3.5 - current Windows downloads

Only the current release is kept here:

- [Windows installer](./EricaSecureTextEditorSetup_3.5.exe?raw=true) - recommended; updates the installed application and shortcuts.
- [Portable application](./EricaSecureTextEditor.exe?raw=true) - launch without installation.
- [SHA-256 checksums](./SHA256SUMS.txt) - verifies bytes, not publisher identity.
- `erica_secure_text_editor.iss` - exact installer source used for this release.

Version 3.5 keeps the familiar uncluttered layout. Right-click in the editor for **Font**, **Paragraph**, and **Table** controls. It also includes incremental word counts, background encryption/storage/recovery, and suppression of permission-command console flashes. Encryption format and legacy document compatibility are unchanged.

Fresh installs default to the current user, with optional all-users installation and an optional desktop shortcut. Existing installation scope and directory are retained. The installer offers `.erica` Open With support without changing the default application. Binaries are unsigned; Windows may display an unknown-publisher warning.

## Rebuild

From the repository root on Windows, run `build_windows.ps1` with the installed Python/PyQt6/cryptography/PyInstaller, Rust MSVC toolchain, C++ Build Tools, and Inno Setup 6. It tests and builds the native DLL, runs Python tests, packages both executables, and generates checksums. It does not install, upload, or push anything.

Successful builds remove their temporary packaging stage and duplicate `dist` executable, and retain only the current installer here. Old binaries remain accessible in Git history, not in this folder.
