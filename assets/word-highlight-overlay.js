(function () {
  "use strict";

  var content = document.getElementById("content");
  if (!content) return;

  var sourcePage = content.getAttribute("data-source-page") || "";
  var physicalPage = Number.parseInt(sourcePage.slice(2), 10);
  if (!Number.isFinite(physicalPage) || physicalPage < 7 || physicalPage > 48) return;

  var layer = document.createElement("div");
  layer.className = "adt-pdf-word-highlight";
  layer.hidden = true;
  layer.setAttribute("aria-hidden", "true");
  content.appendChild(layer);

  var pageData = null;
  var updateQueued = false;
  var lastKey = "";

  function hideHighlight() {
    lastKey = "";
    layer.hidden = true;
    layer.replaceChildren();
  }

  function showWord(activeWord) {
    if (!pageData) return false;
    var parent = activeWord.closest("[data-id]");
    if (!parent) return false;

    var dataId = parent.getAttribute("data-id") || "";
    var wordIndex = Number.parseInt(activeWord.getAttribute("data-word-index"), 10);
    var item = pageData.items && pageData.items[dataId];
    var boxes = Number.isFinite(wordIndex) && item ? item[wordIndex] : null;
    if (!boxes || boxes.length === 0) return false;

    var key = dataId + ":" + wordIndex;
    if (key === lastKey) return true;
    lastKey = key;
    layer.replaceChildren();
    var parentStyle = window.getComputedStyle(parent);

    boxes.forEach(function (box, boxIndex) {
      var marker = document.createElement("span");
      marker.className = "adt-pdf-word-highlight__box";
      var paddingX = 0.65;
      var paddingY = 0.45;
      marker.style.left = ((box[0] - paddingX) / pageData.width) * 100 + "%";
      marker.style.top = ((box[1] - paddingY) / pageData.height) * 100 + "%";
      marker.style.width = ((box[2] - box[0] + paddingX * 2) / pageData.width) * 100 + "%";
      marker.style.height = ((box[3] - box[1] + paddingY * 2) / pageData.height) * 100 + "%";
      if (boxes.length === 1 && boxIndex === 0) {
        marker.textContent = activeWord.textContent || "";
        marker.style.fontSize =
          ((box[3] - box[1]) / pageData.height) * content.clientHeight * 0.92 + "px";
        marker.style.fontStyle = parentStyle.fontStyle;
        marker.style.fontWeight = parentStyle.fontWeight;
      } else {
        marker.classList.add("adt-pdf-word-highlight__box--source-text");
      }
      layer.appendChild(marker);
    });

    layer.hidden = false;
    return true;
  }

  function updateHighlight() {
    updateQueued = false;
    var activeWord = content.querySelector("[data-word-index].bg-yellow-300");
    if (activeWord && showWord(activeWord)) return;
    hideHighlight();
  }

  function scheduleUpdate() {
    if (updateQueued) return;
    updateQueued = true;
    queueMicrotask(updateHighlight);
  }

  var observer = new MutationObserver(scheduleUpdate);
  observer.observe(content, {
    attributes: true,
    attributeFilter: ["class"],
    childList: true,
    subtree: true,
  });

  fetch(new URL("./content/pdf-word-positions.json?v=1", document.baseURI))
    .then(function (response) {
      if (!response.ok) throw new Error("Could not load PDF word positions");
      return response.json();
    })
    .then(function (positions) {
      pageData = positions.pages && positions.pages[sourcePage];
      scheduleUpdate();
    })
    .catch(function (error) {
      console.warn("Source-page word highlighting is unavailable", error);
      hideHighlight();
    });

  scheduleUpdate();
  window.addEventListener(
    "beforeunload",
    function () {
      observer.disconnect();
    },
    { once: true }
  );
})();
