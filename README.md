# 程序收纳盒

一个卡通风格的 Windows 程序收藏夹：把常用的 exe、桌面快捷方式拖进窗口即可收藏，
单击启动，右键编辑 / 删除 / 分类 / 换图标。单文件绿色版，数据和图标都放在 exe 同目录，
拷走整个文件夹就能换电脑使用。

当前版本：**v0.1.2**

## v0.1.2 修复内容

### 1. 删除桌面快捷方式后收纳盒失效（已修复）

旧版把拖进来的 `.lnk` 路径原样存进 `apps_data.json`，等于收藏的是
「桌面快捷方式」这个引用；桌面那份一删，卡片启动时就报「文件不存在」。

现在拖入快捷方式时会解析出**真实程序 exe 的绝对路径**，同时记下启动参数、
工作目录和图标，再写入数据。桌面快捷方式只是入口，删掉不影响收纳盒：

- 新增 `src/linkfix.py`：Win32 COM / pywin32 / PowerShell 三级解析 `.lnk`，
  毫秒级完成，历史数据在程序启动时自动升级（日志见 exe 同目录 `修复日志.txt`）；
- 桌面快捷方式已经被删的历史条目，会按显示名到开始菜单 / 桌面找同名快捷方式尝试恢复；
- 同一快捷方式重复拖入会按真实目标去重。

### 2. 从收纳盒启动程序很慢（已修复）

旧版用 `os.startfile(.lnk)` 启动，`ShellExecute` 要先解析快捷方式、加载外壳扩展，
实测 IDM 在 `.lnk` 上要 **2.3 秒**才返回，期间界面还会被卡住。

现在对 exe 直接走 `CreateProcess`（与资源管理器双击同一条路径），
只有文档、`.url`、`.msc` 这类必须交给系统关联的才走 `ShellExecute`：

| 启动方式 | 返回耗时 |
| --- | --- |
| 旧版 `.lnk` + ShellExecute | ~2.3 s |
| 新版 直达 exe（CreateProcess） | ~0.02 s |

### 3. 界面保持不变

主界面、主题配色、卡片布局、交互习惯均未改动，只替换了底层快捷方式处理与启动逻辑。

## 目录结构

```
src/                源码
  main.py           入口与主界面
  store.py          数据层（apps_data.json）
  linkfix.py        快捷方式独立化（.lnk -> 绝对路径）
  spawner.py        快速启动（CreateProcess / ShellExecute）
  iconutil.py       图标提取
  widgets.py        卡片 / 按钮 / 对话框
  theme.py          主题与字体
  assets.py         路径与 emoji 资源
  build.spec        PyInstaller 打包配置
tools/              调试与测试脚本
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
