#define AppName "CardForge Studio"
#ifndef ReleaseNumber
  #define ReleaseNumber "dev"
#endif
#define AppVersion "1.0.0-rc"
[Setup]
AppId={{993BB058-FB9A-4C27-9F34-09CF75D6CA8A}
AppName={#AppName}
AppVersion={#AppVersion}.{#ReleaseNumber}
AppPublisher=CardForge Studio
AppSupportURL=mailto:curtispasley@gmail.com
DefaultDirName={localappdata}\Programs\CardForgeStudio
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=CardForgeStudio-Setup
SetupIconFile=..\cardforge\assets\CardForge.ico
UninstallDisplayIcon={app}\CardForge4D.exe
LicenseFile=..\LICENSE.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
Uninstallable=yes
UsePreviousAppDir=yes
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\CardForge4D\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\COMMERCIAL_SETUP.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\UPDATE_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\CardForge Studio"; Filename: "{app}\CardForge4D.exe"
Name: "{group}\Uninstall CardForge Studio"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CardForge Studio"; Filename: "{app}\CardForge4D.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\CardForge4D.exe"; Description: "Open CardForge Studio"; Flags: nowait postinstall skipifsilent
