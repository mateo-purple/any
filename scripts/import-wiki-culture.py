#!/usr/bin/env python3
"""Rebuild Japanese party-game words from Japanese Wikipedia article titles.

Normal HTTPS, identifying User-Agent, max two workers, incremental cached requests.
Only titles/IDs and classification metadata are stored; no article text or images. Exact year categories or
subject-specific infoboxes narrow work-title collections. Other subjects additionally
require matching non-hidden article categories. Derived title database: CC BY-SA 4.0.

Reproduction (all requests respect the inherited proxy and TLS trust):
  python3 scripts/import-wiki-culture.py
  KOTOBA_CULTURE_GENRES=movies,music KOTOBA_CULTURE_EXTEND_SINCE=2005 \
    python3 scripts/import-wiki-culture.py
  KOTOBA_CULTURE_AUDIT=1 python3 scripts/import-wiki-culture.py
  KOTOBA_CULTURE_TYPE_AUDIT=1 python3 scripts/import-wiki-culture.py
Do not publish the intermediate file before the final audit. Independent review
rejected the seven general-vocabulary collections; the final audit drops them.
Short sports/clothing additions are restricted to a manually reviewed allowlist.
"""
import concurrent.futures, datetime, hashlib, json, os, re, time, unicodedata
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.getenv('KOTOBA_CULTURE_CACHE', '/tmp/kotoba-culture-cache'))
CACHE.mkdir(parents=True, exist_ok=True)
UA = 'KotobaPartyDictionary/1.0 (https://github.com/mateo-purple/any)'
ENDPOINT = 'https://ja.wikipedia.org/w/api.php'
MAXLEN = 35
FORBID = re.compile(r'一覧|曖昧さ回避|年表|登場人物|の歴史|の作品|作品リスト|用語|事件|事故|殺害|戦争犯罪|性行為|ポルノ|アダルト|エロゲ|凌辱|強姦|痴漢|淫|姦|レイプ|セックス|陵辱|乳首|緊縛|おっぱい|巨乳|爆乳|AV女優|アダルトビデオ|18禁|性器|勃起|射精|フェラ|アナル|マスターベーション|乱交|売春|慰安婦')
BADCAT = re.compile(r'存命人物|\d+年生|\d+年没|設立の|の企業|企業の|製作会社|制作会社|の出版社|放送局|成人向け|ポルノ|アダルト|エロティ|エロス|BDSM|オーラル|クンニ|放送禁止|性的|ピンク映画|官能|性行為|レイプ')
EXACT_BAD = {'Google Chrome','相模鉄道','日本万国博覧会','Nintendo Entertainment System','ゲームソフト','映画','テレビアニメ','日本','テレビ東京','東映','講談社','任天堂','アダルトゲーム','株式会社ポケモン'}

def request(params):
    params = {'action':'query','format':'json','formatversion':2,'maxlag':5, **params}
    url = ENDPOINT + '?' + urllib.parse.urlencode(params)
    f = CACHE / (hashlib.sha256(url.encode()).hexdigest()+'.json')
    if f.exists(): return json.loads(f.read_text())
    for attempt in range(4):
        try:
            req = urllib.request.Request(url,headers={'User-Agent':UA})
            with urllib.request.urlopen(req,timeout=45) as r: data=json.load(r)
            if data.get('error',{}).get('code') in ('maxlag','ratelimited','cirrussearch-too-busy-error'):
                time.sleep(2+attempt*2); continue
            if 'error' in data: raise ValueError(str(data['error']))
            f.write_text(json.dumps(data,ensure_ascii=False)); time.sleep(.18)
            return data
        except urllib.error.HTTPError as e:
            if e.code not in (429,502,503,504): raise
            time.sleep(2+attempt*2)
        except (TimeoutError, ConnectionError): time.sleep(2+attempt*2)
    raise RuntimeError('Wikipedia query retry limit')

def clean(title):
    # Strip only parenthetical disambiguators, retaining the exact article title in metadata.
    w = re.sub(r'\s*[（(][^()（）]*[）)]\s*$', '', title).strip()
    w = unicodedata.normalize('NFKC', w)
    if not 2 <= len(w) <= MAXLEN or FORBID.search(w) or title in EXACT_BAD or re.match(r'^\d{4}年の',w): return None
    if not re.search(r'[ぁ-んァ-ヶ一-龯A-Za-z]',w): return None
    return w

