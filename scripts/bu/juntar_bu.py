# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb>=1.2"]
# ///
"""Junta os 56 zips de BU (baixa_bu_zip.py) num único Parquet: dados_bu_zip/bu_2026.parquet.

Uso:
    python juntar_bu.py            # processa o que falta e gera o arquivo final
    python juntar_bu.py --refaz    # refaz todas as partes do zero

Para cada zip: extrai o CSV para um temporário, converte para uma parte Parquet com
colunas tipadas, confere que nenhuma linha se perdeu e apaga o temporário. No fim, junta
as partes num arquivo só (ZSTD). Retoma de onde parou: parte pronta é pulada.

Tipos: números viram inteiros, datas/horas viram DATE/TIME/TIMESTAMP, "#NULO#", "#NE#" e campos vazios
viram NULL. Os -1 do TSE (ex.: NR_PARTIDO de branco/nulo) ficam como -1.
"""
import argparse, glob, os, shutil, sys, time, zipfile

import duckdb

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_bu_zip")
PARTES = os.path.join(RAIZ, "_partes")
FINAL = os.path.join(RAIZ, "bu_2026.parquet")

INT = "INTEGER"
BIG = "BIGINT"
TS = "TIMESTAMP"
TIPOS = {
    "DT_GERACAO": "DATE", "HH_GERACAO": "TIME", "ANO_ELEICAO": INT, "CD_TIPO_ELEICAO": INT,
    "NM_TIPO_ELEICAO": "VARCHAR", "CD_PLEITO": INT, "DT_PLEITO": TS, "NR_TURNO": INT,
    "CD_ELEICAO": INT, "DS_ELEICAO": "VARCHAR", "SG_UF": "VARCHAR", "CD_MUNICIPIO": INT,
    "NM_MUNICIPIO": "VARCHAR", "NR_ZONA": INT, "NR_SECAO": INT, "NR_LOCAL_VOTACAO": INT,
    "CD_CARGO_PERGUNTA": INT, "DS_CARGO_PERGUNTA": "VARCHAR", "NR_PARTIDO": INT,
    "SG_PARTIDO": "VARCHAR", "NM_PARTIDO": "VARCHAR", "DT_BU_RECEBIDO": TS, "QT_APTOS": INT,
    "QT_COMPARECIMENTO": INT, "QT_ABSTENCOES": INT, "CD_TIPO_URNA": INT, "DS_TIPO_URNA": "VARCHAR",
    "CD_TIPO_VOTAVEL": INT, "DS_TIPO_VOTAVEL": "VARCHAR", "NR_VOTAVEL": BIG, "NM_VOTAVEL": "VARCHAR",
    "QT_VOTOS": INT, "NR_URNA_EFETIVADA": BIG, "CD_CARGA_1_URNA_EFETIVADA": "VARCHAR",
    "CD_CARGA_2_URNA_EFETIVADA": "VARCHAR", "CD_FLASHCARD_URNA_EFETIVADA": "VARCHAR",
    "DT_CARGA_URNA_EFETIVADA": TS, "DS_CARGO_PERGUNTA_SECAO": "VARCHAR",
    "DS_SECOES_AGREGADAS": "VARCHAR", "DT_ABERTURA": TS, "DT_ENCERRAMENTO": TS,
    "QT_ELEI_BIOM_SEM_HABILITACAO": INT, "DT_EMISSAO_BU": TS, "NR_JUNTA_APURADORA": INT,
    "NR_TURMA_APURADORA": INT,
}


def tipos_sql():
    return "{" + ", ".join(f"'{k}': '{v}'" for k, v in TIPOS.items()) + "}"


def conta_linhas(path):
    n = 0
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 24), b""):
            n += bloco.count(b"\n")
    return n - 1  # cabeçalho


def parte(con, zip_path):
    nome = os.path.basename(zip_path)[:-4]
    saida = os.path.join(PARTES, nome + ".parquet")
    if os.path.exists(saida):
        return saida, None
    tmp_dir = os.path.join(PARTES, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        membro = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        csv = os.path.join(tmp_dir, os.path.basename(membro))
        with z.open(membro) as src, open(csv, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 24)
    esperado = conta_linhas(csv)
    tmp_out = saida + ".parte"
    con.execute(f"""
        COPY (SELECT * FROM read_csv('{csv.replace("'", "''")}',
                delim=';', quote='"', header=true, encoding='latin-1',
                columns={tipos_sql()}, nullstr=['#NULO#', '#NE#', ''],
                dateformat='%d/%m/%Y', timestampformat='%Y-%m-%d %H:%M:%S',
                strict_mode=true))
        TO '{tmp_out}' (FORMAT parquet, COMPRESSION zstd)
    """)
    obtido = con.execute(f"SELECT count(*) FROM read_parquet('{tmp_out}')").fetchone()[0]
    os.remove(csv)
    if obtido != esperado:
        os.remove(tmp_out)
        raise RuntimeError(f"{nome}: CSV tem {esperado:,} linhas, Parquet ficou com {obtido:,}")
    os.replace(tmp_out, saida)
    return saida, obtido


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refaz", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    zips = sorted(glob.glob(os.path.join(RAIZ, "[12]t", "bweb_*.zip")))
    if len(zips) != 56:
        print(f"aviso: esperava 56 zips, achei {len(zips)}")
    if a.refaz and os.path.isdir(PARTES):
        shutil.rmtree(PARTES)
    os.makedirs(PARTES, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"SET temp_directory='{os.path.join(PARTES, '_duck').replace(chr(92), '/')}'")
    inicio = time.time()
    for i, z in enumerate(sorted(zips, key=os.path.getsize), 1):
        t = time.time()
        saida, n = parte(con, z)
        msg = "já pronta" if n is None else f"{n:,} linhas, {time.time() - t:.0f}s"
        print(f"{i}/{len(zips)} {os.path.basename(saida)}: {msg}", flush=True)

    print("juntando as partes...", flush=True)
    padrao = os.path.join(PARTES, "bweb_*.parquet").replace("\\", "/")
    tmp = FINAL + ".parte"
    con.execute(f"""
        COPY (SELECT * FROM read_parquet('{padrao}'))
        TO '{tmp.replace(chr(92), '/')}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)
    """)
    total_partes = con.execute(f"SELECT count(*) FROM read_parquet('{padrao}')").fetchone()[0]
    total = con.execute(f"SELECT count(*) FROM read_parquet('{tmp.replace(chr(92), '/')}')").fetchone()[0]
    if total != total_partes:
        raise RuntimeError(f"arquivo final tem {total:,} linhas, partes somam {total_partes:,}")
    os.replace(tmp, FINAL)
    shutil.rmtree(os.path.join(PARTES, "_tmp"), ignore_errors=True)
    print(f"pronto: {FINAL} — {total:,} linhas, {os.path.getsize(FINAL) / 1e9:.2f} GB, "
          f"{time.time() - inicio:.0f}s")
    print("as partes em _partes/ podem ser apagadas depois de conferir o arquivo final")


if __name__ == "__main__":
    main()
