import re
h=open('leaders-final.html').read()
B='https://aibruh-big-proppa-live.hf.space'
items=[('THE ODDS','/odds'),('MATCHUPS','/matchups'),('RAMP','/ramp'),('COLLEGE','/college'),('THROWDOWN THURSDAY','/throwdown'),('MONDAY NIGHT','/monday'),('SUNDAY NIGHT','/sunday-night'),('SUNDAY SLIPS','/parlays'),('ENGINE','/engine'),('NEWS','/news')]
menu=''.join(f'<a role="menuitem" href="{B}{u}" target="_blank" rel="noopener">{l}</a>' for l,u in items)
nav=f'''<nav class="bpnav" aria-label="Main">
  <a class="home" href="{B}/home/index.html" target="_blank" rel="noopener">HOME</a>
  <a class="on" href="{B}/leaders?cat=targets" target="_blank" rel="noopener">LEADERS · TARGETS</a>
  <a href="{B}/queries" target="_blank" rel="noopener">QUERIES</a>
  <a class="boo" href="{B}/myboo" target="_blank" rel="noopener">MY BOO</a>
  <div class="navdd" id="navdd"><button type="button" id="navdd-btn" aria-haspopup="menu" aria-expanded="false">THE ODDS <span id="navdd-caret">▾</span></button><div class="navdd-menu" id="navdd-menu" role="menu" hidden>{menu}</div></div>
</nav>
'''
h=re.sub(r'<nav class="bpnav".*?</nav>\n',lambda m:nav,h,count=1,flags=re.S)
css='''
.navdd{position:relative;}
.navdd button{display:inline-flex;align-items:center;height:30px;padding:0 13px;border-radius:999px;border:1px solid var(--border2);background:var(--surface);color:var(--fg);font:inherit;font-size:11px;font-weight:700;letter-spacing:.1em;cursor:pointer;}
.navdd button:hover,.navdd button[aria-expanded="true"]{border-color:#c9a54e;color:#f1dc92;}
.navdd-menu{position:absolute;top:36px;left:50%;transform:translateX(-50%);z-index:50;min-width:220px;display:flex;flex-direction:column;gap:2px;padding:6px;background:#0b0b0c;border:1px solid #c9a54e;border-radius:12px;box-shadow:0 12px 32px rgba(0,0,0,.6);}
.navdd-menu[hidden]{display:none;}
.navdd-menu a{height:auto;padding:8px 12px;border:0;border-radius:8px;background:transparent;}
.navdd-menu a:hover{background:rgba(201,165,78,.14);color:#f1dc92;}
'''
h=h.replace('</style>',css+'</style>',1)
js='''
(function(){
  const btn=document.getElementById('navdd-btn'), menu=document.getElementById('navdd-menu'), caret=document.getElementById('navdd-caret');
  if(!btn) return;
  function set(o){ menu.hidden=!o; btn.setAttribute('aria-expanded',o?'true':'false'); caret.textContent=o?'▴':'▾'; }
  btn.addEventListener('click',e=>{ e.stopPropagation(); set(menu.hidden); });
  document.addEventListener('click',e=>{ if(!menu.contains(e.target)) set(false); });
  document.addEventListener('keydown',e=>{ if(e.key==='Escape') set(false); });
})();
'''
h=h.replace('// init\n',js+'\n// init\n',1)
open('leaders-final.html','w').write(h)
