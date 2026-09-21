const button=document.querySelector('#call'), statusEl=document.querySelector('#status');
let current=null, configuration;
function status(text,error=false){statusEl.textContent=text;statusEl.classList.toggle('error',error);}
fetch('/api/config').then(r=>{if(!r.ok)throw Error();return r.json();}).then(c=>{
  configuration=c;
  document.querySelector('#doctor').textContent=c.doctor;
  document.querySelector('#example-doctor').textContent=c.doctor;
  document.querySelector('#timezone').textContent=c.timezone;
  if(!c.configured)status('Add your API key to .env to get started.');
}).catch(()=>status('Cannot reach the Python server. Please refresh.',true));
function stopAudio(call){for(const source of call.sources){try{source.stop();}catch{}}call.sources.clear();call.next=call.audio?.currentTime||0;}
// Silence while Jannet composes a reply must look like work in progress, never a frozen page.
function waiting(call,on){clearTimeout(call.waitTimer);if(!on)return;status('Jannet is thinking…');
  call.waitTimer=setTimeout(()=>{if(current===call&&!call.sources.size&&!call.ending)status('Still thinking… if she stays quiet, just say that again.');},9000);}
function cleanup(call,message,error=false){
  if(current!==call)return;
  current=null;clearTimeout(call.timer);clearTimeout(call.connectTimer);clearTimeout(call.waitTimer);
  call.stream?.getTracks().forEach(t=>t.stop());call.mic?.disconnect();call.input?.disconnect();call.micSilence?.disconnect();
  stopAudio(call);call.socket?.close();call.audio?.close().catch(()=>{});
  button.disabled=false;button.classList.remove('active');button.querySelector('span').textContent='Call Jannet';
  status(message,error);
}
function play(call,bytes){
  if(!bytes.byteLength || bytes.byteLength % 2)return;
  const view=new DataView(bytes), buffer=call.audio.createBuffer(1,bytes.byteLength/2,24000), samples=buffer.getChannelData(0);
  for(let i=0;i<samples.length;i++)samples[i]=view.getInt16(i*2,true)/32768;
  const source=call.audio.createBufferSource();source.buffer=buffer;
  const gain=call.audio.createGain();source.connect(gain);gain.connect(call.audio.destination);
  // Keep contiguous chunks contiguous; rebuffer only when the queue runs dry.
  // A short initial cushion absorbs network jitter rather than inserting gaps.
  const start=call.next>call.audio.currentTime ? call.next : call.audio.currentTime+.1;
  const end=start+buffer.duration, ramp=Math.min(.002,buffer.duration/4);
  // Tiny edge ramps prevent nonzero PCM boundaries from becoming sharp clicks.
  gain.gain.setValueAtTime(0,start);
  gain.gain.linearRampToValueAtTime(1,start+ramp);
  gain.gain.setValueAtTime(1,end-ramp);
  gain.gain.linearRampToValueAtTime(0,end);
  source.start(start);call.next=end;
  call.sources.add(source);clearTimeout(call.waitTimer);
  source.onended=()=>{source.disconnect();gain.disconnect();call.sources.delete(source);if(current===call&&!call.sources.size&&!call.ending){clearTimeout(call.waitTimer);status('Listening…');}};
  status('Jannet is speaking · You can interrupt anytime');
}

