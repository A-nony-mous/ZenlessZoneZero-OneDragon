# ZenlessZoneZero-OneDragon 改用 Velopack 分发与自动升级技术设计

- **关联 Issue**：PLAY-2 / PLAY-3
- **目标分支**：`feat/velopack`
- **设计状态**：待评审（In Review）

---

## 0. 工作区与环境安全规范

- **执行环境**：工作区机器为 `arm-1`（aarch64 Linux），路径固定为 `/home/ubuntu/work/ZenlessZoneZero-OneDragon`。
- **不污染远端与推送防护**：
  - 本地代码只在 `feat/velopack` 提交，**绝对不 push 任何远端**，不推 fork，不配推送凭据，不跑 GitHub Actions。
  - **防止误推主仓措施**：为彻底防止后续开发或脚本误触发推送，工作区内已将 `origin` 的 push URL 覆写为无效地址：
    ```bash
    git remote set-url --push origin DISABLED_NO_PUSH
    ```
  - 后续阶段开发产物将在本地分支固化，由人类后续直接从该机器拉取。

---

## 1. 改动清单

本清单覆盖父单 PLAY-2「落地要点 1–6」以及「尚未完成」全部任务项。

| 文件路径 | 变更类型 | 改动内容简述 | 关键接口签名 | 主要调用点 |
| :--- | :--- | :--- | :--- | :--- |
| `pyproject.toml` | 修改 | 添加 `velopack==1.2.161` 依赖项 | 声明依赖 | `uv sync`, `pip install` |
| `src/one_dragon/utils/os_utils.py` | 修改 | 适配 Velopack 目录层级契约与运行模式识别 | `get_velopack_root() -> Path \| None`<br>`is_velopack_mode() -> bool`<br>`get_bundle_dir() -> Path \| None`<br>`get_work_dir() -> str` | `app.py::main`<br>`bundle_seed.py`<br>`updater.py`<br>`git_service.py` |
| `src/one_dragon/utils/bundle_seed.py` | 新增 | 冻结环境首次启动与升级后资源初始化与配置补齐 | `ensure_work_dir_ready() -> None` | `src/zzz_od/gui/app.py::main()` |
| `src/one_dragon/utils/updater.py` | 新增 | Velopack Python SDK 封装（生命周期钩子、更新检查、下载与就地应用） | `init_velopack() -> None`<br>`is_supported() -> bool`<br>`get_update_source(project_config) -> IUpdateSource`<br>`check_for_updates() -> UpdateInfo \| None`<br>`download_and_apply(update_info, callback, restart=True) -> None` | `src/zzz_od/gui/app.py::main()`<br>`src/zzz_od/gui/view/home/home_interface.py` |
| `src/zzz_od/gui/app.py` | 修改 | 启动最早阶段插入 `init_velopack()` 与 `ensure_work_dir_ready()`；版本检查与遥测跳过 Git 调用 | `main() -> None`<br>`CheckVersionRunner.run() -> None` | 进程启动入口、主窗口初始化 |
| `deploy/OneDragon-Portable.spec` | 新增 | 单目录 PyInstaller 规范：全量收集 `src/`，嵌入四类只读资源与基础配置，集成 velopack 原生二进制 | PyInstaller Analysis / EXE / COLLECT | CI 构建流水线、开发者本地构建 |
| `src/one_dragon/envs/git_service.py` | 修改 | 在 Velopack 模式或缺失 `.git` 时全面短路，杜绝抛出 `ValueError` 及多源轮询重试 | `check_repo_exists() -> bool`<br>`is_current_branch_latest() -> tuple[bool, str]`<br>`fetch_total_commit() -> int`<br>`fetch_page_commit(page_num, page_size) -> list[GitLog]`<br>`get_current_version() -> str \| None`<br>`get_head_commit_id(short=False) -> str \| None`<br>`get_current_branch() -> str \| None`<br>`fetch_latest_code(...) -> tuple[GitSyncStatus, str]` | `CheckVersionRunner`<br>`CodeInstallCard`<br>`ResourceManagementInterface`<br>`telemetry_manager.py` |
| `src/one_dragon_qt/widgets/install_card/code_install_card.py` | 修改 | 界面卡片在 Velopack 模式下展示「发行版（自动升级）」，短路分支和同步按钮 | `get_display_content() -> tuple[QIcon, str]` | `ResourceManagementInterface` |
| `src/one_dragon_qt/view/resource_management_interface.py` | 修改 | 资源管理页隐藏/禁用 Git 代码卡片与旧启动器卡片，停用提交记录轮询线程 | `get_content_widget() -> QWidget`<br>`on_interface_shown() -> None` | 资源管理导航入口 |
| `src/one_dragon_qt/services/resource_update_coordinator.py` | 修改 | 在 Velopack 模式下取消向协调器注册旧版 `launcher` 检查任务 | `__init__(ctx, parent=None)` | 启动初始化聚合更新弹窗 |
| `src/zzz_od/telemetry/telemetry_manager.py` | 修改 | 遥测采集跳过 Git HEAD 查询，Velopack 模式下填充固定标识或空串 | `_get_commit_version() -> str` | `TelemetryManager.initialize()` |
| `src/zzz_od/gui/view/home/home_interface.py` | 修改 | 首页更新流程由旧启动器检查改为基于 `updater.py` 的异步更新状态流 | `_init_update_runner() -> None`<br>`_on_update_status_changed(...)` | `HomeInterface.on_interface_shown()` |
| `tools/ci/get_version.py` | 修改 | 输出版本号转为标准 SemVer 2.0.0（剥离 `v` 前缀供 Velopack 打包），Tag 保留 `v` 前缀 | `main() -> int` | GitHub Actions `version` job |
| `.github/workflows/build-release.yml` | 修改 | 移除旧多 spec 构建与 `src` 复制步骤；接入 `deploy/OneDragon-Portable.spec` 与 `vpk pack --runtime win-x64`；调整非发布构建路径与 SignPath 签名矩阵 | Actions YAML | CI/CD 发布流程 |
| `tools/ci/prepare_release_assets.py` | 修改 | 废除旧 RuntimeLauncher/Launcher 打包逻辑；生成独立的离线模型包 `ZenlessZoneZero-OneDragon-Models.zip` 并组织发布物料 | `main() -> int` | GitHub Actions `release` job |
| `deploy/generate_module_manifest.py` | 删除 | 移除已废弃的模块清单生成工具 | — | 原旧版 RuntimeLauncher |
| `deploy/module_manifest.py` | 删除 | 移除已废弃的模块清单文件 | — | 原旧版 RuntimeLauncher |
| `deploy/hook_path_inject.py` | 删除 | 移除外置 `src/` 路径注入运行时 hook | — | 原旧版 PyInstaller 动态路径扩展 |
| `deploy/OneDragon-RuntimeLauncher.spec` | 删除 | 移除集成版启动器 spec | — | 旧构建流程 |
| `deploy/OneDragon-Launcher.spec` | 删除 | 移除源码版启动器 spec | — | 旧构建流程 |
| `deploy/OneDragon-Installer.spec` | 删除 | 移除旧安装器 spec | — | 旧构建流程 |
| `src/one_dragon/launcher/runtime_launcher.py` | 修改 | 删除 `_sync_code()` 及其引发 Git 同步的代码逻辑，保留基础抽象或平滑过渡 | `_sync_code()` 移除 | 外部启动脚本 |
| `docs/develop/one_dragon/runtime_launcher.md` | 删除 | 移除已废弃的集成启动器开发设计文档 | — | 文档维护 |

