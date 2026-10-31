# -*- coding: utf-8 -*-
"""
生成彩色 emoji 资源模块 src/emoji_data.py
==========================================
Tk 8.6 用 GDI 画字，彩色 emoji（COLR/CBDT）会掉成黑白甚至豆腐块；
本机 seguiemj.ttf 里还有一批字形（⚙ 💻 💬 ➕ …）Pillow 也拿不到彩色版本。

所以这里在构建期直接取 Twemoji 的官方彩色 PNG（72x72，CC-BY 4.0），
统一缩放到 56x56 后 base64 内嵌进程序。运行时只让 Tk 解析 PNG，
不依赖任何字体，任何一台 Windows 上显示效果 100% 一致。

用法： python tools/gen_emoji.py
"""
import base64
import io
import os
import sys
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_twemoji")
OUT_PY = os.path.join(HERE, "..", "src", "emoji_data.py")

CDN = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/%s.png"
TARGET = 56          # 最终边长（显示时 subsample 得到 28 / 18）

EMOJI = [
    # ---- 界面功能 ----
    ("box",        "\U0001F4E6"),   # 包裹 / 全部程序
    ("star",       "\u2B50"),       # 常用
    ("clock",      "\U0001F554"),   # 最近
    ("rocket",     "\U0001F680"),   # 打开 / 启动
    ("plus",       "\u2795"),       # 添加
    ("pencil",     "\u270F\uFE0F"), # 编辑
    ("trash",      "\U0001F5D1\uFE0F"),  # 删除
    ("clipboard",  "\U0001F4CB"),   # 复制
    ("folder",     "\U0001F4C2"),   # 打开所在位置
    ("folder2",    "\U0001F4C1"),   # 分类
    ("search",     "\U0001F50D"),   # 搜索
    ("gear",       "\u2699\uFE0F"), # 设置
    ("palette",    "\U0001F3A8"),   # 主题 / 换图标
    ("refresh",    "\U0001F504"),   # 刷新
    ("export",     "\U0001F4E4"),   # 导出
    ("import",     "\U0001F4E5"),   # 导入
    ("save",       "\U0001F4BE"),   # 保存
    ("cross",      "\u274C"),       # 取消 / 关闭
    ("check",      "\u2705"),       # 确定
    ("warn",       "\u26A0\uFE0F"), # 警告
    ("info",       "\u2139\uFE0F"), # 说明
    ("shield",     "\U0001F6E1\uFE0F"),  # 管理员运行
    ("pin",        "\U0001F4CC"),   # 置顶
    ("tag",        "\U0001F3F7\uFE0F"),  # 标签
    ("list",       "\U0001F4CB"),   # 列表视图
    ("grid",       "\U0001F533"),   # 网格视图
    ("question",   "\u2753"),       # 帮助
    ("eyes",       "\U0001F440"),   # 详情
    ("link",       "\U0001F517"),   # 链接
    ("lock",       "\U0001F512"),   # 锁定
    ("key",        "\U0001F511"),   # 密钥
    ("sort",       "\U0001F53D"),   # 排序
    ("up",         "\u2B06\uFE0F"), # 上移
    ("down",       "\u2B07\uFE0F"), # 下移
    ("sparkles",   "\u2728"),       # 推荐 / 高亮
    ("new",        "\U0001F195"),   # 新建
    ("undo",       "\u21A9\uFE0F"), # 撤销
    ("heart",      "\u2764\uFE0F"), # 喜欢
    ("bell",       "\U0001F514"),   # 提醒
    ("magic",      "\U0001F52E"),   # 智能
    # ---- 分类候选 ----
    ("game",       "\U0001F3AE"),
    ("globe",      "\U0001F310"),
    ("memo",       "\U0001F4DD"),
    ("music",      "\U0001F3B5"),
    ("movie",      "\U0001F3AC"),
    ("picture",    "\U0001F5BC\uFE0F"),
    ("chat",       "\U0001F4AC"),
    ("chart",      "\U0001F4CA"),
    ("toolbox",    "\U0001F9F0"),
    ("hammer",     "\U0001F6E0\uFE0F"),
    ("monitor",    "\U0001F5A5\uFE0F"),
    ("laptop",     "\U0001F4BB"),
    ("cloud",      "\u2601\uFE0F"),
    ("fire",       "\U0001F525"),
    ("bulb",       "\U0001F4A1"),
    ("trophy",     "\U0001F3C6"),
    ("crown",      "\U0001F451"),
    ("medal",      "\U0001F3C5"),
    ("target",     "\U0001F3AF"),
    ("puzzle",     "\U0001F9E9"),
    ("dice",       "\U0001F3B2"),
    ("book",       "\U0001F4DA"),
    ("calendar",   "\U0001F4C5"),
    ("mail",       "\u2709\uFE0F"),
    ("phone",      "\U0001F4F1"),
    ("camera",     "\U0001F4F7"),
    ("cart",       "\U0001F6D2"),
    ("money",      "\U0001F4B0"),
    ("bank",       "\U0001F3E6"),
    ("office",     "\U0001F3E2"),
    ("home",       "\U0001F3E0"),
    ("hospital",   "\U0001F3E5"),
    ("school",     "\U0001F3EB"),
    ("car",        "\U0001F697"),
    ("plane",      "\u2708\uFE0F"),
    ("wrench",     "\U0001F527"),
    ("battery",    "\U0001F50B"),
    ("printer",    "\U0001F5A8\uFE0F"),
    ("robot",      "\U0001F916"),
    ("alien",      "\U0001F47D"),
    ("ghost",      "\U0001F47B"),
    ("map",        "\U0001F5FA\uFE0F"),
    ("anchor",     "\u2693"),
    ("gift",       "\U0001F381"),
    ("party",      "\U0001F389"),
    ("sun",        "\u2600\uFE0F"),
    ("moon",       "\U0001F319"),
    ("leaf",       "\U0001F343"),
    ("flower",     "\U0001F338"),
    ("clover",     "\U0001F340"),
    ("rainbow",    "\U0001F308"),
    # ---- 卡通装饰 ----
    ("hatch",      "\U0001F423"),
    ("balloon",    "\U0001F388"),
    ("glow",       "\U0001F31F"),
    ("teddy",      "\U0001F9F8"),
    ("lollipop",   "\U0001F36D"),
    ("cat",        "\U0001F431"),
    ("paw",        "\U0001F43E"),
    ("cake",       "\U0001F370"),
    ("apple",      "\U0001F34E"),
    ("coffee",     "\u2615"),
    ("pizza",      "\U0001F355"),
    ("ball",       "\u26BD"),
    ("candy",      "\U0001F36C"),
    ("donut",      "\U0001F369"),
    ("strawberry", "\U0001F353"),
    ("turtle",     "\U0001F422"),
    ("penguin",    "\U0001F427"),
    ("unicorn",    "\U0001F984"),
]


