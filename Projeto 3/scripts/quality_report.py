#!/usr/bin/env python3
"""Gera docs/RESULTADOS_EXECUCAO.md a partir dos relatórios REAIS das suítes.

Entradas (geradas pelos próprios testes; veja `make test`):
  backend/reports/junit.xml        (pytest --junitxml)
  backend/reports/coverage.xml     (pytest --cov-report=xml)
  frontend/reports/junit.xml       (vitest --reporter=junit)
  frontend/coverage/coverage-summary.json

Nada é estimado: se um arquivo não existe, a suíte aparece como "não executada".
Uso:  python3 scripts/quality_report.py [--strict]
  --strict  sai com código 1 se houver falhas ou suíte não executada (útil no CI).
"""
import argparse
import json
import platform
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_junit(path: Path) -> list[dict]:
    cases = []
    for tc in ET.parse(path).getroot().iter("testcase"):
        status, message = "passed", ""
        for child in tc:
            if child.tag in ("failure", "error"):
                status = "failed"
                message = (child.get("message") or child.text or "").strip().splitlines()[0:1]
                message = message[0] if message else ""
            elif child.tag == "skipped":
                status, message = "skipped", child.get("message") or ""
        cases.append(
            {
                "classname": tc.get("classname") or "",
                "name": tc.get("name") or "",
                "time": float(tc.get("time") or 0),
                "status": status,
                "message": message,
            }
        )
    return cases


def group_key(classname: str) -> str:
    parts = classname.split(".")
    if parts[0] == "tests" and len(parts) >= 3:  # pytest: tests.integration.test_auth.TestLogin
        return ".".join(parts[:3])
    return classname or "(sem nome)"  # vitest: caminho do arquivo


def totals(cases: list[dict]) -> dict:
    return {
        "total": len(cases),
        "passed": sum(c["status"] == "passed" for c in cases),
        "failed": sum(c["status"] == "failed" for c in cases),
        "skipped": sum(c["status"] == "skipped" for c in cases),
        "time": sum(c["time"] for c in cases),
    }


def verdict(t: dict | None) -> str:
    if t is None:
        return "⚠️ não executada"
    if t["total"] == 0:
        return "⚠️ nenhum teste coletado"
    if t["failed"]:
        return "❌ reprovada"
    if t["skipped"] == t["total"]:
        return "⚠️ todos ignorados"
    return "✅ aprovada" + (" (com ignorados)" if t["skipped"] else "")


def pct(value: float) -> str:
    return f"{value:.1f}%"


def backend_coverage(path: Path) -> dict | None:
    if not path.exists():
        return None
    root = ET.parse(path).getroot()
    files = []
    for cls in root.iter("class"):
        rate = cls.get("line-rate")
        if rate is not None:
            files.append((cls.get("filename", "?"), float(rate) * 100))
    return {"lines": float(root.get("line-rate", 0)) * 100, "branches": float(root.get("branch-rate", 0)) * 100, "files": files}


def frontend_coverage(path: Path) -> dict | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    total = data["total"]
    files = [(name, info["lines"]["pct"]) for name, info in data.items() if name != "total"]
    return {
        "lines": total["lines"]["pct"],
        "branches": total["branches"]["pct"],
        "functions": total["functions"]["pct"],
        "statements": total["statements"]["pct"],
        "files": files,
    }


def suite_section(title: str, cases: list[dict] | None, source: str) -> list[str]:
    out = [f"### {title}", ""]
    if cases is None:
        return out + [f"Não executada: `{source}` não encontrado.", ""]
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        groups[group_key(c["classname"])].append(c)
    out += ["| Arquivo | Testes | Passaram | Falharam | Ignorados | Tempo (s) |", "|---|---:|---:|---:|---:|---:|"]
    for key in sorted(groups):
        t = totals(groups[key])
        out.append(f"| `{key}` | {t['total']} | {t['passed']} | {t['failed']} | {t['skipped']} | {t['time']:.2f} |")
    failures = [c for c in cases if c["status"] == "failed"]
    if failures:
        out += ["", "**Falhas:**", ""]
        out += [f"- `{c['classname']}::{c['name']}` — {c['message'][:200]}" for c in failures]
    skipped = [c for c in cases if c["status"] == "skipped"]
    if skipped:
        reasons = sorted({c["message"] for c in skipped if c["message"]})
        out += ["", f"**Ignorados:** {len(skipped)}" + (f" — motivo: {'; '.join(reasons)[:300]}" if reasons else "")]
    return out + [""]