---

## 2. git_service 降级设计

### 2.1 报错根因与调用链定位

在冻结二进制（Frozen）运行模式下，分发目录不存在 `.git/` 文件夹。
当业务代码触发 Git 操作时，进入以下异常传播链：

1. **底层报错源**：
   `src/one_dragon/envs/git_service.py:608`
   ```python
   def _open_repo(self, refresh: bool = False) -> Repository:
       ...
       git_dir = discover_repository(self.repo_dir)
       if not git_dir:
           raise ValueError(f'目录 {self.repo_dir} 不是有效的 Git 仓库')
   ```
2. **多源回退与循环放大**：
   `src/one_dragon/envs/git_service.py:1208` (`_fetch_remote`)
   在进行远程同步或更新检查时，遍历 `_get_repository_candidates()` 候选列表（GitHub、Gitee、CNB 共 3 个代码源）。每个代码源均调用 `_fetch_remote_once()`（第 949 行 `repo = self._open_repo()`），捕获到 `ValueError` 后记录 warning 并附带完整异常堆栈（`exc_info=True`），导致 1 次检测产生 3 次严重日志污染。
   上层若有定时器或循环触发（如 50 秒内 72 轮检测），日志将瞬间被几百条 `ValueError` 刷屏。

### 2.2 调用链与短路方案对照表

