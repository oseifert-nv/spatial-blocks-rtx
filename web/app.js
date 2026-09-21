"use strict";
const $ = id => document.getElementById(id);
const board = $("board"), next = $("next");
const ctx = board.getContext("2d"), preview = next.getContext("2d");
const colors = {I:"#73dce9",O:"#e8cf77",T:"#b999f1",J:"#81a4ed",L:"#efa573",S:"#b9df85",Z:"#e989a0"};
let state = null, chain = Promise.resolve(), pending = 0, disconnected = false;
let lastEvent = -1, flashUntil = 0, flashRows = [];

function resizeCanvas(canvas, context) {
  const size = canvas.getBoundingClientRect(), scale = window.devicePixelRatio || 1;
  canvas.width = Math.round(size.width * scale);
  canvas.height = Math.round(size.height * scale);
  context.setTransform(scale, 0, 0, scale, 0, 0);
  return size;
}

function rounded(context, x, y, width, height, radius) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
}

function block(context, x, y, cell, kind, ghost=false) {
  const gap = Math.max(1.5, cell * .065), size = cell-gap*2;
  const color = colors[kind];
  if (ghost) {
    context.fillStyle = color + "0c";
    context.strokeStyle = color + "75";
    context.lineWidth = 1;
    context.setLineDash([3,3]);
    rounded(context, x+gap+.5, y+gap+.5, size-1, size-1, 3);
    context.fill(); context.stroke(); context.setLineDash([]);
    return;
  }
  context.fillStyle = color;
  rounded(context, x+gap, y+gap, size, size, Math.max(2,cell*.09)); context.fill();
  context.fillStyle = "#ffffff26";
  rounded(context,x+gap+2,y+gap+2,size-4,Math.max(2,cell*.11),2);context.fill();
  context.fillStyle = "#00000012";
  rounded(context,x+gap+2,y+cell-gap-Math.max(3,cell*.12)-1,size-4,Math.max(2,cell*.1),2);context.fill();
}

function draw() {
  if (!state) return;
  const {width,height} = board.getBoundingClientRect(), cell=width/10;
  ctx.clearRect(0,0,width,height);
  ctx.fillStyle="#101823";ctx.fillRect(0,0,width,height);
  ctx.strokeStyle="#25314370";ctx.lineWidth=.5;
  for(let x=1;x<10;x++){ctx.beginPath();ctx.moveTo(x*cell,0);ctx.lineTo(x*cell,height);ctx.stroke();}
  for(let y=1;y<20;y++){ctx.beginPath();ctx.moveTo(0,y*cell);ctx.lineTo(width,y*cell);ctx.stroke();}
  ctx.fillStyle="#354357";
  for(let y=1;y<20;y++)for(let x=1;x<10;x++)ctx.fillRect(x*cell-.7,y*cell-.7,1.4,1.4);
  state.board.forEach(b=>block(ctx,b.x*cell,b.y*cell,cell,b.kind));
  if(state.phase!=="over" && state.phase!=="error")state.ghost.forEach(([x,y])=>{if(y>=0)block(ctx,x*cell,y*cell,cell,state.active.kind,true);});
  state.active.cells.forEach(([x,y])=>{if(y>=0)block(ctx,x*cell,y*cell,cell,state.active.kind);});
  const remaining=flashUntil-performance.now();
  if(remaining>0){ctx.fillStyle=`rgba(215,250,167,${Math.min(.45,remaining/650)})`;flashRows.forEach(y=>ctx.fillRect(0,y*cell,width,cell));requestAnimationFrame(draw);}
  const rect=next.getBoundingClientRect();preview.clearRect(0,0,rect.width,rect.height);
  state.next.forEach((piece,index)=>{
    const unit=Math.min(18,rect.width/15), xs=piece.cells.map(p=>p[0]),ys=piece.cells.map(p=>p[1]);
    const minX=Math.min(...xs),minY=Math.min(...ys),countX=Math.max(...xs)-minX+1,countY=Math.max(...ys)-minY+1;
    const x0=(index+.5)*rect.width/3-countX*unit/2,y0=rect.height/2-countY*unit/2;
    piece.cells.forEach(([x,y])=>block(preview,x0+(x-minX)*unit,y0+(y-minY)*unit,unit,piece.kind));
  });
}

