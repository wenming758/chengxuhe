# -*- coding: utf-8 -*-
"""
数据层
======
所有数据都存在 exe 同目录的 apps_data.json 里（绿色便携），
程序图标缓存在同目录 icons/ 下，拷走整个文件夹即可换机器使用。
"""
import json
import os
import shutil
import time
import uuid

import pngutil

APP_TITLE = "程序收纳盒"
VERSION = "1.0.0"          # 内部版本号（勿随意改动）
APP_VERSION = "v0.1.10"    # 界面展示版本号（用户要求追加，不覆盖上面的 VERSION）
AUTHOR = "wenming758"      # 软件作者

# 在线升级（优先 Gitee，仓库不可达时退回 GitHub）
UPDATE_APIS = [
    "https://gitee.com/api/v5/repos/wenming760/chengxuhe",
    "https://api.github.com/repos/wenming758/chengxuhe",
]
UPDATE_API = UPDATE_APIS[0]

# 图标缓存格式版本：低于它的条目启动时会在后台自动重抓一次
# （v2：裁掉透明留白，修掉部分 exe 被缩成小米粒的问题）
ICON_FORMAT = 2

# 虚拟分类（不落盘，仅用于筛选）
G_ALL = "__all__"
G_FAV = "__fav__"
G_RECENT = "__recent__"

# 分类密码解锁后的有效期：24 小时
LOCK_SECONDS = 24 * 3600

DEFAULT_GROUPS = [
    {"id": "g_default", "name": "未分类", "emoji": "box", "color": "#FF8A3D"},
    {"id": "g_sys", "name": "默认工具", "emoji": "gear", "color": "#9AA0B5"},
    {"id": "g_tool", "name": "工具软件", "emoji": "toolbox", "color": "#63C9F5"},
    {"id": "g_game", "name": "游戏娱乐", "emoji": "game", "color": "#B6A4FF"},
    {"id": "g_media", "name": "影音图像", "emoji": "movie", "color": "#FF9EC4"},
    {"id": "g_office", "name": "办公学习", "emoji": "book", "color": "#5FD0AE"},
]

# Windows 系统自带的常用程序（路径里 %winsys% / %win% 在 _resolve_sys_path
# 里展开成 C:\Windows\System32 / C:\Windows）。只在本机确实存在时才会被
# 预填进收藏，不存在的自动跳过——不会往用户数据里塞无效路径。
# 远程桌面 mstsc 是用户明确要求的「系统默认远程桌面管理软件」。
SYS_APP_TEMPLATES = [
    # 远程桌面连接（系统默认远程桌面管理软件）
    {"name": "远程桌面连接", "path": "%winsys%\\mstsc.exe",
     "emoji": "monitor", "group": "g_sys"},
    # 系统自带的管理 / 实用工具
    {"name": "资源管理器", "path": "%win%\\explorer.exe",
     "emoji": "folder", "group": "g_sys"},
    {"name": "任务管理器", "path": "%winsys%\\Taskmgr.exe",
     "emoji": "chart", "group": "g_sys"},
    {"name": "控制面板", "path": "%winsys%\\control.exe",
     "emoji": "gear", "group": "g_sys"},
    {"name": "注册表编辑器", "path": "%win%\\regedit.exe",
     "emoji": "wrench", "group": "g_sys"},
    {"name": "命令提示符", "path": "%winsys%\\cmd.exe",
     "emoji": "laptop", "group": "g_sys"},
    {"name": "计算器", "path": "%win%\\System32\\calc.exe",
     "emoji": "chart", "group": "g_sys"},
    {"name": "记事本", "path": "%win%\\notepad.exe",
     "emoji": "memo", "group": "g_sys"},
    {"name": "画图", "path": "%win%\\System32\\mspaint.exe",
     "emoji": "picture", "group": "g_sys"},
    {"name": "截图工具", "path": "%win%\\System32\\SnippingTool.exe",
     "emoji": "camera", "group": "g_sys"},
    {"name": "磁盘清理", "path": "%winsys%\\cleanmgr.exe",
     "emoji": "refresh", "group": "g_sys"},
    {"name": "系统信息", "path": "%winsys%\\msinfo32.exe",
     "emoji": "info", "group": "g_sys"},
    {"name": "服务管理", "path": "%winsys%\\services.msc",
     "emoji": "gear", "group": "g_sys"},
    {"name": "事件查看器", "path": "%winsys%\\eventvwr.msc",
     "emoji": "info", "group": "g_sys"},
    {"name": "设备管理器", "path": "%winsys%\\devmgmt.msc",
     "emoji": "wrench", "group": "g_sys"},
]


