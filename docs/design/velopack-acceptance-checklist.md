# Velopack 分布式交付 Windows 人工验收清单

- 关联 Issue：PLAY-2 / PLAY-5 / PLAY-8 / PLAY-10 / PLAY-17
- 依据：`docs/design/velopack-distribution.md` 第 5 节验证矩阵「栏目 2：交人类在 Windows 上验」
- 目标分支：`feat/velopack`
- 适用环境：Windows 10 / 11 x64，已安装 Git、uv、.NET SDK（用于安装 `vpk`）
- 状态：**未执行**。本清单由 Tester 整理，供人类在 Windows 真机上逐条执行并记录结果；arm-1 是 aarch64 Linux，无法代替本清单的任一条。

> 说明：清单里所有命令都从**仓库根目录**开始执行（即 `ZenlessZoneZero-OneDragon\`，下文用 `<仓库根目录>` 指代）。每条都有明确的期望结果和断言命令，不要只看一眼就判通过。执行完把「实际结果」填进第 12 节记录表。

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

> **硬性前置（D3）：必须用本仓库 `uv sync` 出来的 `.venv` 构建，禁止复用别的仓库的 venv。** 用别的仓库的环境构建，会把本仓库声明、但那份环境没装的运行时依赖静默漏掉（人类实测漏过 `websocket-client`，冻结后运行时报 `No module named 'websocket'`）。规则：
>
> 1. 在**本仓库根目录**执行 `uv sync --group dev`，由它生成 `<仓库根目录>\.venv`。本仓库 `pyproject.toml` 里 `default-groups = []`，不显式带 `--group dev` 就不会装 `pyinstaller` / `pyuac` / `colorama` 这些构建期依赖。
> 2. 之后所有构建命令都走 `uv run ...`（即本仓库 `.venv`）。不要用另一个项目 `.venv\Scripts\python.exe -m pyinstaller` 之类的方式跨仓库借用环境，也不要把别的仓库的 `.venv` 复制进来。
> 3. 构建前跑一遍下面的依赖自检；任何一个 `find_spec` 返回 `None` 就**停下**，不要继续打包。

依赖自检（构建前置，逐项检查 `pyproject.toml` 的 `[project].dependencies`）：

```powershell
cd <仓库根目录>
uv sync --group dev
@'
import importlib.util
import re
import sys
import tomllib
from pathlib import Path

# 发行包名 -> import 时的模块名。只有少数对不上的才需要在这里列。
MODULE_OVERRIDES = {
    'pyside6': 'PySide6',
    'pyside6-fluent-widgets': 'qfluentwidgets',
    'opencv-python': 'cv2',
    'onnxruntime-directml': 'onnxruntime',
    'pywin32': 'win32api',
    'pyyaml': 'yaml',
    'websocket-client': 'websocket',
}

project = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
deps = project['project']['dependencies']
missing = []
for dep in deps:
    name = re.split(r'[<>=!~\[; ]', dep, 1)[0].strip()
    module = MODULE_OVERRIDES.get(name.lower(), name.replace('-', '_'))
    if importlib.util.find_spec(module) is None:
        missing.append(f'{name} (期望可导入 {module})')

print(f'运行时依赖 {len(deps)} 个，缺失 {len(missing)} 个')
if missing:
    print('\n'.join('MISSING ' + item for item in missing))
    sys.exit(1)
print('PASS: 所有运行时依赖均可导入')
'@ | uv run python -
```

期望：输出 `运行时依赖 20 个，缺失 0 个` 与 `PASS: 所有运行时依赖均可导入`，退出码 0。输出 `MISSING websocket-client (期望可导入 websocket)` 说明用的是别的仓库的环境或者 `uv sync` 没跑，按上面的规则重来，不要忽略这行继续打包。

> 统一从仓库根目录执行（设计文档第 5 节已同步），`--packDir` 保持 `deploy\dist\OneDragon`。构建环境必须是上面 D3 那套本仓库 `uv sync` 出来的 `.venv`。

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

### 2.2 另存 beta.1 的安装器（第 6.1 节的前置，必须做）

Velopack 安装器的文件名**不带版本号**（`<packId>-Setup.exe` / `<packId>-win-Portable.zip`）。第 3 节往同一个 `--outputDir` 打 `0.1.0-beta.2` 时会把它覆盖掉，第 6.1 节的离线覆盖安装就拿不到 beta.1 的安装器了。所以打完 beta.1 立刻另存一份：

```powershell
cd <仓库根目录>
$save1 = ".\deploy\dist\installers\0.1.0-beta.1"
New-Item -ItemType Directory -Force $save1 | Out-Null
Get-ChildItem .\deploy\dist\releases -Filter "*Setup.exe"       | Copy-Item -Destination $save1 -Force
Get-ChildItem .\deploy\dist\releases -Filter "*win-Portable.zip" | Copy-Item -Destination $save1 -Force
Get-ChildItem $save1 | Select-Object Name, Length
Get-FileHash (Get-ChildItem $save1 -Filter "*Setup.exe").FullName -Algorithm SHA256 | Select-Object Hash, Path
```

期望：`$save1` 下有 `Setup.exe` 与 `Portable.zip` 各一份（名称以实际 `vpk` 输出为准）。把 `Setup.exe` 的 SHA256 记进第 12 节：第 6.1 节靠它区分两个版本的安装器。

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

### 3.1 另存 beta.2 的安装器

同样存到带版本号的目录，和 beta.1 的分开——两版安装器的文件名相同，不能靠文件名区分：

```powershell
cd <仓库根目录>
$save2 = ".\deploy\dist\installers\0.1.0-beta.2"
New-Item -ItemType Directory -Force $save2 | Out-Null
Get-ChildItem .\deploy\dist\releases -Filter "*Setup.exe"        | Copy-Item -Destination $save2 -Force
Get-ChildItem .\deploy\dist\releases -Filter "*win-Portable.zip" | Copy-Item -Destination $save2 -Force
Get-FileHash (Get-ChildItem $save2 -Filter "*Setup.exe").FullName -Algorithm SHA256 | Select-Object Hash, Path
```

期望：`$save2` 里 `Setup.exe` 的 SHA256 与第 2.2 节记录的**不同**（包内 nupkg 版本不同）。相同说明另存时拷错了文件，回第 2.2、3.1 节重来。

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

> 前提：只有 `CREATE_RELEASE == 'true'` 且注入了 `SIGNPATH_*` secrets 的构建才会走 `vpk pack --signTemplate 'pwsh -File tools/ci/sign_file.ps1 "{{file}}"'`。本地无凭据构建产出未签名产物是预期行为；**发布形态必须三个 exe 全部 `Valid`**。CI 的 `sign` job 已经对这三个文件做同样的断言，任一不是 `Valid` 就 `exit 1`，不允许出现「`sign` 绿但产物没签」的情况。
>
> **签名脚本的两种提交形态（B1-a，第 2 轮返工）**：`tools/ci/sign_file.ps1` 按是否设置 `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` 走两条路径，验证前先确认实际走了哪条：
>
> | 环境变量 | 提交形态 | SignPath 侧要求 |
> | :--- | :--- | :--- |
> | 未设置（**当前 workflow 就是这个形态**） | 把单个文件压成 zip，用项目默认 artifact configuration 提交，下载后解压取回同名文件 | SignPath 项目要有能接受 zip 的默认 artifact configuration |
> | 设置了 slug | 直接提交裸 exe，并带 `-ArtifactConfigurationSlug <slug>` | SignPath 项目要配好对应的 artifact configuration slug |
>
> 两种形态在覆盖原文件前都会校验「扩展名一致 + PE 头是 `MZ`」，候选文件是 zip 或无效二进制时**拒绝覆盖**并抛错，`vpk pack` 会因此失败。这个保护是预期的，不要为了签过而放宽它。

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

### 4.3 nupkg 内 exe 的签名核验（B1-c，第 2 轮返工）

> 第 2 轮返工把 CI 的签名门禁从「只看 `Portable.zip`」扩到「同时解压 `*-full.nupkg` 逐个校验」。增量更新走的就是 nupkg 内的二进制，包内 `Update.exe` / `OneDragon.exe` 没签等于更新后仍然被拦截，所以这一步不能省。

```powershell
$releases = ".\deploy\dist\releases"
$nupkgDir = Join-Path $env:TEMP "OneDragon-NupkgSignCheck"
Remove-Item -Recurse -Force $nupkgDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $nupkgDir | Out-Null

$checked = @()
foreach ($nupkg in Get-ChildItem $releases -Filter "*-full.nupkg") {
  $dest = Join-Path $nupkgDir $nupkg.BaseName
  Expand-Archive -Path $nupkg.FullName -DestinationPath $dest -Force
  $exes = Get-ChildItem -Path $dest -Recurse -File |
    Where-Object { $_.Name -in @('OneDragon.exe', 'Update.exe') }
  if (-not ($exes | Where-Object { $_.Name -eq 'OneDragon.exe' })) {
    Write-Host "nupkg 内缺少 OneDragon.exe: $($nupkg.Name)"; exit 1
  }
  $checked += $exes
}

$checked | ForEach-Object {
  $sig = Get-AuthenticodeSignature -FilePath $_.FullName
  [PSCustomObject]@{ PackageFile = $_.Name; Status = $sig.Status; Signer = $sig.SignerCertificate.Subject }
}

