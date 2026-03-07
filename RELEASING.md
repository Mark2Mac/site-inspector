# Releasing Site Inspector

## Local release checklist

1. Run the full local suite:

```powershell
.\run_tests.ps1 -All
```

2. Build the package:

```powershell
py -m build --sdist --wheel --outdir .site_inspector_local\dist
```

3. Validate artifacts:

```powershell
py -m twine check .site_inspector_local\dist\*
```

4. Confirm that no local artifacts leaked into the build:
- `.site_inspector_local/`
- `runs/`
- `diffs/`
- temporary caches

5. Confirm versioning and docs are aligned:
- `pyproject.toml`
- `site_inspector/__init__.py`
- `CHANGELOG.md`
- `README.md`

## Notes

This checklist is intentionally local-first. Publishing should only happen after the production hardening iterations are complete.
