# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb>=1.2"]
# ///
"""Gera turnos_data.json (mesmo formato do build_turnos.py) a partir de dados_bu_zip/bu_2026.parquet.

Diferença para o build_turnos.py: a fonte é o BU publicado pelo TSE no Portal de Dados Abertos
(juntar_bu.py), que inclui as seções apuradas por junta (só busa.dat, sem bu.dat), que o
crawler de bu.dat deixava de fora. Exterior (ZZ) continua fora, como antes.

Uso:
    python build_turnos_parquet.py                 # grava turnos_data.json
    python build_turnos_parquet.py --ordem velho.json   # mantém a ordem das chaves do JSON antigo
"""
import argparse, collections, json, os, time

import duckdb

BASE = os.path.dirname(os.path.abspath(__file__))
PARQUET = os.path.join(BASE, "dados_bu_zip", "bu_2026.parquet").replace("\\", "/")
OUT = os.path.join(BASE, "turnos_data.json")
UFS = "ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to".split()
FINALISTAS = {"13", "22"}


def agrega(con, turno, cargo):
    """{uf: {cd_mun: {nome, aptos, comp, votos{num: n}, brancos, nulos}}} para um cargo."""
    base = f"""FROM '{PARQUET}' WHERE NR_TURNO={turno} AND CD_CARGO_PERGUNTA={cargo} AND SG_UF<>'ZZ'"""
    mun = collections.defaultdict(lambda: collections.defaultdict(
        lambda: {"nome": "", "aptos": 0, "comp": 0, "votos": {}, "brancos": 0, "nulos": 0}))
    # aptos/comparecimento: uma vez por seção
    for uf, cd, nome, aptos, comp in con.execute(f"""
            SELECT lower(SG_UF), lpad(CD_MUNICIPIO::varchar, 5, '0'), any_value(NM_MUNICIPIO),
                   sum(QT_APTOS), sum(QT_COMPARECIMENTO)
            FROM (SELECT DISTINCT SG_UF, CD_MUNICIPIO, NM_MUNICIPIO, NR_ZONA, NR_SECAO, QT_APTOS, QT_COMPARECIMENTO {base})
            GROUP BY 1, 2 ORDER BY 1, 2""").fetchall():
        m = mun[uf][cd]
        m["nome"], m["aptos"], m["comp"] = nome, int(aptos), int(comp)
    for uf, cd, tipo, num, votos in con.execute(f"""
            SELECT lower(SG_UF), lpad(CD_MUNICIPIO::varchar, 5, '0'), CD_TIPO_VOTAVEL, NR_VOTAVEL::varchar,
                   sum(QT_VOTOS)
            {base} GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 5 DESC""").fetchall():
        m = mun[uf][cd]
        if tipo == 1:
            m["votos"][num] = m["votos"].get(num, 0) + int(votos)
        elif tipo == 2:
            m["brancos"] += int(votos)
        elif tipo == 3:
            m["nulos"] += int(votos)
    return mun


def soma_uf(muns):
    tot = {"aptos": 0, "comp": 0, "votos": collections.Counter(), "brancos": 0, "nulos": 0}
    for m in muns.values():
        for k in ("aptos", "comp", "brancos", "nulos"):
            tot[k] += m[k]
        tot["votos"].update(m["votos"])
    tot["votos"] = dict(tot["votos"].most_common())
    return tot


def compute_swings(mun_1t, mun_2t, uf, n=10):
    """Igual ao build_turnos.py: municípios com maior mudança de margem 22-13."""
    swings = []
    for cd in mun_1t:
        if cd not in mun_2t:
            continue
        m1, m2 = mun_1t[cd], mun_2t[cd]
        v1, v2 = m1["votos"], m2["votos"]
        t1 = sum(v1.values()) or 1
        t2 = sum(v2.values()) or 1
        margin_1t = (v1.get("22", 0) - v1.get("13", 0)) / t1 * 100
        margin_2t = (v2.get("22", 0) - v2.get("13", 0)) / t2 * 100
        swings.append({"cd": cd, "nome": m1["nome"], "uf": uf,
                       "margin_1t": round(margin_1t, 2), "margin_2t": round(margin_2t, 2),
                       "swing": round(margin_2t - margin_1t, 2), "comp_1t": m1["comp"], "comp_2t": m2["comp"]})
    swings.sort(key=lambda x: x["swing"])
    return swings[:n] + swings[-n:]


