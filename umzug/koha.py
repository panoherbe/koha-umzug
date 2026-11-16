"""Access to a Koha installation: SQL through `koha-mysql`, shell through `koha-shell`, files by copy.

Only Python's standard library is needed, so the check tools need no extra software. Measured in the test container;
on a library's server the same commands are given as --sql/--shell (paths and rights are set in the analysis):

    in a test container (measured):  --container kohaumzug-koha-1 --instanz kohadev
    on a Koha server:                --sql "sudo koha-mysql <instanz>"  --shell "sudo koha-shell <instanz> -c"

SQL results come back as rows of strings (mysql --batch). Nothing here writes unless a caller sends a write statement.
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _unescape(feld: str) -> str | None:
    if feld == "NULL":
        return None
    out, i = [], 0
    while i < len(feld):
        c = feld[i]
        if c == "\\" and i + 1 < len(feld):
            n = feld[i + 1]
            out.append({"n": "\n", "t": "\t", "0": "\0", "\\": "\\"}.get(n, n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


@dataclass
class Koha:
    instanz: str = "kohadev"
    container: str | None = None          # docker container that runs Koha (test environment)
    sql_befehl: str | None = None         # e.g. "sudo koha-mysql kohadev" on a server
    shell_befehl: str | None = None       # e.g. "sudo koha-shell kohadev -c"

    def _sql_argv(self) -> list[str]:
        if self.sql_befehl:
            return shlex.split(self.sql_befehl) + ["--batch", "-N"]
        if self.container:
            return ["docker", "exec", "-i", self.container, "koha-mysql", self.instanz, "--batch", "-N"]
        return ["koha-mysql", self.instanz, "--batch", "-N"]

    def sql(self, anweisung: str) -> list[list[str | None]]:
        r = subprocess.run(self._sql_argv(), input=anweisung.encode("utf-8"), capture_output=True, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"SQL fehlgeschlagen ({r.returncode}): {r.stderr.decode('utf-8', 'replace')[:500]}")
        zeilen = r.stdout.decode("utf-8").split("\n")
        return [[_unescape(f) for f in z.split("\t")] for z in zeilen if z != ""]

    def wert(self, anweisung: str) -> str | None:
        z = self.sql(anweisung)
        return z[0][0] if z and z[0] else None

    def shell(self, befehl: str, als_root: bool = False) -> str:
        if self.shell_befehl:
            argv = shlex.split(self.shell_befehl) + [befehl]
        elif self.container:
            argv = (["docker", "exec", self.container, "bash", "-lc", befehl] if als_root else
                    ["docker", "exec", self.container, "koha-shell", self.instanz, "-c", befehl])
        else:
            argv = ["koha-shell", self.instanz, "-c", befehl]
        r = subprocess.run(argv, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"{befehl[:80]} … fehlgeschlagen: {r.stderr[-800:]}")
        return r.stdout

    def kopieren(self, quelle: Path, ziel: str) -> None:
        """Copy a local file or folder into the Koha environment (test container) or to a local path (server)."""
        if self.container:
            subprocess.run(["docker", "cp", str(quelle), f"{self.container}:{ziel}"], check=True,
                           capture_output=True)
        else:
            subprocess.run(["cp", "-r", str(quelle), ziel], check=True)


def sql_text(wert: object) -> str:
    """A value as SQL literal (strings quoted and escaped, None as NULL)."""
    if wert is None:
        return "NULL"
    if isinstance(wert, (int, float)):
        return str(wert)
    s = str(wert).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"
