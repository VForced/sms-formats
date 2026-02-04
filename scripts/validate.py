#!/usr/bin/env python3
"""Validate format files: names, columns, regex match, group count, no cross-match."""

import argparse
import sys
from pathlib import Path

from sms_format import (
    ValidationError,
    clean_name,
    compile_regex,
    parse_format_file,
    validate_cross_match,
    validate_sms_format,
    write_format_file,
)


def parse_name_with_id(raw):
    last_underscore = raw.rfind("_")
    if last_underscore == -1:
        return {"name": raw, "id": None}
    name = raw[:last_underscore]
    id_part = raw[last_underscore + 1 :]
    if id_part == "":
        return {"name": name, "id": None}
    try:
        return {"name": name, "id": int(id_part)}
    except ValueError:
        return {"name": name, "id": id_part}


def list_directories(dir_path):
    p = Path(dir_path)
    if not p.exists():
        return []
    return [d.name for d in p.iterdir() if d.is_dir()]


def list_format_files(bank_dir):
    formats_dir = Path(bank_dir) / "formats"
    if not formats_dir.exists():
        return []
    return [
        str(formats_dir / f.name)
        for f in formats_dir.iterdir()
        if f.is_file() and f.name.endswith(".txt")
    ]


def _is_format_file_path(file_path):
    return str(file_path).endswith(".txt") and "/formats/" in str(file_path)


def _relative_path(path, base=None):
    """Path relative to base (default cwd) for shorter output."""
    base = base or Path.cwd()
    try:
        return Path(path).resolve().relative_to(Path(base).resolve())
    except ValueError:
        return path


def _format_error_line(err: ValidationError, base=None) -> str:
    """Single line for stderr from a ValidationError (path: message style)."""
    path = _relative_path(err.file_path, base) if err.file_path else ""
    if path and not err.message.startswith(str(path)):
        return f"{path}: {err.message}"
    return err.message


def _print_errors(errors, src_dir, stream):
    """Print errors in test-runner style: header, one line per error, summary."""
    if not errors:
        return
    base = Path.cwd()
    stream.write("Validation FAILED\n")
    stream.write("=" * 60 + "\n")
    for err in errors:
        stream.write(_format_error_line(err, base) + "\n")
    files_with_errors = len({e.file_path for e in errors})
    stream.write("=" * 60 + "\n")
    stream.write(f"{len(errors)} error(s) in {files_with_errors} file(s)\n")


def run_validation(src_dir):
    """Full pass over all banks and format files. Returns list of ValidationError."""
    errors = []
    bank_dirs = list_directories(src_dir)

    for bank_dir_name in bank_dirs:
        bank_path = src_dir / bank_dir_name
        parsed_bank = parse_name_with_id(bank_dir_name)
        bank_name = parsed_bank["name"]
        bank_id = parsed_bank["id"]

        if bank_name != clean_name(bank_name):
            errors.append(
                ValidationError(
                    kind="invalid_name",
                    file_path=str(bank_path),
                    message="Invalid bank dir name",
                    expected_name=clean_name(bank_name),
                )
            )

        format_files = list_format_files(bank_path)
        if not format_files:
            continue

        formats = []
        formats_with_regex = []
        for file_path in format_files:
            try:
                parsed = parse_format_file(file_path)
                compiled = compile_regex(parsed.regex, file_path)
                base_name = Path(file_path).stem
                format_name = parse_name_with_id(base_name)["name"]
                formats.append((file_path, format_name, parsed, compiled))
                formats_with_regex.append((parsed, compiled, file_path))
            except ValidationError as e:
                errors.append(e)
            except Exception:
                errors.append(
                    ValidationError(
                        kind="invalid_format",
                        file_path=file_path,
                        message="Invalid format file",
                    )
                )

        for file_path, format_name, parsed, compiled in formats:
            errors.extend(
                validate_sms_format(
                    parsed,
                    file_path=file_path,
                    format_name=format_name,
                    compiled_regex=compiled,
                )
            )

        bank_label = f"{bank_name}_{bank_id or ''}"
        errors.extend(validate_cross_match(formats_with_regex, bank_label))

    return errors


def apply_fixes(errors, src_dir):
    """
    Apply fixable corrections: delete invalid_format files; remove example_no_match and
    cross_match examples; rename format files and bank dirs for invalid_name.
    Bank renames are done last so format paths stay valid.
    """
    to_delete = set()
    to_remove_examples = {}
    format_renames = []
    bank_renames = []

    format_rename_target = {}

    for err in errors:
        if err.kind == "invalid_format":
            to_delete.add(err.file_path)
        elif err.kind in ("example_no_match", "cross_match") and err.example_text is not None:
            to_remove_examples.setdefault(err.file_path, set()).add(err.example_text)
        elif err.kind == "invalid_name" and err.expected_name:
            if _is_format_file_path(err.file_path):
                path = Path(err.file_path)
                stem = path.stem
                parsed = parse_name_with_id(stem)
                id_part = parsed["id"]
                new_stem = (
                    f"{err.expected_name}_{id_part}" if id_part is not None else err.expected_name
                )
                new_path = path.parent / f"{new_stem}.txt"
                if str(new_path) != err.file_path:
                    format_rename_target[err.file_path] = str(new_path)
            else:
                bank_renames.append((err.file_path, err.expected_name))

    format_renames = list(format_rename_target.items())

    for file_path in to_delete:
        p = Path(file_path)
        if p.exists():
            p.unlink()

    for file_path, remove_set in to_remove_examples.items():
        p = Path(file_path)
        if not p.exists() or file_path in to_delete:
            continue
        try:
            parsed = parse_format_file(file_path)
        except Exception:
            continue
        kept = [ex for ex in parsed.examples if ex not in remove_set]
        if not kept:
            p.unlink()
        else:
            write_format_file(file_path, parsed, kept)

    for old_path, new_path in format_renames:
        old_p, new_p = Path(old_path), Path(new_path)
        if old_p.exists() and old_path != new_path and not new_p.exists():
            old_p.rename(new_p)

    for bank_path_str, expected_name in bank_renames:
        bank_path = Path(bank_path_str)
        if not bank_path.is_dir():
            continue
        parsed = parse_name_with_id(bank_path.name)
        bank_id = parsed["id"]
        new_name = f"{expected_name}_{bank_id}" if bank_id is not None else expected_name
        new_path = bank_path.parent / new_name
        if str(new_path) != str(bank_path) and bank_path.exists() and not new_path.exists():
            bank_path.rename(new_path)


def main():
    parser = argparse.ArgumentParser(description="Validate SMS format files.")
    parser.add_argument(
        "--fix",
        action="store_true",
        help=(
            "Fix what can be fixed: delete invalid format files, "
            "remove invalid examples, rename format/bank to expected name. "
            "Bank renames applied last."
        ),
    )
    args = parser.parse_args()

    src_dir = Path.cwd() / "src"
    if not src_dir.exists():
        sys.stderr.write("No src/ directory found.\n")
        sys.exit(1)

    bank_dirs = list_directories(src_dir)
    if not bank_dirs:
        sys.stderr.write("No banks found in src/\n")
        sys.exit(1)

    errors = run_validation(src_dir)

    if args.fix and errors:
        apply_fixes(errors, src_dir)
        errors = run_validation(src_dir)

    if errors:
        _print_errors(errors, src_dir, sys.stderr)
        sys.exit(1)

    sys.stdout.write("Validation OK\n")


if __name__ == "__main__":
    main()
