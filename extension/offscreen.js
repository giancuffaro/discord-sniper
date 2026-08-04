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
  if (msg.type === "START_LISTEN") startListen(msg.id, msg.label, msg.streamId, msg.dgKey, msg.model);
  else if (msg.type === "STOP_LISTEN") stopListen(msg.id);
  else if (msg.type === "STOP_ALL") { for (const id of Array.from(SESS.keys())) stopListen(id); }
});

async function startListen(id, label, streamId, dgKey, model) {
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

  const url = "wss://api.deepgram.com/v1/listen"
    + "?encoding=linear16&sample_rate=" + outRate + "&channels=1"
    + "&interim_results=true&smart_format=true&punctuate=true"
    + "&model=" + encodeURIComponent(model || "nova-2");
  let ws;
  try { ws = new WebSocket(url, ["token", dgKey]); }
  catch (e) { toBg({ type: "LISTEN_ERROR", id, label, why: "couldn't open Deepgram: " + (e && e.message || e) }); return; }
  ws.binaryType = "arraybuffer";
  ws.onopen = () => toBg({ type: "LISTEN_STATE", id, label, state: "listening" });
  ws.onerror = () => toBg({ type: "LISTEN_ERROR", id, label, why: "Deepgram connection error — is the key right and funded?" });
  ws.onclose = (ev) => toBg({ type: "LISTEN_STATE", id, label, state: "stopped", code: ev && ev.code });
  ws.onmessage = (ev) => {
    let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
    const alt = d && d.channel && d.channel.alternatives && d.channel.alternatives[0];
    const text = alt && alt.transcript;
    if (text && text.trim()) toBg({ type: "TRANSCRIPT", id, label, text: text.trim(), isFinal: !!d.is_final });
  };

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