def category_query(years, suffixes):
    return 'incategory:"'+'|'.join(f'{y}年の{s}' for y in years for s in suffixes)+'"'

# Every query begins with the most-linked entries; no adjective×noun fabrication.
SPECS = {
 'games': {'limit':9000, 'queries':[
     category_query(range(1980,2027),['コンピュータゲーム'])+' -deepcat:"アダルトゲーム"',
     'deepcat:"ボードゲーム" -deepcat:"コンピュータゲーム"',
     'deepcat:"カードゲーム" -deepcat:"コンピュータゲーム"'],
     'accept':r'用ソフト|ゲーム作品|ゲームソフト|コンピュータゲーム$|ボードゲーム|カードゲーム|テーブルゲーム|ゲームのジャンル'},
 'anime': {'limit':10000,'queries':[
     category_query(range(1960,2027),['漫画','テレビアニメ'])+' -deepcat:"成人向け漫画" -deepcat:"成人向けアニメ"'],
     'accept':r'漫画作品|アニメ作品|年の漫画|年のテレビアニメ|年のアニメ|アメコミ作品'},
 'movies': {'limit':10000,'queries':[
     category_query(range(1930,2027),['映画','アニメ映画'])+' -deepcat:"ポルノ映画" -deepcat:"ピンク映画"'],
     'accept':r'年の映画|年のアニメ映画|の映画作品|の映画$|アニメ映画'},
 'music': {'limit':7000,'queries':[
     category_query(range(1960,2027),['シングル','楽曲']),
     'deepcat:"楽器"','deepcat:"音楽用語"'],
     'accept':r'年のシングル|楽曲|歌曲|器楽曲|交響曲|楽器|音楽用語|演奏技法|音階|和音|調性|音符|音楽のジャンル'},
 'characters': {'limit':4500,'queries':['hastemplate:"Infobox character"','deepcat:"架空の人物"','deepcat:"マスコットキャラクター"','deepcat:"妖怪"'],
     'accept':r'キャラクター(?!ゲーム)|登場人物|架空の|マスコット|妖怪$|神話.*神|の人物'},
 'vehicles': {'limit':4000,'queries':['hastemplate:"Infobox 自動車のスペック表"','deepcat:"オートバイの車種"','deepcat:"鉄道車両"','deepcat:"乗り物"'],
     'accept':r'乗用車|自動車の車種|自動車車種|オートバイの車種|鉄道車両|バス車両|自転車の形態|自動車の形態|車両|乗り物|バス車種|自動車|スポーツカー|クーペ|セダン|ミニバン|ステーションワゴン|軽自動車'},
 'sports': {'limit':2000,'queries':['deepcat:"スポーツ競技"','deepcat:"球技"','deepcat:"子供の遊び"'],
     'accept':r'競技|球技|スポーツ|遊戯|子供の遊び'},
 'electronics': {'limit':1500,'queries':['deepcat:"家電機器"','deepcat:"電子機器"'],
     'accept':r'家電機器|電子機器|照明器具|通信機器|音響機器|映像機器|コンピュータ周辺機器'},
 'clothes': {'limit':1500,'queries':['deepcat:"衣類"','deepcat:"装身具"','deepcat:"履物"'],
     'accept':r'衣類|装身具|履物|ファッション|下着|帽子|靴|服飾|アクセサリー'},
 'jobs': {'limit':1500,'queries':['deepcat:"職業"','deepcat:"専門職"'],
     'accept':r'^Category:職業|専門職|の職業|の称号|^Category:役職'},
 'school': {'limit':1000,'queries':['incategory:"学校教育"','deepcat:"年中行事"','deepcat:"学校行事"'],
     'accept':r'学校|年中行事|教育|祭|祝日|学問|学習'},
 'things': {'limit':2000,'queries':['deepcat:"日用品"','deepcat:"道具"','deepcat:"家具"'],
     'accept':r'日用品|道具|家具|用品|容器|文房具|台所用具|食器|工具'},
 'colors': {'limit':600,'queries':['deepcat:"色"','deepcat:"模様"'],
     'accept':r'^Category:色$|色名|色の|模様|柄|文様'},
 'body': {'limit':800,'queries':['deepcat:"人体"','deepcat:"器官"'],
     'accept':r'解剖学|器官|骨|筋肉|皮膚|感覚器|脳|血管|神経|口|歯|頭頸部|四肢|人体'},
 'actions': {'limit':800,'queries':['deepcat:"身体動作"','deepcat:"日常生活"'],
     'accept':r'動作|日常生活|生活|行為|仕草|運動|食事|家事|コミュニケーション'},
}

