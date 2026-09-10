/* pcm-worklet.js — the microphone end of the voice reader, moved OFF the
 * main thread (9/10).
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * G: "when I join a voice channel everything lags out." It did, and this was
 * why. offscreen.js used ctx.createScriptProcessor(4096, 1, 1), and a
 * ScriptProcessorNode runs its callback ON THE MAIN THREAD — every 4096
 * samples, about every 85 ms, per listening tab, with no cap on how many
 * sessions run at once. He had four going. That is four main-thread audio
 * callbacks fighting the renderer, which is exactly why the whole browser
 * went treacle the moment a voice channel connected. ScriptProcessorNode has
 * been deprecated for years for precisely this reason; AudioWorklet is its
 * replacement and runs on the audio thread.
 *
 * WHAT IT DOES
 * Downsamples the tab's audio to 16 kHz, converts to little-endian signed
 * 16-bit PCM (what Deepgram's linear16 wants), and posts finished buffers to
 * offscreen.js. The main thread's only remaining job per chunk is one
 * ws.send() of an ArrayBuffer it does not have to build or touch.
 *
 * THE DOWNSAMPLE IS DELIBERATELY THE SAME NAIVE ONE the old code used —
 * nearest-sample decimation, no filter. Changing the maths and the threading
 * in one step would make a regression impossible to attribute. If aliasing
 * ever hurts the transcript, that is a separate, testable change.
 */
class PCMWorklet extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const o = (options && options.processorOptions) || {};
    this.outRate = o.outRate || 16000;
    // `sampleRate` is a global inside an AudioWorkletGlobalScope — the real
    // context rate, so nothing has to be passed in and get stale.
    this.inRate = o.inRate || sampleRate;
    this.ratio = this.inRate / this.outRate;
    // ~85 ms at 16 kHz, matching the old 4096-at-48k cadence closely enough
    // that Deepgram sees the same shape of traffic it always has.
    this.target = 1365;
    this.buf = new Int16Array(this.target);
    this.n = 0;
    this.pos = 0;               // fractional read cursor across render quanta
    this.on = true;
    this.port.onmessage = (e) => {
      if (e.data === "stop") this.on = false;
    };
  }

  process(inputs) {
    if (!this.on) return false;               // let the node be collected
    const ch = inputs[0] && inputs[0][0];
    if (!ch || !ch.length) return true;       // no input yet; stay alive

    // Walk the input at `ratio` steps, carrying the fractional position
    // across render quanta so we neither drop nor repeat a sample at the
    // boundary — the old per-callback downsample restarted at 0 every time
    // and quietly jittered the stream.
    while (this.pos < ch.length) {
      let s = ch[this.pos | 0];
      if (s > 1) s = 1; else if (s < -1) s = -1;
      this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      if (this.n >= this.target) {
        // Hand over the bytes and give up ownership — a transfer, not a
        // copy, so the main thread never allocates for audio.
        const out = this.buf.buffer;
        this.port.postMessage(out, [out]);
        this.buf = new Int16Array(this.target);
        this.n = 0;
      }
      this.pos += this.ratio;
    }
    this.pos -= ch.length;
    return true;
  }
}

registerProcessor("pcm-worklet", PCMWorklet);