| 序号 | 触发入口与调用链 | 当前源码位置（文件:行号） | 触发时机 | Velopack 模式下短路方案 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `GitService._open_repo` | `src/one_dragon/envs/git_service.py:608` | 任意底层 Git 操作 | 增加入口守卫：若 `is_velopack_mode()` 或 `discover_repository` 为空，直接抛出受控自定义异常或在公共 API 层截断，禁止进入 `Repository(git_dir)`。 |
| 2 | `GitService.is_current_branch_latest` | `src/one_dragon/envs/git_service.py:1730` | 状态检测、界面刷新 | 头部短路：<br>`if is_velopack_mode() or not self.check_repo_exists(): return True, ''`<br>直接声明已是最新，阻断 `_fetch_remote()` 多源循环。 |
| 3 | `GitService.fetch_total_commit` | `src/one_dragon/envs/git_service.py:1752` | 历史记录页初始化 | 头部短路：<br>`if is_velopack_mode() or not self.check_repo_exists(): return 0`<br>避免调用 `_get_commit_walker()`。 |
| 4 | `GitService.fetch_page_commit` | `src/one_dragon/envs/git_service.py:1760` | 版本日志分页查询 | 头部短路：<br>`if is_velopack_mode() or not self.check_repo_exists(): return []` |
| 5 | `GitService.get_current_version` | `src/one_dragon/envs/git_service.py:1826` | 启动版本展示、日志记录 | 头部短路：<br>`if is_velopack_mode() or not self.check_repo_exists(): return None`<br>（或返回应用打包内嵌版本 `__version__`），阻断 `fetch_page_commit(0, 1)`。 |
| 6 | `GitService.get_head_commit_id` | `src/one_dragon/envs/git_service.py:1721` | 遥测初始化、调试日志 | 头部短路：<br>`if is_velopack_mode() or not self.check_repo_exists(): return None` |
| 7 | `GitService.get_current_branch` | `src/one_dragon/envs/git_service.py:1708` | 卡片分支文本渲染 | 头部短路：<br>`if is_velopack_mode() or not self.check_repo_exists(): return None` |
| 8 | `GitService.get_latest_tag` | `src/one_dragon/envs/git_service.py:1833` | 旧启动器版本比对 | 当前第 1840 行已有 `if not self.check_repo_exists(): return '', ''`，但 `check_repo_exists()` 应前置判定 `if is_velopack_mode(): return False`，彻底避免 `discover_repository` 文件系统 I/O。 |
| 9 | `GitService.fetch_latest_code` | `src/one_dragon/envs/git_service.py:1692` | 用户点击手动代码同步 | 头部短路：<br>`if is_velopack_mode(): return GitSyncStatus.SUCCESS, '当前为自动升级版本，无需同步源码'` |
| 10 | `GitService.update_remote` | `src/one_dragon/envs/git_service.py:1791` | 代码源下拉切换时触发 | 头部短路：<br>`if is_velopack_mode() or not self.check_repo_exists(): return` |
| 11 | `GitService.reset_to_commit` | `src/one_dragon/envs/git_service.py:1803` | 版本回滚弹窗确认 | 头部短路：<br>`if is_velopack_mode() or not self.check_repo_exists(): return False, 'Velopack 模式不支持回滚'` |
| 12 | 启动版本线程 `CheckVersionRunner` | `src/zzz_od/gui/app.py:50` | 应用启动后主窗口加载 | 判断 `if is_velopack_mode(): code_version = "velopack"`，不调用 `git_service.get_current_version()`。 |
| 13 | 遥测管理器 `TelemetryManager._get_commit_version` | `src/zzz_od/telemetry/telemetry_manager.py:110` | 遥测事件上报（所有事件通用字段） | 修改为：<br>`if is_velopack_mode(): return "velopack"`<br>避免进入 `git_service.get_head_commit_id()`。 |
| 14 | 资源管理页代码卡片 `CodeInstallCard` | `src/one_dragon_qt/widgets/install_card/code_install_card.py:96, 104` | 资源管理界面显示 | 在 `get_display_content()` 中增加 `is_velopack_mode()` 分支：返回 `(FluentIcon.INFO, '已通过 Velopack 自动维护')`，禁用同步按钮；或在父容器中直接隐藏该卡片。 |
| 15 | 资源管理页初始化 `ResourceManagementInterface` | `src/one_dragon_qt/view/resource_management_interface.py:122, 616, 713` | 页面创建及展示 | 在 `is_velopack_mode()` 下，不启动 `fetch_total_runner`，隐藏 `self.code_card`、`self.launcher_opt`，隐藏「版本记录」与「代码设置」按钮。 |
| 16 | 聚合更新协调器 `ResourceUpdateCoordinator` | `src/one_dragon_qt/services/resource_update_coordinator.py:98` | 首页显示时触发检查 | `is_velopack_mode()` 下注销/跳过 `launcher` 维度的更新检查（不再调用 `update_service.is_launcher_update_available()`）。 |
| 17 | 首页旧更新检测（历史兼容） | `src/zzz_od/gui/view/home/home_interface.py:499`（原 `_check_code_runner`） | 首页展示 (`on_interface_shown`) | 说明：当前分支已在 v2.5.2 重构移除了历史上的 `_check_code_runner`，统一收拢至主窗口协调器。Velopack 更新将作为独立生命周期直接托管给 `updater.py`。 |