# For ordinary objects/anatomy/jobs, exact topical categories avoid the enormous
# company/person subtrees and the server cost of broad deepcat searches.
DIRECT_CATEGORIES = {
 'electronics':['家電機器','電子機器','音響機器','映像機器','照明器具','通信機器','調理器具','コンピュータ周辺機器','撮影機材'],
 'jobs':['職業','サービス関連の職業','医療関連の職業','芸能関連の職業','職人','教育関連の職業','スポーツ関連の職業','専門職','法務関係の職業','技術者','科学関連の職業','農業関連の職業','建設関連の職業','称号'],
 'school':['学校教育','学校行事','年中行事','日本の祭り','日本の年中行事','祝日','教育の手法','学習','文房具'],
 'things':['日用品','道具','家具','工具','容器','食器','台所用品','調理器具','文房具','清掃用具','計測機器','照明器具','寝具','玩具','鞄','装身具'],
 'colors':['色','色名','色の名称','模様','文様','日本の色','虹'],
 'body':['人体','器官','骨','筋肉','消化器','呼吸器','循環器','神経','血管','脳神経','頭頸部の骨','上肢の骨','下肢の骨','体幹の骨','上肢の筋肉','下肢の筋肉','頭頸部の筋肉','皮膚解剖学','感覚器'],
 'actions':['身体動作','日常生活','家事','生活','非言語コミュニケーション','食事','睡眠','入浴','掃除','歩行','運動','遊び'],
}
for genre, categories in DIRECT_CATEGORIES.items():
    SPECS[genre]['queries']=['incategory:"'+c+'"' for c in categories]

