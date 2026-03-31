[Setup]
AppName=Erica Secure Text Editor
AppVersion=3.1
AppId={{E6E72C45-A094-4F3E-97F7-ERICA-TEXT-EDITOR}}
DefaultDirName={autopf}\EricaSecureText
DefaultGroupName=Erica Secure Text Editor
OutputDir=C:\Users\MGR\Desktop\EricaBuild
OutputBaseFilename=EricaSecureTextEditorSetup_3.1
SetupIconFile="C:\Users\MGR\Documents\My Software\Version3.0\icon.ico"
UninstallDisplayIcon="{app}\EricaSecureTextEditor.exe"
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
DisableProgramGroupPage=yes
VersionInfoVersion=3.1.0.0

[Files]
Source: "C:\Users\MGR\Documents\My Software\Version3.0\dist\EricaSecureTextEditor.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Erica Secure Text Editor"; Filename: "{app}\EricaSecureTextEditor.exe"
Name: "{commondesktop}\Erica Secure Text Editor"; Filename: "{app}\EricaSecureTextEditor.exe"

[Run]
Filename: "{app}\EricaSecureTextEditor.exe"; Description: "Launch Erica Secure Text Editor"; Flags: nowait postinstall skipifsilent
