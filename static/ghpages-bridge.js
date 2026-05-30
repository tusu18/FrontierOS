(function () {
  function base(envKey, fallback) {
    const v = (window[envKey] || '').trim().replace(/\/$/, '');
    return v || fallback;
  }

  window.frontierApi = function (path) {
    const b = base('FRONTIEROS_API', '');
    return b ? b + path : path;
  };

  window.frontierAppUrl = function (query) {
    const app = base('FRONTIEROS_APP', '');
    const api = base('FRONTIEROS_API', '');
    const root = app || (api ? api + '/app' : '');
    const q = query || '';
    if (!root) return '/app' + q;
    if (q.startsWith('?')) return root + q;
    return root + (q.startsWith('/') ? q : '/' + q);
  };
})();