def collect(item):
    genre, spec = item
    selected={}; examined=0; logs=[]
    expected = re.compile(spec['accept'])
    queries=[]
    for original in spec['queries']:
        m=re.match(r'incategory:"([^"]+)"(.*)',original)
        if m and len(m[1].split('|'))>50:
            cs=m[1].split('|');queries.extend('incategory:"'+'|'.join(cs[i:i+50])+'"'+m[2] for i in range(0,len(cs),50))
        else:queries.append(original)
    for query in queries:
        if len(selected)>=spec['limit']:break
        offset=0; total=0
        # Exact year membership is an independently typed source. Infobox/deepcat
        # collections receive full per-article category validation below.
        exact=query.startswith('incategory:') and '年の' in query
        while len(selected)<spec['limit'] and offset<10000:
            if exact:
                data=request({'list':'search','srsearch':query,'srnamespace':0,'srlimit':100,'sroffset':offset,'srsort':'incoming_links_desc','srprop':''})
                pages=data.get('query',{}).get('search',[])
                cont=data.get('continue',{}).get('sroffset')
            else:
                params={'generator':'search','gsrsearch':query,'gsrnamespace':0,'gsrlimit':50,'gsroffset':offset,'gsrsort':'incoming_links_desc','prop':'categories|pageprops','cllimit':'max','clshow':'!hidden','ppprop':'disambiguation'}
                data=request(params); pages=data.get('query',{}).get('pages',[])
                byid={p['pageid']:p for p in pages}
                extra=data
                # Complete all category pages before classification; generator
                # offset is advanced only after current search batch completes.
                while 'clcontinue' in extra.get('continue',{}):
                    extra=request({**params,**extra['continue']})
                    for p in extra.get('query',{}).get('pages',[]):
                        prev=byid.setdefault(p['pageid'],p)
                        if prev is not p:prev.setdefault('categories',[]).extend(p.get('categories',[]));prev.setdefault('pageprops',{}).update(p.get('pageprops',{}))
                pages=list(byid.values()); cont=extra.get('continue',{}).get('gsroffset')
            examined+=len(pages);total+=len(pages)
            for p in sorted(pages,key=lambda x:x.get('index',0)):
                title=p['title'];w=clean(title)
                if not w or 'disambiguation' in p.get('pageprops',{}):continue
                cats=[c['title'] for c in p.get('categories',[])]
                if not exact and (not any(expected.search(c) for c in cats) or any(BADCAT.search(c) for c in cats)):continue
                if genre=='body' and re.search(r'病|癌|疾患|症|炎|細胞|タンパク|ウイルス|微生物|遺伝子|受容体|ホルモン|学|形成|分化|信号|症候',w):continue
                if genre=='colors' and re.search(r'学|モデル|システム|空間|体系|覚|現象|効果|計|軌跡|測|収差|合成|信号|フォーマット|温度',w):continue
                if genre=='sports' and re.search(r'選手|リーグ|連盟|協会|大学|クラブ|チーム|選手権|大会|杯|年度|シーズン',title):continue
                if genre=='school' and re.search(r'大学|高等学校|中学校|小学校|学園|教育委員会|省|法|協会|選手権',title):continue
                if genre=='vehicles' and re.search(r'会社|鉄道$|電鉄$|協会|選手権|サーキット|博物館',title):continue
                if genre=='jobs' and re.search(r'会社|協会|連盟|委員会|大学|学部|学校|制度|法律|法$|試験|賃金|雇用|労働|資格|派遣|保険',title):continue
                if genre=='characters' and (re.search(r'シリーズ|物語|作品|漫画|ゲーム|妖怪$|伝説$|神話$|人形$',w) or re.search(r'神社|寺院|学校|鉄道',w)):continue
                selected.setdefault(w,{'title':title,'pageid':p['pageid'],'categories':cats})
            if offset%500==0:print(genre,offset,'selected',len(selected),'of',examined,flush=True)
            if cont is None or not pages:break
            offset=cont
            if not exact and total>=1800:break
        logs.append({'query':query,'examined':total})
    print('DONE',genre,len(selected),'examined',examined,flush=True)
    return genre,selected,logs