$bad = $checked | Where-Object { (Get-AuthenticodeSignature -FilePath $_.FullName).Status -ne 'Valid' }
if ($bad) {
  $bad | ForEach-Object { Write-Host "nupkg 内签名无效: $($_.FullName)" }
  exit 1
}
Write-Host 'nupkg 内所有 OneDragon.exe / Update.exe 签名均为 Valid'
```

期望：每个 `*-full.nupkg` 内都能找到 `OneDragon.exe`，列出的每一行 `Status` 都是 `Valid`，最后一行输出「nupkg 内所有 OneDragon.exe / Update.exe 签名均为 Valid」，退出码 0。注意 `Update.exe` 在包内可能有多份（`current\` 与根层），要全部为 `Valid`，不能只看其中一份。

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

3. 断言根层目录与播种标记生成：

   ```powershell
   cd C:\TestOneDragon
   Test-Path .\config
   Test-Path .\assets
   Test-Path .\custom
   Test-Path .\.log
   Test-Path .\.bundle_seed_version
   Test-Path .\.bundle_seed_status.json
   ```

   期望：6 行全部为 `True`。

   `.bundle_seed_status.json` 是第 2 轮返工新增的**按目录**播种版本记录（`{"template": "0.1.0-beta.1", "ui": ..., "text": ..., "game_data": ...}`）；根层 `.bundle_seed_version` 仍然只在四类目录全部成功后才写。两个文件都要在，缺前者说明播种逻辑回退了。

   > **D5 口径**：`current\sq.version` 是 nuspec XML，播种代码必须解析出其中的 `<version>` 节点后再写标记。两个文件里都只能是**纯版本号**（如 `0.1.0-beta.1`），不能是 XML 全文、也不能是空串。第 5 步给出具体断言。

4. 断言四类只读资源文件数（S4，动态比对，不写死数字）：

   > **只读资源覆盖规则（S4）**：`assets/template`、`assets/ui`、`assets/text`、`assets/game_data` 这四类目录在**升级（包版本变化）时由包内版本整体覆盖**——旧版本残留文件会被删除，手工修改也会被抹掉。因此不要手工改这四个目录；模板产出请放 `custom/` 或按 S4 建议迁出。`config/` 的规则不同：只补缺失文件与缺失的顶层键，已有键一律不覆盖，用户文件损坏时跳过（验证步骤见第 6 节第 2 步与第 7 节第 4 步）。
   >
   > **断言口径**：根层 `assets\<tree>` 的文件数必须等于**包内** `current\_internal\resources\assets\<tree>` 的文件数。包内路径按 `deploy/OneDragon-Portable.spec` 的 datas 目标核对过——四类资源的目标目录是 `resources/assets/<tree>`，PyInstaller 6 的单目录模式把 datas 收进 `_internal\`，Velopack 又把它整体放到 `current\` 下，所以完整路径是 `current\_internal\resources\assets\<tree>`。不写死数字：源资源增删或换基线时不会假失败，而且能真正证明「播种把包里的东西一个不落地复制到了根层」。

   ```powershell
   cd C:\TestOneDragon
   $trees = 'template', 'ui', 'text', 'game_data'
   $ok = $true
   foreach ($tree in $trees) {
       $rootCount = (Get-ChildItem -Path ".\assets\$tree" -Recurse -File -Force).Count
       $pkgCount  = (Get-ChildItem -Path ".\current\_internal\resources\assets\$tree" -Recurse -File -Force).Count
       if ($rootCount -ne $pkgCount) { $ok = $false }
       $verdict = if ($rootCount -eq $pkgCount) { '一致' } else { '不一致' }
       '{0,-10} 根层 {1,5} / 包内 {2,5} -> {3}' -f $tree, $rootCount, $pkgCount, $verdict
   }
   if (-not $ok) { Write-Host 'FAIL: 至少一类资源的文件数与包内不一致'; exit 1 }
   Write-Host 'PASS: 四类只读资源文件数与包内逐一相等'
   ```

   期望：四个 `->` 结尾都是 `一致`，最后打印 `PASS`，退出码 0。

   参考值（**只用于排查偏差，不作为断言**）：按本单基线 `c2e3865b` 用 `git ls-tree -r c2e3865b --name-only assets/<tree>` 数出来是 template **1948** / ui **5** / text **8** / game_data **159**。如果某一类的根层数量少于包内数量，说明播种没做完或被中断（回看 `.bundle_seed_status.json` 与 `.log\`）；如果根层多于包内，说明根层有旧版本残留没被整体覆盖（S4 回归），把实际数字记进第 12 节记录表。

5. 断言版本标记是**纯版本号**（D5：`sq.version` 是 nuspec XML，标记里不能是 XML 全文）：

   ```powershell
   cd C:\TestOneDragon
   $marker = (Get-Content .\.bundle_seed_version -Raw).Trim()
   $nuspec = [xml](Get-Content .\current\sq.version -Raw)
   $nodeVersion = $nuspec.package.metadata.version

   Write-Host "marker      = '$marker'"
   Write-Host "sq.version  = '$nodeVersion'"

   if ([string]::IsNullOrWhiteSpace($marker)) { Write-Host 'FAIL: .bundle_seed_version 为空'; exit 1 }
   if ($marker -match '[<>]' -or $marker -match 'nuspec') { Write-Host 'FAIL: .bundle_seed_version 里是 XML 全文，不是纯版本号'; exit 1 }
   if ($marker -ne $nodeVersion) { Write-Host 'FAIL: .bundle_seed_version 与 current\sq.version 的 <version> 节点不一致'; exit 1 }
   Write-Host 'PASS: 标记文件是解析后的纯版本号'
   ```

   期望：最后打印 `PASS`，退出码 0。`.bundle_seed_status.json` 的四个键（`template` / `ui` / `text` / `game_data`）值都与 `$marker` 相同，同样不含 `<`。

   > 老用户迁移：升级到本版本前，两个文件里存的是 nuspec XML 全文。由于与纯版本号不相等，**第一次启动会全量重新播种一次**，之后两个文件被改写成纯版本号，不会再重复播种。升级后如果发现每次启动都在重播 46MB 资源，说明迁移逻辑回归了，记进第 12 节记录表。

6. 关闭应用：

   ```powershell
   Get-Process OneDragon -ErrorAction SilentlyContinue | Stop-Process -Force
   ```

### 5.1 播种失败时的降级、告警与按目录重试（N1/N3，可选负向验证）

> 这是第 2 轮返工新增行为的负向验证，**不是交付门禁**：正常升级走不到这些分支。能跑就跑，跑不了在记录表里写「未执行 + 原因」，不要凭代码推断通过。

**场景 A：残留临时目录清理（N3）**

1. 在解压目录里手工造两个本机制自己的残留目录，再放一个「无辜」目录当对照：

   ```powershell
   cd C:\TestOneDragon
   New-Item -ItemType Directory -Force .\assets\.template.new-1a2b3c4d-0 | Out-Null
   New-Item -ItemType Directory -Force .\assets\.ui.old-deadbeef | Out-Null
   New-Item -ItemType Directory -Force .\assets\template_backup | Out-Null
   Set-Content .\assets\template_backup\keep.txt 'keep'
   ```

2. 启动应用一次（同第 5 节第 2 步），等播种完成后关闭。

3. 断言：

   ```powershell
   cd C:\TestOneDragon
   Test-Path .\assets\.template.new-1a2b3c4d-0   # 期望 False
   Test-Path .\assets\.ui.old-deadbeef          # 期望 False
   Test-Path .\assets\template_backup\keep.txt   # 期望 True（不能误删）
   ```

**场景 B：单个目录播种失败的 InfoBar 与重试（N1）**

1. 用另一个进程独占打开 `assets\template` 下的一个文件，让升级时目录交换失败：

   ```powershell
   $lock = [System.IO.File]::Open('C:\TestOneDragon\assets\template\template.txt', 'Open', 'Read', 'None')
   ```

2. 保持锁不释放，把应用升级到下一个包版本（同第 6 节第 3 步）并启动。

3. 期望：
   - 应用**正常启动**，不闪退；
   - 右上方出现一次「资源更新失败（template）」的黄色 InfoBar，提示查看 `.log\`；
   - `Get-Content .\.bundle_seed_version` 仍是**升级前**的版本；
   - `.bundle_seed_status.json` 里 `template` 仍是升级前版本，其他三类已前进到新版本；
   - `assets\template` 里原有的用户文件还在（没有被先清空）；
   - `.log\` 里有「复制只读资源目录失败: template」的堆栈。
4. 关闭应用，释放锁，再启动一次。

5. 期望：本次只重试 `template`（其他目录版本已匹配，不应重复复制），成功后 `.bundle_seed_version` 与 `.bundle_seed_status.json` 全部变为新版本，InfoBar 不再出现。

```powershell
$lock.Close(); $lock.Dispose()
```

> 如果 Windows 上目录交换没有被锁影响（Velopack 先替换 `current\` 而根层文件锁不阻止同级目录 rename），这条负向场景可能跑不出来：把实际现象和锁的形态原样记进记录表，不要改代码迁就。

### 5.2 D4：`--version` 递归自启回归（阻断项，真机必测）

> 来源：人类本机验收发现的 D4。修复前冻结后的主程序不处理 `--version`：`get_launcher_version()` 对 `sys.executable` 跑 `[exe, '--version']`，子进程按完整 GUI 启动后又去问自己的版本，进程链每约 4.5 秒延伸一层，永不停止。日志每轮只有 `Overlay 已启用`、`发现 0 个默认组应用` 两行，没有异常堆栈。
>
> 修复后：`app.py` 在 `--version` 时打印版本号后立即 `exit 0`（不进入 GUI、不播种），且 velopack 模式下所有版本查询入口都不启动子进程。arm-1 上只能单测（零子进程 + 版本一致），**递归现象本身必须按本节在 Windows 真机确认**。

1. 全新解压 Portable 包并从根层启动（不要进 `current\`）：

   ```powershell
   $zip = (Get-ChildItem .\deploy\dist\releases -Filter "*win-Portable.zip" | Select-Object -First 1).FullName
   Remove-Item -Recurse -Force C:\TestOneDragon -ErrorAction SilentlyContinue
   Expand-Archive -Path $zip -DestinationPath C:\TestOneDragon
   Start-Process -FilePath C:\TestOneDragon\OneDragon.exe -WorkingDirectory C:\TestOneDragon
   ```

2. **20 秒后**抓进程与父链（人类给出的复现命令）：

   ```powershell
   Get-CimInstance Win32_Process -Filter "name='OneDragon.exe'" |
     Select-Object ProcessId, ParentProcessId, CommandLine | Format-Table -AutoSize
   ```

   期望：只有一条 `current\OneDragon.exe`，`CommandLine` 里**没有**带 `--version` 参数的进程；不存在「父进程也是 `OneDragon.exe --version`」的链。

3. **60 秒内**再抓一次，确认进程数不增长，只剩一个 `current\OneDragon.exe`：

   ```powershell
   Start-Sleep -Seconds 40
   $procs = @(Get-CimInstance Win32_Process -Filter "name='OneDragon.exe'")
   $procs | Select-Object ProcessId, ParentProcessId, CommandLine | Format-Table -AutoSize
   if ($procs.Count -ne 1) { Write-Host "FAIL: OneDragon.exe 进程数为 $($procs.Count)，疑似递归自启"; exit 1 }
   if ($procs[0].CommandLine -match '--version') { Write-Host 'FAIL: 出现了 --version 自启进程'; exit 1 }
   Write-Host 'PASS: 只剩一个 OneDragon.exe'
   ```

   期望：打印 `PASS`，退出码 0。

4. 日志不再周期性重复 `Overlay 已启用`：

   ```powershell
   cd C:\TestOneDragon
   $before = (Get-ChildItem -Path .\.log\*.log | Select-String -Pattern 'Overlay 已启用' | Measure-Object).Count
   Start-Sleep -Seconds 30
   $after = (Get-ChildItem -Path .\.log\*.log | Select-String -Pattern 'Overlay 已启用' | Measure-Object).Count
   Write-Host "30 秒前 $before 条，现在 $after 条"
   if ($after -ne $before) { Write-Host 'FAIL: 日志仍在周期性重复 Overlay 已启用（递归自启特征）'; exit 1 }
   Write-Host 'PASS: 日志不再周期性重复'
   ```

   期望：两次计数相等（启动阶段允许出现少量，但 30 秒静置期间不能增长）。

5. 直接验证入口本身（窗口不应出现，几秒内退出）：

   ```powershell
   cd C:\TestOneDragon
   $elapsed = Measure-Command { $v = & .\current\OneDragon.exe --version; $code = $LASTEXITCODE }
   Write-Host "stdout='$v' exit=$code elapsed=$([math]::Round($elapsed.TotalSeconds,1))s"
   if ($code -ne 0) { Write-Host 'FAIL: --version 退出码不为 0'; exit 1 }
   if ([string]::IsNullOrWhiteSpace($v) -or $v -match '[<>]') { Write-Host 'FAIL: --version 没有打印纯版本号'; exit 1 }
   if ($elapsed.TotalSeconds -gt 15) { Write-Host 'FAIL: --version 超过 15 秒才返回'; exit 1 }
   Write-Host 'PASS: --version 立即打印版本并退出'
   ```

   期望：`stdout` 是纯版本号（如 `0.1.0-beta.1`），退出码 0，15 秒内返回，没有弹 GUI 窗口。

6. 关闭应用并确认无残留：

   ```powershell
   Get-Process OneDragon -ErrorAction SilentlyContinue | Stop-Process -Force
   Start-Sleep -Seconds 2
   @(Get-CimInstance Win32_Process -Filter "name='OneDragon.exe'").Count   # 期望 0
   ```

**本节通过标准（人类判定口径）**：60 秒内只剩一个 `current\OneDragon.exe`，且日志不再周期性重复 `Overlay 已启用`。任一不满足即 D4 回归，阻断交付。

> 本节的 Windows 真机部分 arm-1 上**未执行**（Linux aarch64 跑不了冻结包）；对应的可执行单测见 `zzz-od-test/test/zzz_od/gui/test_app_version_flag.py`（`--version` 早退、零子进程、版本一致）。

## 6. 就地升级：用户配置保留、current 被替换（对应验收标准 3）

> 本节验的是**在线增量升级机制**（`Update.exe apply` 直接应用 nupkg），这是给测试用的命令行手段，**不是**面向用户的更新入口。用户侧的离线更新只有一种路径：运行新版 `Setup.exe` 覆盖安装，见 6.1 节。本清单**不新增任何本地更新包导入入口**，也不把「重新解压 `Portable.zip` 覆盖已有目录」当作更新方式（会留下新旧混合文件）。

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
   Select-String -Path .\current\sq.version -Pattern '<version>0\.1\.0-beta\.2</version>'
   ```

   期望：`current\sq.version` 是 nuspec XML，其中 `<version>` 节点为 `0.1.0-beta.2`（不是整份文件等于版本号）。升级后重新启动一次应用，再按第 5 节第 5 步断言根层 `.bundle_seed_version` 为纯版本号 `0.1.0-beta.2`。

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

