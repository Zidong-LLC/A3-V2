"""Refresca el bloque automatico de tasks/errores-soluciones.md.

No modifica las secciones manuales del documento. Solo reemplaza el contenido entre
AUTO-GENERATED:START y AUTO-GENERATED:END con indices derivados de tasks/lessons.md
y tasks/todo.md.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "tasks" / "errores-soluciones.md"
LESSONS = ROOT / "tasks" / "lessons.md"
TODO = ROOT / "tasks" / "todo.md"

START = "<!-- AUTO-GENERATED:START -->"
END = "<!-- AUTO-GENERATED:END -->"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _headings(path: Path, pattern: str) -> list[str]:
    regex = re.compile(pattern)
    items: list[str] = []
    for line in _read(path).splitlines():
        match = regex.match(line.strip())
        if match:
            items.append(match.group(1).strip())
    return items


def _render_list(items: list[str], empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {item}" for item in items]


def _generated_block() -> str:
    lessons = _headings(LESSONS, r"^###\s+(L\d+\s+—\s+.+)$")
    tasks = _headings(TODO, r"^##\s+(.+)$")
    tasks = [item for item in tasks if item.lower() != "resultados"]

    lines = [
        START,
        "> Bloque generado con `python tools/scripts/refresh_error_report.py`.",
        "",
        "### Lecciones registradas",
        *_render_list(lessons, "No hay lecciones registradas."),
        "",
        "### Tareas registradas",
        *_render_list(tasks, "No hay tareas registradas."),
        END,
    ]
    return "\n".join(lines)


def refresh() -> None:
    text = _read(REPORT)
    if START not in text or END not in text:
        raise SystemExit(f"No encuentro marcadores automaticos en {REPORT}")

    start = text.index(START)
    end = text.index(END) + len(END)
    updated = text[:start] + _generated_block() + text[end:]
    REPORT.write_text(updated, encoding="utf-8")
    print(f"Actualizado {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    refresh()
