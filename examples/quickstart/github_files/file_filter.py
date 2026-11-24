"""Decides which repository files to replicate, used by connector.py.

Every rule except the binary sniff runs against the tree entry alone, before any content is
decoded. A denylist rather than an allowlist: the goal is "all text and code", and an allowlist
would need hundreds of entries and silently drop every language added after it was written.
"""

# For compiling include path globs into regular expressions
import re

SNIFF_BYTES = 8192

# Files above this are skipped. Not configurable: the binding cost is embedding, not transfer,
# and a text file this large is almost always generated rather than hand-written.
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024

MAX_PATTERN_LENGTH = 512

__MAX_NON_TEXT_FRACTION = 0.3
__SYMLINK_MODE = "120000"

# Directories whose contents are dependencies, build output, or tooling state.
__DENIED_DIRECTORIES = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "vendor",
    "bower_components",
    ".venv",
    "venv",
    "site-packages",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "dist",
    "build",
    "out",
    "target",
    "bin",
    "obj",
    ".gradle",
    ".next",
    ".nuxt",
    ".terraform",
    ".idea",
    ".vscode",
    "coverage",
    ".nyc_output",
    "Pods",
    "Carthage",
    "third_party",
    ".yarn",
}

# Generated or lock files: large, machine-written, and worthless as retrievable documents.
__DENIED_FILENAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.lock",
    "poetry.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
    ".DS_Store",
}

# Filename suffixes that mark generated or minified output.
__DENIED_SUFFIXES = (".lock", ".min.js", ".min.css", ".map", ".snap", ".pb.go", "_pb2.py")

# Never text. Includes credential-bearing formats: hygiene, not a security control, since a
# secret inside a .json file still passes.
__DENIED_EXTENSIONS = {
    # images
    "png",
    "jpg",
    "jpeg",
    "gif",
    "bmp",
    "ico",
    "webp",
    "tiff",
    "tif",
    "svgz",
    "psd",
    "ai",
    "eps",
    # fonts
    "ttf",
    "otf",
    "woff",
    "woff2",
    "eot",
    # archives
    "zip",
    "tar",
    "gz",
    "tgz",
    "bz2",
    "xz",
    "7z",
    "rar",
    "jar",
    "war",
    "ear",
    # media
    "mp3",
    "mp4",
    "mov",
    "avi",
    "mkv",
    "wav",
    "flac",
    "ogg",
    "webm",
    # compiled and binary
    "exe",
    "dll",
    "so",
    "dylib",
    "a",
    "o",
    "obj",
    "lib",
    "class",
    "pyc",
    "pyo",
    "pyd",
    "wasm",
    "bin",
    "dat",
    "db",
    "sqlite",
    "sqlite3",
    "mdb",
    "whl",
    "egg",
    "pyz",
    "pack",
    "idx",
    # columnar data
    "parquet",
    "avro",
    "orc",
    # OS packages
    "iso",
    "dmg",
    "deb",
    "rpm",
    # credentials and state
    "pem",
    "key",
    "p12",
    "pfx",
    "jks",
    "keystore",
    "ppk",
    "kdbx",
    "tfstate",
    "tfvars",
    "env",
}


def compile_include_patterns(patterns):
    """
    Compile include path globs. Empty patterns are ignored.
    Args:
        patterns: the glob strings from the configuration.
    Returns:
        A list of compiled regular expressions.
    Raises:
        ValueError: if a pattern is not a valid glob.
    """
    return [glob_to_regex(pattern) for pattern in patterns if pattern]


def glob_to_regex(pattern: str):
    """
    Translate a glob into a regular expression with the semantics of Java's "glob:" PathMatcher,
    which the original connector used: "*" and "?" do not cross "/", "**" does, "[...]" is a
    bracket expression ("[!...]" negates), "{a,b}" is a group of alternatives and "\\" escapes.
    Args:
        pattern: the glob.
    Returns:
        The compiled regular expression, matched against the whole repository-relative path.
    Raises:
        ValueError: if the glob is malformed, for example an unclosed bracket or group.
    """
    regex = []
    index = 0
    in_group = False
    while index < len(pattern):
        character = pattern[index]
        if character == "\\":
            index += 1
            if index >= len(pattern):
                raise ValueError("No character to escape")
            regex.append(re.escape(pattern[index]))
        elif character == "*":
            if pattern.startswith("**", index):
                regex.append(".*")
                index += 1
            else:
                regex.append("[^/]*")
        elif character == "?":
            regex.append("[^/]")
        elif character == "[":
            index = append_bracket_expression(pattern, index, regex)
        elif character == "{":
            if in_group:
                raise ValueError("Cannot nest groups")
            regex.append("(?:")
            in_group = True
        elif character == "}" and in_group:
            regex.append(")")
            in_group = False
        elif character == "," and in_group:
            regex.append("|")
        else:
            regex.append(re.escape(character))
        index += 1
    if in_group:
        raise ValueError("Missing '}'")
    return re.compile("".join(regex) + r"\Z", re.DOTALL)


