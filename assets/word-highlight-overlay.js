(function () {
  "use strict";

  var content = document.getElementById("content");
  if (!content) return;

  var sourcePage = content.getAttribute("data-source-page") || "";
  var physicalPage = Number.parseInt(sourcePage.slice(2), 10);
  if (!Number.isFinite(physicalPage) || physicalPage < 7 || physicalPage > 48) return;

  var overlay = document.createElement("aside");
  overlay.className = "adt-word-highlight-overlay";
  overlay.hidden = true;
  overlay.setAttribute("aria-hidden", "true");

  var label = document.createElement("span");
  label.className = "adt-word-highlight-overlay__label";
  label.textContent = "Reading word by word";

  var phrase = document.createElement("span");
  phrase.className = "adt-word-highlight-overlay__phrase";

  overlay.append(label, phrase);
  document.body.appendChild(overlay);

  var updateQueued = false;
  var lastKey = "";

  function appendToken(text, active) {
    var token = document.createElement("span");
    token.className = active
      ? "adt-word-highlight-overlay__word adt-word-highlight-overlay__word--active"
      : "adt-word-highlight-overlay__word";
    token.textContent = text;
    phrase.appendChild(token);
  }

  function showWord(activeWord) {
    var parent = activeWord.closest("[data-id]");
    if (!parent) return false;

    var words = Array.from(parent.querySelectorAll("[data-word-index]"));
    var activeIndex = words.indexOf(activeWord);
    if (activeIndex < 0) return false;

    var parentId = parent.getAttribute("data-id") || "";
    var key = parentId + ":" + activeIndex;
    if (key === lastKey) return true;
    lastKey = key;

    var start = Math.max(0, activeIndex - 4);
    var end = Math.min(words.length, activeIndex + 6);
    phrase.replaceChildren();
    if (start > 0) appendToken("…", false);
    for (var index = start; index < end; index += 1) {
      appendToken(words[index].textContent || "", index === activeIndex);
    }
    if (end < words.length) appendToken("…", false);

    overlay.hidden = false;
    overlay.classList.remove("adt-word-highlight-overlay--block");
    return true;
  }

  function showBlock(activeBlock) {
    var text = activeBlock.getAttribute("alt") || activeBlock.textContent || "";
    text = text.replace(/\s+/g, " ").trim();
    if (!text) return false;

    var key = "block:" + (activeBlock.getAttribute("data-id") || text);
    if (key === lastKey) return true;
    lastKey = key;

    var words = text.split(" ");
    var preview = words.slice(0, 16).join(" ");
    if (words.length > 16) preview += "…";
    phrase.replaceChildren();
    appendToken(preview, true);
    overlay.hidden = false;
    overlay.classList.add("adt-word-highlight-overlay--block");
    return true;
  }

  function updateOverlay() {
    updateQueued = false;
    var activeWord = content.querySelector("[data-word-index].bg-yellow-300");
    if (activeWord && showWord(activeWord)) return;

    var activeBlock = content.querySelector(".tts-active-block");
    if (activeBlock && showBlock(activeBlock)) return;

    lastKey = "";
    overlay.hidden = true;
    phrase.replaceChildren();
  }

  function scheduleUpdate() {
    if (updateQueued) return;
    updateQueued = true;
    queueMicrotask(updateOverlay);
  }

  var observer = new MutationObserver(scheduleUpdate);
  observer.observe(content, {
    attributes: true,
    attributeFilter: ["class"],
    childList: true,
    subtree: true,
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
