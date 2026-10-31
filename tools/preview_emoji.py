# -*- coding: utf-8 -*-
"""把生成的 emoji 拼成一张预览图，肉眼确认彩色渲染是否正常。"""
import base64, io, os, sys
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import emoji_data

names = emoji_data.NAMES
cols = 10
cell = 64
rows = (len(names) + cols - 1) // cols
sheet = Image.new("RGB", (cols * cell, rows * (cell + 14)), (255, 255, 255))
d = ImageDraw.Draw(sheet)
for i, n in enumerate(names):
    img = Image.open(io.BytesIO(base64.b64decode(emoji_data.DATA[n]))).convert("RGBA")
    x = (i % cols) * cell
    y = (i // cols) * (cell + 14)
    sheet.paste(img, (x + 4, y + 4), img)
    d.text((x + 4, y + cell), n[:11], fill=(80, 80, 80))
sheet.save(os.path.join(HERE, "_emoji_sheet.png"))
print("ok", sheet.size, len(names))
