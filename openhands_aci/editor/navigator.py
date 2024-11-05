from collections import defaultdict
from pathlib import Path

from grep_ast import TreeContext
from tqdm import tqdm

from openhands_aci.tree_sitter.parser import ParsedTag, TagKind, TreeSitterParser
from openhands_aci.utils.file import GitRepoUtils, get_modified_time, read_text
from openhands_aci.utils.path import PathUtils


class SymbolNavigator:
    def __init__(self, root='./', show_progress=False) -> None:
        if not Path(root).is_absolute():
            root = str(Path(root).resolve())

        self.root = root
        self.show_progress = show_progress

        self.git_utils = GitRepoUtils(self.root)
        self.path_utils = PathUtils(self.root)
        self.ts_parser = TreeSitterParser(self.root)

        # Caching
        self.file_context_cache: dict = {}  # (rel_file) -> {'context': TreeContext_obj, 'mtime': mtime})
        self.rendered_tree_cache: dict = {}  # (rel_file, lois, mtime) -> rendered_tree

    def get_parsed_tags(
        self,
        depth: int | None = None,
        rel_dir_path: str | None = None,
    ) -> tuple[dict, dict, dict, dict]:
        if rel_dir_path:
            all_abs_files = self.git_utils.get_absolute_tracked_files_in_directory(
                rel_dir_path=rel_dir_path,
                depth=depth,
            )
        else:
            all_abs_files = self.git_utils.get_all_absolute_tracked_files(depth=depth)

        ident2defrels = defaultdict(
            set
        )  # symbol identifier -> set of its definitions' relative file paths
        ident2refrels = defaultdict(
            list
        )  # symbol identifier -> list of its references' relative file paths
        identwrel2deftags = defaultdict(
            set
        )  # (relative file, symbol identifier) -> set of its DEF tags
        identwrel2reftags = defaultdict(
            set
        )  # (relative file, symbol identifier) -> set of its REF tags

        all_abs_files_iter = (
            tqdm(all_abs_files, desc='Parsing tags', unit='file')
            if self.show_progress
            else all_abs_files
        )
        for abs_file in all_abs_files_iter:
            rel_file = self.path_utils.get_relative_path_str(abs_file)
            parsed_tags = self.ts_parser.get_tags_from_file(abs_file, rel_file)

            for parsed_tag in parsed_tags:
                if parsed_tag.tag_kind == TagKind.DEF:
                    ident2defrels[parsed_tag.node_content].add(rel_file)
                    identwrel2deftags[(rel_file, parsed_tag.node_content)].add(
                        parsed_tag
                    )
                if parsed_tag.tag_kind == TagKind.REF:
                    ident2refrels[parsed_tag.node_content].append(rel_file)
                    identwrel2reftags[(rel_file, parsed_tag.node_content)].add(
                        parsed_tag
                    )

        return ident2defrels, ident2refrels, identwrel2deftags, identwrel2reftags

    def get_definitions_tree(
        self, symbol: str, rel_file_path: str | None = None, use_end_line=True
    ):
        ident2defrels, _, identwrel2deftags, _ = self.get_parsed_tags()

        # Extract definitions for the symbol
        def_tags = set()
        if symbol:
            def_rels = ident2defrels.get(symbol, set())
            for def_rel in def_rels:
                if rel_file_path is not None and rel_file_path not in def_rel:
                    continue
                def_tags.update(identwrel2deftags.get((def_rel, symbol), set()))

        # Concatenate the definitions to another tree representation
        defs_repr = ''
        defs_repr += f'\nDefinition(s) of `{symbol}`:\n'
        # Sort the tags by file path and line number
        def_tags_list = list(def_tags)
        def_tags_list.sort(key=lambda tag: (tag.rel_path, tag.start_line))
        defs_repr += self.tag_list_to_tree(def_tags_list, use_end_line=use_end_line)
        defs_repr += '\n'

        return defs_repr

    def get_references_tree(self, symbol: str):
        _, ident2refrels, _, identwrel2reftags = self.get_parsed_tags()

        # Extract references for the symbol
        ref_tags = set()
        ref_rels = ident2refrels.get(symbol, set())
        for ref_rel in ref_rels:
            ref_tags.update(identwrel2reftags.get((ref_rel, symbol), set()))

        # Concatenate the direct references to another tree representation
        direct_refs_repr = ''
        direct_refs_repr += f'\nReferences to `{symbol}`:\n'
        # Sort the tags by file path and line number
        ref_tags_list = list(ref_tags)
        ref_tags_list.sort(key=lambda tag: (tag.rel_path, tag.start_line))
        direct_refs_repr += self.tag_list_to_tree(ref_tags_list, use_end_line=False)
        direct_refs_repr += '\n'

        return direct_refs_repr

    def tag_list_to_tree(self, tags: list[ParsedTag], use_end_line=False) -> str:
        if not tags:
            return ''

        cur_rel_file, cur_abs_file = '', ''
        lois: list[int] = []
        output = ''

        dummy_tag = ParsedTag(
            abs_path='',
            rel_path='',
            node_content='',
            tag_kind=TagKind.DEF,
            start_line=0,
            end_line=0,
        )
        for tag in tags + [dummy_tag]:  # Add dummy tag to trigger last file output
            if tag.rel_path != cur_rel_file:
                if lois:
                    output += cur_rel_file + ':\n'
                    output += self.render_tree(cur_abs_file, cur_rel_file, lois)
                    lois = []
                elif cur_rel_file:  # No line of interest
                    output += '\n' + cur_rel_file + ':\n'

                cur_abs_file = tag.abs_path
                cur_rel_file = tag.rel_path

            lois += (
                list(range(tag.start_line, tag.end_line + 1))
                if use_end_line
                else [tag.start_line]
            )

        # Truncate long lines in case we get minified js or something else crazy
        output = '\n'.join(line[:150] for line in output.splitlines())
        return output

    def render_tree(self, abs_file: str, rel_file: str, lois: list) -> str:
        mtime = get_modified_time(abs_file)
        tree_cache_key = (rel_file, tuple(sorted(lois)), mtime)
        if tree_cache_key in self.rendered_tree_cache:
            return self.rendered_tree_cache[tree_cache_key]

        if (
            rel_file not in self.file_context_cache
            or self.file_context_cache[rel_file]['mtime'] < mtime
        ):
            code = read_text(abs_file) or ''
            if not code.endswith('\n'):
                code += '\n'

            context = TreeContext(
                filename=rel_file,
                code=code,
                color=False,
                line_number=True,
                child_context=False,
                last_line=False,
                margin=0,
                mark_lois=False,
                loi_pad=0,
                # header_max=30,
                show_top_of_file_parent_scope=False,
            )
            self.file_context_cache[rel_file] = {'context': context, 'mtime': mtime}
        else:
            context = self.file_context_cache[rel_file]['context']

        context.lines_of_interest = set()
        context.add_lines_of_interest(lois)
        context.add_context()
        res = context.format()
        self.rendered_tree_cache[tree_cache_key] = res
        return res


if __name__ == '__main__':
    navigator = SymbolNavigator()
    # print(navigator.get_definitions_tree('ToolError'))
    print(navigator.get_references_tree('ToolError'))
