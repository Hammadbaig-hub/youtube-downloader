# How to Set Up Google OAuth for VidFlow

## Step 1 — Google Cloud Console

1. Go to: https://console.cloud.google.com
2. Click the project dropdown at the top → **New Project**
3. Name it `VidFlow`, click **Create**
4. Make sure `VidFlow` is selected in the dropdown

---

## Step 2 — Configure OAuth Consent Screen

1. In the left sidebar go to **APIs & Services → OAuth consent screen**
2. Select **External** → click **Create**
3. Fill in:
   - **App name**: `VidFlow`
   - **User support email**: your email
   - **Developer contact email**: your email
4. Click **Save and Continue** through all steps (scopes, test users)
5. Click **Back to Dashboard**

---

## Step 3 — Create OAuth Credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth Client ID**
3. Set **Application type**: `Web application`
4. Set **Name**: `VidFlow`
5. Under **Authorized redirect URIs**, click **+ Add URI** and add:
   ```
   http://localhost:5000/auth/google/callback
   ```
6. Click **Create**
7. A popup shows your **Client ID** and **Client Secret** — copy both

---

## Step 4 — Add Credentials to .env

Open the `.env` file in the project root and fill in:

```env
GOOGLE_CLIENT_ID=paste_your_client_id_here
GOOGLE_CLIENT_SECRET=paste_your_client_secret_here
SECRET_KEY=generate_a_long_random_string_here
DATABASE_URL=sqlite:///vidflow.db
```

To generate a strong `SECRET_KEY`, run this in your terminal:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 5 — Install Dependencies & Run

```bash
pip install -r requirements.txt
python app.py
```

Then open: http://localhost:5000

---

## Step 6 — Test OAuth Flow

1. Click **Sign In** in the navbar
2. Click **Continue with Google**
3. Choose your Google account
4. You should be redirected back to VidFlow, logged in

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `redirect_uri_mismatch` error | Make sure the callback URL in Google Console matches exactly: `http://localhost:5000/auth/google/callback` |
| `invalid_client` error | Double-check `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` |
| Database errors | Delete `vidflow.db` and restart the app — it will be recreated |
| `SECRET_KEY` warning | Make sure `SECRET_KEY` in `.env` is a long random string, not the placeholder |

---

## Production Deployment

When deploying to a public domain (e.g. `https://vidflow.example.com`):

1. Add the production callback URI in Google Console:
   ```
   https://vidflow.example.com/auth/google/callback
   ```
2. Update `DATABASE_URL` in `.env` to a production database (PostgreSQL recommended)
3. Never commit `.env` — it is already in `.gitignore`
