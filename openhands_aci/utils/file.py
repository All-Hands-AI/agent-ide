from pathlib import Path

from git import Repo

from .path import get_depth_of_rel_path, has_image_extension


class GitRepoUtils:
    def __init__(self, abs_repo_path: str) -> None:
        if not Path(abs_repo_path).is_absolute():
            raise ValueError('The path must be absolute')

        self.repo_path = Path(abs_repo_path)
        try:
            self.repo = Repo(self.repo_path)
        except Exception:
            print(
                f'Could not find git repository at {abs_repo_path}, trying to detect at child directories'
            )
            for child in self.repo_path.iterdir():
                if child.is_dir():
                    try:
                        self.repo = Repo(child)
                        self.repo_path = child
                        print(f'Found git repository at {child}')
                        break
                    except Exception:
                        print(f'Could not find git repository at child {child}')
            if not self.repo:
                raise Exception(
                    'Could not find any git repository in the root directory or its children'
                )

    def get_all_absolute_tracked_files(self, depth: int | None = None) -> list[str]:
        return [
            str(self.repo_path / item.path)
            for item in self.repo.tree().traverse()
            if item.type == 'blob'
            and (not depth or get_depth_of_rel_path(item.path) <= depth)
        ]

    def get_all_relative_tracked_files(self, depth: int | None = None) -> list[str]:
        return [
            item.path
            for item in self.repo.tree().traverse()
            if item.type == 'blob'
            and (not depth or get_depth_of_rel_path(item.path) <= depth)
        ]

    def get_all_absolute_staged_files(self) -> list[str]:
        return [
            str(self.repo_path / item.a_path) for item in self.repo.index.diff('HEAD')
        ]

    def get_absolute_tracked_files_in_directory(
        self, rel_dir_path: str, depth: int | None = None
    ) -> list[str]:
        rel_dir_path = rel_dir_path.rstrip('/')
        return [
            str(self.repo_path / item.path)
            for item in self.repo.tree().traverse()
            if item.path.startswith(rel_dir_path + '/')
            and item.type == 'blob'
            and (not depth or get_depth_of_rel_path(item.path) <= depth)
        ]

    def get_tracked_files_tree(
        self, rel_dir_path: str = '', depth: int | None = None
    ) -> str:
        def get_dir_at_depth(file_path: Path, max_depth: int) -> Path | None:
            """Get the directory at the specified depth if the file is deeper."""
            parts = file_path.parts
            if len(parts) > max_depth:  # Depth starts from 1
                return Path(*parts[:max_depth])
            return None

        def build_tree(files: list[Path]) -> dict:
            """Build a tree structure from list of paths."""
            tree: dict = {}

            # If depth is specified, collect directories at depth limit
            if depth is not None:
                deep_dirs = set()
                for file_path in files:
                    dir_at_depth = get_dir_at_depth(file_path, depth)
                    if dir_at_depth:
                        deep_dirs.add(dir_at_depth)

                # Add truncated paths for deep files
                processed_files = []
                for file_path in files:
                    if len(file_path.parts) > depth:
                        if Path(*file_path.parts[:depth]) not in deep_dirs:
                            deep_dirs.add(Path(*file_path.parts[:depth]))
                    else:
                        processed_files.append(file_path)

                # Combine regular files with directories at depth limit
                all_paths = list(processed_files) + list(deep_dirs)
            else:
                all_paths = list(files)

            # Build the tree
            for path in sorted(all_paths):
                current = tree
                for part in path.parts:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

            return tree

        def build_tree_string(
            tree: dict, prefix: str = '', current_depth: int = 1
        ) -> str:
            """Build the tree structure as a string recursively."""
            if depth is not None and current_depth > depth:
                return ''

            result = []
            items = sorted(tree.items())
            for i, (name, subtree) in enumerate(items):
                is_last = i == len(items) - 1
                result.append(f"{prefix}{'└── ' if is_last else '├── '}{name}\n")

                if subtree and (depth is None or current_depth < depth):
                    new_prefix = prefix + ('    ' if is_last else '│   ')
                    result.append(
                        build_tree_string(subtree, new_prefix, current_depth + 1)
                    )

            return ''.join(result)

        # Get tracked files
        tracked_files = set()
        for item in self.repo.tree().traverse():
            if item.type == 'blob':
                if rel_dir_path:
                    if item.path.startswith(rel_dir_path + '/'):
                        file_path = Path(item.path)
                        tracked_files.add(file_path)
                else:
                    file_path = Path(item.path)
                    tracked_files.add(file_path)

        # Build and return the tree string
        tree = build_tree(list(tracked_files))
        return build_tree_string(tree)


def get_modified_time(abs_path: str) -> int:
    if not Path(abs_path).exists():
        return -1

    return int(Path(abs_path).stat().st_mtime)


def read_text(abs_path: str) -> str:
    if has_image_extension(abs_path):
        return ''  # Not support image files yet!

    with open(abs_path, 'r') as f:
        return f.read()