---

## 3. 首页更新流程与 UI 交互设计

### 3.1 现状与改造点分析

- **当前逻辑**：
  首页 `home_interface.py:499` 在 `on_interface_shown` 时调用主窗口的 `check_resource_updates()`。主窗口通过 `ResourceUpdateCoordinator` 分别对 `launcher`（旧启动器）、`project_models`（模型）和 `plugins` 进行后台线程检查。检查完成后，若存在更新且欢迎弹窗已关闭，弹出一个通用的 `ResourceUpdateDialog` 多选弹窗，用户勾选后放入进程内的 `DownloadQueueService` 串行下载。
- **Velopack 升级机制的根本区别**：
  Velopack 更新是整应用生命周期管理（基于 `UpdateManager` 与 `Update.exe`），更新包下载的是 `.nupkg` 增量或全量差分包，且更新应用需要调用 `wait_exit_then_apply_updates()`，在主进程退出后由外部进程原子替换 `current/` 目录并重启。它**不能也不应混入**通用的文件下载队列。

### 3.2 改造后状态机流转

```mermaid
stateDiagram-v2
    [*] --> IDLE: 启动就绪
    IDLE --> CHECKING: 首页展示触发 / 手动点击检查
    CHECKING --> UP_TO_DATE: check_for_updates() 返回 None
    CHECKING --> UPDATE_AVAILABLE: 发现新版本 UpdateInfo
    CHECKING --> CHECK_FAILED: 网络错误或解析失败

    UP_TO_DATE --> IDLE: 自动恢复 / 仅记录日志
    CHECK_FAILED --> IDLE: 提示错误，可手动重试

    UPDATE_AVAILABLE --> DOWNLOADING: 用户点击「立即更新」
    UPDATE_AVAILABLE --> IDLE: 用户点击「稍后提醒」

    DOWNLOADING --> DOWNLOADING: 进度回调 (0% - 100%)
    DOWNLOADING --> DOWNLOAD_FAILED: 下载中断或哈希校验失败
    DOWNLOADING --> READY_TO_RESTART: 下载完成，就绪

    DOWNLOAD_FAILED --> UPDATE_AVAILABLE: 允许重新下载
    READY_TO_RESTART --> RESTARTING: 用户点击「立即重启」
    READY_TO_RESTART --> IDLE: 用户选择「退出时自动应用」
    RESTARTING --> [*]: wait_exit_then_apply_updates 退出当前进程
```

### 3.3 组件复用方案（无需 Designer）

若暂不引入新 UI 组件，系统可 100% 复用现有 Fluent 控件完成闭环：

1. **检查与发现阶段**：
   - 使用 `one_dragon_qt` 现有的 `InfoBar.info` 弹出浮层：
     - 标题：`发现新版本 vX.Y.Z`
     - 内容：`已有更新就绪，是否立即下载？`
     - 挂载自定义按钮：`PillPushButton('下载更新')` 与 `PushButton('忽略')`。
2. **下载进度阶段**：
   - 弹出标准 `MessageBoxBase` 派生的轻量进度弹窗，内嵌 `qfluentwidgets.ProgressBar` 与进度文本标签；或复用 `NoticeCard` 区域展示微型进度条。
