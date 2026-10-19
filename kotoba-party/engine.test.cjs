'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const E = require('./engine.js');
const config = (extra={}) => ({count:3, min:0, max:100, familiar:true, search:false, kind:'fixed', genre:'things', ...extra});
const category = (id, words, common=[]) => ({id, words, common});
const canonicalSet = list => new Set(list.map(e=>E.key(typeof e==='string'?e:e.w)));
function assertUnique(entries, used=new Set()) {
  assert.equal(canonicalSet(entries).size, entries.length);
  for(const e of entries)assert.ok(!canonicalSet([...used]).has(E.key(e.w)), `Already used: ${e.w}`);
}

test('aliases, punctuation and width share a key, without merging signed or decimal numbers', () => {
  for(const group of [['ベッド','寝台'], ['たんす','箪笥'], ['足の裏','足裏'], ['足の指','足指'], ['背骨','脊椎'], ['まぶた','眼瞼'], ['やかん','ケトル'], ['ごみ箱','くずかご'], ['スパゲッティ','スパゲティ'], ['医師','ドクター'], ['手のひら','掌'], ['イヌ', '犬', 'いぬ'], ['マインクラフト', 'Ｍｉｎｅｃｒａｆｔ', 'マイクラ'], ['モンキー・D・ルフィ', 'ルフィ'], ['PC', 'パソコン'], ['１，０００', '+01000', '千'], ['0', '-0', '−００.００', '− ００.０', 'ゼロ', '〇']]) {
    assert.equal(canonicalSet(group).size, 1, group.join(', '));
  }
  assert.notEqual(E.key('-1'), E.key('1'));
  assert.equal(E.key('-1'), E.key('−１'));
  assert.equal(E.key('+ 1'), E.key('1'));
  for(const w of ['+ 1','− ００.０','1,2','1.0','マイクラ','ゼロ'])assert.equal(E.key(E.key(w)),E.key(w));
  assert.notEqual(E.key('1.5'), E.key('15'));
  assert.notEqual(E.key('1..0'), E.key('10'));
  assert.equal(E.key('001.00'), E.key('一'));
  assert.equal(E.key('100000000000000000001'), '100000000000000000001');
  assert.notEqual(E.key('100000000000000000001'), E.key('100000000000000000002'));
});

test('manual validation rejects empty, punctuation-only, long and previously used aliases', () => {
  for(const value of ['', null, '　', '\u200b', '！？', 'a'.repeat(61)])assert.throws(()=>E.validateWord(value,new Set()), /1〜60/);
  assert.throws(()=>E.validateWord('いぬ',new Set(['犬'])), /重複/);
  assert.throws(()=>E.validateWord('ゼロ',new Set(['000'])), /重複/);
  assert.throws(()=>E.validateWord('ＰＣ',new Set(),[{w:'パソコン'}]), /重複/);
  assert.throws(()=>E.validateWord('イヌ',new Set(),['犬']), /重複/);
  assert.equal(E.validateWord('　りんご\u200b　',new Set()), 'りんご');
  assert.equal(E.validateWord('😀'.repeat(60),new Set()), '😀'.repeat(60));
  assert.equal(E.validateWord('-1',new Set(['1'])), '-1');
});

test('word pools deduplicate across all sources and set genuine familiarity tiers', () => {
  const db=[category('things',['イヌ','顕微鏡','パソコン'],['犬','スマホ'])];
  const cache={things:{words:[{w:'PC',tier:0,source:'ネット'},{w:'量子干渉計',tier:0,source:'ネット'}]}};
  const original=JSON.stringify({db,cache});
  const offline=E.wordPool('things',db,cache,new Set(),false);
  assert.equal(offline.length,4);
  assert.deepEqual(offline.map(e=>e.tier),[0,0,1,1]);
  const online=E.wordPool('things',db,cache,new Set(),true);
  assert.equal(online.length,5);
  assert.equal(online.find(e=>e.w==='量子干渉計').tier,2);
  assert.equal(E.wordPool('things',db,cache,new Set(['いぬ']),true).length,4);
  assert.equal(JSON.stringify({db,cache}),original);
});

