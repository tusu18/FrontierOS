/**
 * Production API (GitHub Pages / static preview). Empty = same-origin local dev.
 *
 * EmailJS (optional): sends access codes from the browser when Render blocks SMTP.
 * Setup guide: docs/EMAILJS_SETUP.md — template: docs/EMAILJS_TEMPLATE.html
 */
window.FRONTIEROS_API = window.FRONTIEROS_API || 'https://frontieros-api.onrender.com';
window.FRONTIEROS_APP = window.FRONTIEROS_APP || '';
window.FRONTIEROS_EMAILJS = window.FRONTIEROS_EMAILJS || {
  publicKey: '',
  serviceId: '',
  templateId: '',
};
