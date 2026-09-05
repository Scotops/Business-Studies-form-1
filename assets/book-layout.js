(function () {
  "use strict";

  var frames = Array.from(document.querySelectorAll(".adt-source-fragment-frame"));
  if (!frames.length) return;

  function updateFrame(frame) {
    var fragment = frame.querySelector(":scope > .adt-source-fragment");
    if (!fragment) return;
    var scale = Number.parseFloat(
      getComputedStyle(fragment).getPropertyValue("--adt-fragment-scale")
    );
    if (!Number.isFinite(scale) || scale <= 0) scale = 1;
    frame.style.height = Math.ceil(fragment.scrollHeight * scale) + "px";
  }

  function updateAllFrames() {
    frames.forEach(updateFrame);
  }

  var scheduled = false;
  function scheduleUpdate() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(function () {
      scheduled = false;
      updateAllFrames();
    });
  }

  updateAllFrames();
  window.addEventListener("resize", scheduleUpdate, { passive: true });

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(scheduleUpdate);
  }

  if ("ResizeObserver" in window) {
    var resizeObserver = new ResizeObserver(scheduleUpdate);
    frames.forEach(function (frame) {
      var fragment = frame.querySelector(":scope > .adt-source-fragment");
      if (fragment) resizeObserver.observe(fragment);
    });
  }

  if ("MutationObserver" in window) {
    var mutationObserver = new MutationObserver(scheduleUpdate);
    frames.forEach(function (frame) {
      mutationObserver.observe(frame, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: ["class", "style", "src"],
      });
    });
  }
})();
