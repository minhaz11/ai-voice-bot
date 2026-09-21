// Send 40ms frames to reduce microphone batching delay.
// AudioWorklet runs outside the UI thread. Average samples into 16kHz PCM frames.
class Microphone extends AudioWorkletProcessor {
  constructor() { super(); this.sum=0; this.count=0; this.phase=0; this.frame=new Int16Array(640); this.index=0; }
  process(inputs) {
    const input=inputs[0]?.[0];
    if (input) for (const sample of input) {
      this.sum+=sample; this.count++; this.phase+=16000;
      if (this.phase>=sampleRate) {
        this.phase-=sampleRate;
        const value=Math.max(-1,Math.min(1,this.sum/this.count));
        this.frame[this.index++]=value<0?value*32768:value*32767;
        this.sum=0; this.count=0;
        if(this.index===this.frame.length){this.port.postMessage(this.frame.buffer,[this.frame.buffer]);this.frame=new Int16Array(640);this.index=0;}
      }
    }
    return true;
  }
}
registerProcessor('microphone',Microphone);
