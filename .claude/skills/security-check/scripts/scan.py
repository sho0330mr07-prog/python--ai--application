"""Streamlit + LLM アプリ向けの簡易セキュリティスキャン（標準ライブラリのみ）。

使い方: python3 scan.py <プロジェクトのルート>

結果は「手がかり」。誤検知を含むので、必ずコードを読んで確かめること。
秘密情報の値は先頭数文字だけを表示し、全体は出力しない。
"""

import ast
import json
import re
import sys
import tomllib
from pathlib import Path

SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules", "site-packages"}
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".whl"}
# 自分自身や評価用ワークスペースは対象外
SKIP_PARTS = {"security-check", "security-check-workspace"}

SECRET_PATTERNS = {
    "Google APIキー": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "OpenAI/Anthropic系キー": re.compile(r"sk-(?:ant-)?[A-Za-z0-9_\-]{20,}"),
    "GitHubトークン": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "AWSアクセスキー": re.compile(r"AKIA[0-9A-Z]{16}"),
    "秘密鍵": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
PLACEHOLDER = re.compile(r"your[-_]|example|xxx|placeholder|<.*>|\.\.\.", re.I)
SECRET_ENV_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.I)

DANGEROUS_CALLS = {
    "eval": "高", "exec": "高", "os.system": "高", "pickle.load": "高", "pickle.loads": "高",
    "yaml.load": "中", "subprocess.run": "中", "subprocess.Popen": "中", "subprocess.call": "中",
}

findings: list[dict] = []


def add(severity: str, category: str, location: str, message: str) -> None:
    findings.append({"severity": severity, "category": category, "location": location, "message": message})


def iter_files(root: Path):
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS or part in SKIP_PARTS for part in rel.parts):
            continue
        if p.is_file() and p.suffix not in SKIP_SUFFIXES and p.stat().st_size < 2_000_000:
            yield p, rel


def mask(value: str) -> str:
    return value[:6] + "…（省略）"


def scan_secrets(root: Path) -> None:
    for path, rel in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pat in SECRET_PATTERNS.items():
                for m in pat.finditer(line):
                    if PLACEHOLDER.search(m.group(0)):
                        continue
                    sev = "情報" if rel.name == ".env" else "高"
                    note = "（.env は .gitignore 済みなら通常問題なし）" if rel.name == ".env" else ""
                    add(sev, "秘密情報", f"{rel}:{lineno}", f"{name}らしき値: {mask(m.group(0))}{note}")


def scan_gitignore(root: Path) -> None:
    gi = root / ".gitignore"
    entries = gi.read_text().splitlines() if gi.exists() else []
    for target in [".env", ".streamlit/secrets.toml"]:
        if not any(e.strip().rstrip("/") in (target, f"/{target}", "*.env") for e in entries):
            add("中", "秘密情報", ".gitignore", f"{target} が .gitignore にない")
    if not (root / ".git").exists():
        add("情報", "秘密情報", ".", "gitリポジトリではない（git管理を始めるときは .gitignore を先に確認すること）")


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{call_name(node.value)}.{node.attr}"
    return ""


