"""Generate assets/multiterm.ico (no third-party imaging libs needed)."""
import os
import struct

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "multiterm.ico")

BG = (0x0B, 0x0D, 0x14)
PANE = (0x1B, 0x20, 0x2E)
PANE2 = (0x26, 0x2C, 0x3E)
ACCENT = (0x6C, 0x8C, 0xFF)
GREEN = (0x3D, 0xDC, 0x97)


def draw(size):
    """Return size*size list of (r, g, b, a) - four terminal panes."""
    px = [(0, 0, 0, 0)] * (size * size)

    def put(x, y, c):
        if 0 <= x < size and 0 <= y < size:
            px[y * size + x] = (c[0], c[1], c[2], 255)

    def rect(x0, y0, x1, y1, c):
        for y in range(y0, y1):
            for x in range(x0, x1):
                put(x, y, c)

    r = max(2, size // 8)
    # rounded background
    for y in range(size):
        for x in range(size):
            dx = min(x, size - 1 - x)
            dy = min(y, size - 1 - y)
            if dx < r and dy < r and (r - dx) ** 2 + (r - dy) ** 2 > r * r:
                continue
            put(x, y, BG)

    m = max(1, size // 10)          # margin
    g = max(1, size // 16)          # gap
    w = (size - 2 * m - g) // 2
    h = (size - 2 * m - g) // 2
    quads = [(m, m, PANE2), (m + w + g, m, PANE),
             (m, m + h + g, PANE), (m + w + g, m + h + g, PANE)]
    for qx, qy, col in quads:
        rect(qx, qy, qx + w, qy + h, col)

    # a prompt caret in the first pane, cursor blocks in the others
    px0, py0 = quads[0][0] + max(1, w // 6), quads[0][1] + max(1, h // 3)
    steps = max(2, w // 5)
    for i in range(steps):
        put(px0 + i, py0 + i, GREEN)
        put(px0 + i, py0 - i, GREEN)
        put(px0 + i, py0 + i + 1, GREEN)
        put(px0 + i, py0 - i + 1, GREEN)
    cw = max(2, w // 4)
    chh = max(1, h // 6)
    rect(px0 + steps + max(1, w // 8), py0 - chh // 2,
         px0 + steps + max(1, w // 8) + cw, py0 - chh // 2 + chh, ACCENT)
    for i, (qx, qy, _c) in enumerate(quads[1:]):
        col = (0xA6, 0x6C, 0xFF) if i == 2 else ACCENT
        rect(qx + max(1, w // 6), qy + max(1, h // 3),
             qx + max(1, w // 6) + max(2, w // 5),
             qy + max(1, h // 3) + max(1, h // 6), col)
    return px


def png_free_ico(sizes=(16, 24, 32, 48, 64)):
    images = []
    for s in sizes:
        px = draw(s)
        rows = []
        for y in range(s - 1, -1, -1):       # bottom-up
            row = bytearray()
            for x in range(s):
                r, g, b, a = px[y * s + x]
                row += bytes((b, g, r, a))
            rows.append(bytes(row))
        xor = b"".join(rows)
        mask_row = (s + 31) // 32 * 4
        andmask = b"\x00" * (mask_row * s)
        header = struct.pack("<IiiHHIIiiII", 40, s, s * 2, 1, 32, 0,
                             len(xor) + len(andmask), 0, 0, 0, 0)
        images.append((s, header + xor + andmask))

    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for s, data in images:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32,
                               len(data), offset)
        offset += len(data)
        blobs += data
    return out + entries + blobs


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as fh:
        fh.write(png_free_ico())
    print("wrote " + OUT)


if __name__ == "__main__":
    main()
