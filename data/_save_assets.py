import json, sys

# Map UUID -> list of asset items {t, d, v}
assets = {
    "a41148b9-d409-461e-b1fd-76eb0cf44931": [{"t":"Casa","d":"CASA, LAGO SUL, BRASÍLIA","v":6226043.8},{"t":"Outras participações societárias","d":"QUOTA E QUINHÃO DE CAPITAL","v":46000},{"t":"Outros fundos","d":"FUNDO DE INVESTIMENTO EM COTAS MULTIMERCADO","v":1090520.47},{"t":"Aplicação de renda fixa","d":"APLICAÇÃO EM CDB - BANCO DO BRASIL","v":8266.1},{"t":"Outras participações societárias","d":"SOCIEDADE INDIVIDUAL DE ADVOCACIA","v":10000},{"t":"Veículo","d":"VEÍCULO 2014","v":133000},{"t":"Outras participações societárias","d":"QUOTA OU QUINHÃO DE CAPITAL","v":249},{"t":"Caderneta de poupança","d":"SALDO CONTA POUPANÇA - BANCO ITAU","v":103746.23},{"t":"Depósito bancário","d":"BANCOS DIVERSOS","v":568730.23}],
    "0ffaf29a-23e7-41d2-8663-5f35080119f8": [{"t":"Terreno","d":"64,08% DE TERRENO - RIACHO GRANDE, SÃO BERNARDO DO CAMPO","v":265000},{"t":"Quotas de capital","d":"98% DA L.I.L.S PALESTRAS, EVENTOS E PUBLICAÇÕES","v":49000},{"t":"Fundo de Curto Prazo","d":"FUNDO DI PLUS AGIL","v":132834.2},{"t":"Outros bens","d":"CRÉDITO DECORRENTE DO DISTRATO - BANCOOP","v":179298.96},{"t":"VGBL","d":"BANCO BRADESCO","v":1380000},{"t":"Poupança","d":"CADERNETA DE POUPANÇA","v":0.13},{"t":"Apartamento","d":"50% DO APARTAMENTO - SÃO BERNARDO DO CAMPO","v":94571.25},{"t":"Terreno","d":"26,68% DE SÍTIO - RIACHO GRANDE","v":130000},{"t":"Aplicação financeira","d":"BANCO DO BRASIL","v":485.39},{"t":"FII","d":"TVRI11","v":50000},{"t":"Poupança","d":"SALDO EM CADERNETA","v":14.99},{"t":"Renda fixa","d":"BRADESCO FUNDO RENDA FIXA SIMPLES","v":6277.62},{"t":"Construção","d":"CASA EM CONSTRUÇÃO - SÃO BERNARDO DO CAMPO","v":246918.82},{"t":"Veículo","d":"CHEVROLET, ANO 2010/2011","v":50000},{"t":"Terreno","d":"RIACHO GRANDE","v":2733.45},{"t":"Depósito bancário","d":"BRADESCO","v":56671.07},{"t":"Renda fixa","d":"BB RF LP HIGH","v":207917.4},{"t":"VGBL","d":"BRASILPREV SEGUROS","v":1923927.36}],
    "9f9b2699-a849-4101-9050-90e3ee2a0ef5": [{"t":"Ações","d":"AÇÕES","v":133.53},{"t":"Sala ou conjunto","d":"SALAS OU CONJUNTOS","v":35711.94},{"t":"Título de capitalização","d":"TÍTULO DE CAPITALIZAÇÃO","v":3385.99},{"t":"Veículo","d":"VEÍCULO AUTOMOTOR TERRESTRE","v":7100},{"t":"Quotas de capital","d":"QUOTAS OU QUINHÕES DE CAPITAL","v":1008634.21},{"t":"Casa","d":"CASA","v":70000},{"t":"Imóveis rurais","d":"IMÓVEIS DO TIPO RURAL","v":36213674.73},{"t":"Depósito bancário","d":"DEPÓSITOS À VISTA / NUMERÁRIO","v":44881.89},{"t":"Outros bens imóveis","d":"OUTROS BENS IMÓVEIS","v":4640.34},{"t":"Terreno","d":"TERRENO","v":243037.95},{"t":"Fundos","d":"FUNDOS DE INVESTIMENTO","v":16.71},{"t":"Participações","d":"OUTRAS PARTICIPAÇÕES SOCIETÁRIAS","v":148613.18},{"t":"Títulos isentos","d":"LIG/LCI/LCA/CRI/CRA","v":4288620.51},{"t":"Semoventes","d":"SEMOVENTES (REBANHO)","v":10489480}],
    "062de96d-b021-4127-b851-0b3871c10a72": [{"t":"Quotas de capital","d":"QUOTAS DE CAPITAL","v":100000},{"t":"Bem de atividade autônoma","d":"BEM RELACIONADO COM ATIVIDADE AUTÔNOMA","v":275329},{"t":"Participações","d":"QUOTAS DE SOCIEDADE","v":119760},{"t":"Outros créditos","d":"OUTROS CRÉDITOS E POUPANÇA VINCULADOS","v":300000}],
    "616aa68d-6999-47d7-90f5-3cc5443cc46b": [{"t":"Fundo de ações","d":"FUNDO DE INVESTIMENTO EM AÇÕES","v":1556006.67},{"t":"Quotas de capital","d":"PARTICIPAÇÃO EM SEGURADORA","v":3666680},{"t":"Renda fixa","d":"APLICAÇÃO DE RENDA FIXA","v":3964283.93},{"t":"CDB","d":"APLICAÇÃO EM CDB","v":337400.33},{"t":"Conta corrente","d":"CONTA CORRENTE EM COOPERATIVA","v":14.86},{"t":"Quotas de capital","d":"PARTICIPAÇÃO EM INST. FINANCEIRA","v":16834806},{"t":"Casa","d":"IMÓVEL RESIDENCIAL REFORMADO","v":704864.25},{"t":"Quotas de capital","d":"PARTICIPAÇÃO EM EMPRESA IMOBILIÁRIA","v":47000},{"t":"Poupança","d":"POUPANÇA BANCÁRIA","v":119.02},{"t":"Conta corrente","d":"CONTA CORRENTE","v":9848.34},{"t":"Fundo multimercado","d":"FUNDO MULTIMERCADO","v":56218194.15},{"t":"Fundo renda fixa","d":"FUNDO RENDA FIXA","v":362.56},{"t":"Quotas de capital","d":"QUOTAS OU QUINHÕES","v":3959.16},{"t":"Quotas cooperativa","d":"QUOTAS EM COOPERATIVA DE CRÉDITO","v":393000},{"t":"Terreno","d":"TERRENO RECEBIDO EM DOAÇÃO","v":70000},{"t":"Holding familiar","d":"PARTICIPAÇÃO EM HOLDING FAMILIAR","v":94498898},{"t":"Renda fixa","d":"FUNDO RENDA FIXA","v":4306.56},{"t":"Fundo de cotas","d":"FUNDO DE INVESTIMENTO EM COTAS","v":397866.26}],
    "71a04f7e-6430-4b1f-b2a2-e0756e9d1ffa": [{"t":"Veículo","d":"UNO VIVACE 2016","v":29000},{"t":"Poupança","d":"POUPANÇA","v":4000}],
    "b6383eaf-1384-4ef5-96bd-f9e2abb6d2f1": [{"t":"Renda fixa","d":"VALOR APLICADO","v":232.61},{"t":"Poupança","d":"VALOR APLICADO","v":51403.07},{"t":"Apartamento","d":"50% DO APARTAMENTO","v":350000},{"t":"VGBL","d":"VALOR","v":52850}],
    "e939da2f-e34b-4649-b848-8b64d95de99d": [{"t":"Apartamento","d":"45m², 2 dormitórios","v":170000}],
    "5a294685-041d-4b4c-9720-f4d1c8f7614b": []
}

# Read politicos.js and update 2026 candidatura bensItens
with open("politicos.js", "r", encoding="utf-8") as f:
    content = f.read()
data = json.loads(content.replace("var POLITICOS=", "", 1).rstrip().rstrip(";"))

updated = 0
for k, v in data.items():
    uuid = v.get("uuid", "")
    if uuid in assets:
        for c in v.get("candidaturas", []):
            if c.get("ano") == 2026:
                c["bensItens"] = assets[uuid]
                updated += 1
                break

with open("politicos.js", "w", encoding="utf-8") as f:
    f.write("var POLITICOS=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";")

print(f"Updated {updated} candidates with bensItens")
