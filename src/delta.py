# -*- coding: utf-8 -*-
"""
增量更新补丁（应用端）
======================
格式：固定头 + zlib 压缩的指令流
  头  : magic(8) + 新文件 sha256(32) + old_size(u64) + new_size(u64)
        + block(u32) + payload_len(u64)
  指令: OP_COPY(offset u64, length u32) / OP_DATA(length u32, bytes)

补丁由 tools/make_patch.py 生成，原理同 rsync：旧文件切块建索引，
在新文件上滚动校验，未变化的部分只记「从旧文件哪一段拷贝」，
只有真正变化的字节才作为数据塞进补丁，所以补丁通常比整个 exe 小得多。

应用端只依赖标准库，PyInstaller 打包无需额外模块。
"""
import hashlib
import os
import struct
import zlib

MAGIC = b"CXDLTA1\0"
OP_COPY = 1
OP_DATA = 2
HEADER = struct.Struct("<8s32sQQIQ")


def apply_patch(old_path, patch_path, out_path, on_progress=None):
    """
    把 patch 应用到 old_path，生成完整的 out_path（新 exe）。
    on_progress(done, total) 用于进度条；校验失败抛 ValueError。
    """
    with open(patch_path, "rb") as f:
        head = f.read(HEADER.size)
        if len(head) != HEADER.size:
            raise ValueError("补丁文件不完整")
        magic, sha, old_size, new_size, _block, payload_len = HEADER.unpack(head)
        if magic != MAGIC:
            raise ValueError("不是本程序的更新补丁")
        payload = zlib.decompress(f.read(payload_len))

    if not os.path.isfile(old_path) or os.path.getsize(old_path) != old_size:
        raise ValueError("本地程序版本与补丁不匹配")
    with open(old_path, "rb") as f:
        old = f.read()

    out = bytearray()
    pos = 0
    n = len(payload)
    while pos < n:
        op = payload[pos]
        pos += 1
        if op == OP_COPY:
            off, ln = struct.unpack_from("<QI", payload, pos)
            pos += 12
            out += old[off:off + ln]
        elif op == OP_DATA:
            ln = struct.unpack_from("<I", payload, pos)[0]
            pos += 4
            out += payload[pos:pos + ln]
            pos += ln
        else:
            raise ValueError("补丁内容损坏")
        if on_progress:
            on_progress(min(len(out), new_size), new_size)

    if len(out) != new_size:
        raise ValueError("合并后大小不符")
    if hashlib.sha256(out).hexdigest() != sha.hex():
        raise ValueError("合并后校验失败")

    with open(out_path, "wb") as f:
        f.write(out)
    return out_path
