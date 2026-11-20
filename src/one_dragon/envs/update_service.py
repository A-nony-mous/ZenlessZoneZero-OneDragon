from pathlib import Path

from one_dragon.base.web.common_downloader import CommonDownloaderParam
from one_dragon.envs.env_config import DEFAULT_ENV_PATH, EnvConfig
from one_dragon.envs.git_service import GitService
from one_dragon.envs.project_config import ProjectConfig
from one_dragon.utils import os_utils


class UpdateService:
    """处理资源更新相关的版本检查、下载参数与安装服务。"""

    def __init__(
        self,
        project_config: ProjectConfig,
        env_config: EnvConfig,
        git_service: GitService,
    ) -> None:
        self.project_config: ProjectConfig = project_config
        self.env_config: EnvConfig = env_config
        self.git_service: GitService = git_service

    @staticmethod
    def is_launcher_installed(launcher_type: str = 'launcher') -> bool:
        """检查启动器是否已安装。"""
        launcher_path = Path(os_utils.get_work_dir()) / 'OneDragon-Launcher.exe'
        return launcher_path.exists()

    def get_launcher_download_param(
        self,
        launcher_type: str = 'launcher',
        target_version: str = 'latest',
        staging: bool = False,
    ) -> CommonDownloaderParam:
        """构造启动器安装包的下载参数。"""
        zip_file_name = f'{self.project_config.project_name}-Launcher.zip'
        target_dir = Path(DEFAULT_ENV_PATH)
        exe_path = str(target_dir / 'OneDragon-Launcher.exe')
        tag = '' if target_version == 'latest' else target_version
        download_urls = self.env_config.repo_config.get_resource_asset_urls(
            'main',
            tag,
            zip_file_name,
        )
        if not download_urls:
            base = 'latest/download' if tag == '' else f'download/{tag}'
            download_urls = {
                'github': (
                    f'{self.project_config.github_homepage}/releases/{base}/{zip_file_name}'
                ),
            }
        return CommonDownloaderParam(
            save_file_path=str(target_dir),
            save_file_name=zip_file_name,
            download_urls=download_urls,
            check_existed_list=[exe_path],
            unzip_dir_path=str(target_dir),
        )
