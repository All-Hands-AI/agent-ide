import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal, get_args

from .config import SNIPPET_CONTEXT_WINDOW
from .exceptions import (
    EditorToolParameterInvalidError,
    EditorToolParameterMissingError,
    ToolError,
)
from .navigator import SymbolNavigator
from .results import CLIResult, ToolResult, maybe_truncate
from .shell import run_shell_cmd

Command = Literal[
    'view',
    'create',
    'str_replace',
    'insert',
    'undo_edit',
    'jump_to_definition',
    'find_references',
]


class OHEditor:
    """
    An filesystem editor tool that allows the agent to
    - view
    - create
    - navigate
    - edit files
    The tool parameters are defined by Anthropic and are not editable.

    Original implementation: https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/computer_use_demo/tools/edit.py
    """

    TOOL_NAME = 'oh_editor'

    def __init__(self, workspace='./') -> None:
        self._file_history: dict[Path, list[str]] = defaultdict(list)
        self.symbol_navigator = SymbolNavigator(root=workspace)

    def __call__(
        self,
        *,
        command: Command,
        path: str | None = None,
        file_text: str | None = None,
        view_range: list[int] | None = None,
        old_str: str | None = None,
        new_str: str | None = None,
        insert_line: int | None = None,
        symbol_name: str | None = None,
        **kwargs,
    ) -> ToolResult | CLIResult:
        if path is not None:
            _path = Path(path)
            self.validate_path(command, _path)

        if command == 'view':
            return self.view(_path, view_range)
        elif command == 'create':
            if not file_text:
                raise
            self.write_file(_path, file_text)
            self._file_history[_path].append(file_text)
            return ToolResult(output=f'File created successfully at: {_path}')
        elif command == 'str_replace':
            if not old_str:
                raise EditorToolParameterMissingError(command, 'old_str')
            return self.str_replace(_path, old_str, new_str)
        elif command == 'insert':
            if insert_line is None:
                raise EditorToolParameterMissingError(command, 'insert_line')
            if not new_str:
                raise EditorToolParameterMissingError(command, 'new_str')
            return self.insert(_path, insert_line, new_str)
        elif command == 'undo_edit':
            return self.undo_edit(_path)
        elif command == 'jump_to_definition':
            if not symbol_name:
                raise EditorToolParameterMissingError(command, 'symbol_name')
            return self.jump_to_definition(_path if path else None, symbol_name)
        elif command == 'find_references':
            if not symbol_name:
                raise EditorToolParameterMissingError(command, 'symbol_name')
            return self.find_references(symbol_name)

        raise ToolError(
            f'Unrecognized command {command}. The allowed commands for the {self.TOOL_NAME} tool are: {", ".join(get_args(Command))}'
        )

    def str_replace(self, path: Path, old_str: str, new_str: str | None) -> CLIResult:
        """
        Implement the str_replace command, which replaces old_str with new_str in the file content.
        """
        self._populate_file_history_if_having_content_before_edit(path)

        file_content = self.read_file(path)
        old_str = old_str.expandtabs()
        new_str = new_str.expandtabs() if new_str is not None else ''

        # Check if old_str is unique in the file
        occurrences = file_content.count(old_str)
        if occurrences == 0:
            raise ToolError(
                f'No replacement was performed, old_str `{old_str}` did not appear verbatim in {path}.'
            )
        if occurrences > 1:
            file_content_lines = file_content.split('\n')
            line_numbers = [
                idx + 1
                for idx, line in enumerate(file_content_lines)
                if old_str in line
            ]
            raise ToolError(
                f'No replacement was performed. Multiple occurrences of old_str `{old_str}` in lines {line_numbers}. Please ensure it is unique.'
            )

        # Replace old_str with new_str
        new_file_content = file_content.replace(old_str, new_str)

        # Write the new content to the file
        self.write_file(path, new_file_content)

        # Save the content to history
        self._file_history[path].append(new_file_content)

        # Create a snippet of the edited section
        replacement_line = file_content.split(old_str)[0].count('\n')
        start_line = max(0, replacement_line - SNIPPET_CONTEXT_WINDOW)
        end_line = replacement_line + SNIPPET_CONTEXT_WINDOW + new_str.count('\n')
        snippet = '\n'.join(new_file_content.split('\n')[start_line : end_line + 1])

        # Prepare the success message
        success_msg = f'The file {path} has been edited. '
        success_msg += self._make_output(
            snippet, f'a snippet of {path}', start_line + 1
        )
        success_msg += 'Review the changes and make sure they are as expected. Edit the file again if necessary.'
        return CLIResult(output=success_msg)

    def view(self, path: Path, view_range: list[int] | None = None) -> CLIResult:
        """
        View the contents of a file or a directory.
        """
        if path.is_dir():
            if view_range:
                raise EditorToolParameterInvalidError(
                    'view_range',
                    view_range,
                    'The `view_range` parameter is not allowed when `path` points to a directory.',
                )

            _, stdout, stderr = run_shell_cmd(
                rf"find {path} -maxdepth 2 -not -path '*/\.*'"
            )
            if not stderr:
                stdout = f"Here's the files and directories up to 2 levels deep in {path}, excluding hidden items:\n{stdout}\n"
            return CLIResult(output=stdout, error=stderr)

        file_content = self.read_file(path)
        start_line = 1
        if not view_range:
            return CLIResult(
                output=self._make_output(file_content, str(path), start_line)
            )

        if len(view_range) != 2 or not all(isinstance(i, int) for i in view_range):
            raise EditorToolParameterInvalidError(
                'view_range',
                view_range,
                'It should be a list of two integers.',
            )

        file_content_lines = file_content.split('\n')
        num_lines = len(file_content_lines)
        start_line, end_line = view_range
        if start_line < 1 or start_line > num_lines:
            raise EditorToolParameterInvalidError(
                'view_range',
                view_range,
                f'Its first element `{start_line}` should be within the range of lines of the file: {[1, num_lines]}.',
            )

        if end_line > num_lines:
            raise EditorToolParameterInvalidError(
                'view_range',
                view_range,
                f'Its second element `{end_line}` should be smaller than the number of lines in the file: `{num_lines}`.',
            )

        if end_line != -1 and end_line < start_line:
            raise EditorToolParameterInvalidError(
                'view_range',
                view_range,
                f'Its second element `{end_line}` should be greater than or equal to the first element `{start_line}`.',
            )

        if end_line == -1:
            file_content = '\n'.join(file_content_lines[start_line - 1 :])
        else:
            file_content = '\n'.join(file_content_lines[start_line - 1 : end_line])
        return CLIResult(output=self._make_output(file_content, str(path), start_line))

    def insert(self, path: Path, insert_line: int, new_str: str) -> CLIResult:
        """
        Implement the insert command, which inserts new_str at the specified line in the file content.
        """
        self._populate_file_history_if_having_content_before_edit(path)

        try:
            file_text = self.read_file(path)
        except Exception as e:
            raise ToolError(f'Ran into {e} while trying to read {path}') from None

        file_text = file_text.expandtabs()
        new_str = new_str.expandtabs()

        file_text_lines = file_text.split('\n')
        num_lines = len(file_text_lines)

        if insert_line < 0 or insert_line > num_lines:
            raise EditorToolParameterInvalidError(
                'insert_line',
                insert_line,
                f'It should be within the range of lines of the file: {[0, num_lines]}',
            )

        new_str_lines = new_str.split('\n')
        new_file_text_lines = (
            file_text_lines[:insert_line]
            + new_str_lines
            + file_text_lines[insert_line:]
        )
        snippet_lines = (
            file_text_lines[max(0, insert_line - SNIPPET_CONTEXT_WINDOW) : insert_line]
            + new_str_lines
            + file_text_lines[
                insert_line : min(num_lines, insert_line + SNIPPET_CONTEXT_WINDOW)
            ]
        )
        new_file_text = '\n'.join(new_file_text_lines)
        snippet = '\n'.join(snippet_lines)

        self.write_file(path, new_file_text)
        self._file_history[path].append(new_file_text)

        success_message = f'The file {path} has been edited. '
        success_message += self._make_output(
            snippet,
            'a snippet of the edited file',
            max(1, insert_line - SNIPPET_CONTEXT_WINDOW + 1),
        )
        success_message += 'Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary.'
        return CLIResult(output=success_message)

    def undo_edit(self, path: Path) -> CLIResult:
        """
        Implement the undo_edit command.
        """
        if not self._file_history[path] or len(self._file_history[path]) <= 1:
            raise ToolError(f'No edit history found for {path}.')

        self._file_history[path].pop()
        old_text = self._file_history[path][-1]
        self.write_file(path, old_text)

        return CLIResult(
            output=f'Last edit to {path} undone successfully. {self._make_output(old_text, str(path))}'
        )

    def jump_to_definition(self, path: Path | None, symbol_name: str) -> ToolResult:
        """
        Implement the jump_to_definition command.
        """
        if path is None:
            return CLIResult(
                output=self.symbol_navigator.get_definitions_tree(symbol_name)
            )
        else:
            rel_path_str = str(path.relative_to(self.symbol_navigator.root))
            return CLIResult(
                output=self.symbol_navigator.get_definitions_tree(
                    symbol_name, rel_path_str
                )
            )

    def find_references(self, symbol_name: str) -> ToolResult:
        """
        Implement the find_references command.
        """
        return CLIResult(output=self.symbol_navigator.get_references_tree(symbol_name))

    def validate_path(self, command: Command, path: Path) -> None:
        """
        Check that the path/command combination is valid.
        """
        # Check if its an absolute path
        if not path.is_absolute():
            suggested_path = Path('') / path
            raise EditorToolParameterInvalidError(
                'path',
                path,
                f'The path should be an absolute path, starting with `/`. Maybe you meant {suggested_path}?',
            )
        # Check if path and command are compatible
        if command == 'create' and path.exists():
            raise EditorToolParameterInvalidError(
                'path',
                path,
                f'File already exists at: {path}. Cannot overwrite files using command `create`.',
            )
        if command != 'create' and not path.exists():
            raise EditorToolParameterInvalidError(
                'path',
                path,
                f'The path {path} does not exist. Please provide a valid path.',
            )
        if command != 'view' and path.is_dir():
            raise EditorToolParameterInvalidError(
                'path',
                path,
                f'The path {path} is a directory and only the `view` command can be used on directories.',
            )

    def read_file(self, path: Path) -> str:
        """
        Read the content of a file from a given path; raise a ToolError if an error occurs.
        """
        try:
            return path.read_text()
        except Exception as e:
            raise ToolError(f'Ran into {e} while trying to read {path}') from None

    def write_file(self, path: Path, file_text: str) -> None:
        """
        Write the content of a file to a given path; raise a ToolError if an error occurs.
        """
        try:
            path.write_text(file_text)
        except Exception as e:
            raise ToolError(f'Ran into {e} while trying to write to {path}') from None

    def _populate_file_history_if_having_content_before_edit(self, path: Path) -> None:
        """
        Populate the file history with the current file content.
        """
        # Check if the file exists or history is not empty
        if len(self._file_history[path]) > 0 or not path.exists():
            return

        self._file_history[path].append(self.read_file(path))

    def _make_output(
        self,
        snippet_content: str,
        snippet_description: str,
        start_line: int = 1,
        expand_tabs: bool = True,
    ) -> str:
        """
        Generate output for the CLI based on the content of a code snippet.
        """
        snippet_content = maybe_truncate(snippet_content)
        if expand_tabs:
            snippet_content = snippet_content.expandtabs()

        snippet_content = '\n'.join(
            [
                f'{i + start_line:6}\t{line}'
                for i, line in enumerate(snippet_content.split('\n'))
            ]
        )
        return (
            f"Here's the result of running `cat -n` on {snippet_description}:\n"
            + snippet_content
            + '\n'
        )


