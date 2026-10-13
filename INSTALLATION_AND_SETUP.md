# CloudVault ODBC Website

CloudVault is a cloud-storage management website for the DBMS lab. The Flask front end connects to a local SQLite database through ODBC. It demonstrates user login, input validation, SQL retrieval, and insert, update, and delete operations.

## Architecture

```text
Browser → Flask website → pyodbc → Windows ODBC Driver Manager
        → SQLite ODBC driver → data/cloudvault.db
```

The website stores file metadata (name, type, size, and folder), not uploaded file contents.

## Install and configure ODBC

1. Use 64-bit Python and install a 64-bit SQLite ODBC driver. Driver information is available at [SQLite ODBC](https://github.com/softace/sqliteodbc).
2. Open **ODBC Data Sources (64-bit)** from the Windows Start menu.
3. Select **User DSN** → **Add**, choose the installed SQLite ODBC driver, and set:
   - **Data source name:** `CLOUDVAULT_SQLITE`
   - **Database:** the full path to this project's `data/cloudvault.db`
4. Save the DSN. Python, the ODBC driver, and ODBC Data Sources must all be 64-bit.

`pyodbc` is the Python ODBC package. Installing it does not install the ODBC driver or create the DSN.

## Install and run the website

Open Git Bash in the project folder (the folder containing `app.py`). Create and activate the virtual environment, then install the requirements:

```bash
py -3 -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

Start the site:

```bash
python app.py
```

Open <http://127.0.0.1:5000>. Stop the server with Ctrl+C. For later sessions, activate the environment and run `python app.py` again.

## Application workflow

1. On startup, Flask connects to the `CLOUDVAULT_SQLITE` DSN using `pyodbc`.
2. The application creates the tables from `schema.sql` and inserts sample rows from `seed.sql` when needed.
3. A user signs in or creates an account in the website.
4. The dashboard retrieves that user's folders, file records, and storage use with SQL `SELECT` statements.
5. Forms let the user create folders and file records, search, and delete records. Flask validates the inputs and uses parameterized SQL (`?` placeholders) for database operations.
6. Successful changes are committed; failed operations are rolled back and reported to the user.

## Tables and database operations

The schema follows the cloud storage management design:

- `PLANS`: storage quota and monthly price.
- `USERS`: account details and selected plan.
- `FOLDERS`: folders owned by each user.
- `FILES`: file metadata, linked to a folder and its owner by a foreign key.

`schema.sql` contains the DDL (`CREATE TABLE`, constraints, and index). `seed.sql` contains sample DML (`INSERT` and a demo-account `UPDATE`). The website performs parameterized `SELECT`, `INSERT`, and `DELETE` operations. Folder deletion is allowed only when it contains no file records. Account deletion removes the user's files, folders, and account in one transaction.

## Demo accounts

| Email | Password | Plan |
|---|---|---|
| aarav@example.com | cloud123 | Free |
| priya@example.com | secure123 | Pro |
| admin@example.com | team1234 | Business |

Users can also sign up and choose a plan.

## Check ODBC configuration

In the activated virtual environment, list the installed ODBC drivers and configured data sources:

```bash
python -c "import pyodbc; print(pyodbc.drivers()); print(pyodbc.dataSources())"
```

The output should include a SQLite driver and a `CLOUDVAULT_SQLITE` data source.

## Project files

| File or folder | Purpose |
|---|---|
| `app.py` | Flask website, validation, and ODBC database access |
| `requirements.txt` | Flask and `pyodbc` dependencies |
| `schema.sql` | Table and constraint definitions (DDL) |
| `seed.sql` | Sample plans, users, folders, and files (DML) |
| `data/cloudvault.db` | Local SQLite database selected by the DSN |
| `templates/`, `static/` | Website pages and styling |

## Troubleshooting

- **`No module named pyodbc`:** activate `.venv` and run `python -m pip install -r requirements.txt`.
- **Data source name not found (IM002):** install the SQLite ODBC driver, then create the `CLOUDVAULT_SQLITE` User DSN.
- **ODBC driver not found:** use a 64-bit driver with 64-bit Python and open ODBC Data Sources (64-bit).
- **Database file not found:** edit the DSN to use the full path to this project's `data/cloudvault.db`.
