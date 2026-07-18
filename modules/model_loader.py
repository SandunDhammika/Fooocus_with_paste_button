import os
import sys
from urllib.parse import urlparse
from typing import Optional


COLAB_DRIVE_MOUNT_POINT = '/content/drive'
COLAB_DRIVE_MODELS_ROOT = os.environ.get(
    'FOOOCUS_COLAB_MODELS_DIR',
    '/content/drive/MyDrive/Fooocus/models'
)
_drive_permission_granted: Optional[bool] = None
_drive_file_index: Optional[dict[str, str]] = None


def _colab_log(message: str) -> None:
    print(f'[Colab] {message}')


def _is_colab_environment() -> bool:
    try:
        import google.colab  # noqa: F401
        return True
    except Exception:
        return False


def _is_colab_notebook_runtime() -> bool:
    if not _is_colab_environment():
        return False

    try:
        from IPython import get_ipython
        shell = get_ipython()
        return shell is not None and hasattr(shell, 'kernel')
    except Exception:
        return False


def _request_drive_permission() -> bool:
    global _drive_permission_granted

    if _drive_permission_granted is not None:
        _colab_log(f'Drive permission already cached: {_drive_permission_granted}')
        return _drive_permission_granted

    preset = os.environ.get('FOOOCUS_COLAB_DRIVE_PERMISSION', '').strip().lower()
    if preset in {'1', 'true', 'yes', 'y', 'allow', 'granted'}:
        _colab_log('Drive permission granted via FOOOCUS_COLAB_DRIVE_PERMISSION.')
        _drive_permission_granted = True
        return True
    if preset in {'0', 'false', 'no', 'n', 'deny', 'denied'}:
        _colab_log('Drive permission denied via FOOOCUS_COLAB_DRIVE_PERMISSION.')
        _drive_permission_granted = False
        return False

    if not sys.stdin or not sys.stdin.isatty():
        _colab_log('Non-interactive runtime detected; skipping Drive permission prompt.')
        _colab_log('Set FOOOCUS_COLAB_DRIVE_PERMISSION=true to enable Drive lookup.')
        _drive_permission_granted = False
        return False

    _colab_log('Permission required to mount and access Google Drive models folder.')
    _colab_log(f'Target folder: {COLAB_DRIVE_MODELS_ROOT}')
    answer = input('Allow Google Drive access for model lookup? [y/N]: ').strip().lower()
    _drive_permission_granted = answer in {'y', 'yes'}
    _colab_log(f'Drive permission response: {_drive_permission_granted}')
    return _drive_permission_granted


def _ensure_colab_drive_mounted() -> bool:
    if not _is_colab_environment():
        _colab_log('Not running in a Colab environment; skipping Drive lookup.')
        return False
    if not _request_drive_permission():
        _colab_log('Drive permission not granted; skipping Drive lookup.')
        return False

    if os.path.isdir(COLAB_DRIVE_MODELS_ROOT):
        _colab_log(f'Drive models folder already available: {COLAB_DRIVE_MODELS_ROOT}')
        return True

    auto_mount = os.environ.get('FOOOCUS_COLAB_AUTO_MOUNT', '').strip().lower() in {
        '1', 'true', 'yes', 'y', 'on'
    }
    if not auto_mount:
        _colab_log('Drive models folder not found and auto-mount is disabled.')
        _colab_log('Mount Drive in a notebook cell first, or set FOOOCUS_COLAB_AUTO_MOUNT=true.')
        return False

    if not _is_colab_notebook_runtime():
        _colab_log('Google Drive is not mounted and this runtime cannot mount it (no notebook kernel).')
        _colab_log('Mount Drive in a notebook cell first, then run Fooocus again.')
        return False

    try:
        from google.colab import drive
    except Exception:
        _colab_log('google.colab.drive is unavailable in this runtime.')
        return False

    try:
        if not os.path.isdir(COLAB_DRIVE_MOUNT_POINT) or not os.path.isdir(COLAB_DRIVE_MODELS_ROOT):
            _colab_log('Mounting Google Drive...')
            drive.mount(COLAB_DRIVE_MOUNT_POINT, force_remount=False)
    except Exception as e:
        _colab_log(f'Google Drive mount failed: {e}')
        return False

    if os.path.isdir(COLAB_DRIVE_MODELS_ROOT):
        _colab_log(f'Drive models folder ready: {COLAB_DRIVE_MODELS_ROOT}')
    else:
        _colab_log(f'Drive mounted, but models folder still missing: {COLAB_DRIVE_MODELS_ROOT}')
    return os.path.isdir(COLAB_DRIVE_MODELS_ROOT)