# These short non-work lists were read in full after the taxonomy audit.
# Everything else in small general genres is intentionally omitted.
REVIEWED_GENERAL = {
 'sports': set("野球|陸上競技|テニス|ゴルフ|卓球|格闘技|モータースポーツ|バドミントン|自転車競技|パチンコ|マラソン|競泳|ソフトテニス|ボウリング|登山|スノーボード|競艇|長距離走|体操競技|短距離走|クリケット|ブラジリアン柔術|駅伝競走|トライアスロン|飛込競技|ヤールギュレシ|ダーツ|クシュティー|サンボ|中距離走|シュアイジャオ|球技|七種競技|ウィンタースポーツ|チアリーディング|ハーフマラソン|ロデオ|十種競技|オートバイ競技|BMX|オリエンテーリング|ソフトボール|ゲートボール|スカッシュ|打毬|ローンボウルズ|ペタンク|ネットボール|グラウンド・ゴルフ|フロアボール|キックベースボール|インラインホッケー|ローラーホッケー|ジュ・ド・ポーム|ラウンダーズ|スポールブール|バンディ|サバイバルゲーム|縄跳び|パークゴルフ|アルティメット|一輪車|コーフボール|クロッケー|ファウストボール|セストボール|ハイアライ|雪合戦|シュラークバル|ソサイチ|トーボール|ホースボール|紙相撲|ビーチテニス|マレットゴルフ|ペサパッロ|ゲーリックフットボール|テニピン|インディアカ|カヌーポロ|ピックルボール|スピードゴルフ|タンブレロ|バブルサッカー|ティーボール|チュックボール|棒倒し|ポートボール|パドルテニス|フリースタイルフットボール|バウンドテニス|カナディアンフットボール|ケイマンゴルフ|ウィッフルボール|スティックボール|ウッドボール|ウォーターバスケットボール|ゴロッケー|フリーテニス|パンポン|エスキーテニス|タムビーチ|パデル|スポーツスタッキング|ブーメラン|スピードミントン|カイトサーフィン|KanJam".split('|')),
 'clothes': set("ブラジャー|制服|Tシャツ|ヘルメット|皮革|帽子|下駄|下着|手袋|足袋|靴下|シャツ|スニーカー|野球帽|ブーツ|脚絆|シルクハット|手拭|ブルマー|タイツ|ストッキング|タンクトップ|ターバン|ニーソックス|ノースリーブ|ベレー帽|パンティストッキング|履物|ランジェリー|スカーフ|鉢巻|バンダナ|ガウン|ハイソックス|ふんどし|ガーター|ハイヒール|ステテコ|ベール|山高帽|エプロン|ベルト|オペラグローブ|インバネスコート|サンダル|頭巾|ロシア帽|人民服|スパッツ|ランニングシャツ|ボディスーツ|ローライズ|ボクサーブリーフ|スリッパ|革靴|麦わら帽子|トレンチコート|アンダースコート|ナイトキャップ|中折れ帽|全身タイツ|カフリンクス|ハンチング帽|アルスターコート|ヘッドギア|マフ|スイムキャップ|オーバーパンツ|メリージェーン|ボールガウン|ストラップレスドレス|ロンパース|ブライダルインナー|仮面|上履き|ビーチサンダル|モカシン|サンドレス|運動靴|アンダーシャツ|スパゲティストラップ|キャスケット|紅白帽|ローファー|キャップ|パンプス|バスケットシューズ|バスローブ|ダッフルコート|ネグリジェ|ニット帽|サッシュ|ネッカチーフ|Pコート|スニーカーソックス|法服|草鞋|コルセット|Aライン|ホルターネック|バックレスドレス|チャイナドレス|烏帽子|草履|安全靴|スパイクシューズ|襦袢|手甲|パンツ|パニエ|トガ|雪駄|ズロース|ポケット|チュニック|ショース|股引|クリノリン|バッスル|たすき|ソンブレロ|ティアラ|古着|アオザイ|サリー|キルト|漢服|メリヤス|裾除け|長靴|チマチョゴリ|湯文字|六尺褌|越中褌|テンガロンハット|ビスチェ|制帽|ガードル|フェズ|パナマ帽|キッパー|三角帽子|トウシューズ|ルバシカ|ボディコン|ボンネット|かんじき|ハーフトップ|ウエストニッパー|ディアンドル|トレーニングパンツ|ボディシェイパー|スケート靴|クーフィーヤ|バイザー|シャプカ|ルーズソックス|フリジア帽|グレンガリー帽|学生帽|二角帽子|輪かんじき|スノーシュー|サラファン|スリット|アイゼン|レーダーホーゼン|満洲服|琉装|フリル|銘仙|スモック|バブーシュ|フスタネーラ|ケバヤ|キトン|地下足袋|ストラップ|ダシキ|ラペル|ダルマティカ|帽章|ペプロス|ボディス|ハットピン|ヒマティオン|ココシニク|オー・ド・ショース|裏地|シュールコー|コタルディ|ミトラ|ペタソス|ペチパンツ|ウプランド|モンマス帽|モブキャップ|ピレウス帽|比翼仕立て|目出し帽|スポーツ用サポーター|かりゆしウェア|登山靴|腹巻き|カラーステイ|角隠し|紫衣|帯留|既製服|カンカン帽|綿帽子|ピナフォア|下駄スケート|ケピ帽|ぽっくり下駄|宗十郎頭巾|シースルー|菊綴|浄衣|眼鏡|マスク|かつら|勲章|腕時計|ネクタイ|首輪|ヘアバンド|サスペンダー|フェイスシールド|リボン|懐中時計|襟巻き|お守り|ポーラー・タイ|アスコット・タイ|スヌード|ピアス|バッジ|指輪|ボア|数珠|ネックレス|ブレスレット|レッグウォーマー|厚底靴|靴底|ミュール|ガロッシュ|シークレットシューズ|ヒール|カウボーイブーツ|行田足袋|木靴|ウェリントン・ブーツ|鼻緒|スキーブーツ|半長靴|小具足|ロンドンブーツ|ワークブーツ|靴べら|中敷き|缶下駄|ブローグシューズ|ローラーシューズ|エンジニアブーツ|マラソン足袋|スラップスケート|ジョッパーブーツ|胴付長靴|ジャンピング・スティルト|エスパドリーユ|ダービーシューズ|島ぞうり|ワーレンキ|グラディエーターサンダル|サイクリングシューズ|健康サンダル|ギョサン|チャッカブーツ|フラットシューズ|シューキーパー|ブーティー|アグレット|靴鋲|浅沓|プレーントゥ|Uチップ|ウェディングシューズ|トレンチブーツ|ポソン|足布|チェルシーブーツ".split('|')),
}

