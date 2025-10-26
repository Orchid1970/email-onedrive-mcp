# file_compressor.py
import zipfile
import os
from typing import List


def compress_files(file_paths: List[str], output_zip: str) -> None:
    """
    Compress the provided list of files into output_zip (overwrites if exists).
    """
    os.makedirs(os.path.dirname(output_zip) or ".", exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in file_paths:
            if not os.path.exists(f):
                raise FileNotFoundError(f"File does not exist: {f}")
            arcname = os.path.basename(f)
            zf.write(f, arcname=arcname)