## 6.1 离线更新：新 `Setup.exe` 覆盖安装到已有目录（父单新增需求 2）

> **口径（人类已定，不再讨论替代方案）**：离线更新没有独立入口，也**不新增任何导入本地更新包的入口**；同样不把「重新解压 `Portable.zip` 覆盖已有目录」当作更新方式。离线路径就是**像第一次安装一样运行新版 `Setup.exe`**，验证点是「根层用户数据全部保留、`current\` 被整体替换、版本标记前进」。
>
> **本节目前未实测**。这是人类明确要求补测的一项：Windows 真机项，arm-1 是 aarch64 Linux，没有任何一条能代替执行。请在 Windows 上按下面 4 步跑完，把实际结果填进第 12 节记录表的 6.1–6.7 行；跑不了的写「未执行 + 原因」，**不要**根据代码推断为通过。
>
> 本节所有命令请放在**同一个 PowerShell 会话**里按顺序执行，`$installRoot`、`$modelsManifest`、`$marker` 等变量跨步骤复用。`<仓库根目录>` 按实际路径替换。

### 步骤 1（前置）：用 beta.1 的 `Setup.exe` 安装，首启完成播种并造好标记

#### 1.1 取两个版本的安装器

```powershell
$root = '<仓库根目录>'
$setup1 = (Get-ChildItem "$root\deploy\dist\installers\0.1.0-beta.1" -Filter '*Setup.exe' | Select-Object -First 1).FullName
$setup2 = (Get-ChildItem "$root\deploy\dist\installers\0.1.0-beta.2" -Filter '*Setup.exe' | Select-Object -First 1).FullName
$setup1; $setup2
Test-Path $setup1; Test-Path $setup2
# 两份必须不是同一个文件，哈希必须不同
Get-FileHash $setup1, $setup2 -Algorithm SHA256 | Select-Object Hash, Path
```

期望：两行 `True`；两个 SHA256 不同。哈希相同说明第 2.2 / 3.1 节的另存有问题（beta.2 打包时把 beta.1 的 `Setup.exe` 覆盖后再拷的），回那两节重做。

#### 1.2 装 0.1.0-beta.1（覆盖安装必须在同一安装根上测，所以这一步就用 `Setup.exe` 装）

先确认机器上没有残留进程：

```powershell
Get-Process OneDragon, Update -ErrorAction SilentlyContinue | Select-Object ProcessName, Id, Path
```

期望：输出为空。若已装过旧版本，先用**旧安装根**的 `Update.exe` 卸载干净再继续（把路径换成实际值）：

```powershell
# & "<旧安装根>\Update.exe" --uninstall
```

运行 beta.1 的安装器（交互式，按界面提示走完）：

```powershell
$p1 = Start-Process -FilePath $setup1 -Wait -PassThru
"beta.1 Setup 退出码 = $($p1.ExitCode)"
if ($p1.ExitCode -ne 0) { Write-Host 'FAIL: beta.1 安装器退出码非 0'; exit 1 }
```

期望：退出码 0。观察并记录安装器的实际行为（第 12 节 6.1 行备注）：是否弹界面、是否有目录选择页、是否需要点确认、完成后是否自动拉起应用。

#### 1.3 记录安装根路径

Velopack 是**单用户安装**，默认落到 `%LocalAppData%\<packId>`（本仓库 `packId` 是 `ZenlessZoneZero-OneDragon`）。不要照抄默认值，以实测为准：先从卸载登记信息里取 `InstallLocation`：

```powershell
$packId = 'ZenlessZoneZero-OneDragon'
$regRoots = @(
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
  'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
  'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
)
$entries = foreach ($r in $regRoots) {
  if (Test-Path $r) {
    Get-ChildItem $r | ForEach-Object { Get-ItemProperty $_.PSPath } |
      Where-Object { $_.DisplayName -like '*OneDragon*' -or $_.InstallLocation -like '*OneDragon*' }
  }
}
$entries | Select-Object DisplayName, DisplayVersion, InstallLocation | Format-List