def audit_adult_categories():
    """Exclude adult-subject category members by article ID, including descendants.

    This complements search-time exclusion: CirrusSearch may truncate deepcat
    expansion, so an explicit category-members traversal is required before release.
    Only category metadata is fetched, not the content of the listed works.
    """
    starts=['アダルトゲーム','成人向け漫画','成人向けアニメ','ポルノ映画','ピンク映画','日活ロマンポルノ','エロス映画','BDSM映画','エロティック映画','エロティック・スリラー映画','エロティック・ホラー映画','オーラル・エロティシズム','放送禁止となった楽曲','クンニリングス','成人向けゲーム','アダルトアニメ']
    queue=[('Category:'+c,0) for c in starts];seen=set();blocked=set();counts={}
    while queue:
        cat,depth=queue.pop(0)
        if cat in seen:continue
        seen.add(cat); params={'list':'categorymembers','cmtitle':cat,'cmnamespace':'0|14','cmlimit':500};amount=0
        while True:
            d=request(params);members=d.get('query',{}).get('categorymembers',[])
            for member in members:
                if member['ns']==0:blocked.add(member['pageid']);amount+=1
                elif depth<4 and not re.search(r'女優|俳優|監督|男優|漫画家|作家|製作者|制作会社|企業|団体|人物|雑誌|出版社',member['title']):queue.append((member['title'],depth+1))
            nxt=d.get('continue',{}).get('cmcontinue')
            if not nxt:break
            params['cmcontinue']=nxt
        counts[cat]=amount
        if len(seen)%20==0:print('AUDIT categories',len(seen),'blocked articles',len(blocked),flush=True)
    out=ROOT/'kotoba-party/expanded-wiki-culture.json';meta=ROOT/'kotoba-party/expanded-wiki-culture.sources.json'
    data=json.loads(out.read_text());m=json.loads(meta.read_text());removed={}
    article_categories={}
    for file in CACHE.glob('*.json'):
        cached=json.loads(file.read_text())
        for page in cached.get('query',{}).get('pages',[]):
            article_categories.setdefault(page['pageid'],set()).update(c['title'] for c in page.get('categories',[]))
    def belongs(genre,article):
        cats=set(article.get('categories',[])) | article_categories.get(article['pageid'],set())
        # General-vocabulary imports were rejected after independent sampling:
        # topic membership admits adjacent concepts. Use curated/JMdict words.
        if genre in ('jobs','electronics','school','colors','things','actions','body'):return False
        if any(BADCAT.search(c) for c in cats):return False
        if genre not in ('games','anime','movies','music','characters'):
            irrelevant=re.compile(r'を題材|の楽曲|年のシングル|年のアルバム|年の映画|年の漫画|年のアニメ|博物館|美術館|高等学校|大学|選手権|大会|競技場|スタジアム|アリーナ|チーム|クラブ|代表チーム|スポーツ施設|協会|連盟|財団|ブランド|の一覧|スポーツ賞|の賞|神社|寺院|公園|遊園地|ドーム|組織|企業|会社|放送番組|テレビ番組|テレビドラマ')
            if any(irrelevant.search(c) for c in cats):return False
        if genre=='vehicles' and (re.search(r'賞$|賞の|受賞|第[0-9一二三四五六七八九十]+回',article['title']) or article['title']=='プロトタイプ'):return False
        if genre=='sports':
            eligible=re.compile(r'^Category:(スポーツ競技|球技|ウォータースポーツ|ラケットスポーツ|陸上競技種目|陸上競技の種目|ウィンタースポーツ|格闘技|武道|スポーツの種類|団体競技|個人競技|子供の遊び|遊び|遊戯|鬼ごっこ|伝承遊び|体育|体操|バット・アンド・ボール・ゲーム|マインドスポーツ|モータースポーツ|体操競技|水泳|スノーボード|スキーの競技種目|ニュースポーツ|ボールゲーム|自転車競技|サイクルスポーツ|格闘技の技|スポーツのルール)$')
            return any(eligible.search(c) for c in cats)
        if genre=='clothes':
            if re.search(r'パンチラ|ノーパン|ノーブラ|ファッションショー|フェティシズム|フェチ|制服効果|カジュアル化|アパレル|セクシー',article['title']):return False
            eligible=re.compile(r'^Category:(衣類|衣服|被服|洋服|和服|服飾|装身具|履物|靴|帽子|下着|手袋|眼鏡|鞄|ドレス|民族衣装|トップス|ボトムス|アウターウェア|衣服の部位|ヘアアクセサリー|アクセサリー|靴下|ユニフォーム|防寒具|帯|襟|袖|スカート|ズボン|シャツ|セーター|寝具|水着|制服|子供服|スポーツウェア|装飾品|被服材料|織物|布|毛皮|革|繊維製品|被り物)$')
            return any(eligible.search(c) for c in cats)
        if genre=='characters':
            if article['title'] in ('プリキュアカラフルコレクション','妖術'):return False
            if any(re.search(r'^Category:(.*(?:書籍|画集|イラスト集|図鑑)|架空の(?:能力|物質|技術|現象)|概念|呪術|魔術|妖術)$',c) for c in cats):return False
            if re.search(r'の登場|のキャラクター$|の怪獣$|のモンスター$',article['title']):return False
            acceptable=[c for c in cats if not re.search(r'を題材|キャラクターゲーム|の一覧',c)]
            return any(re.search(SPECS[genre]['accept'],c) for c in acceptable)
        return True
    extra=re.compile(r'団鬼六|シット・オン・マイ・フェイス|肉欲|情欲|欲情|恥辱|SMプレイ|レズビアン|SEX|セクシー|ヌード|性奴隷|好色|緊縛|官能')
    for genre,words in data.items():
        before=len(words);articles=m['articles'][genre]
        kept=[w for w in words if articles[w]['pageid'] not in blocked and clean(w) and not extra.search(w) and belongs(genre,articles[w]) and (genre not in REVIEWED_GENERAL or w in REVIEWED_GENERAL[genre])]
        for w in kept:
            if article_categories.get(articles[w]['pageid']):articles[w]['categories']=sorted(article_categories[articles[w]['pageid']])
        data[genre]=kept;m['articles'][genre]={w:articles[w] for w in kept};removed[genre]=before-len(kept)
    m['adultCategoryAudit']={'checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'Explicit categorymembers traversal to depth 4; exclude article IDs even if search deepcat was truncated; additional unsuitable-title exclusions.','categories':counts,'excludedArticleIds':len(blocked),'removedByGenre':removed}
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');meta.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    print('AUDIT REMOVED',json.dumps(removed,ensure_ascii=False),flush=True)
    print('FINAL COUNTS',json.dumps({k:len(v)for k,v in data.items()},ensure_ascii=False),flush=True)


def audit_work_types():
    """Verify each film / vehicle article has a subject-specific data infobox.

    Exact year categories can contain awards/indexes; deep transport categories can
    contain components. This is a stronger per-article type check for every record.
    """
    out=ROOT/'kotoba-party/expanded-wiki-culture.json';meta=ROOT/'kotoba-party/expanded-wiki-culture.sources.json'
    data=json.loads(out.read_text());m=json.loads(meta.read_text())
    templates={
      'movies':['Template:Infobox Film','Template:Infobox animanga/Movie'],
      'vehicles':['Template:Infobox 自動車のスペック表','Template:Infobox オートバイのスペック表','Template:鉄道車両'],
    }
    batches=[]
    for genre in templates:
        records=list(m['articles'][genre].items())
        for i in range(0,len(records),50):batches.append((genre,records[i:i+50]))
    accepted={g:{} for g in templates}
    def verify(batch):
        genre,records=batch;ids='|'.join(str(p['pageid']) for _,p in records)
        response=request({'pageids':ids,'prop':'templates','tlnamespace':10,'tllimit':'max','tltemplates':'|'.join(templates[genre])})
        pages=response.get('query',{}).get('pages',[])
        matches={p['pageid']:[t['title'] for t in p.get('templates',[])] for p in pages}
        return genre, {w:{**a,'typeEvidence':matches[a['pageid']]} for w,a in records if matches.get(a['pageid'])}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(verify,b) for b in batches]
        for i,f in enumerate(concurrent.futures.as_completed(futures)):
            genre,records=f.result();accepted[genre].update(records)
            if i%20==0:print('TYPE AUDIT',i+1,'/',len(batches),flush=True)
    counts={}
    for genre,records in accepted.items():
        before=len(data[genre]);data[genre]=[w for w in data[genre] if w in records]
        m['articles'][genre]={w:records[w] for w in data[genre]};counts[genre]={'retained':len(data[genre]),'rejected':before-len(data[genre])}
    m['typeAudit']={'checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'Every retained movie/vehicle article has an exact movie, car, motorcycle or train infobox; API templates metadata only.','templates':templates,'counts':counts}
    m['review']={'status':'Independent sample issues corrected; all movie and vehicle records received stronger infobox type verification.','generalGenresOmitted':['jobs','electronics','school','colors','things','actions','body'],'manualAllowlistGenres':['sports','clothes']}
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');meta.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    print('TYPE AUDIT RESULT',json.dumps(counts,ensure_ascii=False),flush=True)


def main():
    data={};source={}
    desired=os.getenv('KOTOBA_CULTURE_GENRES','').split(',')
    specs=[p for p in SPECS.items() if not desired[0] or p[0] in desired]
    out=ROOT/'kotoba-party/expanded-wiki-culture.json'; meta=ROOT/'kotoba-party/expanded-wiki-culture.sources.json'
    if out.exists(): data=json.loads(out.read_text())
    previous=json.loads(meta.read_text()) if meta.exists() else {}
    source=previous.get('articles',{})
    logs=previous.get('queries',{})
    extend_since=os.getenv('KOTOBA_CULTURE_EXTEND_SINCE','')
    if extend_since:
        suffixes={'games':['コンピュータゲーム'],'anime':['漫画','テレビアニメ'],'movies':['映画','アニメ映画'],'music':['シングル','楽曲']}
        specs=[(g,{**sp,'limit':int(os.getenv('KOTOBA_CULTURE_EXTEND_LIMIT','3000')),'queries':[category_query(range(int(extend_since),2027),suffixes[g])+' -deepcat:"アダルトゲーム" -deepcat:"成人向け漫画" -deepcat:"成人向けアニメ" -deepcat:"ポルノ映画" -deepcat:"ピンク映画"']}) for g,sp in specs if g in suffixes]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futures={ex.submit(collect,item):item[0] for item in specs}
        for future in concurrent.futures.as_completed(futures):
            try: genre,selected,queries = future.result()
            except Exception as e:
                print('FAILED',futures[future],repr(e),flush=True);continue
            if extend_since:
                selected={**source.get(genre,{}),**selected}
                queries=logs.get(genre,[])+queries
            data[genre]=list(selected);source[genre]=selected;logs[genre]=queries
            out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            meta.write_text(json.dumps({'source':'Japanese Wikipedia','sourceUrl':'https://ja.wikipedia.org/','license':'CC BY-SA 4.0','licenseUrl':'https://creativecommons.org/licenses/by-sa/4.0/','retrievedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'attribution':'Wikipedia contributors; original article/history accessible by pageid','modifications':'Selected article titles, normalized Unicode, stripped trailing disambiguators; excluded lists, biography/company pages and adult categories; no text or images copied.','method':'Exact year categories for works; category-validated subject searches otherwise; incoming-link rank; no generated combinations.','queries':logs,'articles':source},ensure_ascii=False,indent=2)+'\n')
    print('COUNTS',json.dumps({k:len(v)for k,v in data.items()},ensure_ascii=False),flush=True)

if __name__=='__main__':
    if os.getenv('KOTOBA_CULTURE_TYPE_AUDIT')=='1':audit_work_types()
    elif os.getenv('KOTOBA_CULTURE_AUDIT')=='1':audit_adult_categories()
    else:main()
