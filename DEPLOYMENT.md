# Streamlit Community Cloud Deployment

## 1. Push Code To GitHub

Create a GitHub repository for this project and push the app files.

Do not commit:

- `.secrets/`
- `.venv/`
- `__pycache__/`

These are already ignored in `.gitignore`.

## 2. Deploy On Streamlit Community Cloud

1. Go to `https://share.streamlit.io`.
2. Click **Create app**.
3. Select your GitHub repository.
4. Set the main file path to `app.py`.
5. Open **Advanced settings**.
6. Paste your secrets using the structure in `.streamlit/secrets.example.toml`.
7. Deploy.

## 3. Verify

- Dashboard loads.
- Google Sheets data appears.
- Transactions page shows expenses.
- A web-app transaction writes to Google Sheets.
- A Telegram transaction appears after refresh.
