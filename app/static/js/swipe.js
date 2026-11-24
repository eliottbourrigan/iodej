/* Iodej — pile de cartes façon Tinder (pointer events natifs). */
(() => {
  const deck = document.getElementById("deck");
  if (!deck) return;

  const btnYes = document.getElementById("btn-yes");
  const btnNo = document.getElementById("btn-no");
  const pips = [...document.querySelectorAll("#pips i")];
  const countEl = document.getElementById("count-done");
  const total = +deck.dataset.total;
  let done = +deck.dataset.done;
  let busy = false;

  const topCard = () => {
    const cards = deck.querySelectorAll(".card:not(.fly)");
    return cards[cards.length - 1] || null;
  };

  const restack = () => {
    const cards = [...deck.querySelectorAll(".card:not(.fly)")].reverse();
    cards.forEach((c, i) => c.style.setProperty("--d", i));
  };

  const setStamp = (card, ratio) => {
    const r = Math.max(-1, Math.min(1, ratio));
    card.style.setProperty("--oy", Math.max(0, r));
    card.style.setProperty("--on", Math.max(0, -r));
    card.style.setProperty("--sy", 0.6 + Math.max(0, r) * 0.5);
    card.style.setProperty("--sn", 0.6 + Math.max(0, -r) * 0.5);
  };

  const finish = () => {
    btnYes.disabled = btnNo.disabled = true;
    document.getElementById("deck-done").classList.add("show");
    confetti(90);
    setTimeout(() => { location.href = "/resultats?tab=groupes"; }, 1700);
  };

  async function send(id, liked) {
    const body = new FormData();
    body.append("restaurant_id", id);
    body.append("liked", liked ? "1" : "0");
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const res = await fetch("/api/swipe", { method: "POST", body, credentials: "same-origin" });
        if (res.status === 401) { location.href = "/login"; return null; }
        if (res.status === 409) {
          toast("Nouveau jour, nouveau tirage ! 🎲");
          setTimeout(() => location.reload(), 900);
          return null;
        }
        if (res.ok) return res.json();
      } catch (_) { /* réseau : on retente */ }
      await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
    }
    toast("Impossible d'enregistrer, on recharge…");
    setTimeout(() => location.reload(), 1200);
    return null;
  }

  function swipe(card, liked, fromDrag = false) {
    if (!card || card.classList.contains("fly")) return;
    const w = window.innerWidth;
    const dir = liked ? 1 : -1;
    card.classList.remove("dragging");
    card.classList.add("fly");
    setStamp(card, dir);
    const dy = fromDrag ? (parseFloat(card.dataset.dy) || 0) : -40;
    card.style.transform = `translate(${dir * (w + 200)}px, ${dy * 1.5}px) rotate(${dir * 35}deg)`;
    setTimeout(() => card.remove(), 500);

    const pip = pips[done];
    if (pip) pip.classList.add("on", liked ? "yes" : "no");
    done += 1;
    if (countEl) countEl.textContent = Math.min(done + 1, total);
    if (navigator.vibrate) navigator.vibrate(liked ? [12, 40, 12] : 10);
    restack();

    const result = send(card.dataset.id, liked);
    if (done >= total) result.then((r) => r && finish());
  }

  // ---- drag ----
  let drag = null;
  deck.addEventListener("pointerdown", (e) => {
    const card = e.target.closest(".card");
    if (!card || card !== topCard() || busy) return;
    card.setPointerCapture(e.pointerId);
    card.classList.add("dragging");
    drag = { card, x0: e.clientX, y0: e.clientY, dx: 0, dy: 0, t0: performance.now() };
  });
  deck.addEventListener("pointermove", (e) => {
    if (!drag) return;
    drag.dx = e.clientX - drag.x0;
    drag.dy = e.clientY - drag.y0;
    const rot = drag.dx / 14;
    drag.card.style.transform = `translate(${drag.dx}px, ${drag.dy}px) rotate(${rot}deg)`;
    drag.card.dataset.dy = drag.dy;
    setStamp(drag.card, drag.dx / 110);
    btnYes.classList.toggle("pressed", drag.dx > 60);
    btnNo.classList.toggle("pressed", drag.dx < -60);
  });
  const release = () => {
    if (!drag) return;
    const { card, dx, t0 } = drag;
    drag = null;
    btnYes.classList.remove("pressed");
    btnNo.classList.remove("pressed");
    const velocity = Math.abs(dx) / Math.max(1, performance.now() - t0);
    const threshold = Math.min(120, deck.clientWidth * 0.3);
    if (Math.abs(dx) > threshold || (velocity > 0.6 && Math.abs(dx) > 40)) {
      swipe(card, dx > 0, true);
    } else {
      card.classList.remove("dragging");
      card.style.transform = "";
      setStamp(card, 0);
    }
  };
  deck.addEventListener("pointerup", release);
  deck.addEventListener("pointercancel", release);

  // ---- boutons & clavier ----
  const buttonSwipe = (liked) => {
    const card = topCard();
    if (!card || busy || drag) return;
    setStamp(card, liked ? 1 : -1);
    card.style.transform = `translateX(${liked ? 30 : -30}px) rotate(${liked ? 4 : -4}deg)`;
    busy = true;
    setTimeout(() => { busy = false; swipe(card, liked); }, 140);
  };
  btnYes.addEventListener("click", () => buttonSwipe(true));
  btnNo.addEventListener("click", () => buttonSwipe(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") buttonSwipe(true);
    if (e.key === "ArrowLeft") buttonSwipe(false);
  });

  if (!topCard() && total > 0) finish();
})();
