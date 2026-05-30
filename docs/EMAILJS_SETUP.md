# EmailJS setup for FrontierOS early-access emails

Use this when your API runs on **Render free tier** (SMTP blocked). The landing page saves signups on the server, then sends the access code email **from the browser** via EmailJS over HTTPS.

**Flow:** User submits form → `POST /api/waitlist` (saves signup + code) → **EmailJS sends the code** to `{{to_email}}` when configured (primary on GitHub Pages).

---

## 1. Create an EmailJS account

1. Go to [https://www.emailjs.com](https://www.emailjs.com) and sign up.
2. Confirm your email if prompted.

---

## 2. Connect Gmail (email service)

1. Dashboard → **Email Services** → **Add New Service**.
2. Choose **Gmail** (or Google Workspace).
3. Connect the account you want to send from (e.g. `tsingh98@umd.edu`).
4. After saving, copy the **Service ID** (looks like `service_xxxxxxx`).

---

## 3. Create the email template

1. Dashboard → **Email Templates** → **Create New Template**.
2. Set these fields:

| Field | Value |
|--------|--------|
| **Name** | `FrontierOS Early Access` |
| **To Email** | `{{to_email}}` |
| **From Name** | `FrontierOS` |
| **Reply To** | `tsingh98@umd.edu` |
| **Subject** | `Your FrontierOS access code: {{access_code}}` |

3. In **Content**, paste the HTML from [`EMAILJS_TEMPLATE.html`](./EMAILJS_TEMPLATE.html):

```html
<p>Hi {{user_name}},</p>

<p>Thanks for signing up for FrontierOS early access.</p>

<p>Your access code: <strong>{{access_code}}</strong></p>

<p>Save this code. We will notify you when the product launches.</p>

<p>— FrontierOS</p>
```

4. Save the template and copy the **Template ID** (looks like `template_xxxxxxx`).

### Template variables (required)

These names must match exactly — the landing page sends them:

| Variable | Description |
|----------|-------------|
| `{{to_email}}` | Signup email (recipient) |
| `{{user_name}}` | Name from the form |
| `{{access_code}}` | Code from API, e.g. `FO-ABC123` |
| `{{reply_to}}` | Optional; sent as `tsingh98@umd.edu` |

5. Use **Test It** in EmailJS with sample values:

- `to_email`: your inbox  
- `user_name`: `Test User`  
- `access_code`: `FO-TEST99`

---

## 4. Get your Public Key

1. Dashboard → **Account** → **API Keys** (or **General**).
2. Copy the **Public Key** (safe to use in the browser).

---

## 5. Add keys to FrontierOS

Edit `static/config.js`:

```js
window.FRONTIEROS_EMAILJS = {
  publicKey: 'YOUR_PUBLIC_KEY',
  serviceId: 'YOUR_SERVICE_ID',
  templateId: 'YOUR_TEMPLATE_ID',
};
```

Example:

```js
window.FRONTIEROS_EMAILJS = {
  publicKey: 'aBcDeFgHiJkLmNoPq',
  serviceId: 'service_abc1234',
  templateId: 'template_xyz5678',
};
```

---

## 6. Publish to GitHub Pages

From the project root:

```bash
python scripts/build_ghpages.py
git add static/config.js docs/config.js docs/index.html
git commit -m "Enable EmailJS for access code emails"
git push origin main
```

**Optional (keys not in git):** set GitHub Actions variables instead:

| Variable | Value |
|----------|--------|
| `FRONTIEROS_EMAILJS_PUBLIC_KEY` | Public key |
| `FRONTIEROS_EMAILJS_SERVICE_ID` | Service ID |
| `FRONTIEROS_EMAILJS_TEMPLATE_ID` | Template ID |

Then push any commit to `main` (or re-run **Deploy landing to GitHub Pages**).

---

## 7. Test end-to-end

1. Open [https://tusu18.github.io/FrontierOS/](https://tusu18.github.io/FrontierOS/) (hard refresh: Cmd+Shift+R).
2. Click **Request early access**, submit with a real email.
3. In browser DevTools → **Network**, confirm:
   - `POST` to `frontieros-api.onrender.com/api/waitlist` succeeds
   - `POST` to `api.emailjs.com` returns **200**
4. Check inbox (and spam) for the access code.

If EmailJS fails, the modal still shows the code when the API returns `access_code` in the JSON response.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No EmailJS request in Network | `publicKey`, `serviceId`, or `templateId` empty in `config.js` — rebuild `docs/` and push |
| EmailJS 400 / template error | **To Email** must be `{{to_email}}`; body must use `{{user_name}}` and `{{access_code}}` |
| Email only goes to your Gmail, not signup user | **To Email** field must be `{{to_email}}`, not a fixed address |
| Gmail “less secure” / connect failed | Reconnect Gmail in Email Services; use an App Password if Google requires it |
| Code shows in UI but no email | API signup worked; fix EmailJS keys or template test in dashboard |
| CORS error | EmailJS must run in the browser on the landing page (already wired in `static/index.html`) |

---

## How it works in code

- Config: `static/config.js` → `window.FRONTIEROS_EMAILJS`
- Send function: `sendAccessCodeViaEmailJS()` in `static/index.html`
- Called when waitlist response has `email_sent: false` and an `access_code`

Server-side Gmail SMTP on Render free tier will still fail; EmailJS is the workaround for the landing page only.

For server-side email without EmailJS, use **Resend** on Render — see [DEPLOY.md](../DEPLOY.md) §5.
