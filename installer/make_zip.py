"""make_zip.py <src_dir> <out.zip>  — src_dir を TelloBlocks/ 以下に入れて ZIP にする (UTF-8 名)。"""
import os
import sys
import zipfile

src, dst = sys.argv[1:3]
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
    for d, _, files in os.walk(src):
        for f in files:
            full = os.path.join(d, f)
            z.write(full, os.path.join("TelloBlocks", os.path.relpath(full, src)))
