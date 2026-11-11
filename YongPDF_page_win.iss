; ==============================================================================
;  YongPDF_page Inno Setup 6 Script
;  Windows 고속 실행(onedir) 패키지 배포용 인스톨러 스크립트
; ==============================================================================

#define MyAppName "YongPDF_page"
#define MyAppVersion "1.1"
#define MyAppPublisher "Hwang Jinsu"
#define MyAppURL "https://github.com/hwangjinsu/yongpdf"
#define MyAppExeName "YongPDF_page.exe"

[Setup]
AppId={{9F82A4D1-0C71-4B9A-8E2E-15B771A24B2C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

OutputDir=dist
OutputBaseFilename=YongPDF_page_Setup_v{#MyAppVersion}
SetupIconFile=Assets\YongPDF_page_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "installghostscript"; Description: "Ghostscript PDF 고급 압축 엔진 설치 (권장: 고품질/대용량 PDF 압축 지원)"; GroupDescription: "추가 구성 요소:"

[Files]
Source: "dist\YongPDF_page\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Windows App Paths 등록 (어디서나 YongPDF_page.exe 호출 가능)
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
; 1. Ghostscript 사일런트 백그라운드 설치 (체크박스 선택 및 번들 설치파일 존재 시)
Filename: "{code:GetGhostscriptInstallerPath}"; Parameters: "/S"; StatusMsg: "Ghostscript PDF 압축 엔진을 백그라운드에서 설치하는 중입니다..."; Flags: runhidden waituntilterminated; Tasks: installghostscript; Check: ShouldInstallGhostscript

; 2. 설치 완료 후 앱 바로 실행 체크박스
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  FoundGsInstaller: String;

function FindGhostscriptInstaller: String;
var
  FindRec: TFindRec;
  GsDir: String;
  FileNameLower: String;
begin
  Result := '';
  GsDir := ExpandConstant('{app}\ghostscript\');
  if FindFirst(GsDir + 'gs*.exe', FindRec) then
  begin
    try
      repeat
        FileNameLower := Lowercase(FindRec.Name);
        if (Pos('c.exe', FileNameLower) = 0) and
           ((Pos('w32', FileNameLower) > 0) or (Pos('w64', FileNameLower) > 0) or (Pos('setup', FileNameLower) > 0) or (Pos('install', FileNameLower) > 0)) then
        begin
          Result := GsDir + FindRec.Name;
          Exit;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function ShouldInstallGhostscript: Boolean;
begin
  FoundGsInstaller := FindGhostscriptInstaller();
  Result := (FoundGsInstaller <> '');
end;

function GetGhostscriptInstallerPath(Param: String): String;
begin
  Result := FoundGsInstaller;
end;
