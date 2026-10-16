# Release Artifacts

This folder is for Windows distribution files generated from the repository.

Expected artifacts:

- `EricaSecureTextEditor.exe` built with PyInstaller
- `EricaSecureTextEditorSetup_3.4.exe` built with Inno Setup
- `SHA256SUMS.txt` contains SHA-256 hashes for the current build artifacts
- `erica_secure_text_editor.iss` copied here as the installer source used for the release

Download guidance:

- Use [EricaSecureTextEditorSetup_3.4.exe](./EricaSecureTextEditorSetup_3.4.exe?raw=true) for the normal Windows install experience.
- Use `EricaSecureTextEditor.exe` for a portable launch without installation.
- The installer registers Erica in Windows `Open with` for `.erica` secure documents.

Build steps:

```powershell
pyinstaller erica_secure_text_editor.spec
iscc erica_secure_text_editor.iss
```

The Inno Setup script writes the installer output directly into this `release/` folder.

Prefer the repository-root `build_windows.ps1` script to run tests and generate both binaries and checksums together. Fresh installs default to current-user scope, with optional all-users installation and an optional desktop shortcut. Existing installation scope and directory are retained when detected. Binaries are unsigned; hashes verify integrity, not publisher identity. Version 3.3 is retained only as a historical installer.
