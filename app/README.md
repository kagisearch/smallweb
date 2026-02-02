## Run the App

### Requirements

Python 3.X

```bash
pip install -r app/requirements.txt
```

## On Linux

### Running

To run anything that runs a Flask app, for example
```bash
cd app
gunicorn --workers 1 --threads 4 sw:app
```

## On Windows

```bash
cd app
waitress-serve --host=127.0.0.1 --port=8000 sw:app
```
# Take note on windows⚠️
### From
```python
with open("myfile.txt", "r") as f:
    data = f.read()
```
## to

###
```python
with open("myfile.txt", "r", encoding="utf-8") as f:
    data = f.read()
```

This will run the Small Web frontend app locally.

Open http://127.0.0.1:8000 in browser to access.
