// micro:bit (MakeCode JavaScript) - Yahboom ゲームハンドル用
// microbit/main.py (MicroPython) と同じ内容。50ms ごとに USB シリアル (115200bps) へ
//   "p1,p2,R,G,B,Y"
// を 1 行送る。
//   p1: ジョイスティック前後 (P1 のアナログ値 0..1023、前に倒すと小さくなる)
//   p2: ジョイスティック左右 (P2 のアナログ値 0..1023、右に倒すと小さくなる)
//   R, G, B, Y: 赤(P13) / 緑(P14) / 青(P15) / 黄(P16) ボタン。押されていれば 1
// ボタンは押すと GND につながる (アクティブ Low) ので、プルアップして反転する。

pins.setPull(DigitalPin.P13, PinPullMode.PullUp)
pins.setPull(DigitalPin.P14, PinPullMode.PullUp)
pins.setPull(DigitalPin.P15, PinPullMode.PullUp)
pins.setPull(DigitalPin.P16, PinPullMode.PullUp)

serial.redirectToUSB()
serial.setBaudRate(BaudRate.BaudRate115200)
basic.showIcon(IconNames.Heart)

basic.forever(function () {
    let p1 = pins.analogReadPin(AnalogPin.P1)
    let p2 = pins.analogReadPin(AnalogPin.P2)
    let red = 1 - pins.digitalReadPin(DigitalPin.P13)
    let green = 1 - pins.digitalReadPin(DigitalPin.P14)
    let blue = 1 - pins.digitalReadPin(DigitalPin.P15)
    let yellow = 1 - pins.digitalReadPin(DigitalPin.P16)
    serial.writeLine("" + p1 + "," + p2 + "," + red + "," + green + "," + blue + "," + yellow)
    basic.pause(50)
})