def mentions_secret_env(node: ast.AST) -> str | None:
    """式の中に os.getenv("..KEY..") / os.environ["..KEY.."] があれば変数名を返す。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and call_name(sub.func) in ("os.getenv", "os.environ.get", "getenv"):
            if sub.args and isinstance(sub.args[0], ast.Constant) and SECRET_ENV_NAME.search(str(sub.args[0].value)):
                return sub.args[0].value
        if isinstance(sub, ast.Subscript) and call_name(sub.value) == "os.environ":
            if isinstance(sub.slice, ast.Constant) and SECRET_ENV_NAME.search(str(sub.slice.value)):
                return sub.slice.value
    return None


def scan_python(root: Path) -> None:
    for path, rel in iter_files(root):
        # スキルのスクリプトはアプリのコードではないので scan_skills で別に扱う
        if path.suffix != ".py" or rel.parts[0] in (".claude", ".agents"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node.func)
            loc = f"{rel}:{node.lineno}"
            kwargs = {k.arg: k.value for k in node.keywords if k.arg}

            if name in DANGEROUS_CALLS:
                add(DANGEROUS_CALLS[name], "危険なAPI", loc, f"{name}() の使用。ユーザー入力やLLM出力が届くか確認")
            if "shell" in kwargs and isinstance(kwargs["shell"], ast.Constant) and kwargs["shell"].value is True:
                add("高", "危険なAPI", loc, "shell=True の使用")

            if name.startswith("st.") or name.startswith("streamlit."):
                widget = name.split(".")[-1]
                if "unsafe_allow_html" in kwargs and getattr(kwargs["unsafe_allow_html"], "value", None) is True:
                    add("高", "出力の描画", loc, f"{name}(unsafe_allow_html=True)。LLM出力やユーザー入力が入るとXSS")
                if widget in ("html", "components.html") or name.endswith("components.v1.html"):
                    add("中", "出力の描画", loc, f"{name}() でHTMLを直接描画している")
                if "value" in kwargs and (env := mentions_secret_env(kwargs["value"])):
                    add("高", "秘密情報", loc,
                        f"{name}(value=...) に環境変数 {env} を渡している。"
                        "type='password' でも値はブラウザに送られる")
                if widget == "file_uploader" and "type" not in kwargs:
                    add("低", "アップロード", loc, "file_uploader に type= の制限がない")
                if widget in ("markdown", "write", "write_stream"):
                    add("情報", "出力の描画", loc,
                        f"{name}()。LLM出力を表示しているなら、外部画像やリンクの扱いを確認")

            if name in ("print", "logging.info", "logging.debug", "logger.info", "logger.debug"):
                for arg in node.args:
                    if env := mentions_secret_env(arg):
                        add("中", "秘密情報", loc, f"{env} をログ/標準出力に出している可能性")


def scan_streamlit_config(root: Path) -> None:
    cfg = root / ".streamlit" / "config.toml"
    server = {}
    if cfg.exists():
        try:
            server = tomllib.loads(cfg.read_text()).get("server", {})
        except tomllib.TOMLDecodeError as e:
            add("低", "設定", str(cfg.relative_to(root)), f"config.toml を読めない: {e}")
    loc = ".streamlit/config.toml" if cfg.exists() else ".streamlit/config.toml（なし）"
    address = server.get("address")
    if address in (None, "", "0.0.0.0"):
        add("中", "ネットワーク", loc,
            "server.address が未設定または 0.0.0.0。全てのインターフェースで待ち受け、同じネットワークから接続できる")
    if server.get("enableXsrfProtection") is False:
        add("中", "設定", loc, "enableXsrfProtection = false")
    if server.get("enableCORS") is False:
        add("低", "設定", loc, "enableCORS = false")
    size = server.get("maxUploadSize", 200)
    if size >= 50:
        add("低", "アップロード", loc, f"maxUploadSize = {size}MB（既定200MB）。テキスト用途なら小さくできる")
    if (root / ".streamlit" / "secrets.toml").exists():
        add("情報", "秘密情報", ".streamlit/secrets.toml", "secrets.toml が存在する（.gitignore 済みか確認）")


def scan_requirements(root: Path) -> None:
    for req in list(root.glob("requirements*.txt")):
        unpinned = []
        for line in req.read_text().splitlines():
            line = line.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            if "==" not in line:
                unpinned.append(line)
        if unpinned:
            add("低", "依存パッケージ", req.name,
                f"バージョンが固定されていない: {', '.join(unpinned)}（再現性・サプライチェーン）")
    for lock in ("poetry.lock", "uv.lock", "requirements.lock", "Pipfile.lock"):
        if (root / lock).exists():
            add("情報", "依存パッケージ", lock, "ロックファイルあり")


def scan_skills(root: Path) -> None:
    lock = root / "skills-lock.json"
    if lock.exists():
        try:
            data = json.loads(lock.read_text())
            for name, info in data.get("skills", {}).items():
                add("情報", "サプライチェーン", "skills-lock.json",
                    f"外部スキル {name}（入手元: {info.get('source')}）。scripts/ の中身を確認")
        except json.JSONDecodeError:
            add("低", "サプライチェーン", "skills-lock.json", "JSONとして読めない")
    for base in (root / ".claude" / "skills", root / ".agents" / "skills"):
        if base.exists():
            for d in sorted(p for p in base.iterdir() if p.is_dir() and p.name not in SKIP_PARTS):
                scripts = [s for s in d.rglob("*") if s.suffix in (".py", ".sh", ".js")]
                if scripts:
                    add("情報", "サプライチェーン", str(d.relative_to(root)),
                        f"実行可能なスクリプト {len(scripts)} 件を含むスキル")


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    for scan in (scan_secrets, scan_gitignore, scan_python, scan_streamlit_config, scan_requirements, scan_skills):
        scan(root)

    order = {"高": 0, "中": 1, "低": 2, "情報": 3}
    findings.sort(key=lambda f: (order[f["severity"]], f["category"], f["location"]))
    print(f"# 自動スキャン結果: {root}\n")
    print(f"件数: " + ", ".join(f"{s} {sum(f['severity'] == s for f in findings)}" for s in order) + "\n")
    for f in findings:
        print(f"- [{f['severity']}] ({f['category']}) {f['location']} — {f['message']}")
    print("\n※ 手がかりです。誤検知を含むため、コードを読んで確かめてから採用してください。")


if __name__ == "__main__":
    main()
