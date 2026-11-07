; Inno Setup script -> installer\Output\Whisky-Setup-<ver>.exe
#define AppName "Whisky"
#ifndef AppVer
  #define AppVer "1.4.0"
#endif

[Setup]
AppId={{F7279542-CC7D-4783-9108-67DDC8D90872}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppVer}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=Whisky-Setup-{#AppVer}
SetupIconFile=..\assets\whisky.ico
UninstallDisplayIcon={app}\Whisky.exe
#ifdef Fast
Compression=none
#else
Compression=lzma2/max
#endif
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
CloseApplications=no

[Tasks]
Name: "autostart"; Description: "Start with Windows"
Name: "desktopicon"; Description: "Desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Whisky\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Whisky.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Whisky.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Whisky"; ValueData: """{app}\Whisky.exe"""; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Whisky"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\Whisky.exe"; Description: "Launch Whisky"; Flags: nowait postinstall skipifsilent

[Code]
const UninstKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{F7279542-CC7D-4783-9108-67DDC8D90872}_is1';
var OldVer: String;

function IsUpdate(): Boolean;
begin
  Result := OldVer <> '';
end;

function InitializeSetup(): Boolean;
begin
  if not RegQueryStringValue(HKA, UninstKey, 'DisplayVersion', OldVer) then
    OldVer := '';
  if IsUpdate() then
    Log('Whisky update: ' + OldVer + ' -> {#AppVer}')
  else
    Log('Whisky fresh install {#AppVer}');
  Result := True;
end;

procedure InitializeWizard();
begin
  if IsUpdate() then
    WizardForm.Caption := 'Update {#AppName}';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := IsUpdate() and (PageID = wpSelectTasks);   // keep previous choices
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if not IsUpdate() then exit;
  if CurPageID = wpReady then
  begin
    WizardForm.PageNameLabel.Caption := 'Ready to update';
    if OldVer = '{#AppVer}' then
      WizardForm.PageDescriptionLabel.Caption := '{#AppName} {#AppVer} is already installed. Reinstall it. Settings and models are kept.'
    else
      WizardForm.PageDescriptionLabel.Caption := 'Update {#AppName} ' + OldVer + ' to {#AppVer}. Settings and models are kept.';
    WizardForm.NextButton.Caption := 'Update';
  end
  else if CurPageID = wpInstalling then
    WizardForm.PageNameLabel.Caption := 'Updating'
  else if CurPageID = wpFinished then
    WizardForm.FinishedHeadingLabel.Caption := '{#AppName} updated to {#AppVer}';
end;

procedure KillApp();
var rc: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Whisky.exe', '', SW_HIDE, ewWaitUntilTerminated, rc);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  KillApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  KillApp();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var dataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    dataDir := ExpandConstant('{localappdata}\Whisky');
    if DirExists(dataDir) and (not UninstallSilent) then
      if MsgBox('Delete downloaded models and settings?' #13#10 + dataDir, mbConfirmation, MB_YESNO) = IDYES then
        DelTree(dataDir, True, True, True);
  end;
end;
