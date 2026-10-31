# -*- coding: utf-8 -*-
"""把图标素材准备好放进 src/assets/（构建期运行一次）。"""
import os
import shutil
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src", "assets")
os.makedirs(SRC, exist_ok=True)

ico = os.path.join(ROOT, "launcher_orange.ico")
png = os.path.join(ROOT, "launcher_orange.png")

if os.path.exists(ico):
    shutil.copy2(ico, os.path.join(SRC, "launcher_orange.ico"))
    print("已复制 launcher_orange.ico")
if os.path.exists(png):
    shutil.copy2(png, os.path.join(SRC, "launcher_orange.png"))
    im = Image.open(png).convert("RGBA")
    print("源图尺寸:", im.size)
    for size in (56, 112, 256):
        out = im.resize((size, size), Image.LANCZOS)
        out.save(os.path.join(SRC, "logo_%d.png" % size), optimize=True)
        print("已生成 logo_%d.png" % size)
print("assets 目录:", SRC)
