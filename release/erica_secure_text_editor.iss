#define MyAppName "Erica Secure Text Editor"
#define MyAppVersion "3.1"
#define MyAppExeName "EricaSecureTextEditor.exe"
#define MyAppPublisher "Min Thuta Saw Naing (Eric)"
#define MyAppURL "https://github.com/MinThutaSawNaing/EricaSecureTextEditor"
#define MySourceDir AddBackslash(SourcePath)

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppId={{E6E72C45-A094-4F3E-97F7-ERICA-TEXT-EDITOR}}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\EricaSecureText
DefaultGroupName={#MyAppName}
OutputDir={#MySourceDir}release
OutputBaseFilename=EricaSecureTextEditorSetup_{#MyAppVersion}
SetupIconFile={#MySourceDir}icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
DisableProgramGroupPage=yes
VersionInfoVersion={#MyAppVersion}.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
LicenseFile={#MySourceDir}LICENSE

[Files]
Source: "{#MySourceDir}dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
