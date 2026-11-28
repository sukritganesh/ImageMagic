#define AppVersion "1.1.0"

[Setup]
AppId=ImageMagic.Studio
AppName=ImageMagic
AppVersion={#AppVersion}
AppPublisher=ImageMagic
AppPublisherURL=https://github.com/sukritganesh/ImageMagic
DefaultDirName={localappdata}\Programs\ImageMagic
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.22000
DisableDirPage=no
DisableProgramGroupPage=yes
DefaultGroupName=ImageMagic
WizardStyle=modern
SetupIconFile=ImageMagic.ico
UninstallDisplayIcon={app}\ImageMagic.ico
OutputDir=..\dist
OutputBaseFilename=ImageMagic-Setup-{#AppVersion}
AppMutex=Local\ImageMagic.InstalledLauncher
CloseApplications=no

[Files]
Source: "..\setup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\launch_studio.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\ImageMagic.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ImageMagic.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\WINDOWS-SETUP.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\custom_nodes\imagemagic_studio\*.py"; DestDir: "{app}\custom_nodes\imagemagic_studio"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{app}\Open ImageMagic.ps1"
Type: files; Name: "{app}\custom_nodes\imagemagic_studio\studio.html"
Type: files; Name: "{app}\custom_nodes\imagemagic_studio\sessions.html"
Type: files; Name: "{app}\custom_nodes\imagemagic_studio\style.css"
Type: files; Name: "{app}\custom_nodes\imagemagic_studio\favicon.svg"

[Icons]
Name: "{group}\ImageMagic"; Filename: "{app}\ImageMagic.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\ImageMagic.exe"; WorkingDir: "{app}"; Description: "Open ImageMagic"; Flags: nowait postinstall skipifsilent

[Code]
function StopInstalledStudio(Dir: String): String;
var
  Python, Launcher: String;
  ExitCode: Integer;
begin
  Result := '';
  Python := Dir + '\ComfyUI_windows_portable\python_embeded\python.exe';
  Launcher := Dir + '\launch_studio.py';
  if (FileExists(Dir + '\Open ImageMagic.ps1') or FileExists(Dir + '\ImageMagic.exe')) and FileExists(Python) and FileExists(Launcher) then
    if not Exec(Python, '-I "' + Launcher + '" --stop', Dir, SW_HIDE, ewWaitUntilTerminated, ExitCode)
       or (ExitCode <> 0) then
      Result := 'Could not stop this studio. Let queued jobs finish, then try again.';
end;

// A source checkout is a separate installation with its own server and gallery.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Dir: String;
begin
  Dir := ExpandConstant('{app}');
  if FileExists(Dir + '\Start ImageMagic.cmd') or DirExists(Dir + '\.git') then
    Result := 'Choose a separate folder for the installed edition of ImageMagic.'
  else
    Result := StopInstalledStudio(Dir);
end;

function InitializeUninstall(): Boolean;
var
  MessageText: String;
begin
  MessageText := StopInstalledStudio(ExpandConstant('{app}'));
  Result := MessageText = '';
  if not Result then SuppressibleMsgBox(MessageText, mbError, MB_OK, IDOK);
end;
