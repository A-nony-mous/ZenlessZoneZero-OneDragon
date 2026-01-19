import os
import shutil
import sys

def ensure_runtime_data():
    """
    检查并初始化/同步运行所需的配置和资源文件。
    在 Briefcase 打包环境中，这些文件被打包在应用内部。

    策略：
    1. Config: 仅在缺失时初始化，保留用户修改。
    2. Assets: 每次启动时尝试从 Bundle 同步到 CWD，以支持版本升级带来的资源更新。
    """
    cwd = os.getcwd()
    dst_config_dir = os.path.join(cwd, 'config')
    dst_assets_dir = os.path.join(cwd, 'assets')

    # 计算打包环境下的资源源路径
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    pkg_root = current_file_dir
    app_root = os.path.dirname(pkg_root)

    src_config_dir = os.path.join(app_root, 'config')
    src_assets_dir = os.path.join(app_root, 'assets')

    # 1. 初始化 Config (仅当缺失 config/project.yml 时)
    if not os.path.exists(os.path.join(dst_config_dir, 'project.yml')):
        try:
            if os.path.exists(src_config_dir):
                print(f"Initializing config from {src_config_dir} to {dst_config_dir}")
                shutil.copytree(src_config_dir, dst_config_dir, dirs_exist_ok=True)

                # 清理拷贝过去可能存在的 __init__.py
                init_file = os.path.join(dst_config_dir, '__init__.py')
                if os.path.exists(init_file):
                    os.remove(init_file)
            else:
                pass # 开发环境可能无 bundle config，正常
        except Exception as e:
            print(f"Failed to copy config: {e}")

    # 2. 同步 Assets (总是更新)
    try:
        if os.path.exists(src_assets_dir):
            # 如果目标存在，shutil.copytree 需要 dirs_exist_ok=True 来合并/覆盖
            if os.path.exists(dst_assets_dir):
                print(f"Syncing assets (update) fromBundle to {dst_assets_dir}")
            else:
                print(f"Initializing assets from Bundle to {dst_assets_dir}")

            shutil.copytree(src_assets_dir, dst_assets_dir, dirs_exist_ok=True)

            # 清理 __init__.py
            init_file = os.path.join(dst_assets_dir, '__init__.py')
            if os.path.exists(init_file):
                os.remove(init_file)
        else:
            pass
    except Exception as e:
        print(f"Failed to sync assets: {e}")
