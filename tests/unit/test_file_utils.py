from pathlib import Path

import pytest
from git import Repo

from openhands_aci.utils.file import GitRepoUtils, read_text


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository with some test files."""
    repo_dir = tmp_path / 'test_repo'
    repo_dir.mkdir()

    # Initialize git repo
    repo = Repo.init(repo_dir)

    # Create some test files and directories
    (repo_dir / 'file1.txt').write_text('content1')
    (repo_dir / 'file2.txt').write_text('content2')

    # Create a subdirectory with files
    test_dir = repo_dir / 'test_dir'
    test_dir.mkdir()
    (test_dir / 'file3.txt').write_text('content3')
    (test_dir / 'file4.txt').write_text('content4')

    # Stage and commit initial files
    repo.index.add(
        ['file1.txt', 'file2.txt', 'test_dir/file3.txt', 'test_dir/file4.txt']
    )
    repo.index.commit('Initial commit')

    # Create an unstaged file
    (repo_dir / 'unstaged.txt').write_text('unstaged')

    # Create a staged but not committed file
    (repo_dir / 'staged.txt').write_text('staged')
    repo.index.add(['staged.txt'])

    return repo_dir


@pytest.fixture
def git_utils(temp_git_repo):
    """Create a GitRepoUtils instance with the temporary repository."""
    return GitRepoUtils(str(temp_git_repo))


def test_init_valid_repo(temp_git_repo):
    """Test initialization with a valid repository."""
    utils = GitRepoUtils(str(temp_git_repo))
    assert utils.repo_path == Path(temp_git_repo)
    assert utils.repo is not None


def test_get_all_abs_tracked_files(git_utils):
    """Test getting all tracked files."""
    tracked_files = git_utils.get_all_absolute_tracked_files()

    # Check if all expected files are present
    expected_files = {
        'file1.txt',
        'file2.txt',
        'test_dir/file3.txt',
        'test_dir/file4.txt',
    }
    # Convert to absolute paths
    expected_files = {str(git_utils.repo_path / file) for file in expected_files}
    assert set(tracked_files) == expected_files

    # Verify that unstaged and untracked files are not included
    assert str(git_utils.repo_path / 'unstaged.txt') not in tracked_files


def test_get_all_rel_tracked_files(git_utils):
    """Test getting all relative tracked files."""
    rel_tracked_files = git_utils.get_all_relative_tracked_files()

    # Check if all expected files are present
    expected_files = {
        'file1.txt',
        'file2.txt',
        'test_dir/file3.txt',
        'test_dir/file4.txt',
    }
    assert set(rel_tracked_files) == expected_files

    # Verify that unstaged and untracked files are not included
    assert str(git_utils.repo_path / 'unstaged.txt') not in rel_tracked_files


def test_get_all_abs_tracked_files_with_depth(git_utils):
    """Test getting all tracked files with a depth limit of 1."""
    tracked_files = git_utils.get_all_absolute_tracked_files(depth=1)

    # Only files in the root directory should be returned
    expected_files = {
        'file1.txt',
        'file2.txt',
    }
    # Convert to absolute paths
    expected_files = {str(git_utils.repo_path / file) for file in expected_files}
    assert set(tracked_files) == expected_files

    # Ensure that files in the 'test_dir' are not included
    assert str(git_utils.repo_path / 'test_dir/file3.txt') not in tracked_files
    assert str(git_utils.repo_path / 'test_dir/file4.txt') not in tracked_files


def test_get_all_abs_staged_files(git_utils):
    """Test getting all staged files."""
    staged_files = git_utils.get_all_absolute_staged_files()

    # Only staged.txt should be in the staged files list
    assert str(git_utils.repo_path / 'staged.txt') in staged_files
    assert str(git_utils.repo_path / 'file1.txt') not in staged_files
    assert str(git_utils.repo_path / 'unstaged.txt') not in staged_files


def test_get_abs_tracked_files_in_directory(git_utils):
    """Test getting tracked files in a specific directory."""
    # Test files in test_dir
    test_dir_files = git_utils.get_absolute_tracked_files_in_directory('test_dir')
    expected_files = {'test_dir/file3.txt', 'test_dir/file4.txt'}
    # Convert to absolute paths
    expected_files = {str(git_utils.repo_path / file) for file in expected_files}
    assert set(test_dir_files) == expected_files

    # Test files in root directory (should be empty when specifying a non-existent directory)
    nonexistent_dir_files = git_utils.get_absolute_tracked_files_in_directory(
        'nonexistent'
    )
    assert len(nonexistent_dir_files) == 0


def test_get_abs_tracked_files_in_directory_with_trailing_slash(git_utils):
    """Test getting tracked files in a directory with trailing slash."""
    test_dir_files = git_utils.get_absolute_tracked_files_in_directory('test_dir/')
    expected_files = {'test_dir/file3.txt', 'test_dir/file4.txt'}
    # Convert to absolute paths
    expected_files = {str(git_utils.repo_path / file) for file in expected_files}
    assert set(test_dir_files) == expected_files


def test_get_abs_tracked_files_in_subdirectory(git_utils):
    """Test getting tracked files in a subdirectory."""
    # Test files in test_dir
    test_dir_files = git_utils.get_absolute_tracked_files_in_directory('test_dir')
    expected_files = {'test_dir/file3.txt', 'test_dir/file4.txt'}
    # Convert to absolute paths
    expected_files = {str(git_utils.repo_path / file) for file in expected_files}
    assert set(test_dir_files) == expected_files


def test_empty_directory(git_utils, temp_git_repo):
    """Test getting tracked files in an empty directory."""
    # Create an empty directory
    empty_dir = temp_git_repo / 'empty_dir'
    empty_dir.mkdir()

    files = git_utils.get_absolute_tracked_files_in_directory('empty_dir')
    assert len(files) == 0


def test_get_tracked_files_tree_full(git_utils):
    """Test generating a full tracked files tree without depth restriction."""
    tree_output = git_utils.get_tracked_files_tree()

    # Expected tree structure
    expected_output = """\
