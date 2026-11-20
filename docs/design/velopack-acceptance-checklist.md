# Velopack 分布式交付 Windows 人工验收清单

- 关联 Issue：PLAY-2 / PLAY-5 / PLAY-8
- 依据：`docs/design/velopack-distribution.md` 第 5 节验证矩阵「栏目 2：交人类在 Windows 上验」
- 目标分支：`feat/velopack`
- 适用环境：Windows 10 / 11 x64，已安装 Git、uv、.NET SDK（用于安装 `vpk`）
- 状态：**未执行**。本清单由 Tester 整理，供人类在 Windows 真机上逐条执行并记录结果；arm-1 是 aarch64 Linux，无法代替本清单的任一条。

> 说明：清单里所有命令都从**仓库根目录**开始执行（即 `ZenlessZoneZero-OneDragon\`，下文用 `<仓库根目录>` 指代）。每条都有明确的期望结果和断言命令，不要只看一眼就判通过。执行完把「实际结果」填进第 11 节记录表。

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

### 2.1 非发布构建的版本号格式（S5）

带 `build` 标签的 PR，以及手动 `workflow_dispatch` 但不勾 `create_release` 的构建，走的是非发布分支。`tools/ci/get_version.py` 必须输出**合法的 SemVer 2.0.0**，否则 `vpk pack --packVersion` 解析失败、打包直接中止。

格式约定：

| 触发方式 | `GITHUB_REF` 示例 | 期望输出 |
| :--- | :--- | :--- |
| PR 构建 | `refs/pull/123/merge` | `0.0.0-pr.123.g<短 sha>` |
| PR 号带前导 0 | `refs/pull/007/merge` | `0.0.0-pr.7.g<短 sha>`（前导 0 必须去掉） |
| 普通分支 / 本地 | `refs/heads/feat/velopack` | `0.0.0-dev.g<短 sha>` |

要点：

- core 段必须是三个数字（`MAJOR.MINOR.PATCH`），`pr123` / `dev` 这种字符串不能当 core，旧的 `pr123+<sha>` / `dev+<sha>` 是非法 SemVer2。
- 纯数字的预发布标识符不能有前导 0（`pr.007` 非法，`pr.7` 合法）。
- sha 前面加 `g`（`g<sha>`），避免 Git 短 sha 恰好全是数字时被当成纯数字标识符。
- tag 触发的发布构建仍要保留 `v` 前缀用于 Git tag，但喂给 `vpk` 的版本号去掉 `v`（第 2、3 节的 `--packVersion` 已经是不带 `v` 的形式）。

本地校验（在仓库根目录，PowerShell）：

```powershell
# 模拟 PR 构建
$env:GITHUB_REF = 'refs/pull/123/merge'
$env:CREATE_RELEASE = 'false'
$env:GITHUB_OUTPUT = Join-Path $env:TEMP 'gh_output.txt'
uv run python tools/ci/get_version.py
Get-Content $env:GITHUB_OUTPUT      # 期望 version=0.0.0-pr.123.g<sha>

# 用 SemVer2 官方正则校验非发布版本号
$v = (Get-Content $env:GITHUB_OUTPUT | Select-String '^version=').Line -replace '^version=', ''
$SEMVER2 = '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
if ($v -notmatch $SEMVER2) { Write-Host "非法 SemVer2: $v"; exit 1 }
Write-Host "SemVer2 校验通过: $v"

