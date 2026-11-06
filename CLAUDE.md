# CLAUDE.md

Con Ed residential rate calculator (`conedrates`): prices a customer's interval
usage under four plans (SC 1 Rates I, III, IV and Rider Z Rate I). This repository
is public.

## Start here
- Read `SPEC.md` before changing anything. It is the source of truth for rules,
  data formats, validation results and open items. Update it in the same branch
  as any change to behavior or data.
- Work on one task per conversation. Put what a later conversation needs into
  SPEC.md (project facts) or this file (how to work), not into chat history.

## Commands
- Run the CLI: `python -m conedrates --usage usage.csv --msc LDS_APPND.csv`
- Run the tests: `python3 -m unittest discover -s tests -t .`
- Strict run: `python3 -X dev -W error::ResourceWarning -m unittest discover -s tests -t .`
- Tests that need private files skip when the files are absent.

## Conventions
- Python with pandas. Standard library `unittest`; no extra test framework.
- Inputs that change over time are data (`data/tariff.toml`, `data/statements.toml`,
  the MSC file, the usage export). Rules are code. Rate changes add dated entries;
  never edit old entries. See "Refreshing the data" in SPEC.md.
- Cite the tariff by Leaf number (stable), not PDF page. Cite statements by number.
- Mark anything not verified against the tariff or a bill as an assumption: in the
  code, in the output diagnostics and in SPEC.md. Do not present guesses as facts.
- Report results faithfully: say when tests fail or a step was skipped.

## Git
- One branch per task, branched from `main`. Commit only when asked.
- Run the tests before every commit.
- Do not push or rewrite history without being asked.
- Read a diff before committing it, and check untracked files for personal data.

## Privacy (the repo is public)
- Never commit or print usage exports, bills, account numbers, names or addresses.
  Private files are gitignored: `usage.csv`, `LDS_APPND.csv`, `filtered.csv`,
  `bills.csv`, `bills/`, `statements/`, `electric-tariff.pdf`, `*.json` (except
  `data/*.json`), `old/`, `.claude/`, `CLAUDE.local.md`, and editor backup files.
- Tests and examples use invented data only.
- Keep the repository's docs about the project. Personal notes go in
  `CLAUDE.local.md`, which is gitignored.

## Verifying
- Check claims against the files before stating them: the code, the data, the
  tariff text. Correct earlier statements when they turn out wrong.
