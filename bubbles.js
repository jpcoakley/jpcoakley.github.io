/* Floating, draggable, translucent bubbles for the photography index.
   - Bubbles cluster next to / over one another and bob gently.
   - Drag to toss them (spring-glide on release, they settle where left).
   - Tap/click (movement < 8px) navigates into the collection.
   - Reflection (--gx/--gy) follows mouse, or device tilt on phones (HTTPS).
   - prefers-reduced-motion: static layout, no drift, no drag. */
(function () {
  var space = document.querySelector(".bubblespace");
  if (!space) return;

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- moving reflection ---- */
  function setGlint(nx, ny) {
    space.style.setProperty("--gx", (30 + nx * 26) + "%");
    space.style.setProperty("--gy", (24 + ny * 22) + "%");
  }
  if (!reduced) {
    window.addEventListener("mousemove", function (e) {
      setGlint((e.clientX / window.innerWidth) * 2 - 1,
               (e.clientY / window.innerHeight) * 2 - 1);
    }, { passive: true });
    var tilt = function (e) {
      if (e.gamma === null || e.beta === null) return;
      setGlint(Math.max(-1, Math.min(1, e.gamma / 30)),
               Math.max(-1, Math.min(1, (e.beta - 40) / 30)));
    };
    if (typeof DeviceOrientationEvent !== "undefined") {
      if (typeof DeviceOrientationEvent.requestPermission === "function") {
        window.addEventListener("touchend", function ask() {
          window.removeEventListener("touchend", ask);
          DeviceOrientationEvent.requestPermission().then(function (state) {
            if (state === "granted") {
              window.addEventListener("deviceorientation", tilt, { passive: true });
            }
          }).catch(function () {});
        }, { passive: true });
      } else {
        window.addEventListener("deviceorientation", tilt, { passive: true });
      }
    }
  }

  if (reduced) { space.classList.add("ready"); return; }

  var bubbles = Array.prototype.slice.call(space.querySelectorAll(".bubble"));
  if (!bubbles.length) return;
  space.classList.add("ready");

  var items = [];

  function layout() {
    var W = space.clientWidth, H = space.clientHeight;
    var scale = Math.min(1, W / 760);          // shrink cluster on small screens
    var cx = W / 2, cy = H / 2 - 30;

    // biggest bubble in the middle, others spiral around it, overlapping
    var order = bubbles.map(function (el, i) {
      var d = (parseFloat(getComputedStyle(el.querySelector(".orb")).width) || 180) * scale;
      return { el: el, d: d, i: i };
    }).sort(function (a, b) { return b.d - a.d; });

    var r0 = order[0].d / 2;
    items = order.map(function (o, k) {
      var r = o.d / 2, ax, ay;
      if (k === 0) { ax = cx; ay = cy; }
      else {
        var ang = -0.6 + (k - 1) * 2.4;        // golden-ish angle steps
        var dist = (r0 + r) * 0.78;            // 22% edge overlap with center
        ax = cx + Math.cos(ang) * dist;
        ay = cy + Math.sin(ang) * dist * 0.72; // squash vertically
      }
      ax = Math.max(r + 10, Math.min(W - r - 10, ax));
      ay = Math.max(r + 10, Math.min(H - r - 70, ay));
      return {
        el: o.el, r: r, scale: scale,
        ax: ax, ay: ay, x: ax, y: ay, vx: 0, vy: 0,
        bobA: 6 + (o.i * 7) % 8,
        bobSX: 0.00022 + (o.i % 5) * 0.00005,
        bobSY: 0.00028 + (o.i % 4) * 0.00004,
        phX: o.i * 2.1, phY: o.i * 1.3,
        depth: 0.9 + (o.i % 3) * 0.1,
        drag: null, moved: 0
      };
    });
    items.forEach(function (it, z) { it.el.style.zIndex = z + 1; });
  }

  function frame(t) {
    items.forEach(function (it) {
      if (!it.drag) {
        var tx = it.ax + Math.sin(t * it.bobSX + it.phX) * it.bobA;
        var ty = it.ay + Math.sin(t * it.bobSY + it.phY) * it.bobA * 0.8;
        it.vx = (it.vx + (tx - it.x) * 0.006) * 0.94;
        it.vy = (it.vy + (ty - it.y) * 0.006) * 0.94;
        it.x += it.vx;
        it.y += it.vy;
      }
      it.el.style.transform = "translate3d(" + (it.x - it.r) + "px," +
        (it.y - it.r) + "px,0) scale(" + it.scale + ")";
    });
    requestAnimationFrame(frame);
  }

  items = [];
  layout();

  bubbles.forEach(function (el) {
    el.addEventListener("click", function (e) {
      var it = items.find(function (i) { return i.el === el; });
      if (it && it.moved > 8) e.preventDefault();   // drag, not a tap
    });
    el.addEventListener("dragstart", function (e) { e.preventDefault(); });

    el.addEventListener("pointerdown", function (e) {
      var it = items.find(function (i) { return i.el === el; });
      if (!it) return;
      it.drag = { dx: e.clientX - it.x, dy: e.clientY - it.y,
                  px: e.clientX, py: e.clientY, pt: performance.now() };
      it.moved = 0;
      el.setPointerCapture(e.pointerId);
      el.style.zIndex = 99;                          // dragged bubble on top
      el.classList.add("grabbed");
    });

    el.addEventListener("pointermove", function (e) {
      var it = items.find(function (i) { return i.el === el; });
      if (!it || !it.drag) return;
      var now = performance.now(), dt = Math.max(1, now - it.drag.pt);
      it.vx = (e.clientX - it.drag.px) / dt * 12;
      it.vy = (e.clientY - it.drag.py) / dt * 12;
      it.moved += Math.abs(e.clientX - it.drag.px) + Math.abs(e.clientY - it.drag.py);
      it.drag.px = e.clientX; it.drag.py = e.clientY; it.drag.pt = now;
      it.x = e.clientX - it.drag.dx;
      it.y = e.clientY - it.drag.dy;
    });

    function release(e) {
      var it = items.find(function (i) { return i.el === el; });
      if (!it || !it.drag) return;
      it.drag = null;
      el.classList.remove("grabbed");
      var W = space.clientWidth, H = space.clientHeight;
      it.ax = Math.max(it.r + 10, Math.min(W - it.r - 10, it.x + it.vx * 30));
      it.ay = Math.max(it.r + 10, Math.min(H - it.r - 70, it.y + it.vy * 30));
    }
    el.addEventListener("pointerup", release);
    el.addEventListener("pointercancel", release);
  });

  window.addEventListener("resize", layout);
  requestAnimationFrame(frame);
})();
