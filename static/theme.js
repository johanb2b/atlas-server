// Sätter tema innan sidan ritas, så att den inte blinkar till i fel tema.
(function () {
  try {
    // Mörkt tema som standard. En tom sträng betyder att användaren har valt att följa systemet.
    // app.js sparar valet som JSON ("dark" med citattecken), äldre versioner utan.
    var t = localStorage.getItem("atlas-server:theme");
    if (t === null) t = "dark";
    t = t.replace(/^"|"$/g, "");
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* privat läge */ }
})();