def _get_colab_mirrored_model_path(model_dir: str, file_name: str) -> str:
    normalized_model_dir = os.path.abspath(model_dir).replace('\\', '/')
    marker = '/models/'
    if marker in normalized_model_dir:
        relative_to_models = normalized_model_dir.split(marker, 1)[1]
        return os.path.join(COLAB_DRIVE_MODELS_ROOT, relative_to_models, file_name)
    return os.path.join(COLAB_DRIVE_MODELS_ROOT, file_name)


def _build_drive_file_index() -> dict[str, str]:
    global _drive_file_index
    if _drive_file_index is not None:
        _colab_log(f'Using cached Drive file index with {len(_drive_file_index)} entries.')
        return _drive_file_index

    index: dict[str, str] = {}
    if os.path.isdir(COLAB_DRIVE_MODELS_ROOT):
        _colab_log(f'Building Drive file index from: {COLAB_DRIVE_MODELS_ROOT}')
        for root, _, files in os.walk(COLAB_DRIVE_MODELS_ROOT):
            for name in files:
                index.setdefault(name, os.path.join(root, name))
        _colab_log(f'Indexed {len(index)} Drive files.')
    else:
        _colab_log(f'Drive models root is missing; index will be empty: {COLAB_DRIVE_MODELS_ROOT}')
    _drive_file_index = index
    return _drive_file_index


def _find_model_in_colab_drive(model_dir: str, file_name: str) -> Optional[str]:
    _colab_log(f'Searching for model in Drive: {file_name}')
    if not _ensure_colab_drive_mounted():
        _colab_log('Drive search skipped because Drive is not ready.')
        return None

    mirrored_candidate = _get_colab_mirrored_model_path(model_dir, file_name)
    _colab_log(f'Checking mirrored path: {mirrored_candidate}')
    if os.path.isfile(mirrored_candidate):
        _colab_log(f'Found model at mirrored path: {mirrored_candidate}')
        return os.path.abspath(mirrored_candidate)

    indexed = _build_drive_file_index().get(file_name)
    if indexed and os.path.isfile(indexed):
        _colab_log(f'Found model in indexed Drive path: {indexed}')
        return os.path.abspath(indexed)

    _colab_log(f'Model not found in Drive: {file_name}')
    return None


def load_file_from_url(
        url: str,
        *,
        model_dir: str,
        progress: bool = True,
        file_name: Optional[str] = None,
) -> str:
    """Download a file from `url` into `model_dir`, using the file present if possible.

    Returns the path to the downloaded file.
    """
    domain = os.environ.get("HF_MIRROR", "https://huggingface.co").rstrip('/')
    url = str.replace(url, "https://huggingface.co", domain, 1)
    os.makedirs(model_dir, exist_ok=True)
    if not file_name:
        parts = urlparse(url)
        file_name = os.path.basename(parts.path)
    cached_file = os.path.abspath(os.path.join(model_dir, file_name))

    if os.path.exists(cached_file):
        _colab_log(f'Using existing local cache: {cached_file}')
        return cached_file

    drive_file = _find_model_in_colab_drive(model_dir, file_name)
    if drive_file:
        try:
            os.makedirs(os.path.dirname(cached_file), exist_ok=True)
            os.symlink(drive_file, cached_file)
            _colab_log(f'Using model from Google Drive via symlink: {drive_file}')
            return cached_file
        except Exception:
            _colab_log(f'Using model directly from Google Drive: {drive_file}')
            return drive_file

    if not os.path.exists(cached_file):
        _colab_log(f'Downloading from URL: {url}')
        _colab_log(f'Download target: {cached_file}')
        from torch.hub import download_url_to_file
        download_url_to_file(url, cached_file, progress=progress)
        _colab_log(f'Download complete: {cached_file}')
    return cached_file
