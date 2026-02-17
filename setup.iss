; ── Password Vault Installer Script (Inno Setup) ──

#define MyAppName "Password Vault"
#define MyAppVersion "3.2"
#define MyAppPublisher "Eslam Atwa"
#define MyAppExeName "PasswordVault.exe"

[Setup]
AppId={{B8F3D2A1-7C4E-4A9B-8D5F-1E6A3C2B0D9F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=D:\PasswordVault\PasswordVault\installer
OutputBaseFilename=PasswordVault_Setup
SetupIconFile=D:\PasswordVault\PasswordVault\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; ── Update behavior ──
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
; ── Force close running app during install/update ──
CloseApplications=force
CloseApplicationsFilter=PasswordVault.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "D:\PasswordVault\PasswordVault\dist\PasswordVault.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\PasswordVault\PasswordVault\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  OldVersion: String;
begin
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3D2A1-7C4E-4A9B-8D5F-1E6A3C2B0D9F}_is1',
      'DisplayVersion', OldVersion) or
     RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3D2A1-7C4E-4A9B-8D5F-1E6A3C2B0D9F}_is1',
      'DisplayVersion', OldVersion) then
  begin
    Result := 'Update Information:' + NewLine +
              Space + 'Updating from v' + OldVersion + ' to v{#MyAppVersion}' + NewLine +
              NewLine +
              'Your saved passwords and settings will NOT be affected.' + NewLine +
              NewLine;
  end else
  begin
    Result := 'Installation Information:' + NewLine +
              Space + 'Installing {#MyAppName} v{#MyAppVersion}' + NewLine +
              NewLine;
  end;
  if MemoDirInfo <> '' then
    Result := Result + MemoDirInfo + NewLine + NewLine;
  if MemoGroupInfo <> '' then
    Result := Result + MemoGroupInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then
    Result := Result + MemoTasksInfo + NewLine + NewLine;
end;

function GetCustomSetupTitle(Param: String): String;
var
  OldVersion: String;
begin
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3D2A1-7C4E-4A9B-8D5F-1E6A3C2B0D9F}_is1',
      'DisplayVersion', OldVersion) or
     RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3D2A1-7C4E-4A9B-8D5F-1E6A3C2B0D9F}_is1',
      'DisplayVersion', OldVersion) then
    Result := 'Update'
  else
    Result := 'Install';
end;

procedure CurPageChanged(CurPageID: Integer);
var
  OldVersion: String;
  IsUpdate: Boolean;
begin
  IsUpdate := RegQueryStringValue(HKCU,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3D2A1-7C4E-4A9B-8D5F-1E6A3C2B0D9F}_is1',
    'DisplayVersion', OldVersion) or
    RegQueryStringValue(HKLM,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3D2A1-7C4E-4A9B-8D5F-1E6A3C2B0D9F}_is1',
    'DisplayVersion', OldVersion);

  if IsUpdate then
  begin
    if CurPageID = wpWelcome then
    begin
      WizardForm.WelcomeLabel1.Caption := 'Update {#MyAppName}';
      WizardForm.WelcomeLabel2.Caption :=
        'Setup will update {#MyAppName} from v' + OldVersion + ' to v{#MyAppVersion}.' + #13#10 + #13#10 +
        'Your saved passwords and settings will NOT be affected.' + #13#10 + #13#10 +
        'Click Next to continue, or Cancel to exit.';
    end;
    if CurPageID = wpReady then
    begin
      WizardForm.ReadyLabel.Caption := 'Setup is ready to update {#MyAppName} to v{#MyAppVersion}.';
    end;
    if CurPageID = wpFinished then
    begin
      WizardForm.FinishedHeadingLabel.Caption := 'Update Complete!';
      WizardForm.FinishedLabel.Caption :=
        '{#MyAppName} has been updated to v{#MyAppVersion}.' + #13#10 + #13#10 +
        'Your passwords and settings are safe.';
    end;
  end;
end;
