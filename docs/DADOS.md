# Dados de urna das Eleições 2026: de onde vêm e como chegar neles

Este documento explica como sair do zero e chegar aos dados que o site usa, seção por seção, a partir do que o TSE publica. Os scripts citados ficam em `scripts/bu/` no repositório [`turnos`](https://github.com/AndreRuperto/turnos) e na raiz do projeto local `apuracao-urnas`. São os mesmos arquivos.

## O caminho, de ponta a ponta

```
Portal de Dados Abertos do TSE
  dataset "Resultados - 2026 - Boletim de Urna"
  56 zips: bweb_{1t,2t}_{UF}_{ddmmaaaahhmm}.zip  (27 UFs + ZZ = exterior)
        │  baixa_bu_zip.py   (≈3 min, confere SHA-512)
        ▼
dados_bu_zip/1t/*.zip, dados_bu_zip/2t/*.zip      (5,1 GB)
        │  juntar_bu.py      (≈7 min, DuckDB)
        ▼
dados_bu_zip/bu_2026.parquet                       (2,1 GB, 69.947.081 linhas)
        ├─ build_turnos_parquet.py      ──►  data/turnos_data.json
        └─ build_mun_turnos_parquet.py  ──►  mun_turnos.csv
                 │  build_transferencia.py (≈1 min, 1.000 bootstraps)
                 ▼
             data/transferencia.json
```

## 1. A fonte

**Boletim de Urna (BU) na Web**, publicado pelo TSE no Portal de Dados Abertos.

- Página do conjunto: <https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna>
- API (CKAN) que lista os arquivos: `https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026-boletim-de-urna`
- Os arquivos ficam em `https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/`, com nome `bweb_{turno}t_{UF}_{data e hora}.zip`. A data e a hora no nome mudam a cada publicação, então não dá para adivinhar o link. O script lê os links pela API.
- Cada zip vem com um `.sha512` ao lado, que o script usa para conferir o arquivo.
- Dentro de cada zip há um CSV em **latin-1**, separado por **`;`**, e um PDF `_leiame-boletimurnaweb.pdf` com o dicionário das colunas.
- Publicação: o 1º turno saiu em 05/10/2026 e o 2º em 26/10/2026.

Os números são os mesmos dos boletins impressos e do `bu.dat` de cada urna, mas sem a assinatura digital. Para auditar a assinatura urna por urna, existe o `baixa_bu.py`, descrito no fim deste documento.

## 2. Passo a passo

Rode os comandos de dentro de `scripts/bu/` (no repositório `turnos`) ou da raiz do `apuracao-urnas`. Precisa de Python 3.10 ou mais novo e destes pacotes:

```bash
python -m pip install duckdb numpy scipy
```

### 2.1 Baixar os zips

```bash
python baixa_bu_zip.py               # 1º e 2º turno, todas as UFs
python baixa_bu_zip.py --turno 2     # só o 2º turno
python baixa_bu_zip.py ac rr         # só algumas UFs (zz = exterior)
python baixa_bu_zip.py --listar      # só mostra o que seria baixado
```

- Baixa 8 arquivos em paralelo (`--workers N` muda isso).
- Se o TSE devolver **429** ou **503**, todas as threads param juntas e esperam o `Retry-After`. Sem esse cabeçalho, esperam 30 s, 60 s, 120 s e assim por diante. Quedas de conexão são repetidas até 8 vezes (`TENTATIVAS=N` muda isso).
- O arquivo só é aceito se o SHA-512 bater com o publicado. Se não bater, ele é apagado e baixado de novo.
- Se você rodar de novo, ele pula o que já está certo e tenta só o que falhou.
- Pasta de saída: `dados_bu_zip/`, ou `OUT_DIR=...` para mudar.

### 2.2 Juntar tudo num Parquet

```bash
python juntar_bu.py          # retoma de onde parou
python juntar_bu.py --refaz  # refaz do zero
```

Para cada zip, o script extrai o CSV para um arquivo temporário e converte para uma parte em Parquet com as colunas tipadas. Depois confere se o número de linhas é igual ao do CSV e apaga o temporário. No fim, junta as 56 partes em `dados_bu_zip/bu_2026.parquet` e confere de novo o total. A pasta `dados_bu_zip/_partes/` pode ser apagada depois.

### 2.3 Gerar os arquivos do site

```bash
python build_turnos_parquet.py --ordem ../../data/turnos_data.json --out ../../data/turnos_data.json
python build_mun_turnos_parquet.py
python build_transferencia.py   # grava transferencia.json e copia para ../../data/
```

- O `--ordem` mantém a ordem das chaves do JSON que já existe, para o diff no git ficar pequeno.
- O `build_transferencia.py` copia o resultado para `$TURNOS_DATA_DIR`, se essa variável existir, ou para `../../data/`.

## 3. O que tem no Parquet

Uma linha por **seção × cargo × votável** (candidato, legenda, branco ou nulo), nos dois turnos.

| | 1º turno | 2º turno |
|---|---|---|
| Linhas | 67.858.974 | 2.088.107 |
| Seções | 499.206 | 499.207 |
| Cargos | presidente, governador, senador, dep. federal, dep. estadual, dep. distrital, conselheiro distrital | presidente, governador |

As 45 colunas são as do TSE, já com tipo (inteiro, data, hora). As que mais importam:

| Coluna | O que é |
|---|---|
| `NR_TURNO` | 1 ou 2 |
| `CD_ELEICAO` | 6257 = presidente 1º turno; 6258 = presidente 2º turno; 6259 = estadual 1º turno; 6260 = governador 2º turno; 6261 = conselheiro distrital (DF, 1º turno) |
| `SG_UF`, `CD_MUNICIPIO`, `NM_MUNICIPIO` | código do município no TSE, que **não é** o código do IBGE; `ZZ` é o exterior |
| `NR_ZONA`, `NR_SECAO`, `NR_LOCAL_VOTACAO` | identificam a seção |
| `CD_CARGO_PERGUNTA` | 1 presidente, 3 governador, 5 senador, 6 dep. federal, 7 dep. estadual, 8 dep. distrital, 25 conselheiro distrital |
| `CD_TIPO_VOTAVEL` | 1 nominal, 2 branco, 3 nulo, 4 legenda |
| `NR_VOTAVEL`, `NM_VOTAVEL` | número e nome do candidato (95 = branco, 96 = nulo) |
| `QT_VOTOS` | votos desta linha |
| `QT_APTOS`, `QT_COMPARECIMENTO`, `QT_ABSTENCOES` | da seção, **repetidos em todas as linhas dela** |
| `NR_JUNTA_APURADORA` | −1 = apurada na urna; outro valor = apurada por junta (ver armadilhas) |
| `DT_ABERTURA`, `DT_ENCERRAMENTO`, `DT_EMISSAO_BU`, `DT_BU_RECEBIDO` | horários da urna e do envio |
| `NR_URNA_EFETIVADA`, `CD_FLASHCARD_URNA_EFETIVADA`, `DT_CARGA_URNA_EFETIVADA` | identificação da urna usada |
| `DS_SECOES_AGREGADAS` | seções agregadas a esta, quando houver |

Na conversão, `#NULO#`, `#NE#` e campo vazio viram NULL. Os −1 que o TSE usa (por exemplo, o partido de um voto branco) continuam −1.

### Exemplos de consulta (DuckDB)

```python
import duckdb
P = "dados_bu_zip/bu_2026.parquet"

# Presidente, 2º turno, por UF
duckdb.sql(f"""
  SELECT SG_UF, NM_VOTAVEL, sum(QT_VOTOS) votos
  FROM '{P}' WHERE NR_TURNO = 2 AND CD_CARGO_PERGUNTA = 1
  GROUP BY ALL ORDER BY SG_UF, votos DESC
""")

# Aptos e comparecimento: contar UMA vez por seção
duckdb.sql(f"""
  SELECT SG_UF, sum(QT_APTOS) aptos, sum(QT_COMPARECIMENTO) comp
  FROM (SELECT DISTINCT SG_UF, CD_MUNICIPIO, NR_ZONA, NR_SECAO, QT_APTOS, QT_COMPARECIMENTO
        FROM '{P}' WHERE NR_TURNO = 1 AND CD_CARGO_PERGUNTA = 1)
  GROUP BY 1
""")
```

O arquivo também abre no pandas (`pd.read_parquet`) e no Power BI. No Excel não abre: são quase 70 milhões de linhas.

## 4. De onde vem cada arquivo em `data/` do site

| Arquivo | Origem | Script |
|---|---|---|
| `turnos_data.json` | BU do TSE (Parquet) | `build_turnos_parquet.py` |
| `transferencia.json` | BU do TSE → `mun_turnos.csv` | `build_mun_turnos_parquet.py` + `build_transferencia.py` |
| `mun_geo.json`, `mun_gov_geo.json` | 2º turno por município + malha do IBGE | `build_mapa_mun.py` (ainda não migrado para o Parquet) |
| `zz_data.json` | 2º turno no exterior + locais de votação do TSE | `build_zz.py` (lê `dados_limpos/zz.csv`, do crawler antigo) |
| `highlights.json` | destaques por município no 2º turno | ainda não migrado para o Parquet; os valores conferem com o BU |
| `state_borders.json`, `brazil-simple.json`, `ra_geo.json` | geometria (IBGE; regiões administrativas do DF) | `build_borders.py` |
| `politicos.json`, `politicos.js` | candidatos, bens e histórico | API Eleições.dev (`scripts/generate_json.py`) |

O que o `turnos_data.json` contém:
- `pres_1t`, `pres_2t`, `gov_1t`, `gov_2t`: por UF, com aptos, comparecimento, votos por número, brancos e nulos. O exterior fica de fora.
- `depfed_partidos`: votos para deputado federal (nominais e de legenda) por partido, usando os 2 primeiros dígitos do número.
- `migration` e `swings`: comparação entre turnos por município.

O que o `transferencia.json` contém: uma regressão ecológica por município, incluindo as cidades do exterior, que estima para onde foram os votos de cada candidato eliminado.
- **A2:** mínimos quadrados com coeficientes entre 0 e 1 e controles regionais.
- **EI:** média e intervalo de 95% de 1.000 reamostragens com 80% dos municípios.
- `by_region`: o modelo A2 rodado por região.

## 5. Conferências e números de referência

Depois de regerar, estes números têm que bater:

- Presidente por UF (votos em candidatos, brancos e nulos) bate entre o Parquet e o `turnos_data.json` nas 27 UFs, nos dois turnos.
- Presidente, 1º turno, Brasil incluindo o exterior: Flávio Bolsonaro 56.104.503, Lula 53.879.538, Augusto Cury 3.448.569, Renan Santos 2.675.887, Ronaldo Caiado 2.605.148.
- `transferencia.json`: 5.715 municípios, R² do A2 = 0,997462.
- O `build_mun_turnos_parquet.py --sem-junta` reproduz exatamente os totais e o A2 dos arquivos antigos, que vinham do crawler. É a prova de que a única diferença são as seções apuradas por junta.

## 6. Armadilhas

1. **Seções apuradas por junta.** Algumas seções têm o boletim feito pela junta eleitoral, e não pela urna. Nesse caso `NR_JUNTA_APURADORA` é diferente de −1 e não há hora de abertura nem de encerramento. Essas seções não têm `bu.dat`, só `busa.dat`.
   - 1º turno: 30 seções (1.348 comparecimentos), sendo 2 em MG (Belo Horizonte z39 s168 e Piedade dos Gerais z47 s41) e 28 no exterior.
   - 2º turno: 29 seções, todas no exterior (831 comparecimentos).
   - O BU do Portal **inclui** essas seções. O crawler antigo de `bu.dat` deixava todas de fora.
2. **Exterior (ZZ).** O `turnos_data.json` não inclui o exterior, como sempre foi. O `transferencia.json` inclui. 27 cidades do exterior só têm seção apurada por junta num dos turnos, por isso só aparecem com os dados novos.
3. **Aptos e comparecimento se repetem em todas as linhas da seção.** Some uma vez por seção (`SELECT DISTINCT ...`), senão o total fica multiplicado pelo número de candidatos.
4. **Código de município do TSE é diferente do IBGE.** Para juntar com mapas, use a tabela de correspondência (o `build_mapa_mun.py` casa por nome e UF).
5. **Duas linhas sem cargo no 2º turno.** São seções de Trípoli e Ciudad Guayana (ZZ) com comparecimento zero: `CD_CARGO_PERGUNTA = −1` e nenhum voto. Não afetam nenhuma soma.
6. **O EI varia com a semente.** Com 1.000 reamostragens, sementes diferentes ainda variam cerca de 1 ponto nas fontes grandes e de 1 a 2 pontos nos candidatos pequenos. O intervalo de confiança destes vai de 0 a 1: o modelo não consegue dizer para onde esses votos foram. O A2 não tem esse problema.
7. **Arquivos que ainda vêm do crawler antigo.** O `zz_data.json` (mapa do exterior no 2º turno) ainda não tem as 29 seções de junta do exterior. O `mun_geo.json` e o `highlights.json` usam o 2º turno, que não teve seção de junta fora do exterior, então não são afetados.

## 7. Alternativa: o `bu.dat` assinado de cada urna

O `baixa_bu.py`, que está só no projeto local `apuracao-urnas`, baixa e decodifica o `bu.dat` de cada seção em `resultados.tse.jus.br/oficial/ele2026/arquivo-urna/{pleito}`. Os pleitos são 3220 para o 1º turno e 3221 para o 2º.

- Serve para auditar a assinatura digital urna por urna.
- É lento: são cerca de 500 mil seções. Acima de uns 25 requisições por segundo, o TSE bloqueia por IP (429). O download completo leva perto de 2 dias.
- Não pega as seções apuradas por junta, que só têm `busa.dat`. O `refaz_sem_bu.py` tenta de novo essas seções.

Para análise, use o BU do Portal (seções 1 a 3 deste documento).
