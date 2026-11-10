import json, sys

assets_file = sys.argv[1] if len(sys.argv) > 1 else '_assets_new.json'
with open(assets_file, 'r', encoding='utf-8') as f:
    assets = json.load(f)

with open('politicos.js', 'r', encoding='utf-8') as f:
    content = f.read()
data = json.loads(content.replace('var POLITICOS=', '', 1).rstrip().rstrip(';'))

updated = 0
for k, v in data.items():
    uuid = v.get('uuid', '')
    if uuid in assets:
        for c in v.get('candidaturas', []):
            if c.get('ano') == 2026:
                c['bensItens'] = assets[uuid]
                updated += 1
                break

with open('politicos.js', 'w', encoding='utf-8') as f:
    f.write('var POLITICOS=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')

print(f'Updated {updated} candidates with bensItens')
