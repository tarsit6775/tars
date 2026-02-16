#!/usr/bin/env python3
"""Generate TARS app icon using pure Python (no Pillow needed)."""
import os
import struct
import zlib
import math

SIZE = 512

def create_icon():
    """Create a 512x512 PNG icon - blue circle with white T."""
    raw_data = b""
    cx, cy = SIZE // 2, SIZE // 2
    radius = SIZE // 2 - 20

    for y in range(SIZE):
        row = [0]  # PNG filter byte
        for x in range(SIZE):
            dx = x - cx
            dy = y - cy
            dist = math.sqrt(dx * dx + dy * dy)

            if dist <= radius:
                # Inside circle - blue gradient
                t = dist / radius
                pr = int(30 + 20 * (1 - t))
                pg = int(60 + 60 * (1 - t))
                pb = int(140 + 80 * (1 - t))

                # Draw T letterform
                in_t = False
                # Horizontal bar of T
                if -80 < dy < -45 and -70 < dx < 70:
                    in_t = True
                # Vertical bar of T
                if -45 <= dy < 100 and -20 < dx < 20:
                    in_t = True

                if in_t:
                    row.extend([255, 255, 255, 255])
                else:
                    alpha = 255 if dist < radius - 3 else max(0, int(255 * (radius - dist) / 3))
                    row.extend([pr, pg, pb, alpha])
            else:
                row.extend([0, 0, 0, 0])

        raw_data += bytes(row)

    # Build PNG file
    def make_chunk(chunk_type, data):
        c = chunk_type + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    ihdr_data = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += make_chunk(b"IHDR", ihdr_data)
    png += make_chunk(b"IDAT", zlib.compress(raw_data, 9))
    png += make_chunk(b"IEND", b"")

    out_path = os.path.join(os.path.dirname(__file__), "icon.png")
    with open(out_path, "wb") as f:
        f.write(png)
    print(f"Icon created: {out_path} ({os.path.getsize(out_path)} bytes)")
    return out_path

if __name__ == "__main__":
    create_icon()