3. **就绪与重启阶段**：
   - 弹出 `InfoBar.success` 或模态弹窗：
     - 标题：`更新已就绪`
     - 内容：`新版本已下载完毕，重启应用即可生效。`
     - 按钮：`立即重启`（触发退出并调用 `wait_exit_then_apply_updates`）和 `下次启动时应用`。

---

### 3.4 需 Designer（单列评估）

如果产品希望将更新状态深度融合至首页（例如取代弹窗，在 Banner、启动按钮旁或公告卡片区域形成无缝的原生状态条），则需要 Designer 介入：

> [!IMPORTANT]
> **设计需求规格说明**：
> 1. **展示容器定位**：
>    - 方案建议：在首页 `bottom_bar`（`home_interface.py:388`）的公告卡片上方或启动按钮左侧，增设常驻的 `UpdateNotificationCard`（更新状态条）。
> 2. **视觉状态规范（需输出深/浅两套色系及微交互）**：
>    - **检查中**：带有 Fluent 环形微动画（Indeterminate Ring），文案「正在检查更新...」，避免遮挡首页 Banner 操作。
>    - **发现新版**：展示版本号徽章（Badge，如 `v0.1.0-beta.2`）、简要 Release 标题、以及高亮的操作按钮（`立即更新`）。
>    - **下载进度**：展示带有圆角渐变的紧凑型进度条、当前下载百分比、下载速率。需定义取消按钮的交互。
>    - **待重启**：黄色或高对比度强调色卡片，文案「更新已就绪，重启后生效」，提供主操作按钮「立即重启」。
> 3. **响应式断点**：
>    - 需提供在 1140×760（默认窗口）以及全屏拉伸状态下的宽度约束、边缘间距与阴影参数（配合 `apply_shadow` 统一视觉风格）。
>
> **Leader 决策建议**：当前阶段建议先采用「3.3 组件复用方案」，功能逻辑验收通过后，若对视觉一体化有更高追求，再派发 Designer 进行首页卡片定制。

---

## 4. CI 改造与非发布构建设计

> [!NOTE]
> **执行约束说明**：
> 本设计文档包含完整的 `.github/workflows/build-release.yml`、`tools/ci/get_version.py`、`tools/ci/prepare_release_assets.py` 改造规范，并作为源码变更写入仓库。但在当前研发阶段中，**不推远端、不配置外部凭据、不实际触发 GitHub Actions 执行**。

### 4.1 `.github/workflows/build-release.yml` 改造前后步骤对照

```
改造前 (Legacy Build)                       改造后 (Velopack Build)
────────────────────────────────────────────────────────────────────────────
1. setup-python / uv sync                    1. setup-python / uv sync
2. UPX 下载与解压                            2. (移除 UPX，Velopack 官方建议禁用 UPX)
3. 打包三个可执行文件：                       3. PyInstaller 单目录构建：
   - OneDragon-Installer.spec                   - OneDragon-Portable.spec
   - OneDragon-Launcher.spec                      产物：deploy/dist/OneDragon/
   - OneDragon-RuntimeLauncher.spec
4. Copy-Item ..\src 到 RuntimeLauncher       4. (移除源码外置拷贝，代码已全量打包)
5. Bundle wheels (Environment.zip)          5. (移除 wheels 导出与打包)
6. 准备发布物料 (prepare_release_assets.py):  6. 安装 Velopack CLI：
   - 下载嵌入式 cpython 运行时                   - dotnet tool install -g vpk
   - 多次 zip 打包生成 Full/WithRuntime 等    7. SignPath 签名阶段 1 (仅发布)：
                                                - 对 deploy/dist/OneDragon/OneDragon.exe 签名
                                             8. vpk 打包发布物料：
                                                - vpk pack --runtime win-x64 ...
                                             9. SignPath 签名阶段 2 (仅发布)：
                                                - 对 Setup.exe 与 Update.exe 签名
                                             10. 离线模型包构建：
                                                - 打包 assets/models 为 Models.zip
                                             11. 发布分支或 Artifact 收集
```

### 4.2 非发布构建路径与正式发布隔离防护

为支持开发者/人类在 fork 仓手动测试（`workflow_dispatch`）或给 PR 打 `build` 标签进行构建检验，流水线必须具备严格的非发布构建路径与防护机制：

