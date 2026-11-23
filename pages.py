"""Páginas HTML do MindSync: /explore (gráficos) e /checkin (labels de energia e foco).

Sem dependências externas: os gráficos são SVG desenhado em JavaScript simples.
"""

COMMON_CSS = r"""
:root{color-scheme:dark;--bg:#0e0e0d;--surface:#1a1a19;--surface2:#232321;--grid:#2c2c2a;--axis:#3d3d3a;
--text:#f0efec;--text2:#c3c2b7;--muted:#8f8e86;--accent:#3987e5;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s5:#d55181;--s6:#0ca30c;--s7:#9085e9}
@media (prefers-color-scheme:light){:root{color-scheme:light;--bg:#f4f3f0;--surface:#fcfcfb;--surface2:#f0efec;
--grid:#e7e6e1;--axis:#d3d2cb;--text:#0b0b0b;--text2:#52514e;--muted:#74736c;--accent:#2a78d6;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s5:#e87ba4;--s6:#008300;--s7:#6250d6}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;line-height:1.4}
a{color:var(--accent)}
"""

EXPLORE_HTML = r"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MindSync - Dados</title>
<style>
""" + COMMON_CSS + r"""
.wrap{max-width:1100px;margin:0 auto;padding:24px 20px 60px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:18px}
h1{font-size:22px;margin:0;font-weight:650}
.sub{color:var(--muted);font-size:13px;margin-top:2px}
.links a{font-size:13px;margin-left:14px;text-decoration:none}
.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:18px}
select,button.btn{background:var(--surface);color:var(--text);border:1px solid var(--axis);border-radius:8px;padding:8px 12px;font-size:14px;font-family:inherit}
button.btn{cursor:pointer}
button.btn:hover,select:hover{border-color:var(--muted)}
button.btn[aria-expanded="true"]{border-color:var(--accent)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:18px}
.tile{background:var(--surface);border-radius:12px;padding:14px 16px}
.tile .l{color:var(--text2);font-size:13px}
.tile .v{font-size:28px;font-weight:650;margin-top:2px}
.tile .v small{font-size:14px;font-weight:500;color:var(--text2);margin-left:4px}
.tile .d{color:var(--muted);font-size:12px;margin-top:2px}
.card{background:var(--surface);border-radius:12px;padding:14px 16px 8px;margin-bottom:14px;transition:opacity .15s}
.loading .card,.loading .tiles{opacity:.5}
.card h2{font-size:15px;margin:0;font-weight:600}
.card .u{color:var(--muted);font-size:13px;font-weight:400;margin-left:6px}
.legend{display:flex;gap:16px;margin:6px 0 0;font-size:13px;color:var(--text2);flex-wrap:wrap}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{display:inline-block;width:14px;height:3px;border-radius:2px}
.note{color:var(--muted);font-size:12px;margin:2px 0 6px}
.empty{color:var(--muted);padding:26px 0;text-align:center;font-size:14px}
svg{display:block;width:100%;height:auto;touch-action:pan-y}
svg:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
svg text{font-family:inherit;font-size:11px;fill:var(--muted)}
#tip{position:fixed;display:none;pointer-events:none;background:var(--surface2);border:1px solid var(--axis);border-radius:8px;padding:8px 10px;font-size:12px;min-width:150px;z-index:10;box-shadow:0 4px 18px rgba(0,0,0,.35)}
#tip .th{color:var(--text2);margin-bottom:4px}
#tip .tr{display:flex;align-items:center;gap:8px;margin-top:3px}
#tip .key{display:inline-block;width:12px;height:3px;border-radius:2px;flex:none}
#tip .tv{font-weight:650;font-size:14px;color:var(--text)}
#tip .tn{color:var(--text2)}
#tip .tnote{color:var(--muted);margin-top:5px;max-width:240px}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--grid)}
th:first-child,td:first-child{text-align:left}
th{color:var(--text2);font-weight:600}
#tablecard{display:none}
</style>
</head>
<body>
<div class="wrap" id="root">
<header>
  <div><h1>MindSync - Dados</h1><div class="sub">Blocos de 15 min a partir das janelas de 5 s (horas de Lisboa)</div></div>
  <div class="links"><a id="lnkDash" href="#">Estado</a><a id="lnkCheck" href="#">Check-in</a></div>
