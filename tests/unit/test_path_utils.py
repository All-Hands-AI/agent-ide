from pathlib import Path

import pytest

from openhands_aci.utils.path import (
    PathUtils,
    get_depth_of_rel_path,
    has_image_extension,
)


@pytest.fixture
def path_utils():
    return PathUtils(root='/home/user/project')


def test_get_absolute_path_str(path_utils):
    relative_path = 'src/module/file.py'
    expected_absolute = str(
        Path('/home/user/project').joinpath(relative_path).resolve()
    )

    result = path_utils.get_absolute_path_str(relative_path)

    assert result == expected_absolute, f'Expected {expected_absolute}, got {result}'


def test_get_relative_path_str(path_utils):
    absolute_path = '/home/user/project/src/module/file.py'
    expected_relative = 'src/module/file.py'

    result = path_utils.get_relative_path_str(absolute_path)

    assert result == expected_relative, f'Expected {expected_relative}, got {result}'


def test_get_absolute_path_str_with_non_existing_path(path_utils):
    relative_path = 'non_existent_folder/file.txt'
    expected_absolute = str(
        Path('/home/user/project').joinpath(relative_path).resolve()
    )

    result = path_utils.get_absolute_path_str(relative_path)

    assert result == expected_absolute, 'Unexpected result for a non-existing path'


def test_get_relative_path_str_with_non_project_path(path_utils):
    with pytest.raises(ValueError):
        path_utils.get_relative_path_str('/home/user/other_project/file.py')


def test_has_image_extension_png():
    assert has_image_extension('some/dir/image.png') is True


def test_get_depth_of_rel_path():
    assert get_depth_of_rel_path('folder/subfolder/file.txt') == 3
    assert get_depth_of_rel_path('folder/file.txt') == 2
    assert get_depth_of_rel_path('file.txt') == 1
    assert get_depth_of_rel_path('') == 0
    assert get_depth_of_rel_path('folder/subfolder/subsubfolder/') == 3
