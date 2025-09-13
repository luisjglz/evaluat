/**
* Theme: Konrix - Responsive Tailwind Admin Dashboard
* Author: coderthemes
* Module/App: Theme Config Js
*/

(function () {

    var savedConfig = sessionStorage.getItem("__CONFIG__");
    // var savedConfig = localStorage.getItem("__CONFIG__");

    var defaultConfig = {
        direction: "ltr",
        theme: "light",
        layout: {
            width: "default",  // Boxed width Only available at large resolutions > 1600px (xl)
            position: "fixed",
        },
        topbar: {
            color: "light",
        },
        menu: {
            color: "light",
        },
        sidenav: {
            view: "default"  
        },
    };

    const html = document.getElementsByTagName("html")[0];

    config = Object.assign(JSON.parse(JSON.stringify(defaultConfig)), {});

    config.direction = html.getAttribute("dir") || defaultConfig.direction;
    config.theme = html.getAttribute("data-mode") || defaultConfig.theme;
    config.layout.width = html.getAttribute("data-layout-width") || defaultConfig.layout.width;
    config.layout.position = html.getAttribute("data-layout-position") || defaultConfig.layout.position;
    config.topbar.color = html.getAttribute("data-topbar-color") || defaultConfig.topbar.color;
    config.menu.color = html.getAttribute("data-menu-color") || defaultConfig.menu.color;
    config.sidenav.view = html.getAttribute("data-sidenav-view") || defaultConfig.sidenav.view;

    window.defaultConfig = JSON.parse(JSON.stringify(config));

    if (savedConfig !== null) {
        config = JSON.parse(savedConfig);
    }

    window.config = config;

    if (config) {
        html.setAttribute("dir", config.direction);
        html.setAttribute("data-mode", config.theme);
        html.setAttribute("data-layout-width", config.layout.width);
        html.setAttribute("data-layout-position", config.layout.position);
        html.setAttribute("data-topbar-color", config.topbar.color);
        html.setAttribute("data-menu-color", config.menu.color);

        if (window.innerWidth <= 768) {
            html.setAttribute("data-sidenav-view", "mobile");
        } else {
            html.setAttribute("data-sidenav-view", config.sidenav.view);
        }
    }
})();

// Manejar el cambio de tema claro/oscuro
(function () {
  var html = document.documentElement;

  // Lee el tema desde localStorage unificado
  var savedTheme = localStorage.getItem('bs-theme') || 'light';

  // Función para aplicar el modo y sincronizar atributos y clases
  function applyTheme(mode) {
    html.removeAttribute('data-theme');
    document.body.removeAttribute('data-theme');
    html.classList.remove('dark');
    document.body.classList.remove('dark');

    html.setAttribute('data-bs-theme', mode);
    html.setAttribute('data-mode', mode);

    if (mode === 'dark') {
      html.classList.add('dark');
    }
    localStorage.setItem('bs-theme', mode);
    window.config = window.config || {};
    window.config.theme = mode;
  }

  // Aplica tema guardado inicialmente
  applyTheme(savedTheme);

  // Listener del botón toggle con id 'light-dark-mode'
  var toggleBtn = document.getElementById('light-dark-mode');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      var current = html.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light';
      var next = current === 'dark' ? 'light' : 'dark';
      applyTheme(next);
    });
  }
})();
