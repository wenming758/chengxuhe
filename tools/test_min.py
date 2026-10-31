# -*- coding: utf-8 -*-
"""最小复现：完整 Launcher + dnd hook，不发消息，只验证初始化和退出。"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import assets as A
import main as M

tmp = os.path.join(ROOT, "_dndtest")
if os.path.isdir(tmp):
    shutil.rmtree(tmp)
os.makedirs(tmp)
A.app_dir = lambda: tmp
A.data_path = lambda: os.path.join(tmp, "apps_data.json")
A.icon_dir = lambda: os.path.join(tmp, "icons")

app = M.Launcher()
app.root.geometry("900x640")
app.root.update()
print("init ok, dnd_ok =", app.dnd_ok)
print("items =", len(app.store.items), "cards =", len(app.cards))
app.root.after(400, lambda: (print("about to destroy"), app.root.destroy()))
try:
    app.run()
except Exception as e:
    import traceback
    traceback.print_exc()
print("退出完成")
shutil.rmtree(tmp, ignore_errors=True)
