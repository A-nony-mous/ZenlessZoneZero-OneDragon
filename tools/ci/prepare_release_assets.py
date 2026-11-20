import argparse
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


class _DownloadRedirectHandler(urllib.request.HTTPRedirectHandler):
    """仅同源重定向保留凭据，拒绝携带凭据的 HTTPS 请求降级。"""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        source = urlsplit(req.full_url)
        target = urlsplit(newurl)
        if (
            req.has_header('Authorization')
            and source.scheme == 'https'
            and target.scheme == 'http'
        ):
            raise urllib.error.HTTPError(
                req.full_url, code, '拒绝携带凭据的 HTTPS 请求重定向到 HTTP', headers, fp
            )
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        source_origin = (
            source.scheme,
            source.hostname,
            source.port
            if source.port is not None
            else (443 if source.scheme == 'https' else 80),
        )
        target_origin = (
            target.scheme,
            target.hostname,
            target.port
            if target.port is not None
            else (443 if target.scheme == 'https' else 80),
        )
        if redirected is not None and source_origin != target_origin:
            redirected.remove_header('Authorization')
        return redirected


def _log(msg: str) -> None:
    print(msg, flush=True)


def _download(
    url: str,
    dest: Path,
    *,
    token: str | None = None,
    retries: int = 3,
    timeout: int = 60,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        'User-Agent': 'ZenlessZoneZero-OneDragon CI',
        'Accept': 'application/octet-stream',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            opener = urllib.request.build_opener(_DownloadRedirectHandler())
            with opener.open(req, timeout=timeout) as resp, dest.open('wb') as f:
                shutil.copyfileobj(resp, f)
            return
        except Exception as e:
            _log(f'[attempt {attempt}/{retries}] Download failed: {url} — {e}')
            if attempt < retries:
                time.sleep(2 * attempt)
            else:
                raise


def _fetch_json(
    url: str, *, token: str | None = None, retries: int = 3, timeout: int = 60
) -> object:
    headers = {
        'User-Agent': 'ZenlessZoneZero-OneDragon CI',
        'Accept': 'application/vnd.github+json',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            _log(f'[attempt {attempt}/{retries}] JSON fetch failed: {url} — {e}')
            if attempt < retries:
                time.sleep(2 * attempt)
            else:
                raise


def _get_latest_model_asset(
    repo: str, pattern: str, *, token: str | None = None
) -> dict | None:
    api_url = f'https://api.github.com/repos/{repo}/releases'
    data = _fetch_json(api_url, token=token)
    if not isinstance(data, list):
        return None

    rx = re.compile(pattern)
    best: dict | None = None
    max_number = -1

    for release in data:
        if not isinstance(release, dict):
            continue
        assets = release.get('assets')
        if not isinstance(assets, list):
            continue

        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = asset.get('name')
            if not isinstance(name, str):
                continue
            if not rx.search(name):
                continue

            url = asset.get('browser_download_url')
            if not isinstance(url, str) or not url:
                continue

            m = re.search(r'(\d{8})\.zip$', name)
            if m:
                number = int(m.group(1))
                if number > max_number:
                    max_number = number
                    best = {
                        'url': url,
                        'name': name,
                        'version_number': number,
                    }
            elif best is None:
                best = {
                    'url': url,
                    'name': name,
                    'version_number': 0,
                }

    return best


def _extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_dir)


def _write_dir_contents(
    zf: zipfile.ZipFile,
    root_dir: Path,
    *,
    root_prefix: str,
    exclude_prefixes: set[str] | None = None,
) -> None:
    """把目录内容写入已打开的 zip，带统一前缀。"""
    prefix = root_prefix.strip('/\\')

    for path in root_dir.rglob('*'):
        if not path.is_file():
            continue

        relative_path = path.relative_to(root_dir).as_posix()
        if exclude_prefixes and any(
            relative_path.startswith(item) for item in exclude_prefixes
        ):
            continue

        arcname = f'{prefix}/{relative_path}' if prefix else relative_path
        zf.write(path, arcname)


# ---- 模型资源配置 ----

_MODEL_CONFIGS: list[dict[str, str]] = [
    {
        'label': 'ppocrv6',
        'repo': 'OneDragon-Anything/OneDragon-Env',
        'pattern': r'ppocrv6\.zip$',
        'dest_folder': 'onnx_ocr',
        'fallback_url': 'https://github.com/OneDragon-Anything/OneDragon-Env/releases/download/ppocrv6/ppocrv6.zip',
        'fallback_name': 'ppocrv6',
    },
    {
        'label': 'flash',
        'repo': 'OneDragon-Anything/OneDragon-YOLO',
        'pattern': r'flash.*\.zip$',
        'dest_folder': 'flash_classifier',
        'fallback_url': 'https://github.com/OneDragon-Anything/OneDragon-YOLO/releases/download/zzz_model/yolov8n-640-flash-0127.zip',
        'fallback_name': 'yolov8n-640-flash-0127',
    },
    {
        'label': 'hollow',
        'repo': 'OneDragon-Anything/OneDragon-YOLO',
        'pattern': r'hollow.*\.zip$',
        'dest_folder': 'hollow_zero_event',
        'fallback_url': 'https://github.com/OneDragon-Anything/OneDragon-YOLO/releases/download/zzz_model/yolov8s-736-hollow-zero-event-0126.zip',
        'fallback_name': 'yolov8s-736-hollow-zero-event-0126',
    },
    {
        'label': 'lost_void_det',
        'repo': 'OneDragon-Anything/OneDragon-YOLO',
        'pattern': r'lost.*\.zip$',
        'dest_folder': 'lost_void_det',
        'fallback_url': 'https://github.com/OneDragon-Anything/OneDragon-YOLO/releases/download/zzz_model/yolov8n-736-lost-void-det-20250612.zip',
        'fallback_name': 'yolov8n-736-lost-void-det-20250612',
    },
]


def _download_models(model_base: Path, temp_dir: Path, *, token: str | None) -> None:
    """根据 _MODEL_CONFIGS 下载并解压所有模型到 assets/models/。"""
    for cfg in _MODEL_CONFIGS:
        dest = model_base / cfg['dest_folder']
        dest.mkdir(parents=True, exist_ok=True)

        _log(f"Resolve {cfg['label']} model")
        asset = _get_latest_model_asset(cfg['repo'], cfg['pattern'], token=token)

        tmp_zip = temp_dir / f"{cfg['label']}.zip"
        if asset:
            folder_name = asset['name'].removesuffix('.zip')
            url = asset['url']
        else:
            folder_name = cfg['fallback_name']
            url = cfg['fallback_url']

        _log(f'Download: {url}')
        _download(url, tmp_zip, token=token)
        target = dest / folder_name
        target.mkdir(parents=True, exist_ok=True)
        _extract_zip(tmp_zip, target)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Prepare release assets and offline models package.'
    )
    parser.add_argument('--repo-root', default='.', help='Repository root (default: .)')
    parser.add_argument(
        '--release-version', default='', help='Release version (optional)'
    )
    parser.add_argument(
        '--output-dir',
        default='deploy/dist/releases',
        help='Output directory for models zip (default: deploy/dist/releases)',
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    token = os.environ.get('GITHUB_TOKEN', '')

    output_dir = (repo_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = repo_root / 'temp_models'
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    model_dir = repo_root / 'temp_assets_models'
    if model_dir.exists():
        shutil.rmtree(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    _log('Downloading models...')
    _download_models(model_dir, temp_dir, token=token or None)
    shutil.rmtree(temp_dir, ignore_errors=True)

    models_zip = output_dir / 'ZenlessZoneZero-OneDragon-Models.zip'
    _log(f'Creating offline models zip: {models_zip}')
    if models_zip.exists():
        models_zip.unlink()

    with zipfile.ZipFile(
        models_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as zf:
        _write_dir_contents(zf, model_dir, root_prefix='assets/models')

    shutil.rmtree(model_dir, ignore_errors=True)
    _log('Offline models zip prepared successfully.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
