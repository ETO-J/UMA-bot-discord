"""统一路径解析工具"""
from pathlib import Path
from ..config import PROJECT_ROOT


def get_project_root() -> Path:
    """获取项目根目录"""
    return PROJECT_ROOT


def ensure_dir(path: Path) -> Path:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)
    return path