├── file1.txt
├── file2.txt
└── test_dir
    ├── file3.txt
    └── file4.txt
"""
    assert tree_output == expected_output


def test_get_tracked_files_tree_with_depth(git_utils):
    """Test generating a tracked files tree with a depth limit of 1."""
    tree_output = git_utils.get_tracked_files_tree(depth=1)

    # Expected tree structure with depth 1 (only root-level files and directories)
    expected_output = """\
├── file1.txt
├── file2.txt
└── test_dir
"""
    assert tree_output == expected_output


def test_get_tracked_files_tree_in_subdirectory(git_utils):
    """Test generating a tracked files tree in a specific subdirectory."""
    tree_output = git_utils.get_tracked_files_tree(rel_dir_path='test_dir')

    # Expected tree structure including the rel_dir_path
    expected_output = """\
└── test_dir
    ├── file3.txt
    └── file4.txt
"""
    assert tree_output == expected_output


def test_get_tracked_files_tree_in_empty_directory(git_utils, temp_git_repo):
    """Test generating a tracked files tree in an empty directory."""
    empty_dir = temp_git_repo / 'empty_dir'
    empty_dir.mkdir()

    tree_output = git_utils.get_tracked_files_tree(rel_dir_path='empty_dir')

    # No files should be listed
    assert tree_output == ''


def test_get_tracked_files_tree_in_nonexistent_directory(git_utils):
    """Test generating a tracked files tree in a nonexistent directory."""
    tree_output = git_utils.get_tracked_files_tree(rel_dir_path='nonexistent')

    # No files should be listed as the directory doesn't exist
    assert tree_output == ''


def test_read_text_with_regular_file(tmp_path):
    # Test reading a regular text file
    test_file = tmp_path / 'test.txt'
    content = 'Hello, World!'
    test_file.write_text(content)

    result = read_text(str(test_file))
    assert result == content


def test_read_text_with_image_file(tmp_path):
    # Test reading an image file (should return empty string)
    image_file = tmp_path / 'test.jpg'
    image_file.write_bytes(b'fake image content')

    result = read_text(str(image_file))
    assert result == ''


@pytest.fixture
def temp_git_repo_in_subdir(tmp_path):
    """Create a temporary git repository inside a subdirectory."""
    # Create the parent directory and the subdirectory
    parent_dir = tmp_path / 'parent_dir'
    sub_dir = parent_dir / 'sub_repo'
    sub_dir.mkdir(parents=True)

    # Initialize git repo in the subdirectory
    repo = Repo.init(sub_dir)

    # Create some test files in the subdirectory
    (sub_dir / 'file1.txt').write_text('content1')
    (sub_dir / 'file2.txt').write_text('content2')

    # Stage and commit initial files
    repo.index.add(['file1.txt', 'file2.txt'])
    repo.index.commit('Initial commit in subdirectory repo')

    return parent_dir


def test_init_with_subdirectory_repo(temp_git_repo_in_subdir):
    """Test initialization with a Git repository in a subdirectory."""
    # Initialize GitRepoUtils with the subdirectory repo
    utils = GitRepoUtils(str(temp_git_repo_in_subdir))

    # Check that repo_path is set correctly to the subdirectory
    assert utils.repo_path == Path(temp_git_repo_in_subdir) / 'sub_repo'
    assert utils.repo is not None
