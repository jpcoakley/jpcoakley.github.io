/* Floating translucent bubbles for the photography index.
   - Desktop: bubbles drift on sine paths with depth + mouse parallax;
     the specular reflection (--gx/--gy) follows the mouse.
   - Phones/tablets: static layout, but the reflection follows device
     tilt via DeviceOrientation (requires HTTPS; iOS asks on first tap).
   - prefers-reduced-motion: static layout, static reflection. */
(function () {
  var space = document.querySelector(".bubblespace");
  if (!space) return;

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var small = window.matchMedia("(max-width: 640px)").matches;

  /* ---- moving reflection (all modes except reduced-motion) ---- */
  function setGlint(nx, ny) {  // nx, ny in -1..1
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
        // iOS: needs a user gesture + HTTPS
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

  /* ---- floating layout (desktop, motion allowed) ---- */
  if (reduced || small) {
    space.classList.add("ready");
    return;
  }

  var bubbles = Array.prototype.slice.call(space.querySelectorAll(".bubble"));
  if (!bubbles.length) return;
  space.classList.add("ready");

  var mouse = { x: 0, y: 0 };
  var items = [];

  function layout() {
    var W = space.clientWidth, H = space.clientHeight;
    items = bubbles.map(function (el, i) {
      var d = parseFloat(getComputedStyle(el.querySelector(".orb")).width) || 180;
      var depth = 0.55 + ((i * 0.37) % 1) * 0.65;           // 0.55 (far) – 1.2 (near)
      var cols = Math.max(1, Math.min(bubbles.length, Math.floor(W / (d + 80))));
      var col = i % cols, row = Math.floor(i / cols);
      var jx = (((i * 73) % 47) / 47 - 0.5) * 80;
      var jy = (((i * 131) % 53) / 53 - 0.5) * 60;
      return {
        el: el, d: d, depth: depth,
        baseX: (W / (cols + 1)) * (col + 1) - d / 2 + jx,
        baseY: Math.min(H - d - 60, 40 + row * (d + 110) + jy),
        ampX: 14 + ((i * 29) % 12), ampY: 10 + ((i * 17) % 14),
        spX: 0.00022 + ((i * 7) % 5) * 0.00005,
        spY: 0.00028 + ((i * 11) % 5) * 0.00004,
        phX: i * 2.1, phY: i * 1.3
      };
    });
    items.sort(function (a, b) { return a.depth - b.depth; })
      .forEach(function (it, z) { it.el.style.zIndex = z + 1; });
  }

  function frame(t) {
    items.forEach(function (it) {
      var x = it.baseX + Math.sin(t * it.spX + it.phX) * it.ampX
            + mouse.x * 26 * (it.depth - 0.85);
      var y = it.baseY + Math.sin(t * it.spY + it.phY) * it.ampY
            + mouse.y * 18 * (it.depth - 0.85);
      it.el.style.transform =
        "translate3d(" + x + "px," + y + "px,0) scale(" + it.depth + ")";
      it.el.style.filter = "brightness(" + (0.72 + it.depth * 0.28) + ")";
    });
    requestAnimationFrame(frame);
  }

  window.addEventListener("mousemove", function (e) {
    mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
    mouse.y = (e.clientY / window.innerHeight) * 2 - 1;
  }, { passive: true });
  window.addEventListener("resize", layout);

  layout();
  requestAnimationFrame(frame);
})();
