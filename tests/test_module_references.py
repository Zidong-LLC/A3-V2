"""Lint de refactor (Fase 3.4): ningún módulo extraído referencia nombres sin definir
ni importar. Caza los NameError latentes que la suite no ejercita (p. ej. el
_ACCENT_TRANSLATION sin importar que detuvo la prueba en vivo del 2026-07-17)."""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
MODULES = ([APP / "menus.py", APP / "orders.py", APP / "flow.py", APP / "catalog.py",
            APP / "state.py", APP / "text.py", APP / "messages.py", APP / "laterales.py"]
           + sorted((APP / "detectors").glob("*.py"))
           + sorted((APP / "enforcers").glob("*.py")))


def _names(src: str):
    defined = set(re.findall(r"^(?:def |class )?(_?\w+)", src, re.M))
    defined |= set(re.findall(r"^\s+def (_?\w+)", src, re.M))   # funciones anidadas
    imported = set(re.findall(r"as (_?\w+)", src)) | set(re.findall(r"import (\w+)", src))
    for line in re.findall(r"from [\w.]+ import \(?([^)\n]+(?:\n[^)]+)*)\)?", src):
        for tok in re.split(r"[,\n]", line):
            tok = tok.strip().split(" as ")[-1].strip()
            if tok:
                imported.add(tok)
    return defined | imported


def test_no_unresolved_private_references():
    problems = {}
    for path in MODULES:
        if path.name == "__init__.py":
            continue
        src = path.read_text(encoding="utf-8")
        known = _names(src)
        consts = set(re.findall(r"\b(_[A-Z][A-Z_0-9]{2,})\b", src))
        calls = set(re.findall(r"\b(_[a-z]\w+)\(", src))
        missing = sorted(n for n in (consts | calls) if n not in known)
        if missing:
            problems[path.name] = missing
    assert not problems, f"referencias sin resolver: {problems}"
