# -*- coding: utf-8 -*-
"""分类密码回归测试：加密、24 小时有效期、多条提示、找回、导出、对话框"""
import json
import os
import shutil
import sys
import tempfile
import time
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import assets
import main as M
import store as S

ok = True


def check(label, cond):
    global ok
    print(("  PASS " if cond else "  FAIL ") + label)
    if not cond:
        ok = False


def main():
    d = tempfile.mkdtemp(prefix="cxhe_lock_")
    st = S.Store(os.path.join(d, "apps_data.json"), os.path.join(d, "icons"))
    g = st.add_group("系统优化", "gear", "#FF8A3D", "mima123",
                     [{"q": "我最喜欢的颜色？", "a": "蓝色"},
                      {"q": "my city?", "a": "Beijing"}])
    gid = g["id"]
    g2 = st.add_group("私密", "lock", "#B6A4FF", "pw2",
                      [{"q": "我最喜欢的动物？", "a": "猫"}])
    gid2 = g2["id"]
    print("[1] 数据层")
    check("新建即上锁", st.group_locked(gid) and st.group_locked(gid2))
    check("错密码不放行", not st.unlock_group(gid, "bad") and st.group_locked(gid))
    check("两条提示都保存", len(st.group_hints(gid)) == 2)
    check("答错不通过", not st.check_group_answer(gid, "红色"))
    check("答对第一条通过", st.check_group_answer(gid, "  蓝色 "))
    check("答对第二条通过（忽略大小写）", st.check_group_answer(gid, "beijing"))
    check("提示按分类独立", not st.check_group_answer(gid2, "蓝色")
          and st.check_group_answer(gid2, "猫"))
    check("对密码不限长度/字符", st.unlock_group(gid, "mima123"))
    check("解锁 24h 内有效", not st.group_locked(gid))
    st.group_by_id(gid)["unlocked_at"] = time.time() - S.LOCK_SECONDS - 1
    check("超过 24h 重新上锁", st.group_locked(gid))

    st.add_app(r"C:\Windows\System32\notepad.exe", group=gid, name="notepad")
    check("锁定分类的程序不出现在全部程序",
          all(i.get("group") != gid for i in st.visible_items(S.G_ALL)))
    st.unlock_group(gid, "mima123")
    check("解锁后出现在全部程序",
          any(i.get("group") == gid for i in st.visible_items(S.G_ALL)))

    e = os.path.join(d, "exp.json")
    st.export_to(e)
    data = json.load(open(e, encoding="utf-8"))
    grp = [x for x in data["groups"] if x["id"] == gid][0]
    check("导出包含密码和多条提示",
          grp.get("password") == "mima123" and len(grp.get("pw_hints", [])) == 2)

    print("[2] 对话框")
    root = tk.Tk()
    root.withdraw()
    bank = assets.EmojiBank()
    try:
        dlg = M.GroupPasswordDialog(root, bank, st, gid)
        dlg.update_idletasks()
        dlg.var.set("bad")
        dlg._ok()
        check("密码框：错误提示且不关闭",
              dlg.winfo_exists() and "不对" in dlg.lbl_err.cget("text"))
        dlg.var.set("mima123")
        dlg._ok()
        check("密码框：正确后通过", dlg._result is True)

        st.group_by_id(gid)["unlocked_at"] = 0
        st.save()
        rec = M.GroupRecoverDialog(root, bank, st, gid)
        rec.update_idletasks()
        check("找回框列出全部提示", len(rec.hints) == 2)
        rec.var.set("猫")
        rec._ok()
        check("找回：别的分类答案不通过", "不对" in rec.lbl_err.cget("text"))
        rec.var.set("蓝色")
        rec._ok()
        check("找回：答对直接显示密码", "mima123" in rec.lbl_pw.cget("text"))
        check("找回：答对即解锁", not st.group_locked(gid))
        rec._ok()
        check("找回：确认后关闭并返回成功", rec._result is True)

        print("[3] 新建分类对话框")
        gd = M.GroupDialog(root, bank, st, None)
        gd.update_idletasks()
        gd.var_name.set("私密2")
        gd.var_pw.set("abc")
        gd._save()
        check("有密码缺密保时拒绝保存",
              gd.winfo_exists() and "密保" in gd.lbl_err.cget("text"))

        hd = M.GroupHintsDialog(root, bank, gd.hints)
        hd.update_idletasks()
        check("密保默认三组问答", len(hd._vars) == 3)
        hd._save()
        check("密保全空时拒绝保存",
              hd.winfo_exists() and "至少" in hd.lbl_err.cget("text"))
        hd._vars[0][0].set("我的生日？")
        hd._save()
        check("只填问题不给答案时拒绝",
              hd.winfo_exists() and "第" in hd.lbl_err.cget("text"))
        hd._vars[0][1].set("0101")
        hd._add()
        hd._vars[-1][0].set("我的学校？")
        hd._vars[-1][1].set("一中")
        hd._save()
        check("密保保存成功并去掉空行",
              hd._result is True and len(hd.hints) == 2)

        gd.hints = hd.hints
        gd._paint_hints()
        gd._save()
        g2s = [x for x in st.groups if x["name"] == "私密2"]
        check("多组密保保存成功", len(g2s) == 1 and g2s[0]["password"] == "abc"
              and len(g2s[0]["pw_hints"]) == 2)

        ed = M.GroupDialog(root, bank, st, st.group_by_id(gid))
        ed.update_idletasks()
        check("编辑时密码/多组密保已回填",
              ed.var_pw.get() == "mima123" and len(ed.hints) == 2
              and ed.hints[1]["q"] == "my city?")
        ed.var_pw.set("")
        ed._save()
        check("清空密码后不再上锁", not st.group_locked(gid)
              and not st.group_by_id(gid)["password"])
    finally:
        root.destroy()
        shutil.rmtree(d, ignore_errors=True)

    print("结果:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