def append_bracket_expression(pattern: str, start: int, regex: list):
    """
    Translate the bracket expression that starts at pattern[start] and append it to regex.
    Args:
        pattern: the glob.
        start: the index of the opening "[".
        regex: the regular expression parts being built.
    Returns:
        The index of the closing "]".
    Raises:
        ValueError: if the bracket expression is not closed.
    """
    end = pattern.find("]", start + 2 if pattern.startswith("[!", start) else start + 1)
    if end < 0:
        raise ValueError("Missing ']'")
    body = pattern[start + 1 : end]
    negated = body.startswith("!")
    if negated:
        body = body[1:]
    escaped = body.replace("\\", "\\\\").replace("^", "\\^")
    # As in Java, a bracket expression never matches the path separator.
    regex.append(f"[^/{escaped}]" if negated else f"(?=[^/])[{escaped}]")
    return end


def rejection_reason(entry: dict, include_patterns: list):
    """
    Return why a tree entry is skipped, or None when it should be replicated. A reason rather than
    a boolean so callers can log it and tests can assert which rule fired.
    Args:
        entry: a tree entry with path, type, mode and size keys.
        include_patterns: compiled include globs; empty means include everything not denied.
    Returns:
        The reason string, or None.
    """
    if entry.get("type") != "blob":
        # Directories, and submodule gitlinks whose content lives elsewhere.
        return "not a file"
    if entry.get("mode") == __SYMLINK_MODE:
        return "symlink"
    path = entry.get("path")
    if not path:
        return "missing path"
    if has_denied_directory(path):
        return "excluded directory"
    name = file_name_of(path)
    if name.lower().startswith(".env"):
        # The .env family, which no extension rule can catch: a leading dot is part of the name,
        # so ".env" has no extension and ".env.local" has the extension "local".
        return "environment file"
    if has_denied_file_name(name):
        return "generated or lock file"
    if extension_of(name) in __DENIED_EXTENSIONS:
        return "binary or credential file type"
    size = entry.get("size")
    if size is not None and size > MAX_FILE_SIZE_BYTES:
        return f"larger than {MAX_FILE_SIZE_BYTES} bytes"
    if include_patterns and not any(pattern.match(path) for pattern in include_patterns):
        return "did not match any include pattern"
    return None


def is_prunable_directory(path: str):
    """
    Check whether a directory can be skipped without descending into it.
    Args:
        path: the repository-relative directory path.
    Returns:
        True when the directory is on the built-in denylist.
    """
    return has_denied_directory(path)


def has_denied_directory(path: str):
    """
    Check whether any segment of a path is a denied directory, including Bazel's "bazel-*" trees.
    Args:
        path: the repository-relative path.
    Returns:
        True when a segment is denied.
    """
    return any(
        segment in __DENIED_DIRECTORIES or segment.startswith("bazel-")
        for segment in path.split("/")
    )


def has_denied_file_name(name: str):
    """
    Check a file name against the generated and lock file rules.
    Args:
        name: the file name without its directory.
    Returns:
        True when the file is generated or a lock file.
    """
    if name in __DENIED_FILENAMES:
        return True
    lower = name.lower()
    return lower.endswith(__DENIED_SUFFIXES) or ".generated." in lower


def file_name_of(path: str):
    """
    Return the file name portion of a path.
    Args:
        path: the repository-relative path.
    Returns:
        The text after the last "/".
    """
    return path.rpartition("/")[2]


def directory_of(path: str):
    """
    Return the directory portion of a path.
    Args:
        path: the repository-relative path.
    Returns:
        The text before the last "/", or an empty string for a root-level file.
    """
    return path.rpartition("/")[0]


def extension_of(name: str):
    """
    Return the lower-cased extension of a file name. A leading dot is not a separator, so
    ".gitignore" has no extension.
    Args:
        name: the file name.
    Returns:
        The extension, or an empty string when there is none.
    """
    last_dot = name.rfind(".")
    if last_dot <= 0 or last_dot == len(name) - 1:
        return ""
    return name[last_dot + 1 :].lower()


def looks_binary(head: bytes):
    """
    Check whether content looks binary. Extensions lie (".ts" is TypeScript and also MPEG
    transport stream), and without this such a file would be decoded to replacement characters.
    Args:
        head: the first bytes of the content.
    Returns:
        True when the content has a NUL byte or too many control characters.
    """
    if not head:
        return False
    non_text = 0
    for byte in head:
        if byte == 0:
            return True
        # Control characters other than tab, newline, carriage return and form feed.
        if byte < 0x09 or byte == 0x0B or 0x0E <= byte < 0x20:
            non_text += 1
    return non_text / len(head) > __MAX_NON_TEXT_FRACTION
