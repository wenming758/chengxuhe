# -*- coding: utf-8 -*-
"""
分类栏拖拽改序回归测试。

模拟用户用鼠标把第一条「用户自建分类」拖到末尾：
  <ButtonPress-1> 记起点 → <B1-Motion> 跨过阈值进入拖拽 →
  <B1-Motion> 移到目标行 → <ButtonRelease-1> 落下重排。
校验：
  1) store.groups 顺序变化正确（首条跑到末位）
  2) 重排结果落盘到 JSON（进程外可读回）
  3) 全程无 Tk 回调异常

数据目录重定向到临时副本，不碰真实数据。
"""
import json, os, shutil, sys, tempfile, time, traceback

SRC = r"C:/Users/Administrator/Desktop/DIY/汇总程序/src"
PROJ = os.path.dirname(SRC)
sys.path.insert(0, SRC)

# 造一份确定性的数据：4 个用户分类 + 1 个程序
SEED = {
    "groups": [
        {"id": "g1", "name": "分类甲", "emoji": "folder2"},
        {"id": "g2", "name": "分类乙", "emoji": "folder2"},
        {"id": "g3", "name": "分类丙", "emoji": "folder2"},
        {"id": "g4", "name": "分类丁", "emoji": "folder2"},
    ],
    "items": [
        {"id": "a1", "name": "示例程序", "path": "notepad.exe",
         "groups": ["g1"], "note": ""}
    ],
}

TMP = tempfile.mkdtemp(prefix="wbtest_drag_")
os.makedirs(os.path.join(TMP, "icons"), exist_ok=True)
with open(os.path.join(TMP, "apps_data.json"), "w", encoding="utf-8") as f:
    json.dump(SEED, f, ensure_ascii=False, indent=2)

import assets as A
A.app_dir = lambda: TMP
A.data_path = lambda: os.path.join(TMP, "apps_data.json")
A.icon_dir = lambda: os.path.join(TMP, "icons")
import main as M

ERRS = []
RESULT = {}


def pump():
    app.root.update_idletasks()
    app.root.update()
    time.sleep(0.05)
    app.root.update()


def run():
    try:
        before = [g["name"] for g in app.store.groups]
        RESULT["before"] = before
        assert before == ["分类甲", "分类乙", "分类丙", "分类丁"], before

        rows = app._user_group_rows()
        assert len(rows) == 4, "用户分类行数=%d" % len(rows)
        dragged = rows[0]          # 分类甲
        last = rows[-1]            # 分类丁
        dragged_gid = dragged.gid

        # 1) 按下（按在拖拽行中心）
        cx = dragged.winfo_width() // 2
        cy = dragged.winfo_height() // 2
        dragged.event_generate("<ButtonPress-1>", x=cx, y=cy)
        app.root.update()

        # 2) 移动到「超过阈值」的位置（同 x，y 大幅下移）—— 触发拖拽态
        #    目标绝对 Y 取末行中线 + 几像素 → 落点索引 = len(行) = 末尾
        target_abs_y = last.winfo_rooty() + last.winfo_height() // 2 + 5
        my = target_abs_y - dragged.winfo_rooty()   # 转成相对拖拽行的 y
        dragged.event_generate("<B1-Motion>", x=cx, y=cy + 12)   # 先超阈值
        app.root.update_idletasks()
        dragged.event_generate("<B1-Motion>", x=cx, y=my)        # 移到末行
        app.root.update_idletasks()

        # 校验：已进入拖拽态
        RESULT["dragging"] = dragged._dragging
        # 校验：插入条可见（落点应为末尾）
        idx_now = app._drop_index(target_abs_y)
        RESULT["drop_index"] = idx_now

        # 3) 松开 → 重排
        dragged.event_generate("<ButtonRelease-1>", x=cx, y=my)
        app.root.update_idletasks()
        app.root.update()

        after = [g["name"] for g in app.store.groups]
        RESULT["after"] = after
        # 首条应跑到末位
        RESULT["reorder_ok"] = (after == ["分类乙", "分类丙", "分类丁", "分类甲"])

        # store 内顺序也要对
        RESULT["store_gids"] = [g["id"] for g in app.store.groups]

        # ---- 场景 2：点击（不拖）一个用户分类行 → 切换分类 ----
        # 关键回归点：_select_group 会 _render_groups() 把当前 GroupRow 自身销毁，
        # _on_release 的非拖拽分支如果事后还碰 self 就会 invalid command name。
        # 没动 → 直接在中心点按下+松开。
        rows2 = app._user_group_rows()
        click_target = rows2[0]              # 当前第一条（分类乙）
        cx2 = click_target.winfo_width() // 2
        cy2 = click_target.winfo_height() // 2
        click_target.event_generate("<ButtonPress-1>", x=cx2, y=cy2)
        click_target.event_generate("<ButtonRelease-1>", x=cx2, y=cy2)
        app.root.update_idletasks()
        app.root.update()
        RESULT["after_click_cur"] = app.cur_group
        RESULT["after_click_ok"] = (app.cur_group == click_target.gid)
    except Exception:
        ERRS.append(traceback.format_exc())
    app.root.quit()


app = M.Launcher()
app.root.report_callback_exception = lambda e, v, t: ERRS.append(
    "".join(traceback.format_exception(e, v, t)))
app.root.after(700, run)
app.root.after(30000, app.root.quit)
app.run()

# ---- 进程外读回 JSON，校验落盘 ----
on_disk = False
try:
    with open(os.path.join(TMP, "apps_data.json"), encoding="utf-8") as f:
        data = json.load(f)
    on_disk = [g["name"] for g in data["groups"]] == \
        ["分类乙", "分类丙", "分类丁", "分类甲"]
except Exception as e:
    ERRS.append("读 JSON 失败: %s" % e)

print(">>> 拖拽前顺序: %s" % RESULT.get("before"))
print(">>> 进入拖拽态: %s" % RESULT.get("dragging"))
print(">>> 落点索引:   %s (应为 4)" % RESULT.get("drop_index"))
print(">>> 拖拽后顺序: %s" % RESULT.get("after"))
print(">>> 重排正确:   %s" % RESULT.get("reorder_ok"))
print(">>> JSON 落盘:  %s" % on_disk)
print(">>> 点击切换(非拖)后 cur_group: %s (应为 %s) → %s" % (
    RESULT.get("after_click_cur"), "g2",
    "PASS" if RESULT.get("after_click_ok") else "FAIL"))
print(">>> 回调异常:   %s" % (ERRS or "无"))

ok = bool(RESULT.get("reorder_ok")) and on_disk \
    and bool(RESULT.get("after_click_ok")) and not ERRS
print(">>> 总体: %s" % ("PASS" if ok else "FAIL"))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