test('familiar selection always uses common first, then other built-ins, then online', () => {
  const db=[category('things',['顕微鏡','針金'],['犬','猫'])],cache={things:{words:[{w:'量子干渉計'}]}};
  for(let i=0;i<20;i++) {
    const common=E.draw(config({count:2,search:true}),db,cache,new Set());
    assert.ok(common.every(e=>e.tier===0));
    const rest=E.draw(config({count:2,search:true}),db,cache,new Set(['犬','猫']));
    assert.ok(rest.every(e=>e.tier===1));
  }
  assert.equal(E.drawOne('things',config({search:true}),db,cache,new Set(['犬','猫','顕微鏡','針金'])).tier,2);
  assert.throws(()=>E.drawOne('things',config(),db,cache,new Set(['犬','猫','顕微鏡','針金'])), /未出題/);
});

test('fixed genre supports 50 players and preserves caller data', () => {
  const db=[category('things',Array.from({length:130},(_,i)=>`道具${i}`),Array.from({length:70},(_,i)=>`身近なお題${i}`))];
  const used=new Set(['身近なお題0','道具0']),before=[...used];
  const result=E.draw(config({count:50}),db,{},used);
  assert.equal(result.length,50);
  assert.ok(result.every(e=>e.c==='things'&&e.tier===0));
  assertUnique(result,used);
  assert.deepEqual([...used],before);
});

test('fixed genre excludes both historic and same-round aliases', () => {
  const db=[category('things',['犬','イヌ','猫','ネコ','車','クルマ','りんご','林檎'])];
  const used=new Set(['イヌ']);
  const result=E.draw(config(),db,{},used);
  assert.equal(result.length,3);
  assertUnique(result,used);
  assert.throws(()=>E.draw(config({count:4}),db,{},used),/人数分/);
});

test('same random genre only selects categories that can supply the entire round', () => {
  const db=[category('tiny',['犬']),category('ready',['猫','車','りんご','犬'])];
  const cfg=config({kind:'same',min:0,max:0});
  for(let i=0;i<20;i++) {
    const planned=E.plan(cfg,db,{},new Set(['犬']));
    assert.deepEqual(planned,['ready','ready','ready']);
    assertUnique(E.draw({...cfg,plan:planned},db,{},new Set(['犬'])),new Set(['犬']));
  }
  assert.throws(()=>E.plan({...cfg,count:5},db,{},new Set()), /ジャンルがありません/);
});

test('mixed mode cycles eligible genres without repeats until the cycle ends', () => {
  const db=['a','b','c'].map(id=>category(id,Array.from({length:30},(_,i)=>`${id}のお題${i}`)));
  const cfg=config({kind:'mixed',count:12,min:0,max:29});
  for(let i=0;i<20;i++) {
    const planned=E.plan(cfg,db,{},new Set());
    for(let offset=0;offset<12;offset+=4)assert.equal(new Set(planned.slice(offset,offset+4)).size,4);
    assertUnique(E.draw({...cfg,plan:planned},db,{},new Set()));
  }
});

test('mixed mode does not overbook tiny genres when other words are available', () => {
  const db=[category('tiny',['犬']),category('ample',Array.from({length:60},(_,i)=>`遊び${i}`))];
  const cfg=config({kind:'mixed',count:50,min:0,max:0});
  for(let i=0;i<10;i++) {
    const planned=E.plan(cfg,db,{},new Set());
    assert.equal(planned.filter(c=>c==='tiny').length,1);
    assert.equal(planned.filter(c=>c==='numbers').length,1);
    const entries=E.draw({...cfg,plan:planned},db,{},new Set());
    assert.equal(entries.length,50);
    assertUnique(entries);
  }
});

