# micro:bit で Tello を制御する手順

出典: [tkyko13「ドローン(Ryze Tello)をProcessingのみで飛ばした」](https://qiita.com/tkyko13/items/a873ef8a34dc3f6dc67d) / [kikpond「micro:bit + Processing で Tello」](https://qiita.com/kikpond/items/d7d6c21221e4dfb93474)

## 全体構成
```
[micro:bit] --USBシリアル 115200bps, 1行 "x,y,A,B,AB"--> [PC: Processing]
                                                            | Wi-Fi(UDP)
                                                            v
                                         [Tello 192.168.10.1 : 8889]
```
- micro:bit は Wi-Fi を持たないため、PC（Processing）が中継する。
- Tello はテキストコマンドを UDP で受ける。最初に `command` を送って SDK モードにする。

## 必要なもの
- micro:bit、USB ケーブル、DJI(Ryze) Tello、Wi-Fi 付き PC
- MakeCode（micro:bit 側）: https://makecode.microbit.org/_KD3XDP6ebejd
- Processing 3 以降 + ライブラリ `UDP`（hypermedia.net）と標準の `Serial`
- 参考リポジトリ: https://github.com/kikpond15/tello_p5_microbit（`microbit/*.hex`, `rcController/`, `simpleController/`, `udp/`）

## 手順
1. **micro:bit にプログラムを書き込む**
   - MakeCode リンクを開いて書き込む（またはリポジトリの `rcController.hex` を micro:bit ドライブにコピー）。
   - 内容: シリアル 115200bps で、加速度 X, Y とボタン A, B, A+B の状態を `x,y,A,B,AB` の形でカンマ区切り＋改行で送り続ける。
2. **Processing を準備する**
   - Processing をインストールし、「ライブラリを追加」から `UDP` を入れる。
3. **（動作確認）Processing だけで Tello を飛ばす**（記事1）
   - Tello の電源を入れ、PC の Wi-Fi を `TELLO-xxxxxx` に接続。
   - `new UDP(this, 8889)` → `udp.listen(true)` → `udp.send("command", "192.168.10.1", 8889)`。
   - キー `t`=`takeoff`、`l`=`land`、`p`=`battery?` 等で応答を確認。
4. **micro:bit を USB で PC に接続する**
5. **micro:bit 連携スケッチ（`rcController`）を実行する**（記事2）
   - `Serial.list()[0]` を 115200bps で開く → micro:bit 以外が先頭なら番号を変える。
   - `serialEvent` で 1 行読んで `split(',')` → `x, y, A, B, AB`。
   - `DroneControl.update()` が毎フレーム `rc lr fb ud yaw` を送る。

## 操作割り当て（rcController）
| 入力 | 動作 |
|---|---|
| A+B | 離陸 / 着陸 を切り替え |
| A | 上昇モード ON/OFF（ud=+30） |
| B | 下降モード ON/OFF（ud=-30） |
| 左右に傾ける（x < -511 / > 511） | 左 / 右移動（lr=±50） |
| 前後に傾ける（y < -511 / > 511） | 前進 / 後退（fb=±50） |
| 水平 | ホバリング（全 0） |
旋回（yaw）は常に 0 で、割り当てはない。

## 使う Tello SDK コマンド
`command`（SDK モード）/ `takeoff` / `land` / `rc a b c d`（-100〜100）/ `battery?` `speed?` `time?`

## 注意点
- PC は Tello の Wi-Fi に接続するので、その間インターネットは使えない。
- Tello は約 15 秒コマンドが来ないと自動着陸する。
- 記事2のコードの気になる点（記事を読んだうえでの指摘）:
  - `takeoff()` / `land()` の待機ループが `second()+2` を使うため、58〜59 秒に実行すると止まらなくなる → `millis()` に置き換える。
  - シリアルポートが `[0]` 固定。
  - 着陸時に上昇/下降フラグがリセットされない。
  - 終了時に自動で着陸しない → 緊急用に `land` / `emergency` キーを用意する。
- 屋内の広い場所で、プロペラガードを付け、バッテリー残量を確認してから飛ばす。
- どちらの記事も 2018〜2019 年のもので、5 年以上更新されていない。

## 検証
- 手順3でキー操作により離着陸し、コンソールに `ok` やバッテリー値が出ることを確認する。
- 手順5の前に、Processing で受信した `x,y,A,B,AB` を println して、傾きとボタンに値が反応することを確認する。

---

# Python 版での実行手順（このフォルダの実装）

Processing の代わりに Python で中継する。記事のコードの不具合（`second()` の無限ループ、着陸時にフラグが戻らない、ポート固定、終了時に着陸しない）は修正済み。

| ファイル | 内容 |
|---|---|
| `microbit/main.py` | micro:bit 用 MicroPython（Yahboom ハンドル用）。50ms ごとに `p1,p2,R,G,B,Y` を送る（Y=黄ボタン P16。5 値の行も受け付ける） |
| `microbit/probe.py` | ハンドルのピン調査用（使い捨て） |
| `tello_microbit.py` | PC 側の中継（シリアル → UDP） |
| `tests/test_controller.py` | 操作ロジックのテスト |

## セットアップ
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -s tests
```

## micro:bit への書き込み
```
.venv\Scripts\uflash microbit\main.py
```
uflash が止まる場合は、`uflash microbit\main.py <出力フォルダ>` で `micropython.hex` を作り、MICROBIT ドライブにコピーする。

## 実行
1. Tello なしで確認: `.venv\Scripts\python -u tello_microbit.py --dry-run`（`--show-input` で生の入力も表示）
2. Tello の電源を入れ、PC の Wi-Fi を `TELLO-xxxxxx` に接続
3. `.venv\Scripts\python -u tello_microbit.py`
   - 初回に Windows ファイアウォールの確認が出たら、Python の通信を許可する（許可しないと Tello の応答が届かない）
4. 操作（Yahboom ゲームハンドル）

| 入力 | ピン | 動作 |
|---|---|---|
| 赤ボタン | P13 | 離陸 / 着陸（押すたびに切り替え） |
| 緑ボタン | P14 | 押している間 上昇（ud=+40） |
| 青ボタン | P15 | 押している間 下降（ud=-40） |
| スティック前後 | P1 | 前進 / 後退（倒した量に比例、最大 60） |
| スティック左右 | P2 | 右 / 左（倒した量に比例、最大 60） |
| 黄ボタン + スティック左右 | P16 | 押している間 旋回（右に倒すと時計回り、最大 60）。左右の水平移動はせず、前後・上昇・下降は効く |

## ブロックプログラミング版（教育イベント用）

Scratch のようなブロックで「どのボタンで何をするか」を自由に組み立てられる。ブラウザ画面は同梱の Blockly で動くので、Tello の Wi-Fi に接続中（インターネット無し）でも使える。

```
.venv\Scripts\python -u block_server.py --dry-run --no-microbit   # Tello もハンドルも無しで練習 (画面の仮想ボタンで操作)
.venv\Scripts\python -u block_server.py --dry-run                 # ハンドルあり、Tello には送らない
.venv\Scripts\python -u block_server.py                           # 実機
```
`http://127.0.0.1:8000/` が自動で開く。ブロックを組んだら「ドローンに おくる」を押す（押すまで反映されない）。

| ブロック | 働き |
|---|---|
| イベント: 「[みどり/あお/スティック前後左右] を おしたとき」 | 押した瞬間に中のブロックを 1 回実行 |
| イベント: 「… を おしているあいだ」 | 押している間、「うごきつづける」「まわりつづける」を実行 |
| イベント: 「スティックで そうじゅうする」 | スティックの倒した量に比例して水平移動 |
| うごき | りりく / ちゃくりく / [向き]に [20〜500]cm すすむ / [右左]に [1〜360]度 / [前後左右]に ちゅうがえり |
| くりかえし | [1〜10]回くりかえす / [0.1〜10]秒 まつ |
| うごきつづける | [向き]に うごきつづける はやさ[10〜100] / まわりつづける |

- **赤ボタンは常に 離陸/着陸**（ブロックでは変えられない）。
- **安全**: 画面の大きな「とまる」ボタン（スペースキー / Esc）でどのプログラムよりも優先して着陸する。数値は範囲内に丸められ、くり返しの入れ子は 3 段まで。
- 飛んでいない時の移動ブロックは無視して「先に離陸してね」と表示。Tello がエラーを返すと、そのスクリプトは中止される（宙返りはバッテリー 50% 未満だと失敗する）。
- 組んだブロックは `programs/current.json` に保存される。「はじめの ブロックに もどす」で `programs/default.json`（上の標準操作と同じ）に戻る。
- 画面の通信は `127.0.0.1` のみ。Blockly (Apache-2.0) は `web/vendor/blockly/` に同梱。

| ファイル | 内容 |
|---|---|
| `block_server.py` | 起動スクリプト（シリアル読み取り・制御ループ・HTTP サーバー） |
| `block_runtime.py` | ブロックの検証と実行（`BlockController`, `ScriptRunner`） |
| `web/` | ブロック画面（`blocks.js` にブロック定義） |
| `tests/test_block_runtime.py` | ランタイムのテスト |

---

# 配布用パッケージ（別の PC で Python 無しに動かす）

Python と pyserial を PyInstaller で同梱するので、配布先の PC には何も入れなくてよい。**管理者権限も不要**（ユーザー単位で `%LOCALAPPDATA%\Programs\TelloBlocks` に入る）。

## 作り方（このPC）
```
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```
`.venv-build` を作ってテストを通し、`dist\` に次を作る（Inno Setup は `winget install JRSoftware.InnoSetup --scope user`）。
- `TelloBlocks-setup.exe` … インストーラー（スタートメニュー / デスクトップのショートカット、アンインストール対応）
- `TelloBlocks-portable.zip` … 展開して `Start-*.cmd` をダブルクリックするだけの版

## 配布先での使い方
- `Start-Blocks.cmd`（本番） / `Start-Blocks-Practice.cmd`（Tello もハンドルも無しで練習） / `Start-Blocks-HandleCheck.cmd`（Tello には送らない） / `Start-Handle.cmd`（ブロック無しの直接操縦）。詳細は同梱の `はじめに.txt`。
- **ファイアウォール**: Tello の応答 (UDP 8889) を受けるため `firewall_allow.cmd` で許可を登録する（ここだけ管理者の確認が出る）。setup.exe は最後のチェックで実行でき、アンインストール時に自動で削除する。断っても動作はするが、Windows の確認ダイアログで「許可」しない限り Tello に接続できない。
- micro:bit には `microbit\tello_handle.hex` を MICROBIT ドライブへコピーして書き込む。
- 署名していないので SmartScreen の警告が出る →「詳細情報」→「実行」。
- 保存したブロックは `%LOCALAPPDATA%\TelloBlocks\programs\current.json`。

---

起動時はスティックから手を離しておく（その位置を中心として記録する）。Ctrl+C でも着陸して終了する。
仕組みの解説: https://claude.ai/artifact/XVCGkYEosz6UrCQB47tYXW

---

## ライセンス

MIT License（`LICENSE` 参照）。同梱の `web/vendor/blockly/` は Blockly (Apache-2.0) のライセンスに従います。
