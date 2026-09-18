/*
 * ReqogniLoom presentation site — interaction layer.
 *
 * Plain vanilla JavaScript, no dependencies, no network access. Everything
 * degrades gracefully: the English content is in the HTML, and the CSS keeps
 * panels and reveal targets visible until this script asks for the enhanced
 * behaviour by adding the `js` class to <html>.
 */
(function () {
  'use strict';

  var doc = document;
  var root = doc.documentElement;
  var STORAGE_THEME = 'reqlo-theme';
  var STORAGE_LANG = 'reqlo-lang';

  root.classList.add('js');

  /* ---------------------------------------------------------------- i18n */

  var DICT = window.REQLO_I18N || { en: {}, de: {} };
  var DEFAULT_LANG = 'en';
  var currentLang = DEFAULT_LANG;

  function t(key) {
    var active = DICT[currentLang] || {};
    if (typeof active[key] === 'string') { return active[key]; }
    var fallback = DICT[DEFAULT_LANG] || {};
    return typeof fallback[key] === 'string' ? fallback[key] : key;
  }

  function readStoredLang() {
    try {
      var stored = window.localStorage.getItem(STORAGE_LANG);
      return DICT[stored] ? stored : DEFAULT_LANG;
    } catch (e) {
      return DEFAULT_LANG;
    }
  }

  function applyLang(lang) {
    if (!DICT[lang]) { lang = DEFAULT_LANG; }
    currentLang = lang;

    var nodes = doc.querySelectorAll('[data-i18n]');
    for (var i = 0; i < nodes.length; i += 1) {
      nodes[i].textContent = t(nodes[i].getAttribute('data-i18n'));
    }

    var contentNodes = doc.querySelectorAll('[data-i18n-content]');
    for (var c = 0; c < contentNodes.length; c += 1) {
      contentNodes[c].setAttribute('content', t(contentNodes[c].getAttribute('data-i18n-content')));
    }

    var labelNodes = doc.querySelectorAll('[data-i18n-aria-label]');
    for (var a = 0; a < labelNodes.length; a += 1) {
      labelNodes[a].setAttribute('aria-label', t(labelNodes[a].getAttribute('data-i18n-aria-label')));
    }

    var titleNodes = doc.querySelectorAll('[data-i18n-title]');
    for (var ti = 0; ti < titleNodes.length; ti += 1) {
      titleNodes[ti].setAttribute('title', t(titleNodes[ti].getAttribute('data-i18n-title')));
    }

    doc.title = t('meta.title');
    root.setAttribute('lang', lang);

    var langButtons = doc.querySelectorAll('.lang-btn');
    for (var l = 0; l < langButtons.length; l += 1) {
      var on = langButtons[l].getAttribute('data-lang') === lang;
      langButtons[l].setAttribute('aria-pressed', on ? 'true' : 'false');
      if (on) { langButtons[l].classList.add('is-active'); }
      else { langButtons[l].classList.remove('is-active'); }
    }

    refreshThemeLabel();
    refreshMenuLabel();

    try { window.localStorage.setItem(STORAGE_LANG, lang); } catch (e) { /* ignore */ }
  }

  var langHandlers = doc.querySelectorAll('.lang-btn');
  for (var lh = 0; lh < langHandlers.length; lh += 1) {
    langHandlers[lh].addEventListener('click', function (event) {
      applyLang(event.currentTarget.getAttribute('data-lang'));
    });
  }

  /* --------------------------------------------------------------- theme */

  var themeToggle = doc.getElementById('theme-toggle');
  var lightQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;

  function currentTheme() {
    return root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  }

  function refreshThemeLabel() {
    if (!themeToggle) { return; }
    /* Stable accessible name; `aria-pressed` carries the current state:
       pressed = dark mode is active. This avoids the "Switch to X, pressed"
       contradiction (F-05). */
    themeToggle.setAttribute('aria-label', t('theme.name'));
    themeToggle.setAttribute('aria-pressed', currentTheme() === 'dark' ? 'true' : 'false');
  }

  function setTheme(theme, persist) {
    root.setAttribute('data-theme', theme === 'light' ? 'light' : 'dark');
    refreshThemeLabel();
    if (persist) {
      try { window.localStorage.setItem(STORAGE_THEME, theme); } catch (e) { /* ignore */ }
    }
  }

  if (themeToggle) {
    themeToggle.addEventListener('click', function () {
      setTheme(currentTheme() === 'light' ? 'dark' : 'light', true);
    });
  }

  /* Follow the OS preference only while the visitor has not chosen explicitly. */
  if (lightQuery) {
    var onSchemeChange = function (event) {
      var stored = null;
      try { stored = window.localStorage.getItem(STORAGE_THEME); } catch (e) { stored = null; }
      if (stored === 'light' || stored === 'dark') { return; }
      setTheme(event.matches ? 'light' : 'dark', false);
    };
    if (lightQuery.addEventListener) { lightQuery.addEventListener('change', onSchemeChange); }
    else if (lightQuery.addListener) { lightQuery.addListener(onSchemeChange); }
  }

  /* ------------------------------------------------------- mobile menu */

  var menuToggle = doc.getElementById('menu-toggle');
  var nav = doc.getElementById('primary-nav');

  function refreshMenuLabel() {
    if (!menuToggle) { return; }
    var open = menuToggle.getAttribute('aria-expanded') === 'true';
    menuToggle.setAttribute('aria-label', open ? t('nav.menuClose') : t('nav.menuOpen'));
  }

  function setMenu(open) {
    if (!menuToggle || !nav) { return; }
    menuToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) { nav.classList.add('is-open'); }
    else { nav.classList.remove('is-open'); }
    refreshMenuLabel();
  }

  if (menuToggle && nav) {
    menuToggle.addEventListener('click', function () {
      setMenu(menuToggle.getAttribute('aria-expanded') !== 'true');
    });

    doc.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && menuToggle.getAttribute('aria-expanded') === 'true') {
        setMenu(false);
        menuToggle.focus();
      }
    });

    doc.addEventListener('click', function (event) {
      if (menuToggle.getAttribute('aria-expanded') !== 'true') { return; }
      if (nav.contains(event.target) || menuToggle.contains(event.target)) { return; }
      setMenu(false);
    });

    nav.addEventListener('click', function (event) {
      if (event.target.closest && event.target.closest('a')) { setMenu(false); }
    });

    window.addEventListener('resize', function () {
      if (window.innerWidth >= 1280) { setMenu(false); }
    });
  }

  /* --------------------------------------------------------- scroll spy */

  var navLinks = [].slice.call(doc.querySelectorAll('.site-nav a[href^="#"]'));
  var sections = [];
  navLinks.forEach(function (link) {
    var target = doc.getElementById(link.getAttribute('href').slice(1));
    if (target) { sections.push(target); }
  });

  function setCurrent(id) {
    navLinks.forEach(function (link) {
      if (link.getAttribute('href') === '#' + id) { link.setAttribute('aria-current', 'true'); }
      else { link.removeAttribute('aria-current'); }
    });
  }

  if (sections.length && 'IntersectionObserver' in window) {
    var spy = new IntersectionObserver(function (entries) {
      var active = null;
      for (var e = 0; e < entries.length; e += 1) {
        if (entries[e].isIntersecting) { active = entries[e].target.id; break; }
      }
      if (active) { setCurrent(active); }
    }, { rootMargin: '-40% 0px -55% 0px', threshold: 0 });
    sections.forEach(function (section) { spy.observe(section); });
  }

  /* ------------------------------------------------------- scroll reveal */

  var reducedMotion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  var revealItems = [].slice.call(doc.querySelectorAll('.reveal'));

  function revealAll() {
    revealItems.forEach(function (item) { item.classList.add('is-visible'); });
  }

  if (revealItems.length) {
    if (reducedMotion && reducedMotion.matches) {
      revealAll();
    } else if ('IntersectionObserver' in window) {
      var revealer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            revealer.unobserve(entry.target);
          }
        });
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
      revealItems.forEach(function (item) { revealer.observe(item); });
      /* Safety net: never leave content hidden, even if the observer misfires. */
      window.setTimeout(revealAll, 8000);
    } else {
      revealAll();
    }
  }

  /* ---------------------------------------------------- layer explorer */

  var explorers = doc.querySelectorAll('[data-explorer]');
  for (var x = 0; x < explorers.length; x += 1) {
    (function (explorer) {
      var tabs = [].slice.call(explorer.querySelectorAll('[role="tab"]'));
      if (!tabs.length) { return; }

      function activate(tab, moveFocus) {
        tabs.forEach(function (candidate) {
          var selected = candidate === tab;
          candidate.setAttribute('aria-selected', selected ? 'true' : 'false');
          candidate.tabIndex = selected ? 0 : -1;
          var panel = doc.getElementById(candidate.getAttribute('aria-controls'));
          if (panel) {
            if (selected) { panel.classList.add('is-active'); }
            else { panel.classList.remove('is-active'); }
          }
        });
        if (moveFocus) { tab.focus(); }
      }

      tabs.forEach(function (tab, index) {
        tab.addEventListener('click', function () { activate(tab, false); });
        tab.addEventListener('keydown', function (event) {
          var next = null;
          if (event.key === 'ArrowRight' || event.key === 'ArrowDown') { next = tabs[(index + 1) % tabs.length]; }
          else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') { next = tabs[(index - 1 + tabs.length) % tabs.length]; }
          else if (event.key === 'Home') { next = tabs[0]; }
          else if (event.key === 'End') { next = tabs[tabs.length - 1]; }
          if (next) { event.preventDefault(); activate(next, true); }
        });
      });

      var selected = tabs.filter(function (tab) {
        return tab.getAttribute('aria-selected') === 'true';
      })[0] || tabs[0];
      activate(selected, false);
      /* Only now may the CSS hide the non-active panels. */
      explorer.classList.add('explorer-ready');
    }(explorers[x]));
  }

  /* ----------------------------------------------------------- accordion */

  var accordions = doc.querySelectorAll('[data-accordion]');
  for (var y = 0; y < accordions.length; y += 1) {
    (function (accordion) {
      var triggers = [].slice.call(accordion.querySelectorAll('.acc-trigger'));
      if (!triggers.length) { return; }

      function itemOf(trigger) { return trigger.closest('.acc-item'); }

      function close(trigger) {
        trigger.setAttribute('aria-expanded', 'false');
        var item = itemOf(trigger);
        if (item) { item.classList.remove('is-open'); }
      }

      function open(trigger) {
        trigger.setAttribute('aria-expanded', 'true');
        var item = itemOf(trigger);
        if (item) { item.classList.add('is-open'); }
      }

      /* Without JavaScript the panels are visible (the HTML defaults to
         aria-expanded="true"). Once the script runs, start fully collapsed. */
      triggers.forEach(function (trigger) { close(trigger); });

      triggers.forEach(function (trigger, index) {
        trigger.addEventListener('click', function () {
          var isOpen = trigger.getAttribute('aria-expanded') === 'true';
          if (isOpen) { close(trigger); return; }
          triggers.forEach(function (other) { if (other !== trigger) { close(other); } });
          open(trigger);
        });

        trigger.addEventListener('keydown', function (event) {
          var next = null;
          if (event.key === 'ArrowDown') { next = triggers[(index + 1) % triggers.length]; }
          else if (event.key === 'ArrowUp') { next = triggers[(index - 1 + triggers.length) % triggers.length]; }
          else if (event.key === 'Home') { next = triggers[0]; }
          else if (event.key === 'End') { next = triggers[triggers.length - 1]; }
          if (next) { event.preventDefault(); next.focus(); }
        });
      });

      /* Only now may the CSS hide the collapsed panels: if anything above
         throws, all eight panels stay visible instead of hidden (F-08). */
      accordion.classList.add('accordion-ready');
    }(accordions[y]));
  }

  /* ------------------------------------------------------------- boot */

  applyLang(readStoredLang());
  refreshThemeLabel();
  refreshMenuLabel();
}());
