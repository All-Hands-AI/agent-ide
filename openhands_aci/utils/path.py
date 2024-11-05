from pathlib import Path


class PathUtils:
    def __init__(self, root: str) -> None:
        self.root = root

    def get_absolute_path_str(self, rel_path: str) -> str:
        return str(Path(self.root).joinpath(rel_path).resolve())

    def get_relative_path_str(self, abs_path: str) -> str:
        return str(Path(abs_path).relative_to(self.root))

    def get_depth_from_root(self, abs_path: str) -> int:
        return len(Path(abs_path).relative_to(self.root).parts)


def has_image_extension(path: str) -> bool:
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
    return Path(path).suffix in IMAGE_EXTENSIONS


def get_depth_of_rel_path(rel_path: str) -> int:
    return len(Path(rel_path).parts)
