; Inno Setup script: wraps dist\Lorekeeper (PyInstaller) into one installer, Lorekeeper-Setup-<version>.exe.
;   iscc /DAppVersion=0.1.0 packaging\lorekeeper.iss
; Per-user install (no admin prompt) into %LOCALAPPDATA%\Programs\Lorekeeper. Your notes, gear and settings live in
; %APPDATA%\Lorekeeper and are kept on uninstall.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{27FCD19A-01DD-440D-A0DD-EFB72B18928D}
AppName=Lorekeeper
AppVersion={#AppVersion}
AppVerName=Lorekeeper {#AppVersion}
AppPublisher=FindlayHi
AppPublisherURL=https://lorekeeper-cgv.pages.dev/
AppSupportURL=https://github.com/FindlayHi/lorekeeper/issues
AppUpdatesURL=https://github.com/FindlayHi/lorekeeper/releases
DefaultDirName={localappdata}\Programs\Lorekeeper
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Lorekeeper-Setup-{#AppVersion}
SetupIconFile=..\assets\lorekeeper.ico
UninstallDisplayIcon={app}\Lorekeeper.exe
UninstallDisplayName=Lorekeeper
Compression=lzma2/max
SolidCompression=yes
; Dressed like the landing page: dark, night-sky navy, pixel art (packaging/wizard_art.py makes the images)
WizardStyle=modern dark hidebevels includetitlebar
WizardBackColor=#0b0b2b
WizardImageBackColor=#0b0b2b
WizardImageFile=wizard\banner-100.png,wizard\banner-125.png,wizard\banner-150.png,wizard\banner-175.png,wizard\banner-200.png,wizard\banner-250.png
WizardSmallImageFile=wizard\corner-58.png,wizard\corner-64.png,wizard\corner-72.png,wizard\corner-80.png,wizard\corner-96.png,wizard\corner-116.png,wizard\corner-128.png
WizardBackImageFile=wizard\back-100.png,wizard\back-125.png,wizard\back-150.png,wizard\back-175.png,wizard\back-200.png,wizard\back-250.png
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "startup"; Description: "Start Lorekeeper when Windows starts"; GroupDescription: "Options:"

[Files]
Source: "..\dist\Lorekeeper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "wizard\raptor-*.bmp"; Flags: dontcopy

[Icons]
Name: "{userprograms}\Lorekeeper"; Filename: "{app}\Lorekeeper.exe"; Comment: "A voice companion for PC games"
Name: "{userstartup}\Lorekeeper"; Filename: "{app}\Lorekeeper.exe"; Tasks: startup

[Run]
Filename: "{app}\Lorekeeper.exe"; Description: "Start Lorekeeper now"; Flags: nowait postinstall skipifsilent
; an update from inside the app runs this installer quietly with /AUTOSTART=1: come back on the new version
Filename: "{app}\Lorekeeper.exe"; Flags: nowait; Check: AutoStart

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Lorekeeper.exe /F"; Flags: runhidden; RunOnceId: "StopLorekeeper"

[Messages]
WelcomeLabel2=This installs Lorekeeper, a voice companion for PC games: hold a key in a game, ask out loud, hear the answer.%n%nIt answers through Claude Code on a Claude Pro or Max plan, or your own Ollama, LM Studio or OpenAI key (pick in the tray, under AI). If Claude Code isn't installed yet, Lorekeeper offers to set it up the first time it starts.

[Code]
function AutoStart(): Boolean;
begin
  Result := ExpandConstant('{param:AUTOSTART|0}') = '1';
end;

// Anonymous usage counts: asked here, once, with nothing pre-selected. The answer goes into %APPDATA%\Lorekeeper\config.json,
// so the app doesn't ask again. Skipped when it was answered before (an upgrade); silent installs leave it to the app.
var
  UsagePage: TInputOptionWizardPage;
  Raptor: TBitmapImage;

// The secret's raptor, on the last page only, bottom right: one image per display scaling (3 screen px per art px at 100%)
procedure AddRaptor(Page: TWinControl);
var
  K: Integer;
  F: String;
begin
  K := (ScaleX(300) + 50) div 100;
  if K < 3 then K := 3;
  if K = 7 then K := 6;
  if K > 8 then K := 8;
  F := 'raptor-' + IntToStr(K) + '.bmp';
  ExtractTemporaryFile(F);
  Raptor := TBitmapImage.Create(Page);
  Raptor.Parent := Page;
  Raptor.Bitmap.LoadFromFile(ExpandConstant('{tmp}\' + F));
  Raptor.AutoSize := True;
  Raptor.Left := Page.ClientWidth - Raptor.Width - ScaleX(20);
  Raptor.Top := Page.ClientHeight - Raptor.Height - ScaleY(12);
  Raptor.Anchors := [akRight, akBottom];
end;

function ConfigPath(): String;
begin
  Result := ExpandConstant('{userappdata}\Lorekeeper\config.json');
end;

function UsageAnswered(): Boolean;
var
  S: AnsiString;
begin
  Result := LoadStringFromFile(ConfigPath(), S) and (Pos('"telemetry"', S) > 0);
end;

procedure InitializeWizard();
begin
  UsagePage := CreateInputOptionPage(wpSelectTasks, 'Anonymous usage counts',
    'Help show how many people use Lorekeeper?',
    'If you share, Lorekeeper sends a random id, the app and Windows version, and which features are on (listen mode, RomM, '
    + 'the voice engine), so its maker can see how many people use it. Never your games, questions, answers or anything you say, '
    + 'and IP addresses aren''t kept. You can change this any time in the tray.',
    True, False);
  UsagePage.Add('Share anonymous usage counts');
  UsagePage.Add('Don''t share');
  UsagePage.Values[0] := False;
  UsagePage.Values[1] := False;
#ifdef RaptorTest
  AddRaptor(WizardForm.WelcomePage);   // test builds only: see him without finishing an install
#else
  AddRaptor(WizardForm.FinishedPage);
#endif
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = UsagePage.ID) and UsageAnswered();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = UsagePage.ID) and not (UsagePage.Values[0] or UsagePage.Values[1]) then
  begin
    MsgBox('Please choose one: share anonymous usage counts, or don''t.', mbInformation, MB_OK);
    Result := False;
  end;
end;

procedure SaveUsageChoice();
var
  S: AnsiString;
  V: String;
  P: Integer;
begin
  if not (UsagePage.Values[0] or UsagePage.Values[1]) or UsageAnswered() then
    exit;
  if UsagePage.Values[0] then V := 'true' else V := 'false';
  ForceDirectories(ExtractFileDir(ConfigPath()));
  if not LoadStringFromFile(ConfigPath(), S) or (Trim(S) = '') then
    S := '{}';
  P := Pos('{', S);
  if Trim(Copy(S, P + 1, MaxInt)) = '}' then
    S := '{"telemetry": ' + V + '}'
  else
    S := Copy(S, 1, P) + '"telemetry": ' + V + ', ' + Copy(S, P + 1, MaxInt);
  SaveStringToFile(ConfigPath(), S, False);
end;

// Close a running Lorekeeper here, at once. Left to the Restart Manager (CloseApplications), it waits ~30 s for the tray app to
// answer a close request it never answers, and the wizard can't be moved or redrawn meanwhile.
// No /T: an in-app update starts this installer as Lorekeeper's child, and killing the tree would kill the installer too.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Lorekeeper.exe /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveUsageChoice();
end;

// Lorekeeper answers through Claude Code: say on the last page whether it's here yet (the app offers to install it).
function ClaudeCodeFound(): Boolean;
begin
  Result := FileExists(ExpandConstant('{%USERPROFILE}\.local\bin\claude.exe'))
    or (FileSearch('claude.exe', GetEnv('PATH')) <> '')
    or (FileSearch('claude.cmd', GetEnv('PATH')) <> '');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
    if ClaudeCodeFound() then
      WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 +
        'Claude Code is installed, so Lorekeeper is ready. Hold Ctrl+Alt+Space in a game and ask.'
    else
      WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 +
        'One more step: Lorekeeper answers through Claude Code (with a Claude Pro or Max plan). It isn''t installed yet, ' +
        'so when Lorekeeper starts it will offer to install it and help you sign in. ' +
        'Or pick Ollama, LM Studio or OpenAI from the tray, under AI.';
end;
