import warnings
from collections import namedtuple
from enum import Enum
from pathlib import Path

from diskcache import Cache
from grep_ast import filename_to_lang
from tree_sitter_languages import get_language, get_parser

from openhands_aci.utils.file import get_modified_time, read_text

warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')

ParsedTag = namedtuple(
    'ParsedTag',
    ('rel_path', 'abs_path', 'start_line', 'end_line', 'node_content', 'tag_kind'),
)


class TagKind(Enum):
    DEF = 'def'
    REF = 'ref'
    DEF_WITH_BODY = 'def_with_body'


class TreeSitterParser:
    TAGS_CACHE_VERSION = 3
    TAGS_CACHE_DIR = f'.cache.tags.v{TAGS_CACHE_VERSION}'

    def __init__(self, cache_root_dir: str) -> None:
        self.load_tags_cache(cache_root_dir)

    def load_tags_cache(self, abs_root_dir: str) -> None:
        cache_path = Path(abs_root_dir) / self.TAGS_CACHE_DIR
        try:
            self.tags_cache = Cache(cache_path)
        except Exception:
            print(
                f'Could not load tags cache from {cache_path}, try deleting cache directory.'
            )
            self.tags_cache = dict()

    def get_tags_from_file(self, abs_path: str, rel_path: str) -> list[ParsedTag]:
        mtime = get_modified_time(abs_path)
        cache_key = abs_path
        cache_val = self.tags_cache.get(cache_key)
        if cache_val and cache_val.get('mtime') == mtime:
            return cache_val.get('data')

        data = self.get_tags_raw(abs_path, rel_path)
        # Update cache
        self.tags_cache[cache_key] = {'mtime': mtime, 'data': data}
        return data

    def get_tags_raw(self, abs_path: str, rel_path: str) -> list[ParsedTag]:
        lang = filename_to_lang(abs_path)
        if not lang:
            return []

        ts_language = get_language(lang)
        ts_parser = get_parser(lang)

        tags_file_path = (
            Path(__file__).resolve().parent / 'queries' / f'tree-sitter-{lang}-tags.scm'
        )
        if not tags_file_path.exists():
            return []
        tags_query = tags_file_path.read_text()

        if not Path(abs_path).exists():
            return []
        code = read_text(abs_path)
        if not code:
            return []

        parsed_tree = ts_parser.parse(bytes(code, 'utf-8'))

        # Run the tags queries
        query = ts_language.query(tags_query)
        captures = query.captures(parsed_tree.root_node)

        parsed_tags = []
        for node, tag_str in captures:
            if tag_str.startswith('name.definition.'):
                tag_kind = TagKind.DEF
            elif tag_str.startswith('name.reference.'):
                tag_kind = TagKind.REF
            elif tag_str.startswith('definition.'):
                tag_kind = TagKind.DEF_WITH_BODY
            else:
                # Skip other tags
                continue

            result_tag = ParsedTag(
                rel_path=rel_path,
                abs_path=abs_path,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                node_content=node.text.decode('utf-8'),
                tag_kind=tag_kind,
            )
            parsed_tags.append(result_tag)

        parsed_tags = self._update_end_lines_for_def_using_def_with_body(parsed_tags)
        return parsed_tags

    def _update_end_lines_for_def_using_def_with_body(
        self, parsed_tags: list[ParsedTag]
    ) -> list[ParsedTag]:
        # Create a dictionary to quickly look up end_line for DEF_WITH_BODY tags
        def_with_body_lookup = {
            (tag.abs_path, tag.start_line): tag.end_line
            for tag in parsed_tags
            if tag.tag_kind == TagKind.DEF_WITH_BODY
        }

        # Iterate over tags and update end_line if a matching DEF_WITH_BODY exists
        result_tags = []
        for tag in parsed_tags:
            if (
                tag.tag_kind == TagKind.DEF
                and (tag.abs_path, tag.start_line) in def_with_body_lookup
            ):
                updated_tag = ParsedTag(
                    rel_path=tag.rel_path,
                    abs_path=tag.abs_path,
                    start_line=tag.start_line,
                    end_line=def_with_body_lookup[(tag.abs_path, tag.start_line)],
                    node_content=tag.node_content,
                    tag_kind=tag.tag_kind,
                )
                result_tags.append(updated_tag)
            else:
                result_tags.append(tag)

        return result_tags