def reordena(novo, velho):
    """Mantém a ordem das chaves do JSON antigo (diff menor no git); chaves novas vão no fim."""
    if isinstance(novo, dict) and isinstance(velho, dict):
        chaves = [k for k in velho if k in novo] + [k for k in novo if k not in velho]
        return {k: reordena(novo[k], velho.get(k)) for k in chaves}
    return novo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ordem", help="JSON antigo para copiar a ordem das chaves")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    t0 = time.time()
    con = duckdb.connect()

    pres1, pres2 = agrega(con, 1, 1), agrega(con, 2, 1)
    gov1, gov2 = agrega(con, 1, 3), agrega(con, 2, 3)
    vazio = {"aptos": 0, "comp": 0, "votos": {}, "brancos": 0, "nulos": 0}

    depfed = collections.defaultdict(dict)
    for uf, partido, votos in con.execute(f"""
            SELECT lower(SG_UF), substr(NR_VOTAVEL::varchar, 1, 2), sum(QT_VOTOS)
            FROM '{PARQUET}' WHERE NR_TURNO=1 AND CD_CARGO_PERGUNTA=6 AND SG_UF<>'ZZ'
              AND CD_TIPO_VOTAVEL IN (1, 4)
            GROUP BY 1, 2 ORDER BY 1, 2""").fetchall():
        depfed[uf][partido] = int(votos)

    result = {"pres_1t": {}, "pres_2t": {}, "gov_1t": {}, "gov_2t": {},
              "migration": {"eliminados_1t": 0, "delta_13": 0, "delta_22": 0, "delta_comp": 0, "muns": 0},
              "swings": [], "depfed_partidos": {}}
    for uf in UFS:
        result["pres_1t"][uf] = soma_uf(pres1[uf])
        result["pres_2t"][uf] = soma_uf(pres2[uf])
        result["gov_1t"][uf] = soma_uf(gov1[uf]) if uf in gov1 else dict(vazio)
        result["gov_2t"][uf] = soma_uf(gov2[uf]) if uf in gov2 else dict(vazio)
        result["depfed_partidos"][uf] = depfed[uf]
        mun1, mun2 = pres1[uf], pres2[uf]
        for cd in mun1:
            if cd not in mun2:
                continue
            v1, v2 = mun1[cd]["votos"], mun2[cd]["votos"]
            mig = result["migration"]
            mig["eliminados_1t"] += sum(v for n, v in v1.items() if n not in FINALISTAS)
            mig["delta_13"] += v2.get("13", 0) - v1.get("13", 0)
            mig["delta_22"] += v2.get("22", 0) - v1.get("22", 0)
            mig["delta_comp"] += mun2[cd]["comp"] - mun1[cd]["comp"]
            mig["muns"] += 1
        result["swings"].extend(compute_swings(mun1, mun2, uf))
        print(f"{uf.upper()}: pres 1T {sum(result['pres_1t'][uf]['votos'].values()):,} | "
              f"2T {sum(result['pres_2t'][uf]['votos'].values()):,}", flush=True)

    result["swings"].sort(key=lambda x: x["swing"])
    result["swings"] = result["swings"][:30] + result["swings"][-30:]

    if a.ordem:
        with open(a.ordem, encoding="utf-8") as f:
            result = reordena(result, json.load(f))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"migração: {result['migration']}")
    print(f"pronto: {a.out} ({os.path.getsize(a.out):,} bytes, {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
