/* Single-device pass-and-play. Only optional Wikipedia search makes requests. */
(function(){
'use strict';
const E=KotobaEngine,DB=KOTOBA_DATA,STORE='kotoba-party.v1',VERSION=1;
const $=id=>document.getElementById(id),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const defaultPrefs={count:3,min:0,max:100,search:false,familiar:true};
let disk={version:VERSION,prefs:{...defaultPrefs},used:[],cache:{},current:null},durable=true,storageNotice='',activePlayer=null,scene='count',busy=false,job=null,searchController=null,manualReady=false,lastFocus=null,viewEpoch=0,bulkController=null,manualReplacement=null;
const CACHE_LIMIT=3000,BULK_TIME_LIMIT=60000;
try{const text=localStorage.getItem(STORE);if(text){const p=JSON.parse(text);if(p&&p.version===1&&Array.isArray(p.used)&&p.prefs){disk={...disk,...p,prefs:{...defaultPrefs,...p.prefs},cache:p.cache||{}};disk.used=disk.used.filter(x=>typeof x==='string');if(!validCurrent(disk.current))disk.current=null;}}localStorage.setItem('kotoba-test','1');localStorage.removeItem('kotoba-test');}catch(e){durable=false;storageNotice='保存できません。ページを閉じると履歴が消えます。';}
let used=new Set(disk.used);
// Cache is only a reservoir. It never overrides the persistent used-word set.
for(const id of Object.keys(disk.cache)){const c=disk.cache[id];if(!DB.some(g=>g.id===id)||!c||!Array.isArray(c.words)){delete disk.cache[id];continue;}c.words=E.unique(c.words.filter(validEntry)).slice(0,CACHE_LIMIT);}
function validEntry(e){return e&&typeof e.w==='string'&&e.w.length<=200&&typeof e.c==='string';}
function validCurrent(c){return !c||(c.count>=2&&c.count<=50&&Number.isInteger(c.count)&&['auto','manual'].includes(c.mode)&&Array.isArray(c.entries)&&c.entries.every(e=>!e||validEntry(e))&&c.entries.length===c.count&&(!c.done||c.entries.every(validEntry)));}
function save(){disk.used=[...used];try{localStorage.setItem(STORE,JSON.stringify(disk));durable=true;return true;}catch(e){try{localStorage.setItem(STORE,JSON.stringify({...disk,cache:{}}));storageNotice='検索候補は一時保存です。お題・履歴は保存済みです。';durable=true;return true;}catch(err){durable=false;storageNotice='保存できません。ページを閉じると履歴が消える場合があります。';return false;}}}
function category(id){return id==='numbers'?'数字':id==='free'?'自由なお題':(DB.find(c=>c.id===id)||{}).name||'お題';}
function config(){return {...disk.prefs,count:Number(disk.prefs.count),min:Number(disk.prefs.min),max:Number(disk.prefs.max)};}
let builtinWordCount;
function countStats(){if(builtinWordCount===undefined){const total=new Set();for(const c of DB)for(const w of c.words)total.add(E.key(w));builtinWordCount=total.size;}return builtinWordCount;}
function onlineCount(){const s=new Set();for(const c of Object.values(disk.cache)){for(const e of c.words||[]){if(validEntry(e))s.add(E.key(e.w));}}return s.size;}
function updateHeader(){const running=!!disk.current;$('topEnd').hidden=!running;$('headerBadge').hidden=running;}
function error(text){$('error').textContent=text;$('error').hidden=!text;if(text)$('error').scrollIntoView({block:'nearest',behavior:'smooth'});}
function cancelPending(){if(job)job.abort();if(searchController)searchController.abort();if(bulkController)bulkController.abort();job=null;searchController=null;bulkController=null;busy=false;}
function setMain(html,which){cancelPending();viewEpoch++;scene=which;hideReveal(false);$('main').innerHTML=html;updateHeader();error('');$('error').hidden=true;$('storageNote').textContent=storageNotice;$('storageNote').hidden=!storageNotice;window.scrollTo(0,0);}
function bind(id,fn){const e=$(id);if(e)e.addEventListener('click',fn);}
function inputNumber(id){const s=$(id).value.trim();if(!s)return NaN;return Number(s);}
function prefInputs(){disk.prefs.min=inputNumber('minNum');disk.prefs.max=inputNumber('maxNum');E.validateRange(disk.prefs.min,disk.prefs.max);save();}
function searchSwitch(id='searchToggle'){return `<label for="${id}" class="small ${disk.prefs.search?'on':''}" style="display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:12px;cursor:pointer"><input id="${id}" type="checkbox" ${disk.prefs.search?'checked':''} style="width:20px;height:20px;min-height:20px;margin:0;accent-color:var(--accent)"><span>ネット検索 ${disk.prefs.search?'ON':'OFF'}</span></label>`;}
function hookSearchSwitch(render,id='searchToggle'){const toggle=$(id);if(!toggle)return;toggle.addEventListener('change',()=>{disk.prefs.search=toggle.checked;if(!toggle.checked)cancelPending();save();render();});}
function rangeInputs(){return `<div class="two"><label>最小値<input id="minNum" type="number" inputmode="numeric" min="0" max="1000000" step="1" value="${disk.prefs.min}"></label><label>最大値<input id="maxNum" type="number" inputmode="numeric" min="0" max="1000000" step="1" value="${disk.prefs.max}"></label></div>`;}
function historyDetails(){return `<details><summary>遊び方・出題履歴</summary><p>本人以外がお題を確認。「はい／いいえ」で答えられる質問をして、自分のお題を当てます。</p><p>内蔵 ${countStats().toLocaleString()}語 ／ 出題済み ${used.size.toLocaleString()}語</p><p>出題履歴はこのブラウザーに保存します。ゲーム終了後も同じお題を避けます。表記違い・登録済みの別名も重複扱いです。</p><p>検索ON時のみ、ジャンル・検索語をWikipediaに送信します。お題の表示中にアプリを離れると、自動で隠れます。</p><p><a href="credits.html" target="_blank" rel="noopener noreferrer">辞書・出典</a></p><button id="clearHistory" class="small danger" type="button">出題履歴を消す</button></details>`;}
function hookHistory(){bind('clearHistory',()=>{if(disk.current){error('先にゲームを終了してください。');return;}ask('出題履歴を消しますか？','同じお題が再び出るようになります。','履歴を消す',()=>{used.clear();save();renderCount();});});}
function renderCount(){setMain(`<h1>何人で遊ぶ？</h1><div class="box"><div class="count"><button id="minus" aria-label="人数を1人減らす" type="button">−</button><input id="playerCount" type="number" inputmode="numeric" min="2" max="50" step="1" value="${Number(disk.prefs.count)||3}" aria-label="プレイヤー人数"><button id="plus" aria-label="人数を1人増やす" type="button">＋</button></div><p class="center note">2〜50人</p></div><div class="stack"><button id="autoMode" class="primary wide" type="button">自動で決める</button><button id="manualMode" class="wide" type="button">みんなで決める</button></div>${historyDetails()}`,'count');const change=d=>{let n=inputNumber('playerCount');if(!Number.isInteger(n))n=3;$('playerCount').value=Math.max(2,Math.min(50,n+d));};bind('minus',()=>change(-1));bind('plus',()=>change(1));const next=manual=>{try{disk.prefs.count=E.validatePlayers(inputNumber('playerCount'));save();manual?renderManualConfig():renderGenres();}catch(e){error(e.message);}};bind('autoMode',()=>next(false));bind('manualMode',()=>next(true));hookHistory();}
function renderGenres(){const cfg=config();const btns=DB.map(c=>{let available=E.remaining(c.id,cfg,DB,disk.cache,used);return `<button type="button" class="genre" data-genre="${c.id}">${esc(c.name)}<span>未出題 ${available.toLocaleString()}語</span></button>`;}).join('');setMain(`<div class="row between"><button id="back" class="small subtle" type="button">← 人数</button><span class="badge">${cfg.count}人</span></div><h1 class="section-heading">ジャンル</h1><div class="choice-options">${searchSwitch()}<label for="familiar" class="choice-toggle ${cfg.familiar?'on':''}"><input id="familiar" type="checkbox" ${cfg.familiar?'checked':''}><span>身近なお題を優先</span></label></div><div class="two"><button id="randomSame" class="random" type="button"><strong>ランダム</strong><small>全員同じジャンル</small></button><button id="randomMixed" class="random" type="button"><strong>ランダム</strong><small>全員バラバラ</small></button></div><div class="genres">${btns}<button type="button" class="genre" data-genre="numbers">数字<span>範囲を指定</span></button></div><details id="numberSettings"><summary>数字・検索設定</summary>${rangeInputs()}<p class="note setting-label">検索候補 ${onlineCount().toLocaleString()}語 ／ 各ジャンル最大3,000語</p><div class="row"><select id="refillGenre" aria-label="候補を補充するジャンル" style="flex:1">${DB.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select><button id="refill" type="button" class="small" ${cfg.search?'':'disabled'}>追加</button><button id="cancelRefill" type="button" class="small subtle" hidden>停止</button></div><p id="refillStatus" class="searchstatus" role="status"></p></details>${historyDetails()}`,'genre');bind('back',renderCount);hookSearchSwitch(renderGenres);$('familiar').addEventListener('change',()=>{disk.prefs.familiar=$('familiar').checked;$('familiar').closest('label').classList.toggle('on',disk.prefs.familiar);save();});for(const id of ['minNum','maxNum'])$(id).addEventListener('change',()=>{try{prefInputs();error('');}catch(e){error(e.message);}});document.querySelectorAll('[data-genre]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.genre==='numbers')renderNumberConfig();else startAuto('fixed',b.dataset.genre);}));bind('randomSame',()=>startAuto('same'));bind('randomMixed',()=>startAuto('mixed'));bind('refill',bulkRefill);bind('cancelRefill',()=>{if(bulkController)bulkController.abort();});hookHistory();}
function renderNumberConfig(){setMain(`<button id="back" class="small subtle" type="button">← ジャンル</button><h1 class="section-heading">数字の範囲</h1><div class="box">${rangeInputs()}</div><button id="startNumbers" class="primary wide" type="button">スタート</button>`,'numbers');bind('back',()=>{try{prefInputs();}catch(e){}renderGenres();});bind('startNumbers',()=>{try{prefInputs();startAuto('fixed','numbers');}catch(e){error(e.message);}});}
async function startAuto(kind,genre){
  if(busy)return;
  let thisJob=null,epoch=viewEpoch;
  try{
    if($('minNum'))prefInputs();
    const cfg={...config(),kind,genre};
    E.validatePlayers(cfg.count);E.validateRange(cfg.min,cfg.max);
    cfg.plan=E.plan(cfg,DB,disk.cache,used);
    if(cfg.search&&cfg.plan.some(c=>c!=='numbers')){
      setMain('<h1>お題を準備中</h1><div class="spinner" aria-hidden="true"></div><p id="loadingStatus" class="center searchstatus" role="status">最大8秒</p><button id="skipSearch" class="wide" type="button">すぐに始める</button>','loading');
      busy=true;job=new AbortController();thisJob=job;epoch=viewEpoch;
      bind('skipSearch',()=>thisJob.abort());
      const messages=[],uniqueCats=[...new Set(cfg.plan.filter(x=>x!=='numbers'))];
      const deadline=setTimeout(()=>thisJob.abort(),8000);
      let next=0;
      async function worker(){
        while(next<uniqueCats.length&&!thisJob.signal.aborted){
          const cat=uniqueCats[next++];
          try{const r=await fetchGenre(cat,thisJob.signal);messages.push(r.added);}catch(e){}
          if(job===thisJob&&viewEpoch===epoch&&$('loadingStatus'))$('loadingStatus').textContent=`${messages.reduce((a,b)=>a+b,0)}語追加`;
        }
      }
      try{await Promise.all([worker(),worker()]);}finally{clearTimeout(deadline);}
      // Cancel/navigation invalidates the entire request, while "skip" only stops its search.
      if(job!==thisJob||viewEpoch!==epoch||scene!=='loading')return;
      busy=false;job=null;
    }
    const entries=E.draw(cfg,DB,disk.cache,used);
    for(const e of entries)used.add(E.key(e.w));
    disk.current={id:Date.now().toString(36)+'-'+E.randomInt(100000).toString(36),mode:'auto',count:cfg.count,config:cfg,entries,done:true};
    save();renderPlay();
  }catch(e){
    if(thisJob&&(viewEpoch!==epoch||(job&&job!==thisJob)))return;
    busy=false;job=null;renderGenres();error(e.message);
  }
}
function renderPlay(){manualReplacement=null;const c=disk.current;if(!c||!c.done)return renderCount();setMain(`<h1 class="play-title">本人は見ないでね</h1><div class="players">${c.entries.map((e,i)=>`<button class="player" type="button" data-player="${i}" aria-label="プレイヤー${i+1}のお題を表示"><span class="num">${i+1}</span></button>`).join('')}</div>`,'play');document.querySelectorAll('[data-player]').forEach(b=>b.addEventListener('click',()=>reveal(Number(b.dataset.player))));}
function reveal(i){const c=disk.current;if(!c||!c.done||!c.entries[i])return;activePlayer=i;lastFocus=document.activeElement;const e=c.entries[i];$('revealPlayer').textContent=`${i+1}番の人は見ないでね`;$('revealCategory').textContent=category(e.c);$('word').textContent=e.w;const source=$('source');source.replaceChildren();if(e.source==='Wikipedia'&&e.title){const a=document.createElement('a');a.textContent='日本語版Wikipedia';a.href='https://ja.wikipedia.org/wiki/'+encodeURIComponent(e.title);a.target='_blank';a.rel='noopener noreferrer';source.append(a);}$('sourceDetails').hidden=!source.hasChildNodes();$('sourceDetails').open=false;$('replaceWord').hidden=false;$('overlay').hidden=false;$('app').inert=true;document.body.style.overflow='hidden';$('hideWord').focus();try{history.pushState({kotobaReveal:true},'');}catch(e){}}
function hideReveal(back=true){if(!$('overlay'))return;const had=!$('overlay').hidden;activePlayer=null;$('word').textContent='';$('source').replaceChildren();$('overlay').hidden=true;$('app').inert=false;document.body.style.overflow='';if(had&&back&&history.state&&history.state.kotobaReveal){try{history.replaceState({kotobaReveal:false},'');}catch(e){}}if(had&&lastFocus&&document.contains(lastFocus))lastFocus.focus();}
function endRound(){hideReveal();ask('ゲームを終了しますか？','お題をリセットします。出題履歴は残ります。','終了する',()=>{if(job)job.abort();if(searchController)searchController.abort();disk.current=null;manualReady=false;manualReplacement=null;save();renderCount();});}
function ask(title,body,ok,fn){const d=$('confirmDialog');$('dialogTitle').textContent=title;$('dialogBody').textContent=body;$('dialogOk').textContent=ok;$('dialogOk').onclick=()=>{d.close();fn();};$('dialogCancel').onclick=()=>d.close();d.showModal();$('dialogCancel').focus();}
function renderManualConfig(){setMain(`<button id="back" class="small subtle" type="button">← 人数</button><h1 class="section-heading">順番に決める</h1><p class="muted">1番が2番へ、最後の人が1番へ。</p><div class="box"><label>ジャンル<select id="manualGenre"><option value="free">自由</option>${DB.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}<option value="numbers">数字</option></select></label></div><div class="setting-label">${searchSwitch()}</div><button id="beginManual" class="primary wide" type="button">スタート</button>`,'manualConfig');bind('back',renderCount);hookSearchSwitch(()=>{const genre=$('manualGenre').value;renderManualConfig();$('manualGenre').value=genre;});bind('beginManual',()=>{disk.current={id:Date.now().toString(36),mode:'manual',count:disk.prefs.count,genre:$('manualGenre').value,step:0,entries:Array(disk.prefs.count).fill(null),done:false};manualReady=false;save();renderManualGate();});}
function renderManualGate(){const c=disk.current;if(!c||c.mode!=='manual')return renderCount();if(c.done){setMain(`<h1>準備できました</h1><button id="goPlay" class="primary wide" type="button">スタート</button>`,'manualDone');bind('goPlay',renderPlay);return;}const author=c.step+1,target=((c.step+1)%c.count)+1;setMain(`<h1>プレイヤー${author}へ</h1><p class="notice">${target}番の人は見ないでね</p><button id="readyManual" class="primary wide" type="button">${target}番のお題を決める</button>`,'manualGate');manualReady=false;bind('readyManual',()=>{manualReady=true;renderManualInput();});}
function renderManualInput(){const c=disk.current;if(!c||c.mode!=='manual'||c.done||!manualReady)return renderManualGate();const target=((c.step+1)%c.count);setMain(`<h1>プレイヤー${target+1}のお題</h1><p class="notice">${target+1}番の人は見ないでね</p><form id="manualForm" autocomplete="off"><label for="manualWord">${esc(category(c.genre))}（1〜60文字）</label><input id="manualWord" class="manualword" name="secret-word-${Date.now()}" type="text" maxlength="120" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" placeholder="例：りんご"><button id="saveManual" class="primary wide" type="submit">決定して隠す</button></form><div class="setting-label">${searchSwitch()}</div>${disk.prefs.search?`<details><summary>候補を検索</summary><div class="row"><input id="query" type="search" maxlength="80" placeholder="例：野菜、動物" aria-label="候補を検索する言葉" style="flex:1"><button id="searchWords" class="small" type="button">検索</button></div><p id="manualSearchStatus" class="searchstatus" role="status"></p><div id="candidateList"></div></details>`:''}`,'manualInput');$('manualForm').addEventListener('submit',e=>{e.preventDefault();try{const word=E.validateWord($('manualWord').value,used,c.entries.filter(Boolean));if(c.genre==='numbers'&&!/^[0-9]+$/.test(word))throw Error('数字ジャンルでは、0以上の整数を数字で入力してください。');c.entries[target]={w:word,c:c.genre,source:'手入力',tier:0};used.add(E.key(word));c.step++;c.done=c.step>=c.count;$('manualWord').value='';manualReady=false;if(searchController)searchController.abort();save();renderManualGate();}catch(err){error(err.message);}});hookSearchSwitch(()=>{const draft=$('manualWord').value;renderManualInput();if($('manualWord'))$('manualWord').value=draft;});bind('searchWords',manualSearch);if($('query'))$('query').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();manualSearch();}});}
function replacementRound(){
  const c=disk.current;
  return manualReplacement&&c&&c.mode==='manual'&&c.done&&c.id===manualReplacement.roundId&&c.entries[manualReplacement.index]?c:null;
}
function renderReplacementGate(){
  const c=replacementRound();if(!c)return renderPlay();
  const target=manualReplacement.index+1,author=((manualReplacement.index+c.count-1)%c.count)+1;
  setMain(`<h1>プレイヤー${author}へ</h1><p class="notice">${target}番の人は見ないでね</p><button id="readyReplacement" class="primary wide" type="button">${target}番のお題を決め直す</button><button id="cancelReplacement" class="wide subtle setting-label" type="button">キャンセル</button>`,'replacementGate');
  bind('readyReplacement',renderReplacementInput);bind('cancelReplacement',renderPlay);
}
function renderReplacementInput(){
  const c=replacementRound();if(!c)return renderPlay();
  const index=manualReplacement.index,target=index+1;
  setMain(`<h1>プレイヤー${target}のお題</h1><p class="notice">${target}番の人は見ないでね</p><form id="replacementForm" autocomplete="off"><label for="replacementWord">${esc(category(c.genre))}（1〜60文字）</label><input id="replacementWord" class="manualword" name="replacement-secret-${Date.now()}" type="text" maxlength="120" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" placeholder="新しいお題"><button id="saveReplacement" class="primary wide" type="submit">変更して隠す</button></form><button id="cancelReplacement" class="wide subtle setting-label" type="button">キャンセル</button>`,'replacementInput');
  $('replacementForm').addEventListener('submit',event=>{
    event.preventDefault();
    if(replacementRound()!==c)return renderPlay();
    try{
      const word=E.validateWord($('replacementWord').value,used,c.entries);
      if(c.genre==='numbers'&&!/^[0-9]+$/.test(word))throw Error('数字ジャンルでは、0以上の整数を数字で入力してください。');
      c.entries[index]={w:word,c:c.genre,source:'手入力',tier:0};
      used.add(E.key(word));$('replacementWord').value='';save();renderPlay();
    }catch(e){error(e.message);}
  });
  bind('cancelReplacement',renderPlay);
}
async function manualSearch(){
  if(!disk.prefs.search||scene!=='manualInput'||!manualReady||!$('query'))return;
  const q=$('query').value.trim();
  if(!q){$('manualSearchStatus').textContent='検索する言葉を入力してください。';return;}
  if(searchController)searchController.abort();
  const own=new AbortController(),epoch=viewEpoch,round=disk.current,step=round.step;
  const current=()=>scene==='manualInput'&&viewEpoch===epoch&&disk.current===round&&round.step===step&&searchController===own&&disk.prefs.search;
  searchController=own;$('searchWords').disabled=true;$('manualSearchStatus').textContent='検索中…';$('candidateList').replaceChildren();
  try{
    const data=await wikiSearch(q,0,own.signal,40);
    if(!current()||own.signal.aborted)return;
    const entries=parseResults(data,'free').filter(e=>!used.has(E.key(e.w)));
    for(const e of entries){
      const b=document.createElement('button');b.type='button';b.textContent=e.w;
      b.addEventListener('click',()=>{if(!current()||used.has(E.key(e.w)))return;$('manualWord').value=e.w;$('manualWord').focus();});
      $('candidateList').append(b);
    }
    $('manualSearchStatus').textContent=entries.length?`${entries.length}件`:'候補がありません。';
  }catch(e){if(current())$('manualSearchStatus').textContent='検索できませんでした。手入力してください。';}
  finally{if(current())$('searchWords').disabled=false;}
}
function searchAllowed(signal){if(!disk.prefs.search||(signal&&signal.aborted))throw new DOMException('検索を中止しました。','AbortError');}
async function wikiSearch(query,offset,externalSignal,limit=100){searchAllowed(externalSignal);const own=new AbortController();const cancel=()=>own.abort();if(externalSignal){if(externalSignal.aborted)own.abort();else externalSignal.addEventListener('abort',cancel,{once:true});}const timer=setTimeout(()=>own.abort(),7500);const url=new URL('https://ja.wikipedia.org/w/api.php');url.search=new URLSearchParams({action:'query',list:'search',format:'json',formatversion:'2',origin:'*',srnamespace:'0',srlimit:String(limit),srsort:'incoming_links_desc',srprop:'',srsearch:query,sroffset:String(offset),maxlag:'5'}).toString();try{const r=await fetch(url.href,{signal:own.signal,credentials:'omit',referrerPolicy:'no-referrer'});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();searchAllowed(externalSignal);if(own.signal.aborted)throw new DOMException('検索を中止しました。','AbortError');if(d.error||!d.query||!Array.isArray(d.query.search))throw Error('検索結果が取得できませんでした。');return d;}finally{clearTimeout(timer);if(externalSignal)externalSignal.removeEventListener('abort',cancel);}}
function parseResults(data,cat){const reject=/(一覧|リスト|曖昧さ回避|カテゴリ|の歴史|の文化|の分類|の研究|の一覧|の人物|の選手|一覧表|用語集|選手権|大会|受賞|賞$|史$|科$|属$|目$|亜科$|学$|[0-9]{3,4}年|[0-9]{3,4}年度|エピソード|事件|事故|死去|殺人|虐待|ポルノ|アダルト|AV女優)/;return E.unique(data.query.search.filter(p=>p&&typeof p.title==='string'&&(!('ns'in p)||p.ns===0)).map(p=>({w:E.cleanWord(p.title.replace(/\s*[（(][^）)]*[）)]\s*$/,'')),title:p.title,c:cat,source:'Wikipedia',tier:1})).filter(e=>e.w.length>=1&&Array.from(e.w).length<=28&&!reject.test(e.title)&&!/[<>{}\[\]:]/.test(e.w)&&!/^\d+$/.test(e.w)&&!used.has(E.key(e.w))));}
async function fetchGenre(id,signal){
  searchAllowed(signal);
  const genre=DB.find(c=>c.id===id);
  if(!genre)return {added:0,done:true};
  const old=disk.cache[id]||{words:[],seed:0,offset:0,done:false};
  old.words=old.words.filter(e=>!used.has(E.key(e.w)));
  if(disk.cache[id])disk.cache[id]=old;
  if(old.done)return {added:0,done:true};
  if(old.words.length>=CACHE_LIMIT)return {added:0,done:false,full:true};
  const seeds=genre.seeds||[];
  let seed=Number(old.seed)||0,offset=Number(old.offset)||0;
  if(seed>=seeds.length)return {added:0,done:true};
  const cleanSeed=seeds[seed].replace(/["\\]/g,'');
  let data;
  try{data=await wikiSearch(`deepcat:"${cleanSeed}"`,offset,signal);}
  catch(e){searchAllowed(signal);if(e.name==='AbortError')throw e;data=await wikiSearch(`incategory:"${cleanSeed}"`,offset,signal);}
  searchAllowed(signal);
  const add=parseResults(data,id),builtin=new Set(genre.words.map(E.key));
  const merged=E.unique([...old.words,...add]).filter(e=>!builtin.has(E.key(e.w))).slice(0,CACHE_LIMIT);
  const added=Math.max(0,merged.length-old.words.length);
  const next=data.continue&&data.continue.sroffset;
  if(Number.isInteger(next)&&next>offset)offset=next;else{seed++;offset=0;}
  disk.cache[id]={words:merged,seed,offset,done:seed>=seeds.length};
  return {added,done:seed>=seeds.length,full:merged.length>=CACHE_LIMIT};
}
function pause(ms,signal){return new Promise((resolve,reject)=>{
  if(signal.aborted){reject(new DOMException('中止','AbortError'));return;}
  const abort=()=>{clearTimeout(timer);reject(new DOMException('中止','AbortError'));};
  const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},ms);
  signal.addEventListener('abort',abort,{once:true});
});}
function refreshGenreCounts(){if(scene!=='genre')return;const cfg=config();document.querySelectorAll('[data-genre]').forEach(button=>{if(button.dataset.genre==='numbers')return;const count=E.remaining(button.dataset.genre,cfg,DB,disk.cache,used);button.querySelector('span').textContent=`未出題 ${count.toLocaleString()}語`;});}
async function bulkRefill(){
  if(!disk.prefs.search||scene!=='genre'||bulkController)return;
  const id=$('refillGenre').value,own=new AbortController(),epoch=viewEpoch;
  // Make space for fresh candidates without ever forgetting used answers.
  if(disk.cache[id])disk.cache[id].words=disk.cache[id].words.filter(e=>!used.has(E.key(e.w)));
  bulkController=own;
  const current=()=>bulkController===own&&viewEpoch===epoch&&scene==='genre'&&disk.prefs.search;
  const count=()=>((disk.cache[id]||{}).words||[]).length;
  let added=0,batches=0,timedOut=false,outcome='';
  const progress=()=>{if(current())$('refillStatus').textContent=`${count().toLocaleString()} / ${CACHE_LIMIT.toLocaleString()}語（＋${added.toLocaleString()}）`;};
  $('refill').disabled=true;$('refillGenre').disabled=true;$('cancelRefill').hidden=false;progress();
  const deadline=setTimeout(()=>{timedOut=true;own.abort();},BULK_TIME_LIMIT);
  try{
    while(!own.signal.aborted&&count()<CACHE_LIMIT){
      const result=await fetchGenre(id,own.signal);
      if(!current())return;
      added+=result.added;batches++;save();progress();refreshGenreCounts();
      if(result.done){outcome='取得完了。';break;}
      if(result.full)break;
      // A single serial stream with a pause avoids flooding the public API.
      await pause(350,own.signal);
    }
    if(count()>=CACHE_LIMIT)outcome='3,000語保存済み。';
  }catch(e){outcome=own.signal.aborted?(timedOut?'60秒で停止。続きから追加できます。':'停止しました。'):'通信エラー。取得済みの候補は保存しました。';}
  finally{
    clearTimeout(deadline);
    if(current()){
      save();progress();$('refillStatus').textContent+=' '+outcome;
      $('refill').disabled=false;$('refillGenre').disabled=false;$('cancelRefill').hidden=true;
      refreshGenreCounts();bulkController=null;
    }
  }
}
bind('hideWord',()=>hideReveal());bind('topEnd',endRound);
bind('replaceWord',()=>{
  const i=activePlayer,c=disk.current;if(i===null||!c||!c.done)return;
  hideReveal();
  const description=c.mode==='manual'?`${i+1}番のお題を、元の出題者が決め直します。`:`${i+1}番を、同じジャンルの別のお題に替えます。`;
  ask('お題をチェンジする？',description,c.mode==='manual'?'決め直す':'チェンジ',()=>{
    if(disk.current!==c)return;
    if(c.mode==='manual'){manualReplacement={roundId:c.id,index:i};renderReplacementGate();return;}
    try{const e=E.drawOne(c.entries[i].c,c.config,DB,disk.cache,used);used.add(E.key(e.w));c.entries[i]=e;save();reveal(i);}catch(e){error(e.message);}
  });
});
function secureScreen(){hideReveal(false);if(scene==='manualInput'){if(searchController)searchController.abort();manualReady=false;renderManualGate();}else if(scene==='replacementInput')renderReplacementGate();}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')secureScreen();});window.addEventListener('pagehide',secureScreen);window.addEventListener('pageshow',()=>{hideReveal(false);});window.addEventListener('blur',()=>{if(activePlayer!==null||scene==='manualInput'||scene==='replacementInput')secureScreen();});window.addEventListener('popstate',secureScreen);document.addEventListener('keydown',e=>{if(e.key==='Escape')hideReveal();});
window.addEventListener('storage',e=>{if(e.key!==STORE||!e.newValue)return;try{const other=JSON.parse(e.newValue);if(other.version!==1)return;for(const k of other.used||[])used.add(k);if(other.current&&disk.current&&other.current.id===disk.current.id){secureScreen();if(validCurrent(other.current)){disk.current=other.current;disk.current.done?renderPlay():renderManualGate();}}}catch(err){}});
if(disk.current){disk.current.done?renderPlay():renderManualGate();}else renderCount();
window.KOTOBA_READY=true;
})();
