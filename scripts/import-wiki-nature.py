#!/usr/bin/env python3
"""Rebuild the nature/food/place dictionary from Japanese Wikipedia titles.

Only page titles and category metadata are read; article text and images are not
copied. Uses the ordinary HTTPS proxy and verified TLS inherited from the host.
Two workers, 100 search hits per batch, stable popularity ordering, local cache.
HTTP 403 is fatal and never retried or routed around.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import http.client
import json
import pathlib
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = pathlib.Path('/tmp/kotoba-wiki-nature-cache')
API = 'https://ja.wikipedia.org/w/api.php'
UA = 'KotobaPartyDictionary/1.0 (https://github.com/mateo-purple/any)'
CONFIG = {
    'food': [('料理', 10000), ('食材', 3000)],
    'sweets': [('菓子', 6000), ('デザート', 1000)],
    'drinks': [('飲料', 9000)],
    'animals': [('魚類', 5000), ('鳥類', 6000), ('昆虫', 4000), ('爬虫類', 2000), ('両生類', 1500), ('軟体動物', 2000), ('哺乳類', 6000)],
    'plants': [('植物', 10000), ('キク科', 1500), ('ラン科', 1500), ('バラ科', 1500), ('マメ科', 1500), ('イネ科', 1500), ('ナス科', 800), ('アブラナ科', 800), ('シダ植物', 1500), ('コケ植物', 1000), ('裸子植物', 1200), ('多肉植物', 1000), ('果物', 1500), ('野菜', 1500), ('シソ科', 800), ('セリ科', 800), ('ツツジ科', 800), ('ユリ科', 800), ('キンポウゲ科', 800), ('ヒガンバナ科', 800), ('アヤメ科', 800), ('ナデシコ科', 800), ('クスノキ科', 800), ('ヤナギ科', 800), ('アオイ科', 1000), ('ツバキ科', 800), ('キョウチクトウ科', 800), ('サトイモ科', 800), ('ウコギ科', 800)],
    'world': [('都市', 7000), ('地方区分', 4000), ('国', 2000), ('日本の市町村', 5000), ('中国の都市', 3000), ('ヨーロッパの都市', 4000), ('アメリカ合衆国の都市', 5000)],
    'sights': [('観光地', 9000)],
    'places': [('公共施設', 3000), ('建築物', 7000)],
    'nature': [('気象', 4000), ('地形', 6000), ('鉱物', 3000), ('天体', 6000)],
}

# Genre membership is checked against actual page categories: deepcat alone also
# finds TV shows, companies and biographies several levels below a food category.
BAD_CATS = re.compile(r'人物|年生$|年没$|企業|会社|メーカー|業者|団体|組織|協会|学会|チーム|クラブ|選手|競走馬|競走犬|牧場|賞$|受賞|事件|事故|戦争|戦闘|災害|地震|台風|台風の|映画|漫画|アニメ|テレビ|ラジオ|番組|楽曲|アルバム|小説|文学|雑誌|書籍|ゲーム|ブランド|政党|政治家|法令|条約|法律|条例|犯罪|侵害|差別|殺人|虐待|性風俗|色情|AV女優|ポルノ|鉄道路線|鉄道車両|軍事|軍艦|兵器')
BAD_TITLE = re.compile(r'一覧|リスト|の歴史|の一覧|の分類|の文化|の経済|の政治|の交通|の教育|における|について|に関する|問題$|事件$|事故$|協会$|学会$|会社$|法人$|株式会社|研究所$|センター試験|差別|虐殺|慰安婦|性交|性器|射精|ポルノ|アダルト|エロ|おっぱい|陰茎|陰核|膣|睾丸|精液|肛門|レイプ|セックス|糞|糞便|排泄|排尿|死体|自殺|殺害|殺人|感染症|ウイルス|寄生虫|病$|症$')
POSITIVE = {
    'food': re.compile(r'料理$|食品$|食材$|調味料$|加工品$|発酵|保存食|麺|パン$|豆腐|漬物|ソース|チーズ|乳製品|寿司|食肉|乾物|香辛料|主食|スープ|サラダ|鍋料理|穀物|食用'),
    'sweets': re.compile(r'菓子$|菓子の商品名$|菓子パン$|デザート$|ケーキ$|アイスクリーム$|チョコレート$|キャンディ$|クッキー$|ビスケット$|プリン$|餅$|ドーナツ$|和スイーツ$|洋スイーツ$|甘味$|グミ$|ガム$'),
    'drinks': re.compile(r'飲料$|飲料の商品名$|飲み物$|カクテル$|ワイン$|ビール$|日本酒$|焼酎$|ウイスキー$|ウィスキー$|ブランデー$|リキュール$|蒸留酒$|醸造酒$|果実酒$|コーヒー$|茶$|茶の商品名$|炭酸飲料$|ジュース$|牛乳$|酒$'),
    'animals': re.compile(r'科$|属$|目$|動物$|哺乳類$|爬虫類$|両生類$|鳥類$|魚類$|昆虫$|節足動物$|軟体動物$|甲殻類$|犬種$|猫種$|犬の品種$|猫の品種$|カタツムリ$|クモ$|貝類$|水鳥$|海鳥$|猛禽類$|ペット$|恐竜$'),
    'plants': re.compile(r'植物$|樹木$|草木$|野菜$|果物$|果実$|花卉$|花木$|ハーブ$|穀物$|菌類$|キノコ$|コケ$|シダ$|ヤシ$|花$|木$|木の実$|ブドウの品種$|イチゴの品種$|リンゴの品種$|イネの品種$|サクラの品種$'),
    'world': re.compile(r'国家$|国$|の都市$|の州$|の県$|の郡$|の市$|の町$|の村$|の市町村$|の地域$|の地方$|地方区分|行政区画|自治体|自治州|自治共和国|自治管区|連邦管区|首都$|州都$|県都$|政令指定都市'),
    'sights': re.compile(r'観光地$|名所|名勝|世界遺産|公園|庭園|神社|寺院|城$|の城|宮殿|教会|修道院|大聖堂|遺跡|動物園|植物園|水族館|美術館|博物館|遊園地|テーマパーク|展望|タワー|橋$|灯台|温泉|ビーチ|海水浴|記念碑|遊歩道|山$|火山|湖$|湾$|滝$|島$|海岸|岬$'),
    'places': re.compile(r'施設|建築|建物|図書館|博物館|美術館|会館|劇場|映画館|公民館|学校|公園|神社|寺院|教会|病院|市場|商店街|住宅|団地|タワー|ビル|港$|空港|鉄道駅|サービスエリア|道の駅|体育館|競技場|運動場|ドーム|ホテル|旅館|温泉|水族館|動物園|植物園|郵便局|警察署|消防署|橋$|ダム$'),
    'nature': re.compile(r'(^|の)(地形|地質|地学|気象|天気|気候|雲|風|雨|雪|霧|自然現象|大気|空|海|海洋|山|火山|高原|平野|盆地|台地|山脈|山地|谷|渓谷|川|河川|湖|池|泉|滝|湾|半島|島|諸島|砂漠|森林|草原|湿原|湿地|洞窟|鍾乳洞|氷河|惑星|恒星|星雲|星団|銀河|星座|衛星|天体|天文現象|流星|彗星|太陽|月)$|地形$|気象現象$|自然現象$|海流$|暖流$|寒流$|火山$|温泉地$|鉱物$|岩石$|宝石$|結晶$|恒星$|変光星$|矮星$|巨星$|惑星$|星雲$|星団$|銀河$|星座$|隕石$|彗星$'),
}
SWEET_NON_DESSERTS = {
    '土産', '駄菓子屋', '駄菓子バー', 'ビーントゥーバー', 'カカオ',
    'ココアバター', '上新粉', 'バター', 'ショウガ', 'ユーフー',
    'まねき馬倶楽部', 'ココア', '白玉粉', 'きな粉', '種実類',
    'チョコレート色', 'テオブロミン', 'ファットブルーム', '純チョコレート規格',
    '和菓子の日', 'アイスクリーム頭痛', 'キャンディ・デスク', 'かたさ度',
    '全国和菓子甲子園', '菓子屋横丁', 'カカオベルト', 'エシカルスイーツ',
    '日本のカカオ産業', '巻き菓子のある静物', 'ガムボール自動販売機', 'ケラーマシン',
    'お好み焼き', 'もんじゃ焼き', 'たこ焼き', '土産物',
    'テンパリング', 'ひえづマルシェ', '千鳥屋', 'ケーキ屋',
    'スイーツ男子', 'お菓子リュック', 'ホワイト・カーゴ',
}
DRINK_NON_BEVERAGES = {
    'エタノール', '上水道', '醸造', '発酵', '花見', '蒸留', 'アルコール度数',
    'バーテンダー', 'カフェイン', '茶商', '酢酸イソアミル', '茶鋏',
    'ワインの化学', '醸造家', '抗酸化飲料サーバー', 'ウイスキーキャット',
    'とりあえずビール', 'スティルトン', 'バッター液', '破精', '杜氏',
    'ネゴシアン', 'ソムリエ', 'ティーマスター', '利き酒', '唎酒',
    '茶柱', '茶筅', '茶筌', '茶杓', '茶道', '茶室', '茶人', '茶器', '茶碗',
    '茶箱', '茶棚', '急須', '酒器', '酒粕', '酒米', '水質', '軟水器',
    '禁酒法', '禁酒', '飲酒', '飲酒文化', 'ミルク缶', 'ビールサーバー',
    '乳製品', 'ブドウ', 'ペットボトル', 'ウイスキーボンボン',
    '悪魔の取り分', 'ニホンコウジカビ', '桔梗ヶ原', 'フーゼル油',
    'ワイングラス', 'アルコールプルーフ', '桑茶政策', 'スピークイージー',
    'ラムネ瓶', '酒屋', '茶園', '葡萄園', '保護原産地呼称', '茶草場農法',
    'カプロン酸エチル', 'リノール酸エチル', '高温糖化法', '長野県原産地呼称管理制度',
    '一杯のおいしい紅茶', '千厩酒のくら交流施設', 'クラッシュドアイス',
}
PLANT_FAMILIES = set(('アオイ アオキ アカザ アカテツ アカネ アケビ アブラナ アヤメ イイギリ イグサ イチイ イチョウ イネ イラクサ ウコギ ウリ ウルシ エゴノキ オオバコ オトギリソウ オシロイバナ カエデ カタバミ カツラ カバノキ カヤツリグサ カンナ キキョウ キク キジカクシ キツネノマゴ キョウチクトウ キンポウゲ クスノキ クマツヅラ クワ ケシ コショウ ゴマ ゴマノハグサ サクラソウ ザクロ サトイモ サボテン シソ シナノキ シクンシ シュウカイドウ シュロソウ ショウガ スイカズラ スイレン スベリヒユ スミレ セリ センリョウ タデ ツゲ ツツジ ツバキ ツユクサ トウダイグサ トケイソウ トチノキ ドクダミ ナス ナデシコ ニガキ ニシキギ ニレ ノウゼンカズラ パイナップル ハス バラ ヒガンバナ ヒノキ ヒユ ヒルガオ フウロソウ ブドウ フトモモ ブナ ベンケイソウ ホウセンカ マキ マタタビ マツ マツムシソウ マメ ミカン ミズキ ミソハギ ムクロジ メギ モクセイ モクレン ヤシ ヤナギ ユキノシタ ユリ ラン リンドウ レンプクソウ クルミ ヤマモモ ビャクダン ヤドリギ ハマウツボ モチノキ スズカケノキ スギ イワタバコ ハエドクソウ カバノキ アケビ ツヅラフジ マンサク ツリフネソウ イワウメ ヒメシラタマソウ ガガイモ アザミ ブナシメジ シメジ ハラタケ テングタケ ベニタケ イグチ サルノコシカケ ホウライタケ ヒラタケ タマチョレイタケ モエギタケ タケノコチャワンタケ ツチダンゴ フウチョウソウ ウマノスズクサ アワゴケ ヒシ グネツム マオウ ウツボカズラ モウセンゴケ タヌキモ バショウ ゴクラクチョウカ パパイア キントラノオ サガリバナ クロウメモドキ バンレイシ ヤマゴボウ').split())
PLANT_TAXA = {family+'科' for family in PLANT_FAMILIES} | set('サクラ バラ キク ラン マツ スギ ヒノキ ユリ アヤメ カキ カエデ モミジ クヌギ コナラ ナラ ブナ ミズナラ シダ スゲ タケ コケ ミカン リンゴ ナシ イチゴ ブドウ アンズ トウヒ モミ ツガ エノキ ケヤキ ゼルコバ ホオズキ ナス イネ イヌワラビ ワラビ オシダ イワヒバ スギナ シロイヌナズナ カラタチ ポプラ ヤナギ ウメ ケシ シャクナゲ ツツジ カシ マメ ニンジン ベゴニア アロエ アガベ ハオルチア エケベリア ガステリア エウフォルビア センペルビウム サボテン'.split())
PLANT_TAXA |= {word+'属' for word in list(PLANT_TAXA) if not word.endswith('科')}

def normalized(s):
    return unicodedata.normalize('NFKC', s).casefold().replace(' ', '').replace('・', '')

def accepted(genre, page, seed=None):
    title = page.get('title', '')
    if page.get('ns', 0) != 0 or 'disambiguation' in page.get('pageprops', {}):
        return None
    if BAD_TITLE.search(title) or re.search(r'\d|[A-Za-z]{3,}|[:：/]|「|」', title):
        return None
    if re.search(r'脱法|違法|麻薬|大麻|覚醒剤|危険ドラッグ|抗がん|発癌|発がん|毒性|致死|毒物|中毒|奴隷|強制収容', title):
        return None
    name = re.sub(r'\s*[（(][^()（）]*[)）]$', '', title).strip()
    if not 2 <= len(name) <= 22:
        return None
    categories = [c['title'].removeprefix('Category:') for c in page.get('categories', [])]
    if any(BAD_CATS.search(c) for c in categories):
        return None
    if any(re.search(r'童話|民話|神話|伝説|物語|おとぎ話|イベント|騒動|刑務所|収容所|絵画|美術作品|コンテスト|記念日|随筆|エッセイ|評論|詩集|詩人', c) for c in categories):
        return None
    plant_taxon = genre == 'plants' and (any(c in PLANT_TAXA for c in categories) or (seed is not None and seed not in ('植物', '果物', '野菜') and any(re.search(r'科$|属$', c) for c in categories)))
    if not any(POSITIVE[genre].search(c) for c in categories) and not plant_taxon:
        return None
    if genre in ('animals', 'plants'):
        if re.search(r'科$|属$|目$|綱$|門$|類$|亜科$|亜属$|上科$|下目$|分類|系統|亜種|遺伝|ゲノム|細胞|組織|学$|療法|生態|生理|形態|器官|標本|剥製|解剖|飼育|養殖|栽培|園芸|現象|分布|絶滅|保護|一覧|交配|学名|進化|人類|ホモ・|ヒト属', name):
            return None
        if not re.search(r'[ァ-ヶ]', name):
            return None
        if any(re.search(r'動物学|植物学|生物学|栽培技術|生殖|細胞|性$|学説|人体|人類|組織|神話|伝説|架空|キャラクター|技法', c) for c in categories):
            return None
        if any(re.search(r'動物園|植物園|公園|博物館|水族館|貝塚|遺跡|施設|牧場|マスコット|殺虫剤|農薬|医薬品|化合物|配糖体|アルカロイド|フラボノイド|テルペン|フェノール|アミノ酸|有機酸|タンパク質|糖類|ステロイド|毒素|食品$|料理$|調味料|混合香辛料|調合香辛料|香辛料の混合物|植物の成分|化学物質', c) for c in categories):
            return None
        if re.search(r'レース$|王国$|発生地$|群$|の枝$|係数$|値$|度$|ポプリ$|ソース$|オイル$|コウジ$|毒$|毒素$|ヒ素$', name):
            return None
    if genre == 'animals' and (any(c in PLANT_TAXA or re.search(r'植物|樹木|野菜|果物|菌類|キノコ|植物の品種', c) for c in categories) or name in {'イクラ', 'ウニ丼', 'フカヒレ', 'サンゴ礁'} or re.search(r'ネット$|捕獲器$|水槽$|虫かご$|罠$|網$|捕虫器$|防虫剤$', name)):
        return None
    if genre == 'plants' and (any(re.search(r'動物|哺乳類|爬虫類|鳥類|魚類|昆虫|犬種|猫種|犬の品種|猫の品種|ウシの品種|ウマの品種|品種\s*\(動物|飲料|ワイン$|ビール$|カクテル|ソフトドリンク', c) for c in categories) or name in {'スサノオ', 'ワイン', 'ウシ', 'ヒ素', 'エコナ', 'ペリー', 'フルーツポンチ', 'ポプリ', 'アコニチン', 'タバコ', 'ガストロジン', 'エルブ・ド・プロヴァンス'}):
        return None
    if genre == 'world' and (name.endswith(('料理', '語', '大学', '公国', '王国', '帝国', '朝')) or any(re.search(r'歴史|かつて|旧制|廃止|歴史上|旧国名', c) for c in categories)):
        return None
    if genre == 'world' and re.search(r'の(?:地方行政区画|行政区画|地方区分|自治体|市町村|都市|州|県|郡|地域|地方)$|^行政区画の', name):
        return None
    if genre in ('food', 'sweets', 'drinks') and any(re.search(r'飲食店|店舗|店$|レストラン|食品安全|食の安全|調理法|製法|製造|技術|器具|機械|装置|ロボット|自動販売機|博物館|施設|学問|食事法|栄養|アレルギー|添加物|料理人|食の祭典|祭り|食品関連|化学物質|有機化合物|キサンチン|規格|法規|男性を指す|女性を指す|消費行動|工作|手芸', c) for c in categories):
        return None
    if genre == 'food' and name in {'ジャンボおしどり寿司', '時価'}:
        return None
    if genre in ('food', 'sweets', 'drinks') and (re.search(r'学$|製法$|製造$|発酵$|醸造$|蒸留$|菌$|カビ$|酵母$|屋$|店$|茶園$|葡萄園$|ブドウ園$|ワイナリー$|マルシェ$|現象$|原産地|呼称|制度$|政策$|ブーム$|貿易$|の食用利用$|農法$|化法$|処理$|栽培$', name) or name in {'八百善'} or any(re.search(r'食品科学|生化学|化合物|化学工学|醸造学|職業|上水道|水処理|醸造用微生物|飲食店', c) for c in categories)):
        return None
    if genre == 'sweets' and (any(re.search(r'菓子材料|食玩|玩具|カードゲーム|食品包装|香辛料|穀物|甘味料|カクテル', c) for c in categories) or name in SWEET_NON_DESSERTS or name.endswith('料理')):
        return None
    if genre == 'drinks' and re.search(r'酒蔵|酒造|醸造|蒸溜所|蒸留所|酒税|アルコール依存|飲酒|未成年|禁酒|仕込み|仕込|発酵|焙煎|濾過|ろ過|抽出|ネゴシアン|酒米|酒粕|ノキ$', title):
        return None
    if genre == 'drinks' and (name in DRINK_NON_BEVERAGES or any(re.search(r'容器|包装|果物|科$|属$|リサイクル', c) for c in categories)):
        return None
    if genre == 'drinks' and re.search(r'グラス$|瓶$|びん$|酸エチル|^エチル|アルデヒド|酸$|油$|プルーフ$|職人$|の化学$|の取り分$|浄水|農園$|ケトル$|ポット$|サーバー$', name):
        return None
    if genre == 'drinks' and (re.search(r'ゼリー|プリン|ケーキ|チョコレート$|ガム|ミントタブレット|茶柱|茶器|茶碗|ティーセット|コーヒーメーカー|コーヒーフィルター|コーヒーミル|ドリッパー|焙煎|抽出|杜氏|唎酒|利き酒|ソムリエ', name) or any(re.search(r'菓子|デザート|料理$|器具|茶道|茶人|菓子の商品名|野菜|食品添加物', c) for c in categories)):
        return None
    if genre in ('places', 'sights') and any(re.search(r'建築様式|建築構造|建築材料|建築史|建築学|工法|祭り|年中行事|スポーツ$|スポーツ用語|登山$|観光用語|観光の形式|旅行の形式|艦船|鉄道車両|スローガン', c) for c in categories):
        return None
    if genre in ('places', 'sights') and (re.search(r'造$|造り$|機$|装置$|用具$|百選$|百景$|名数$|^日本百名', name) or name in {'大阪市電', '自動改札機', 'マンホール', '竹垣'} or any(re.search(r'建築部材|庭園材料|造園用具|機器|装置|機械|家具|インテリア|路面電車|鉄道事業者', c) for c in categories)):
        return None
    if genre == 'nature' and (name.endswith(('学', '計', '法', '説', '理論')) or any(re.search(r'人工衛星|宇宙機|宇宙船|宇宙探査|打ち上げ|ロケット|天文台|望遠鏡|気象機関|気象会社|学者|観測装置', c) for c in categories)):
        return None
    if genre == 'nature' and (not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', name) or any(re.search(r'架空|フィクション|施設|建築|建造物|博物館|美術館|科学館|資料館|遺跡|観測所|職業|資格|国家試験|工業|工場|産業|鉱業|炭鉱|鉱山|道路|橋梁|鉄道|港湾|測位|機器|装置|機械|コンピュータ|ソフトウェア|衣服|服飾|スポーツ競技|ウィンタースポーツ|スポーツ用品|キャンプ用品|年中行事|祭り|情報システム|地理情報システム|競技会|研究機関|画家|文化財|人造石|人工宝石|模造宝石|宝石加工|用水|運河|疏水|灌漑', c) for c in categories)):
        return None
    if genre == 'nature' and any(re.search(r'の県$|の市$|の市町村$|の都市$|の町$|の村$|の郡$|の州$|自治体|行政区画', c) for c in categories):
        return None
    if genre == 'nature' and (re.search(r'ダム$|用水$|上水$|運河$|疏水$|分水路$|堰$|水路$|発電所$|炭鉱$|鉱山$|銀山$|金山$|銅山$|鉱区$|教会$|寺$|寺院$|神社$|神宮$|博物館$|資料館$|科学館$|美術館$|天文台$|観測所$|指針$|システム$|ナビゲーション$|情報$|観測年$|ショーツ$|リゾート$|温泉旅館$|温泉ホテル$', name) or name in {'スキー', '登山', 'スノーボード', 'キャンプ', '正月', '温泉地熱料理', '気象予報士', '風力発電', '地獄釜', '内湯', '未回収のイタリア', 'バルト帝国', 'クエント', 'コスモオーラ'}):
        return None
    return name

def request(params):
    encoded = urllib.parse.urlencode(params)
    path = CACHE / (hashlib.sha256(encoded.encode()).hexdigest()+'.json')
    if path.exists():
        return json.loads(path.read_text())
    req = urllib.request.Request(API+'?'+encoded, headers={'User-Agent': UA, 'Accept': 'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                data = json.load(response)
            if data.get('error'):
                if data['error'].get('code') == 'maxlag' and attempt < 2:
                    time.sleep(3)
                    continue
                raise RuntimeError(str(data['error']))
            path.write_text(json.dumps(data, ensure_ascii=False))
            time.sleep(.15)
            return data
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(2 + attempt * 2)
        except (http.client.RemoteDisconnected, TimeoutError, ConnectionError) as exc:
            if attempt == 2:
                raise
            time.sleep(2 + attempt * 2)
    raise RuntimeError('No response')

def fetch_seed(seed, limit):
    params = dict(action='query', generator='search', gsrsearch='deepcat:"'+seed+'"', gsrnamespace=0, gsrlimit=100, gsrsort='incoming_links_desc', prop='categories|pageprops', cllimit='max', clshow='!hidden', ppprop='disambiguation', format='json', formatversion=2, maxlag=5)
    pages = {}
    while True:
        data = request(params)
        for row in data.get('query', {}).get('pages', []):
            key = row['pageid']
            if key in pages:
                pages[key].setdefault('categories', []).extend(row.get('categories', []))
                pages[key].setdefault('pageprops', {}).update(row.get('pageprops', {}))
            else:
                pages[key] = row
        cont = data.get('continue')
        if not cont or int(cont.get('gsroffset', 0)) >= limit:
            break
        for key in ['gsroffset', 'clcontinue', 'continue', 'ppcontinue']:
            params.pop(key, None)
        params.update(cont)
    return sorted(pages.values(), key=lambda row: row.get('index', 10**9))

def collect(genre):
    words, seen, info, original_titles = [], set(), [], {}
    for seed, limit in CONFIG[genre]:
        try:
            rows = fetch_seed(seed, limit)
        except (http.client.RemoteDisconnected, TimeoutError, ConnectionError) as exc:
            info.append(dict(seed=seed, maxSearchHits=limit, error=type(exc).__name__))
            print(f'{genre}: {seed} incomplete: {type(exc).__name__}', flush=True)
            continue
        added = 0
        for row in rows:
            word = accepted(genre, row, seed)
            if word and normalized(word) not in seen:
                seen.add(normalized(word))
                words.append(word)
                if word != row['title']:
                    original_titles[word] = row['title']
                added += 1
        info.append(dict(seed=seed, maxSearchHits=limit, inspected=len(rows), acceptedUnique=added))
        print(f'{genre}: {seed} {len(rows)} inspected / {added} added / {len(words)} total', flush=True)
    return genre, words, info, original_titles

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--genres', nargs='*', choices=CONFIG, default=list(CONFIG))
    args = parser.parse_args()
    CACHE.mkdir(exist_ok=True)
    output = ROOT/'kotoba-party/expanded-wiki-nature.json'
    report_path = ROOT/'kotoba-party/expanded-wiki-nature.sources.json'
    result = json.loads(output.read_text()) if output.exists() else {}
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    report.update(source='Japanese Wikipedia page titles and categories', api=API, retrieved=datetime.datetime.now(datetime.timezone.utc).date().isoformat(), license='CC BY-SA 4.0', licenseUrl='https://creativecommons.org/licenses/by-sa/4.0/', attribution='Wikipedia contributors', sourceUrl='https://ja.wikipedia.org/', changes='Titles selected by category, suitability filtered, trailing disambiguation labels removed and normalized duplicates removed. No article text or images included.')
    report.setdefault('genres', {})
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(collect, genre): genre for genre in args.genres}
        failures = []
        for future in concurrent.futures.as_completed(futures):
            try:
                genre, words, info, original_titles = future.result()
            except Exception as exc:
                print(f'FAILED {futures[future]}: {type(exc).__name__}: {exc}', flush=True)
                failures.append(futures[future])
                continue
            result[genre] = words
            report['genres'][genre] = {'words': len(words), 'queries': info, 'originalTitles': original_titles}
            if any(query.get('error') for query in info):
                failures.append(genre)
            for path, data in [(output, result), (report_path, report)]:
                pending = path.with_suffix(path.suffix+'.tmp')
                pending.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
                pending.replace(path)
    print(json.dumps({key: len(words) for key, words in result.items()}, ensure_ascii=False))
    if failures:
        raise SystemExit('Incomplete genres: '+', '.join(failures))

if __name__ == '__main__':
    main()
