/* Adaptive Intake — customer portal widget (PORTAL.md §12).
 * Vanilla JS, Shadow DOM, no framework, no build step. It is an intake + status portal — NOT a chatbot:
 * submit your mess, answer at most two drills, track it. It renders whatever the engine decides; it
 * contains zero question logic. One <script src=".../p/embed.js" data-key="..."> tag drops it in. */
(function () {
  "use strict";

  // --- config: standalone page sets window.__ADAPTIVE_PORTAL__; else read the <script> data-attrs ---
  var cfg = window.__ADAPTIVE_PORTAL__ || null;
  var script = document.currentScript || (function () {
    var s = document.querySelectorAll("script[data-key]");
    return s[s.length - 1];
  })();
  var apiBase, key, token, accent, position, standalone;
  if (cfg) {
    standalone = true;
    apiBase = cfg.api;
    key = cfg.mode === "submit" ? cfg.value : "";
    token = cfg.mode === "status" ? cfg.value : "";
    accent = cfg.accent || "#2563eb";
    position = "inline";
  } else {
    standalone = false;
    apiBase = new URL(script.src).origin + "/p";
    key = script.getAttribute("data-key") || "";
    accent = script.getAttribute("data-accent") || "#2563eb";
    position = script.getAttribute("data-position") || "bottom-right";
    token = "";
  }
  var LS = "adaptive-intake.token." + (key || "standalone");
  if (!token && !standalone) token = localStorage.getItem(LS) || "";

  // --- host + shadow root ---
  var host = document.createElement("div");
  host.setAttribute("data-adaptive-intake", "");
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });

  var pos = {
    "bottom-right": "bottom:20px;right:20px;",
    "bottom-left": "bottom:20px;left:20px;",
  }[position] || "bottom:20px;right:20px;";

  root.innerHTML =
    "<style>" +
    ":host{all:initial}" +
    "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}" +
    ".launch{position:fixed;" + pos + "z-index:2147483000;border:0;border-radius:999px;padding:13px 18px;" +
    "background:" + accent + ";color:#fff;font-size:15px;font-weight:600;cursor:pointer;box-shadow:0 6px 24px rgba(0,0,0,.22)}" +
    ".panel{background:#fff;color:#14171c;border-radius:14px;overflow:hidden;box-shadow:0 18px 60px rgba(0,0,0,.28)}" +
    ".float{position:fixed;" + pos + "z-index:2147483001;width:380px;max-width:calc(100vw - 28px)}" +
    ".inline{width:100%;max-width:560px;margin:0 auto}" +
    ".hd{padding:16px 18px;background:" + accent + ";color:#fff}" +
    ".hd h2{margin:0;font-size:16px;font-weight:650}" +
    ".hd p{margin:3px 0 0;font-size:12.5px;opacity:.9}" +
    ".hd .x{position:absolute;top:12px;right:14px;background:none;border:0;color:#fff;font-size:20px;cursor:pointer;opacity:.9}" +
    ".bd{padding:16px 18px}" +
    "textarea{width:100%;min-height:120px;border:1px solid #d7dbe0;border-radius:10px;padding:12px;font-size:15px;resize:vertical;color:#14171c}" +
    "textarea:focus,button:focus-visible{outline:2px solid " + accent + ";outline-offset:1px}" +
    ".tools{display:flex;gap:8px;margin-top:10px;align-items:center;flex-wrap:wrap}" +
    ".rec{display:flex;align-items:center;gap:8px;border:1px solid " + accent + ";color:" + accent +
    ";background:#fff;border-radius:10px;padding:11px 14px;font-size:14px;font-weight:600;cursor:pointer}" +
    ".rec.on{background:" + accent + ";color:#fff}" +
    ".dot{width:9px;height:9px;border-radius:50%;background:currentColor}" +
    ".rec.on .dot{animation:bl 1s infinite}@keyframes bl{50%{opacity:.25}}" +
    ".file{font-size:13px;color:#5b6470}" +
    ".send{width:100%;margin-top:14px;border:0;border-radius:10px;background:" + accent +
    ";color:#fff;font-size:15px;font-weight:650;padding:13px;cursor:pointer}" +
    ".send:disabled{opacity:.55;cursor:default}" +
    ".hint{font-size:12px;color:#6b7480;margin:8px 2px 0}" +
    ".err{background:#fdecea;color:#b42318;border-radius:8px;padding:9px 11px;font-size:13px;margin-top:10px}" +
    ".stage{display:flex;align-items:center;gap:10px;padding:7px 0;color:#9aa4b1;font-size:14px}" +
    ".stage.on{color:#14171c;font-weight:600}.stage.done{color:#3fb950}" +
    ".sd{width:9px;height:9px;border-radius:50%;border:1px solid #cdd3da}.stage.on .sd{background:" + accent + ";border-color:" + accent + "}" +
    ".stage.done .sd{background:#3fb950;border-color:#3fb950}" +
    ".ref{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#6b7480}" +
    ".big{font-size:19px;font-weight:650;margin:6px 0 4px}.sub{font-size:14px;color:#5b6470}" +
    ".card{border:1px solid #e4e7eb;border-radius:10px;padding:12px 14px;margin:12px 0;font-size:14.5px}" +
    ".due{font-size:13px;color:#14171c;margin-top:6px}.due b{color:" + accent + "}" +
    ".q{font-size:15.5px;font-weight:600;margin:14px 0 10px}" +
    ".opts{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}" +
    ".opt{border:1px solid " + accent + ";color:" + accent + ";background:#fff;border-radius:999px;padding:9px 14px;font-size:14px;cursor:pointer}" +
    ".opt.sel{background:" + accent + ";color:#fff}" +
    ".foot{padding:10px 18px;font-size:11px;color:#9aa4b1;border-top:1px solid #eef0f3;text-align:center}" +
    "</style>" +
    '<div id="mount"></div>';

  var mount = root.getElementById("mount");
  var recorder = null, chunks = [], recBlob = null, recTimer = null, recSecs = 0, open = standalone;

  function api(path, opts) {
    return fetch(apiBase + path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || "Something went wrong. Please try again.");
        return j;
      });
    });
  }

  function el(html) { var d = document.createElement("div"); d.innerHTML = html; return d.firstElementChild; }
  function esc(s) { return (s || "").replace(/[<>&]/g, function (c) { return { "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]; }); }

  // ---------------------------------------------------------------- render shells

  function shell(title, sub, inner) {
    var wrap = standalone ? "inline" : "float";
    var closeBtn = standalone ? "" : '<button class="x" aria-label="Close">×</button>';
    return (
      '<div class="panel ' + wrap + '" role="dialog" aria-label="Contact us">' +
      '<div class="hd" style="position:relative">' + closeBtn +
      "<h2>" + esc(title) + "</h2>" + (sub ? "<p>" + esc(sub) + "</p>" : "") + "</div>" +
      '<div class="bd">' + inner + "</div>" +
      '<div class="foot">Powered by Adaptive Intake</div></div>'
    );
  }

  function renderLauncher() {
    mount.innerHTML = "";
    if (standalone) { renderSubmit(); return; }
    var b = el('<button class="launch" aria-haspopup="dialog">' + (token ? "Track your case" : "Contact us") + "</button>");
    b.onclick = function () { open = true; token ? renderStatus() : renderSubmit(); };
    mount.appendChild(b);
  }

  function wireClose() {
    var x = root.querySelector(".x");
    if (x) x.onclick = function () { open = false; renderLauncher(); };
  }

  // ---------------------------------------------------------------- screen 1: submit

  function renderSubmit() {
    var voiceSupported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
    mount.innerHTML = shell(
      "Tell us what happened",
      "No forms. In your own words.",
      '<textarea id="t" aria-label="Describe what went wrong" placeholder="Tell us what went wrong. Type it, paste it, or record it — no forms."></textarea>' +
      '<div class="tools">' +
      (voiceSupported ? '<button class="rec" id="rec"><span class="dot"></span><span id="reclbl">Record</span></button>' : "") +
      '<label class="file"><input type="file" id="f" accept="image/*,audio/*,application/pdf,.pdf,.txt" multiple style="max-width:200px"></label>' +
      "</div>" +
      '<div id="err"></div>' +
      '<button class="send" id="go">Send it</button>' +
      '<p class="hint">A person on our team will see this. You’ll get a link to check on it.</p>'
    );
    wireClose();
    if (voiceSupported) wireVoice();
    var go = root.getElementById("go");
    go.onclick = submit;
  }

  function wireVoice() {
    var btn = root.getElementById("rec"), lbl = root.getElementById("reclbl");
    btn.onclick = function () {
      if (recorder && recorder.state === "recording") { recorder.stop(); return; }
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
        var mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
        recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
        chunks = [];
        recorder.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
        recorder.onstop = function () {
          stream.getTracks().forEach(function (t) { t.stop(); });
          clearInterval(recTimer);
          recBlob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          btn.classList.remove("on"); lbl.textContent = "Recorded ✓ (tap to redo)";
        };
        recorder.start();
        recSecs = 0; btn.classList.add("on"); lbl.textContent = "Recording 0:00 — tap to stop";
        recTimer = setInterval(function () {
          recSecs++; lbl.textContent = "Recording 0:" + (recSecs < 10 ? "0" : "") + recSecs + " — tap to stop";
          if (recSecs >= 120) recorder.stop();
        }, 1000);
      }).catch(function () {
        // permission denied / unavailable — never a dead button; text stays primary (PORTAL.md §12)
        btn.outerHTML = '<span class="file">Mic access is off — just type it instead.</span>';
      });
    };
  }

  function submit() {
    var text = (root.getElementById("t").value || "").trim();
    var files = root.getElementById("f").files;
    if (!text && !files.length && !recBlob) { showErr("Tell us what went wrong, or attach a file."); return; }
    var fd = new FormData();
    fd.append("key", key);
    fd.append("text", text);
    for (var i = 0; i < files.length; i++) fd.append("files", files[i]);
    if (recBlob) {
      var ext = (recBlob.type.indexOf("mp4") >= 0) ? "mp4" : (recBlob.type.indexOf("ogg") >= 0 ? "ogg" : "webm");
      fd.append("files", recBlob, "voice-note." + ext);
    }
    var go = root.getElementById("go"); go.disabled = true; go.textContent = "Sending…";
    api("/submit", { method: "POST", body: fd }).then(function (j) {
      token = j.token; if (!standalone) localStorage.setItem(LS, token);
      renderStatus();
    }).catch(function (e) { go.disabled = false; go.textContent = "Send it"; showErr(e.message); });
  }

  function showErr(m) { var e = root.getElementById("err"); if (e) e.innerHTML = '<div class="err">' + esc(m) + "</div>"; }

  // ---------------------------------------------------------------- screen 2: status + drill

  var poll = null;
  function renderStatus() {
    if (poll) clearInterval(poll);
    fetchStatus();
    poll = setInterval(fetchStatus, 2500);
  }

  function fetchStatus() {
    api("/case/" + token, {}).then(drawStatus).catch(function (e) {
      if (poll) clearInterval(poll);
      mount.innerHTML = shell("We couldn’t load your case", "", '<p class="sub">' + esc(e.message) + "</p>");
      wireClose();
    });
  }

  var STAGES = [
    ["received", "Received"], ["transcribing", "Transcribing your recording"],
    ["understanding", "Understanding it"], ["checking", "Checking your order"], ["ready", "Ready"]
  ];

  function drawStatus(s) {
    var inner;
    if (s.processing) {
      if (s.stalled || s.stage === "delayed") {
        inner = '<p class="sub">' + esc(s.detail) + '</p><p class="ref">Ref ' + esc(s.ref) + "</p>";
      } else {
        var cur = 0;
        for (var i = 0; i < STAGES.length; i++) if (STAGES[i][0] === s.stage) cur = i;
        var rows = STAGES.slice(0, 4).map(function (st, i) {
          var cls = i < cur ? "done" : (i === cur ? "on" : "");
          return '<div class="stage ' + cls + '"><span class="sd"></span>' + st[1] + "</div>";
        }).join("");
        inner = rows + '<p class="hint">This usually takes a few seconds — you can close this and come back.</p>';
      }
      mount.innerHTML = shell(s.headline, "", inner);
      wireClose();
      return;
    }
    if (poll) clearInterval(poll);
    var parts = "";
    if (s.understood) parts += '<div class="card">' + esc(s.understood) + "</div>";
    if (s.deadline) parts += '<div class="due">We’ll come back to you by <b>' + esc(fmtDate(s.deadline)) + "</b>.</div>";
    if (s.question) {
      parts += '<div class="q">' + esc(s.question) + "</div>";
      if (s.options && s.options.length) {
        parts += '<div class="opts">' + s.options.map(function (o) {
          return '<button class="opt" type="button">' + esc(o) + "</button>";
        }).join("") + "</div>";
      }
      parts += '<textarea id="ans" aria-label="Your answer" placeholder="…or type your answer"></textarea>' +
        '<div id="err"></div><button class="send" id="asend">Send</button>';
    }
    mount.innerHTML = shell(s.headline, s.detail, '<p class="ref">Ref ' + esc(s.ref) + "</p>" + parts);
    wireClose();
    if (s.question) wireAnswer();
  }

  function wireAnswer() {
    var ta = root.getElementById("ans");
    root.querySelectorAll(".opt").forEach(function (b) {
      b.onclick = function () {
        root.querySelectorAll(".opt").forEach(function (x) { x.classList.remove("sel"); });
        b.classList.add("sel"); ta.value = b.textContent;
      };
    });
    root.getElementById("asend").onclick = function () {
      var v = (ta.value || "").trim();
      if (!v) { showErr("Type your answer, or tap one of the options."); return; }
      var fd = new FormData(); fd.append("answer", v);
      var btn = root.getElementById("asend"); btn.disabled = true; btn.textContent = "Sending…";
      api("/case/" + token + "/answer", { method: "POST", body: fd })
        .then(function () { renderStatus(); })
        .catch(function (e) { btn.disabled = false; btn.textContent = "Send"; showErr(e.message); });
    };
  }

  function fmtDate(iso) {
    try { return new Date(iso).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" }); }
    catch (e) { return iso; }
  }

  renderLauncher();
})();
