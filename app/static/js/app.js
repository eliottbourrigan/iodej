/* Iodej — utilitaires globaux (toasts, confettis, loader, PWA). */
(() => {
  const loader = () => document.getElementById("page-loader");

  // Loader plein écran après un court délai (évite le flash sur les pages rapides).
  let loaderTimer = null;
  window.showLoader = () => {
    clearTimeout(loaderTimer);
    loaderTimer = setTimeout(() => loader()?.classList.add("show"), 120);
  };
  window.hideLoader = () => { clearTimeout(loaderTimer); loader()?.classList.remove("show"); };
  window.addEventListener("pageshow", hideLoader);

  document.addEventListener("submit", (e) => {
    if (e.target.matches("form[data-loader]") && !e.defaultPrevented) showLoader();
  });
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href]");
    if (!a || a.hasAttribute("hx-get") || a.target || e.metaKey || e.ctrlKey) return;
    const url = new URL(a.href, location.href);
    if (url.origin === location.origin && url.href !== location.href && !url.hash) showLoader();
  });

  window.toast = (msg, ms = 2200) => {
    const box = document.getElementById("toasts");
    if (!box) return;
    const t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    box.appendChild(t);
    setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 350); }, ms);
  };

  const COLORS = ["#ffc933", "#ff4d6d", "#3ddc84", "#2fa8ff", "#7b5cff", "#ff8a1f", "#ff5cc8"];
  window.confetti = (n = 60) => {
    for (let i = 0; i < n; i++) {
      const c = document.createElement("i");
      c.className = "confetti";
      c.style.left = Math.random() * 100 + "vw";
      c.style.background = COLORS[i % COLORS.length];
      c.style.setProperty("--x", (Math.random() * 200 - 100) + "px");
      c.style.setProperty("--r", (Math.random() * 900 - 450) + "deg");
      c.style.setProperty("--t", (1.4 + Math.random() * 1.4) + "s");
      c.style.animationDelay = Math.random() * 0.4 + "s";
      if (i % 3 === 0) c.style.borderRadius = "50%";
      document.body.appendChild(c);
      setTimeout(() => c.remove(), 3500);
    }
  };

  document.addEventListener("htmx:responseError", () => toast("Oups, le serveur fait la sieste…"));
  document.addEventListener("htmx:sendError", () => toast("Pas de réseau 📡"));
  // Petit feu d'artifice quand on choisit son resto.
  document.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.requestConfig?.path === "/api/meal" && e.detail.target.querySelector(".is-going")) {
      confetti(40);
      toast("Bon appétit ! 🍽️");
    }
  });

  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
})();
