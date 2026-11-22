#define RepoRoot GetEnv("APO_REPO_ROOT")
#if RepoRoot == ""
  #error "APO_REPO_ROOT must be set to the repository root"
#endif

[Setup]
AppName=АПО.ТИМИМО
AppVersion=0.1.2
AppVerName=АПО.ТИМИМО 0.1.2
AppPublisher=Команда КАИРО
AppPublisherURL=https://github.com/IvaSerz/APO-TIMIMO
DefaultDirName={localappdata}\Programs\APO.TIMIMO
DefaultGroupName=АПО.ТИМИМО
UninstallDisplayIcon={app}\APO_TIMIMO.exe
OutputDir={#RepoRoot}\releases
OutputBaseFilename=APO_TIMIMO_v0.1.2_Windows_x64_Setup
SetupIconFile={#RepoRoot}\software_audit\assets\app-icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
DisableWelcomePage=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительные задачи"; Flags: unchecked

[Files]
Source: "{#RepoRoot}\dist\APO_TIMIMO.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\АПО.ТИМИМО"; Filename: "{app}\APO_TIMIMO.exe"
Name: "{autodesktop}\АПО.ТИМИМО"; Filename: "{app}\APO_TIMIMO.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\APO_TIMIMO.exe"; Description: "Запустить АПО.ТИМИМО"; Flags: nowait postinstall skipifsilent