# tag 发布版本（如 0.1.0-beta.1）额外用 packaging 校验（PEP 440 能解析 beta.N）
uv run python -c "from packaging.version import Version; print(Version('0.1.0-beta.1'))"
```

期望：`$v` 匹配官方 SemVer2 正则并打印「SemVer2 校验通过」。

> 注意：`pr` / `dev` 是自定义预发布标识符，`packaging` 的 PEP 440 解析会拒绝（这不是缺陷，SemVer2 允许而 PEP 440 不收录）。因此非发布版本以 SemVer2 正则为准；`packaging` 只用于 tag 发布版本（`0.1.0-beta.1` → `0.1.0b1`）。

CI 侧对应位置：`.github/workflows/build-release.yml` 的 `Pack with Velopack` 步骤（`--packVersion "$semver"`）。arm-1 上无法执行 `vpk`，这里只校验版本串本身。

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

### 4.1 三个 exe 的 Authenticode 签名验证（B1 / 验收标准 1）

> 前提：只有 `CREATE_RELEASE == 'true'` 且注入了 `SIGNPATH_*` secrets 的构建才会走 `vpk pack --signTemplate "pwsh -File tools/ci/sign_file.ps1 {{file}}"`。本地无凭据构建产出未签名产物是预期行为；**发布形态必须三个 exe 全部 `Valid`**。CI 的 `sign` job 已经对这三个文件做同样的断言，任一不是 `Valid` 就 `exit 1`，不允许出现「`sign` 绿但产物没签」的情况。

```powershell
$releases = ".\deploy\dist\releases"
$setup = (Get-ChildItem $releases -Filter "*Setup.exe" | Select-Object -First 1).FullName
$zip = (Get-ChildItem $releases -Filter "*win-Portable.zip" | Select-Object -First 1).FullName
$extract = Join-Path $env:TEMP "OneDragon-SignCheck"
Remove-Item -Recurse -Force $extract -ErrorAction SilentlyContinue
Expand-Archive -Path $zip -DestinationPath $extract

$targets = @(
  [PSCustomObject]@{ Name = 'Setup.exe';     Path = $setup },
  [PSCustomObject]@{ Name = 'OneDragon.exe'; Path = (Join-Path $extract 'current\OneDragon.exe') },
  [PSCustomObject]@{ Name = 'Update.exe';    Path = (Join-Path $extract 'Update.exe') }
)

$targets | ForEach-Object {
  $sig = Get-AuthenticodeSignature -FilePath $_.Path
  [PSCustomObject]@{
    File   = $_.Name
    Status = $sig.Status
    Signer = $sig.SignerCertificate.Subject
  }
}