</header>
<div class="filters">
  <select id="selUser" aria-label="Utilizador"></select>
  <select id="selDate" aria-label="Dia"></select>
  <button class="btn" id="btnRefresh" type="button">Atualizar</button>
  <button class="btn" id="btnTable" type="button" aria-expanded="false">Ver tabela</button>
</div>
<div id="msg" class="empty" style="display:none"></div>
<div id="content">
  <div class="tiles" id="tiles"></div>
  <div class="card"><h2>Velocidade de escrita<span class="u">teclas por minuto ativo</span></h2><div id="c_speed"></div></div>
  <div class="card"><h2>Pausas e correções<span class="u">por minuto ativo de escrita</span></h2>
    <div class="legend" id="lg_rhythm"></div><div id="c_rhythm"></div></div>
  <div class="card"><h2>Retidão do rato<span class="u">% (100 = linha reta)</span></h2><div id="c_mouse"></div></div>
  <div class="card"><h2>Check-ins<span class="u">1 a 5</span></h2>
    <div class="legend" id="lg_check"></div><div id="c_check"></div></div>
  <div class="card" id="tablecard"><h2>Tabela de blocos</h2><div style="overflow-x:auto" id="tablebox"></div></div>
</div>
</div>
<div id="tip" role="status"></div>
<script>
(function(){
const Q=new URLSearchParams(location.search), TOKEN=Q.get('token')||'';
const $=(s,r)=>(r||document).querySelector(s);
const NS='http://www.w3.org/2000/svg';
function S(tag,attrs,parent,text){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(text!=null)e.textContent=text;if(parent)parent.appendChild(e);return e;}
function D(tag,cls,parent,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;if(parent)parent.appendChild(e);return e;}
const cssVar=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const pad=n=>String(n).padStart(2,'0');
const fmtMin=m=>pad(Math.floor(m/60))+':'+pad(m%60);
const fmtDate=s=>s.slice(8,10)+'/'+s.slice(5,7)+'/'+s.slice(0,4);
const num=(v,dec)=>v==null?'-':Number(v).toLocaleString('pt-PT',{maximumFractionDigits:dec||0,minimumFractionDigits:dec||0});
const MIN_RELIABLE_NOTE='Menos de 2 min de escrita ativa neste bloco: valor pouco fiável.';

let meta=null, day=null, user=null, date=null, hover=null, charts=[];
const x={x0:0,x1:1440};

async function api(path,params){
  const u=new URL(path,location.origin);u.searchParams.set('token',TOKEN);
  for(const k in (params||{}))u.searchParams.set(k,params[k]);
  const r=await fetch(u);if(!r.ok)throw new Error('Erro '+r.status);return r.json();
}

const CFG=[
 {id:'speed',box:'#c_speed',kind:'bar',kb:true,series:[{key:'typing_kpm',name:'Teclas por minuto',color:'--s1',dec:0,unit:' teclas/min'}]},
 {id:'rhythm',box:'#c_rhythm',kind:'line',kb:true,series:[
   {key:'pauses_per_min',name:'Micro-pausas',color:'--s2',dec:1,unit:' /min'},
   {key:'corr_eps_per_min',name:'Episódios de correção',color:'--s3',dec:1,unit:' /min'}]},
 {id:'mouse',box:'#c_mouse',kind:'line',yMax:100,series:[{key:'straightness_pct',name:'Retidão da trajetória',color:'--s5',dec:0,unit:' %'}],
   extra:[{key:'mouse_speed_px_s',name:'Velocidade do rato',dec:0,unit:' px/s'}]}
];

function niceTicks(max,n){
  n=n||4;const raw=max/n;const p=Math.pow(10,Math.floor(Math.log10(raw)));const f=raw/p;
  const step=(f<=1?1:f<=2?2:f<=5?5:10)*p;const top=Math.ceil(max/step-1e-9)*step;const t=[];
  for(let v=0;v<=top+1e-9;v+=step)t.push(+v.toFixed(6));return t;
}
function xTicks(pw){const span=x.x1-x.x0,maxT=Math.max(2,Math.floor(pw/62));let step=60;[60,120,180,240,360].some(s=>{step=s;return span/s+1<=maxT;});const t=[];for(let m=x.x0;m<=x.x1;m+=step)t.push(m);return t;}

/* ---------- tooltip ---------- */
const tip=$('#tip');
function showTip(head,rows,note,px,py){
  tip.innerHTML='';D('div','th',tip,head);
  rows.forEach(r=>{const row=D('div','tr',tip);if(r.color){const k=D('span','key',row);k.style.background=r.color;}
    D('span','tv',row,r.value);D('span','tn',row,r.name);});
  if(note)D('div','tnote',tip,note);
  tip.style.display='block';
  const w=tip.offsetWidth,hh=tip.offsetHeight;
  let l=px+14,t=py+14;if(l+w>innerWidth-8)l=px-w-14;if(t+hh>innerHeight-8)t=py-hh-14;
  tip.style.left=Math.max(8,l)+'px';tip.style.top=Math.max(8,t)+'px';
}
function hideTip(){tip.style.display='none';}

/* ---------- gráficos de blocos ---------- */
function geom(box){const W=Math.max(320,box.clientWidth||800);const H=W<520?170:190;return{W:W,H:H,m:{l:44,r:22,t:10,b:24}};}
function drawChart(c){
  const box=$(c.box);box.innerHTML='';
  const blocks=day.blocks;
  const g=geom(box),W=g.W,H=g.H,m=g.m,pw=W-m.l-m.r,ph=H-m.t-m.b;
  const vals=[];c.series.forEach(s=>blocks.forEach(b=>{if(b[s.key]!=null)vals.push(b[s.key]);}));
  const ticks=c.yMax?[0,25,50,75,100]:niceTicks(Math.max.apply(null,vals.concat([1])));
  const ymax=ticks[ticks.length-1];
  const xs=v=>m.l+(v-x.x0)/(x.x1-x.x0)*pw, ys=v=>m.t+ph-(v/ymax)*ph;
  const svg=S('svg',{viewBox:'0 0 '+W+' '+H,role:'img',tabindex:'0','aria-label':c.series.map(s=>s.name).join(' e ')+' ao longo do dia. Usa as setas para ler cada bloco.'},box);
  ticks.forEach(t=>{S('line',{x1:m.l,x2:W-m.r,y1:ys(t),y2:ys(t),stroke:cssVar('--grid'),'stroke-width':1},svg);
    S('text',{x:m.l-8,y:ys(t)+4,'text-anchor':'end'},svg,num(t,0));});
  xTicks(pw).forEach(t=>S('text',{x:xs(t),y:H-6,'text-anchor':'middle'},svg,fmtMin(t%1440)));
  S('line',{x1:m.l,x2:W-m.r,y1:ys(0),y2:ys(0),stroke:cssVar('--axis'),'stroke-width':1},svg);
  const surface=cssVar('--surface');
  if(c.kind==='bar'){
    const s=c.series[0],col=cssVar(s.color),sw=15/(x.x1-x.x0)*pw,bw=Math.max(2,Math.min(24,sw-2));
    blocks.forEach(b=>{const v=b[s.key];if(v==null)return;
      const hgt=Math.max(1,(v/ymax)*ph),cx=xs(b.local_min+7.5),x0=cx-bw/2,y0=ys(0)-hgt,r=Math.min(4,bw/2,hgt);
      S('path',{d:'M'+x0+','+(y0+hgt)+' L'+x0+','+(y0+r)+' Q'+x0+','+y0+' '+(x0+r)+','+y0+' L'+(x0+bw-r)+','+y0+' Q'+(x0+bw)+','+y0+' '+(x0+bw)+','+(y0+r)+' L'+(x0+bw)+','+(y0+hgt)+' Z',
        fill:col,opacity:b.reliable?1:0.35},svg);});
  }else{
    c.series.forEach(s=>{
      const col=cssVar(s.color);let seg=[];const flush=()=>{if(seg.length>1)S('polyline',{points:seg.map(p=>p.join(',')).join(' '),fill:'none',stroke:col,'stroke-width':2,'stroke-linejoin':'round','stroke-linecap':'round'},svg);seg=[];};
      let prev=null;
      blocks.forEach(b=>{const v=b[s.key];
        if(v==null||(prev!=null&&b.local_min-prev>15)){flush();}
        if(v!=null){seg.push([xs(b.local_min+7.5),ys(v)]);prev=b.local_min;}else prev=null;});
      flush();
      blocks.forEach(b=>{const v=b[s.key];if(v==null)return;
        S('circle',{cx:xs(b.local_min+7.5),cy:ys(v),r:4,fill:col,stroke:surface,'stroke-width':2,opacity:(c.kb&&!b.reliable)?0.4:1},svg);});
    });
  }
  const xh=S('line',{y1:m.t,y2:m.t+ph,stroke:cssVar('--muted'),'stroke-width':1,style:'display:none'},svg);
  const ov=S('rect',{x:m.l,y:m.t,width:pw,height:ph,fill:'transparent'},svg);
  const chart={cfg:c,svg:svg,xh:xh,xs:xs,m:m,W:W,pw:pw};charts.push(chart);
  function idxAt(clientX){const r=svg.getBoundingClientRect();const px=(clientX-r.left)*(W/r.width);
    const mn=x.x0+(px-m.l)/pw*(x.x1-x.x0);let best=null,bd=1e9;
    blocks.forEach((b,i)=>{const d=Math.abs(b.local_min+7.5-mn);if(d<bd){bd=d;best=i;}});return bd<=10?best:null;}
  function show(i,cx,cy){hover=i;syncHover();if(i==null){hideTip();return;}
    const b=blocks[i];const rows=c.series.map(s=>({value:b[s.key]==null?'-':num(b[s.key],s.dec)+s.unit,name:s.name,color:cssVar(s.color)}));
    (c.extra||[]).forEach(s=>{if(b[s.key]!=null)rows.push({value:num(b[s.key],s.dec)+s.unit,name:s.name});});
    showTip(fmtMin(b.local_min)+' a '+fmtMin(b.local_min+15),rows,(c.kb&&!b.reliable)?MIN_RELIABLE_NOTE:null,cx,cy);}
  ov.addEventListener('pointermove',e=>show(idxAt(e.clientX),e.clientX,e.clientY));
  ov.addEventListener('pointerleave',()=>show(null));
  svg.addEventListener('keydown',e=>{if(!blocks.length)return;
    if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();
      let i=hover==null?(e.key==='ArrowRight'?0:blocks.length-1):hover+(e.key==='ArrowRight'?1:-1);
      i=Math.max(0,Math.min(blocks.length-1,i));const r=svg.getBoundingClientRect();
      show(i,r.left+xs(blocks[i].local_min+7.5)*(r.width/W),r.top+r.height/2);}
    if(e.key==='Escape')show(null);});
  svg.addEventListener('blur',()=>show(null));
}
function syncHover(){
  charts.forEach(ch=>{if(!ch.cfg.kind)return;
    if(hover==null||ch.cfg.id==='check'){ch.xh.style.display='none';return;}
    const b=day.blocks[hover],px=ch.xs(b.local_min+7.5);
    ch.xh.setAttribute('x1',px);ch.xh.setAttribute('x2',px);ch.xh.style.display='';});
}

/* ---------- check-ins ---------- */
function drawCheck(){
  const box=$('#c_check');box.innerHTML='';const lg=$('#lg_check');lg.innerHTML='';
  const labs=day.labels;
  if(!labs.length){D('div','empty',box,'Sem check-ins neste dia.');return;}
  [['Energia','--s6'],['Foco','--s7']].forEach(p=>{const s=D('span','',lg);const i=D('i','',s);i.style.background=cssVar(p[1]);D('span','',s,p[0]);});
  const g=geom(box),W=g.W,H=g.H,m=g.m,pw=W-m.l-m.r,ph=H-m.t-m.b;
  const xs=v=>m.l+(v-x.x0)/(x.x1-x.x0)*pw, ys=v=>m.t+ph-((v-1)/4)*ph;
  const svg=S('svg',{viewBox:'0 0 '+W+' '+H,role:'img','aria-label':'Check-ins de energia e foco ao longo do dia'},box);
  [1,2,3,4,5].forEach(t=>{S('line',{x1:m.l,x2:W-m.r,y1:ys(t),y2:ys(t),stroke:cssVar('--grid'),'stroke-width':1},svg);S('text',{x:m.l-8,y:ys(t)+4,'text-anchor':'end'},svg,String(t));});
  xTicks(pw).forEach(t=>S('text',{x:xs(t),y:H-6,'text-anchor':'middle'},svg,fmtMin(t%1440)));
  const surface=cssVar('--surface');
  [['slot_1','--s6'],['slot_2','--s7']].forEach(p=>{const col=cssVar(p[1]);
    const pts=labs.filter(l=>l[p[0]]!=null).map(l=>[xs(l.local_min),ys(l[p[0]])]);
    if(pts.length>1)S('polyline',{points:pts.map(q=>q.join(',')).join(' '),fill:'none',stroke:col,'stroke-width':2,'stroke-linejoin':'round','stroke-linecap':'round'},svg);
    pts.forEach(q=>S('circle',{cx:q[0],cy:q[1],r:p[0]==='slot_1'?7:4.5,fill:col,stroke:surface,'stroke-width':2},svg));});
  const ov=S('rect',{x:m.l,y:m.t,width:pw,height:ph,fill:'transparent'},svg);
  ov.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect();const px=(e.clientX-r.left)*(W/r.width);
    let best=null,bd=1e9;labs.forEach(l=>{const d=Math.abs(xs(l.local_min)-px);if(d<bd){bd=d;best=l;}});
    if(!best||bd>24*(W/r.width)){hideTip();return;}
    const rows=[];if(best.slot_1!=null)rows.push({value:String(best.slot_1),name:'Energia',color:cssVar('--s6')});
    if(best.slot_2!=null)rows.push({value:String(best.slot_2),name:'Foco',color:cssVar('--s7')});
    showTip(best.local_time,rows,best.notes||null,e.clientX,e.clientY);});
  ov.addEventListener('pointerleave',hideTip);
}

