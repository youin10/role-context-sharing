"""Freeze / verify / extract a reproducible snapshot of the core experiment.

  python tools/snapshot.py hashes                 write expected-hashes.json (expected tables)
  python tools/snapshot.py create                 snapshots/<id>.tar.gz + <id>.json (+ .sha256)
  python tools/snapshot.py verify <id>            working tree == snapshot file list and hashes
  python tools/snapshot.py extract <id> <dir>     extract and verify the extracted tree

The tar holds the full code/input/runner/expected tree (src, runner, inputs, tools, upstream,
run.sh, README.md, expected-hashes.json, .gitignore), so an earlier version can be
restored from it, not only identified. Deterministic: sorted members, mtime 0, uid/gid 0.
"""
import datetime, glob, gzip, hashlib, io, json, os, sys, tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(ROOT, "snapshots")
MEMBERS = ["src", "runner", "inputs", "tools", "upstream", "run.sh", "README.md",
           "expected-hashes.json", ".gitignore"]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def tree(root):
    files = {}
    for m in MEMBERS:
        p = os.path.join(root, m)
        cands = [p] if os.path.isfile(p) else sorted(glob.glob(os.path.join(p, "**", "*"), recursive=True))
        for f in cands:
            if os.path.isfile(f) and "__pycache__" not in f:
                files[os.path.relpath(f, root)] = sha(open(f, "rb").read())
    return dict(sorted(files.items()))


def digest(files):
    return sha("".join(f"{k}:{v}\n" for k, v in files.items()).encode())


def cmd_hashes():
    files = {os.path.relpath(p, ROOT): sha(open(p, "rb").read())
             for p in sorted(glob.glob(os.path.join(ROOT, "inputs", "expected", "**", "*.yml"), recursive=True))}
    json.dump({"recorded_at": datetime.datetime.now().astimezone().isoformat(),
               "note": "frozen hashes of the expected tables of this snapshot (history: results/expected-prerun-hashes.json, results/expected-metadata-supplements.json)",
               "files": files}, open(os.path.join(ROOT, "expected-hashes.json"), "w"), indent=1)
    print(len(files))


def cmd_create():
    files = tree(ROOT)
    sid = "cs-core-" + digest(files)[:12]
    os.makedirs(SNAP, exist_ok=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for rel in files:
            data = open(os.path.join(ROOT, rel), "rb").read()
            ti = tarfile.TarInfo(f"conditional-sharing/{rel}")
            ti.size, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = len(data), 0, 0, 0, "", ""
            ti.mode = 0o755 if os.access(os.path.join(ROOT, rel), os.X_OK) else 0o644
            tar.addfile(ti, io.BytesIO(data))
    tgz = os.path.join(SNAP, sid + ".tar.gz")
    if os.path.exists(tgz):
        sys.exit(f"{tgz} exists")
    with open(tgz, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as gz:
            gz.write(buf.getvalue())
    tsha = sha(open(tgz, "rb").read())
    open(tgz + ".sha256", "w").write(f"{tsha}  {sid}.tar.gz\n")
    json.dump({"snapshot": sid, "created": datetime.datetime.now().astimezone().isoformat(),
               "tree_digest": digest(files), "tar_sha256": tsha, "n_files": len(files), "files": files},
              open(os.path.join(SNAP, sid + ".json"), "w"), indent=1)
    print(sid, tsha)


def cmd_verify(sid, root=ROOT):
    man = json.load(open(os.path.join(SNAP, sid + ".json")))
    files = tree(root)
    bad = sorted(k for k in set(files) | set(man["files"]) if files.get(k) != man["files"].get(k))
    print("verify", sid, root, "OK" if not bad else f"DIFF {bad[:10]}")
    return 0 if not bad else 1


def cmd_extract(sid, dest):
    tgz = os.path.join(SNAP, sid + ".tar.gz")
    want = open(tgz + ".sha256").read().split()[0]
    if sha(open(tgz, "rb").read()) != want:
        sys.exit("tar sha256 mismatch")
    with tarfile.open(tgz) as tar:
        tar.extractall(dest, filter="data")
    return cmd_verify(sid, os.path.join(dest, "conditional-sharing"))


if __name__ == "__main__":
    c = sys.argv[1]
    sys.exit({"hashes": lambda: cmd_hashes(), "create": lambda: cmd_create(),
              "verify": lambda: cmd_verify(sys.argv[2]), "extract": lambda: cmd_extract(sys.argv[2], sys.argv[3])}[c]() or 0)
