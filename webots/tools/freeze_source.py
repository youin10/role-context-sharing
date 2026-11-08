"""Writes a deterministic archive of the source tree to snapshots/ and prints its identifier."""
import gzip
import hashlib
import io
import os
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS = ["config", "sim", "tools", "wcs", "requirements.txt", "setup.sh"]


def files():
    for member in MEMBERS:
        path = os.path.join(ROOT, member)
        if os.path.isfile(path):
            yield member
        for base, dirs, names in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in sorted(names):
                if not name.endswith(".pyc") and name != ".DS_Store":
                    yield os.path.relpath(os.path.join(base, name), ROOT)


def main():
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, filename="") as gz, tarfile.open(fileobj=gz, mode="w") as tar:
        for rel in sorted(files()):
            info = tarfile.TarInfo(rel)
            with open(os.path.join(ROOT, rel), "rb") as f:
                data = f.read()
            info.size = len(data)
            info.mode = 0o755 if os.access(os.path.join(ROOT, rel), os.X_OK) else 0o644
            tar.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(buf.getvalue()).hexdigest()
    os.makedirs(os.path.join(ROOT, "snapshots"), exist_ok=True)
    name = f"wcs-v2-{digest[:12]}.tar.gz"
    with open(os.path.join(ROOT, "snapshots", name), "wb") as f:
        f.write(buf.getvalue())
    print(name, digest)


if __name__ == "__main__":
    main()