def filename_variants(ch):
    """Twemoji 文件名规则：码点小写十六进制用 - 连接，去掉 U+FE0F。"""
    cps = [ord(c) for c in ch]
    full = "-".join("%x" % c for c in cps)
    no_vs = "-".join("%x" % c for c in cps if c != 0xFE0F)
    base = "%x" % cps[0]
    out = []
    for v in (no_vs, full, base):
        if v and v not in out:
            out.append(v)
    return out


def fetch(ch, name):
    """下载并缓存一张 twemoji PNG，返回本地路径。"""
    os.makedirs(CACHE, exist_ok=True)
    for fn in filename_variants(ch):
        local = os.path.join(CACHE, fn + ".png")
        if os.path.exists(local) and os.path.getsize(local) > 200:
            return local, fn
        url = CDN % fn
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if len(data) > 200:
                with open(local, "wb") as f:
                    f.write(data)
                return local, fn
        except Exception:
            continue
    return None, None


def main():
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""彩色 emoji 资源（由 tools/gen_emoji.py 自动生成，请勿手改）。',
        "",
        "每个 emoji 都是 %dpx 彩色 PNG（带透明通道）的 base64 编码；" % TARGET,
        "运行时用 tk.PhotoImage(data=...) 加载，再用 subsample 取小尺寸。",
        "图形素材来自 Twemoji（CC-BY 4.0）。",
        '"""',
        "",
        "SIZE = %d" % TARGET,
        "",
        "DATA = {",
    ]
    total = 0
    ok = 0
    failed = []
    for name, ch in EMOJI:
        path, fn = fetch(ch, name)
        if not path:
            failed.append(name)
            continue
        img = Image.open(path).convert("RGBA").resize((TARGET, TARGET), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        raw = buf.getvalue()
        total += len(raw)
        ok += 1
        lines.append('    "%s": "%s",' % (name, base64.b64encode(raw).decode("ascii")))
    lines.append("}")
    lines.append("")
    lines.append("NAMES = sorted(DATA.keys())")
    lines.append("")
    with open(OUT_PY, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("已生成 %s" % OUT_PY)
    print("成功 %d / %d, PNG 合计 %.0f KB, 模块 %.0f KB"
          % (ok, len(EMOJI), total / 1024.0, os.path.getsize(OUT_PY) / 1024.0))
    if failed:
        print("下载失败:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