def parse_command_input(cmd_input: str) -> tuple[Command, dict]:
    """Parse the command input into command name and parameters."""
    try:
        cmd_dict = json.loads(cmd_input)
        command = cmd_dict.pop('command')
        assert command in get_args(Command)
        return command, cmd_dict  # type: ignore
    except json.JSONDecodeError:
        raise ValueError('Invalid command format. Please provide a valid JSON object.')
    except KeyError:
        raise ValueError("Command must include a 'command' field.")


def print_help():
    """Print available commands and their usage."""
    help_text = """
Available commands (provide as JSON objects):
------------------------------------------
1. View file/directory:
    {"command": "view", "path": "/absolute/path", "view_range": [start_line, end_line]}

2. Create file:
    {"command": "create", "path": "/absolute/path", "file_text": "content"}

3. Replace string:
    {"command": "str_replace", "path": "/absolute/path", "old_str": "old", "new_str": "new"}

4. Insert at line:
    {"command": "insert", "path": "/absolute/path", "insert_line": number, "new_str": "content"}

5. Undo last edit:
    {"command": "undo_edit", "path": "/absolute/path"}

6. Jump to definition:
    {"command": "jump_to_definition", "path": "/absolute/path", "symbol_name": "symbol"}

7. Find references:
    {"command": "find_references", "symbol_name": "symbol"}

Type 'exit' to quit or 'help' to see this message again.
"""
    print(help_text)


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='OHEditor - File System Editor Tool')
    parser.add_argument(
        '--workspace',
        type=str,
        default='./',
        help='Workspace directory path (default: current directory)',
    )

    # Parse command line arguments
    args = parser.parse_args()

    # Initialize the editor
    editor = OHEditor(workspace=args.workspace)

    # Print welcome message and help
    print(f'OHEditor initialized with workspace: {args.workspace}')
    print_help()

    # Main command loop
    while True:
        try:
            # Get user input
            user_input = input("\nEnter command (or 'help'/'exit'): ").strip()

            # Check for exit command
            if user_input.lower() == 'exit':
                print('Exiting OHEditor...')
                break

            # Check for help command
            if user_input.lower() == 'help':
                print_help()
                continue

            # Parse and execute command
            try:
                command, params = parse_command_input(user_input)
                result = editor(command=command, **params)
                print('\nResult:')
                print(result.output)
                if result.error:
                    print('\nErrors:')
                    print(result.error)

            except (
                ValueError,
                ToolError,
                EditorToolParameterInvalidError,
                EditorToolParameterMissingError,
            ) as e:
                print(f'\nError: {str(e)}')

        except KeyboardInterrupt:
            print("\nReceived interrupt signal. Type 'exit' to quit.")
            continue
        except Exception as e:
            print(f'\nUnexpected error: {str(e)}')
            continue


if __name__ == '__main__':
    main()
