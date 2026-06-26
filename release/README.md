# Release Artifacts

This folder is for Windows distribution files generated from the repository.

Expected artifacts:

- `EricaSecureTextEditor.exe` built with PyInstaller
- `EricaSecureTextEditorSetup_3.1.exe` built with Inno Setup
- `erica_secure_text_editor.iss` copied here as the installer source used for the release

Build steps:

```powershell
pyinstaller erica_secure_text_editor.spec
iscc erica_secure_text_editor.iss
```

The Inno Setup script writes the installer output directly into this `release/` folder.
