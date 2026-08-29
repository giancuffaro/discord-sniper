/* offscreen.js — captures the audio of one or MORE Discord voice tabs and
 * streams each to Deepgram for live transcription. Runs only inside the hidden
 * offscreen document (MV3 forbids MediaStream/Web Audio in the service worker).
 *
 * Multiple channels at once: Discord only lets ONE voice channel per account,
 * so you run each in its own tab (a second account, a second profile) and this
 * captures them all in parallel — one AudioContext + one Deepgram socket per
 * tab, kept in SESS keyed by the tab id. Each word we hand back is tagged with
 * the tab it came from, so the log knows which room said it.
 *
 * It NEVER trades and never touches your account — it only listens and writes
 * down what it hears. Can't be tested off your machine (needs real audio + a
 * real key), so it fails loudly, in one plain sentence.
 */

const SESS = new Map();   // id -> { ctx, ws, source, processor, stream }

function toBg(obj) {
  try { chrome.runtime.sendMessage(Object.assign({ from: "offscreen" }, obj)); }
  catch (e) { /* background asleep; nothing we can do from here */ }
}

chrome.runtime.onMessage.addListener((msg) => {
  if (!msg || msg.target !== "offscreen") return;
  if (msg.type === "START_LISTEN") startListen(msg.id, msg.label, msg.streamId, msg.dgKey, msg.model, msg.keyterms);
  else if (msg.type === "STOP_LISTEN") stopListen(msg.id);
  else if (msg.type === "STOP_ALL") { for (const id of Array.from(SESS.keys())) stopListen(id); }
});

