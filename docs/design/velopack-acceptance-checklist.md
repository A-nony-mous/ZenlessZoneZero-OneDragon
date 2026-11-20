# Velopack 分布式交付 Windows 人工验收清单

- 关联 Issue：PLAY-2 / PLAY-5
- 依据：`docs/design/velopack-distribution.md` 第 5 节验证矩阵「栏目 2：交人类在 Windows 上验」
- 目标分支：`feat/velopack`
- 适用环境：Windows 10 / 11 x64，已安装 Git、uv、.NET SDK（用于安装 `vpk`）
- 状态：**未执行**。本清单由 Tester 整理，供人类在 Windows 真机上逐条执行并记录结果；arm-1 是 aarch64 Linux，无法代替本清单的任一条。

> 说明：清单里所有命令都从**仓库根目录**开始执行（即 `ZenlessZoneZero-OneDragon\`，下文用 `<仓库根目录>` 指代）。每条都有明确的期望结果和断言命令，不要只看一眼就判通过。执行完把「实际结果」填进第 7 节记录表。

## 0. 执行前准备

1. 切到待验分支并确认提交：

   ```powershell
   cd <仓库根目录>
   git switch feat/velopack
   git log --oneline -5
   git status --short
   ```

   期望：`git status --short` 里没有 `src/`、`deploy/`、`.github/` 的未提交修改。

2. 安装依赖：

   ```powershell
   uv sync --group dev
   ```

   期望：命令退出码为 0，`.venv\Scripts\python.exe` 存在。

3. 安装 Velopack 命令行工具：

   ```powershell
   dotnet tool install -g vpk
   vpk --version
   ```

   期望：`vpk --version` 输出版本号（不是「找不到命令」）。

4. 准备干净的打包输出目录（避免上一次的旧产物干扰断言）：

   ```powershell
   Remove-Item -Recurse -Force .\deploy\dist -ErrorAction SilentlyContinue
   New-Item -ItemType Directory -Force .\deploy\dist | Out-Null
   ```

## 1. 构建单目录产物（对应验收标准 1）

> 与设计文档的差异（已修正）：设计原文先 `cd deploy` 再执行 `pyinstaller`，之后 `--packDir deploy\dist\OneDragon` 这个相对路径就不再成立。这里统一成从仓库根目录执行，`--packDir` 保持 `deploy\dist\OneDragon`。

```powershell
cd <仓库根目录>
uv run pyinstaller deploy\OneDragon-Portable.spec --noconfirm --clean
```

期望：

- 退出码为 0。
- 存在 `deploy\dist\OneDragon\OneDragon.exe`。
- 存在 `deploy\dist\OneDragon\_internal\`（单目录模式，不是单文件）。

断言命令：

```powershell
Test-Path .\deploy\dist\OneDragon\OneDragon.exe
Test-Path .\deploy\dist\OneDragon\_internal
(Get-ChildItem .\deploy\dist\OneDragon -Recurse -File | Measure-Object).Count
```

前两行都应为 `True`，第三行记录文件总数备用。

## 2. 打第 1 个版本包 `0.1.0-beta.1`（对应验收标准 1）

```powershell
cd <仓库根目录>
vpk pack `
  --packId "ZenlessZoneZero-OneDragon" `
  --packVersion "0.1.0-beta.1" `
  --packDir "deploy\dist\OneDragon" `
  --mainExe "OneDragon.exe" `
  --runtime win-x64 `
  --outputDir "deploy\dist\releases"
```

期望：

- 退出码为 0。
- `--runtime win-x64` 不能省；省掉会按 x86 打包，64 位 Python 动态库加载失败。
- 版本号不带前导 `v`（SemVer 2.0.0）。

## 3. 用同一份代码打第 2 个版本包 `0.1.0-beta.2`（对应验收标准 1、3）

输出目录必须与第 1 个版本相同，Velopack 才能生成完整的更新元数据。

```powershell
cd <仓库根目录>
vpk pack `
  --packId "ZenlessZoneZero-OneDragon" `
  --packVersion "0.1.0-beta.2" `
  --packDir "deploy\dist\OneDragon" `
  --mainExe "OneDragon.exe" `
  --runtime win-x64 `
  --outputDir "deploy\dist\releases"
```

期望：退出码为 0。

## 4. 打包产物断言（对应验收标准 1）

```powershell
Get-ChildItem .\deploy\dist\releases | Select-Object Name, Length
```

期望文件都在（文件名以实际 `vpk` 输出为准，用下面的模式匹配）：

```powershell
Test-Path .\deploy\dist\releases\RELEASES
Test-Path .\deploy\dist\releases\releases.win.json
(Get-ChildItem .\deploy\dist\releases -Filter "*win-Portable.zip").Count
(Get-ChildItem .\deploy\dist\releases -Filter "*Setup.exe").Count
(Get-ChildItem .\deploy\dist\releases -Filter "*0.1.0-beta.1-full.nupkg").Count
(Get-ChildItem .\deploy\dist\releases -Filter "*0.1.0-beta.2-full.nupkg").Count
```

期望：前四行断言分别为 `True`、`True`、`1`、`1`；两个 nupkg 的计数各为 `1`。

再确认版本元数据里有两个版本：

```powershell
(Get-Content .\deploy\dist\releases\releases.win.json -Raw | ConvertFrom-Json).Assets |
  Select-Object -ExpandProperty Version
