from __future__ import annotations

import errno
import hashlib
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import DeviceUnavailableError


def default_lock_directory() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        candidate = Path(runtime)
        try:
            info = candidate.lstat()
            owner_ok = not hasattr(os, "getuid") or info.st_uid == os.getuid()
            private = not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            if stat.S_ISDIR(info.st_mode) and owner_ok and private:
                return candidate / "host-slot-switch"
        except OSError:
            pass
    return Path.home() / ".cache" / "host-slot-switch" / "locks"


@contextmanager
def switch_lock(device: str, *, directory: Path | None = None) -> Iterator[None]:
    """Prevent repeated hotkeys from launching concurrent Solaar commands."""
    directory = directory or default_lock_directory()
    fd: int | None = None
    try:
        existed = directory.exists()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise OSError(f"lock path is not a directory: {directory}")
        if os.name == "posix":
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise OSError(f"lock directory is owned by another user: {directory}")
            if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise OSError(f"lock directory is group/world writable: {directory}")
        if os.name == "posix" and not existed:
            directory.chmod(0o700)
        digest = hashlib.sha256(device.casefold().encode("utf-8")).hexdigest()[:24]
        path = directory / f"{digest}.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        if os.name == "posix":
            os.fchmod(fd, 0o600)
    except OSError as exc:
        if fd is not None:
            os.close(fd)
        raise DeviceUnavailableError(f"Cannot create the switch lock: {exc}") from exc

    try:
        release: Callable[[], None] | None = None
        try:
            release = _acquire_platform_lock(fd)
        except BlockingIOError as exc:
            raise DeviceUnavailableError(
                "Another switch command is already in progress; this key press was ignored."
            ) from exc
        except OSError as exc:
            raise DeviceUnavailableError(
                f"Cannot acquire the switch lock: {exc}"
            ) from exc
        yield
    finally:
        if release is not None:
            try:
                release()
            except OSError:
                pass
        os.close(fd)


def _acquire_platform_lock(fd: int) -> Callable[[], None]:
    if os.name == "nt":
        import msvcrt

        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise BlockingIOError from exc
            raise

        def release() -> None:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

        return release

    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def release() -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)

    return release
