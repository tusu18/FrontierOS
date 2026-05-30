/* ResearchRadar — icons (thin-line geometric) */
const { createElement: h } = React;

function Icon({ name, size = 17, stroke = 'currentColor', sw = 1.6 }) {
  const p = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke, strokeWidth: sw, strokeLinecap: 'round', strokeLinejoin: 'round' };
  const paths = {
    grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
    feed: 'M4 6h16M4 12h16M4 18h10',
    doc: 'M7 3h7l5 5v13H7zM14 3v5h5',
    spark: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z',
    graph: 'M6 6a2 2 0 100-.01M18 8a2 2 0 100-.01M9 17a2 2 0 100-.01M7.5 7l9 .8M8 15l8.5-6',
    radar: 'M12 12V3M12 12l7 4M12 21a9 9 0 110-18 9 9 0 010 18zM12 12l-6 3',
    target: 'M12 21a9 9 0 100-18 9 9 0 000 18zM12 16a4 4 0 100-8 4 4 0 000 8zM12 12h.01',
    code: 'M8 8l-4 4 4 4M16 8l4 4-4 4M13 5l-2 14',
    build: 'M3 21h18M5 21V10l7-5 7 5v11M9 21v-6h6v6',
    report: 'M5 3h14v18l-7-3-7 3zM9 8h6M9 12h6',
    bookmark: 'M6 3h12v18l-6-4-6 4z',
    gear: 'M12 9a3 3 0 100 6 3 3 0 000-6zM12 2l1.5 2.6 3-.4 .9 2.9 2.6 1.5-1.3 2.7 1.3 2.7-2.6 1.5-.9 2.9-3-.4L12 22l-1.5-2.6-3 .4-.9-2.9L4 15.4l1.3-2.7L4 10l2.6-1.5.9-2.9 3 .4z',
    search: 'M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3',
    bell: 'M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0',
    arrow: 'M5 12h14M13 6l6 6-6 6',
    plus: 'M12 5v14M5 12h14',
    minus: 'M5 12h14',
    download: 'M12 3v12M7 11l5 4 5-4M5 21h14',
    external: 'M14 4h6v6M20 4l-9 9M18 13v6H5V6h6',
    compare: 'M9 3v18M4 7h5M4 12h5M4 17h5M15 3v18M15 8h5M15 13h5',
    check: 'M5 13l4 4 10-11',
    chevron: 'M9 6l6 6-6 6',
    reset: 'M4 4v6h6M20 20v-6h-6M20 9a8 8 0 00-15-1M4 15a8 8 0 0015 1',
  };
  return h('svg', p, h('path', { d: paths[name] || paths.grid }));
}
window.Icon = Icon;
