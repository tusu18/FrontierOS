/**
 * Production API (GitHub Pages / static preview). Empty = same-origin local dev.
 *
 * EmailJS (optional): sends access codes from the browser when Render blocks SMTP.
 * Create template at emailjs.com — set To field to {{to_email}}, body uses {{access_code}}, {{user_name}}.
 */
window.FRONTIEROS_API = window.FRONTIEROS_API || 'https://frontieros-api.onrender.com';
window.FRONTIEROS_APP = window.FRONTIEROS_APP || '';
window.FRONTIEROS_EMAILJS = window.FRONTIEROS_EMAILJS || {
  publicKey: '',
  serviceId: '',
  templateId: '',
};
/** Logo URL used in EmailJS access-code emails */
window.FRONTIEROS_EMAIL_LOGO = window.FRONTIEROS_EMAIL_LOGO || (
  'https://tusu18.github.io/FrontierOS/assets/logo-mark.svg'
);
