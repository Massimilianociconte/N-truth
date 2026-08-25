# Verifica clean-checkout — 2026-08-23

Procedura: clone vergine del repository, ambiente sincronizzato con
`uv sync --extra dev --extra api --locked`, poi i gate documentati.

| Gate | Esito |
|---|---|
| `uv run ruff check .` | PASS |
| `uv run mypy packages` (207 file) | PASS, 0 errori |
| `uv run pytest --disable-warnings` | **3340 passed, 1 skipped** (2111 s) |
| `uv lock --check` | PASS |

Ambiente: macOS arm64 (Apple Silicon), Python 3.12, uv con lockfile firmato.
Commit verificato: `c65c695` (linea canonica, post-transizione pin 0.1.1).

Nota di scope (SRR-V8-028): questa registrazione prova la riproducibilità
del checkout su QUESTA piattaforma; non è un'attestazione hardware,
di accessibilità o di localizzazione per ambienti supportati diversi,
che restano di competenza dei rispettivi owner.