function update(nextState) {
  state=nextState;
  $("score").textContent=String(state.score).padStart(6,"0");
  $("lines").textContent=state.lines;$("level").textContent=String(state.level).padStart(2,"0");$("pieces").textContent=state.pieces;
  $("ordinal").textContent=String(state.engine.ordinal).padStart(3,"0");
  $("objects").textContent=state.engine.objects;$("queries").textContent=state.engine.queries.toLocaleString();
  $("query-time").textContent=state.engine.query_ms.toFixed(3)+" ms";
  $("move-result").textContent=state.action_result==="Blocked"?"Move blocked":"Space checked";
  $("result-dot").style.background=state.action_result==="Blocked"?"#efa573":"#c8f27a";
  $("connection").textContent="CPU LIBRARY CONNECTED";
  $("phase-label").textContent=state.phase==="playing"?"LIVE":state.phase.toUpperCase();
  $("pause").textContent=state.phase==="paused"?"Resume":"Pause";
  $("message").textContent=state.message;
  if(state.event_id!==lastEvent){if(lastEvent>=0&&state.cleared_rows.length){flashRows=state.cleared_rows;flashUntil=performance.now()+300;}lastEvent=state.event_id;}
  const overlay=$("overlay");overlay.hidden=state.phase==="playing";
  if(state.phase==="paused"){
    $("overlay-tag").textContent="TAKE YOUR TIME";$("overlay-title").textContent="Room to breathe.";$("overlay-copy").textContent="Your board is right where you left it.";$("play").textContent="Resume ↗";$("overlay-hint").textContent="or press P";
  }else if(state.phase==="over"){
    $("overlay-tag").textContent="THAT’S A WRAP";$("overlay-title").textContent="Every stack is a new start.";$("overlay-copy").textContent=state.score.toLocaleString()+" points · "+state.lines+" lines cleared";$("play").textContent="Play again ↗";$("overlay-hint").textContent="or press Enter";
  }else if(state.phase==="ready"){
    $("overlay-tag").textContent="STACK. ROTATE. CLEAR.";$("overlay-title").innerHTML="A little space.<br>A lot of possibilities.";$("overlay-copy").textContent="Fit the falling pieces. Complete a row to make it disappear.";$("play").textContent="Let’s play ↗";$("overlay-hint").textContent="or press Enter";
  }
  draw();
}

function showError(error) {
  disconnected=true;document.body.classList.add("error");$("connection").textContent="CONNECTION STOPPED";
  $("overlay").hidden=false;$("overlay-tag").textContent="GAME PAUSED";$("overlay-title").textContent="The spatial engine stopped.";
  $("overlay-copy").textContent=error.message;$("play").hidden=true;$("overlay-hint").textContent="Reopen Play Spatial Blocks to reconnect.";
}

function action(name) {
  if(disconnected || (name==="tick" && (pending>0 || document.hidden || !state || state.phase!=="playing")))return chain;
  pending++;
  chain=chain.then(async()=>{
    if(disconnected)return;
    const response=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:name})});
    const data=await response.json();if(!response.ok)throw new Error(data.error||"The request failed.");update(data);
  }).catch(showError).finally(()=>{pending--;});
  return chain;
}

function control(name) {
  action(name).then(()=>board.focus({preventScroll:true}));
}
$("play").addEventListener("click",()=>control("start"));
$("pause").addEventListener("click",()=>control("pause"));
$("restart").addEventListener("click",()=>control("restart"));
document.querySelectorAll("[data-action]").forEach(button=>button.addEventListener("click",()=>control(button.dataset.action)));
document.addEventListener("keydown",event=>{
  if(event.ctrlKey||event.metaKey||event.altKey)return;
  const mapping={ArrowLeft:"left",ArrowRight:"right",ArrowDown:"down",ArrowUp:"rotate",KeyA:"left",KeyD:"right",KeyS:"down",KeyW:"rotate",KeyX:"rotate",KeyZ:"rotate_ccw",KeyQ:"rotate_ccw",Space:"drop",KeyP:"pause",Escape:"pause",Enter:"start",KeyR:"restart"};
  const name=mapping[event.code];if(!name)return;
  if(event.target instanceof HTMLButtonElement&&(event.code==="Enter"||event.code==="Space"))return;
  event.preventDefault();if(event.repeat&&!['left','right','down'].includes(name))return;action(name);
});
document.addEventListener("visibilitychange",()=>{if(document.hidden&&state&&state.phase==="playing")action("pause_only");});
$("exit").addEventListener("click",async()=>{
  if(disconnected)return;
  await action("pause_only");disconnected=true;
  try{await fetch("/api/shutdown",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});}catch(_){}
  $("overlay").hidden=false;$("overlay-tag").textContent="SEE YOU NEXT ROUND";$("overlay-title").textContent="Game closed.";$("overlay-copy").textContent="You can close this window. Reopen Play Spatial Blocks whenever you like.";$("play").hidden=true;$("overlay-hint").textContent="";$("connection").textContent="OFFLINE";
});
const resize=()=>{resizeCanvas(board,ctx);resizeCanvas(next,preview);draw();};
new ResizeObserver(resize).observe(board.parentElement);new ResizeObserver(resize).observe(next);
fetch("/api/state").then(response=>{if(!response.ok)throw new Error("Could not load the game.");return response.json();}).then(update).catch(showError);
setInterval(()=>action("tick"),80);