1. **触发条件与上下文环境变量**：
   ```yaml
   env:
     # 仅当为 tag 推送，或在主仓手动触发并显式勾选 create_release 时，才置为 true
     CREATE_RELEASE: ${{ github.repository_owner == 'OneDragon-Anything' && ((github.event_name == 'workflow_dispatch' && inputs.create_release == true) || startsWith(github.ref, 'refs/tags/v')) }}
   ```
2. **非发布构建逻辑（只出 Artifact，不建 Release、不跑 SignPath）**：
   - **打包与 Pack 正常执行**：在 `windows-latest` runner 上运行 PyInstaller 与 `vpk pack --runtime win-x64`。
   - **SignPath 门禁拦截**：
     ```yaml
     sign:
       if: ${{ env.CREATE_RELEASE == 'true' }}
     ```
     非发布构建跳过所有 SignPath 步骤，不需要任何 `SIGNPATH_API_TOKEN` 或签名组织凭据。
   - **Artifact 收集与上传**：
     非发布构建时，通过 `actions/upload-artifact@v4` 将产物完整导出供下载验证：
     - `ZenlessZoneZero-OneDragon-Setup.exe`
     - `ZenlessZoneZero-OneDragon-win-Portable.zip`
     - `RELEASES`
     - `releases.win.json`
     - `*.nupkg`
   - **Release 门禁拦截**：
     ```yaml
     release:
       if: ${{ env.CREATE_RELEASE == 'true' }}
     ```
     彻底杜绝非发布构建误建 Release、打 Git Tag 或向 CNB 发起镜像同步。

### 4.3 `vpk pack` 规范执行命令

在 Windows Runner 的 PowerShell 环境下，必须严格执行以下命令：

```powershell
# 1. 确保全局安装并信任 vpk 工具
dotnet tool install -g vpk

# 2. 从 Git Tag 或 CI 脚本提取去 v 的 SemVer 2.0.0 版本号
$rawVersion = "${{ needs.version.outputs.version }}"
$semver = $rawVersion.TrimStart('v')

# 3. 执行 vpk 打包（显式指定 win-x64 运行时）
vpk pack `
  --packId "ZenlessZoneZero-OneDragon" `
  --packVersion "$semver" `
  --packDir "deploy\dist\OneDragon" `
  --mainExe "OneDragon.exe" `
  --icon "assets\ui\logo.ico" `
  --runtime win-x64 `
  --packTitle "ZenlessZoneZero-OneDragon" `
  --packAuthors "OneDragon-Anything" `
  --outputDir "deploy\dist\releases"
