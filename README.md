# 程序收纳盒

一个卡通风格的 Windows 程序收藏夹：把常用的 exe、桌面快捷方式拖进窗口即可收藏，
单击启动，右键编辑 / 删除 / 分类 / 换图标。单文件绿色版，数据和图标都放在 exe 同目录，
拷走整个文件夹就能换电脑使用。

当前版本：**v0.1.3**

## 界面预览

![主界面](docs/screenshot-main.png)

| 右键菜单 | 设置菜单 |
| --- | --- |
| ![右键菜单](docs/screenshot-menu.png) | ![设置菜单](docs/screenshot-settings.png) |

## v0.1.3 修复内容

### 1. 部分程序图标在收纳盒里只有「小米粒」大（已修复）

一些 exe（如 IDM 绿色版）从系统 JUMBO 图像列表拿到的是一张 256×256 画布，
真正的图标只画在左上角 48×48 区域。旧版把整张画布缩到 48px，图标自然只剩
几个像素。现在提取后会先按不透明像素包围盒裁掉透明留白，再缩放缓存；
旧缓存（`iconv < 2`）会在启动后由后台线程自动重抓一次，界面无需任何操作。

### 2. 检测更新 + 增量更新（新增）

「设置 → 检测更新」现在优先查 GitHub Releases（Gitee 作为兜底）。发现新版本时：

- 如果发布里带 `patch_旧版_to_新版.bin` 增量包，就只下载这个补丁（通常几 MB），
  在本地用滚动校验 + zlib 合并出新版 exe，`sha256` 校验通过后才替换；
- 补丁缺失或合并失败时才回退下载完整安装包；
- 全程用进度条展示「下载增量补丁… / 正在合并更新…」，替换仍由原来的
  `update_helper.bat` 在退出后完成，只覆盖 exe 本身，`apps_data.json` 和
  `icons/` 原样保留。

### 3. v0.1.2 的修复一并包含

拖入快捷方式后删除桌面 `.lnk` 不再失效（存真实 exe 路径 + 参数 + 工作目录，
启动走 CreateProcess，实测 IDM 从 2.3 秒降到 0.02 秒）；界面、主题、布局与
操作方式完全不变。

## 目录结构

```
src/                源码
  main.py           入口与主界面
  store.py          数据层（apps_data.json）
  linkfix.py        快捷方式独立化（.lnk -> 绝对路径）
  spawner.py        快速启动（CreateProcess / ShellExecute）
  iconutil.py       图标提取（裁透明留白）
  delta.py          增量补丁合并（rsync 式滚动校验）
  widgets.py        卡片 / 按钮 / 对话框
  theme.py          主题与字体
  assets.py         路径与 emoji 资源
  build.spec        PyInstaller 打包配置
tools/              调试与测试脚本（make_patch.py 生成增量补丁）
使用说明.md          用户手册
程序收纳盒.exe       已打包的单文件程序
```

## 构建

```bash
pip install pyinstaller windnd pywin32
python -m PyInstaller src/build.spec --noconfirm --clean
```

产物：`dist/程序收纳盒.exe`（单文件，无需 Python 环境）。

## 数据与隐私

- `apps_data.json`、`icons/` 是本机用户数据，已加入 `.gitignore`，不会提交到仓库；
- 源码中不包含任何账号、密码或令牌，发布与推送使用本机 Git 凭据。
