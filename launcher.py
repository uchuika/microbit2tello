"""配布用 exe の入口。

  TelloBlocks.exe blocks [--dry-run] [--no-microbit]   ブロック画面
  TelloBlocks.exe handle [--dry-run]                   ハンドルで直接操縦
引数なしは blocks。
"""
import sys
import traceback


def _pause():
    try:
        input("\nEnter キーで閉じます...")
    except (EOFError, KeyboardInterrupt):
        pass


def main():
    mode, rest = "blocks", sys.argv[1:]
    if rest and rest[0] in ("blocks", "handle"):
        mode, rest = rest[0], rest[1:]
    try:
        if mode == "handle":
            import tello_microbit
            tello_microbit.main(rest)
        else:
            import block_server
            block_server.main(rest)
    except SystemExit as e:
        if isinstance(e.code, str):  # micro:bit 未接続などのメッセージ付き終了
            print(e.code)
            _pause()
            return 1
        return e.code or 0
    except Exception:
        traceback.print_exc()
        _pause()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