def _resolve_sys_path(p):
    """展开系统程序模板里的 %win% / %winsys% 占位符。"""
    win = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or \
        r"C:\Windows"
    winsys = os.path.join(win, "System32")
    return p.replace("%win%", win).replace("%winsys%", winsys)


def _default_sys_apps():
    """返回本机确实存在的系统默认程序条目列表（已展开路径）。"""
    out = []
    for t in SYS_APP_TEMPLATES:
        real = _resolve_sys_path(t["path"])
        if os.path.exists(real):
            it = dict(t)
            it["path"] = real
            out.append(it)
    return out

SUPPORTED_EXT = (
    ".exe", ".lnk", ".bat", ".cmd", ".com", ".msc", ".ps1",
    ".url", ".jar", ".appref-ms", ".vbs",
)


def now_str():
    return time.strftime("%Y-%m-%d %H:%M")


def normalize_hints(hints):
    """密码提示统一成 [{"q": 问题, "a": 答案}]，全空的条目丢掉。"""
    out = []
    for h in hints or []:
        if not isinstance(h, dict):
            continue
        q = str(h.get("q", "")).strip()
        a = str(h.get("a", "")).strip()
        if q or a:
            out.append({"q": q, "a": a})
    return out


class Store(object):
    def __init__(self, path, icon_dir):
        self.path = path
        self.icon_dir = icon_dir
        self.groups = []
        self.items = []
        self.settings = {"sort": "manual", "view": "grid"}
        self.load()

    # -------------------------------------------------- 读写
    def load(self):
        raw = None
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                # 数据坏了就备份一份，别把用户的东西直接冲掉
                try:
                    shutil.copy2(self.path, self.path + ".bad")
                except Exception:
                    pass
                raw = None
        if not isinstance(raw, dict):
            raw = {}
        # 老数据里可能没有「默认工具」分类，补一个（插在未分类之后）
        groups = raw.get("groups") or [dict(g) for g in DEFAULT_GROUPS]
        if not any(g.get("id") == "g_sys" for g in groups):
            insert_at = 1
            for i, g in enumerate(groups):
                if g.get("id") == "g_default":
                    insert_at = i + 1
                    break
            groups.insert(insert_at, dict(DEFAULT_GROUPS[1]))
        self.groups = groups
        # 分类密码：默认留空 = 不加密；unlocked_at 是最近一次输对密码的时间。
        # 密码提示按分类独立保存，可有多条；老数据里的单条 pw_q/pw_a 自动迁移。
        for g in self.groups:
            g.setdefault("password", "")
            g.setdefault("unlocked_at", 0)
            hints = normalize_hints(g.get("pw_hints"))
            if not hints and (g.get("pw_q") or g.get("pw_a")):
                hints = normalize_hints([{"q": g.get("pw_q", ""),
                                          "a": g.get("pw_a", "")}])
            g["pw_hints"] = hints
            g.pop("pw_q", None)
            g.pop("pw_a", None)
        self.items = raw.get("items") or []
        st = raw.get("settings") or {}
        self.settings = {
            "sort": st.get("sort", "manual"),
            "view": st.get("view", "grid"),
            # 记住上次退出时所在的分类，下次启动直接进入该分类
            "last_group": st.get("last_group", ""),
            # 上次自动检查更新的时间戳（秒），避免每次启动都请求
            "update_checked_at": st.get("update_checked_at", 0),
        }
        # 兜底修补字段
        for it in self.items:
            it.setdefault("id", uuid.uuid4().hex[:12])
            it.setdefault("name", os.path.basename(it.get("path", "")) or "未命名")
            it.setdefault("args", "")
            it.setdefault("note", "")
            it.setdefault("group", "g_default")
            it.setdefault("icon", "")
            it.setdefault("emoji", "rocket")
            it.setdefault("pinned", False)
            it.setdefault("count", 0)
            it.setdefault("added", now_str())
            it.setdefault("last", "")
            # 独立启动信息：工作目录 + 来源快捷方式（历史数据迁移用）
            it.setdefault("workdir", "")
            it.setdefault("lnk", "")
            it.setdefault("iconv", 0)
        # 预填系统默认程序：只补「本机存在 + 尚未收藏过」的，不重复、不覆盖
        existing = set()
        for it in self.items:
            try:
                existing.add(os.path.normcase(os.path.abspath(it.get("path", ""))))
            except Exception:
                pass
        added_sys = False
        for t in _default_sys_apps():
            key = os.path.normcase(os.path.abspath(t["path"]))
            if key in existing:
                continue
            it = {
                "id": uuid.uuid4().hex[:12],
                "name": t["name"],
                "path": t["path"],
                "args": "",
                "note": "系统默认程序",
                "group": t["group"],
                "icon": "",
                "emoji": t.get("emoji", "gear"),
                "pinned": False,
                "count": 0,
                "added": now_str(),
                "last": "",
            }
            self.items.append(it)
            existing.add(key)
            added_sys = True
        if added_sys:
            self.save()


    def save(self):
        data = {
            "app": APP_TITLE,
            "version": VERSION,
            "saved": now_str(),
            "settings": self.settings,
            "groups": self.groups,
            "items": self.items,
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # -------------------------------------------------- 分类
    def group_by_id(self, gid):
        for g in self.groups:
            if g["id"] == gid:
                return g
        return None

    def group_name(self, gid):
        g = self.group_by_id(gid)
        return g["name"] if g else "未分类"

    def add_group(self, name, emoji="folder2", color="#FF8A3D", password="",
                  hints=None):
        g = {"id": "g_" + uuid.uuid4().hex[:8], "name": name,
             "emoji": emoji, "color": color,
             "password": password or "", "unlocked_at": 0,
             "pw_hints": normalize_hints(hints)}
        self.groups.append(g)
        self.save()
        return g

    def update_group(self, gid, **kw):
        g = self.group_by_id(gid)
        if g:
            g.update(kw)
            self.save()
        return g

    # -------------------------------------------------- 分类密码
    def group_locked(self, gid):
        """分类是否处于「需要输密码」状态（没过密码 / 解锁已超 24 小时）。"""
        g = self.group_by_id(gid)
        if not g or not g.get("password"):
            return False
        try:
            at = float(g.get("unlocked_at") or 0)
        except Exception:
            at = 0
        return (time.time() - at) >= LOCK_SECONDS

    def unlock_group(self, gid, password):
        """校验密码；正确则记住解锁时间（24 小时内免输），返回是否通过。"""
        g = self.group_by_id(gid)
        if not g or not g.get("password"):
            return True
        if (password or "") != g.get("password"):
            return False
        g["unlocked_at"] = time.time()
        self.save()
        return True

    def set_group_password(self, gid, password, hints=None):
        """设置 / 修改 / 清空分类密码；只要密码变了就重新上锁。"""
        g = self.group_by_id(gid)
        if not g:
            return None
        password = password or ""
        if password != (g.get("password") or ""):
            g["password"] = password
            g["unlocked_at"] = 0
        g["pw_hints"] = normalize_hints(hints)
        self.save()
        return g

    def group_hints(self, gid):
        g = self.group_by_id(gid)
        if not g:
            return []
        return [h for h in normalize_hints(g.get("pw_hints"))
                if h["q"] and h["a"]]

    def check_group_answer(self, gid, answer):
        """任意一条密码提示的答案匹配即通过（忽略首尾空格和英文大小写）。"""
        ans = (answer or "").strip().casefold()
        if not ans:
            return False
        for h in self.group_hints(gid):
            if ans == h["a"].strip().casefold():
                return True
        return False

    def remove_group(self, gid, fallback="g_default"):
        """删分类：里面的程序挪到 fallback，不删程序。"""
        self.groups = [g for g in self.groups if g["id"] != gid]
        for it in self.items:
            if it.get("group") == gid:
                it["group"] = fallback
        self.save()

    def count_of_group(self, gid):
        items = self._without_locked(self.items, gid)
        if gid == G_ALL:
            return len(items)
        if gid == G_FAV:
            return sum(1 for i in items if i.get("pinned"))
        if gid == G_RECENT:
            return sum(1 for i in items if i.get("last"))
        return sum(1 for i in self.items if i.get("group") == gid)

    def _without_locked(self, items, gid=None):
        """锁着的分类里的程序，不从「全部 / 置顶 / 最近」里漏出来。"""
        locked = {g["id"] for g in self.groups if self.group_locked(g["id"])}
        if not locked:
            return items
        return [i for i in items
                if i.get("group") not in locked or i.get("group") == gid]

    # -------------------------------------------------- 程序条目
    def get(self, aid):
        for it in self.items:
            if it.get("id") == aid:
                return it
        return None

    def find_by_path(self, path):
        low = os.path.normcase(os.path.abspath(path))
        for it in self.items:
            if os.path.normcase(os.path.abspath(it.get("path", ""))) == low:
                return it
        return None

    def find_by_lnk(self, lnk):
        """同一个桌面快捷方式（解析前）是否已经收藏过。"""
        if not lnk:
            return None
        low = os.path.normcase(os.path.abspath(lnk))
        for it in self.items:
            src = it.get("lnk") or ""
            if src and os.path.normcase(os.path.abspath(src)) == low:
                return it
        return None

    def add_app(self, path, name=None, group=None, note="", args="",
                emoji=None, icon_file=None, workdir="", lnk=""):
        it = {
            "id": uuid.uuid4().hex[:12],
            "name": name or os.path.splitext(os.path.basename(path))[0],
            "path": path,
            "args": args,
            "workdir": workdir,
            "lnk": lnk,
            "note": note,
            "group": group or (self.groups[0]["id"] if self.groups else "g_default"),
            "icon": icon_file or "",
            "iconv": ICON_FORMAT,
            "emoji": emoji or "rocket",
            "pinned": False,
            "count": 0,
            "added": now_str(),
            "last": "",
        }
        self.items.append(it)
        return it

    def update_app(self, aid, **kw):
        it = self.get(aid)
        if it:
            it.update(kw)
            self.save()
        return it

    def remove_app(self, aid):
        it = self.get(aid)
        if not it:
            return
        self.items = [i for i in self.items if i.get("id") != aid]
        # 顺手清掉图标缓存
        f = it.get("icon")
        if f:
            p = os.path.join(self.icon_dir, f)
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        self.save()

    def record_launch(self, aid):
        it = self.get(aid)
        if it:
            it["count"] = int(it.get("count", 0)) + 1
            it["last"] = now_str()
            self.save()

    # -------------------------------------------------- 图标缓存
    ICON_SIZE = 48          # 卡片用 48px；预览/高清场景同图放大也够用

    def cache_icon(self, rgba_tuple):
        """把 (w,h,rgba) 统一缩到 64x64 存成 PNG，返回文件名。"""
        if not rgba_tuple:
            return ""
        w, h, data = rgba_tuple
        name = "ic_%s_%d.png" % (uuid.uuid4().hex[:10], int(time.time() * 1000) % 1000000)
        path = os.path.join(self.icon_dir, name)
        try:
            png = pngutil.encode_rgba_scaled(w, h, data, self.ICON_SIZE, self.ICON_SIZE)
            with open(path, "wb") as f:
                f.write(png)
        except Exception:
            return ""
        return name

    # -------------------------------------------------- 筛选 / 排序
    def visible_items(self, gid, keyword="", sort="manual"):
        out = list(self.items)
        if gid == G_FAV:
            out = [i for i in out if i.get("pinned")]
        elif gid == G_RECENT:
            out = [i for i in out if i.get("last")]
        elif gid not in (G_ALL, "", None):
            out = [i for i in out if i.get("group") == gid]
        out = self._without_locked(out, gid)

        kw = (keyword or "").strip().lower()
        if kw:
            def hit(i):
                return (kw in i.get("name", "").lower()
                        or kw in i.get("path", "").lower()
                        or kw in i.get("note", "").lower())
            out = [i for i in out if hit(i)]

        if sort == "name":
            out.sort(key=lambda i: i.get("name", ""))
        elif sort == "count":
            out.sort(key=lambda i: -int(i.get("count", 0)))
        elif sort == "recent":
            out.sort(key=lambda i: i.get("last") or "", reverse=True)
        elif sort == "added":
            out.sort(key=lambda i: i.get("added") or "", reverse=True)
        else:  # manual：置顶优先，其余保持添加顺序
            out.sort(key=lambda i: 0 if i.get("pinned") else 1)
        return out

    # -------------------------------------------------- 导入导出
    def export_to(self, path):
        data = {
            "app": APP_TITLE, "version": VERSION, "saved": now_str(),
            "settings": self.settings, "groups": self.groups, "items": self.items,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def import_from(self, path, merge=True):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        added = 0
        if not merge:
            self.groups = data.get("groups") or self.groups
            self.items = data.get("items") or []
            added = len(self.items)
        else:
            known = {g["id"] for g in self.groups}
            for g in data.get("groups", []):
                if g.get("id") not in known:
                    self.groups.append(g)
                    known.add(g.get("id"))
            exist = {os.path.normcase(os.path.abspath(i.get("path", "")))
                     for i in self.items}
            for it in data.get("items", []):
                key = os.path.normcase(os.path.abspath(it.get("path", "")))
                if key in exist:
                    continue
                it.setdefault("id", uuid.uuid4().hex[:12])
                self.items.append(it)
                exist.add(key)
                added += 1
        self.save()
        return added