test('matching reassigns a broad genre instead of consuming the narrow genre’s only alias', () => {
  const db=[category('broad',['犬','猫'],['犬']),category('narrow',['イヌ'])];
  const cfg=config({count:2,kind:'mixed',plan:['broad','narrow']});
  for(let i=0;i<20;i++)assert.deepEqual(E.draw(cfg,db,{},new Set()).map(e=>E.key(e.w)),[E.key('猫'),E.key('犬')]);
});

test('overlapping mixed pools either supply unique assignments or report exhaustion', () => {
  const db=[category('a',['犬','猫']),category('b',['イヌ','ネコ']),category('c',['猫'])];
  for(let i=0;i<20;i++) {
    const cfg=config({kind:'mixed',count:3,min:0,max:0});
    const planned=E.plan(cfg,db,{},new Set());
    assertUnique(E.draw({...cfg,plan:planned},db,{},new Set()));
    assert.throws(()=>E.plan({...cfg,count:4},db,{},new Set()),/人数分/);
  }
});

test('numeric aliases collide across genres while distinct signed words remain available', () => {
  const db=[category('words',['ゼロ','一','-1','二'])];
  const cfg=config({kind:'mixed',count:4,min:0,max:1,plan:['words','numbers','words','numbers']});
  for(let i=0;i<20;i++) {
    const entries=E.draw(cfg,db,{},new Set());
    assertUnique(entries);
    assert.deepEqual([...canonicalSet(entries)].sort(),['-1','0','1','2']);
  }
});

test('numeric ranges count zero aliases once and reject exhaustion without reusing numbers', () => {
  const used=new Set(['0','ゼロ','001','一','-1','1.5','001.0']);
  const cfg=config({genre:'numbers',min:0,max:3,count:2});
  assert.equal(E.remaining('numbers',cfg,[],{},used),2);
  assert.deepEqual(E.numberPool(0,3,used).map(e=>e.w),['2','3']);
  assert.deepEqual([...canonicalSet(E.draw(cfg,[],{},used))].sort(),['2','3']);
  assert.throws(()=>E.draw({...cfg,count:3},[],{},used),/人数分/);
  assert.throws(()=>E.drawOne('numbers',cfg,[],{},new Set(['0','1','2','3'])),/すべて出題済み/);
});

test('50 numeric players across the widest allowed range stay in range and unique', () => {
  const cfg=config({genre:'numbers',count:50,min:0,max:1000000});
  const used=new Set(['0','1','1000000']);
  const result=E.draw(cfg,[],{},used);
  assert.equal(result.length,50);assertUnique(result,used);
  assert.ok(result.every(e=>Number(e.w)>=0&&Number(e.w)<=1000000));
});

test('a nearly exhausted numeric pool finds its remaining value', () => {
  const cfg=config({genre:'numbers',min:0,max:1000});
  const used=new Set(Array.from({length:1001},(_,i)=>String(i)).filter(n=>n!=='731'));
  assert.equal(E.drawOne('numbers',cfg,[],{},used).w,'731');
});

test('invalid players, ranges, modes, genres and prepared plans fail clearly', () => {
  for(const count of [0,1,51,2.5,NaN,'3'])assert.throws(()=>E.validatePlayers(count),/2〜50/);
  for(const [min,max] of [[-1,2],[3,2],[0,1000001],[0,1.5],[NaN,1],['0',3]])assert.throws(()=>E.validateRange(min,max),/数字/);
  assert.throws(()=>E.plan(config({kind:'unknown'}),[],{},new Set()),/モード/);
  assert.throws(()=>E.plan(config({genre:'missing'}),[],{},new Set()),/ジャンル/);
  assert.throws(()=>E.draw(config({plan:['numbers']}),[],{},new Set()),/人数/);
  assert.throws(()=>E.draw(config({plan:['missing','numbers','numbers']}),[],{},new Set()),/ジャンル/);
  assert.throws(()=>E.pick([],true),/未出題/);
});

