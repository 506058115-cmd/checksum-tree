#!/usr/bin/env python3
"""Create or verify a portable SHA-256 manifest for a directory tree."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys


CHUNK_SIZE = 1024 * 1024
FORMAT = {"format": "checksum-tree", "version": 1}


def terminal_safe(value):
    return "".join(
        char if char.isprintable() else char.encode("unicode_escape").decode("ascii")
        for char in value
    )


def is_linklike(path):
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction and is_junction(path))


def collect_files(root, warnings):
    files = []

    def on_error(error):
        warnings.append(f"无法遍历 {error.filename}: {error}")

    for current, directories, names in os.walk(root, followlinks=False, onerror=on_error):
        base = Path(current)
        directories[:] = [name for name in sorted(directories) if not is_linklike(base / name)]
        for name in sorted(names):
            path = base / name
            try:
                info = path.lstat()
            except OSError as error:
                warnings.append(f"无法读取 {path}: {error}")
                continue
            if stat.S_ISREG(info.st_mode):
                files.append(path)
    # ponytail: keep paths in memory to emit a stable sorted manifest; use an external sort for huge trees.
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def digest_file(path):
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise OSError("文件在校验时发生变化")
    return after.st_size, digest.hexdigest()


def get_root(value):
    root = Path(value).expanduser()
    if is_linklike(root) or not root.is_dir():
        raise ValueError("根路径必须是非链接目录")
    return root.resolve(strict=True)


def write_manifest(records, output, root):
    lines = [json.dumps(FORMAT, ensure_ascii=False)]
    lines.extend(json.dumps(item, ensure_ascii=False) for item in records)
    content = "\n".join(lines) + "\n"
    if output == "-":
        sys.stdout.write(content)
        return

    destination = Path(output).expanduser().resolve()
    if os.path.commonpath((str(root), str(destination))) == str(root):
        raise ValueError("清单文件必须保存在扫描目录之外")
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def create(args):
    root = get_root(args.root)
    warnings = []
    records = []
    for path in collect_files(root, warnings):
        try:
            size, digest = digest_file(path)
        except OSError as error:
            warnings.append(f"无法校验 {path}: {error}")
            continue
        records.append({
            "path": path.relative_to(root).as_posix(),
            "size": size,
            "sha256": digest,
        })

    for warning in warnings:
        print(f"checksum-tree: {terminal_safe(warning)}", file=sys.stderr)
    if warnings:
        return 1
    write_manifest(records, args.output, root)
    print(f"已记录 {len(records)} 个文件。", file=sys.stderr)
    return 0


def safe_relative_path(value):
    if not value or "\\" in value or ":" in value:
        return None
    relative = PurePosixPath(value)
    if relative.is_absolute() or str(relative) != value or ".." in relative.parts:
        return None
    return relative


def load_manifest(path):
    with Path(path).open("r", encoding="utf-8") as stream:
        header = json.loads(next(stream, ""))
        if header != FORMAT:
            raise ValueError("清单格式或版本不受支持")
        records = {}
        for number, line in enumerate(stream, 2):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"清单第 {number} 行必须是 JSON 对象")
            relative = safe_relative_path(item.get("path", ""))
            digest = item.get("sha256")
            size = item.get("size")
            if (
                relative is None
                or not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
            ):
                raise ValueError(f"清单第 {number} 行无效")
            key = relative.as_posix()
            if key in records:
                raise ValueError(f"清单第 {number} 行路径重复")
            records[key] = item
    return records


def verify(args):
    root = get_root(args.root)
    expected = load_manifest(args.manifest)
    warnings = []
    actual = {
        path.relative_to(root).as_posix(): path
        for path in collect_files(root, warnings)
    }
    issues = 0

    for path in sorted(expected):
        file_path = actual.get(path)
        if file_path is None:
            print(f"缺少: {terminal_safe(path)}")
            issues += 1
            continue
        try:
            size, digest = digest_file(file_path)
        except OSError as error:
            warnings.append(f"无法校验 {file_path}: {error}")
            continue
        item = expected[path]
        if size != item["size"] or digest != item["sha256"]:
            print(f"不匹配: {terminal_safe(path)}")
            issues += 1

    for path in sorted(actual.keys() - expected.keys()):
        print(f"未列入清单: {terminal_safe(path)}")
        issues += 1
    for warning in warnings:
        print(f"checksum-tree: {terminal_safe(warning)}", file=sys.stderr)

    if issues or warnings:
        print(f"发现 {issues} 项差异；校验可能不完整。", file=sys.stderr)
        return 1
    print(f"已核验 {len(expected)} 个文件，全部匹配。")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="创建或校验目录树的 SHA-256 清单。")
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create", help="创建清单")
    create_parser.add_argument("root", help="扫描的目录")
    create_parser.add_argument("-o", "--output", default="-", help="清单文件；默认输出到标准输出")
    create_parser.set_defaults(run=create)
    verify_parser = commands.add_parser("verify", help="校验清单")
    verify_parser.add_argument("root", help="要核对的目录")
    verify_parser.add_argument("manifest", help="create 生成的 JSON Lines 清单")
    verify_parser.set_defaults(run=verify)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"checksum-tree: {terminal_safe(str(error))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("checksum-tree: 已中断。", file=sys.stderr)
        raise SystemExit(130)
