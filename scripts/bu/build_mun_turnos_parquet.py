# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb>=1.2"]
# ///
"""Gera mun_turnos.csv (entrada do build_transferencia.py) a partir de dados_bu_zip/bu_2026.parquet.

Uma linha por município presente nos dois turnos (inclui o exterior, ZZ), com votos para
presidente por candidato, brancos, nulos, aptos e comparecimento em cada turno.

Uso:
    python build_mun_turnos_parquet.py               # todas as seções (fonte: BU do TSE)
    python build_mun_turnos_parquet.py --sem-junta   # reproduz o CSV antigo, sem as seções
                                                     # apuradas por junta (só para conferência)
"""
import argparse, csv, os

import duckdb

BASE = os.path.dirname(os.path.abspath(__file__))
PARQUET = os.path.join(BASE, "dados_bu_zip", "bu_2026.parquet").replace("\\", "/")
OUT = os.path.join(BASE, "mun_turnos.csv")
CANDIDATES_1T = ["13", "22", "55", "70", "14", "28", "30", "80", "27", "16", "21", "35", "29"]
CANDIDATES_2T = ["13", "22"]
# mesma ordem de UFs do build_turnos.py, exterior no fim
UFS = "ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz".split()


def agrega(con, turno, sem_junta):
    filtro = "AND NR_JUNTA_APURADORA = -1" if sem_junta else ""
    base = f"FROM '{PARQUET}' WHERE NR_TURNO={turno} AND CD_CARGO_PERGUNTA=1 {filtro}"
    muns = {}
    for uf, cd, nome, aptos, comp in con.execute(f"""
            SELECT SG_UF, lpad(CD_MUNICIPIO::varchar, 5, '0'), any_value(NM_MUNICIPIO),
                   sum(QT_APTOS), sum(QT_COMPARECIMENTO)
            FROM (SELECT DISTINCT SG_UF, CD_MUNICIPIO, NM_MUNICIPIO, NR_ZONA, NR_SECAO, QT_APTOS, QT_COMPARECIMENTO {base})
            GROUP BY 1, 2 ORDER BY 1, 2""").fetchall():
        muns[(uf, cd)] = {"nome": nome, "aptos": int(aptos), "comp": int(comp), "brancos": 0, "nulos": 0, "votos": {}}
    for uf, cd, tipo, num, votos in con.execute(f"""
            SELECT SG_UF, lpad(CD_MUNICIPIO::varchar, 5, '0'), CD_TIPO_VOTAVEL, NR_VOTAVEL::varchar, sum(QT_VOTOS)
            {base} GROUP BY ALL""").fetchall():
        m = muns[(uf, cd)]
        if tipo == 1:
            m["votos"][num] = int(votos)
        elif tipo == 2:
            m["brancos"] += int(votos)
        elif tipo == 3:
            m["nulos"] += int(votos)
    return muns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-junta", action="store_true")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    con = duckdb.connect()
    m1, m2 = agrega(con, 1, a.sem_junta), agrega(con, 2, a.sem_junta)

    fields = ["uf", "cd_mun", "nome", "aptos_1t", "comp_1t", "brancos_1t", "nulos_1t"] + \
             [f"v{n}_1t" for n in CANDIDATES_1T] + \
             ["aptos_2t", "comp_2t", "brancos_2t", "nulos_2t"] + \
             [f"v{n}_2t" for n in CANDIDATES_2T]
    rows = []
    for uf, cd in sorted(m1, key=lambda k: (UFS.index(k[0].lower()), k[1])):
        if (uf, cd) not in m2:
            continue
        a1, a2 = m1[(uf, cd)], m2[(uf, cd)]
        row = {"uf": uf, "cd_mun": cd, "nome": a1["nome"],
               "aptos_1t": a1["aptos"], "comp_1t": a1["comp"], "brancos_1t": a1["brancos"], "nulos_1t": a1["nulos"],
               "aptos_2t": a2["aptos"], "comp_2t": a2["comp"], "brancos_2t": a2["brancos"], "nulos_2t": a2["nulos"]}
        for n in CANDIDATES_1T:
            row[f"v{n}_1t"] = a1["votos"].get(n, 0)
        for n in CANDIDATES_2T:
            row[f"v{n}_2t"] = a2["votos"].get(n, 0)
        rows.append(row)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)
    fora = len(set(m1) ^ set(m2))
    print(f"{a.out}: {len(rows)} municípios nos dois turnos ({fora} só num turno, fora do arquivo)")


if __name__ == "__main__":
    main()
