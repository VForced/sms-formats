#!/usr/bin/env python3
"""Export changed formats and senders as JSON (--since or --last-commit)."""

import json
import subprocess
import sys
from pathlib import Path

# Allow importing from same directory when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sms_format import (
    DeletedSmsFormat,
    ValidationError,
    parse_format_file,
    parse_senders,
)


def parse_args(argv):
    args = {}
    i = 0
    while i < len(argv):
        key = argv[i]
        if not key.startswith("--"):
            i += 1
            continue
        value = argv[i + 1] if i + 1 < len(argv) else None
        if not value or value.startswith("--"):
            args[key] = True
        else:
            args[key] = value
            i += 1
        i += 1
    return args


def fail(message):
    sys.stderr.write(message + "\n")
    sys.exit(1)


def run_git(command):
    try:
        return subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None


def commit_exists(commit_sha):
    if not commit_sha:
        return False
    result = subprocess.run(
        f"git cat-file -e {commit_sha}^{{commit}}",
        shell=True,
        capture_output=True,
    )
    return result.returncode == 0


def resolve_since_iso(since_value):
    try:
        as_number = int(float(since_value))
        from datetime import datetime

        dt = datetime.utcfromtimestamp(as_number / 1000.0)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except (ValueError, OSError):
        pass
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(since_value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except (ValueError, TypeError):
        pass
    fail("Invalid --since value (expected unix ms or ISO date)")


def list_changes_with_git_args(git_args):
    output = run_git(f"git log {git_args} --name-status --pretty=format: -- src")
    if not output:
        return []
    changes = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        parts = [p.strip() for p in parts]
        status = parts[0] if parts else ""
        if not status:
            continue
        if status.startswith("R") and len(parts) >= 3:
            changes.append({"status": status, "path": parts[2]})
            continue
        if len(parts) >= 2:
            changes.append({"status": status, "path": parts[1]})
    return changes


def get_last_change_iso(file_path):
    output = run_git(f'git log -1 --format=%cI -- "{file_path}"')
    if not output:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    return output.strip()


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


def main():
    args = parse_args(sys.argv[1:])
    since = args.get("--since")
    last_commit = args.get("--last-commit")

    if not since and not last_commit:
        fail("Usage: python3 scripts/export_changes.py --since <unix_ms|ISO> [--last-commit <sha>]")

    if last_commit and commit_exists(last_commit):
        changes = list_changes_with_git_args(f"{last_commit}..HEAD")
    else:
        since_iso = resolve_since_iso(since)
        changes = list_changes_with_git_args(f'--since="{since_iso}"')

    format_files = set()
    deleted_formats = []
    sender_files = set()

    for change in changes:
        path_str = change.get("path")
        if not path_str:
            continue
        parts = path_str.replace("\\", "/").split("/")
        if parts[0] != "src" or len(parts) < 3:
            continue

        if parts[2] == "senders.txt":
            if change.get("status") != "D":
                sender_files.add(path_str)
            continue

        if len(parts) >= 4 and parts[2] == "formats":
            format_file = parts[3]
            if not format_file.endswith(".txt"):
                continue
            if change.get("status") == "D":
                base = format_file[:-4]
                format_id = parse_name_with_id(base)["id"]
                if isinstance(format_id, int):
                    deleted_formats.append(
                        DeletedSmsFormat(
                            id=str(format_id),
                            changed=get_last_change_iso(path_str),
                        ).to_diff_dict()
                    )
                continue
            format_files.add(path_str)

    cwd = Path.cwd()
    formats_out = []

    for file_path in format_files:
        parts = file_path.replace("\\", "/").split("/")
        if len(parts) < 4:
            continue
        bank_dir = parts[1]
        bank_id = parse_name_with_id(bank_dir)["id"]
        if not isinstance(bank_id, int):
            continue

        format_file = parts[3]
        base = format_file[:-4]
        format_name = parse_name_with_id(base)["name"]
        format_id = parse_name_with_id(base)["id"]
        format_id_value = format_id if isinstance(format_id, int) else None

        full_path = cwd / file_path
        try:
            parsed = parse_format_file(str(full_path))
        except ValidationError as e:
            fail(str(e))
        except Exception as e:
            fail(str(e) or f"Invalid format file: {full_path}")

        parsed.name = format_name
        parsed.id = format_id_value
        parsed.company_id = str(bank_id)
        parsed.changed = get_last_change_iso(file_path)
        formats_out.append(parsed.to_diff_dict())

    senders_out = []
    for file_path in sender_files:
        parts = file_path.replace("\\", "/").split("/")
        if len(parts) < 3:
            continue
        bank_dir = parts[1]
        bank_id = parse_name_with_id(bank_dir)["id"]
        if not isinstance(bank_id, int):
            continue
        full_path = cwd / file_path
        if not full_path.exists():
            continue
        senders_list = parse_senders(str(full_path))
        senders_out.append(
            {
                "companyId": str(bank_id),
                "changed": get_last_change_iso(file_path),
                "senders": senders_list,
            }
        )

    result = {
        "formats": formats_out + deleted_formats,
        "senders": senders_out,
    }
    sys.stdout.write(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
