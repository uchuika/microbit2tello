; Inno Setup 6 — 管理者権限なし (ユーザー単位) のインストーラー
; build.ps1 が dist\TelloBlocks を作ってからコンパイルする
#define AppName "Tello ブロック"
#define AppVer "1.0.0"

[Setup]
AppId=TelloBlocksEducation
AppName={#AppName}
AppVersion={#AppVer}
DefaultDirName={autopf}\TelloBlocks
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=TelloBlocks-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\TelloBlocks.exe
DisableProgramGroupPage=yes

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作る"; Flags: unchecked
Name: "firewall"; Description: "ファイアウォールの許可を登録する（Tello の応答を受けるため。管理者の確認が出ます）"

[Files]
Source: "..\dist\TelloBlocks\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Tello ブロック（本番）"; Filename: "{app}\TelloBlocks.exe"; Parameters: "blocks"
Name: "{group}\Tello ブロック（れんしゅう）"; Filename: "{app}\TelloBlocks.exe"; Parameters: "blocks --dry-run --no-microbit"
Name: "{group}\Tello ブロック（ハンドル確認）"; Filename: "{app}\TelloBlocks.exe"; Parameters: "blocks --dry-run"
Name: "{group}\Tello ハンドル操縦"; Filename: "{app}\TelloBlocks.exe"; Parameters: "handle"
Name: "{group}\ファイアウォールの許可を登録"; Filename: "{app}\firewall_allow.cmd"
Name: "{group}\micro:bit 用プログラム"; Filename: "{app}\microbit"
Name: "{group}\はじめに"; Filename: "{app}\はじめに.txt"
Name: "{group}\アンインストール"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Tello ブロック"; Filename: "{app}\TelloBlocks.exe"; Parameters: "blocks"; Tasks: desktopicon

[Run]
Filename: "{app}\firewall_allow.cmd"; Parameters: "/q"; Tasks: firewall; Flags: runhidden waituntilterminated; StatusMsg: "ファイアウォールを設定中..."

[UninstallRun]
Filename: "{app}\firewall_remove.cmd"; Parameters: "/q"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveFirewall"
