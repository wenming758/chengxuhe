# -*- coding: utf-8 -*-
"""
极简 PNG 编码器（纯标准库）
==========================
程序运行时不需要 Pillow：提取到的图标（RGBA 原始像素）直接用它写成 PNG，
既能落盘到 icons/ 缓存目录，也能转成 base64 交给 Tk 显示。
"""
import base64
import struct
import zlib


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def encode_png(width, height, rgba, level=9):
    """把 RGBA 原始字节编码为 PNG 字节流。"""
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        raw += rgba[y * stride:(y + 1) * stride]
    out = b"\x89PNG\r\n\x1a\n"
    out += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    out += _chunk(b"IDAT", zlib.compress(bytes(raw), level))
    out += _chunk(b"IEND", b"")
    return out


def encode_png_b64(width, height, rgba, level=9):
    return base64.b64encode(encode_png(width, height, rgba, level)).decode("ascii")


def write_png(path, width, height, rgba, level=9):
    data = encode_png(width, height, rgba, level)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


# ============================================================ 缩放
def resize_rgba(src, sw, sh, dw, dh):
    """
    RGBA 缩放（纯 Python，程序运行时不需要 Pillow）。
      · 缩小：按源像素块做面积平均（抗锯齿，不会闪烁噪点）
      · 放大：双线性插值（边缘平滑）
    """
    if sw == dw and sh == dh:
        return bytes(src)
    out = bytearray(dw * dh * 4)
    if dw <= 0 or dh <= 0:
        return bytes(out)

    if dw < sw or dh < sh:
        # ---- 面积平均 ----
        for dy in range(dh):
            y0 = dy * sh / float(dh)
            y1 = (dy + 1) * sh / float(dh)
            iy0, iy1 = int(y0), max(int(y1), int(y0) + 1)
            if iy1 > sh:
                iy1 = sh
            for dx in range(dw):
                x0 = dx * sw / float(dw)
                x1 = (dx + 1) * sw / float(dw)
                ix0, ix1 = int(x0), max(int(x1), int(x0) + 1)
                if ix1 > sw:
                    ix1 = sw
                r = g = b = a = 0
                n = 0
                for yy in range(iy0, iy1):
                    row = yy * sw * 4
                    for xx in range(ix0, ix1):
                        i = row + xx * 4
                        r += src[i]
                        g += src[i + 1]
                        b += src[i + 2]
                        a += src[i + 3]
                        n += 1
                o = (dy * dw + dx) * 4
                if n:
                    out[o] = r // n
                    out[o + 1] = g // n
                    out[o + 2] = b // n
                    out[o + 3] = a // n
    else:
        # ---- 双线性 ----
        for dy in range(dh):
            fy = (dy + 0.5) * sh / float(dh) - 0.5
            y0 = int(fy)
            wy = fy - y0
            if y0 < 0:
                y0, wy = 0, 0.0
            y1 = min(y0 + 1, sh - 1)
            for dx in range(dw):
                fx = (dx + 0.5) * sw / float(dw) - 0.5
                x0 = int(fx)
                wx = fx - x0
                if x0 < 0:
                    x0, wx = 0, 0.0
                x1 = min(x0 + 1, sw - 1)
                i00 = (y0 * sw + x0) * 4
                i01 = (y0 * sw + x1) * 4
                i10 = (y1 * sw + x0) * 4
                i11 = (y1 * sw + x1) * 4
                o = (dy * dw + dx) * 4
                for k in range(4):
                    v = (src[i00 + k] * (1 - wx) * (1 - wy) +
                         src[i01 + k] * wx * (1 - wy) +
                         src[i10 + k] * (1 - wx) * wy +
                         src[i11 + k] * wx * wy)
                    out[o + k] = int(v + 0.5)
    return bytes(out)


def encode_rgba_scaled(w, h, rgba, dw, dh, level=9):
    """缩放后直接编码成 PNG 字节。"""
    return encode_png(dw, dh, resize_rgba(rgba, w, h, dw, dh), level)