/* ---------- tiles e tabela ---------- */
function tile(l,v,unit,d){const t=D('div','tile',$('#tiles'));D('div','l',t,l);const vv=D('div','v',t,v);if(unit)D('small','',vv,unit);if(d)D('div','d',t,d);}
function drawTiles(){
  const T=$('#tiles');T.innerHTML='';const B=day.blocks;
  const act=B.reduce((a,b)=>a+(b.active_s||0),0)/60;
  let w=0,ws=0;B.forEach(b=>{if(b.typing_kpm!=null&&b.kb_active_s>0){w+=b.typing_kpm*b.kb_active_s;ws+=b.kb_active_s;}});
  const rel=B.filter(b=>b.reliable).length;
  tile('Tempo ativo',num(act,0),'min','Teclado ou rato, janelas de 5 s');
  tile('Velocidade média',ws?num(w/ws,0):'-','teclas/min','Ponderada pelo tempo de escrita');
  tile('Blocos fiáveis',rel+' / '+B.length,'','Fiável = pelo menos 2 min de escrita ativa');
  const b=day.bio;
  if(b){const h=Math.floor((b.total_sleep_min||0)/60),mm=Math.round((b.total_sleep_min||0)%60);
    tile('Sono',h+'h '+pad(mm),'',b.device_brand+' · profundo '+num(b.deep_sleep_min,0)+' min · REM '+num(b.rem_sleep_min,0)+' min · HRV '+num(b.hrv_rmssd_ms,0)+' ms');}
  else tile('Sono','-','','Sem dados de wearable neste dia');
}
function drawTable(){
  const box=$('#tablebox');box.innerHTML='';const t=D('table','',box);const hr=D('tr','',D('thead','',t));
  ['Bloco','Ativo (min)','Teclas/min','Pausas/min','Correções/min','Retidão (%)','Rato (px/s)','Fiável'].forEach(h=>D('th','',hr,h));
  const tb=D('tbody','',t);
  day.blocks.forEach(b=>{const r=D('tr','',tb);
    [fmtMin(b.local_min),num(b.active_s/60,1),num(b.typing_kpm,0),num(b.pauses_per_min,1),num(b.corr_eps_per_min,1),num(b.straightness_pct,0),num(b.mouse_speed_px_s,0),b.reliable?'sim':'não'].forEach(v=>D('td','',r,v));});
}

