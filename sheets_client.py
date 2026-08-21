from functools import lru_cache
import json
from pathlib import Path

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

from config import SPREADSHEET_ID, SERVICE_ACCOUNT_FILE

try:
    import streamlit as st
except Exception:
    st = None


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_secret_value(key):
    if st is None:
        return None

    try:
        return st.secrets.get(key)
    except Exception:
        return None


def get_spreadsheet_id():
    return get_secret_value("SPREADSHEET_ID") or SPREADSHEET_ID


def get_service_account_info_from_secrets():
    service_account = get_secret_value("gcp_service_account")

    if service_account:
        info = dict(service_account)

        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")

        return info

    raw_json = get_secret_value("GOOGLE_SERVICE_ACCOUNT_JSON")

    if raw_json:
        return json.loads(raw_json)

    return None


def get_credentials():
    service_account_info = get_service_account_info_from_secrets()

    if service_account_info:
        return Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )

    service_account_path = Path(SERVICE_ACCOUNT_FILE)

    if service_account_path.exists():
        return Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES,
        )

    raise FileNotFoundError(
        "Google service account credentials not found. "
        "Locally, create .secrets/google_service_account.json. "
        "On Streamlit Cloud, add gcp_service_account or GOOGLE_SERVICE_ACCOUNT_JSON "
        "to the app secrets."
    )


@lru_cache(maxsize=1)
def get_client():
    credentials = get_credentials()
    return gspread.authorize(credentials)


@lru_cache(maxsize=1)
def get_spreadsheet():
    client = get_client()
    return client.open_by_key(get_spreadsheet_id())


@lru_cache(maxsize=None)
def get_worksheet(tab_name):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(tab_name)


def read_sheet(tab_name):
    worksheet = get_worksheet(tab_name)
    rows = worksheet.get_all_records()
    return pd.DataFrame(rows)


def append_row(tab_name, row_values):
    worksheet = get_worksheet(tab_name)
    worksheet.append_row(row_values, value_input_option="USER_ENTERED")


def append_rows(tab_name, rows_values):
    if not rows_values:
        return

    worksheet = get_worksheet(tab_name)
    worksheet.append_rows(rows_values, value_input_option="USER_ENTERED")


def read_sheet_with_row_numbers(tab_name):
    worksheet = get_worksheet(tab_name)
    rows = worksheet.get_all_records()
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    # Google Sheets row 1 is the header.
    # Data rows start from row 2.
    df.insert(0, "_row_number", range(2, len(df) + 2))
    return df


def update_row_cells(tab_name, row_number, updates):
    worksheet = get_worksheet(tab_name)
    headers = worksheet.row_values(1)

    for column_name, value in updates.items():
        if column_name not in headers:
            raise ValueError(f"Column '{column_name}' not found in tab '{tab_name}'.")

        column_number = headers.index(column_name) + 1
        worksheet.update_cell(row_number, column_number, value)


def delete_row(tab_name, row_number):
    worksheet = get_worksheet(tab_name)
    worksheet.delete_rows(row_number)


def delete_rows(tab_name, row_numbers):
    if not row_numbers:
        return

    worksheet = get_worksheet(tab_name)

    clean_row_numbers = sorted(
        {int(row_number) for row_number in row_numbers},
        reverse=True
    )

    for row_number in clean_row_numbers:
        worksheet.delete_rows(row_number)