test('cached online words are excluded unless search is explicitly enabled', () => {
  const db=[category('things',['椅子','机'])],cache={things:{words:[{w:'天球儀'}]}};
  const used=new Set(['椅子','机']);
  for(const search of [false,undefined,null])assert.throws(()=>E.drawOne('things',config({search}),db,cache,used),/未出題/);
  assert.equal(E.drawOne('things',config({search:true,familiar:false}),db,cache,used).w,'天球儀');
});

test('mixed matching fills the available union across varied overlapping pools', () => {
  let seed=777;
  const rand=n=>{seed=(seed*1664525+1013904223)>>>0;return seed%n;};
  for(let trial=0;trial<80;trial++) {
    const db=Array.from({length:4},(_,i)=>category(`g${i}`,Array.from({length:10},(_,j)=>`テスト単語${j}`).filter(()=>rand(3)>0)));
    const used=new Set(['0',`テスト単語${rand(10)}`]);
    const union=canonicalSet(db.flatMap(c=>c.words).filter(w=>!used.has(w)));
    if(union.size<2)continue;
    const cfg=config({kind:'mixed',count:union.size,min:0,max:0,familiar:trial%2===0});
    const planned=E.plan(cfg,db,{},used),entries=E.draw({...cfg,plan:planned},db,{},used);
    assert.equal(entries.length,union.size);assertUnique(entries,used);
    assert.throws(()=>E.plan({...cfg,count:union.size+1},db,{},used),/人数分/);
  }
});

test('large dictionaries retain unique familiar assignments across 50 mixed players', () => {
  const common=Array.from({length:80},(_,i)=>`共通のお題${i}`);
  const db=Array.from({length:24},(_,i)=>category(`large${i}`,[...common,...Array.from({length:5000},(_,j)=>`分類${i}のお題${j}`)],common));
  const used=new Set(common.slice(0,20));
  const cfg=config({kind:'mixed',count:50,min:0,max:0});
  used.add('0');
  for(const c of db)assert.equal(E.remaining(c.id,cfg,db,{},used),5060);
  const planned=E.plan(cfg,db,{},used),result=E.draw({...cfg,plan:planned},db,{},used);
  assert.equal(result.length,50);
  assert.ok(result.every(e=>e.tier===0));
  assertUnique(result,used);
  assert.equal(new Set(planned.slice(0,24)).size,24);
});

test('a large preferred pool leaves the only usable words for 49 narrow categories', () => {
  const shared=Array.from({length:49},(_,i)=>`限定のお題${i}`);
  const db=[category('broad',Array.from({length:5000},(_,i)=>`広い分類のお題${i}`),shared),...shared.map((w,i)=>category(`narrow${i}`,[w]))];
  const cfg=config({count:50,plan:db.map(c=>c.id)});
  const result=E.draw(cfg,db,{},new Set());
  assert.equal(result.length,50);
  assertUnique(result);
  assert.equal(result[0].tier,1);
  assert.deepEqual(result.slice(1).map(e=>e.w),shared);
});


test('unchecked familiarity gives common, built-in and online words equal selection slots', () => {
  const vm=require('node:vm'),fs=require('node:fs');
  // Uniform deterministic random input enumerates every slot, without a flaky statistical test.
  let next=0;
  const sandbox={Math:Object.create(Math)};
  sandbox.Math.random=()=>next;
  vm.runInNewContext(fs.readFileSync(require.resolve('./engine.js'),'utf8'),sandbox);
  const engine=sandbox.KotobaEngine;
  const db=[category('things',['コップ','顕微鏡'],['コップ'])];
  const cache={things:{words:[{w:'量子干渉計'}]}};
  const cfg=config({familiar:false,search:true});
  const drawn=[];
  for(let slot=0;slot<3;slot++){
    next=(slot+.5)/3;
    drawn.push(engine.drawOne('things',cfg,db,cache,new Set()).w);
  }
  assert.deepEqual(drawn,['コップ','顕微鏡','量子干渉計']);
});
