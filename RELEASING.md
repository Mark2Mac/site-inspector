# Releasing Site Inspector

This project is Windows-first and should only be released after the full local regression suite is green.

## Release checklist

1. Update version in `site_inspector/__init__.py` and `pyproject.toml`.
2. Update `CHANGELOG.md`.
3. Run:
   - `py -m pytest -q`
   - `.\run_tests.ps1 -All`
4. Build release artifacts:
   - `py -m build --sdist --wheel --outdir .site_inspector_local\dist`
5. Validate package metadata:
   - `py -m twine check .site_inspector_local\dist\*`
6. Smoke-check the module entrypoint:
   - `py -m site_inspector --version`
7. Tag the release and publish through your chosen channel.

## Notes

- Local artifacts are intentionally kept under `.site_inspector_local/`.
- The legacy `site_audit.py` script remains supported for local development.
- Public release should prefer the package entrypoint (`site-inspector` / `python -m site_inspector`).
