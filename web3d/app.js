"use strict";
const $=id=>document.getElementById(id), scene=$("scene");
const colors={I:"#41cee8",O:"#f7bf44",T:"#9f6fe8",J:"#4d80e3",L:"#f5803d",S:"#8dd158",Z:"#e55275"};
let state=null, stopped=false, chain=Promise.resolve(), previousEvent=-1, nextSignature="", imageURL=null, cameraPending=false;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));

function display(data){
  state=data;
  $("status").textContent=data.ready?"CONNECTED":data.phase==="error"?"STOPPED":"WARMING UP";
  if(!data.ready){
    if(data.phase==="error"){
      $("overlay").hidden=false;$("overlay-title").textContent="The renderer stopped.";
      $("overlay-copy").textContent=data.message;$("play").hidden=true;$("overlay-hint").textContent="See game3d.log for the rendering diagnostic.";
    }
    return;
  }
  $("score").textContent=String(data.score).padStart(6,"0");$("lines").textContent=data.lines;
  $("level").textContent=String(data.level).padStart(2,"0");$("pieces").textContent=data.pieces;
  $("queries").textContent=data.engine.queries.toLocaleString();$("render-ms").textContent=data.renderer.render_ms.toFixed(1)+" ms";
  $("frame-stat").textContent=Math.round(data.renderer.fps)+" FPS / RTX PATH TRACING";
  const frontal=Math.abs(data.renderer.camera[0])+Math.abs(data.renderer.camera[1])<.001;
  $("front").classList.toggle("selected",frontal);$("angle").classList.toggle("selected",!frontal);
  $("message").textContent=data.message;$("pause").textContent=data.phase==="paused"?"Resume · P":"Pause · P";
  $("overlay").hidden=data.phase==="playing";
  $("play").disabled=false;
  if(data.phase==="ready"){
    $("overlay-tag").textContent="THE NEXT DIMENSION OF PLAY";$("overlay-title").innerHTML="Make room.<br>Make your move.";
    $("overlay-copy").textContent="Fit the falling pieces. Clear a row. Watch the light scatter.";$("play").textContent="Let’s play ↗";$("overlay-hint").textContent="or press Enter";
  }else if(data.phase==="paused"){
    $("overlay-tag").textContent="TAKE YOUR TIME";$("overlay-title").textContent="Room to breathe.";
    $("overlay-copy").textContent="Your board is right where you left it.";$("play").textContent="Resume ↗";$("overlay-hint").textContent="or press P";
  }else if(data.phase==="over"){
    $("overlay-tag").textContent="EVERY STACK IS A NEW START";$("overlay-title").textContent="Another round?";
    $("overlay-copy").textContent=data.score.toLocaleString()+" points · "+data.lines+" lines cleared";$("play").textContent="Play again ↗";$("overlay-hint").textContent="or press Enter";
  }
  if(data.event_id!==previousEvent){
    if(previousEvent>=0&&data.cleared_rows.length){
      const toast=$("clear-toast");toast.textContent=["","SINGLE LINE","DOUBLE LINE","TRIPLE LINE","FOUR LINES!"][data.cleared_rows.length];
      toast.classList.remove("show");void toast.offsetWidth;toast.classList.add("show");
    }
    previousEvent=data.event_id;
  }
  const sig=data.next.map(p=>p.kind).join("");
  if(sig!==nextSignature){
    nextSignature=sig;
    $("next").innerHTML=data.next.map((p,i)=>{
      const xs=p.cells.map(c=>c[0]),ys=p.cells.map(c=>c[1]);
      const minX=Math.min(...xs),minY=Math.min(...ys),w=Math.max(...xs)-minX+1,h=Math.max(...ys)-minY+1;
      const rects=p.cells.map(([x,y])=>`<rect x="${(x-minX)*12+(60-w*12)/2}" y="${(y-minY)*12+(32-h*12)/2}" width="10.5" height="10.5" rx="1.5" fill="${colors[p.kind]}"/>`).join("");
      return `<div class="next-piece"><svg viewBox="0 0 60 32" aria-label="${p.kind} piece">${rects}</svg><small>0${i+1}</small></div>`;
    }).join("");
  }
}
function failure(error){
  if(stopped)return;
  stopped=true;$("overlay").hidden=false;$("overlay-tag").textContent="CONNECTION STOPPED";
  $("overlay-title").textContent="The game is paused.";$("overlay-copy").textContent=error.message;
  $("play").hidden=true;$("overlay-hint").textContent="Reopen Play Spatial Blocks 3D to reconnect.";
}
function action(name,extra={}){
  if(stopped||!state?.ready)return Promise.resolve();
  chain=chain.then(async()=>{
    const response=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:name,...extra})});
    const data=await response.json();if(!response.ok)throw new Error(data.error);display(data);
  }).catch(failure);
  return chain;
}
function control(name){action(name).then(()=>scene.focus({preventScroll:true}));}
$("play").onclick=()=>control("start");$("pause").onclick=()=>control("pause");$("restart").onclick=()=>control("restart");
for(const view of ["front","angle"]){$(view).onclick=()=>{control(view);$("front").classList.toggle("selected",view==="front");$("angle").classList.toggle("selected",view==="angle");};}
document.querySelectorAll("[data-action]").forEach(b=>b.onclick=()=>control(b.dataset.action));
document.addEventListener("keydown",event=>{
  if(event.ctrlKey||event.altKey||event.metaKey)return;
  const mapping={ArrowLeft:"left",ArrowRight:"right",ArrowDown:"down",ArrowUp:"rotate",KeyA:"left",KeyD:"right",KeyS:"down",KeyW:"rotate",KeyX:"rotate",KeyZ:"rotate_ccw",KeyQ:"rotate_ccw",Space:"drop",KeyP:"pause",Escape:"pause",Enter:"start",KeyR:"restart",Digit1:"front",Digit2:"angle"};
  const name=mapping[event.code];if(!name)return;
  if(event.target instanceof HTMLButtonElement&&["Enter","Space"].includes(event.code))return;
  event.preventDefault();if(event.repeat&&!["left","right","down"].includes(name))return;action(name);
});
let drag=null, orbitX=0, orbitY=0;
scene.addEventListener("pointerdown",event=>{scene.setPointerCapture(event.pointerId);drag={x:event.clientX,y:event.clientY};scene.focus({preventScroll:true});});
scene.addEventListener("pointermove",event=>{if(!drag)return;orbitX+=event.clientX-drag.x;orbitY+=event.clientY-drag.y;drag={x:event.clientX,y:event.clientY};});
scene.addEventListener("pointerup",()=>{drag=null;});scene.addEventListener("pointercancel",()=>{drag=null;});
setInterval(()=>{if(cameraPending||(!orbitX&&!orbitY))return;const dx=orbitX,dy=orbitY;orbitX=orbitY=0;cameraPending=true;action("orbit",{dx,dy}).finally(()=>cameraPending=false);},65);
scene.addEventListener("wheel",event=>{event.preventDefault();if(cameraPending)return;cameraPending=true;action("zoom",{delta:Math.max(-200,Math.min(200,event.deltaY))}).finally(()=>cameraPending=false);},{passive:false});
document.addEventListener("visibilitychange",()=>{if(document.hidden&&state?.phase==="playing")action("pause_only");});
$("exit").onclick=async()=>{
  stopped=true;
  try{await fetch("/api/shutdown",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});}catch(_){}
  $("overlay").hidden=false;$("overlay-tag").textContent="SEE YOU NEXT ROUND";$("overlay-title").textContent="Game closed.";
  $("overlay-copy").textContent="Reopen Play Spatial Blocks 3D whenever you like.";$("play").hidden=true;$("overlay-hint").textContent="You can close this window.";
};
async function poll(){
  while(!stopped){try{const r=await fetch("/api/state");if(!r.ok)throw new Error("Could not read game state");display(await r.json());}catch(e){failure(e);}await delay(250);}
}
async function frames(){
  let sequence=-1;
  while(!stopped){
    if(document.hidden){await delay(300);continue;}
    try{
      const r=await fetch("/frame.jpg?after="+sequence);
      if(r.status===204){await delay(200);continue;}
      if(!r.ok)throw new Error("The image stream stopped");
      sequence=Number(r.headers.get("X-Frame"));
      const nextURL=URL.createObjectURL(await r.blob());scene.src=nextURL;await scene.decode();
      if(imageURL)URL.revokeObjectURL(imageURL);imageURL=nextURL;
    }catch(e){failure(e);}
  }
}
poll();frames();
