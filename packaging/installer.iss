; Inno Setup script: builds ProvoOremSimulator-Setup.exe from dist\ProvoOremSimulator (PyInstaller output).
; Installs per user (no admin prompt), adds Start menu + desktop shortcuts.
#define AppName "Provo-Orem Social Simulator"
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{8F3C2A51-6B1E-4C2B-9E7A-2D5F1A0B7C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Utah County College Simulator project
DefaultDirName={localappdata}\Programs\ProvoOremSimulator
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ProvoOremSimulator-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\ProvoOremSimulator.exe
UninstallDisplayName={#AppName}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
; in-app updates run this installer silently while the old app is quitting
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[InstallDelete]
; the previous version's page bundles (names carry a content hash, so new ones never overwrite them)
Type: filesandordirs; Name: "{app}\_internal\web\dist"
Type: filesandordirs; Name: "{app}\web\dist"

[Files]
Source: "..\dist\ProvoOremSimulator\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\ProvoOremSimulator.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ProvoOremSimulator.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ProvoOremSimulator.exe"; Description: "Start the simulator now"; Flags: nowait postinstall skipifsilent
; after a silent (in-app) update, start the new version straight away
Filename: "{app}\ProvoOremSimulator.exe"; Flags: nowait skipifnotsilent