/* ---------- ciclo ---------- */
function computeDomain(){
  const mins=[];day.blocks.forEach(b=>{mins.push(b.local_min,b.local_min+15);});day.labels.forEach(l=>mins.push(l.local_min));
  if(!mins.length){x.x0=480;x.x1=1200;return;}
  let a=Math.floor(Math.min.apply(null,mins)/60)*60,b=Math.ceil(Math.max.apply(null,mins)/60)*60;
  if(b-a<360){b=Math.min(1440,a+360);a=Math.max(0,b-360);}x.x0=a;x.x1=b;
}
function renderCharts(){
  charts=[];hover=null;hideTip();
  CFG.forEach(drawChart);drawCheck();
}
function render(){
  const empty=!day.blocks.length&&!day.labels.length;
  $('#msg').style.display=empty?'block':'none';$('#content').style.display=empty?'none':'block';
  if(empty){$('#msg').textContent='Sem dados para este utilizador neste dia.';return;}
  computeDomain();drawTiles();renderCharts();drawTable();
  const lg=$('#lg_rhythm');lg.innerHTML='';CFG[1].series.forEach(s=>{const sp=D('span','',lg);const i=D('i','',sp);i.style.background=cssVar(s.color);D('span','',sp,s.name);});
}
async function loadDay(){
  $('#root').classList.add('loading');
  try{day=await api('/api/explore/day',{user_id:user,date:date});render();}
  catch(e){$('#msg').style.display='block';$('#msg').textContent='Não foi possível carregar os dados ('+e.message+').';$('#content').style.display='none';}
  $('#root').classList.remove('loading');
}
function fillDates(){
  const sel=$('#selDate');sel.innerHTML='';const u=meta.users.find(u=>u.user_id===user);
  (u?u.dates:[]).forEach(d=>{const o=D('option','',sel,fmtDate(d));o.value=d;});
  if(u&&u.dates.indexOf(date)<0)date=u.dates[0];sel.value=date;
}
async function init(){
  $('#lnkDash').href='/dashboard?token='+encodeURIComponent(TOKEN);
  $('#lnkCheck').href='/checkin?token='+encodeURIComponent(TOKEN)+'&user_id='+encodeURIComponent(user||'');
  try{meta=await api('/api/explore/meta');}catch(e){$('#msg').style.display='block';$('#content').style.display='none';$('#msg').textContent='Acesso negado ou servidor indisponível ('+e.message+').';return;}
  if(!meta.users.length){$('#msg').style.display='block';$('#content').style.display='none';$('#msg').textContent='Ainda sem dados.';return;}
  const su=$('#selUser');meta.users.forEach(u=>{const o=D('option','',su,u.user_id);o.value=u.user_id;});
  user=Q.get('user_id')&&meta.users.some(u=>u.user_id===Q.get('user_id'))?Q.get('user_id'):meta.users[0].user_id;su.value=user;
  date=Q.get('date')||null;fillDates();
  $('#lnkCheck').href='/checkin?token='+encodeURIComponent(TOKEN)+'&user_id='+encodeURIComponent(user);
  su.addEventListener('change',()=>{user=su.value;date=null;fillDates();loadDay();});
  $('#selDate').addEventListener('change',e=>{date=e.target.value;loadDay();});
  $('#btnRefresh').addEventListener('click',async()=>{try{meta=await api('/api/explore/meta');}catch(e){}fillDates();loadDay();});
  $('#btnTable').addEventListener('click',e=>{const open=e.target.getAttribute('aria-expanded')!=='true';e.target.setAttribute('aria-expanded',open);$('#tablecard').style.display=open?'block':'none';});
  let raf=null;new ResizeObserver(()=>{if(!day||raf)return;raf=requestAnimationFrame(()=>{raf=null;if(day.blocks.length||day.labels.length)renderCharts();});}).observe($('#root'));
  loadDay();
}
init();
})();
</script>
</body>
</html>
"""

CHECKIN_HTML = r"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MindSync - Check-in</title>
<style>
""" + COMMON_CSS + r"""
.wrap{max-width:460px;margin:0 auto;padding:22px 18px 60px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);font-size:13px;margin-bottom:22px}
.q{margin-bottom:22px}
.q h2{font-size:16px;margin:0 0 2px}
.q .hint{color:var(--muted);font-size:13px;margin-bottom:10px}
.row{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
.row button{background:var(--surface);color:var(--text);border:2px solid var(--axis);border-radius:12px;height:58px;font-size:20px;font-weight:650;cursor:pointer;font-family:inherit}
.row button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.ends{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin-top:6px}
input[type=text]{width:100%;background:var(--surface);color:var(--text);border:1px solid var(--axis);border-radius:10px;padding:12px;font-size:16px;font-family:inherit}
label{display:block;color:var(--text2);font-size:13px;margin-bottom:6px}
.send{width:100%;background:var(--accent);color:#fff;border:0;border-radius:12px;height:54px;font-size:17px;font-weight:650;cursor:pointer;margin-top:6px;font-family:inherit}
.send:disabled{opacity:.4;cursor:default}
#status{margin-top:14px;font-size:14px;min-height:20px}
.ok{color:var(--s6)}.err{color:#e66767}
ul{list-style:none;padding:0;margin:18px 0 0;color:var(--text2);font-size:14px}
li{padding:8px 0;border-bottom:1px solid var(--grid)}
</style>
</head>
<body>
<div class="wrap">
<h1>Check-in</h1>
<div class="sub">Responde em 5 segundos, de preferência a cada 60 a 90 minutos.</div>
<div class="q"><label for="user">Utilizador</label><input type="text" id="user" autocomplete="off" autocapitalize="none"></div>
<div class="q"><h2>Energia agora</h2><div class="hint">Quão desperto e com energia te sentes?</div>
  <div class="row" id="r1"></div><div class="ends"><span>Exausto</span><span>Muita energia</span></div></div>
<div class="q"><h2>Foco agora</h2><div class="hint">Quão fácil é manteres a atenção no que estás a fazer?</div>
  <div class="row" id="r2"></div><div class="ends"><span>Disperso</span><span>Muito focado</span></div></div>
<div class="q"><label for="note">Nota (opcional)</label><input type="text" id="note" maxlength="140" placeholder="Ex.: depois do café, reunião, ruído"></div>
<button class="send" id="send" type="button" disabled>Registar</button>
<div id="status" role="status"></div>
<ul id="recent" aria-label="Registos desta sessão"></ul>
</div>
<script>
(function(){
const Q=new URLSearchParams(location.search), TOKEN=Q.get('token')||'';
const $=s=>document.querySelector(s);
let v1=null,v2=null;
function store(k,v){try{if(v==null)return localStorage.getItem(k);localStorage.setItem(k,v);}catch(e){return null;}}
$('#user').value=Q.get('user_id')||store('ms_user')||'';
function makeRow(id,set){const row=$(id);for(let i=1;i<=5;i++){const b=document.createElement('button');b.type='button';b.textContent=i;b.setAttribute('aria-pressed','false');
  b.addEventListener('click',()=>{[...row.children].forEach(c=>c.setAttribute('aria-pressed','false'));b.setAttribute('aria-pressed','true');set(i);check();});row.appendChild(b);}}
function reset(){[...document.querySelectorAll('.row button')].forEach(c=>c.setAttribute('aria-pressed','false'));v1=v2=null;$('#note').value='';check();}
makeRow('#r1',v=>v1=v);makeRow('#r2',v=>v2=v);
function check(){$('#send').disabled=!(v1&&v2&&$('#user').value.trim());}
$('#user').addEventListener('input',check);
$('#send').addEventListener('click',async()=>{
  const user=$('#user').value.trim();store('ms_user',user);
  const st=$('#status');st.className='';st.textContent='A enviar...';$('#send').disabled=true;
  try{
    const r=await fetch('/api/labels',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+TOKEN},
      body:JSON.stringify({user_id:user,slot_1:v1,slot_2:v2,notes:$('#note').value.trim()||null})});
    if(!r.ok)throw new Error(r.status===401?'Token inválido':'Erro '+r.status);
    const t=new Date().toLocaleTimeString('pt-PT',{hour:'2-digit',minute:'2-digit'});
    st.className='ok';st.textContent='Registado às '+t;
    const li=document.createElement('li');li.textContent=t+'  ·  energia '+v1+'  ·  foco '+v2;$('#recent').prepend(li);reset();
  }catch(e){st.className='err';st.textContent='Falhou: '+e.message;check();}
});
})();
</script>
</body>
</html>
"""
