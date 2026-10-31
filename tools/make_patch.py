# -*- coding: utf-8 -*-
"""
生成增量更新补丁（发布端用）
============================
用法：
    python tools/make_patch.py 旧版.exe 新版.exe 输出.bin

原理同 rsync：旧文件按 block 切块建 (adler32, blake2b) 索引，
在新文件上滚动校验；命中就写 COPY(offset,len)，没命中的字节写 DATA。
最终指令 + 字面量一起 zlib 压紧，补丁只包含真正变化的字节。
"""
import hashlib
import os
import struct
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
import delta  # noqa: E402

M = 65521


def _strong(buf):
    return hashlib.blake2b(buf, digest_size=16).digest()


def build_patch(old, new, block=4096):
    index = {}
    for off in range(0, len(old) - block + 1, block):
        chunk = old[off:off + block]
        weak = zlib.adler32(chunk) & 0xFFFFFFFF
        index.setdefault(weak, []).append((off, _strong(chunk)))

    instr = bytearray()
    literals = 0
    copies = 0

    def emit_data(start, end):
        nonlocal literals
        if end <= start:
            return
        blob = new[start:end]
        instr.append(delta.OP_DATA)
        instr.extend(struct.pack("<I", len(blob)))
        instr.extend(blob)
        literals += len(blob)

    def emit_copy(off, ln):
        nonlocal copies
        instr.append(delta.OP_COPY)
        instr.extend(struct.pack("<QI", off, ln))
        copies += 1

    size = len(new)
    start = 0          # 未命中区间的起点
    pos = 0
    if size >= block:
        win = new[0:block]
        ad = zlib.adler32(win) & 0xFFFFFFFF
        a, b = ad & 0xFFFF, ad >> 16
        while pos + block <= size:
            cands = index.get((b << 16) | a)
            hit = None
            if cands:
                sh = _strong(new[pos:pos + block])
                for off, h in cands:
                    if h == sh:
                        hit = off
                        break
            if hit is not None:
                emit_data(start, pos)
                emit_copy(hit, block)
                pos += block
                start = pos
                if pos + block <= size:
                    ad = zlib.adler32(new[pos:pos + block]) & 0xFFFFFFFF
                    a, b = ad & 0xFFFF, ad >> 16
                continue
            if pos + block >= size:
                break
            old_byte = new[pos]
            new_byte = new[pos + block]
            a = (a - old_byte + new_byte) % M
            b = (b - block * old_byte + a - 1) % M
            pos += 1
    emit_data(start, size)

    payload = zlib.compress(bytes(instr), 9)
    head = delta.HEADER.pack(delta.MAGIC, hashlib.sha256(new).digest(),
                             len(old), len(new), block, len(payload))
    return head + payload, copies, literals


def main():
    if len(sys.argv) != 4:
        print("用法: python tools/make_patch.py 旧版.exe 新版.exe 输出.bin")
        return 1
    old_p, new_p, out_p = sys.argv[1:4]
    old = open(old_p, "rb").read()
    new = open(new_p, "rb").read()
    t = time.time()
    blob, copies, literals = build_patch(old, new)
    with open(out_p, "wb") as f:
        f.write(blob)
    print("patch: %s  %.2f MB  (原文件 %.2f MB, 节省 %.0f%%)" % (
        out_p, len(blob) / 1048576.0, len(new) / 1048576.0,
        100 - len(blob) * 100.0 / max(1, len(new))))
    print("COPY %d 段, 新增字面量 %.0f KB, 用时 %.1fs" % (
        copies, literals / 1024.0, time.time() - t))
    return 0


if __name__ == "__main__":
    sys.exit(main())
