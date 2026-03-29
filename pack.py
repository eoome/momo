#!/usr/bin/env python3
"""打包 momo 项目为 zip"""
import zipfile, os, sys

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(os.path.dirname(PROJ_DIR), "momo.zip")
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
SKIP_EXTS = {".pyc"}

def make_zip():
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PROJ_DIR):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if any(f.endswith(ext) for ext in SKIP_EXTS):
                    continue
                filepath = os.path.join(root, f)
                arcname = os.path.relpath(filepath, os.path.dirname(PROJ_DIR))
                zf.write(filepath, arcname)
    size = os.path.getsize(ZIP_PATH)
    print(f"✅ momo.zip 已更新 ({size:,} bytes)")

if __name__ == "__main__":
    make_zip()
