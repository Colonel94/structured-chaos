/* Adaptive Intake — customer portal widget (PORTAL.md §12).
 * Vanilla JS, Shadow DOM, no framework, no build step. It is a CONVERSATION over intake — you tell us
 * what happened in your own words, and we work it out WITH you: for a vague or emotional opener ("i'm
 * sad", a half-formed gripe) it investigates in a short chat instead of logging a dead, empty case; once
 * the details make sense for resolution it confirms the case and hands you a reference. It is NOT a
 * chatbot — every question comes from the shared elicitation policy (the anchor + two-drill budget,
 * enforced server-side); the widget renders the exchange, it never invents a question. One
 * <script src=".../p/embed.js" data-key="..."> tag drops it in. */
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
    ".panel{background:#fff;color:#14171c;border-radius:14px;overflow:hidden;box-shadow:0 18px 60px rgba(0,0,0,.28);display:flex;flex-direction:column}" +
    ".float{position:fixed;" + pos + "z-index:2147483001;width:380px;max-width:calc(100vw - 28px);max-height:calc(100vh - 40px)}" +
    ".inline{width:100%;max-width:560px;margin:0 auto;max-height:78vh}" +
    ".hd{padding:16px 18px;background:" + accent + ";color:#fff;flex:0 0 auto}" +
    ".hd h2{margin:0;font-size:16px;font-weight:650}" +
    ".hd p{margin:3px 0 0;font-size:12.5px;opacity:.9}" +
    ".hd .x{position:absolute;top:12px;right:14px;background:none;border:0;color:#fff;font-size:20px;cursor:pointer;opacity:.9}" +
    ".bd{padding:16px 18px;overflow-y:auto}" +
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
    ".ref{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#6b7480}" +
    /* ---- conversation thread ---- */
    ".chat{display:flex;flex-direction:column;gap:0;padding:0}" +
    ".thread{flex:1 1 auto;overflow-y:auto;padding:16px 16px 8px;display:flex;flex-direction:column;gap:10px}" +
    ".msg{max-width:82%;padding:10px 13px;border-radius:14px;font-size:14.5px;line-height:1.42;white-space:pre-wrap;word-wrap:break-word}" +
    ".msg.you{align-self:flex-end;background:" + accent + ";color:#fff;border-bottom-right-radius:5px}" +
    ".msg.system{align-self:flex-start;background:#f1f3f6;color:#14171c;border-bottom-left-radius:5px}" +
    ".msg.note{align-self:center;background:#fff7ed;color:#8a5a12;border:1px solid #f2d9b3;font-size:13px;text-align:center;max-width:92%}" +
    ".msg .due{display:block;margin-top:6px;font-size:12.5px;opacity:.85}" +
    ".msg .due b{font-weight:650}" +
    ".typing{display:inline-flex;gap:4px;align-items:center}" +
    ".typing i{width:7px;height:7px;border-radius:50%;background:#9aa4b1;display:inline-block;animation:tb 1.2s infinite}" +
    ".typing i:nth-child(2){animation-delay:.2s}.typing i:nth-child(3){animation-delay:.4s}" +
    "@keyframes tb{0%,60%,100%{opacity:.3;transform:translateY(0)}30%{opacity:1;transform:translateY(-3px)}}" +
    ".typing span{font-size:12.5px;color:#6b7480;margin-left:2px}" +
    ".composer{flex:0 0 auto;border-top:1px solid #eef0f3;padding:12px 16px}" +
    ".opts{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}" +
    ".opt{border:1px solid " + accent + ";color:" + accent + ";background:#fff;border-radius:999px;padding:8px 13px;font-size:13.5px;cursor:pointer}" +
    ".opt.sel{background:" + accent + ";color:#fff}" +
    ".crow{display:flex;gap:8px;align-items:flex-end}" +
    ".crow textarea{min-height:44px;max-height:120px;flex:1 1 auto}" +
    ".csend{flex:0 0 auto;border:0;border-radius:10px;background:" + accent + ";color:#fff;font-size:14px;font-weight:650;padding:0 16px;height:44px;cursor:pointer}" +
    ".csend:disabled{opacity:.5;cursor:default}" +
    ".closed{font-size:13px;color:#5b6470;text-align:center;padding:2px 0}" +
    ".foot{padding:10px 18px;font-size:11px;color:#9aa4b1;border-top:1px solid #eef0f3;text-align:center;flex:0 0 auto}" +
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

  function shell(title, sub, inner, cls) {
    var wrap = standalone ? "inline" : "float";
    var closeBtn = standalone ? "" : '<button class="x" aria-label="Close">×</button>';
    return (
      '<div class="panel ' + wrap + '" role="dialog" aria-label="Contact us">' +
      '<div class="hd" style="position:relative">' + closeBtn +
      "<h2>" + esc(title) + "</h2>" + (sub ? "<p>" + esc(sub) + "</p>" : "") + "</div>" +
      '<div class="bd ' + (cls || "") + '">' + inner + "</div>" +
      '<div class="foot">Powered by Adaptive Intake</div></div>'
    );
  }

  function renderLauncher() {
    mount.innerHTML = "";
    if (standalone) { token ? resumeConversation() : renderSubmit(); return; }
    var b = el('<button class="launch" aria-haspopup="dialog">' + (token ? "Track your case" : "Contact us") + "</button>");
    b.onclick = function () { open = true; token ? resumeConversation() : renderSubmit(); };
    mount.appendChild(b);
  }

  function wireClose() {
    var x = root.querySelector(".x");
    if (x) x.onclick = function () { open = false; stopPoll(); renderLauncher(); };
  }

  // ---------------------------------------------------------------- screen 1: submit

  function renderSubmit() {
    var voiceSupported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
    mount.innerHTML = shell(
      "Tell us what happened",
      "In your own words — we'll take it from there.",
      '<textarea id="t" aria-label="Describe what went wrong" placeholder="Tell us what went wrong. Type it, paste it, or record it — no forms. Even a few words is fine; we&#39;ll ask if we need more."></textarea>' +
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

  // Pick a container the browser can actually record: webm/opus (Chrome/Android) else mp4/aac (iOS
  // Safari). isTypeSupported can be missing on old Safari — guard it. Empty string → let the UA choose
  // (Safari then produces mp4), and we still tag the blob so the server picks the right extension.
  function pickMime() {
    var can = window.MediaRecorder && MediaRecorder.isTypeSupported;
    if (can && MediaRecorder.isTypeSupported("audio/webm")) return "audio/webm";
    if (can && MediaRecorder.isTypeSupported("audio/mp4")) return "audio/mp4";
    return "";
  }

  function micDenied(btn) {
    // Permission denied / unavailable — NEVER a dead button; text stays primary and we say so, the
    // instant it happens, announced for a11y (PORTAL.md §12 — the iOS-Safari-iframe path is flakiest).
    btn.outerHTML =
      '<span class="file" role="status" aria-live="polite">Mic access is off — just type it instead.</span>';
  }

  function wireVoice() {
    var btn = root.getElementById("rec"), lbl = root.getElementById("reclbl");
    btn.onclick = function () {
      if (recorder && recorder.state === "recording") { recorder.stop(); return; }
      if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) { micDenied(btn); return; }
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
        var mime = pickMime();
        try {
          recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
        } catch (e) {
          // some iOS builds reject the options object outright — retry with the UA default, else degrade.
          try { recorder = new MediaRecorder(stream); }
          catch (e2) { stream.getTracks().forEach(function (t) { t.stop(); }); micDenied(btn); return; }
        }
        chunks = [];
        recorder.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
        recorder.onstop = function () {
          stream.getTracks().forEach(function (t) { t.stop(); });
          clearInterval(recTimer);
          recBlob = new Blob(chunks, { type: recorder.mimeType || mime || "audio/mp4" });
          btn.classList.remove("on"); lbl.textContent = "Recorded ✓ (tap to redo)";
        };
        recorder.start();
        recSecs = 0; btn.classList.add("on"); lbl.textContent = "Recording 0:00 — tap to stop";
        recTimer = setInterval(function () {
          recSecs++; lbl.textContent = "Recording 0:" + (recSecs < 10 ? "0" : "") + recSecs + " — tap to stop";
          if (recSecs >= 120) recorder.stop();
        }, 1000);
      }).catch(function () { micDenied(btn); });
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
    // What the customer "said" — echoed as their first chat bubble (their words, or a label for media).
    var firstMsg = text || (recBlob ? "🎤 Voice note" : "📎 " + (files.length > 1 ? files.length + " files" : "Attached file"));
    var go = root.getElementById("go"); go.disabled = true; go.textContent = "Sending…";
    api("/submit", { method: "POST", body: fd }).then(function (j) {
      token = j.token; if (!standalone) localStorage.setItem(LS, token);
      startConversation(firstMsg);
    }).catch(function (e) { go.disabled = false; go.textContent = "Send it"; showErr(e.message); });
  }

  function showErr(m) { var e = root.getElementById("err"); if (e) e.innerHTML = '<div class="err">' + esc(m) + "</div>"; }

  // ---------------------------------------------------------------- screen 2: the conversation

  var poll = null, pollStart = 0, thread = null, composer = null, typingEl = null;
  var noteShown = false, resuming = false;
  var POLL_MAX_MS = 120000; // ~2 min, then STOP — a phone left open must not hammer an unauthenticated
  //                           endpoint forever (battery + cost). We show an honest note + a manual re-check.

  // Friendly, honest labels for the "typing" indicator — derived from the real persisted stage, never a
  // fake timer (so voice reads "Transcribing…", text reads "Reading…"). PORTAL.md §4.
  var STAGE_LABEL = {
    transcribing: "Transcribing your recording…",
    understanding: "Reading what you sent…",
    checking: "Checking your records…",
    received: "Got it — reading it now…",
  };

  function chatShell(title, sub) {
    mount.innerHTML = shell(
      title, sub,
      '<div class="thread" id="thread" aria-live="polite" aria-label="Conversation"></div>' +
      '<div class="composer" id="composer"></div>',
      "chat"
    );
    wireClose();
    thread = root.getElementById("thread");
    composer = root.getElementById("composer");
    typingEl = null;
  }

  function bubble(role, html, dueHtml) {
    var b = el('<div class="msg ' + role + '">' + html + (dueHtml || "") + "</div>");
    thread.appendChild(b);
    thread.scrollTop = thread.scrollHeight;
    return b;
  }

  function showTyping(label) {
    hideTyping();
    typingEl = el('<div class="msg system typing"><i></i><i></i><i></i>' +
      (label ? '<span>' + esc(label) + "</span>" : "") + "</div>");
    thread.appendChild(typingEl);
    thread.scrollTop = thread.scrollHeight;
  }
  function hideTyping() { if (typingEl && typingEl.parentNode) typingEl.parentNode.removeChild(typingEl); typingEl = null; }

  // A fresh submit: open the chat with the customer's own words, then poll for the system's first move.
  function startConversation(firstMsg) {
    resuming = false;
    chatShell("Let’s sort this out", null);
    bubble("you", esc(firstMsg));
    beginPoll();
  }

  // A returning customer opening their link: we don't have the earlier turns client-side, so lead with a
  // short "here's where we are" and let the current status fill in the rest.
  function resumeConversation() {
    resuming = true;
    chatShell("Your case", "Here’s where things stand.");
    beginPoll();
  }

  function beginPoll() {
    noteShown = false;
    composer.innerHTML = "";
    showTyping("Got it — reading it now…");
    if (poll) clearInterval(poll);
    pollStart = Date.now();
    fetchStatus();
    poll = setInterval(fetchStatus, 2500);
  }

  function stopPoll() { if (poll) { clearInterval(poll); poll = null; } }

  function fetchStatus() {
    api("/case/" + token, {}).then(onStatus).catch(function (e) {
      stopPoll(); hideTyping();
      bubble("note", "We couldn’t load your case just now. " + esc(e.message));
      composer.innerHTML = '<button class="send" id="again">Try again</button>';
      var a = root.getElementById("again"); if (a) a.onclick = beginPoll;
    });
  }

  function onStatus(s) {
    if (s.processing) {
      if (Date.now() - pollStart > POLL_MAX_MS) {
        stopPoll(); hideTyping();
        if (!noteShown) { bubble("note", "This is taking longer than usual — we’ve got your case and we’re on it. You don’t need to resend it. Ref " + esc(s.ref)); noteShown = true; }
        composer.innerHTML = '<button class="send" id="again">Check again</button>';
        root.getElementById("again").onclick = beginPoll;
        return;
      }
      if (s.stalled || s.stage === "delayed") {
        // A stall OR a processing failure the server reported. Say so honestly, once; keep a slow watch
        // in case a genuine stall recovers (the cap above eventually stops it either way).
        hideTyping();
        if (!noteShown) { bubble("note", (s.detail || "This is taking a little longer — we’ve got it and a person will pick it up. You don’t need to resend it.") + " Ref " + esc(s.ref)); noteShown = true; }
        return;
      }
      showTyping(STAGE_LABEL[s.stage] || "Working on it…");
      return;
    }

    // Ready: elicitation has run. Either a single next question (keep the conversation going) or a
    // settled case (confirm it — this is the "logged once it makes sense" moment).
    stopPoll(); hideTyping();
    if (s.question) {
      var lead = s.understood ? esc(s.understood) + "\n\n" : "";
      bubble("system", lead + esc(s.question));
      askComposer(s.options);
    } else {
      var due = s.deadline ? '<span class="due">We’ll come back to you by <b>' + esc(fmtDate(s.deadline)) + "</b>.</span>" : "";
      var body = s.understood ? esc(s.understood) + "\n\n" : "";
      body += esc(s.detail || "Thanks — your case is with our team.");
      bubble("system", body, due);
      closedComposer(s.ref);
    }
  }

  // The composer while a question is pending: tappable options (a hint from the shared policy) + free
  // text, always. Sending re-enters intake as a continuation of the SAME case and advances the drill.
  function askComposer(options) {
    var optsHtml = (options && options.length)
      ? '<div class="opts">' + options.map(function (o) { return '<button class="opt" type="button">' + esc(o) + "</button>"; }).join("") + "</div>"
      : "";
    composer.innerHTML =
      optsHtml +
      '<div id="err"></div>' +
      '<div class="crow"><textarea id="ans" rows="1" aria-label="Your reply" placeholder="Type your reply…"></textarea>' +
      '<button class="csend" id="asend">Send</button></div>';
    var ta = root.getElementById("ans");
    ta.focus();
    root.querySelectorAll(".opt").forEach(function (b) {
      b.onclick = function () {
        root.querySelectorAll(".opt").forEach(function (x) { x.classList.remove("sel"); });
        b.classList.add("sel"); ta.value = b.textContent; ta.focus();
      };
    });
    ta.onkeydown = function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAnswer(); } };
    root.getElementById("asend").onclick = sendAnswer;
  }

  function closedComposer(ref) {
    composer.innerHTML = '<p class="closed">You can close this and come back any time with your link — nothing is lost.<br><span class="ref">Ref ' + esc(ref) + "</span></p>";
  }

  function sendAnswer() {
    var ta = root.getElementById("ans");
    var v = (ta.value || "").trim();
    if (!v) { showErr("Type your reply, or tap one of the options."); return; }
    bubble("you", esc(v));
    var fd = new FormData(); fd.append("answer", v);
    var btn = root.getElementById("asend"); btn.disabled = true;
    var box = root.getElementById("ans"); box.disabled = true;
    api("/case/" + token + "/answer", { method: "POST", body: fd })
      .then(function () { composer.innerHTML = ""; beginPoll(); })
      .catch(function (e) { btn.disabled = false; box.disabled = false; showErr(e.message); });
  }

  function fmtDate(iso) {
    try { return new Date(iso).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" }); }
    catch (e) { return iso; }
  }

  renderLauncher();
})();
