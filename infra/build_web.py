"""AI Studio web istemcisini (origin/ai dalı) derleyip depo kökündeki `web-dist/` klasörüne koyar.

Kullanım (venv Python ile, depo kökünden):
    python infra/build_web.py [--base /qa/app/] [--no-fetch]

- origin/ai dalı fetch edilir, `%LOCALAPPDATA%\kys-agent\web-src` altına AYRIK (detached) git worktree olarak alınır
  (ai dalına commit atılmaz, main'e merge edilmez).
- Bağımlılıklar node ile `npm-cli.js` çağrılarak kurulur (npm.cmd / cmd.exe gerekmez).
- `vite build --base <yol>` ile derlenir. Çıktı:
    * `%LOCALAPPDATA%\kys-agent\web-dist\`  yerel kopya (`KYS_WEB_DIR` ile `kys serve` bunu sunar)
    * `web-dist.zip` (depo kökü) Cloud Build/Docker'a giden paket; Dockerfile imajda `/app/web` içine açar
  Neden zip: W: paylaşımı `.js` dosyası yazmayı engelliyor (EPERM), zip serbest.
  `BUILD.txt` hangi ai commit'inden derlendiğini söyler.
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "origin/ai"


def run(cmd, cwd=None, **kw):
    print("$", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], cwd=cwd, check=True, **kw)


def out(cmd, cwd=None) -> str:
    return subprocess.run([str(c) for c in cmd], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def find_npm_cli(node: Path) -> Path:
    for cand in (node.parent / "node_modules/npm/bin/npm-cli.js", node.parent.parent / "lib/node_modules/npm/bin/npm-cli.js"):
        if cand.exists():
            return cand
    sys.exit("npm-cli.js bulunamadı (Node.js kurulu mu?)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="/qa/app/", help="uygulamanın yayınlanacağı yol (varsayılan /qa/app/)")
    ap.add_argument("--no-fetch", action="store_true", help="git fetch yapma")
    args = ap.parse_args()
    base = "/" + args.base.strip("/") + "/"

    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local/share") / "kys-agent"
    src = local / "web-src"
    dist = local / "web-dist"
    pack = ROOT / "web-dist.zip"

    node = shutil.which("node")
    if not node:
        sys.exit("node bulunamadı")
    node = Path(node)
    npm_cli = find_npm_cli(node)

    if not args.no_fetch:
        run(["git", "fetch", "origin", "ai"], cwd=ROOT)
    commit = out(["git", "rev-parse", BRANCH], cwd=ROOT)

    local.mkdir(parents=True, exist_ok=True)
    if (src / ".git").exists():
        run(["git", "checkout", "--detach", "--force", commit], cwd=src)
        run(["git", "clean", "-fdq", "-e", "node_modules"], cwd=src)
    else:
        run(["git", "worktree", "prune"], cwd=ROOT)
        run(["git", "worktree", "add", "--detach", "--force", src, commit], cwd=ROOT)

    lock = "ci" if (src / "package-lock.json").exists() else "install"
    run([node, npm_cli, lock, "--no-audit", "--no-fund"], cwd=src)
    run([node, "node_modules/vite/bin/vite.js", "build", "--base", base, "--outDir", "dist", "--emptyOutDir"], cwd=src)

    if dist.exists():
        shutil.rmtree(dist)
    shutil.copytree(src / "dist", dist)
    subject = out(["git", "log", "-1", "--format=%s", commit], cwd=ROOT)
    (dist / "BUILD.txt").write_text(
        f"kaynak: {BRANCH}\ncommit: {commit}\nkonu: {subject}\nbase: {base}\n"
        f"derleme: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n", encoding="utf-8")
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(dist.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(dist).as_posix())
    print(f"Tamam: {dist} ve {pack} (ai {commit[:7]})")


if __name__ == "__main__":
    main()