```

> [!WARNING]
> **关键约束**：
> 1. 必须带 `--runtime win-x64`。若省略，vpk 默认打包为 win-x86，将导致 64 位 CPython 动态库加载失败引发崩溃。
> 2. 版本号必须剔除前导 `v`（符合 SemVer 2.0.0 规范，如 `0.1.0-beta.1`）。

### 4.4 产物矩阵与 SignPath 签名范围

#### 产物输出目录 (`deploy/dist/releases/`)
- `ZenlessZoneZero-OneDragon-Setup.exe`：一键安装程序，集成安装向导与桌面快捷方式。
- `ZenlessZoneZero-OneDragon-win-Portable.zip`：便携免安装版本，解压即用。
- `RELEASES`：Velopack 升级索引清单（SHA1 哈希及大小）。
- `releases.win.json`：Velopack 跨平台通道元数据清单。
- `ZenlessZoneZero-OneDragon-0.1.0-beta.1-full.nupkg`：版本完整包（供更新器下载）。
- `ZenlessZoneZero-OneDragon-Models.zip`：独立离线模型压缩包。

#### SignPath 签名矩阵（仅在正式发布时触发）
1. **主程序可执行体**：`deploy\dist\OneDragon\OneDragon.exe`（在进入 `vpk pack` 前签名，确保打包进 Portable.zip 和 .nupkg 的本体受信任）。
2. **安装器可执行体**：`deploy\dist\releases\ZenlessZoneZero-OneDragon-Setup.exe`（打包完成后签名，避免 Windows Defender / SmartScreen 拦截）。
3. **便携更新存根**：`Update.exe`（Velopack 在 Portable 根目录中释放的执行体）。

### 4.5 离线模型包生成与上传

修改 `tools/ci/prepare_release_assets.py`：
1. 主程序安装包中**彻底排除** `assets/models`（体积约 150MB~300MB），保持主包体积在 ~308MB 以内。
2. 独立脚本下载所需模型至临时目录，执行：
   ```powershell
   Compress-Archive -Path "temp_models\*" -DestinationPath "deploy\dist\releases\ZenlessZoneZero-OneDragon-Models.zip" -Force
   ```
3. Release 发布附件中作为可选下载资产上传。离线用户解压该 zip 至 `<RootAppDir>/assets/models/` 即可直接离线运行。

---

## 5. 验证矩阵

根据人类最新决策：**验证矩阵精简为两栏，严谨划分「arm-1 上能验」与「arm-1 验不了，交人类在 Windows 上验」**。
对于第二栏，逐条附带清晰可执行的人类验证步骤与预期基准：

| 验收标准 | 栏目 1：arm-1 上能验（开发机自动化） | 栏目 2：arm-1 验不了，交人类在 Windows 上验（人类可照着执行） |
| :--- | :--- | :--- |
| **1. `vpk pack` 一条命令产出 `Setup.exe` 与 `Portable.zip`，两者都能装/解压后启动** | 1. 运行 `ruff check src/ deploy/ tools/` 校验代码语法与规范；<br>2. 运行纯逻辑单元测试解析 `OneDragon-Portable.spec`，断言入口、datas 资源路径与依赖项；<br>3. 校验 `pyproject.toml` 锁定版本。 | **人类 Windows 验证步骤**：<br>1. 在 Windows x64 上执行 PyInstaller 构建单目录；<br>2. 执行 `vpk pack --runtime win-x64 ...`；<br>3. 验证生成 `Setup.exe`、`Portable.zip`、`RELEASES`、`releases.win.json`、`full.nupkg`；<br>4. 双击运行 `Setup.exe` 完成安装并从快捷方式拉起；解压 `Portable.zip`，双击 `OneDragon.exe` 确认正常启动。 |
| **2. 解压到全新目录启动后，根层自动生成 `config/assets/custom/.log`，四类只读资源到位** | **单测 Mock 覆盖**：<br>编写 `tests/test_bundle_seed.py`：<br>1. Mock `sys.frozen=True`, `sys.executable="/mock/app/current/OneDragon.exe"`, `sys._MEIPASS="/mock/bundle"`;<br>2. 模拟全新空目录执行 `ensure_work_dir_ready()`；<br>3. 断言四类只读目录文件复制与 `.bundle_seed_version` 写入。 | **人类 Windows 验证步骤**：<br>1. 将 `Portable.zip` 解压至一个全新的空目录（如 `C:\TestOneDragon`）；<br>2. 启动根层 `OneDragon.exe`，等待 30–60 秒；<br>3. **断言目录**：根层自动生成 `config/`、`assets/`、`custom/`、`.log/`；<br>4. **断言文件数基准（实测值）**：检查 `assets/` 下四类只读资源文件数量：<br>   - `template`: 1820 个文件<br>   - `ui`: 10 个文件<br>   - `text`: 8 个文件<br>   - `game_data`: 178 个文件<br>5. 验证完成后结束/终止进程。 |
| **3. 改根层 `config/project.yml` 后升级，改动保留、`current/` 被替换** | **单测 Mock 覆盖**：<br>1. 预置含用户自定义字段（如 `test_key: custom_val`）的 `config/project.yml`；<br>2. 模拟新版本环境执行 `ensure_work_dir_ready()`；<br>3. 断言用户自定义配置未被覆盖，只读资源得到更新。 | **人类 Windows 验证步骤**：<br>1. 在第 2 项生成的根层中，手动修改 `config/project.yml`（如修改代理配置或添加自定义标记行）；<br>2. 在命令行执行升级应用：<br>   `.\Update.exe apply -p <新版本-full.nupkg> --norestart`<br>3. **断言版本**：查看 `current/sq.version`，确认已变为新版本号；<br>4. **断言配置**：打开 `config/project.yml`，断言此前修改的自定义内容依然完好保留。 |
| **4. 完整日志里不再出现「不是有效的 Git 仓库」** | **单测 Mock 覆盖**：<br>编写 `tests/test_git_service_fallback.py`：<br>1. Mock `is_velopack_mode() = True` 且工作目录无 `.git`；<br>2. 遍历调用 `is_current_branch_latest`、`fetch_total_commit`、`fetch_page_commit`、`get_current_version`、`get_head_commit_id`、`telemetry.initialize()`；<br>3. 断言日志中零次出现 `ValueError: 目录 xxx 不是有效的 Git 仓库` 且无多源重试 warning。 | **人类 Windows 验证步骤**：<br>1. 升级完成后，再次启动根层 `OneDragon.exe`；<br>2. 确认应用正常拉起并运行约 1 分钟；<br>3. 打开根层 `.log/` 目录下最新生成的日志文件；<br>4. 全文检索关键词 `不是有效的 Git 仓库`，**断言命中数为 0**。 |
| **5. 源码模式 `python main.py` 行为与改造前一致** | **直接运行验证**：<br>1. 在 arm-1 上执行 `python3 main.py`（无 GUI 下测试入口导入与基础依赖）；<br>2. 断言 `is_velopack_mode()` 为 `False`；<br>3. 断言 `get_work_dir()` 正确解析为仓库根目录；<br>4. 执行既有测试套件 `pytest tests/` 全部通过。 | **人类 Windows 验证步骤**：<br>1. 在 Windows 机器克隆或拉取本分支源码；<br>2. 在虚拟环境中执行 `python main.py`；<br>3. 验证 GUI 正常显示，功能与改造前完全一致。 |
| **6. 跑完清理掉启动的进程，不留后台** | **代码走查验证**：<br>验证 `updater.py` 退出调用 `wait_exit_then_apply_updates` 前的主进程清理逻辑与 `app.py::closeEvent`，确保无未挂起的后台守护线程。 | **人类 Windows 验证步骤**：<br>1. 启动 `OneDragon.exe`，执行任务或测试后正常关闭主窗口；<br>2. 打开 Windows 任务管理器，在「详细信息」中检索 `OneDragon.exe`、`Update.exe` 或 Python 宿主进程；<br>3. **断言无任何残留孤儿进程**。<br>*注：针对「点击更新按钮、查看窗口渲染」等人工交互细节，直接标为「未验证，写入交付说明供人类验收确认」。* |

---

## 6. 风险评估与应对策略

### 6.1 签名与 Windows SmartScreen 拦截风险
- **风险**：
  若 SignPath 签名遗漏了 `Setup.exe`、`Update.exe` 或 `OneDragon.exe` 中的任何一个，用户在 Windows 10/11 安装或升级时将遭遇 SmartScreen 强力拦截甚至被杀毒软件误杀。
- **应对策略**：
  在 CI 流程中严格拆分两阶段签名：PyInstaller 构建后先签 `OneDragon.exe`，`vpk pack` 输出后对 `Setup.exe` 与 `Update.exe` 再次签名；并在 Release 之前增加前置校验步骤，使用 PowerShell `Get-AuthenticodeSignature` 检验三大可执行文件签名状态。

### 6.2 发布流水线与国内 CDN 同步风险
- **风险**：
  国内用户主要依赖 CNB 镜像源。Velopack 更新严重依赖 `releases.win.json`、`RELEASES` 以及 `.nupkg` 文件的完整性。如果 CNB Release 同步只同步了 exe 而漏掉了元数据文件，国内用户将全部升级失败。
- **应对策略**：
  更新 `.github/workflows/build-release.yml` 中的 CNB 同步触发逻辑，确保全量物料（包含 `releases.win.json`, `RELEASES`, 所有 `.nupkg`, `Setup.exe`, `Portable.zip`, `Models.zip`）作为一个发布事务完整推送。

### 6.3 用户数据目录隔离与迁移破坏风险
- **风险**：
  Velopack 升级机制会在升级时彻底删除并重建 `current/` 文件夹。如果用户或开发人员不小心将数据存储在 `current/` 内部，升级后将导致用户数据永久丢失。
- **应对策略**：
  1. `get_work_dir()` 必须具备高可靠防护，确保在冻结状态下牢牢锚定在 `<RootAppDir>`。
  2. 单元测试针对 `get_velopack_root()` 进行详尽的边界与异常路径覆盖。

### 6.4 旧版本（集成版/源码版）用户的过渡风险
- **风险**：
  老用户目前处于「源码启动器 / 旧 RuntimeLauncher」体系，其目录结构与 Velopack 规范不兼容，无法通过应用内静默升级到 Velopack 版本。
- **应对策略**：
  1. **首发全量升级公告**：发布版本时在 Release Notes、QQ 群及公告卡片明确注明分发体系重构。
  2. **无缝配置迁移指南**：老用户只需下载全新的 `Setup.exe` 或 `Portable.zip`，将旧版本的 `config/` 目录直接拷贝至新程序根目录下即可完全继承所有账号与设置。
