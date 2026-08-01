/* Lightbox for gallery grids. Each .gallery is its own sequence;
   links keep working as plain image links without JS. */
(function () {
  var overlay, img, counter, current, items;

  function build() {
    overlay = document.createElement("div");
    overlay.className = "lightbox";
    overlay.innerHTML =
      '<button class="lb-close" aria-label="Close"><span class="lb-donut"></span></button>' +
      '<button class="lb-prev" aria-label="Previous">&#8249;</button>' +
      '<figure class="lb-stage"><img alt=""></figure>' +
      '<button class="lb-next" aria-label="Next">&#8250;</button>' +
      '<p class="lb-counter"></p>';
    document.body.appendChild(overlay);
    img = overlay.querySelector("img");
    counter = overlay.querySelector(".lb-counter");

    overlay.querySelector(".lb-close").addEventListener("click", close);
    overlay.querySelector(".lb-prev").addEventListener("click", function () { step(-1); });
    overlay.querySelector(".lb-next").addEventListener("click", function () { step(1); });
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay || e.target.className === "lb-stage") close();
    });

    document.addEventListener("keydown", function (e) {
      if (!overlay.classList.contains("open")) return;
      if (e.key === "Escape") close();
      if (e.key === "ArrowLeft") step(-1);
      if (e.key === "ArrowRight") step(1);
    });

    var touchX = null;
    overlay.addEventListener("touchstart", function (e) {
      touchX = e.changedTouches[0].clientX;
    }, { passive: true });
    overlay.addEventListener("touchend", function (e) {
      if (touchX === null) return;
      var dx = e.changedTouches[0].clientX - touchX;
      if (Math.abs(dx) > 40) step(dx > 0 ? -1 : 1);
      touchX = null;
    }, { passive: true });
  }

  function open(list, index) {
    if (!overlay) build();
    items = list;
    show(index);
    overlay.classList.add("open");
    document.body.style.overflow = "hidden";
  }

  function close() {
    overlay.classList.remove("open");
    document.body.style.overflow = "";
  }

  function step(d) {
    show((current + d + items.length) % items.length);
  }

  function show(index) {
    current = index;
    img.src = items[index];
    counter.textContent = (index + 1) + " / " + items.length;
    [-1, 1].forEach(function (d) {   // preload neighbours
      new Image().src = items[(index + d + items.length) % items.length];
    });
  }

  document.querySelectorAll(".gallery").forEach(function (gallery) {
    var links = Array.prototype.slice.call(gallery.querySelectorAll("a.frame"));
    var list = links.map(function (a) { return a.getAttribute("href"); });
    links.forEach(function (a, i) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        open(list, i);
      });
    });
  });
})();
