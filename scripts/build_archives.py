"""
Fast Archive Builder using system tar and hashlib.
"""
import os
import subprocess
import hashlib
from pathlib import Path

BASE_DIR = Path("/mnt/harddisk/wsy")
PROJECT_DIR = BASE_DIR / "drug-design-agent"

PRIVATE_BACKUP_TAR = BASE_DIR / "drug-design-agent-backup.tar.gz"
GITHUB_PACKAGE_TAR = BASE_DIR / "drug-design-agent-github.tar.gz"


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def get_formatted_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB ({size_bytes:,} bytes)"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB ({size_bytes:,} bytes)"


def build_archives():
    print("Building Private Backup tar.gz...")
    cmd_priv = [
        "tar", "-czf", str(PRIVATE_BACKUP_TAR),
        "--exclude=__pycache__",
        "--exclude=*.pyc",
        "--exclude=*.log",
        "--exclude=*.tmp",
        "--exclude=drug-design-agent/outputs/smoke_test/*",
        "drug-design-agent"
    ]
    subprocess.run(cmd_priv, cwd=str(BASE_DIR), check=True)
    print(f"Private Backup created at: {PRIVATE_BACKUP_TAR}")

    print("Building GitHub Code Package tar.gz...")
    cmd_gh = [
        "tar", "-czf", str(GITHUB_PACKAGE_TAR),
        "--exclude=__pycache__",
        "--exclude=*.pyc",
        "--exclude=*.log",
        "--exclude=*.tmp",
        "--exclude=*.pt",
        "--exclude=*.bin",
        "--exclude=*.safetensors",
        "--exclude=*.msgpack",
        "--exclude=*.onnx",
        "--exclude=*.ot",
        "--exclude=drug-design-agent/.env",
        "--exclude=drug-design-agent/.env.local",
        "--exclude=drug-design-agent/outputs/*",
        "drug-design-agent"
    ]
    subprocess.run(cmd_gh, cwd=str(BASE_DIR), check=True)
    print(f"GitHub Package created at: {GITHUB_PACKAGE_TAR}")


def main():
    build_archives()

    priv_size = PRIVATE_BACKUP_TAR.stat().st_size
    priv_sha = sha256_file(PRIVATE_BACKUP_TAR)

    gh_size = GITHUB_PACKAGE_TAR.stat().st_size
    gh_sha = sha256_file(GITHUB_PACKAGE_TAR)

    print("\n" + "=" * 70)
    print("ARCHIVE GENERATION SUMMARY")
    print("=" * 70)
    print(f"Private backup:")
    print(f"Path: {PRIVATE_BACKUP_TAR}")
    print(f"Size: {get_formatted_size(priv_size)}")
    print(f"SHA256: {priv_sha}")
    print()
    print(f"GitHub package:")
    print(f"Path: {GITHUB_PACKAGE_TAR}")
    print(f"Size: {get_formatted_size(gh_size)}")
    print(f"SHA256: {gh_sha}")
    print("=" * 70)

if __name__ == "__main__":
    main()
