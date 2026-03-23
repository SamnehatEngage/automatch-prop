# AutoMatch Comparator

Public Streamlit app for comparing `properties/listings/auto-match` and `properties/listings/auto-match/v2` from the same API, matching the internal CMS comparator with a simplified public UI.

## Local run

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Fill in `.env` with your API settings.
4. Start the app:

```bash
streamlit run streamlit_app.py
```

## Environment variables

Store these values in `.env` for local development:

```bash
AUTO_MATCH_API_BASE_URL=https://api.cencorpcms.net
AUTO_MATCH_FRONTEND_BASE_URL=https://app.engageplatform.ai
AUTO_MATCH_BEARER_TOKEN=your_cms_jwt_bearer_token
AUTO_MATCH_DEFAULT_LIMIT=20
```

For Streamlit Community Cloud, add the same keys in the app Secrets settings instead of committing them to the repo.

The deployed app keeps these values behind the scenes and only exposes the reference listing ID or slug in the UI.

## Streamlit Community Cloud

- Main file path: `streamlit_app.py`
- Python dependencies: `requirements.txt`
- Secrets: add the env keys above in the Streamlit dashboard