# 门禁断言：任意一个不是 Valid 就失败
$bad = $targets | Where-Object { (Get-AuthenticodeSignature -FilePath $_.Path).Status -ne 'Valid' }
if ($bad) {
  $bad | ForEach-Object { Write-Host "签名无效: $($_.Name) -> $((Get-AuthenticodeSignature -FilePath $_.Path).Status)" }
  exit 1
}
Write-Host '三个 exe 签名均为 Valid'
```

期望：

- 三行 `Status` 全部为 `Valid`。
- `Signer` 的 `Subject` 含预期的签名主体（OneDragon-Anything 在 SignPath 上配置的组织名），不是 `CN=...` 的自签证书、也不是空值。
- 最后一行输出「三个 exe 签名均为 Valid」，退出码为 0。

常见非通过状态及含义：`NotSigned`（`--signTemplate` 没挂上或 secrets 未注入）、`HashMismatch`（签名后文件又被改写）、`UnknownError`（时间戳服务不可达）。这几种都算失败，要贴原始 `Status` 回 Issue。

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

4. 断言四类只读资源文件数（S4）：

   > **只读资源覆盖规则（S4）**：`assets/template`、`assets/ui`、`assets/text`、`assets/game_data` 这四类目录在**升级（包版本变化）时由包内版本整体覆盖**——旧版本残留文件会被删除，手工修改也会被抹掉。因此不要手工改这四个目录；模板产出请放 `custom/` 或按 S4 建议迁出。`config/` 的规则不同：只补缺失文件与缺失的顶层键，已有键一律不覆盖，用户文件损坏时跳过（验证步骤见第 6 节第 2 步与第 7 节第 4 步）。数字取自设计文档第 5 节；如果仓库资源在改造期间有增删，记录实际值并说明：

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

2. 制造「旧版本残留 + 用户删了一个顶层键」的场景，用于验证 S4（缺键合并与只读资源整体覆盖）：

   ```powershell
   cd C:\TestOneDragon
   New-Item -ItemType File -Force .\assets\template\stale_from_old_version.txt | Out-Null
   Set-Content -Path .\assets\ui\ui.txt -Value 'patched by hand'
   # 删掉一个非必需顶层键，期望升级后首次启动时被包内默认值补齐
   (Get-Content .\config\project.yml) | Where-Object { $_ -notmatch '^doc_link:' } | Set-Content .\config\project.yml
   Test-Path .\assets\template\stale_from_old_version.txt      # 期望 True
   Select-String -Path .\config\project.yml -Pattern '^doc_link:'   # 期望无输出
   ```

3. 执行就地升级。

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

4. 断言版本已切换：

   ```powershell
   cd C:\TestOneDragon
   Get-Content .\current\sq.version
   ```

   期望：内容为 `0.1.0-beta.2`。

5. 断言用户配置保留：

   ```powershell
   Select-String -Path .\config\project.yml -Pattern 'test_custom_marker'
   Get-Content .\config\project.yml
   ```

   期望：`test_custom_marker: "verified"` 仍然存在，其余用户改动的键没有被包内默认值覆盖。

6. 断言 `current\` 已被整体替换（文件时间比根层 `config\` 新，且 `current\` 里没有升级前手工新增的文件）：

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

4. 断言只读资源被整体覆盖、config 缺失的顶层键被补齐（S4）：

   ```powershell
   cd C:\TestOneDragon
   Test-Path .\assets\template\stale_from_old_version.txt              # 期望 False
   Select-String -Path .\assets\ui\ui.txt -Pattern 'patched by hand'   # 期望无输出
   Select-String -Path .\config\project.yml -Pattern '^doc_link:'       # 期望能查到
   Select-String -Path .\config\project.yml -Pattern 'test_custom_marker'  # 期望仍能查到
   ```

   期望：

   - 第 1、2 条通过 → 四类只读目录在版本变化时由包内版本整体覆盖，旧残留和手工修改被清掉。
   - 第 3 条通过 → `config/*.yml` 的缺键合并把用户删掉的顶层键补回来了。
   - 第 4 条通过 → 补齐新键**没有**覆盖用户已有的顶层键。

   > 校验时机：覆盖与合并发生在应用启动的 `ensure_work_dir_ready()` 里，所以必须在第 7 节第 1 步重新启动应用之后、且等首启播种完成后才能断言；`Update.exe apply` 本身不跑应用。

5. 关闭应用：

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
- SignPath 签名后的三个 exe 是否都带合法签名（Windows 上用第 4.1 节的 `Get-AuthenticodeSignature` 核查；arm-1 上只能确认 workflow 与 `sign_file.ps1` 的代码路径，不能执行签名）。
- 离线模型包 `ZenlessZoneZero-OneDragon-Models.zip` 解压到根层后离线可用。
- CNB 镜像同步 `RELEASES` / `releases.win.json` / `.nupkg` 是否完整。

## 11. 执行记录表

| 编号 | 步骤 | 期望结果 | 实际结果 | 结论（通过/失败） | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 构建单目录产物 | 退出码 0，`deploy\dist\OneDragon\OneDragon.exe` 存在 | | | |
| 2 | 打 `0.1.0-beta.1` | 退出码 0 | | | |
| 3 | 打 `0.1.0-beta.2`（同一 outputDir） | 退出码 0 | | | |
| 4 | 产物断言 | `Setup.exe` / `win-Portable.zip` / `RELEASES` / `releases.win.json` / 两个 nupkg 齐全 | | | |
| 4.1 | 签名验证（B1） | `Setup.exe` / `OneDragon.exe` / `Update.exe` 的 `Get-AuthenticodeSignature` 全为 `Valid` | | | |
| 4.2 | 非发布版本号（S5） | PR 构建为 `0.0.0-pr.<n>.g<sha>`，分支构建为 `0.0.0-dev.g<sha>`，匹配 SemVer2 | | | |
| 5 | 便携版首启播种 | `config` / `assets` / `custom` / `.log` / `.bundle_seed_version` 存在，四类资源计数 1820/10/8/178 | | | |
| 6 | 就地升级 | `current\sq.version` 为 `0.1.0-beta.2`，`config\project.yml` 的 `test_custom_marker` 保留 | | | |
| 7 | 日志检索 | 「不是有效的 Git 仓库」计数 0，「尝试下一个代码源」计数 0 | | | |
| 7.1 | S4 覆盖与合并 | 只读资源残留被清、手工改动被盖回；`doc_link` 被补齐、`test_custom_marker` 保留 | | | |
| 8 | 源码模式 | `is_velopack_mode()` 为 `False`，`get_work_dir()` 为仓库根目录，GUI 正常 | | | |
| 9 | 进程清理 | 退出后无 `OneDragon` / `Update` 残留进程 | | | |
| 10 | 未验证项 | 应用内检查更新 UI / 窗口渲染 / `Setup.exe` 安装向导 | | | 需人类单独确认 |
