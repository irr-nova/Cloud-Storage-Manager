# CloudVault ODBC Website

CloudVault is a Flask cloud-storage management website. It connects to its local SQLite database through ODBC using `pyodbc` and the Windows ODBC Driver Manager.

## Run

Before starting, install a 64-bit SQLite ODBC driver and create a 64-bit User DSN named `CLOUDVAULT_SQLITE` that points to `data/cloudvault.db`. See [INSTALLATION_AND_SETUP.md](INSTALLATION_AND_SETUP.md) for setup details.

From Git Bash in this folder:

```bash
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>. The app initializes the tables and sample data through ODBC. It stores file metadata, not file contents.