async function startListen(id, label, streamId, dgKey, model, keyterms) {
  stopListen(id);                     // never stack two captures on one tab
  if (!streamId) { toBg({ type: "LISTEN_ERROR", id, label, why: "no tab to capture" }); return; }
  if (!dgKey) { toBg({ type: "LISTEN_ERROR", id, label, why: "no Deepgram key saved" }); return; }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: streamId } }
    });
  } catch (e) {
    toBg({ type: "LISTEN_ERROR", id, label, why: "couldn't capture the tab's audio: " + (e && e.message || e) });
    return;
  }

  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  source.connect(ctx.destination);    // capturing mutes the tab — play it back so you still hear it
  const outRate = 16000, inRate = ctx.sampleRate;

  const cleanup = () => {             // a socket that never opened must not
    try { stream.getTracks().forEach(t => t.stop()); } catch (e) {}
    try { if (ctx.state !== "closed") ctx.close(); } catch (e) {}
  };

  const makeUrl = (mdl) => {
    let u = "wss://api.deepgram.com/v1/listen"
      + "?encoding=linear16&sample_rate=" + outRate + "&channels=1"
      + "&interim_results=true&smart_format=true&punctuate=true"
      + "&diarize=true"
      + "&model=" + encodeURIComponent(mdl);
    // Keyterm prompting is a nova-3 feature: the tickers this room actually
    // trades, so "SLV" comes back as SLV and not "silver". Spelling help
    // only — nothing about what fires depends on this list.
    if (/^nova-3/.test(mdl) && Array.isArray(keyterms))
      for (const t of keyterms.slice(0, 50)) u += "&keyterm=" + encodeURIComponent(t);
    return u;
  };

  let ws = null, gotWords = false;
  const openSocket = (mdl, canFallback) => {
    let sock;
    try { sock = new WebSocket(makeUrl(mdl), ["token", dgKey]); }
    catch (e) { toBg({ type: "LISTEN_ERROR", id, label, why: "couldn't open Deepgram: " + (e && e.message || e) }); return null; }
    sock.binaryType = "arraybuffer";
    sock.onopen = () => toBg({ type: "LISTEN_STATE", id, label, state: "listening" });
    sock.onerror = () => {
      // About to fall back? Save the scary toast for a REAL dead end.
      if (!(canFallback && !gotWords))
        toBg({ type: "LISTEN_ERROR", id, label, why: "Deepgram connection error — is the key right and funded?" });
    };
    sock.onclose = (ev) => {
      const s = SESS.get(id);
      if (!s || s.ws !== sock) return;     // stopped on purpose, or replaced
      if (canFallback && !gotWords) {
        // nova-3 died before a single word — a key without nova-3 access or
        // a rejected parameter. Same tab stream, one retry on nova-2, and
        // the log says so. gotWords guards the loop: the retry never gets
        // its own retry.
        toBg({ type: "LISTEN_NOTE", id, label,
               why: "Deepgram dropped the nova-3 session before any words — retrying this room on nova-2." });
        const nw = openSocket("nova-2", false);
        if (nw) { s.ws = nw; ws = nw; return; }
      }
      toBg({ type: "LISTEN_STATE", id, label, state: "stopped", code: ev && ev.code });
    };
    sock.onmessage = (ev) => {
      let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
      const alt = d && d.channel && d.channel.alternatives && d.channel.alternatives[0];
      const text = alt && alt.transcript;
      if (text && text.trim()) {
        gotWords = true;
        // DIARIZATION (8/29, his ask "can you distinguish voices?"):
        // Deepgram tags every word with a speaker index. The utterance's
        // speaker = the majority speaker of its words. Rides out with the
        // transcript so staging and "I'm in" stay per-VOICE.
        let spk = null;
        try {
          const words = alt.words || [];
          const tally = {};
          for (const w of words)
            if (w.speaker !== undefined) tally[w.speaker] = (tally[w.speaker] || 0) + 1;
          let best = -1;
          for (const k in tally) if (tally[k] > best) { best = tally[k]; spk = parseInt(k, 10); }
        } catch (e) {}
        toBg({ type: "TRANSCRIPT", id, label, text: text.trim(),
               isFinal: !!d.is_final, speaker: spk });
      }
    };
    return sock;
  };

  const mdl0 = model || "nova-3";
  ws = openSocket(mdl0, /^nova-3/.test(mdl0));
  if (!ws) { cleanup(); return; }

  const processor = ctx.createScriptProcessor(4096, 1, 1);
  source.connect(processor);
  processor.connect(ctx.destination);   // keeps the node alive; emits silence
  processor.onaudioprocess = (e) => {
    if (!ws || ws.readyState !== 1) return;
    ws.send(floatToPCM16(downsample(e.inputBuffer.getChannelData(0), inRate, outRate)));
  };

  SESS.set(id, { ctx, ws, source, processor, stream });
}

function stopListen(id) {
  const s = SESS.get(id);
  if (!s) return;
  try { if (s.processor) { s.processor.disconnect(); s.processor.onaudioprocess = null; } } catch (e) {}
  try { if (s.source) s.source.disconnect(); } catch (e) {}
  try { if (s.ws && s.ws.readyState <= 1) s.ws.close(); } catch (e) {}
  try { if (s.stream) s.stream.getTracks().forEach(t => t.stop()); } catch (e) {}
  try { if (s.ctx && s.ctx.state !== "closed") s.ctx.close(); } catch (e) {}
  SESS.delete(id);
  toBg({ type: "LISTEN_STATE", id, state: "stopped" });
}

function downsample(buf, inRate, outRate) {
  if (outRate >= inRate) return buf;
  const ratio = inRate / outRate;
  const outLen = Math.floor(buf.length / ratio);
  const out = new Float32Array(outLen);
  let pos = 0;
  for (let i = 0; i < outLen; i++) {
    const next = Math.floor((i + 1) * ratio);
    let sum = 0, cnt = 0;
    for (let j = Math.floor(pos); j < next && j < buf.length; j++) { sum += buf[j]; cnt++; }
    out[i] = cnt ? sum / cnt : 0;
    pos = next;
  }
  return out;
}

function floatToPCM16(buf) {
  const out = new Int16Array(buf.length);
  for (let i = 0; i < buf.length; i++) {
    const s = Math.max(-1, Math.min(1, buf[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return out.buffer;
}