$installRoot = ($entries | Where-Object { $_.InstallLocation } | Select-Object -First 1).InstallLocation
$installRoot
```

如果卸载登记里没有 `InstallLocation`（不同 Velopack 版本登记字段不完全一致），从默认位置找：

```powershell
if (-not $installRoot) {
  Get-ChildItem $env:LOCALAPPDATA -Directory | Where-Object { $_.Name -like '*OneDragon*' } |
    Select-Object FullName, LastWriteTime
}
```

把结果写进变量并断言安装根里有覆盖安装必需的三个东西（`Setup.exe` 覆盖的是安装形态，不是 Portable 解压目录）：

```powershell
# 若上面一行找到的目录确实是安装根，把它写进来（示例）：
# $installRoot = Join-Path $env:LOCALAPPDATA $packId
$installRoot = $installRoot.TrimEnd('\')
"安装根 = $installRoot"
Test-Path $installRoot                                                 # 期望 True
Test-Path (Join-Path $installRoot 'current\OneDragon.exe')             # 期望 True
Test-Path (Join-Path $installRoot 'Update.exe')                        # 期望 True
Test-Path (Join-Path $installRoot 'current\sq.version')                # 期望 True
(Get-ChildItem $installRoot -Directory | Select-Object -ExpandProperty Name) -join ', '
```

期望：四行 `True`；根层能看到 `current`、`config`、`assets`、`custom`、`.log`（首启之前的全新安装可能还没有 `config` / `assets`，下一步启动后会补上）。把 `安装根` 的原值记进第 12 节——覆盖安装后必须还是同一个路径。

#### 1.4 启动一次完成首启播种

从**根本层**启动（不要进 `current\`）：

```powershell
Start-Process -FilePath (Join-Path $installRoot 'OneDragon.exe') -WorkingDirectory $installRoot
Start-Sleep -Seconds 60
Get-Content (Join-Path $installRoot '.bundle_seed_version')   # 期望 0.1.0-beta.1
Test-Path (Join-Path $installRoot '.bundle_seed_status.json')
```

期望：`.bundle_seed_version` 为纯版本号 `0.1.0-beta.1`，`Test-Path` 为 `True`。播种没完成（文件缺失或为空）先解决，否则后面的「标记前进」断言无法成立。

#### 1.5 造根层用户数据标记（离线覆盖安装要证明这些不被清掉）

```powershell
$marker = 'offline_update_marker_20261120'

# config：追加一条自定义键
Add-Content -Path (Join-Path $installRoot 'config\project.yml') -Value ('test_offline_marker: "' + $marker + '"')
Select-String -Path (Join-Path $installRoot 'config\project.yml') -Pattern 'test_offline_marker'

# custom：放一个用户文件
New-Item -ItemType Directory -Force (Join-Path $installRoot 'custom') | Out-Null
Set-Content -Path (Join-Path $installRoot 'custom\offline_update_marker.txt') -Value $marker -Encoding UTF8
(Get-Content (Join-Path $installRoot 'custom\offline_update_marker.txt') -Raw).Trim()
```

期望：`Select-String` 查到 `test_offline_marker: "offline_update_marker_20261120"`；最后一行输出 `offline_update_marker_20261120`。

#### 1.6 记录 `assets/models` 的文件数与哈希（主包不含模型，这一步按目录是否存在分开处理）

```powershell
$modelsDir = Join-Path $installRoot 'assets\models'
$modelsManifest = Join-Path $env:TEMP 'onedragon_assets_models_beta1.csv'
$modelsExist = Test-Path $modelsDir
$modelsExist
if ($modelsExist) {
  Get-ChildItem $modelsDir -Recurse -File -Force |
    ForEach-Object {
      [PSCustomObject]@{
        Rel  = $_.FullName.Substring($modelsDir.Length + 1)
        Hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
      }
    } | Sort-Object Rel | Export-Csv $modelsManifest -NoTypeInformation -Encoding UTF8
  "assets\models 文件数 = $((Import-Csv $modelsManifest).Count)"
} else {
  Write-Host 'assets\models 不存在（主包不带模型，属正常）。本项按「覆盖前后都不存在」判，若要先测模型保留，请先按设计文档 4.5 节解压离线模型包，再重跑本步造清单'
}
```

期望：要么打印 `True` 与文件数，要么打印 `False` 加提示。两种都要把结论记进第 12 节 6.4 行。

#### 1.7 记录 beta.1 的 `current\` 特征，并放一个 beta.1 独有的文件

```powershell
$exePath = Join-Path $installRoot 'current\OneDragon.exe'
$before = [PSCustomObject]@{
  Sha256      = (Get-FileHash $exePath -Algorithm SHA256).Hash
  FileVersion = (Get-Item $exePath).VersionInfo.FileVersion
  SqVersion   = ([xml](Get-Content (Join-Path $installRoot 'current\sq.version') -Raw)).package.metadata.version
}
$before | Format-List

# 两个版本由同一份代码构建，exe 哈希可能完全一样，靠哈希证不了「current 被替换」；放一个文件进 current 才可靠
$staleMarker = Join-Path $installRoot 'current\_stale_beta1_marker.txt'
Set-Content -Path $staleMarker -Value 'beta.1 only' -Encoding UTF8
Test-Path $staleMarker    # 期望 True
```

期望：`SqVersion` 为 `0.1.0-beta.1`；`Test-Path` 为 `True`。`Sha256` / `FileVersion` 记下来供第 4.3 步对照。

### 步骤 2：退出应用，确认没有 `OneDragon.exe` 进程

```powershell
Get-Process OneDragon -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
$procs = @(Get-CimInstance Win32_Process -Filter "name='OneDragon.exe'")
if ($procs.Count -ne 0) {
  $procs | Select-Object ProcessId, ParentProcessId, CommandLine | Format-Table -AutoSize
  Write-Host 'FAIL: 还有 OneDragon.exe 在运行，覆盖安装前必须全部退出'; exit 1
}
$upd = @(Get-CimInstance Win32_Process -Filter "name='Update.exe'")
if ($upd.Count -ne 0) { $upd | Select-Object ProcessId, CommandLine | Format-Table -AutoSize; Write-Host 'FAIL: 还有 Update.exe 在运行'; exit 1 }
Write-Host 'PASS: 覆盖安装前没有 OneDragon.exe / Update.exe 在运行'
```

期望：最后打印 `PASS`，退出码 0。有残留先解决，再跑一次本步。

### 步骤 3：运行 beta.2 的 `Setup.exe` 覆盖安装

#### 3.1 安装器会不会询问目录、能不能选择同一目录

预计行为（Velopack 单用户安装器，以实测为准）：

| 观察点 | 预期 | 记录实际结果 |
| :--- | :--- | :--- |
| 有没有目录选择页 | **没有**。固定装到 `%LocalAppData%\<packId>`，不提供「选安装目录」向导页 | |
| 能不能指定同一目录 | 默认就不需要选：只要前置安装（1.2 步）也是用 `Setup.exe` 装的，覆盖目标天然就是同一个安装根 | |
| 已有安装时是覆盖还是并存 | **覆盖**已有安装（同一目录替换 `current\`），`%LocalAppData%` 下不会出现第二个 OneDragon 目录 | |
| 要不要人工确认 | 交互式运行会弹安装进度窗口，按界面提示走完；无人值守可用 `--silent` | |
| 完成后会不会自动启动应用 | 取决于安装器完成页的勾选。自动拉起也罢，本节都要求先确认播种完成（见 4.4）再做 4.5–4.7 的断言 | |

如果本次实测发现安装器**会**询问目录或接受目录参数（例如 `--installto`），就照它给的选项装到 `$installRoot`，并把参数原文与界面截图记进第 12 节；不要为了贴合本文的预期去改安装位置。

**如果它总是装到默认位置怎么办：**

1. **不要**手工把 beta.1 的安装目录搬 / 复制到默认位置。Velopack 靠安装时登记的信息判断「是否已安装」，手工搬移会让它认不出已有安装，退化成全新安装，那测的就不是「覆盖」了。
2. 正确做法是让前置安装也发生在默认位置：1.2 步本来就是用 beta.1 的 `Setup.exe` 装的，安装器默认去的地方就是 beta.1 的安装根，beta.2 自然覆盖同一目录。这也是为什么 1.2 步不让你拿 `Portable.zip` 解压目录当安装根。
3. 如果 beta.1 之前只以 Portable 解压形式存在于 `C:\TestOneDragon` 这类目录，那个目录不在本节测试范围内（`Setup.exe` 不会去覆盖解压目录）：按 1.2 节用 `Setup.exe` 重装一次 beta.1 再测。
4. 万一装出两个目录（beta.1 与 beta.2 并存），直接判失败，把两个目录路径都记进第 12 节——这不是符合预期的覆盖行为。

#### 3.2 执行覆盖安装

```powershell
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$p2 = Start-Process -FilePath $setup2 -Wait -PassThru
$sw.Stop()
"beta.2 Setup 退出码 = $($p2.ExitCode)，耗时 $([math]::Round($sw.Elapsed.TotalSeconds,1)) 秒"
if ($p2.ExitCode -ne 0) { Write-Host 'FAIL: beta.2 安装器退出码非 0'; exit 1 }
```

无人值守写法（需要时改这一行）：`Start-Process -FilePath $setup2 -ArgumentList '--silent' -Wait -PassThru`。

期望：退出码 0。随后断言安装根没变、没有多出第二个安装目录：

```powershell
$installRoot
Test-Path (Join-Path $installRoot 'current\OneDragon.exe')   # 期望 True
Get-ChildItem $env:LOCALAPPDATA -Directory | Where-Object { $_.Name -like '*OneDragon*' } |
  Select-Object FullName, LastWriteTime
```

期望：`$installRoot` 与 1.3 步记录的值**完全一致**；`Test-Path` 为 `True`；最后一条只列出一个目录，且就是 `$installRoot`。

### 步骤 4：断言

#### 4.1 根层的 `config\project.yml` 与 `custom\` 标记还在

```powershell
$yml = Join-Path $installRoot 'config\project.yml'
$customFile = Join-Path $installRoot 'custom\offline_update_marker.txt'

Select-String -Path $yml -Pattern 'test_offline_marker'

$configOk = [bool](Select-String -Path $yml -Pattern 'test_offline_marker')
if (-not $configOk) { Write-Host 'FAIL: 覆盖安装后 config\project.yml 里的 test_offline_marker 丢了'; exit 1 }
if (-not (Test-Path $customFile)) { Write-Host 'FAIL: 覆盖安装后 custom\offline_update_marker.txt 被删了'; exit 1 }
$customText = (Get-Content $customFile -Raw).Trim()
"custom marker = '$customText'"
if ($customText -ne $marker) { Write-Host "FAIL: custom 标记内容变了（期望 '$marker'，实际 '$customText'）"; exit 1 }
Write-Host 'PASS: 根层 config / custom 用户数据保留'
```

期望：打印 `PASS`，退出码 0。任一失败即「离线覆盖安装丢用户数据」，是阻断项，原样贴输出回 Issue。

#### 4.2 `assets\models` 的文件数与哈希不变

```powershell
if (-not $modelsExist) {
  Write-Host 'SKIP: 前置时 assets\models 不存在，覆盖后应仍然不存在'
  Test-Path (Join-Path $installRoot 'assets\models')   # 期望 False
} else {
  $afterRows = Get-ChildItem $modelsDir -Recurse -File -Force |
    ForEach-Object {
      [PSCustomObject]@{
        Rel  = $_.FullName.Substring($modelsDir.Length + 1)
        Hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
      }
    } | Sort-Object Rel
  $beforeRows = Import-Csv $modelsManifest
  $diff = Compare-Object -ReferenceObject $beforeRows -DifferenceObject $afterRows -Property Rel, Hash
  "before=$($beforeRows.Count) after=$($afterRows.Count) diff=$(($diff | Measure-Object).Count)"
  if ($beforeRows.Count -ne $afterRows.Count -or $diff) {
    $diff | Format-Table -AutoSize
    Write-Host 'FAIL: assets\models 的文件数或哈希发生变化'
    exit 1
  }
  Write-Host 'PASS: assets\models 文件数与每个文件的 SHA256 与前置清单完全一致'
}
```

期望：走 `PASS` 分支（或按前置记录走 `SKIP` 分支并确认目录仍不存在），退出码 0。

#### 4.3 `current\` 被整体替换

```powershell
$exePath = Join-Path $installRoot 'current\OneDragon.exe'
$staleMarker = Join-Path $installRoot 'current\_stale_beta1_marker.txt'
$sq = Join-Path $installRoot 'current\sq.version'

# ① 目录被整目录替换的硬证据：前置时手工放进 current\ 的文件必须消失
Test-Path $staleMarker                       # 期望 False
if (Test-Path $staleMarker) { Write-Host 'FAIL: current\ 没有被整体替换（beta.1 里手工放的文件还在）'; exit 1 }

# ② 版本必须换了：复用第 5 节第 5 步的 nuspec 解析方式
$nodeVersion = ([xml](Get-Content $sq -Raw)).package.metadata.version
$after = [PSCustomObject]@{
  Sha256      = (Get-FileHash $exePath -Algorithm SHA256).Hash
  FileVersion = (Get-Item $exePath).VersionInfo.FileVersion
  SqVersion   = $nodeVersion
}
"前置: $($before.Sha256) / $($before.FileVersion) / $($before.SqVersion)"
"现在: $($after.Sha256) / $($after.FileVersion) / $($after.SqVersion)"
if ($nodeVersion -ne '0.1.0-beta.2') { Write-Host "FAIL: current\sq.version 解析出 '$nodeVersion'，不是 0.1.0-beta.2"; exit 1 }
Write-Host 'PASS: current\ 已被替换，sq.version 前进到 0.1.0-beta.2'
```

期望：`Test-Path` 为 `False`；`sq.version` 的 `<version>` 节点为 `0.1.0-beta.2`；最后打印 `PASS`。

> 两个版本的包由同一份代码构建，`current\OneDragon.exe` 的 SHA256 与 `FileVersion` **可能完全相同**，哈希相同不构成失败——所以 ① 那个标记文件才是「整目录被替换」的硬证据，哈希只作记录。若哈希确实变了，在记录表里写明「二进制也确实换了」；若没变，写明「同代码重建，二进制一致属预期」。

#### 4.4 启动一次，让升级后的首次播种跑完

若安装器在完成页已经自动拉起了应用，跳过启动命令，只等播种完成后继续。

```powershell
Start-Process -FilePath (Join-Path $installRoot 'OneDragon.exe') -WorkingDirectory $installRoot
Start-Sleep -Seconds 60
```

#### 4.5 `.bundle_seed_version` 与 `.bundle_seed_status.json` 四项都是 `0.1.0-beta.2`

```powershell
$seed = (Get-Content (Join-Path $installRoot '.bundle_seed_version') -Raw).Trim()
$status = Get-Content (Join-Path $installRoot '.bundle_seed_status.json') -Raw | ConvertFrom-Json
"seed = '$seed'"
$status | Format-List

if ([string]::IsNullOrWhiteSpace($seed)) { Write-Host 'FAIL: .bundle_seed_version 为空'; exit 1 }
if ($seed -match '[<>]') { Write-Host 'FAIL: .bundle_seed_version 里是 nuspec XML 全文，不是纯版本号'; exit 1 }
if ($seed -ne '0.1.0-beta.2') { Write-Host "FAIL: .bundle_seed_version 是 '$seed'，没有前进到 0.1.0-beta.2"; exit 1 }
$bad = $status.PSObject.Properties | Where-Object { $_.Value -ne '0.1.0-beta.2' }
if ($bad) {
  $bad | ForEach-Object { Write-Host "FAIL: .bundle_seed_status.json 的 $($_.Name) = '$($_.Value)'" }
  exit 1
}
Write-Host 'PASS: 两个播种标记四项全部前进到 0.1.0-beta.2'
```

期望：`seed` 为 `0.1.0-beta.2`；`template` / `ui` / `text` / `game_data` 四项都是 `0.1.0-beta.2`；最后打印 `PASS`。

#### 4.6 四类只读资源的文件数仍与包内一致

复用第 5 节第 4 步（D2）的动态计数循环，不写死数字，只是把路径从 `C:\TestOneDragon` 换成 `$installRoot`：

```powershell
$trees = 'template', 'ui', 'text', 'game_data'
$ok = $true
foreach ($tree in $trees) {
  $rootCount = (Get-ChildItem -Path (Join-Path $installRoot "assets\$tree") -Recurse -File -Force).Count
  $pkgCount  = (Get-ChildItem -Path (Join-Path $installRoot "current\_internal\resources\assets\$tree") -Recurse -File -Force).Count
  if ($rootCount -ne $pkgCount) { $ok = $false }
  $verdict = if ($rootCount -eq $pkgCount) { '一致' } else { '不一致' }
  '{0,-10} 根层 {1,5} / 包内 {2,5} -> {3}' -f $tree, $rootCount, $pkgCount, $verdict
}
if (-not $ok) { Write-Host 'FAIL: 覆盖安装后至少一类只读资源的文件数与包内不一致'; exit 1 }
Write-Host 'PASS: 四类只读资源文件数与包内逐一相等'
```

期望：四行都以 `一致` 结尾，最后打印 `PASS`，退出码 0。根层少于包内 → 播种没跑完；根层多于包内 → 新旧文件混合，都是失败，把数字记进第 12 节。

#### 4.7 启动后只有 1 个 `current\OneDragon.exe` 进程

复用 5.2 节（D4）的单进程与 `--version` 检查：

```powershell
$procs = @(Get-CimInstance Win32_Process -Filter "name='OneDragon.exe'")
$procs | Select-Object ProcessId, ParentProcessId, CommandLine | Format-Table -AutoSize
if ($procs.Count -ne 1) { Write-Host "FAIL: OneDragon.exe 进程数为 $($procs.Count)"; exit 1 }
if ($procs[0].CommandLine -notmatch 'current\\OneDragon\.exe') { Write-Host 'FAIL: 存活进程不是 current\OneDragon.exe'; exit 1 }
if ($procs[0].CommandLine -match '--version') { Write-Host 'FAIL: 出现了 --version 自启进程'; exit 1 }
Write-Host 'PASS: 只剩一个 current\OneDragon.exe'
```

期望：进程表只有一行且是 `current\OneDragon.exe`；最后打印 `PASS`，退出码 0。

#### 4.8 收尾

```powershell
Get-Process OneDragon -ErrorAction SilentlyContinue | Stop-Process -Force
```

**本节通过标准**：4.1–4.7 全部 `PASS`，退出码均为 0；且第 12 节 6.1–6.7 行填了实际结果。任何一条 `FAIL` 都算离线覆盖安装不成立，原样贴输出回 Issue，不要靠改断言让它变绿。

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
   Get-Content .\.bundle_seed_status.json                              # 期望四项都是 0.1.0-beta.2
   Get-Content .\.bundle_seed_version                                  # 期望 0.1.0-beta.2
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

> 源码模式的唯一入口是 `uv run src/zzz_od/gui/app.py`（仓库根目录下执行）。仓库根目录**没有** `main.py`，验收口径不提 `main.py`；父单 PLAY-2 正文里写的 `python main.py` 是笔误，以本节为准。

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

## 10. 旧数据迁移（B 阶段新增，父单「迁移方案确认」）

本节对应设计文档第 7 节，口径以人类 2026-11-20 的确认（父单评论「迁移方案确认：5 项按下面执行」）为准，与第 7 节原文冲突的地方按本节执行：

- 探测只做**方案 A**：首启弹窗手动选目录，**不扫描驱动器、不读快捷方式**；
- 弹窗只在**纯首启**出现（新根层只有播种出来的默认配置，且没有迁移标记）；升级后的日常启动不弹；
- 两个跳过项：**「我是新用户」写 `dismissed`、「以后再说」写 `skipped`**，两者之后都**不再主动弹窗、不挂横幅**，只保留设置页入口；
- 延迟迁移**默认保留新版的修改**，只有核心冲突（游戏路径、主账号等）才弹差异清单；
- `plugins/` **不迁移**，只在设置页卡片上引导重新安装；
- 备份 `config_backup_<YYYYMMDD_HHMMSS>/` **永久保留**，程序不自动删；设置页卡片显示备份目录数与总占用。

> **本节在 arm-1 上一条都无法执行**（aarch64 Linux，跑不了 Windows 冻结包）。下面每一步都是给 Windows 真机准备的可粘贴命令，跑完把实际输出与 `PASS` / `FAIL` 填进第 12 节记录表。跑不了的写「未执行 + 原因」，不要按代码推断为通过。

### 10.0 通用准备与清单工具

1. 准备两个目录：新根层 `<解压目录>`（示例 `C:\TestOneDragon-Mig`）与旧安装目录（示例 `C:\TestOneDragon-Legacy`）。

   ```powershell
   $newRoot = 'C:\TestOneDragon-Mig'
   $legacy  = 'C:\TestOneDragon-Legacy'
   Remove-Item -Recurse -Force $newRoot, $legacy -ErrorAction SilentlyContinue
   $zip = (Get-ChildItem <仓库根目录>\deploy\dist\releases -Filter '*win-Portable.zip' | Select-Object -First 1).FullName
   Expand-Archive -Path $zip -DestinationPath $newRoot
   Get-ChildItem $newRoot | Select-Object Name
   ```

   期望：`OneDragon.exe`、`Update.exe`、`current\` 都在。

2. 造一个旧安装目录。它同时包含白名单数据与所有「严禁迁移」的目录，后面靠它一次验完迁移范围与只读性：

   ```powershell
   $dirs = @(
       'config\00', 'config\01', 'custom\assets\ui\banner',
       'assets\models\onnx_ocr', 'assets\template', 'assets\ui', 'assets\text', 'assets\game_data',
       'plugins\sample_plugin', '.install\python', '.venv\Scripts', '.runtime',
       'src\one_dragon', '.git', '.log', '.debug\images'
   )
   foreach ($d in $dirs) { New-Item -ItemType Directory -Force (Join-Path $legacy $d) | Out-Null }

   [IO.File]::WriteAllBytes((Join-Path $legacy 'OneDragon-Launcher.exe'), [byte[]](0x4D, 0x5A, 0x90, 0x00))
   Set-Content (Join-Path $legacy 'config\project.yml') @'
   test_legacy_marker: from-legacy
   project_name: Legacy OneDragon
   '@
   Set-Content (Join-Path $legacy 'config\env.yml') "game_path: 'D:\OldGamePath'`nlegacy_only_key: old-value`n"
   Set-Content (Join-Path $legacy 'config\game_account.yml') "account: legacy-account`n"
   Set-Content (Join-Path $legacy 'config\00\scheduler.yml') "plan: legacy-instance-zero`n"
   Set-Content (Join-Path $legacy 'config\01\scheduler.yml') "plan: legacy-instance-one`n"
   Set-Content (Join-Path $legacy 'custom\assets\ui\banner\banner.png') 'legacy-banner-bytes'
   $model = New-Object byte[] (1024 * 1024)
   (New-Object Random 42).NextBytes($model)
   [IO.File]::WriteAllBytes((Join-Path $legacy 'assets\models\onnx_ocr\model.onnx'), $model)
   Set-Content (Join-Path $legacy 'assets\template\corrupted_template.png') 'dirty-template'
   Set-Content (Join-Path $legacy 'assets\ui\legacy_ui.txt') 'legacy ui'
   Set-Content (Join-Path $legacy 'assets\text\legacy_text.txt') 'legacy text'
   Set-Content (Join-Path $legacy 'assets\game_data\legacy_data.txt') 'legacy game data'
   Set-Content (Join-Path $legacy 'plugins\sample_plugin\plugin.json') '{"name":"sample"}'
   Set-Content (Join-Path $legacy '.install\python\python.exe') 'legacy-python'
   Set-Content (Join-Path $legacy '.venv\Scripts\python.exe') 'legacy-venv'
   Set-Content (Join-Path $legacy '.runtime\runtime.dll') 'legacy-runtime'
   Set-Content (Join-Path $legacy 'src\one_dragon\os_utils.py') 'legacy-src'
   Set-Content (Join-Path $legacy '.git\HEAD') 'ref: refs/heads/main'
   Set-Content (Join-Path $legacy '.log\legacy_only_marker.log') 'legacy log'
   Set-Content (Join-Path $legacy '.debug\images\shot.png') 'legacy debug'
   ```

   > 旧目录里的 `.log` 用**独有文件名** `legacy_only_marker.log`：新根层自己会播种一个 `.log\`（第 5 节断言它必须存在），所以不能用「`.log` 不存在」来判断，只能断言旧日志文件没被搬过去。

3. 把下面两个函数粘贴进当前 PowerShell 会话。后面所有 SHA-256 断言都靠它们，不要用「看起来一样」代替：

   ```powershell
   function Get-TreeManifest {
       param(
           [Parameter(Mandatory)][string]$Root,
           [switch]$FilesOnly
       )
       $rootFull = (Resolve-Path -LiteralPath $Root).Path
       $items = @()
       foreach ($f in Get-ChildItem -LiteralPath $rootFull -Recurse -File -Force) {
           $items += [pscustomobject]@{
               Kind     = 'File'
               RelPath  = $f.FullName.Substring($rootFull.Length).TrimStart('\')
               Length   = $f.Length
               MtimeUtc = $f.LastWriteTimeUtc.ToString('o')
               Sha256   = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
           }
       }
       if (-not $FilesOnly) {
           foreach ($d in Get-ChildItem -LiteralPath $rootFull -Recurse -Directory -Force) {
               $items += [pscustomobject]@{
                   Kind     = 'Dir'
                   RelPath  = $d.FullName.Substring($rootFull.Length).TrimStart('\')
                   Length   = 0
                   MtimeUtc = $d.LastWriteTimeUtc.ToString('o')
                   Sha256   = ''
               }
           }
       }
       @($items | Sort-Object RelPath)
   }

   function Compare-TreeManifest {
       param(
           [Parameter(Mandatory)][array]$Before,
           [Parameter(Mandatory)][array]$After,
           [switch]$IgnoreMtime,
           [string]$Label = 'manifest'
       )
       $props = @('Kind', 'RelPath', 'Length', 'Sha256')
       if (-not $IgnoreMtime) { $props += 'MtimeUtc' }
       $diffs = @(Compare-Object -ReferenceObject $Before -DifferenceObject $After -Property $props)
       if ($diffs.Count -gt 0) {
           Write-Host "FAIL: $Label 有 $($diffs.Count) 处差异（前 $([Math]::Min(20, $diffs.Count)) 条）："
           $diffs | Select-Object -First 20 | Format-Table -AutoSize | Out-String | Write-Host
           return $false
       }
       Write-Host "PASS: $Label 完全一致（$($Before.Count) 条记录：文件哈希/大小/时间/目录结构）"
       return $true
   }
   ```

   期望：粘贴后 `$Before = Get-TreeManifest $legacy` 能返回非空数组；`Compare-TreeManifest -Before $Before -After $Before -Label '自检'` 打印 `PASS`。

### 10.1 全新首启：选「我是新用户」，之后不再弹窗

1. 从 `<解压目录>` 根层启动（`C:\TestOneDragon-Mig\OneDragon.exe`），等待主窗口出现。

2. 期望：首启出现一次迁移弹窗，含【选择旧版本目录】【我是新用户】【以后再说】三个按钮。点【我是新用户】。

3. 断言标记与目录状态：

   ```powershell
   cd $newRoot
   $status = Get-Content .\.legacy_migration_status.json -Raw -Encoding UTF8 | ConvertFrom-Json
   $status | ConvertTo-Json
   if ($status.status -ne 'dismissed') { Write-Host "FAIL: status=$($status.status)，期望 dismissed"; exit 1 }
   if (@(Get-ChildItem -Force -Directory -Filter 'config_backup_*').Count -ne 0) { Write-Host 'FAIL: 没迁移却生成了 config_backup_*'; exit 1 }
   if (Test-Path .\config\00) { Write-Host 'FAIL: 全新首启不应出现多实例子目录'; exit 1 }
   Write-Host 'PASS: 我是新用户 -> dismissed，无备份、无迁移数据'
   ```

   期望：`status` 为 `dismissed`，最后打印 `PASS`，退出码 0。

4. 关闭应用，记下标记文件的哈希，再启动一次：

   ```powershell
   $markerHash1 = (Get-FileHash .\.legacy_migration_status.json -Algorithm SHA256).Hash
   Start-Process -FilePath (Join-Path $newRoot 'OneDragon.exe') -WorkingDirectory $newRoot
   Start-Sleep -Seconds 60
   ```

   期望（人工观察 + 断言）：**不再出现迁移弹窗**；标记文件哈希不变：

   ```powershell
   $markerHash2 = (Get-FileHash .\.legacy_migration_status.json -Algorithm SHA256).Hash
   if ($markerHash1 -ne $markerHash2) { Write-Host 'FAIL: 第二次启动改写了迁移标记'; exit 1 }
   if (@(Get-ChildItem -Force -Directory -Filter 'config_backup_*').Count -ne 0) { Write-Host 'FAIL: 第二次启动产生了备份目录'; exit 1 }
   Write-Host 'PASS: dismissed 后不再弹窗，标记未被改写'
   ```

5. 打开「设置 → 脚本环境 → 数据管理」页，找到「旧版本数据迁移」卡片，期望状态行显示「当前状态：已跳过（新用户）」，并有【从旧版本导入数据】和【打开所在目录】两个入口，以及「第三方插件（plugins/）不迁移」的说明。

### 10.2 迁移后首启：旧目录 SHA-256 前后比对 + 新根层数据正确 + 再启动不弹窗

> 这是人类点名要求的用例：**旧目录迁移前后逐文件 SHA-256 必须完全一致**，目录结构与 mtime 也要一致。

1. 迁移前导出旧目录清单（文件 + 目录）：

   ```powershell
   $legacyBefore = Get-TreeManifest -Root $legacy
   $legacyBefore | Measure-Object | Select-Object Count
   $legacyBefore | Export-Csv -NoTypeInformation -Encoding UTF8 "$env:TEMP\legacy-before.csv"
   ```

   期望：`Count` 大于 20（示例目录约 24 条）。

2. 启动 `$newRoot\OneDragon.exe`，首启弹窗点【选择旧版本目录】，选中 `C:\TestOneDragon-Legacy`。

3. 期望：出现预览/确认框，展示将迁移的内容（`config/`、`custom/`、`assets/models/`）、总体积，并明确说明旧目录只读。确认迁移，等待完成提示。

4. 迁移后重新导出旧目录清单并逐项比对：

   ```powershell
   $legacyAfter = Get-TreeManifest -Root $legacy
   $ok = Compare-TreeManifest -Before $legacyBefore -After $legacyAfter -Label '旧目录迁移前后'
   if (-not $ok) { exit 1 }
   if ($legacyAfter.Count -ne $legacyBefore.Count) { Write-Host "FAIL: 旧目录文件/目录数 $($legacyBefore.Count) -> $($legacyAfter.Count)"; exit 1 }
   Write-Host "PASS: 旧目录 $($legacyAfter.Count) 条记录逐文件 SHA-256、大小、mtime、目录结构全部未变"
   ```

   期望：打印 `PASS`，退出码 0。**任何一条差异都直接判失败**，把 `Compare-Object` 输出原样贴回 Issue。

5. 断言新根层数据正确、白名单之外一个都没进来：

   ```powershell
   cd $newRoot
   $fail = @()
   foreach ($p in @(
       'config\project.yml', 'config\env.yml', 'config\00\scheduler.yml', 'config\01\scheduler.yml',
       'custom\assets\ui\banner\banner.png', 'assets\models\onnx_ocr\model.onnx'
   )) { if (-not (Test-Path -LiteralPath $p)) { $fail += "缺少白名单文件: $p" } }

   foreach ($p in @('.install', '.venv', '.runtime', 'src', '.git', '.debug', 'plugins')) {
       if (Test-Path -LiteralPath $p) { $fail += "严禁迁移的目录出现在新根层: $p" }
   }
   if (Test-Path -LiteralPath '.log\legacy_only_marker.log') { $fail += '旧 .log 被迁入新根层' }
   if (@(Get-ChildItem -Recurse -File -Force -Filter 'corrupted_template.png').Count -ne 0) { $fail += '旧 assets/template 脏文件被迁入' }
   if (@(Get-ChildItem -Recurse -File -Force -Filter 'legacy_ui.txt').Count -ne 0) { $fail += '旧只读资源 assets/ui 被迁入' }
   if (@(Get-ChildItem -Recurse -File -Force -Filter 'legacy_text.txt').Count -ne 0) { $fail += '旧只读资源 assets/text 被迁入' }
   if (@(Get-ChildItem -Recurse -File -Force -Filter 'legacy_data.txt').Count -ne 0) { $fail += '旧只读资源 assets/game_data 被迁入' }
   if (@(Get-ChildItem -Recurse -File -Force -Filter 'plugin.json' | Where-Object { $_.FullName -notmatch '\\current\\' }).Count -ne 0) { $fail += 'plugins 被迁入新根层' }

   if ($fail.Count -gt 0) { $fail | ForEach-Object { Write-Host "FAIL: $_" }; exit 1 }
   Write-Host 'PASS: 白名单三类数据到位，plugins/只读资源/旧运行时/旧源码/旧日志均未进入新根层'
   ```

6. 断言迁移标记与备份：

   ```powershell
   $status = Get-Content .\.legacy_migration_status.json -Raw -Encoding UTF8 | ConvertFrom-Json
   $status | ConvertTo-Json
   if ($status.status -ne 'migrated') { Write-Host "FAIL: status=$($status.status)"; exit 1 }
   if ($status.source_path -ne $legacy) { Write-Host "FAIL: source_path=$($status.source_path)"; exit 1 }
   if (@(Get-ChildItem -Force -Directory | Where-Object { $_.Name -like '.migration_staging_*' -or $_.Name -like '.config.backup_*' }).Count -ne 0) {
       Write-Host 'FAIL: 迁移成功后有 staging/临时备份残留'; exit 1
   }
   Write-Host 'PASS: 标记 migrated，source_path 正确，无 staging 残留'
   ```

7. 关闭应用，再启动一次，期望**不再弹窗**，配置仍在：

   ```powershell
   $markerHash1 = (Get-FileHash .\.legacy_migration_status.json -Algorithm SHA256).Hash
   Start-Process -FilePath (Join-Path $newRoot 'OneDragon.exe') -WorkingDirectory $newRoot
   Start-Sleep -Seconds 60
   $markerHash2 = (Get-FileHash .\.legacy_migration_status.json -Algorithm SHA256).Hash
   if ($markerHash1 -ne $markerHash2) { Write-Host 'FAIL: 第二次启动改写了迁移标记'; exit 1 }
   if ((Get-Content .\config\project.yml -Raw) -notmatch 'test_legacy_marker') { Write-Host 'FAIL: 迁移后的配置在重启后丢失'; exit 1 }
   Write-Host 'PASS: migrated 后不再弹窗，配置保留'
   ```

### 10.3 延迟迁移覆盖：新版改动保留、备份目录生成、卡片数量与占用正确

1. 全新解压到 `$newRoot` 后首启，弹窗点【以后再说】。

2. 断言 `skipped` 且没有备份：

   ```powershell
   cd $newRoot
   $status = Get-Content .\.legacy_migration_status.json -Raw -Encoding UTF8 | ConvertFrom-Json
   if ($status.status -ne 'skipped') { Write-Host "FAIL: status=$($status.status)，期望 skipped"; exit 1 }
   Write-Host 'PASS: 以后再说 -> skipped'
   ```

3. 关闭应用，在新版里造出「用户已修改」状态（改核心冲突键 `game_path`、加一个普通键、加一张自定义 banner）：

   ```powershell
   Set-Content .\config\env.yml "game_path: 'D:\NewGamePath'`nnew_version_key: new-value`n"
   Add-Content .\config\project.yml "`ntest_delay_marker: keep-me`n"
   Set-Content .\custom\assets\ui\banner\new_banner.png 'new-banner-bytes'
   ```

4. 记录迁移前新根层 `config` / `custom` 的清单（备份内容要等于它）：

   ```powershell
   $newBefore = Get-TreeManifest -Root (Join-Path $newRoot 'config')
   $newCustomBefore = Get-TreeManifest -Root (Join-Path $newRoot 'custom')
   ```

5. 启动应用。期望：**不弹迁移窗**（`skipped` 不主动提示）。进入「设置 → 脚本环境 → 数据管理」页，卡片状态行应为「当前状态：已跳过」，点【从旧版本导入数据】，选择 `C:\TestOneDragon-Legacy` 并确认。

6. 期望：出现「检测到新版本已有配置」弹窗，差异清单里列出 `game_path` 的旧值 `D:\OldGamePath` 与新值 `D:\NewGamePath`，选择【保留新版修改（推荐）】。迁移完成后：

   ```powershell
   cd $newRoot
   $fail = @()
   if ((Get-Content .\config\env.yml -Raw) -notmatch "D:\\NewGamePath") { $fail += '新版 game_path 被旧版覆盖' }
   if ((Get-Content .\config\project.yml -Raw) -notmatch 'test_delay_marker') { $fail += '新版普通键被旧版覆盖' }
   if ((Get-Content .\config\env.yml -Raw) -notmatch 'legacy_only_key') { $fail += '旧版独有键未补齐' }
   if (-not (Test-Path .\config\01\scheduler.yml)) { $fail += '旧版多实例 config/01 未补入' }
   if (-not (Test-Path .\assets\models\onnx_ocr\model.onnx)) { $fail += '旧版模型未补入' }
   if (-not (Test-Path .\custom\assets\ui\banner\new_banner.png)) { $fail += '新版自定义 banner 丢失' }
   if (Test-Path .\plugins) { $fail += 'plugins 被迁入' }
   if ($fail.Count -gt 0) { $fail | ForEach-Object { Write-Host "FAIL: $_" }; exit 1 }
   Write-Host 'PASS: 新版修改保留、旧版缺失项补齐、plugins 未迁入'
   ```

7. 断言备份目录生成，且内容等于迁移前的新根层：

   ```powershell
   $backups = @(Get-ChildItem -Force -Directory -Filter 'config_backup_*')
   if ($backups.Count -ne 1) { Write-Host "FAIL: config_backup_* 数量=$($backups.Count)，期望 1"; exit 1 }
   $name = $backups[0].Name
   if ($name -notmatch '^config_backup_\d{8}_\d{6}$') { Write-Host "FAIL: 备份目录命名不合契约: $name"; exit 1 }
   $backupRoot = $backups[0].FullName

   $backupCfg = Get-TreeManifest -Root (Join-Path $backupRoot 'config')
   $backupCustom = Get-TreeManifest -Root (Join-Path $backupRoot 'custom')
   $ok1 = Compare-TreeManifest -Before $newBefore -After $backupCfg -IgnoreMtime -Label '备份 config 内容'
   $ok2 = Compare-TreeManifest -Before $newCustomBefore -After $backupCustom -IgnoreMtime -Label '备份 custom 内容'
   if (-not ($ok1 -and $ok2)) { exit 1 }

   $status = Get-Content .\.legacy_migration_status.json -Raw -Encoding UTF8 | ConvertFrom-Json
   if ($status.status -ne 'migrated') { Write-Host "FAIL: status=$($status.status)"; exit 1 }
   if ($status.backup_path -ne $name) { Write-Host "FAIL: backup_path=$($status.backup_path)，期望 $name"; exit 1 }
   Write-Host "PASS: 生成 $name，内容等于迁移前的新根层，标记 backup_path 正确"
   ```

8. 断言设置页卡片上的「备份数量 / 总占用」与磁盘实际值一致：

   ```powershell
   $count = $backups.Count
   $bytes = ($backups | Get-ChildItem -Recurse -File -Force | Measure-Object -Property Length -Sum).Sum
   $expected = '{0:N1} MB' -f ($bytes / 1MB)
   Write-Host "期望卡片显示：$count 个备份 / 合计 $bytes 字节（$expected）"
   ```

   期望：卡片文本里的目录数是 `1`，总占用与 `$bytes` 四舍五入到同一单位后相等（录下卡片原文与这里算出的值，差一个数量级或显示 0 都判失败）。

9. 关闭应用，再启动一次，期望不再弹窗、新版修改与备份都还在。

### 10.4 迁移失败回退：新根层恢复原状、无残留

> 用「旧目录里的文件被独占占用」制造复制阶段失败。也可以把新根层设成不可写，但改 ACL 容易留下副作用，优先用锁。

1. 全新解压到 `$newRoot` 并首启，点【以后再说】；关闭应用。

2. 在新版里造一条可辨识的修改，并记录新根层清单：

   ```powershell
   cd $newRoot
   Add-Content .\config\project.yml "`ntest_fail_marker: rollback-me`n"
   $rootBefore = @{
       config  = Get-TreeManifest -Root (Join-Path $newRoot 'config')
       custom  = Get-TreeManifest -Root (Join-Path $newRoot 'custom')
       models  = Get-TreeManifest -Root (Join-Path $newRoot 'assets\models')
   }
   $legacyBeforeFail = Get-TreeManifest -Root $legacy
   ```

3. 独占占用旧目录里的一个模型文件（`FileShare.None`，其他进程读不到）：

   ```powershell
   $lock = [System.IO.File]::Open("$legacy\assets\models\onnx_ocr\model.onnx", 'Open', 'Read', 'None')
   ```

4. 启动应用 → 设置页 →【从旧版本导入数据】→ 选择 `C:\TestOneDragon-Legacy` → 确认迁移。

5. 期望：出现「迁移未完成」提示并给出失败原因；应用**不崩溃、不退出**。关闭提示框。

6. 断言新根层恢复到迁移前状态、无任何残留：

   ```powershell
   cd $newRoot
   $ok = $true
   $ok = (Compare-TreeManifest -Before $rootBefore.config -After (Get-TreeManifest -Root (Join-Path $newRoot 'config')) -Label '回退后 config') -and $ok
   $ok = (Compare-TreeManifest -Before $rootBefore.custom -After (Get-TreeManifest -Root (Join-Path $newRoot 'custom')) -Label '回退后 custom') -and $ok
   $ok = (Compare-TreeManifest -Before $rootBefore.models -After (Get-TreeManifest -Root (Join-Path $newRoot 'assets\models')) -Label '回退后 assets/models') -and $ok
   if (-not $ok) { exit 1 }

   $staging = @(Get-ChildItem -Force -Directory | Where-Object { $_.Name -like '.migration_staging_*' })
   $tmpBackup = @(Get-ChildItem -Force -Directory | Where-Object { $_.Name -like '.config.backup_*' })
   $backups = @(Get-ChildItem -Force -Directory -Filter 'config_backup_*')
   if ($staging.Count -ne 0)   { Write-Host "FAIL: 残留 staging: $($staging.Name -join ', ')"; exit 1 }
   if ($tmpBackup.Count -ne 0) { Write-Host "FAIL: 残留 .config.backup_*: $($tmpBackup.Name -join ', ')"; exit 1 }
   if ($backups.Count -ne 0)   { Write-Host "FAIL: 失败却留下 config_backup_*: $($backups.Name -join ', ')"; exit 1 }
   $status = Get-Content .\.legacy_migration_status.json -Raw -Encoding UTF8 | ConvertFrom-Json
   if ($status.status -eq 'migrated') { Write-Host 'FAIL: 迁移失败却写了 migrated 标记'; exit 1 }
   if ((Get-Content .\config\project.yml -Raw) -notmatch 'test_fail_marker') { Write-Host 'FAIL: 回退后新版配置丢失'; exit 1 }
   if (Test-Path .\config\01\scheduler.yml) { Write-Host 'FAIL: 失败后仍留下了旧目录的部分文件'; exit 1 }
   Write-Host 'PASS: 新根层逐文件恢复原状，无 staging/临时备份/持久备份残留，未写 migrated 标记'
   ```

7. 释放锁，再对旧目录做一次前后比对（失败的这次也不能写旧目录）：

   ```powershell
   $lock.Close(); $lock.Dispose()
   $ok = Compare-TreeManifest -Before $legacyBeforeFail -After (Get-TreeManifest -Root $legacy) -Label '失败流程后的旧目录'
   if (-not $ok) { exit 1 }
   ```

8. 在「设置 → 脚本环境 → 数据管理」重新点【从旧版本导入数据】并发起迁移，期望这次成功；关闭并重启应用，确认数据可用。

### 10.5 C1：首启后根层没有 `.install/` 和 `.venv/`

> 验收背景：冻结模式此前会在根层创建这两个空目录（来自旧启动器的环境路径初始化）。C1 要求从源头不创建，而不是创建后删除。用 10.1 或 10.2 已经完成首启的 `$newRoot` 直接断言。

```powershell
cd $newRoot
$fail = @()
if (Test-Path -LiteralPath '.install') { $fail += '根层存在 .install' }
if (Test-Path -LiteralPath '.venv')    { $fail += '根层存在 .venv' }
$nested = @(Get-ChildItem -Recurse -Directory -Force | Where-Object { $_.Name -in @('.install', '.venv') })
if ($nested.Count -ne 0) { $fail += "根层下仍存在 .install/.venv: $($nested.FullName -join ', ')" }
if ($fail.Count -gt 0) { $fail | ForEach-Object { Write-Host "FAIL: $_" }; exit 1 }
Write-Host 'PASS: 首启后根层没有 .install / .venv'
```

期望：打印 `PASS`，退出码 0。同时确认 `config\`、`assets\`、`custom\`、`.log\` 仍然存在（C1 不能靠少建目录顺手把正常目录也省掉）：

```powershell
foreach ($p in @('config', 'assets', 'custom', '.log')) {
    if (-not (Test-Path -LiteralPath $p)) { Write-Host "FAIL: 正常目录缺失: $p"; exit 1 }
}
Write-Host 'PASS: 正常根层目录齐全'
```

## 11. 未验证项（本次不覆盖，交付时需人类单独确认）

以下几项设计文档第 5 节已明确标注「未验证，写入交付说明供人类验收确认」，本清单不把它们算作通过：

1. **点界面的「检查更新」按钮**：完整走一遍「发现新版本 → 下载 → 进度 → 立即重启/下次启动应用」的 UI 交互，确认按钮可用、状态流转正确、错误提示可重试。本清单第 6 节只验证了命令行 `Update.exe apply` 的增量升级，6.1 节只验证了离线 `Setup.exe` 覆盖安装，两者都没覆盖应用内更新 UI。
2. **首页检查更新的 10 分钟冷却与失败退避（N4）**：自动检查在切回首页时触发、刻意隐藏了时间戳，人工只能通过「短时间内反复切回首页不应反复发起检查」间接观察，无法逐档验证 600/1200/2400/4800/7200 秒的退避阶梯；这部分由单测覆盖，不在本清单断言。
3. **窗口渲染**：主窗口、各页面、更新提示浮层的实际渲染效果（布局、字体、深浅色主题、高 DPI）是否符合设计要求。
4. **`Setup.exe` 安装器的图形界面观感**：安装 / 覆盖安装的进度窗口、完成页、快捷方式创建、卸载项渲染属于视觉项，由人类看界面确认。**功能断言（覆盖后根层数据保留、`current\` 被替换、版本标记前进、单进程）已经写在 6.1 节并可粘贴执行，但同样未实测**；不要因为界面看着正常就判 6.1 通过，必须把 6.1 的 `PASS` / `FAIL` 输出记进记录表。

另外，以下项在 arm-1 上同样无法验证，需要人类或 CI 环境确认，不算本清单通过：

- `vpk pack`、PyInstaller 冻结构建本身是否成功（arm-1 是 Linux，无法执行）。
- SignPath 签名后的三个 exe 是否都带合法签名（Windows 上用第 4.1 节与第 4.3 节核查；arm-1 上只能确认 workflow 与 `sign_file.ps1` 的代码路径，不能执行签名）。
- 离线模型包 `ZenlessZoneZero-OneDragon-Models.zip` 解压到根层后离线可用。
- 离线更新（新 `Setup.exe` 覆盖安装到已有目录）后的数据保留与版本前进：步骤与断言见 6.1 节，**未实测**。
- CNB 镜像同步 `RELEASES` / `releases.win.json` / `.nupkg` 是否完整。
- 旧数据迁移的全部场景（第 10 节：全新首启、迁移后首启、延迟迁移覆盖、失败回退、C1）：需要 Windows 冻结包与真实弹窗交互，arm-1 无法执行；单测覆盖到的只是迁移核心函数，不等于真机通过。

## 12. 执行记录表

| 编号 | 步骤 | 期望结果 | 实际结果 | 结论（通过/失败） | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 构建单目录产物 | 退出码 0，`deploy\dist\OneDragon\OneDragon.exe` 存在 | | | |
| 2 | 打 `0.1.0-beta.1` | 退出码 0 | | | |
| 2.2 | 另存 beta.1 的安装器 | `deploy\dist\installers\0.1.0-beta.1\` 下有 `Setup.exe` / `Portable.zip`，记下 `Setup.exe` 的 SHA256 | | | 第 6.1 节前置 |
| 3 | 打 `0.1.0-beta.2`（同一 outputDir） | 退出码 0 | | | |
| 3.1 | 另存 beta.2 的安装器 | `Setup.exe` 的 SHA256 与 2.2 记录的不同 | | | 第 6.1 节前置 |
| 4 | 产物断言 | `Setup.exe` / `win-Portable.zip` / `RELEASES` / `releases.win.json` / 两个 nupkg 齐全 | | | |
| 4.1 | 签名验证（B1） | `Setup.exe` / `OneDragon.exe` / `Update.exe` 的 `Get-AuthenticodeSignature` 全为 `Valid` | | | |
| 4.2 | 非发布版本号（S5） | PR 构建为 `0.0.0-pr.<n>.g<sha>`，分支构建为 `0.0.0-dev.g<sha>`，匹配 SemVer2 | | | |
| 4.3 | nupkg 内 exe 签名（B1-c） | 每个 `*-full.nupkg` 内的 `OneDragon.exe` / `Update.exe` 全部 `Valid` | | | |
| 5 | 便携版首启播种 | `config` / `assets` / `custom` / `.log` / `.bundle_seed_version` / `.bundle_seed_status.json` 存在；四类资源逐个目录比对「根层 `assets\<tree>` 文件数 == 包内 `current\_internal\resources\assets\<tree>` 文件数」全部为 `一致`；两个版本文件内容都是纯版本号，且等于 `current\sq.version` 的 `<version>` 节点 | | | |
| 5.1 | 残留清理与失败重试（N1/N3） | 残留 `.new-*` / `.old-*` 被清且不误删其他目录；播种失败时应用不崩、出现一次 InfoBar、版本标记不前进、恢复后只重试失败目录 | | | 可选负向验证 |
| 5.2 | `--version` 递归自启（D4） | 20 秒后进程表只有一条 `current\OneDragon.exe`、无 `--version` 子进程；60 秒内进程数不增长；日志不再周期性重复 `Overlay 已启用`；`current\OneDragon.exe --version` 15 秒内打印纯版本号并退出码 0 | | | Windows 真机必测 |
| 5.3 | 播种版本标记为纯版本号（D5） | `.bundle_seed_version` / `.bundle_seed_status.json` 不含 `<`，等于 `current\sq.version` 的 `<version>` 节点；老用户升级后只全量重播一次 | | | |
| 6 | 就地升级（在线增量：`Update.exe apply`） | `current\sq.version` 为 `0.1.0-beta.2`，`config\project.yml` 的 `test_custom_marker` 保留 | | | |
| 6.1 | 离线前置：beta.1 `Setup.exe` 安装 + 造标记 | 安装根已记录（含 `current\OneDragon.exe` / `Update.exe`）；首启后 `.bundle_seed_version` = `0.1.0-beta.1`；`config\project.yml` 有 `test_offline_marker`；`custom\offline_update_marker.txt` 存在；`assets\models` 清单已导出或确认不存在；`current\_stale_beta1_marker.txt` 已放 | | | **未实测**，人类要求补测 |
| 6.2 | 退出应用后运行 beta.2 `Setup.exe` 覆盖安装 | 覆盖前无 `OneDragon.exe` / `Update.exe`；Setup 退出码 0；安装根与 6.1 完全一致；`%LocalAppData%` 下只有一个 OneDragon 安装目录；安装器行为（有没有目录选择页）已记录 | | | **未实测** |
| 6.3 | 根层用户数据保留 | `test_offline_marker` 仍在，`custom\offline_update_marker.txt` 内容不变 | | | **未实测** |
| 6.4 | `assets\models` 不变 | 文件数与每个文件的 SHA256 与前置清单完全一致（或前后都不存在） | | | **未实测** |
| 6.5 | `current\` 被整体替换 | `current\_stale_beta1_marker.txt` 消失；`current\sq.version` 的 `<version>` = `0.1.0-beta.2`；exe 哈希与 FileVersion 变化已记录 | | | **未实测** |
| 6.6 | 播种标记前进 | `.bundle_seed_version` = `0.1.0-beta.2`（纯版本号），`.bundle_seed_status.json` 四项都是 `0.1.0-beta.2` | | | **未实测** |
| 6.7 | 只读资源与进程 | 四类资源根层文件数 == 包内文件数；启动后只有 1 个 `current\OneDragon.exe`，无 `--version` 子进程 | | | **未实测** |
| 7 | 日志检索 | 「不是有效的 Git 仓库」计数 0，「尝试下一个代码源」计数 0 | | | |
| 7.1 | S4 覆盖与合并 | 只读资源残留被清、手工改动被盖回；`doc_link` 被补齐、`test_custom_marker` 保留；`.bundle_seed_status.json` 四项都为 `0.1.0-beta.2` | | | |
| 8 | 源码模式 | `is_velopack_mode()` 为 `False`，`get_work_dir()` 为仓库根目录，GUI 正常 | | | |
| 9 | 进程清理 | 退出后无 `OneDragon` / `Update` 残留进程 | | | |
| 10 | 未验证项 | 应用内检查更新 UI / 窗口渲染 / `Setup.exe` 安装器界面观感 | | | 需人类单独确认 |
| 10.1 | 全新首启选「我是新用户」 | 只弹一次窗；`.legacy_migration_status.json` 的 `status` 为 `dismissed`；无 `config_backup_*`；第二次启动不再弹窗且标记哈希不变 | | | **未实测**，Windows 真机 |
| 10.2 | 迁移后首启（旧目录 SHA-256 比对） | 旧目录迁移前后逐文件 SHA-256、大小、mtime、目录结构 **100% 一致**（`Compare-TreeManifest` 打印 `PASS`）；新根层只有 `config/`（含多实例）、`custom/`、`assets/models/`；`plugins/.install/.venv/.runtime/src/.git/.debug` 与只读资源脏文件均未进入；标记 `migrated`、`source_path` 正确；重启不弹窗 | | | **未实测**，人类点名用例 |
| 10.3 | 延迟迁移覆盖 | 首启 `skipped` 后不弹窗；设置页迁移保留新版 `game_path` 与普通键、补入旧版多实例/模型；生成且仅生成一个 `config_backup_<YYYYMMDD_HHMMSS>`，内容等于迁移前的新根层；标记 `migrated` 且 `backup_path` 正确；卡片备份数与总占用与磁盘一致 | | | **未实测**，Windows 真机 |
| 10.4 | 迁移失败回退 | 旧目录文件被独占占用时提示「迁移未完成」且应用不崩；`config` / `custom` / `assets/models` 清单与迁移前逐文件一致；无 `.migration_staging_*`、`.config.backup_*`、`config_backup_*` 残留；未写 `migrated`；旧目录清单也未变；释放锁后重试成功 | | | **未实测**，Windows 真机 |
| 10.5 | C1：根层无 `.install` / `.venv` | 首启后根层及递归子目录都没有 `.install`、`.venv`；`config` / `assets` / `custom` / `.log` 仍齐全 | | | **未实测**，Windows 真机 |
