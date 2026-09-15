# Northstar Workspace

Internal helper service used by the office tools team.

The service exposes a small HTTP API for:

- downloading workspace files
- reading published documents
- fetching integration payloads
- previewing webhook endpoints
- rendering report title previews

This is a development snapshot, not a production deployment.

## Layout

```text
app/
    main.py
    config.py
    routes/
    services/
    common/
tests/
```

## Run

```bash
pip install -r requirements.txt
python -m app.main
```

The default listener is `127.0.0.1:5000`.

## Tests

```bash
python -m unittest discover -s tests -v
```
