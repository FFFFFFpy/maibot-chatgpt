"""Deterministic allowlist build. No credentials, configs, checkout, or tests are copied."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FOLDER = "maibot_chatgpt_provider_plugin"
FILES = (
    "plugin.py",
    "webui.json",
    "web/connection.html",
    "_manifest.json",
    "_locales/zh-CN.json",
    "pyproject.toml",
    "requirements.txt",
    "scripts/login.py",
    "scripts/package_plugin.py",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/docker.md",
    "docs/compatibility-report.md",
    *(
        "maibot_chatgpt_provider/" + n + ".py"
        for n in (
            "__init__",
            "adapter",
            "cli",
            "catalog_install",
            "credentials",
            "errors",
            "oauth",
            "oauth_constants",
            "model_probe",
            "page_login",
            "provider",
            "responses",
            "token_manager",
            "wire",
        )
    ),
)


def actual(url):
    u = urlsplit(url)
    if (
        u.scheme not in ("http", "https")
        or not u.hostname
        or u.username
        or u.password
        or u.query
        or u.fragment
        or any(c.isspace() for c in url)
    ):
        raise ValueError("不接受无效、含认证或查询参数的地址")
    return url


def build(output, preview, author, repo):
    if bool(author) != bool(repo) or (preview and (author or repo)):
        raise ValueError("选择 --preview，或者同时提供真实作者主页与项目仓库 URL")
    output.mkdir(parents=True, exist_ok=True)
    destination = output / (
        "maibot-chatgpt-provider-v0.4.0-web-login" + ("-preview" if preview else "") + ".zip"
    )
    entries = {name: (ROOT / name).read_bytes() for name in FILES}
    manifest = json.loads(entries["_manifest.json"])
    if author and repo:
        manifest["author"]["url"] = actual(author)
        manifest["urls"]["repository"] = actual(repo)
        entries["_manifest.json"] = (
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        ).encode()
    actual(manifest["author"]["url"])
    actual(manifest["urls"]["repository"])
    with tempfile.NamedTemporaryFile(dir=output, delete=False, suffix=".tmp") as temp:
        temp_path = Path(temp.name)
    try:
        with ZipFile(temp_path, "w") as archive:
            for name, data in sorted(entries.items()):
                info = ZipInfo(FOLDER + "/" + name, date_time=(2026, 11, 25, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                info.create_system = 3
                archive.writestr(info, data, compress_type=ZIP_DEFLATED)
        with ZipFile(temp_path) as archive:
            assert (
                set(archive.namelist()) == {FOLDER + "/" + p for p in FILES}
                and archive.testzip() is None
            )
        temp_path.replace(destination)
    finally:
        temp_path.unlink(missing_ok=True)
    print(
        destination.name,
        destination.stat().st_size,
        sha256(destination.read_bytes()).hexdigest(),
        sep="  ",
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="在归档中注入真实发布元数据，不改工作区 Manifest。构建不代表 Host 已验收。"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--author-url")
    parser.add_argument("--repository-url")
    args = parser.parse_args()
    try:
        build(args.output_dir, args.preview, args.author_url, args.repository_url)
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")
