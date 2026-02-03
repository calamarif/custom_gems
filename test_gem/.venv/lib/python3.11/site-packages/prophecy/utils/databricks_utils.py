from fnmatch import fnmatchcase
from pyspark.sql import SparkSession
from databricks.sdk.errors.platform import NotFound
import os

def dbfs_glob(pattern: str, *, files_only: bool = True, max_results: int | None = None) -> list[str]:
    try:
        from databricks.sdk.runtime import dbutils
    except NameError:
        raise ImportError(
            "Unable to import `dbutils` from databricks.sdk.runtime. "
            "This typically means you are not running inside a Databricks runtime "
            "with the `databricks-sdk` package available."
        )

    def _split_anchor(p: str) -> [str, list[str]]:
        # Return (anchor, parts) where anchor is either 'dbfs:/' or '/'.
        if p.startswith("dbfs:/"):
            return "dbfs:/", [s for s in p[len("dbfs:/"):].split('/') if s]
        elif p.startswith('/'):
            return '/', [s for s in p[1:].split('/') if s]
        else:
            return "dbfs:/", [s for s in p.split('/') if s]

    anchor, parts = _split_anchor(pattern)

    def _join(anchor: str, comps: list[str]) -> str:
        return (anchor if anchor.endswith('/') else anchor + '/') + '/'.join(comps) if comps else anchor

    def _ls(path: str):
        try:
            return dbutils.fs.ls(path)
        except NotFound:
            raise NotFound(f"Path not found : {path}. Please verify that path exists on databricks.")
        except Exception as e:
            raise RuntimeError(f"Could not list files at path : {path}", e)

    def _is_dir(path: str) -> bool:
        # dbutils marks directories with trailing '/'
        return path.endswith('/')

    def _has_magic(s: str) -> bool:
        return ('*' in s) or ('?' in s) or ('[' in s) or (']' in s)

    # Find fixed prefix without any wildcards (to minimize listing)
    fixed = 0
    while fixed < len(parts) and parts[fixed] != '**' and not _has_magic(parts[fixed]):
        fixed += 1
    start_dir = _join(anchor, parts[:fixed]).rstrip('/')
    start_idx = fixed

    out, seen = [], set()

    # --- recursive matcher ----------------------------------------------------
    def _emit(p: str):
        if p not in seen:
            seen.add(p)
            out.append(p)

    def _recurse(cur_dir: str, idx: int):
        if max_results is not None and len(out) >= max_results:
            return
        try:
            children = _ls(cur_dir if cur_dir else anchor)
        except Exception:
            raise 

        # If we've consumed the pattern, current directory itself may be a match (dirs only)
        if idx >= len(parts):
            if not files_only:
                _emit(cur_dir)
            return

        seg = parts[idx]
        last = (idx == len(parts) - 1)

        if seg == '**':
            # '**' as last segment: include everything under cur_dir (and dirs if requested)
            if last:
                for fi in children:
                    if _is_dir(fi.path):
                        if not files_only:
                            _emit(fi.path.rstrip('/'))
                        _recurse(fi.path.rstrip('/'), idx)  # stay on '**'
                    else:
                        _emit(fi.path)
                return

            # '**' with more to match:
            # 1) zero segments
            _recurse(cur_dir, idx + 1)
            # 2) one-or-more segments: descend into subdirs and stay on '**'
            for fi in children:
                if _is_dir(fi.path):
                    _recurse(fi.path.rstrip('/'), idx)
            return

        # Normal segment (with/without simple wildcard)
        for fi in children:
            name = fi.name.rstrip('/')  # strip trailing '/' for dirs
            if fnmatchcase(name, seg):
                if _is_dir(fi.path):
                    if not last:
                        _recurse(fi.path.rstrip('/'), idx + 1)
                    elif not files_only:
                        _emit(fi.path.rstrip('/'))
                else:
                    if last:
                        _emit(fi.path)

    # Handle no-wildcard patterns by direct lookup in parent
    if start_idx == len(parts):
        parent = _join(anchor, parts[:-1]).rstrip('/') if parts else anchor
        leaf = parts[-1] if parts else ''
        try:
            for fi in _ls(parent or anchor):
                if fi.name.rstrip('/') == leaf:
                    if _is_dir(fi.path):
                        if not files_only:
                            _emit(fi.path.rstrip('/'))
                    else:
                        _emit(fi.path)
        except Exception:
            raise RuntimeError("Error while listing using dbutils")
        return out[:max_results] if max_results else out

    # Kick off recursion
    _recurse(start_dir, start_idx)
    return out[:max_results] if max_results else out


def to_fuse(p: str) -> str:
    if p.startswith("dbfs:/"):      return "/dbfs/" + p[len('dbfs:/'):]
    if p.startswith("/Volumes/"):   return "/dbfs" + p
    raise ValueError(f"Unsupported path for FUSE conversion: {p}")

def copy_from_dbfs_to_local(paths: list[str]) -> list[str]:
    from pathlib import Path
    from databricks.sdk.runtime import dbutils
    out = []
    for src in paths:
        dest = f'/tmp/prophecy{to_fuse(src)}'
        dest_path = Path(dest)
        dest_file_path = Path(f'file:{dest}')

        if dest_path.exists():
            dest_path.unlink(missing_ok=True)

        os.makedirs('/tmp/prophecy/', exist_ok=True)

        dbutils.fs.cp(src, dest_file_path)
        out.append(dest)
    return out

def is_dbfs_or_volumes_path(path: str, spark: SparkSession) -> bool:
    return path.startswith("dbfs:") or path.startswith("/Volumes")