def coverage_section(title: str, cov: dict | None, source: str, keys: list[tuple[str, str]]) -> list[str]:
    out = [f"### {title}", ""]
    if cov is None:
        return out + [f"Sem dados: `{source}` não encontrado.", ""]
    out += ["| Métrica | Cobertura |", "|---|---:|"] + [f"| {label} | {pct(cov[k])} |" for k, label in keys]
    lowest = sorted(cov["files"], key=lambda f: f[1])[:5]
    if lowest:
        out += ["", "Arquivos com menor cobertura de linhas:", ""] + [f"- `{Path(name).as_posix()}` — {pct(p)}" for name, p in lowest]
    return out + [""]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend-junit", type=Path, default=ROOT / "backend/reports/junit.xml")
    parser.add_argument("--backend-coverage", type=Path, default=ROOT / "backend/reports/coverage.xml")
    parser.add_argument("--frontend-junit", type=Path, default=ROOT / "frontend/reports/junit.xml")
    parser.add_argument("--frontend-coverage", type=Path, default=ROOT / "frontend/coverage/coverage-summary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/RESULTADOS_EXECUCAO.md")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    backend = parse_junit(args.backend_junit) if args.backend_junit.exists() else None
    frontend = parse_junit(args.frontend_junit) if args.frontend_junit.exists() else None
    tb = totals(backend) if backend is not None else None
    tf = totals(frontend) if frontend is not None else None

    lines = [
        "# Resultados da execução dos testes",
        "",
        f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} por `scripts/quality_report.py` "
        f"(Python {platform.python_version()}, {platform.system()}).",
        "Os números vêm dos relatórios reais das suítes; nada é estimado.",
        "",
        "## Resumo",
        "",
        "| Suíte | Veredito | Testes | Passaram | Falharam | Ignorados | Tempo (s) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for name, t in (("Backend (pytest)", tb), ("Frontend (Vitest)", tf)):
        if t is None:
            lines.append(f"| {name} | {verdict(t)} | — | — | — | — | — |")
        else:
            lines.append(f"| {name} | {verdict(t)} | {t['total']} | {t['passed']} | {t['failed']} | {t['skipped']} | {t['time']:.1f} |")
    if tb and tb["skipped"]:
        lines += ["", "> Atenção: há testes ignorados no backend. Os de integração só rodam com `TEST_DATABASE_URL` definida."]

    lines += ["", "## Detalhamento", ""]
    lines += suite_section("Backend", backend, str(args.backend_junit.relative_to(ROOT)) if args.backend_junit.is_relative_to(ROOT) else str(args.backend_junit))
    lines += suite_section("Frontend", frontend, str(args.frontend_junit.relative_to(ROOT)) if args.frontend_junit.is_relative_to(ROOT) else str(args.frontend_junit))

    lines += ["## Cobertura de código", ""]
    lines += coverage_section("Backend", backend_coverage(args.backend_coverage), "backend/reports/coverage.xml", [("lines", "Linhas"), ("branches", "Ramificações")])
    lines += coverage_section(
        "Frontend", frontend_coverage(args.frontend_coverage), "frontend/coverage/coverage-summary.json",
        [("lines", "Linhas"), ("statements", "Instruções"), ("functions", "Funções"), ("branches", "Ramificações")],
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Relatório gravado em {args.output}")

    problems = any(t is None or t["failed"] or t["total"] == 0 for t in (tb, tf))
    return 1 if (args.strict and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
