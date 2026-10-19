#!/usr/bin/env python3
"""Build a bounded, category-specific JMdict vocabulary; never makes up words.

Usage: python3 scripts/import-lexicon.py --input /tmp/jmdict-eng.json
The input is the unpacked, pinned upstream release listed in SOURCE_URL.
Source entries are reduced to one modern spelling; rare spellings, dialect,
archaic senses and unsuitable terms are excluded. No definitions are shipped.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://github.com/scriptin/jmdict-simplified/releases/download/3.6.2%2B20261012204142/jmdict-eng-3.6.2+20261012204142.json.tgz"
ARCHIVE_SHA256 = "4e742f7d5b0c59e6818c545b73ed3ca71618878de11f54876d3aa43a5f0cafa9"
BAD_TAGS = {"arch", "obs", "rare", "vulg", "X", "derog", "sens", "obsc", "dated", "sl", "proverb", "yoji", "organization", "company", "person", "given", "surname", "place", "station", "unclass", "dei", "leg", "myth", "fict"}
BAD_FORM_TAGS = {"rK", "sK", "iK", "oK", "rk", "sk", "ok", "ik"}
BAD_ENGLISH = re.compile(r"\b(sex|sexual|sexuality|pornograph\w*|penis|vagina|vulva|clitoris|testicle\w*|scrot\w*|masturbat\w*|prostitut\w*|erection|semen|ejaculat\w*|fuck\w*|shit\w*|cunt\w*|anus|anal|rectum|urine|feces|faeces|defecat\w*|genital\w*|rape|raping|murder\w*|suicid\w*|tortur\w*|executing|execution|killing|slaughter\w*|terroris\w*|racial|racist|offensive|slur|stupid|idiot|retard\w*|naked|nudity|nude|wearing nothing)\b", re.I)
BAD_JAPANESE = re.compile(r"[○〇×□]|性交|性行為|性器|陰茎|陰部|陰唇|陰毛|包皮|睾丸|肛門|膣|精液|射精|自慰|痴漢|変態|売春|風俗|殺|虐|拷問|差別|奴隷|放尿|排便|脱糞|血便|テレクラ|爆撃|空爆|主砲|砲弾|軍艦|戦艦|戦車|銃|刀剣|ポルノ|アダルト|エロ|倒閣|撃沈|酷使|殲滅|籠城|交戦|報復|威嚇|締殺|爆破|脅迫")
VERBS = {"v1", "v5u", "v5k", "v5g", "v5s", "v5t", "v5n", "v5b", "v5m", "v5r", "vk", "vs", "vs-i", "v5k-s", "v5r-i"}
ACTION_EXCLUDE = re.compile(r"\b(war|military|criminal|crime|arrest|prison|imprison|torture|execute|execution|invad\w*|attack|bomb\w*|tax\w*|investment|stock market|defeat|conquer|legislat\w*|discriminat\w*|punish\w*|persecut\w*|bankrupt\w*|bribe|bribery|censor\w*|embezzl\w*|convict\w*|indict\w*|lawsuit|deceiv\w*|fraud|smuggl\w*|conspir\w*|swindl\w*)\b", re.I)
FAMILIAR_ACTION = re.compile(r"\b(eat|drink|cook|wash|clean|sleep|wake|walk|run|jump|swim|dance|sing|laugh|smile|cry|read|write|draw|paint|play|open|close|push|pull|hold|carry|lift|throw|catch|ride|drive|buy|sell|shop|travel|visit|watch|listen|hear|speak|talk|say|ask|answer|wait|meet|help|thank|greet|rest|sit|stand|lie down|climb|slide|fold|cut|peel|mix|stir|bake|boil|fry|roast|grill|steam|pour|chew|taste|smell|touch|look|see|think|remember|forget|learn|teach|study|count|choose|search|find|lose|lend|borrow|wear|dress|change|pack|wrap|tie|untie|knit|sew|repair|make|build|plant|water|feed|pet|hug|wave|nod|clap|whistle|blow|yawn|sneeze|cough|stretch|exercise|bathe|shower|brush|comb|shave|dry|hang|sweep|wipe|polish|tidy|prepare|arrange|decorate|celebrate|invite|telephone|call|mail|photograph|record|print|copy|type|save|load|check|start|stop|finish|continue|return|leave|arrive|depart|commute|relax|enjoy|care|worry|surprise|expect|hope|wish|dream|promise|apologize|explain|understand|compare|decide|plan)\b", re.I)

def pattern(words):
    return re.compile(r"\b(?:" + "|".join(words.split("|")) + r")s?\b", re.I)

RULES = {
    "things": pattern("tool|utensil|furniture|plate|bowl|spoon|fork|knife|pan|pot|box|bag|bottle|basket|jar|canister|book|magazine|paper|card|pen|pencil|eraser|ruler|scissors|adhesive tape|glue|stapler|ink|brush|comb|mirror|towel|blanket|pillow|cushion|bed|mattress|chair|table|desk|shelf|drawer|cabinet|cupboard|door|window|curtain|carpet|rug|clock|watch|umbrella|wallet|key|lock|chain|rope|cord|string|wire|hook|nail|screw|hammer|saw|drill|wrench|pliers|needle|thread|button|zipper|candle|match|lighter|broom|mop|bucket|sponge|soap|detergent|dustpan|ashtray|toy|doll|kite|puzzle|board|bell|whistle|flag|signboard|envelope|postcard|postage stamp|newspaper|map|ticket|receipt|mask|helmet|goggles|lever|pedal|wheel|handle|knob|pipe|rod|pole|brick|tile|lumber|cement|plaster|container|vessel|tableware|cookware|cutlery|stationery|bedding|equipment|implement|accessory|trinket|ornament|vase|figurine|statue|calendar|notebook|diary|album|frame|canvas|easel|palette|crayon|chalk|charcoal|marker|whiteboard|blackboard|pin|clip|clamp|hinge|fastener|chain saw|shovel|spade|rake|hoe|sickle|shears|trowel|ladder|stepladder|scaffold|faucet|tap|sink|basin|bathtub|toilet|showerhead|plunger|drain|tub|futon|hammock|tent|tarpaulin|sleeping bag|ribbon|bead|dice|die|marble|balloon|confetti|present|souvenir|trophy|medal|cup|saucer|teacup|mug|tray|chopstick|skewer|ladle|spatula|whisk|strainer|colander|funnel|grater|peeler|rolling pin|chopping board|mort ar|pestle|thermos|flask|kettle|teapot|coaster|placemat|napkin|tablecloth|apron|oven mitt|utensil|suitcase|trunk|backpack|purse|pouch|sack|net|mesh|screen|partition|awning|blind|shutter|lintel|threshold|railing|banister|handrail"),
    "clothes": pattern("clothing|clothes|garment|dress|shirt|blouse|t-shirt|sweater|jumper|cardigan|vest|waistcoat|jacket|coat|overcoat|raincoat|parka|poncho|cape|cloak|robe|kimono|yukata|haori|hakama|obi|trouser|pant|jeans|shorts|skirt|suit|tuxedo|uniform|swimsuit|swimwear|underwear|underpants|brief|bra|brassiere|panties|sock|stocking|tights|legging|shoe|boot|sandal|slipper|sneaker|loafer|clog|geta|zori|tabi|footwear|hat|cap|beret|bonnet|hood|headband|hairband|hairpin|barrette|wig|scarf|shawl|stole|necktie|bow tie|glove|mitten|belt|suspender|bracelet|necklace|earring|pendant|brooch|cufflink|ring|jewelry|jewellery|accessories|handbag|purse|collar|sleeve|lapel|cuff|hem|pocket|seam|lining|pleat|frill|ruffle|lace|embroidery|knitwear|denim|flannel|velvet|satin|silk|cotton fabric|linen|wool fabric|fleece|tweed|suede|leather clothing|fashion|cosmetic|lipstick|mascara|eyeliner|eyeshadow|foundation makeup|blusher|rouge|nail polish|perfume|cologne|hairstyle|haircut|hairdo|braid|ponytail|pigtail"),
    "jobs": pattern("worker|employee|employer|manager|executive|director|supervisor|foreman|clerk|secretary|receptionist|assistant|accountant|auditor|banker|broker|trader|salesman|salesperson|shopkeeper|shop assistant|merchant|retailer|wholesaler|entrepreneur|businessperson|businessman|businesswoman|consultant|counselor|counsellor|lawyer|attorney|judge|prosecutor|solicitor|notary|police officer|policeman|firefighter|fireman|detective|guard|security officer|teacher|instructor|professor|lecturer|tutor|educator|principal|headmaster|headmistress|librarian|curator|researcher|scientist|engineer|technician|programmer|developer|analyst|designer|architect|planner|doctor|physician|surgeon|dentist|nurse|midwife|pharmacist|therapist|physiotherapist|veterinarian|vet|paramedic|nutritionist|dietician|dietitian|psychologist|counselor|caregiver|carer|social worker|babysitter|nanny|housekeeper|cleaner|janitor|caretaker|butler|maid|cook|chef|baker|butcher|fishmonger|greengrocer|grocer|confectioner|waiter|waitress|server|bartender|barista|sommelier|florist|hairdresser|barber|beautician|stylist|makeup artist|tailor|dressmaker|seamstress|shoemaker|cobbler|jeweler|jeweller|watchmaker|carpenter|plumber|electrician|welder|mechanic|mason|bricklayer|plasterer|roofer|painter|decorator|gardener|landscaper|farmer|fisherman|fisher|rancher|shepherd|dairyman|beekeeper|forester|lumberjack|miner|driver|chauffeur|pilot|copilot|sailor|seaman|captain|conductor|steward|stewardess|flight attendant|courier|postman|mailman|postal worker|delivery person|porter|baggage handler|mover|actor|actress|performer|comedian|entertainer|singer|musician|composer|songwriter|conductor|dancer|choreographer|model|announcer|presenter|host|reporter|journalist|editor|author|writer|novelist|poet|screenwriter|playwright|illustrator|cartoonist|animator|photographer|cameraman|filmmaker|producer|translator|interpreter|tour guide|travel agent|athlete|sportsman|sportswoman|coach|trainer|referee|umpire|lifeguard|instructor|priest|monk|nun|pastor|minister|fortune teller|magician|juggler|acrobat|clown|puppeteer|artisan|craftsman|craftswoman|potter|sculptor|weaver|dyer|brewer|winemaker|distiller|ferryman"),
    "school": pattern("school|classroom|schoolyard|schoolchild|schoolteacher|kindergarten|nursery school|elementary school|primary school|high school|secondary school|junior college|university|college|campus|curriculum|syllabus|lesson|homework|schoolwork|textbook|workbook|exercise book|school uniform|school bag|school lunch|school trip|school excursion|school festival|entrance examination|entrance exam|graduation|enrollment|enrolment|admission to school|academic year|school year|school term|school semester|school report|report card|classmate|class president|student council|student club|after-school|extracurricular|physical education|gymnastics|homeroom|morning assembly|sports day|athletic meet|athletics meet|field day|cultural festival|summer vacation|winter vacation|spring vacation|school holiday|school library|infirmary|staffroom|staff room|teachers' room|music room|science room|laboratory class|science class|art class|cooking class|home economics|handicraft|calligraphy|penmanship|arithmetic|multiplication table|summer festival|firework|bon festival|new year celebration|new year's day|christmas|halloween|valentine|birthday|wedding ceremony|coming-of-age|children's day|doll festival|star festival|sports festival|celebration|ceremony|festival|parade|carnival|anniversary"),
    "body": pattern("forehead|eyebrow|eyelash|eyelid|eyeball|iris|pupil of the eye|cornea|retina|nose|nostril|cheek|chin|jaw|lip|tongue|tooth|teeth|gum|palate|throat|tonsil|ear|earlobe|eardrum|neck|shoulder|arm|elbow|forearm|wrist|hand|palm|finger|thumb|fingernail|chest|breastbone|rib|backbone|spine|waist|abdomen|stomach|belly|navel|hip|buttock|leg|thigh|knee|calf|shin|ankle|heel|foot|feet|sole of the foot|toe|toenail|skin|hair|scalp|beard|moustache|mustache|sideburn|bone|joint|muscle|tendon|ligament|cartilage|nerve|brain|heart|lung|liver|kidney|intestine|spleen|pancreas|gallbladder|bladder|esophagus|oesophagus|trachea|bronchus|diaphragm|artery|vein|blood vessel|blood|lymph|lymph node|sweat gland|tear gland|salivary gland|biceps|triceps|quadriceps|hamstring|anklebone|collarbone|shoulder blade|breast|eyetooth|molar|incisor|wisdom tooth|canine tooth|taste bud|vocal cord|voice box"),
    "colors": pattern("red|blue|yellow|green|orange color|orange colour|purple|violet color|violet colour|pink|brown|black|white|gray|grey|beige|ivory|crimson|scarlet|vermilion|maroon|burgundy|magenta|fuchsia|lilac|lavender color|lavender colour|mauve|indigo|navy blue|azure|cyan|turquoise|teal|aqua|emerald green|olive green|lime green|chartreuse|khaki|ochre|ocher|amber color|amber colour|coral color|coral colour|salmon pink|peach color|peach colour|cream color|cream colour|tan color|tan colour|sepia|chocolate brown|coffee brown|silver color|silver colour|gold color|gold colour|copper color|copper colour|bronze color|bronze colour|color|colour|striped pattern|checkered pattern|checked pattern|polka dot|paisley|tartan|houndstooth|herringbone|argyle|floral pattern|geometric pattern|camouflage pattern|animal print|leopard print|zebra pattern|tiger stripe|gradient|gradation|monochrome|pastel|neon color|neon colour|fluorescent color|fluorescent colour"),
    "music": pattern("musical instrument|instrumental music|piano|organ|keyboard instrument|guitar|bass guitar|violin|viola|cello|double bass|contrabass|harp|flute|piccolo|clarinet|oboe|bassoon|saxophone|sax|trumpet|trombone|tuba|french horn|euphonium|cornet|bugle|harmonica|accordion|concertina|melodica|recorder|ocarina|panpipe|bagpipe|ukulele|banjo|mandolin|lute|sitar|shamisen|koto|biwa|shakuhachi|shinobue|taiko|drum|snare drum|bass drum|timpani|cymbal|tambourine|castanet|maraca|triangle instrument|xylophone|marimba|vibraphone|glockenspiel|celesta|chime|gong|bell|percussion instrument|tambour|bongo|conga|djembe|cajon|harmonium|harpsichord|clavichord|hurdy-gurdy|balalaika|bouzouki|dulcimer|zither|erhu|guzheng|pipa|sheng|suona|dizi|kalimba|mbira|didgeridoo|steelpan|steel drum|synthesizer|turntable|phonograph|record player|music|musical|melody|harmony|rhythm|tempo|beat|chord|tune|song|singing|vocal|chorus|choir|orchestra|ensemble|band|concert|recital|opera|operetta|symphony|concerto|sonata|suite|overture|etude|nocturne|rhapsody|serenade|march music|waltz|polka|jazz|blues|rock music|pop music|folk music|country music|classical music|hip-hop|rap music|reggae|ska|punk rock|heavy metal|disco music|soul music|funk music|gospel music|hymn|ballad|lullaby|anthem|carol|chant|mantra|refrain|verse|lyric|score|sheet music|notation|clef|octave|semitone|solfege|arpeggio|vibrato|tremolo|staccato|legato|crescendo|diminuendo|forte|pianissimo|allegro|adagio|andante|presto|metronome|tuning fork|capo|plectrum|guitar pick|drumstick|baton|mute|reed|mouthpiece|fret|fretboard|fingerboard|bridge of an instrument|soundboard|resonator"),
    "electronics": pattern("computer|laptop|tablet computer|smartphone|mobile phone|cell phone|cellular phone|telephone|television|television set|tv set|radio|transistor radio|camera|digital camera|video camera|camcorder|projector|monitor|display screen|touchscreen|touch screen|keyboard|computer mouse|trackpad|touchpad|joystick|game controller|game console|video game console|printer|scanner|photocopier|fax machine|facsimile machine|modem|router|hub|switching hub|server|hard disk|hard drive|solid state drive|flash drive|usb drive|memory card|memory stick|sd card|optical disk|optical disc|compact disc|cd player|dvd player|blu-ray|disk drive|disc drive|floppy disk|floppy disc|headphone|earphone|earbud|headset|speaker|loudspeaker|microphone|amplifier|audio amplifier|receiver|tuner|audio recorder|tape recorder|cassette player|walkman|turntable|phonograph|record player|stereo system|boombox|bluetooth|wifi|wi-fi|wireless lan|antenna|aerial|cable|connector|adapter|adaptor|charger|battery|power bank|power supply|solar panel|socket|plug|outlet|extension cord|power strip|switch|remote control|refrigerator|freezer|washing machine|dryer|dishwasher|microwave oven|oven|toaster|toaster oven|rice cooker|electric kettle|coffee maker|coffee machine|blender|food processor|juicer|mixer|electric grill|hot plate|induction cooker|electric pot|vacuum cleaner|robot vacuum|air conditioner|air conditioning|electric fan|ceiling fan|ventilator|heater|electric heater|space heater|humidifier|dehumidifier|air purifier|hair dryer|hairdryer|electric shaver|electric razor|electric toothbrush|electric iron|sewing machine|electric blanket|heated blanket|electric carpet|massage chair|massager|electric pump|electric motor|light bulb|lamp|lighting fixture|flashlight|torch|lantern|led light|fluorescent lamp|incandescent lamp|neon lamp|alarm clock|digital clock|digital watch|smartwatch|calculator|electronic dictionary|electronic book|e-reader|gps|navigation system|dashcam|security camera|surveillance camera|doorbell|intercom|smoke detector|fire alarm|carbon monoxide detector|thermometer|digital scale|weighing scale|blood pressure monitor|hearing aid|electronic instrument|electrical appliance|home appliance|household appliance"),
}

# Bilingual safeguards: English homonyms such as ruler, organ, school, suit,
# monitor, cleaner and cabinet are not enough to decide a Japanese category.
JP_ENDINGS = {
    "body": r"(?:指|爪|手|腕|肘|肩|骨|筋|関節|肌|毛|髪|舌|歯|唇|口|鼻|耳|目|眼|眉|顔|頭|脳|首|胸|背|腹|腰|尻|足|脚|膝|踵|踝|心臓|肺|肝臓|胃|腎臓|腸|血液|血管|脈|神経|乳房|臍|皮膚|角膜|網膜|鼓膜|気管|気管支|食道|へそ|つむじ|うなじ|もみあげ|ほほ|ほっぺ|ほっぺた|おでこ|ひたい|のど|喉|腱|上皮|表皮|涙腺|汗腺|唾液腺|粘膜|横隔膜|じん帯|靭帯|靱帯|胆嚢|胆のう|すい臓|膵臓|脾臓|リンパ|つま先|かかと|すね)$",
    "things": r"(?:具|器|機|装置|設備|装飾|飾り|工具|用具|道具|家具|寝具|食器|文房具|文具|ガラス|鏡|ケース|カバー|バッグ|バック|ベルト|マット|タオル|ペン|紙|袋|箱|缶|瓶|びん|ビン|かご|カゴ|籠|篭|皿|鉢|碗|椀|カップ|コップ|ボウル|茶碗|茶わん|茶わん|湯のみ|湯飲み|グラス|ジョッキ|マグ|ボトル|チューブ|ポット|やかん|ヤカン|鍋|ケットル|ケトル|パン|刃|刀|包丁|ナイフ|フォーク|スプーン|箸|はし|はさみ|ハサミ|さじ|匙|へら|ヘラ|お玉|布|クロス|レース|ネクタイ|トレイ|トレー|盆|机|椅子|いす|イス|チェア|デスク|テーブル|ベンチ|棚|シェルフ|ラック|キャビネット|箪笥|たんす|タンス|ロッカー|引き出し|押し入れ|押入れ|本|誌|書|辞典|辞書|ノート|手帳|日記|アルバム|帳|葉書|はがき|ハガキ|封筒|カード|札|券|チケット|地図|図鑑|標識|掲示板|看板|黒板|白板|ホワイトボード|ボード|盤|パネル|ガイドブック|ガラス戸|戸|扉|ドア|窓|門|シャッター|カーテン|カーペット|ラグ|絨毯|じゅうたん|マットレス|布団|ふとん|ベッド|寝台|枕|まくら|ピロー|毛布|ブランケット|タオルケット|シーツ|クッション|座布団|ずきん|帽子|ハット|キャップ|マスク|仮面|ヘルメット|ゴーグル|櫛|くし|クシ|ブラシ|刷毛|筆|鉛筆|クレヨン|チョーク|マーカー|インク|インキ|のり|糊|接着剤|テープ|ゴム|消しゴム|石鹸|石けん|せっけん|洗剤|クリーナー|シャンプー|リンス|スポンジ|たわし|タワシ|ほうき|ホウキ|箒|ちりとり|モップ|バケツ|桶|盥|洗面器|鍬|鋤|ショベル|シャベル|スコップ|鋏|鋸|のこぎり|ノコギリ|ハンマー|金槌|かなづち|釘|ネジ|ねじ|螺子|螺旋|針|ピン|鋲|ホッチキス|ステープラ|パンチ|クリップ|ペンチ|ニッパー|レンチ|ドライバー|ドリル|定規|物差し|ものさし|メジャー|コンパス|分度器|糸|縄|綱|紐|ひも|ヒモ|ロープ|ワイヤー|針金|鎖|チェーン|リボン|網|ネット|網戸|蚊帳|トランク|スーツケース|リュック|鞄|かばん|カバン|財布|さいふ|サイフ|ハンドバッグ|ハンドバック|ポーチ|小銭入れ|キーホルダー|かぎ|鍵|錠|南京錠|傘|かさ|カサ|パラソル|人形|ぬいぐるみ|おもちゃ|玩具|パズル|凧|こま|独楽|積み木|ブロック|ビー玉|おはじき|風船|バルーン|骰子|サイコロ|さいころ|花火|クラッカー|トランプ|カルタ|かるた|かざぐるま|風車|オルゴール|ベル|鈴|鐘|ホイッスル|笛|旗|はた|ろうそく|ロウソク|ローソク|蝋燭|キャンドル|マッチ|ライター|ランタン|ランプ|提灯|ちょうちん|トーチ|懐中電灯|ライト|時計|ウォッチ|置時計|置き時計|目覚まし|温度計|体温計|計り|はかり|バネ|ばね|スプリング|車輪|ホイール|歯車|ギア|レバー|ペダル|ハンドル|ノブ|つまみ|取っ手|ボタン|ホック|ファスナー|チャック|金具|フック|蝶番|ヒンジ|棒|竿|ポール|柱|支柱|手すり|欄干|額縁|フレーム|板|合板|木材|木炭|石炭|レンガ|れんが|煉瓦|タイル|セメント|粘土|石膏|ブリキ|テント|タープ|ハンモック|寝袋|ストーブ|焜炉|コンロ|グリル|炊飯器|トースター|フライパン|鉄板|まな板|壺|つぼ|ツボ|花瓶|トロフィー|メダル|楯|盾|賞状|記章|徽章|バッジ|スタンプ|印鑑|判子|はんこ|ハンコ|贈り物|プレゼント|置物|彫像|銅像|像|記念品|土産|お土産|みやげ|粗品|模造品|パレット|イーゼル|キャンバス|額|トイレットペーパー|ティッシュペーパー|しおり|栞)$",
    "electronics": r"(?:機|器|装置|計|電池|テレビ|ラジオ|プレイヤー|プレーヤー|レコーダー|プロジェクター|モニター|ディスプレイ|スクリーン|スマホ|スマートフォン|タブレット|パソコン|コンピュータ|コンピューター|ラップトップ|ノートパソコン|ワークステーション|サーバー|ルーター|モデム|ハブ|スキャナ|スキャナー|プリンタ|プリンター|キーボード|マウス|トラックボール|トラックパッド|タッチパッド|コントローラ|コントローラー|ジョイスティック|カメラ|ヘッドホン|イヤホン|ヘッドフォン|イヤフォン|マイク|スピーカ|スピーカー|ヘッドセット|アンプ|チューナー|コンセント|プラグ|アダプタ|アダプター|ケーブル|コード|バッテリー|コネクター|コネクタ|スイッチ|リモコン|チャージャー|リーダー|ドライブ|ハードディスク|フロッピーディスク|メモリ|メモリー|メモリーカード|カードリーダー|エアコン|クーラー|ヒーター|ホットプレート|ホットカーペット|冷蔵庫|冷凍庫|オーブン|電子レンジ|レンジ|トースター|ポット|ホットポット|ミキサー|フードプロセッサー|ブレンダー|ジューサー|シェーバー|ドライヤー|アイロン|ミシン|電灯|電球|蛍光灯|照明|ネオンサイン|ＬＥＤ|LED|目覚まし|ラジカセ|ステレオ|コンポ|ウォークマン|CD|DVD|ＭＤ|ＭＰ３|カセットデッキ|オーディオ|電話|電話機|公衆電話|インターホン|ファクシミリ|ファックス|ＦＡＸ|FAX|アンテナ|ナビ|カーナビ|ドラレコ|ドローン|ホバークラフト|電卓|デジカメ|デジ一|コンデジ|デジいち)$",
    "jobs": r"(?:師|士|家|医|長|官|員|職|職人|役|者|屋|業|工|農|農民|漁師|僧|僧侶|神主|神官|神父|牧師|記者|選手|運転手|操縦手|棋士|力士|監督|元締め|親方|店主|芸人|料理人|商人|船頭|番人|女中|女優|俳優|男優|子役|声優|歌手|歌人|詩人|筆者|陶工|書記|大臣|総理|大工|とび職|コック|シェフ|バーテン|バーテンダー|ソムリエ|バリスタ|ウェイター|ウェイトレス|ウェイター|ウエーター|ウエートレス|パティシエ|ブーランジェ|モデル|アイドル|タレント|アナウンサー|レポーター|リポーター|キャスター|コメンテーター|パーソナリティ|コメディアン|マジシャン|ジャグラー|ピエロ|クラウン|ダンサー|シンガー|ソングライター|ミュージシャン|ピアニスト|ギタリスト|ベーシスト|ドラマー|バイオリニスト|ヴァイオリニスト|チェリスト|オペレーター|プログラマー|エンジニア|デザイナー|イラストレーター|アニメーター|ライター|ジャーナリスト|フォトグラファー|カメラマン|プロデューサー|ディレクター|エディター|スタイリスト|ヘアメイク|メイクアップアーティスト|カウンセラー|セラピスト|トレーナー|コーチ|インストラクター|ドクター|ナース|パイロット|ドライバー|ガードマン|ポーター|ヘルパー|ベビーシッター|ハウスキーパー|メイド|バトラー|コンシェルジュ|レセプショニスト|バーバー|テーラー|ジュエラー|フローリスト|ガーデナー|プランナー|コンサルタント|アナリスト|バイヤー|ブローカー|ディーラー|セールスマン|ビジネスマン|マネージャー|アシスタント|スーパーバイザー|キュレーター|レフェリー|レフリー|アンパイア|リフリー|ジャッジ|スポーツマン|アスリート|アーティスト|クリエイター|クリエーター)$",
}

COMMON_EXCLUDE = set("ゴールデンアワー|シュミットカメラ|トーチ|ラウドスピーカー|レシーバー|寒暖計|無線|講師|鍵盤|ケルン|サンチュール|シャッポ|シートベルト|スペンサージャケット|ハイレグ|パンティー|プレタポルテ|ヘム|ベルトコンベア|ボーカラー|マキシ|ミディ|モアレ|モード|一律|一様|土俵|左前|時流|芳香|じゃんけん|ガスマスク|グルー|クロック|ジェットコースター|ジャパンカップ|スーパーチェーン|スーパーボウル|ソープ|チョキ|デビスカップ|ドーマーウインドー|ナショナルチェーン|バックスクリーン|パー|フィナカップ|フラッグ|ブック|ブルペン|ホイール|マガジン|マーブル|ミスマッチ|リターンマッチ|リーグ戦|ワールドカップ|一同|一時|一杯|三時|三輪|両輪|九九|交番|今昔|会計検査院|入金|入閣|公式戦|分かれ目|分割|分岐点|別表|北極|南極|取締役会|受領|口笛|名著|大陸棚|山岳|当分|影の内閣|打席|指針|教育委員会|旧暦|机上|枠組み|気球|水車|汽笛|流域|現在|現有|現行|画面|盆地|目下|目次|短調|福助|窓際|答案|紙上|総統|胴体|脊髄|船舶|艦船|艦艇|血管|覇者|見張り|試合|誌上|読本|警鐘|議長|賜杯|賞牌|連鎖|長調|開幕|閣内|閾値|零時|領収|馬券|黒幕|黒木|４時|７時|オールドガード|ガストアルバイター|ギャルソン|クラーク|クリーナー|コングロマーチャント|シェパード|スクリプター|チューター|テクニシャン|フォアマン|レガース|元本|前衛|力学|厳戒|執行部|宰相|掃除機|旅行会社|海上保安庁|目抜き|管長|紺屋|行政|親衛|近衛|選者|量販店|開発元|首脳部|馬車|魔法使い|たんす|ガム|ゴム|ニー|ネック|ハイヒール|ヒール|フィート|リブ|ルンゲ|レバー|土足|子牛|心中|手中|手持ち|手洗い|拍手|毒舌|洗髪|満腹|耳目|肩こり|空腹|胸中|胸襟|腹いっぱい|舌打ち|苦慮|襟元|豊胸|金脈|ブルース|音色|ドラム缶|内臓|呼吸器|強み|泌尿器|琵琶湖|臓器|融和|調和|鼓動|一校|一派|全学|全校|卒業後|同校|園内|学内|教訓|新派|旧派|本校|校内|流派|目盛り|示し|電通大|魚群".split("|"))

def base(text):
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(chr(ord(c)-96) if "ァ" <= c <= "ヶ" else c for c in text)
    return re.sub(r"[\s・･\-‐‑–—ー]", "", text)

def spelling(word, sense):
    kanji = [x for x in word["kanji"] if not set(x["tags"]) & BAD_FORM_TAGS]
    kana = [x for x in word["kana"] if not set(x["tags"]) & BAD_FORM_TAGS]
    if not kana:
        return None
    # A usually-kana word is shown in its normal reading (e.g. はさみ, not 鋏).
    if "uk" in sense["misc"]:
        return next((x["text"] for x in kana if x["common"]), kana[0]["text"])
    return next((x["text"] for x in kanji if x["common"]), (kanji or kana)[0]["text"])

def head_phrase(gloss):
    """The noun being defined, excluding modifiers/comparisons/examples.

    A 'black cat' is a cat, not a color; a 'computer animation' isn't a PC.
    A 'ticket examiner' is a person, not a ticket. Matching the phrase's final
    noun deliberately sacrifices coverage to prevent these category errors.
    """
    stripped = re.sub(r"\([^)]*\)", "", gloss).strip()
    head = re.split(r"[,;:]|\s+(?:of|for|with|without|from|in|on|at|by|to|that|which|used|using|worn|made|having|worn|representing|wielded)\s+", stripped, maxsplit=1)[0]
    return head.strip(" -/.")

def is_category_noun(category, regex, gloss, fields, japanese):
    reviewed_exclusions = {
        "music": {"重金属"},
        "clothes": {"胃壁", "腸壁", "子宮内膜", "血管内皮", "内膜", "胃粘膜", "粘膜", "膀胱"},
        "jobs": {"サンデードライバー", "恩師", "主人役", "日曜大工", "素人役者", "免許皆伝", "役者不足"},
        "electronics": {"盗撮カメラ", "盗聴器", "盗聴機", "盗聴マイク"},
    }
    if japanese in reviewed_exclusions.get(category, set()):
        return False
    if category in JP_ENDINGS and not re.search(JP_ENDINGS[category], japanese):
        return False
    if re.search(r"\([A-Z][a-z]+ [a-z]+(?:[, )])", gloss):
        return False  # A scientific species name is not a household object.
    if fields & {"mil", "Buddh", "Shinto", "Christn", "law", "finc", "stockm", "politics", "math", "chem", "ling", "gramm", "logic", "stat", "genet", "biochem", "psyanal", "psych", "psy", "pathol", "surg", "dent", "pharm", "med", "zool", "bot", "fish", "ornith", "ent"}:
        return False
    if category != "electronics" and fields & {"comp", "internet", "elec", "electr", "telec"}:
        return False
    head = head_phrase(gloss)
    match = regex.search(head)
    matches = list(regex.finditer(head))
    if not matches or matches[-1].end() != len(head):
        return False
    if category == "colors":
        # Only a color/pattern itself. Phrases such as "red tape" never qualify.
        if re.search(r"\b(?:image|picture|print|flower|plant|tree|seaweed|algae|bird|fish|snake|turtle|lizard|wine|bean|rice|hair|eye|skin|blood|person|paper|ink|dye|paint|pigment|crayon|pencil|chalk|powder|stain|sauce|sugar|salt|pepper|tea|coffee|school|flag|team|party|army|dragon|tile|emblem|banner|clothes|cloth|garment|robe|dress|shirt|shoe|trouser|uniform|coat|hat|collar|metamorphosis|complement|sense|change|representation|quality|sort|type)\b", head, re.I):
            return False
        if re.search(r"(?:色|縞|格子|模様|柄|紋|斑|トーン|カラー|ブルー|レッド|グリーン|ピンク|イエロー|オレンジ|ブラウン|ブラック|ホワイト|グレー|グレイ|パープル|バイオレット|ベージュ|アイボリー|ネイビー|カーキ|セピア|マゼンタ|シアン|モノクロ|カモフラージュ|チェック|ドット|ストライプ|ボーダー|パステル)$", japanese) is None:
            return False
        if japanese in {"音色", "地方色", "ローカルカラー", "アールグレイ", "保護色", "政党色", "声色", "顔色", "毛色", "血色", "目の色", "肌色", "目色", "腹黒色"} or re.search(r"\b(?:local|national|political|tone|timbre|face|hair|eyes|skin|earl|film|movie|novel|album|lyric|song|flag|emblem)\b", gloss, re.I):
            return False
        if re.search(r"\b(?:blues|winter|depression|depressive|syndrome|illness|disease|disorder|gloom|sad|sadness|unhappy|melancholy|feel|feeling|emotion|mood|angry|anger|sorrow|flower|seaweed|tea|coffee|drink|wine|juice|alga|algae|plumage|greenery)\b", gloss, re.I):
            return False
    if category == "body":
        # Require the dictionary's anatomy field for supplementary terms.
        # Existing hand-curated familiar body words remain in the base dictionary.
        if "anat" not in fields:
            return False
        if re.search(r"\b(?:disease|illness|cancer|infection|injury|wound|inflammation|tumor|tumour|pain|ache|symptom|disorder|syndrome|reconstruction|implant|artificial|prosthetic|fake|imitation|false|operation|surgery|transplant|blood-shedding|bleeding|bloody|weapon|military|army|naval|armed|combat|fighting|joint venture|joint committee|person|someone|one who|animal|fish|bird|lizard|frog|snake|plant|tree|flower|fruit|nut|seed|rice|bean|headwind|aircraft|plane|ship|machine|wooden|wood|handshake|embrace|clasp|chemical|laboratory|spirit)\b", gloss, re.I):
            return False
        if "anat" not in fields and re.search(r"\b(?:joint|palm|iris|nerve|hand|arm|foot|bone|breast|blood|heart|stomach|hair|skin|tongue|tooth|leg|backbone|sole|muscle)s?\b", head, re.I):
            # Ambiguous words need direct anatomical context or Japanese anatomy.
            if re.search(r"指|爪|手|腕|肘|肩|骨|筋|関節|皮|肌|毛|髪|舌|歯|口|鼻|耳|目|眼|眉|顔|頭|脳|首|胸|背|腹|腰|尻|足|脚|膝|踵|踝|心|肺|肝|胃|腎|腸|血|脈|神経|乳|臍|へそ|つむじ|うなじ|もみあげ|ほほ|ほっぺ|おでこ|ひたい|のど|喉|アキレス|キューティクル|エナメル", japanese) is None:
                return False
        if re.search(r"\b(?:stiff|numb|sore|aching|injured|broken|sprained|cramped|tired|weak|trembling|paralyzed|paralysed|chilled|cold|warm|heated|hot|empty|full|gold|silver|copper|tin|iron|steel|mineral|golden|bleached|dyed|comb|combed|curled|perm|permed|joint action|armed force|military force|nerve to|courage|audacity|bravery)\b", gloss, re.I):
            return False
        if re.match(r"\w+ing\b", head) and not re.match(r"(?:ring|ringing|string)\b", head):
            return False
    if category in {"things", "electronics", "clothes"}:
        if re.search(r"\b(?:person|someone|examiner|collector|employee|worker|keeper|smoker|store|shop|company|corporation|agency|government|ministry|department|party|business|trade|market|account|profit|loss|balance|budget|price|cost|expense|ratio|rate|coefficient|syndrome|disease|noise|lizard|dragon|turtle|monkey|bird|fish|frog|snake|insect|plant|tree|flower|fruit|bean|rice|bread|cake|mushroom|alga|algae|seaweed|software|program|programming|command|algorithm|function|code|text|character|notation|logic|variable|parameter|element|symbol|protocol|control|operation|management|processing|computation|calculation|service|support|animation|broadcast|broadcasting|station|channel|show|series|event|meeting|festival|rehearsal|practice|policy|regulation|law|rule|method|system|technique|science|theory|problem|solution|abstraction|memory allocation)\b", gloss, re.I):
            return False
    if category == "things":
        if re.search(r"\b(?:video clip|audio clip|movie clip|music video|tournament|championship|league|contest|competition|world cup|world championship|poem|poetry|song title|novel title|film title)\b", gloss, re.I) or japanese in {"フィナカップ", "ジャパンカップ", "ワールドカップ", "デビスカップ", "スーパーボウル"}:
            return False
    if category == "electronics":
        if re.search(r"\b(?:guest speaker|native speaker|speaker of|public speaker|keynote speaker|main speaker|after-dinner speaker|lecture|orator|speech|spokesman|spokesperson|lecturer|information hub|transport hub|transportation hub|wheel hub|bicycle hub|book|novel|movie|film|story|fairytale|fiction)\b", gloss, re.I):
            return False
        if re.search(r"\bhub\b", head, re.I) and not (fields & {"comp", "internet", "telec"} or re.search(r"USB|ＵＳＢ|接続|ネットワーク|イーサ|スイッチング", japanese)):
            return False
    if category == "jobs":
        if re.search(r"\b(?:company|agency|corporation|department|office|bureau|ministry|headquarters|committee|commission|council|cabinet|association|organization|school|university|college|institution|hospital|bank|factory|shop|store|firm|software|program|device|equipment|support|insurance|welfare|benefit|salary|wage|pay|fee|expense|cost|record|register|book|diary|list|name|title|license|licence|certificate|qualification|badge|uniform|hat|coat|car|train|ship|model|statue|image|figure|picture|painting|portrait|medicine|drug|product|goods|food|meal|tea|coffee|tea ceremony|job offer|position|appointment|employment|workforce|labor force|unemployed)\b", head, re.I):
            return False
    if category == "music":
        if re.search(r"\b(?:organ|band|beat|bell|gong|suite|record|recorder|march|score|notation|verse|reed|mute|bridge|baton|key|tune|harmony|drum)s?\b", head, re.I) and "music" not in fields:
            if re.search(r"(?:音|曲|歌|楽|奏|唱|笛|鐘|鼓|弦|琴|箏|琵琶|三味線|ギター|ベース|バンド|リズム|ビート|メロディ|オルガン|ホルン|チャイム|コーラス|クワイア|レコーダー|リコーダー|ソング|ボーカル|ヴォーカル|ロック|ラップ|ジャズ|ブルース|ポップ|パンク|メタル|シンセ|アコーディオン|チューバ|ヴァイオリン|バイオリン|チェロ|フルート|クラリネット|オーボエ|ファゴット|バスーン|トランペット|トロンボーン|サックス|ピアノ|ハープ|ハーモニカ|ウクレレ|マンドリン|バンジョー)$", japanese) is None:
                return False
        if re.search(r"(?:管|血|肺|腎|肝|胃|泌尿|臓|行政|内閣|政府|軍|戦|放送|電波|ワイドバンド|狭帯域|広帯域|体|神経|湖|地形|岩石|割れ|缶|ドラム缶)", japanese) or re.search(r"\b(?:film|movie|novel|theory|political|electrical|electronic circuit|computer|organism|organisms|urinary|digestive|reproductive|internal organ|internal organs|coastal|government|administrative|oil drum|radio frequency|wide-band|narrow-band|telephone|cooperation|concord)\b", gloss, re.I):
            return False
        if re.search(r"\b(?:rubber band|hair band|head band|wrist band|wristband|armband|arm band|ribbon|gasket|belt|bangle|bracelet|ring|finger ring|engagement ring|wedding band|watch band|frequency band|wavelength band|collection of poems|poetry collection|poems|poetry)\b", gloss, re.I):
            return False
    if category == "school":
        if re.search(r"(?:学派|流派|一派|新派|旧派|派|魚群|目盛り)$", japanese) or re.search(r"\b(?:school of thought|philosoph|philosophy|sect|confucian|buddhis|taois|zen|fish|fishes|schooling|Warring States|dynasty|discuss|opinion|political|politics|ancient|Edo period|Heian period|Kamakura period|Muromachi|feudal|Tokugawa|hypothesis)\b", gloss, re.I):
            return False
        if re.search(r"\b(?:school|college|university|academy)s?\b", head, re.I) and not re.search(r"(?:学校|校|大学|高校|学園|幼稚園|中学|小学|短大|学院|予備校|スクール|カレッジ|キャンパス|専修|塾|大学院|専門|早慶|国公立|私立|公立|国立)$", japanese):
            return False
    if category == "clothes":
        if re.search(r"\b(?:lawsuit|court|law|damage|damages|bridge game|card game|cards|playing cards|poker|suited|identical|uniformity|unvarying|unvaried|same|dentistry|dentist|tooth|teeth|gear|mechanism|conveyor|seat belt|seatbelt|lap belt|seal|gasket|piston|boxing ring|sumo ring|wrestling ring|golf|surrounding|circle|circuit|group|gang|ring of|paint|coating|bodywork|horse|animal|bird|fish|fruit|plant|flower|vine|spaghetti)\b", gloss, re.I):
            return False
        if re.search(r"\b(?:onion ring|onion rings|french toast|croissant|croissants|doughnut|doughnuts|donut|donuts|pasta|pizza|roll|rolls|sushi|sashimi|ring cake|food|pastry|dessert|sugar|chocolate|candy|sweet|confectionery)\b", gloss, re.I):
            return False
        if re.search(r"\b(?:stomach|intestinal|intestine|uterine|uterus|bladder|artery|vein|vessel|cornea|retina|blood|skin|organ|organs|mucous|mucosa)\b", gloss, re.I):
            return False
        if japanese in {"略叙", "お手元金", "同一", "一様", "一律", "均一", "土俵", "ケルン", "シートベルト", "ベルトコンベア", "ボンネット", "アクセサリーシュー", "ホットシュー", "カラーリング", "紫帯", "黒帯", "黄帯", "輪", "ループ", "円環", "環", "リングノート"}:
            return False
    return True

def build(source):
    data = json.loads(source.read_text())
    categories = collections.defaultdict(list)
    common = collections.defaultdict(list)
    entries = collections.defaultdict(list)
    seen = collections.defaultdict(set)
    review = collections.defaultdict(list)
    for word in data["words"]:
        # First sense avoids e.g. human jobs inferred from figurative meanings.
        sense = word["sense"][0]
        if sense["dialect"] or set(sense["misc"]) & BAD_TAGS:
            continue
        if any(set(s["misc"]) & {"X", "vulg", "derog"} for s in word["sense"]):
            continue
        glosses = [g["text"] for g in sense["gloss"] if g["lang"] == "eng"]
        gloss = "; ".join(glosses)
        if not gloss or BAD_ENGLISH.search(gloss):
            continue
        text = spelling(word, sense)
        if not text or not 2 <= len(text) <= 18 or BAD_JAPANESE.search(text):
            continue
        is_common = any(f["common"] for f in word["kanji"] + word["kana"])
        fields, pos = set(sense["field"]), set(sense["partOfSpeech"])
        targets = []
        if is_common and not fields and VERBS & pos and not ACTION_EXCLUDE.search(gloss):
            if glosses[0].startswith("to ") or ("n" in pos and ("vs" in pos or "vs-i" in pos) and re.match(r"[a-z]+ing\b", glosses[0])):
                targets.append("actions")
        if "n" in pos:
            for category, regex in RULES.items():
                # Only inspect the first definition, not remote/secondary senses.
                if is_category_noun(category, regex, glosses[0], fields, text):
                    targets.append(category)
            if fields & {"music"} and len(text) <= 12 and not re.search(r"ポルノ|アダルト|エロ", text):
                targets.append("music")
            if fields & {"cloth"} and len(text) <= 12:
                targets.append("clothes")
        for cat in set(targets):
            k = base(text)
            if k in seen[cat]:
                continue
            seen[cat].add(k)
            categories[cat].append(text)
            entries[cat].append(word["id"])
            if is_common and text not in COMMON_EXCLUDE and (cat != "actions" or FAMILIAR_ACTION.search(glosses[0])):
                common[cat].append(text)
            review[cat].append([text, glosses[0], word["id"], is_common])
    for values in categories.values():
        values.sort()
    for values in common.values():
        values.sort()
    meta = {
        "source": "JMdict (Electronic Dictionary Research and Development Group; project begun by Jim Breen), JSON conversion by scriptin/jmdict-simplified",
        "sourceUrl": "https://github.com/scriptin/jmdict-simplified",
        "upstreamLicenseUrl": "https://www.edrdg.org/edrdg/licence.html",
        "upstreamLicenseDescription": "EDRDG licence (same as upstream JMdict)",
        "licenseEvidenceUrl": "https://github.com/scriptin/jmdict-simplified#jmdict-and-jmnedict",
        "attribution": "JMdict is the property of the Electronic Dictionary Research and Development Group. This derivative vocabulary is used and distributed in conformance with the Group's licence, under the same conditions as upstream JMdict.",
        "releaseUrl": SOURCE_URL,
        "archiveSha256": ARCHIVE_SHA256,
        "dictionaryDate": data["dictDate"],
        "inputSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "modifications": "Category selection; unsuitable/obsolete/rare/dialect exclusions; one modern spelling per entry; no definitions included; kana and punctuation deduplication. See scripts/import-lexicon.py.",
        "counts": {k: len(v) for k, v in categories.items()},
    }
    (ROOT / "kotoba-party/expanded-lexicon.json").write_text(json.dumps(dict(categories), ensure_ascii=False, indent=2) + "\n")
    # Upstream common flags measure dictionary frequency, not game familiarity.
    # The app's existing human-curated familiar list must retain its priority.
    (ROOT / "kotoba-party/expanded-common.json").write_text("{}\n")
    (ROOT / "kotoba-party/expanded-lexicon-sources.json").write_text(json.dumps({"metadata": meta, "entryIds": dict(entries)}, ensure_ascii=False, indent=2) + "\n")
    Path("/tmp/lexicon-review.json").write_text(json.dumps(dict(review), ensure_ascii=False, indent=2))
    print(json.dumps({"counts": meta["counts"], "commonCounts": {}}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    build(args.input)
