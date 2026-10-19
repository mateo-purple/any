#!/usr/bin/env python3
"""Rebuild the reviewed Japanese WordNet supplement (standard library + Node).

python3 scripts/import-wordnet.py --source-dir /tmp/kotoba-wordnet --download

The curated choices are explicit, one spelling per sense, and are checked against
both the source lexical entries and the positive noun hypernym hierarchy. This
never classifies by substring matching an English definition. Raw source archives
remain outside the app; only reviewed Japanese words and provenance are shipped.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'kotoba-party'
SOURCES = [
    {'filename': 'wnja-2.0.xml', 'url': 'https://github.com/bond-lab/wnja/releases/download/v2.0/wnja-2.0.xml', 'sha256': 'c5fa7512f4d420db95a54ad3f84ed4bdc55bdfdff5dc4b79c4064954978fbc9d'},
    {'filename': 'wordnet.zip', 'url': 'https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip', 'sha256': 'cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59'},
]
# Princeton WordNet 3.0 noun offsets. Japanese WordNet 2.0 adds its own noun
# hypernym edges to these; using the graph keeps homonymous senses separate.
ROOTS = {
    'food': ['07555863'],
    'drinks': ['07881800'],
    'sweets': ['07596967', '07597365', '07609840'],
    'things': ['03563967', '03405725', '03094503', '06258852', '03964744', '02820210', '03932670'],
    'clothes': ['03051540', '03597469', '03113152'],
    'electronics': ['03269401', '03278248', '03528263'],
    'jobs': ['09632518', '09616922', '10480253', '09820263'],
    'vehicles': ['04524313'],
    'body': ['05220461'],
    'colors': ['04956594', '03011162', '03516367', '03978300', '04683136'],
    'music': ['03800933'],
    'plants': ['00017222', '07705931', '07707451', '07737081', '07734744', '12997919'],
    'animals': ['00015388'],
}
EXCLUDED = ['04565375', '03764276', '05513302', '13087625', '10317007', '10622053']


def checked_sources(directory, download):
    directory.mkdir(parents=True, exist_ok=True)
    for spec in SOURCES:
        target = directory / spec['filename']
        if not target.exists():
            if not download:
                raise SystemExit(f'Missing {target}; use --download to fetch the pinned public sources.')
            temporary = target.with_suffix(target.suffix + '.part')
            # urllib inherits the session proxy and trusted CAs; TLS is verified.
            with urllib.request.urlopen(spec['url'], timeout=60) as response, temporary.open('wb') as out:
                while data := response.read(1 << 20):
                    out.write(data)
            temporary.replace(target)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != spec['sha256']:
            raise SystemExit(f'Source checksum mismatch: {target}')


def read_graph(directory):
    children = defaultdict(set)
    with zipfile.ZipFile(directory / 'wordnet.zip') as archive:
        noun_data = archive.read('wordnet/data.noun').decode()
    for line in noun_data.splitlines():
        if not line or not line[0].isdigit():
            continue
        fields = line.split('|', 1)[0].split()
        offset = fields[0]
        index = 4 + 2 * int(fields[3], 16)
        pointer_count = int(fields[index])
        index += 1
        for _ in range(pointer_count):
            relation, target, pos, _ = fields[index:index + 4]
            index += 4
            # Instance-of relations deliberately excluded: jobs get occupations,
            # not the names of individuals who held them.
            if relation == '@' and pos == 'n':
                children[target].add(offset)
    lexicon = ET.parse(directory / 'wnja-2.0.xml').getroot().find('Lexicon')
    for synset in lexicon.findall('Synset'):
        if synset.get('partOfSpeech') != 'n':
            continue
        sid = synset.get('id').split('-')[1]
        for relation in synset.findall('SynsetRelation'):
            target = relation.get('target').split('-')[1]
            if relation.get('relType') == 'hypernym':
                children[target].add(sid)
            elif relation.get('relType') == 'hyponym':
                children[sid].add(target)
    attested = defaultdict(set)
    for entry in lexicon.findall('LexicalEntry'):
        lemma = entry.find('Lemma')
        if lemma.get('partOfSpeech') != 'n':
            continue
        # Curated nature labels may use the source's normal katakana reading.
        # These readings never generate extra entries: one chosen label per sense.
        forms = {lemma.get('writtenForm')}
        forms.update(f.get('writtenForm') for f in entry.findall('Form') if f.get('script') in (None, 'kana'))
        for sense in entry.findall('Sense'):
            if float(sense.get('confidenceScore', '1')) >= 0.85:
                attested[sense.get('synset')].update(forms)
    return children, attested


def descendants(roots, children):
    seen, pending = set(), list(roots)
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(children[node])
    return seen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=Path('/tmp/kotoba-wordnet'))
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    checked_sources(args.source_dir, args.download)
    graph, attested = read_graph(args.source_dir)
    curation = json.loads((APP / 'wordnet-curation.json').read_text())
    excluded = descendants(EXCLUDED, graph)
    all_words = [record['word'] for records in curation.values() for record in records]
    canonical = json.loads(subprocess.check_output(
        ['node', '-e', "const fs=require('fs'),E=require('./kotoba-party/engine.js');process.stdout.write(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(E.key)));"],
        input=json.dumps(all_words, ensure_ascii=False).encode(), cwd=ROOT))
    keys = dict(zip(all_words, canonical))
    output, records = {}, {}
    for category, choices in curation.items():
        if category not in ROOTS:
            raise SystemExit(f'Unknown category: {category}')
        eligible = descendants(ROOTS[category], graph) - excluded
        if category in ('plants', 'animals'):
            eligible = descendants(ROOTS[category], graph) - descendants(['02472293', '00007846', '01321579', '07992450'], graph)
        if category == 'things':
            eligible -= descendants(['04524313', '03051540', '03597469', '03278248', '03269401'], graph)
        output[category], records[category] = [], []
        used_words, used_synsets = set(), set()
        for choice in choices:
            word, synset = choice['word'], choice['synset']
            if synset.split('-')[1] not in eligible or word not in attested[synset]:
                raise SystemExit(f'Unattested or misclassified choice: {category} / {synset} / {word}')
            if synset in used_synsets:
                raise SystemExit(f'Multiple spellings of one sense: {category} / {synset}')
            used_synsets.add(synset)
            key = keys[word]
            if not key or key in used_words:
                continue
            used_words.add(key)
            output[category].append(word)
            records[category].append({'word': word, 'synset': synset})
    provenance = {
        'source': 'Japanese WordNet 2.0 + Princeton WordNet 3.0 noun hierarchy',
        'homepage': 'https://bond-lab.github.io/wnja/index.ja.html',
        'sources': SOURCES,
        'licenseFile': 'wordnet-LICENSE.txt',
        'licenseUrls': [
            'https://raw.githubusercontent.com/bond-lab/wnja/v2.0/docs/license.txt',
            'https://wordnet.princeton.edu/license-and-commercial-use',
        ],
        'method': 'Positive noun hypernym descendants; manually reviewed explicit choices; one spelling per synset per category; game canonical-key deduplication. Curated nature names may display an attested katakana reading without adding another entry for that sense. Low-confidence senses, named-person instance links and rejected subtrees excluded. Nature labels were additionally reviewed to omit taxonomic ranks, general biological concepts and mistranslations. English definition substrings are never classification rules.',
        'curationFile': 'wordnet-curation.json',
        'importScript': 'scripts/import-wordnet.py',
        'counts': {category: len(words) for category, words in output.items()},
        'rootSynsets': ROOTS,
        'excludedSubtrees': EXCLUDED,
        'excludedSubtreesApplyTo': 'Non-nature categories; nature categories use their separate exclusion set so edible fruits and nuts are retained.',
        'natureExcludedSubtrees': ['02472293', '00007846', '01321579', '07992450'],
        'natureReview': {
            'plants': 'All 430 preliminary candidates reviewed; abstract concepts, processed foods, mistranslations and obvious alternate spellings removed; source-attested common readings selected.',
            'animals': 'All 811 preliminary candidates independently reviewed; mistranslations, taxonomic ranks, general concepts and labels differing only by role or coat color removed.',
        },
        'records': records,
    }
    (APP / 'expanded-wordnet.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    (APP / 'expanded-wordnet.sources.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(provenance['counts'], ensure_ascii=False))
    print('Category entries:', sum(map(len, output.values())))
    print('Global canonical words:', len({keys[w] for words in output.values() for w in words}))


if __name__ == '__main__':
    main()
