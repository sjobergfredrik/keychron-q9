"""Keychron Q9 (ISO, knob, PID 0x0193) keymap via VIA raw HID.

    uv run --with hidapi python q9_keymap.py dump            # print current keymap
    uv run --with hidapi python q9_keymap.py backup FILE     # save all layers to JSON
    uv run --with hidapi python q9_keymap.py apply           # write the layout below
    uv run --with hidapi python q9_keymap.py restore FILE    # write a backup back

Firmware speaks VIA protocol 9 = old QMK keycodes (MO(n)=0x5100|n, LT=0x4000).
Symbols assume macOS input source "Swedish - Pro" (@ = Option+2, { = Shift+Option+8).
Layers: 0 Mac base, 1 Win base, 2 Mac Fn2 (media/RGB), 3 hold Caps (nav), 4 hold Fn (num/sym).
"""
import json
import sys

import hid

VID, PID, ROWS, COLS = 0x3434, 0x0193, 4, 15

TRNS = 0x0001
S, A, G = 0x0200, 0x0400, 0x0800  # Shift, Option, Cmd modifiers
LSFT, LALT, LGUI = 0xE1, 0xE2, 0xE3
K = {c: 0x04 + i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz")}
N = {str((i + 1) % 10): 0x1E + i for i in range(10)}  # '1'..'9','0'
GRV, MINS, RBRC, ESC, BSPC = 0x35, 0x2D, 0x30, 0x29, 0x2A
RIGHT, LEFT, DOWN, UP, PGUP, PGDN = 0x4F, 0x50, 0x51, 0x52, 0x4B, 0x4E
F = [0x3A + i for i in range(12)]  # F1..F12


def LT(layer, kc):
    return 0x4000 | (layer << 8) | kc


# Physical ISO_53 key -> matrix position (from qmk keyboards/keychron/q9/iso_encoder)
TOP = [(0, c) for c in range(13)]            # Tab Q W E R T Y U I O P Å Del-cap
HOME = [(1, c) for c in range(12)]           # Caps A S D F G H J K L Ö Ä
BOTTOM = [(2, c) for c in range(12)]         # Shift <> Z X C V B N M , . -
RSHIFT, UPKEY = (2, 13), (2, 14)
LAYOUT_KEYS = TOP + HOME + BOTTOM + [(0, 13), (0, 14), (1, 13), (1, 14), (1, 12),
                                     RSHIFT, UPKEY, (3, 0), (3, 1), (3, 2), (3, 6),
                                     (3, 10), (3, 11), (3, 12), (3, 13), (3, 14)]

PLAN = {
    0: {HOME[0]: LT(3, ESC)},  # Caps: tap Esc, hold nav layer
    4: {  # hold Fn (first key right of Space)
        TOP[0]: GRV,  # §
        **{TOP[i]: N[d] for i, d in enumerate("1234567890", start=1)},
        TOP[11]: MINS,  # +
        TOP[12]: BSPC,
        HOME[0]: ESC,
        HOME[1]: A | N["2"],          # @
        HOME[2]: A | N["4"],          # $
        HOME[3]: S | A | N["8"],      # {
        HOME[4]: S | A | N["9"],      # }
        HOME[5]: A | N["7"],          # |
        HOME[6]: S | A | N["7"],      # \
        HOME[7]: A | N["8"],          # [
        HOME[8]: A | N["9"],          # ]
        HOME[9]: S | N["8"],          # (
        HOME[10]: S | N["9"],         # )
        HOME[11]: A | RBRC,           # ~ (dead key: then Space)
        **{BOTTOM[i]: F[i - 2] for i in range(2, 12)},  # Z..- = F1..F10
        RSHIFT: F[10],
        UPKEY: F[11],
    },
    3: {  # hold Caps: navigation
        TOP[2]: G | K["w"],           # Cmd+W
        TOP[6]: PGUP,
        TOP[7]: A | LEFT,             # word left
        TOP[8]: UP,
        TOP[9]: A | RIGHT,            # word right
        HOME[2]: LSFT,
        HOME[3]: LALT,
        HOME[4]: LGUI,
        HOME[6]: G | LEFT,            # start of line
        HOME[7]: LEFT,
        HOME[8]: DOWN,
        HOME[9]: RIGHT,
        HOME[10]: G | RIGHT,          # end of line
        BOTTOM[2]: G | K["z"],
        BOTTOM[3]: G | K["x"],
        BOTTOM[4]: G | K["c"],
        BOTTOM[5]: G | K["v"],
        BOTTOM[7]: PGDN,
    },
}
CLEAR_FIRST = {3}  # layers whose physical keys are reset to transparent before applying


def open_dev():
    path = next(d["path"] for d in hid.enumerate(VID, PID)
                if d["usage_page"] == 0xFF60 and d["usage"] == 0x61)
    dev = hid.device()
    dev.open_path(path)
    return dev


def cmd(dev, payload):
    dev.write(bytes([0]) + bytes(payload) + bytes(32 - len(payload)))
    return dev.read(32, 1000)


def read_all(dev):
    layers = cmd(dev, [0x11])[1]
    size, buf, off = layers * ROWS * COLS * 2, [], 0
    while off < size:
        n = min(28, size - off)
        buf += cmd(dev, [0x12, off >> 8, off & 0xFF, n])[4:4 + n]
        off += n
    return [[[buf[((l * ROWS + r) * COLS + c) * 2] << 8 | buf[((l * ROWS + r) * COLS + c) * 2 + 1]
              for c in range(COLS)] for r in range(ROWS)] for l in range(layers)]


def set_key(dev, layer, row, col, kc):
    cmd(dev, [0x05, layer, row, col, kc >> 8, kc & 0xFF])


def dump(keymap):
    for l, rows in enumerate(keymap):
        print(f"--- layer {l}")
        for r in rows:
            print(" ".join(f"{k:04x}" for k in r))


def main():
    action = sys.argv[1]
    dev = open_dev()
    current = read_all(dev)
    if action == "dump":
        dump(current)
    elif action == "backup":
        json.dump(current, open(sys.argv[2], "w"))
        print("saved", sys.argv[2])
    elif action in ("apply", "restore"):
        if action == "restore":
            target = json.load(open(sys.argv[2]))
        else:
            target = [[row[:] for row in layer] for layer in current]
            for layer in CLEAR_FIRST:
                for r, c in LAYOUT_KEYS:
                    target[layer][r][c] = TRNS
            for layer, keys in PLAN.items():
                for (r, c), kc in keys.items():
                    target[layer][r][c] = kc
        changed = 0
        for l in range(len(target)):
            for r in range(ROWS):
                for c in range(COLS):
                    if target[l][r][c] != current[l][r][c]:
                        set_key(dev, l, r, c, target[l][r][c])
                        changed += 1
        ok = read_all(dev) == target
        print(f"wrote {changed} keys, read-back {'OK' if ok else 'MISMATCH'}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
