# Google OAuth Setup

VidFlow uses Google OAuth 2.0 for user sign-in. Follow these steps to configure it.

## 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Give it a name (e.g., `VidFlow`) and click **Create**

## 2. Enable the Google+ API (People API)

1. In your project, go to **APIs & Services** → **Library**
2. Search for **Google People API** and click **Enable**

## 3. Configure the OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** (for personal use) or **Internal** (for Workspace orgs)
3. Fill in:
   - **App name**: VidFlow
   - **User support email**: your email
   - **Developer contact**: your email
4. Under **Scopes**, add:
   - `openid`
   - `email`
   - `profile`
5. Add test users if using External + Testing mode
6. Click **Save and Continue** through all steps

## 4. Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Select **Web application**
4. Set **Authorized redirect URIs**:
   - Development: `http://localhost:5000/auth/google/callback`
   - Production: `https://yourdomain.com/auth/google/callback`
5. Click **Create**
6. Copy the **Client ID** and **Client Secret**

## 5. Configure VidFlow

Create a `.env` file in the project root:

```env
SECRET_KEY=your-random-secret-key-here
GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-secret-here
```

Or set them as environment variables directly.

## 6. Test the Login

Start the server (`python run.py`) and navigate to `/login`. The **Continue with Google** button should initiate the OAuth flow.

## Troubleshooting

| Error | Fix |
|---|---|
| `redirect_uri_mismatch` | Ensure the callback URL in Google Console exactly matches your running URL |
| `access_blocked` | App is in Testing mode — add your Google account as a test user |
| `invalid_client` | Double-check `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` values |
