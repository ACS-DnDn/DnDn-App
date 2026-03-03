# apps/worker

This package contains the **Worker (A-part)** code for DnDn.

## Local setup (Mac/Linux)

```bash
cd <repo-root>
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip

# install worker as editable package (avoids PYTHONPATH issues)
pip install -e apps/worker
```

Quick import check:

```bash
python -c "import dndn_worker; print('OK', dndn_worker.__file__)"
```
