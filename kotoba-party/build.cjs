'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=__dirname,read=name=>fs.readFileSync(path.join(root,name),'utf8'),E=require('./engine.js');
const data=[];let current=null;
for(const file of ['words-1.txt','words-2.txt','words-3.txt','words-4a.txt','words-4b.txt'])for(const raw of read(file).split(/\r?\n/)){const line=raw.trim();if(!line)continue;if(line.startsWith('[')&&line.endsWith(']')){const[id,name,...seeds]=line.slice(1,-1).split('|');assert(/^[a-z]+$/.test(id));current={id,name,seeds,words:[]};data.push(current);}else{assert(current);current.words.push(...line.split('|').map(s=>s.trim()).filter(Boolean));}}
assert.equal(data.length,24);assert.equal(new Set(data.map(c=>c.id)).size,24);for(const c of data){c.words=E.unique(c.words);assert(c.words.length>=50,c.id);}
const common=JSON.parse(read('common-words.json'));
for(const c of data){
 assert(Array.isArray(common[c.id])&&common[c.id].length>=50,'Missing common words for '+c.id);
 const keys=new Set(c.words.map(E.key));
 c.common=E.unique(common[c.id]);
 assert(c.common.every(w=>keys.has(E.key(w))),'Common word outside category '+c.id);
}
const count=new Set(data.flatMap(c=>c.words.map(E.key))).size;assert(count>=5000,'Incomplete dictionary');
const app=read('app.js'),engine=read('engine.js');new vm.Script(app);new vm.Script(engine);
const cfg={count:3,min:0,max:100,kind:'fixed',genre:'food',search:false,familiar:true},used=new Set();
for(let i=0;i<30;i++){const batch=E.draw(cfg,data,{},used);assert.equal(batch.length,3);for(const e of batch){assert(!used.has(E.key(e.w)));used.add(E.key(e.w));}}assert.equal(used.size,90);
assert.equal(E.key('スマホ'),E.key('スマートフォン'));assert.equal(E.key('リンゴ'),E.key('りんご'));assert.throws(()=>E.validateWord('スマートフォン',new Set([E.key('スマホ')])));
for(const n of [1,51,2.5])assert.throws(()=>E.validatePlayers(n));assert.throws(()=>E.draw({...cfg,genre:'numbers',min:0,max:1},data,{},new Set()));
for(const mode of ['same','mixed']){const cc={...cfg,count:25,kind:mode},plan=E.plan(cc,data,{},new Set());assert.equal(plan.length,25);assert.equal(new Set(plan).size,mode==='same'?1:25);const entries=E.draw({...cc,plan},data,{},new Set());assert.equal(new Set(entries.map(e=>E.key(e.w))).size,25);}
let html=read('template.html');for(const[marker,value]of Object.entries({__STYLE__:read('style.css'),__DATA__:JSON.stringify(data).replace(/<\//g,'<\\/'),__ENGINE__:engine,__APP__:app})){assert(html.includes(marker));html=html.split(marker).join(value);}
const output=path.join(root,'public');fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,'index.html'),html);
const report={ok:true,name:'わたしは、なに？',version:'1.2.0',categories:data.length,uniqueWords:count,categoryEntries:data.reduce((n,c)=>n+c.words.length,0),commit:process.env.RENDER_GIT_COMMIT||null,builtAt:new Date().toISOString(),sha256:crypto.createHash('sha256').update(html).digest('hex'),ruleTests:'passed',counts:data.map(c=>({id:c.id,name:c.name,words:c.words.length,commonWords:c.common.length}))};
fs.writeFileSync(path.join(output,'health.json'),JSON.stringify(report,null,2));
// The repository root is directly publishable by GitHub Pages; no server needed.
fs.writeFileSync(path.join(root,'..','index.html'),html);
fs.writeFileSync(path.join(root,'..','health.json'),JSON.stringify(report,null,2));fs.writeFileSync(path.join(output,'data.json'),JSON.stringify(data));console.log(JSON.stringify(report,null,2));console.log('Static game ready. No dependencies or secrets.');
