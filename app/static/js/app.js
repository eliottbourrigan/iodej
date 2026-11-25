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

  // ---- Installation en PWA -------------------------------------------------
  let deferredPrompt = null;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // on affiche notre propre bouton
    deferredPrompt = e;
    window.dispatchEvent(new Event("iodej:can-install"));
  });

  const HINT_KEY = "iodej:pwa-hint-dismissed";
  const SNOOZE_DAYS = 7;

  window.detectPlatform = () => {
    const ua = navigator.userAgent || "";
    const standalone = window.matchMedia("(display-mode: standalone)").matches
      || window.matchMedia("(display-mode: fullscreen)").matches
      || navigator.standalone === true;
    // iPadOS se présente comme un Mac : on le reconnaît à l'écran tactile.
    const ios = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
    const android = /Android/i.test(ua);
    const safari = ios && !/CriOS|FxiOS|EdgiOS|OPiOS|GSA|FBAN|FBAV|Instagram/i.test(ua);
    return { os: ios ? "ios" : android ? "android" : "other", standalone, safari };
  };

  window.pwaHint = () => ({
    open: false,
    os: "other",
    safari: false,
    canPrompt: !!deferredPrompt,
    init() {
      const p = detectPlatform();
      this.os = p.os;
      this.safari = p.safari;
      const snoozed = +localStorage.getItem(HINT_KEY) || 0;
      const fresh = Date.now() - snoozed > SNOOZE_DAYS * 864e5;
      // Pas pendant un swipe : l'encart masquerait les boutons.
      const busy = !!document.getElementById("deck")?.querySelector(".card");
      if (p.os !== "other" && !p.standalone && fresh && !busy) {
        setTimeout(() => { this.open = true; }, 1200);
      }
      window.addEventListener("iodej:can-install", () => { this.canPrompt = true; });
      window.addEventListener("appinstalled", () => { this.open = false; toast("Appli installée ! 🎉"); });
    },
    async install() {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      deferredPrompt = null;
      this.canPrompt = false;
      if (outcome === "accepted") this.open = false;
    },
    dismiss() {
      localStorage.setItem(HINT_KEY, String(Date.now()));
      this.open = false;
    },
  });

  // ---- Notifications (Web Push) --------------------------------------------
  const pushSupported = () =>
    "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

  const b64ToBytes = (b64) => {
    const pad = "=".repeat((4 - (b64.length % 4)) % 4);
    const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  };

  const postJSON = (url, body) => fetch(url, {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });

  const currentSubscription = async () => {
    if (!pushSupported()) return null;
    const reg = await navigator.serviceWorker.ready;
    return reg.pushManager.getSubscription();
  };

  window.pushToggle = () => ({
    state: "hidden", // hidden | install | denied | off | on
    busy: false,
    key: null,
    async init() {
      const p = detectPlatform();
      if (!pushSupported()) {
        // Sur iPhone, le push n'existe que dans l'appli installée.
        if (p.os === "ios" && !p.standalone) this.state = "install";
        return;
      }
      if (Notification.permission === "denied") { this.state = "denied"; return; }
      try {
        // Clé récupérée d'avance : la demande de permission doit suivre
        // immédiatement le clic (exigence d'iOS).
        this.key = (await (await fetch("/api/push/key", { credentials: "same-origin" })).json()).key;
        const sub = Notification.permission === "granted" ? await currentSubscription() : null;
        this.state = sub ? "on" : "off";
        if (sub) postJSON("/api/push/subscribe", sub.toJSON()); // resynchronise l'appareil
      } catch (_) { this.state = "hidden"; }
    },
    label() {
      if (this.busy) return "⏳ Un instant…";
      return {
        install: "🔔 Notifications : installe d'abord l'appli",
        denied: "🔕 Notifications bloquées (réglages)",
        off: "🔔 Activer les notifications",
        on: "🔕 Désactiver les notifications",
      }[this.state] || "";
    },
    async toggle() {
      if (this.busy) return;
      this.busy = true;
      try {
        if (this.state === "on") {
          const sub = await currentSubscription();
          if (sub) {
            await postJSON("/api/push/unsubscribe", { endpoint: sub.endpoint });
            await sub.unsubscribe();
          }
          this.state = "off";
          toast("Notifications désactivées");
        } else {
          const perm = await Notification.requestPermission();
          if (perm !== "granted") {
            this.state = perm === "denied" ? "denied" : "off";
            toast("Notifications refusées");
            return;
          }
          const reg = await navigator.serviceWorker.ready;
          const sub = await reg.pushManager.subscribe({
            userVisibleOnly: true, applicationServerKey: b64ToBytes(this.key),
          });
          const res = await postJSON("/api/push/subscribe", sub.toJSON());
          if (!res.ok) throw new Error("subscribe");
          this.state = "on";
          toast("🔔 Rappel activé : 11h30 en semaine");
        }
      } catch (_) {
        toast("Impossible d'activer les notifications sur cet appareil");
      } finally {
        this.busy = false;
      }
    },
  });

  // À la déconnexion, l'appareil cesse de recevoir les rappels de ce collègue.
  window.iodejLogout = async () => {
    showLoader();
    try {
      const sub = await Promise.race([currentSubscription(), new Promise((r) => setTimeout(() => r(null), 1500))]);
      if (sub) {
        await postJSON("/api/push/unsubscribe", { endpoint: sub.endpoint });
        await sub.unsubscribe();
      }
    } catch (_) { /* on se déconnecte quand même */ }
    location.href = "/logout";
  };

  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
})();
