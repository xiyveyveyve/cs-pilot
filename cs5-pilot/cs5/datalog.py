"""CORRW ASCII 数据文件（CS Studio 的 .cor）读写。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MAGIC = "CORRW ASCII"


@dataclass
class CorPoint:
    e: float
    i: float
    t: float


@dataclass
class CorFile:
    method: str = "ID_GalStatic"
    serial: str = ""
    soft_version: str = "5.6.1202.2"
    boot_version: str = ""
    summary: str = ""
    ocp: float = 0.0
    temperature: float = 0.0
    started: datetime | None = None
    finished: datetime | None = None
    points: list[CorPoint] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines: list[str] = [MAGIC]
        ver = f"CorrTest for Windows: SN {self.serial} V{self.soft_version}"
        if self.boot_version:
            ver += f" V{self.boot_version}"
        lines.append(ver)
        lines.append(self.method)
        start = self.started or datetime.now()
        lines.append(f"Data: {start:%Y-%m-%d}")
        lines.append(f"Time: {start:%H:%M:%S}")
        if self.summary:
            lines.append(self.summary)
        lines.append(f"Open Circuit Potential (V): {self.ocp:.4f}")
        lines.append(f"Temperature (C): {self.temperature:.1f}")
        lines.append("Begin Information")
        if self.started:
            lines.append(f"Begin Time: {self.started:%Y-%m-%d %H:%M:%S}")
        if self.finished:
            lines.append(f"End Time: {self.finished:%Y-%m-%d %H:%M:%S}")
        lines.append("End Information")
        lines.append("E(V)\ti(A/cm^2)\tT(s)")
        for p in self.points:
            lines.append(f"{p.e:.6f}\t{p.i:.6e}\t{p.t:.3f}")
        lines.append("End Comments")
        for c in self.comments:
            lines.append(c)
        return "\n".join(lines) + "\n"

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.render(), encoding="utf-8", newline="\n")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "CorFile":
        raw = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        if not raw or raw[0].strip() != MAGIC:
            raise ValueError(f"not a CORRW ASCII file: {path}")
        cf = cls()
        i = 1
        n = len(raw)
        while i < n:
            line = raw[i]
            if line.startswith("CorrTest for Windows:"):
                parts = line.split()
                for k, tok in enumerate(parts):
                    if tok == "SN" and k + 1 < len(parts):
                        cf.serial = parts[k + 1]
                cf.soft_version = next((t[1:] for t in parts if t.startswith("V")), "")
            elif line.startswith("ID_"):
                cf.method = line.strip()
            elif line.startswith("Open Circuit Potential"):
                cf.ocp = _tail_float(line)
            elif line.startswith("Temperature"):
                cf.temperature = _tail_float(line)
            elif line.startswith("The polarization") or line.startswith("Init Current"):
                cf.summary = line.strip()
            elif line.startswith("E(V)"):
                i += 1
                break
            i += 1
        while i < n:
            line = raw[i].strip()
            if not line or line.startswith("End Comments"):
                break
            cols = line.split("\t") if "\t" in line else line.split()
            if len(cols) >= 3:
                try:
                    cf.points.append(CorPoint(float(cols[0]), float(cols[1]), float(cols[2])))
                except ValueError:
                    pass
            i += 1
        return cf


def _tail_float(line: str) -> float:
    tok = line.split(":")[-1].strip().split()[0] if ":" in line else ""
    try:
        return float(tok)
    except ValueError:
        return 0.0