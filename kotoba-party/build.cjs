'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=__dirname,read=name=>fs.readFileSync(path.join(root,name),'utf8'),E=require('./engine.js');
const data=[];let current=null;
for(const file of ['words-1.txt','words-2.txt','words-3.txt','words-4a.txt','words-4b.txt'])for(const raw of read(file).split(/\r?\n/)){const line=raw.trim();if(!line)continue;if(line.startsWith('[')&&line.endsWith(']')){const[id,name,...seeds]=line.slice(1,-1).split('|');assert(/^[a-z]+$/.test(id));current={id,name,seeds,words:[]};data.push(current);}else{assert(current);current.words.push(...line.split('|').map(s=>s.trim()).filter(Boolean));}}
assert.equal(data.length,24);assert.equal(new Set(data.map(c=>c.id)).size,24);
// These source snapshots ship with the app. No runtime download is needed.
const supplements=['expanded-lexicon.json','expanded-wiki-nature.json','expanded-wiki-culture.json','expanded-wordnet.json'];
for(const file of supplements){
 const extra=JSON.parse(read(file));
 for(const [id,words] of Object.entries(extra)){
  const category=data.find(c=>c.id===id);assert(category,'Unknown genre in '+file+': '+id);
  assert(Array.isArray(words)&&words.every(w=>typeof w==='string'&&w.trim()===w&&w.length>0&&Array.from(w).length<=60),'Invalid words in '+file+': '+id);
  category.words.push(...words);
 }
}
for(const c of data){c.words=E.unique(c.words);assert(c.words.length>=50,c.id);}
const common=JSON.parse(read('common-words.json'));
const addedCommon=JSON.parse(read('expanded-common.json'));
for(const c of data){
 assert(Array.isArray(common[c.id])&&common[c.id].length>=50,'Missing common words for '+c.id);
 const keys=new Set(c.words.map(E.key));
 c.common=E.unique([...common[c.id],...(addedCommon[c.id]||[])]);
 assert(c.common.every(w=>keys.has(E.key(w))),'Common word outside category '+c.id);
}
const count=new Set(data.flatMap(c=>c.words.map(E.key))).size;
assert(count>=60000,'Incomplete expanded dictionary');
assert(data.filter(c=>c.words.length>=2000).length>=12,'Expanded genre coverage regressed');
const app=read('app.js'),engine=read('engine.js');new vm.Script(app);new vm.Script(engine);
const cfg={count:3,min:0,max:100,kind:'fixed',genre:'food',search:false,familiar:true},used=new Set();
for(let i=0;i<30;i++){const batch=E.draw(cfg,data,{},used);assert.equal(batch.length,3);for(const e of batch){assert(!used.has(E.key(e.w)));used.add(E.key(e.w));}}assert.equal(used.size,90);
assert.equal(E.key('スマホ'),E.key('スマートフォン'));assert.equal(E.key('リンゴ'),E.key('りんご'));assert.throws(()=>E.validateWord('スマートフォン',new Set([E.key('スマホ')])));
for(const n of [1,51,2.5])assert.throws(()=>E.validatePlayers(n));assert.throws(()=>E.draw({...cfg,genre:'numbers',min:0,max:1},data,{},new Set()));
for(const mode of ['same','mixed']){const cc={...cfg,count:25,kind:mode},plan=E.plan(cc,data,{},new Set());assert.equal(plan.length,25);assert.equal(new Set(plan).size,mode==='same'?1:25);const entries=E.draw({...cc,plan},data,{},new Set());assert.equal(new Set(entries.map(e=>E.key(e.w))).size,25);}
const wordnetLicense=read('wordnet-LICENSE.txt');
const notices={JMdict:'Electronic Dictionary Research and Development Group. Selected and classified headwords; distributed under the same EDRDG licence as JMdict: https://www.edrdg.org/edrdg/licence.html',Wikipedia:'Wikipedia contributors. Selected and classified page titles, some disambiguation labels removed. CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/',WordNet:wordnetLicense};
let html=read('template.html');for(const[marker,value]of Object.entries({__STYLE__:read('style.css'),__DATA__:JSON.stringify(data).replace(/<\//g,'<\\/'),__ENGINE__:engine,__APP__:app,__LICENSES__:JSON.stringify(notices).replace(/<\//g,'<\\/')})){assert(html.includes(marker));html=html.split(marker).join(value);}
const output=path.join(root,'public');fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,'index.html'),html);
const report={ok:true,name:'わたしは、なに？',version:'1.3.0',categories:data.length,uniqueWords:count,categoryEntries:data.reduce((n,c)=>n+c.words.length,0),commit:process.env.RENDER_GIT_COMMIT||null,builtAt:new Date().toISOString(),sha256:crypto.createHash('sha256').update(html).digest('hex'),ruleTests:'passed',counts:data.map(c=>({id:c.id,name:c.name,words:c.words.length,commonWords:c.common.length}))};
fs.writeFileSync(path.join(output,'health.json'),JSON.stringify(report,null,2));
const escapeHTML=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const credits=read('credits.html').replace('__COUNTS__',data.map(c=>`<tr><td>${escapeHTML(c.name)}</td><td>${c.words.length.toLocaleString('ja-JP')}語</td></tr>`).join('')).replace('__WORDNET_LICENSE__',escapeHTML(wordnetLicense));
const dictionary=JSON.stringify({name:report.name,version:report.version,notices,categories:data});
for(const [name,contents] of [['credits.html',credits],['dictionary.json',dictionary]]){
 fs.writeFileSync(path.join(output,name),contents);fs.writeFileSync(path.join(root,'..',name),contents);
}
// The repository root is directly publishable by GitHub Pages; no server needed.
fs.writeFileSync(path.join(root,'..','index.html'),html);
fs.writeFileSync(path.join(root,'..','health.json'),JSON.stringify(report,null,2));fs.writeFileSync(path.join(output,'data.json'),JSON.stringify(data));console.log(JSON.stringify(report,null,2));console.log('Static game ready. No dependencies or secrets.');
