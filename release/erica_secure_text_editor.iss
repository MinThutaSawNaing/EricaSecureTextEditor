#define MyAppName "Erica Secure Text Editor"
#define MyAppVersion "3.2"
#define MyAppExeName "EricaSecureTextEditor.exe"
#define MyAppPublisher "Min Thuta Saw Naing (Eric)"
#define MyAppURL "https://github.com/MinThutaSawNaing/EricaSecureTextEditor"
#define MySourceDir AddBackslash(SourcePath)
#define MyAppAssocName "Erica Secure Document"
#define MyAppAssocExt ".erica"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

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
ChangesAssociations=yes

[Files]
Source: "{#MySourceDir}dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
Root: HKCR; Subkey: "{#MyAppAssocExt}"; ValueType: string; ValueData: "{#MyAppAssocKey}"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "{#MyAppAssocKey}"; ValueType: string; ValueData: "{#MyAppAssocName}"; Flags: uninsdeletekey
Root: HKCR; Subkey: "{#MyAppAssocKey}\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCR; Subkey: "{#MyAppAssocKey}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
Root: HKCR; Subkey: "Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: "{#MyAppAssocExt}"; ValueData: ""
Root: HKCR; Subkey: "Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
