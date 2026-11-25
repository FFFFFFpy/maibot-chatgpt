import errno
import os
import stat
from types import SimpleNamespace

import pytest
from maibot_chatgpt_provider import credentials as cred
from maibot_chatgpt_provider.page_login import PageLogin
import asyncio

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "mode,owner,managed,success",
    [
        (0o755, 17, True, True),
        (0o750, 17, True, True),
        (0o755, 17, False, False),
        (0o777, 17, True, False),
        (0o755, 18, True, False),
    ],
)
def test_managed_mode_policy(monkeypatch, mode, owner, managed, success):
    # Simulate descriptor APIs on Windows too; never writes actual permissions here.
    info = SimpleNamespace(st_mode=stat.S_IFDIR | mode, st_uid=owner)
    changed = []
    closed = []
    path = SimpleNamespace(stat=lambda: info)

    def chmod(fd, new):
        changed.append((fd, new))
        info.st_mode = stat.S_IFDIR | new

    def open_dir(target, flags):
        assert target is path and flags == 3
        return 7

    monkeypatch.setattr(
        cred,
        "os",
        SimpleNamespace(
            name="posix",
            O_RDONLY=0,
            O_DIRECTORY=1,
            O_NOFOLLOW=2,
            open=open_dir,
            fstat=lambda fd: info,
            geteuid=lambda: 17,
            fchmod=chmod,
            close=closed.append,
        ),
    )
    if success:
        cred.protect_directory(path, managed)
    else:
        with pytest.raises(cred.StorageError):
            cred.protect_directory(path, managed)
    assert changed == ([(7, 0o700)] if success else []) and closed == (
        [7] if managed else []
    )


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX inode permissions")
def test_real_precreated_runner_dir(tmp_path):
    target = tmp_path / "plugin"
    target.mkdir()
    target.chmod(0o755)
    before = tmp_path.stat().st_mode
    store = cred.Store(target, runner_owned=True)
    uid, _ = store.begin()
    assert uid == store.begin()[0] and stat.S_IMODE(target.stat().st_mode) == 0o700
    assert (
        tmp_path.stat().st_mode == before
        and stat.S_IMODE((target / "host_identity.json").stat().st_mode) == 0o600
    )


@pytest.mark.parametrize(
    "number,word",
    [(errno.EROFS, "只读"), (errno.EACCES, "UID"), (errno.ENOSPC, "空间")],
)
def test_storage_error_reason(number, word):
    err = cred.storage_io(OSError(number, "synthetic-private-value"))
    assert (
        word in str(err)
        and "synthetic-private-value" not in str(err)
        and err.exit_code == 7
    )


def test_broken_store_status_is_actionable(tmp_path):
    s = cred.Store(tmp_path)
    s.path.write_bytes(b"{broken")
    s.path.chmod(0o600)
    page = PageLogin(SimpleNamespace(store=s))
    result = asyncio.run(page.status())
    assert (
        result["session"] == "unreadable"
        and "损坏" in result["problem"]
        and "broken" not in str(result)
    )
