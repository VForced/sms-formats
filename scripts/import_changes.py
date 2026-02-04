#!/usr/bin/env python3
"""Import formats/senders from JSON on stdin: companies -> senders -> formats, with git commits."""

import json
import sys
from pathlib import Path

# Allow importing from same directory when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sms_format import (
    MARKER_COLUMNS,
    MARKER_EXAMPLE,
    DeletedSmsFormat,
    SmsFormat,
    clean_name,
    get_format_name,
    validate_sms_format_for_import,
)


def fail(message):
    sys.stderr.write(message + "\n")
    sys.exit(1)


def run_git(command, env=None):
    import os
    import subprocess

    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        env=full_env,
    )
    if result.returncode != 0:
        fail(f"Git command failed: {command}\n{result.stderr or result.stdout}")
    return (result.stdout or "").strip()


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


def list_bank_dirs(src_dir):
    p = Path(src_dir)
    if not p.exists():
        return []
    return [d.name for d in p.iterdir() if d.is_dir()]


def find_bank_dir_by_id(src_dir, company_id):
    for dir_name in list_bank_dirs(src_dir):
        parsed = parse_name_with_id(dir_name)
        if str(parsed["id"]) == str(company_id):
            return dir_name
    return None


def find_bank_dir_by_name_with_empty_id(src_dir, name):
    for dir_name in list_bank_dirs(src_dir):
        parsed = parse_name_with_id(dir_name)
        if parsed["name"] == name and (parsed["id"] is None or parsed["id"] == ""):
            return dir_name
    return None


def find_format_file_by_id(src_dir, format_id, company_id):
    bank_dirs = list_bank_dirs(src_dir)
    if company_id is not None:
        target_dirs = [d for d in bank_dirs if str(parse_name_with_id(d)["id"]) == str(company_id)]
    else:
        target_dirs = bank_dirs

    found = None
    for bank_dir in target_dirs:
        formats_dir = Path(src_dir) / bank_dir / "formats"
        if not formats_dir.exists():
            continue
        for f in formats_dir.iterdir():
            if not f.is_file() or not f.name.endswith(".txt"):
                continue
            base = f.stem
            fid = parse_name_with_id(base)["id"]
            if str(fid) == str(format_id):
                if found:
                    fail(f"Ambiguous format id {format_id}: multiple files found")
                found = {
                    "bankDir": bank_dir,
                    "filePath": str(formats_dir / f.name),
                    "fileName": f.name,
                }
    return found


def validate_changed(changed):
    from datetime import datetime, timezone

    try:
        s = str(changed).strip()
        if "Z" in s or "+" in s or s.count("-") >= 2:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except (ValueError, TypeError):
        fail(f"Invalid changed value: {changed}")


def format_file_content(regex, regex_group_names, examples):
    lines = []
    lines.append(str(regex).strip())
    lines.append("")
    lines.append(MARKER_COLUMNS)
    names = regex_group_names if regex_group_names is not None else []
    if isinstance(names, str):
        names = [n.strip() for n in names.strip().split(";")]
    else:
        names = [str(n).strip() for n in names]
    lines.append(";".join(names))
    for example in examples:
        lines.append("")
        lines.append(MARKER_EXAMPLE)
        example_lines = str(example).strip().splitlines()
        lines.extend(example_lines)
    lines.append("")
    return "\n".join(lines)


def commit_file(file_paths, message, changed):
    env = {
        "GIT_AUTHOR_DATE": changed,
        "GIT_COMMITTER_DATE": changed,
    }
    paths = file_paths if isinstance(file_paths, list) else [file_paths]
    paths = [p for p in paths if p is not None]
    cwd = Path.cwd()
    relative_paths = []
    for p in paths:
        pp = Path(p)
        if not pp.is_absolute():
            pp = cwd / pp
        relative_paths.append(str(pp.relative_to(cwd)))
    quoted = " ".join(f'"{p}"' for p in relative_paths)
    run_git(f"git add -A --ignore-errors -- {quoted}", env=env)
    safe_message = message.replace('"', '\\"')
    run_git(f'git commit -m "{safe_message}"', env=env)


