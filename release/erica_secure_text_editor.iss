#define MyAppName "Erica Secure Text Editor"
#define MyAppVersion "3.5"
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
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
AppReadmeFile={#MyAppURL}#readme
AppComments=Local-first secure text editor
; Keep AppId and the original directory name for in-place upgrades.
; autopf resolves per install scope; existing installs retain their directory.
DefaultDirName={autopf}\EricaSecureText
UsePreviousAppDir=yes
UsePreviousPrivileges=yes
DefaultGroupName={#MyAppName}
OutputDir={#MySourceDir}release
OutputBaseFilename=EricaSecureTextEditorSetup_{#MyAppVersion}
SetupIconFile={#MySourceDir}icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
; Fresh installs need no elevation; all-users is an explicit choice.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
VersionInfoVersion={#MyAppVersion}.0.0
VersionInfoProductVersion={#MyAppVersion}.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
UninstallDisplayName={#MyAppName} {#MyAppVersion}
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
LicenseFile={#MySourceDir}LICENSE
ChangesAssociations=yes

[Files]
Source: "{#MySourceDir}dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Registry]
; HKA selects HKCU for current-user installs and HKLM for all-users.
; Offer Open With without setting .erica's default value or UserChoice.
; Leave legacy default associations alone when upgrading from 3.3.
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppAssocKey}"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}"; ValueType: string; ValueData: "{#MyAppAssocName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\DefaultIcon"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: "{#MyAppAssocExt}"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