function transcript(message){
  const box=document.querySelector('#transcript');let row=box.lastElementChild;
  if(!row||row.dataset.role!==message.role){row=document.createElement('p');row.dataset.role=message.role;const label=document.createElement('strong');label.textContent=message.role+': ';row.append(label,document.createTextNode(''));box.append(row);}
  row.lastChild.textContent+=message.text;box.scrollTop=box.scrollHeight;
}
button.addEventListener('click',async()=>{
  if(current){cleanup(current,'Call ended. Thank you for calling.');return;}
  if(!configuration?.configured){status('Add GEMINI_API_KEY to .env, restart the server, then refresh.',true);return;}
  const call={sources:new Set(),next:0,ending:false,failed:false};current=call;
  button.disabled=true;status('Connecting to Jannet…');
  document.querySelector('#booking').hidden=true;document.querySelector('#transcript').replaceChildren();
  try{
    if(!navigator.mediaDevices?.getUserMedia)throw Error('Microphone access needs localhost or HTTPS.');
    call.audio=new AudioContext();await call.audio.resume();
    const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    if(current!==call){stream.getTracks().forEach(t=>t.stop());return;}call.stream=stream;
    await call.audio.audioWorklet.addModule('/static/microphone.js?v=3');
    if(current!==call)return;
    call.input=call.audio.createMediaStreamSource(stream);call.mic=new AudioWorkletNode(call.audio,'microphone');
    call.input.connect(call.mic);
    // Keep capture processing active without any microphone monitoring/feedback.
    call.micSilence=call.audio.createGain();call.micSilence.gain.value=0;
    call.mic.connect(call.micSilence);call.micSilence.connect(call.audio.destination);
    const socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/call`);call.socket=socket;socket.binaryType='arraybuffer';
    call.connectTimer=setTimeout(()=>cleanup(call,'Connection timed out. Please try again.',true),25000);
    call.mic.port.onmessage=e=>{if(call.ready&&!call.ending&&socket.readyState===WebSocket.OPEN&&socket.bufferedAmount<64000)socket.send(e.data);};
    socket.onmessage=({data})=>{
      if(current!==call)return;
      if(data instanceof ArrayBuffer){play(call,data);return;}
      const m=JSON.parse(data);
      if(m.type==='ready'){clearTimeout(call.connectTimer);call.ready=true;button.disabled=false;button.classList.add('active');button.querySelector('span').textContent='End call';document.querySelector('#conversation').hidden=false;status('Connected · Jannet will greet you');}
      if(m.type==='transcript')transcript(m);
      if(m.type==='thinking'&&!call.sources.size)waiting(call,true);
      if(m.type==='stalled'&&!call.sources.size)status('Jannet has gone quiet — reconnecting her…');
      if(m.type==='interrupted'){stopAudio(call);waiting(call,false);status('Listening…');}
      if(m.type==='turn_complete'&&!call.sources.size){waiting(call,false);status('Listening…');}
      if(m.type==='booking'){
        const panel=document.querySelector('#booking');panel.replaceChildren();panel.hidden=false;
        const heading=document.createElement('strong');heading.textContent='Appointment confirmed';panel.append(heading);
        for(const text of [new Date(m.slot).toLocaleString(undefined,{timeZone:configuration.timezone,dateStyle:'full',timeStyle:'short'})+' · '+configuration.timezone,'Patient: '+m.patient_name,'Reference: '+m.reference,'Visit: '+m.reason,'Phone: '+m.phone]){const row=document.createElement('div');row.textContent=text;panel.append(row);}
      }
      if(m.type==='error'){call.failed=true;cleanup(call,m.message,true);}
      if(m.type==='ended'){
        call.ending=true;call.stream.getTracks().forEach(t=>t.stop());status('Jannet is saying goodbye…');
        call.timer=setTimeout(()=>cleanup(call,'Thank you for calling. Take care!'),Math.max(0,(call.next-call.audio.currentTime)*1000)+350);
      }
    };
    socket.onerror=()=>cleanup(call,'Unable to connect. Check the server and try again.',true);
    socket.onclose=()=>{if(current===call&&!call.ending)cleanup(call,'Connection ended. Please call again if needed.',true);};
  }catch(error){cleanup(call,error.name==='NotAllowedError'?'Please allow microphone access, then call again.':error.name==='NotFoundError'?'No microphone found. Connect a microphone and open this page in Chrome.':error.message||'Unable to start your microphone.',true);}
});
window.addEventListener('pagehide',()=>{if(current)cleanup(current,'Call ended.');});
