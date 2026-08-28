// os-fx.js — efectos del kit ZIDONG OS en vanilla JS, sin dependencias.
// Spotlight: port de OsSpotlightCard (Vue Bits, MIT) — halo radial que sigue
// al cursor dentro de [data-spotlight]. Blur text: port de OsBlurText — el
// título entra palabra por palabra desde blur(10px) en [data-blur-text].
(function () {
  'use strict';

  document.querySelectorAll('[data-spotlight]').forEach(function (card) {
    var halo = document.createElement('div');
    halo.className = 'os-spotlight-halo';
    card.appendChild(halo);
    card.addEventListener('mousemove', function (e) {
      var r = card.getBoundingClientRect();
      halo.style.background = 'radial-gradient(circle at ' + (e.clientX - r.left) + 'px ' +
        (e.clientY - r.top) + 'px, rgba(122,13,32,.06), transparent 70%)';
    });
    card.addEventListener('mouseenter', function () { halo.style.opacity = '1'; });
    card.addEventListener('mouseleave', function () { halo.style.opacity = '0'; });
  });

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.querySelectorAll('[data-blur-text]').forEach(function (el) {
    var words = el.textContent.trim().split(/\s+/);
    el.textContent = '';
    words.forEach(function (word, i) {
      var span = document.createElement('span');
      span.className = 'os-blur-word';
      span.style.animationDelay = (i * 90) + 'ms';
      span.textContent = word + ' ';
      el.appendChild(span);
    });
  });
})();
