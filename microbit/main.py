# micro:bit (MicroPython) - Yahboom ゲームハンドル用
# 50ms ごとに "p1,p2,R,G,B,Y" を USB シリアル (115200bps) に送る。
#   p1: ジョイスティック前後 (P1 のアナログ値 0..1023、前に倒すと小さくなる)
#   p2: ジョイスティック左右 (P2 のアナログ値 0..1023、右に倒すと小さくなる)
#   R, G, B, Y: 赤(P13) / 緑(P14) / 青(P15) / 黄(P16) ボタン。押されていれば 1
# ボタンは押すと GND につながる (アクティブ Low) ので、プルアップして反転する。
from microbit import pin1, pin2, pin13, pin14, pin15, pin16, display, Image, sleep

BUTTONS = (pin13, pin14, pin15, pin16)  # 赤, 緑, 青, 黄
for p in BUTTONS:
    p.set_pull(p.PULL_UP)

display.show(Image.HEART)

while True:
    p1 = pin1.read_analog()
    p2 = pin2.read_analog()
    r, g, b, y = [1 - p.read_digital() for p in BUTTONS]
    print("{},{},{},{},{},{}".format(p1, p2, r, g, b, y))
    sleep(50)
