"""Punto de entrada: `python -m gabinete_evals` (ver cli.py). Con PYTHONPATH="packages/harness;packages/evals"."""
import sys

try:
    from gabinete_evals.cli import main
except ModuleNotFoundError as exc:  # lo más común: se olvidó PYTHONPATH (o falta PyYAML)
    if (exc.name or "").split(".")[0] not in ("gabinete_harness", "yaml"):
        raise
    print(
        f"error: no se encuentra el módulo {exc.name!r}. Define PYTHONPATH con las dos carpetas del repo, por ejemplo en "
        'PowerShell: $env:PYTHONPATH = "packages/harness;packages/evals" (y pip install pyyaml si falta PyYAML).',
        file=sys.stderr,
    )
    raise SystemExit(2) from None

if __name__ == "__main__":
    raise SystemExit(main())
