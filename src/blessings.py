# -*- coding: utf-8 -*-
"""
顶栏祝福语
==========
每条祝福语配一个 emoji（assets/emoji_data 里的名字，彩色图片渲染，
Tk 文本里的 unicode emoji 在 Windows 上显示不出颜色），
再带一个生效时段：早上说早安、深夜催睡觉，比纯随机更像人话。

时段是 [start, end)，start > end 表示跨零点；两个 None 表示全天。
"""
import random
import time

# (emoji, 文案, 起始小时, 结束小时)
PHRASES = [
    ("sun", "美好的一天从早晨开始", 5, 9),
    ("coffee", "早安，先喝杯温水再开工", 5, 9),
    ("flower", "早起的这几分钟属于你自己", 5, 10),
    ("sparkles", "今天也会顺利得让人意外", 5, 11),
    ("rocket", "手头的事，一件一件都会做完", 9, 12),
    ("star", "认真的人最好看，加油", 9, 13),
    ("medal", "又坚持了一天，很了不起", 9, 22),
    ("pizza", "到点了，午饭要吃香一点", 11, 14),
    ("donut", "忙归忙，别忘了加餐", 11, 15),
    ("music", "下午容易犯困，起来走两步", 13, 18),
    ("battery", "喝口水，给自己充个电", 13, 19),
    ("leaf", "望望窗外绿色，眼睛会谢谢你", 13, 19),
    ("clover", "好运正在路上，再耐心一点", 12, 22),
    ("bulb", "卡住的时候，先离开座位一下", 10, 21),
    ("gift", "辛苦一天，晚上对自己好一点", 17, 22),
    ("balloon", "今天也辛苦了，笑一个", 17, 23),
    ("candy", "晚风很温柔，回家路上慢一点", 17, 23),
    ("cake", "该收工了，剩下的明天再战", 18, 23),
    ("moon", "夜深了，早点睡比什么都重要", 21, 5),
    ("heart", "别熬啦，明天还要见面", 22, 3),
    ("glow", "今晚的星星替你守着", 20, 6),
    ("rainbow", "慢慢来，反而比较快", None, None),
    ("magic", "愿你今天遇到的都是好消息", None, None),
    ("party", "小事也值得庆祝一下", None, None),
    ("paw", "水喝够了，精神才会好", None, None),
    ("trophy", "桌面收拾干净，效率跟着翻倍", None, None),
    ("home", "常用的都收好，用着才顺手", None, None),
    ("target", "先把最要紧的那一件做掉", None, None),
    ("unicorn", "好消息正在赶来的路上", None, None),
]

INTERVAL_MS = 5 * 60 * 1000        # 每 5 分钟换一条


def _in_range(hour, start, end):
    if start is None:
        return True
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end      # 跨零点


def candidates(hour=None):
    """当前时段能说的祝福语（含全天通用的）。"""
    if hour is None:
        hour = time.localtime().tm_hour
    out = [p for p in PHRASES if _in_range(hour, p[2], p[3])]
    return out or [p for p in PHRASES if p[2] is None] or list(PHRASES)


def pick(exclude=None):
    """随机取一条，尽量不和上一条重复。"""
    pool = candidates()
    if exclude:
        rest = [p for p in pool if p[1] != exclude]
        pool = rest or pool
    return random.choice(pool)
