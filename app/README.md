## Run the App

### Requirements

Python 3.X

```bash
pip install -i app/requirements.txt
```

### Running

To run anything that runs a Flask app, for example
```bash
cd app
gunicorn --workers 1 --threads 4 sw:app
```

This will run the Small Web frontend app locally.

Open http://127.0.0.1:8000 in browser to access.