```

期望：输出里同时包含 `0.1.0-beta.1` 和 `0.1.0-beta.2`。

## 5. 便携版解压启动与首启播种（对应验收标准 2）

1. 解压便携包到**全新空目录**（示例 `C:\TestOneDragon`，目录必须不存在或为空）：

   ```powershell
   $zip = (Get-ChildItem .\deploy\dist\releases -Filter "*win-Portable.zip" | Select-Object -First 1).FullName
   Remove-Item -Recurse -Force C:\TestOneDragon -ErrorAction SilentlyContinue
   Expand-Archive -Path $zip -DestinationPath C:\TestOneDragon
   Get-ChildItem C:\TestOneDragon | Select-Object Name
   ```

   期望：解压目录根层有 `OneDragon.exe`、`Update.exe`、`current\`。

2. 从解压目录根层启动（不要进 `current\` 里启动）：

   ```powershell
   Start-Process -FilePath C:\TestOneDragon\OneDragon.exe -WorkingDirectory C:\TestOneDragon
   ```

   等待 30–60 秒完成首启播种，让主窗口出现。

3. 断言根层目录生成：

   ```powershell
   cd C:\TestOneDragon
   Test-Path .\config
   Test-Path .\assets
   Test-Path .\custom
   Test-Path .\.log
   Test-Path .\.bundle_seed_version
   ```

   期望：5 行全部为 `True`。

4. 断言四类只读资源文件数（数字取自设计文档第 5 节；如果仓库资源在改造期间有增删，记录实际值并说明）：

   ```powershell
   (Get-ChildItem -Path .\assets\template -Recurse -File).Count      # 期望 1820
   (Get-ChildItem -Path .\assets\ui -Recurse -File).Count            # 期望 10
   (Get-ChildItem -Path .\assets\text -Recurse -File).Count          # 期望 8
   (Get-ChildItem -Path .\assets\game_data -Recurse -File).Count     # 期望 178
   ```

5. 记录版本标记内容备用：

   ```powershell
   Get-Content .\.bundle_seed_version
   ```

   期望：文件内容非空。

6. 关闭应用：

   ```powershell
   Get-Process OneDragon -ErrorAction SilentlyContinue | Stop-Process -Force
   ```

## 6. 就地升级：用户配置保留、current 被替换（对应验收标准 3）

1. 在根层用户配置里加一条自定义标记：

   ```powershell
   cd C:\TestOneDragon
   Add-Content -Path .\config\project.yml -Value 'test_custom_marker: "verified"'
   Select-String -Path .\config\project.yml -Pattern 'test_custom_marker'
   ```

   期望：`Select-String` 能查到这一行。

2. 执行就地升级。

   > 与设计文档的差异（已修正）：设计原文在 `C:\TestOneDragon` 里执行 `Update.exe apply -p deploy\dist\releases\...nupkg`，这个相对路径在解压目录里不存在（`deploy\` 在仓库里）。这里改成先用绝对路径取到 nupkg，再传给 `Update.exe`。

   ```powershell
   # 第 1 步：在仓库根目录取 nupkg 的绝对路径（上一个命令块的会话若已切换目录，先 cd 回仓库根目录）
   $nupkg = (Get-ChildItem ".\deploy\dist\releases" -Filter "*0.1.0-beta.2-full.nupkg" | Select-Object -First 1).FullName
   $nupkg
   Test-Path $nupkg   # 期望 True

   # 第 2 步：到解压目录执行升级，-p 传绝对路径
   cd C:\TestOneDragon
   .\Update.exe apply -p "$nupkg" --norestart
   ```

   期望：`Update.exe` 退出码为 0，输出里有应用/安装成功的提示。

3. 断言版本已切换：

   ```powershell
   cd C:\TestOneDragon
   Get-Content .\current\sq.version
   ```

   期望：内容为 `0.1.0-beta.2`。

4. 断言用户配置保留：

   ```powershell
   Select-String -Path .\config\project.yml -Pattern 'test_custom_marker'
   Get-Content .\config\project.yml
   ```

   期望：`test_custom_marker: "verified"` 仍然存在，其余用户改动的键没有被包内默认值覆盖。

5. 断言 `current\` 已被整体替换（文件时间比根层 `config\` 新，且 `current\` 里没有升级前手工新增的文件）：

   ```powershell
   (Get-Item .\current\OneDragon.exe).LastWriteTime
   (Get-Item .\config\project.yml).LastWriteTime
   ```

   期望：`current\OneDragon.exe` 的时间晚于 `config\project.yml`。

## 7. 完整日志不再出现 Git 仓库报错（对应验收标准 4）

1. 再次从根层启动：

   ```powershell
   Start-Process -FilePath C:\TestOneDragon\OneDragon.exe -WorkingDirectory C:\TestOneDragon
   ```

2. 打开应用后正常浏览各界面约 1 分钟（首页、资源管理、代码/版本记录相关入口都点一遍）。

3. 检索日志：

   ```powershell
   cd C:\TestOneDragon
   (Get-ChildItem -Path .\.log\*.log | Select-String -Pattern "不是有效的 Git 仓库" | Measure-Object).Count
   (Get-ChildItem -Path .\.log\*.log | Select-String -Pattern "尝试下一个代码源" | Measure-Object).Count
   ```

   期望：两个计数都为 `0`。

4. 关闭应用：

   ```powershell
   Get-Process OneDragon -ErrorAction SilentlyContinue | Stop-Process -Force
   ```

## 8. 源码模式不回归（对应验收标准 5）

> 与设计文档的差异（已修正）：设计原文和父单验收标准写的是 `python main.py`，但当前仓库根目录**没有** `main.py`。仓库的源码入口是 `src/zzz_od/gui/app.py`（见 `AGENTS.md` 常用命令）。这里按实际入口执行；如果改造确实新增了 `main.py`，再改回 `uv run python main.py`。

1. 在仓库根目录（不是解压目录）运行：

   ```powershell
   cd <仓库根目录>
   uv run src/zzz_od/gui/app.py
   ```

2. 期望：GUI 正常启动；首页、任务启动、关闭均与改造前一致。

3. 另开一个 PowerShell 会话断言非 Velopack 模式：

   ```powershell
   cd <仓库根目录>
   uv run python -c "from one_dragon.utils import os_utils; print(os_utils.is_velopack_mode()); print(os_utils.get_work_dir())"
   ```

   期望：第一行 `False`；第二行是仓库根目录的绝对路径，不是 `...\current`。

## 9. 退出后无残留进程（对应验收标准 6）

1. 在源码模式（`uv run src/zzz_od/gui/app.py`）或便携版里跑一个任务，然后点右上角关闭按钮正常退出。

2. 断言无残留：

   ```powershell
   Get-Process OneDragon, Update -ErrorAction SilentlyContinue |
     Select-Object ProcessName, Id, Path
   ```

   期望：输出为空（没有 `OneDragon`、`Update` 进程）。

3. 打开任务管理器 →「详细信息」，人工确认没有残留的 `OneDragon.exe`、`Update.exe` 和孤儿 Python 进程。

## 10. 未验证项（本次不覆盖，交付时需人类单独确认）

以下三项设计文档第 5 节已明确标注「未验证，写入交付说明供人类验收确认」，本清单不把它们算作通过：

1. **点界面的「检查更新」按钮**：完整走一遍「发现新版本 → 下载 → 进度 → 立即重启/下次启动应用」的 UI 交互，确认按钮可用、状态流转正确、错误提示可重试。本清单第 6 节只验证了命令行 `Update.exe apply` 的就地升级，没有覆盖应用内更新 UI。
2. **窗口渲染**：主窗口、各页面、更新提示浮层的实际渲染效果（布局、字体、深浅色主题、高 DPI）是否符合设计要求。
3. **`Setup.exe` 安装向导**：双击 `Setup.exe` 走完安装流程（安装目录选择、快捷方式、首次启动、卸载），确认与便携版行为一致。

另外，以下项在 arm-1 上同样无法验证，需要人类或 CI 环境确认，不算本清单通过：

- `vpk pack`、PyInstaller 冻结构建本身是否成功（arm-1 是 Linux，无法执行）。
- SignPath 签名后 `Setup.exe` / `Update.exe` / `OneDragon.exe` 是否都带合法签名。
- 离线模型包 `ZenlessZoneZero-OneDragon-Models.zip` 解压到根层后离线可用。
- CNB 镜像同步 `RELEASES` / `releases.win.json` / `.nupkg` 是否完整。

## 11. 执行记录表

| 编号 | 步骤 | 期望结果 | 实际结果 | 结论（通过/失败） | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 构建单目录产物 | 退出码 0，`deploy\dist\OneDragon\OneDragon.exe` 存在 | | | |
| 2 | 打 `0.1.0-beta.1` | 退出码 0 | | | |
| 3 | 打 `0.1.0-beta.2`（同一 outputDir） | 退出码 0 | | | |
| 4 | 产物断言 | `Setup.exe` / `win-Portable.zip` / `RELEASES` / `releases.win.json` / 两个 nupkg 齐全 | | | |
| 5 | 便携版首启播种 | `config` / `assets` / `custom` / `.log` / `.bundle_seed_version` 存在，四类资源计数 1820/10/8/178 | | | |
| 6 | 就地升级 | `current\sq.version` 为 `0.1.0-beta.2`，`config\project.yml` 的 `test_custom_marker` 保留 | | | |
| 7 | 日志检索 | 「不是有效的 Git 仓库」计数 0，「尝试下一个代码源」计数 0 | | | |
| 8 | 源码模式 | `is_velopack_mode()` 为 `False`，`get_work_dir()` 为仓库根目录，GUI 正常 | | | |
| 9 | 进程清理 | 退出后无 `OneDragon` / `Update` 残留进程 | | | |
| 10 | 未验证项 | 应用内检查更新 UI / 窗口渲染 / `Setup.exe` 安装向导 | | | 需人类单独确认 |