def main():
    input_text = sys.stdin.read()
    if not input_text.strip():
        fail("No input provided on stdin")

    try:
        diff = json.loads(input_text)
    except json.JSONDecodeError as e:
        fail(f"Invalid JSON input: {e}")

    formats = diff.get("formats")
    if formats is None:
        formats = []
    elif not isinstance(formats, list):
        formats = []

    senders = diff.get("senders")
    if senders is None:
        senders = []
    elif not isinstance(senders, list):
        senders = []

    companies = diff.get("companies")
    if companies is None:
        companies = []
    elif not isinstance(companies, list):
        companies = []

    src_dir = Path.cwd() / "src"

    # First update companies
    for company in companies:
        company_id = company.get("id")
        name = clean_name(company.get("name") or "")
        changed = validate_changed(company.get("changed", ""))
        if company_id is None or not name:
            fail("Company entry missing id or name")

        existing_by_id = find_bank_dir_by_id(src_dir, company_id)
        if existing_by_id:
            desired_dir = f"{name}_{company_id}"
            if existing_by_id != desired_dir:
                from_path = src_dir / existing_by_id
                to_path = src_dir / desired_dir
                from_path.rename(to_path)
                commit_file(
                    [str(from_path), str(to_path)],
                    f"[{name}] rename bank",
                    changed,
                )
            continue

        existing_by_name = find_bank_dir_by_name_with_empty_id(src_dir, name)
        if existing_by_name:
            from_path = src_dir / existing_by_name
            to_path = src_dir / f"{name}_{company_id}"
            from_path.rename(to_path)
            commit_file(
                [str(from_path), str(to_path)],
                f"[{name}] rename bank",
                changed,
            )
            continue

        new_dir = src_dir / f"{name}_{company_id}"
        new_dir.mkdir(parents=True, exist_ok=True)
        senders_path = new_dir / "senders.txt"
        senders_path.write_text("", encoding="utf-8")
        commit_file(str(new_dir), f"[{name}] create bank", changed)

    # Then update senders
    for sender_entry in senders:
        company_id = sender_entry.get("companyId")
        senders_list = sender_entry.get("senders")
        if senders_list is None:
            senders_list = []
        elif not isinstance(senders_list, list):
            senders_list = []
        changed = validate_changed(sender_entry.get("changed", ""))
        if company_id is None:
            fail("Sender entry missing companyId")
        bank_dir = find_bank_dir_by_id(src_dir, company_id)
        if not bank_dir:
            fail(f"Bank directory not found for companyId {company_id}")
        bank_name = parse_name_with_id(bank_dir)["name"]
        senders_path = src_dir / bank_dir / "senders.txt"
        content = "\n".join(senders_list) + "\n" if senders_list else "\n"
        current = senders_path.read_text(encoding="utf-8") if senders_path.exists() else None
        if current == content:
            continue
        senders_path.write_text(content, encoding="utf-8")
        commit_file(str(senders_path), f"[{bank_name}] update senders", changed)

    # Then update formats
    for format_entry in formats:
        has_regex = isinstance(format_entry.get("regexp"), str)
        has_examples = isinstance(format_entry.get("examples"), list)
        is_deletion = not has_regex and not has_examples

        if is_deletion:
            deleted = DeletedSmsFormat.from_diff_dict(format_entry)
            if not deleted.id:
                fail("Deleted format entry missing id")
            found = find_format_file_by_id(
                src_dir,
                deleted.id,
                format_entry.get("companyId"),
            )
            if not found:
                continue
            bank_name = parse_name_with_id(found["bankDir"])["name"]
            changed = validate_changed(deleted.changed)
            Path(found["filePath"]).unlink()
            commit_file(found["filePath"], f"[{bank_name}] delete format", changed)
            continue

        fmt = SmsFormat.from_diff_dict(format_entry)
        import_errors = validate_sms_format_for_import(fmt)
        if import_errors:
            fail(import_errors[0])
        changed = validate_changed(fmt.changed or "")
        name = get_format_name(fmt)
        bank_dir = find_bank_dir_by_id(src_dir, fmt.company_id)
        if not bank_dir:
            fail(f"Bank directory not found for companyId {fmt.company_id}")

        bank_name = parse_name_with_id(bank_dir)["name"]
        formats_dir = src_dir / bank_dir / "formats"
        formats_dir.mkdir(parents=True, exist_ok=True)

        desired_file_name = f"{name}_{fmt.id}.txt" if fmt.id else f"{name}.txt"
        target_path = formats_dir / desired_file_name

        renamed_from = None
        if fmt.id is not None:
            for no_id_name in [f"{name}.txt", f"{name}_.txt"]:
                no_id_path = formats_dir / no_id_name
                if no_id_path.exists() and not target_path.exists():
                    no_id_path.rename(target_path)
                    renamed_from = str(no_id_path)
                    break

        content = format_file_content(
            fmt.regex,
            fmt.regex_group_names,
            fmt.examples,
        )
        current = target_path.read_text(encoding="utf-8") if target_path.exists() else None
        if not renamed_from and current == content:
            continue
        target_path.write_text(content, encoding="utf-8")
        commit_file(
            [renamed_from, str(target_path)] if renamed_from else str(target_path),
            f"[{bank_name}] update format {name}",
            changed,
        )


if __name__ == "__main__":
    main()
