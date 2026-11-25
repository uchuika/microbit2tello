# ハンドルのピン調査用 (使い捨て)。値が変わったピンだけ表示する。
from microbit import pin0, pin1, pin2, pin8, pin12, pin13, pin14, pin15, pin16, sleep

DIG = [("P0", pin0), ("P8", pin8), ("P12", pin12), ("P13", pin13),
       ("P14", pin14), ("P15", pin15), ("P16", pin16)]
for _, p in DIG:
    p.set_pull(p.PULL_UP)

prev = {}
tick = 0
while True:
    out = []
    for name, p in DIG:
        v = p.read_digital()
        if prev.get(name) != v:
            out.append("{}={}".format(name, v))
            prev[name] = v
    for name, p in (("X1", pin1), ("Y2", pin2)):
        v = p.read_analog()
        if abs(prev.get(name, -999) - v) > 80:
            out.append("{}={}".format(name, v))
            prev[name] = v
    if out:
        print(" ".join(out))
    tick += 1
    if tick % 40 == 0:
        print("alive", pin1.read_analog(), pin2.read_analog())
    sleep(50)
