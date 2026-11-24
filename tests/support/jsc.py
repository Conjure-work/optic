"""Where the JavaScriptCore shell is, on macOS and on Linux (2026-11-24).

About two hundred test files run the front end's modules in JavaScriptCore. They used to name the macOS framework's
copy directly, which tied the suite to macOS runners. This is the one place that finds the shell now:

1. the `JSC` environment variable, if set (a path, or a name on PATH);
2. the macOS framework's copy, if present;
3. on PATH: `jsc` (Ubuntu and Debian's libjavascriptcoregtk-bin installs /usr/bin/jsc), then the versioned names
   some distributions use.

`JSC` is the path found, or "" when there is none; the tests skip on "" (a falsy value), and the workflow's count job
fails on any skip, so CI can never pass without the shell.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

MACOS = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"
NAMES = ("jsc", "jsc-6.0", "jsc-4.1", "jsc-4.0")


def find() -> str:
    env = os.environ.get("JSC")
    if env:
        return shutil.which(env) or ""
    if os.access(MACOS, os.X_OK):
        return MACOS
    for name in NAMES:
        found = shutil.which(name)
        if found:
            return found
    return ""


JSC = find()


def run_e(exe: str, source: str, **kwargs) -> subprocess.CompletedProcess:
    """What `subprocess.run([exe, "-e", source], **kwargs)` did, with the source in a file instead of an argument.

    Linux caps a single argument at 128 KiB (MAX_ARG_STRLEN) and macOS does not, so the tests that hand JavaScriptCore
    all of static/charts.js on the command line ran on the Mac and failed on Ubuntu with "Argument list too long"
    (44 tests in eleven files on 2026-11-24). A script file is evaluated the same way `-e` evaluates its string.
    """
    fd, path = tempfile.mkstemp(suffix=".js", prefix="jsc-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(source)
        return subprocess.run([exe, path], **kwargs)
    finally:
        os.unlink(path)


if __name__ == "__main__":
    print(JSC or "no JavaScriptCore shell found")
