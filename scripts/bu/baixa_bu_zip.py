# /// script
# requires-python = ">=3.10"
# ///
"""Baixa os zips de Boletim de Urna (BU na Web) de 2026 do Portal de Dados Abertos do TSE.

É a alternativa rápida ao baixa_bu.py: um zip por UF e turno, com um CSV de votos
por seção x cargo x votável. Mesmos números do bu.dat, sem a assinatura de cada urna.

Uso:
    python baixa_bu_zip.py                 # 1º e 2º turno, todas as UFs
    python baixa_bu_zip.py --turno 2       # só 2º turno
    python baixa_bu_zip.py ac rr           # só algumas UFs (zz = exterior)
    python baixa_bu_zip.py --extrair       # também extrai o CSV ao lado do zip
    python baixa_bu_zip.py --listar        # só mostra o que seria baixado

Saída (em ./dados_bu_zip, ou OUT_DIR):
    {1t,2t}/bweb_{t}t_{UF}_{data}.zip     conferido com o .sha512 publicado pelo TSE
    {1t,2t}/bweb_{t}t_{UF}_{data}.csv     se --extrair

Retoma de onde parou: zip já baixado e com hash certo é pulado.
Os links vêm da API do portal (o nome do arquivo tem data e hora, não dá para adivinhar).
Só usa a biblioteca padrão.
"""
import argparse, concurrent.futures as cf, hashlib, json, os, random, re, shutil, sys, threading, time
import urllib.error, urllib.request, zipfile

API = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026-boletim-de-urna"
DIR = os.environ.get("OUT_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_bu_zip")
NOME = re.compile(r"/(bweb_([12])t_([A-Z]{2})_\d{12}\.zip)$", re.I)
UA = {"User-Agent": "apuracao-urnas/1.0"}


TENTATIVAS = int(os.environ.get("TENTATIVAS", "8"))
_pausa_global = [0.0]  # depois de um 429, todas as threads esperam até este instante
_trava = threading.Lock()


def _espera_global():
    while True:
        with _trava:
            falta = _pausa_global[0] - time.time()
        if falta <= 0:
            return
        time.sleep(min(falta, 5))


def get(url, timeout=60):
    """Abre a URL com retentativas. 429/503 respeitam Retry-After e pausam todas as threads."""
    for i in range(TENTATIVAS):
        _espera_global()
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == TENTATIVAS - 1:
                raise
            if e.code in (429, 503):
                ra = e.headers.get("Retry-After", "")
                espera = float(ra) if ra.isdigit() else 30 * 2 ** min(i, 4)
                with _trava:
                    _pausa_global[0] = max(_pausa_global[0], time.time() + espera)
                print(f"    {e.code} do TSE: todas as threads pausam {espera:.0f}s", flush=True)
                continue
            espera = 2 ** i + random.random()
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if i == TENTATIVAS - 1:
                raise
            espera = 2 ** i + random.random()
        print(f"    erro em {url.rsplit('/', 1)[-1]}; nova tentativa em {espera:.0f}s", flush=True)
        time.sleep(espera)


def lista_zips():
    with get(API) as r:
        res = json.load(r)["result"]["resources"]
    zips = {}
    for item in res:
        m = NOME.search(item["url"])
        if m:
            arq, turno, uf = m.group(1), int(m.group(2)), m.group(3).lower()
            # se o TSE republicar, fica a versão mais nova (data/hora no nome)
            chave = (turno, uf)
            if chave not in zips or arq > zips[chave][0]:
                zips[chave] = (arq, item["url"])
    return zips


def sha512(path):
    h = hashlib.sha512()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def hash_publicado(url):
    with get(url + ".sha512") as r:
        return r.read().decode("ascii", "replace").split()[0].lower()


def baixa(url, destino):
    """Baixa para .parte e renomeia; queda no meio da transferência também é retentada."""
    tmp = destino + ".parte"
    for i in range(TENTATIVAS):
        try:
            with get(url, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            os.replace(tmp, destino)
            return
        except urllib.error.HTTPError:
            raise  # get() já esgotou as tentativas
        except Exception as e:
            if i == TENTATIVAS - 1:
                raise
            espera = 2 ** i + random.random()
            print(f"    conexão caiu em {os.path.basename(destino)} ({e}); de novo em {espera:.0f}s", flush=True)
            time.sleep(espera)


def extrai_csv(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        for nome in z.namelist():
            if nome.lower().endswith(".csv"):
                alvo = os.path.join(os.path.dirname(zip_path), os.path.basename(nome))
                if not os.path.exists(alvo):
                    with z.open(nome) as src, open(alvo, "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                return alvo


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ufs", nargs="*", help="UFs (padrão: todas)")
    ap.add_argument("--turno", type=int, choices=[1, 2])
    ap.add_argument("--extrair", action="store_true")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "8")),
                    help="downloads em paralelo (padrão 8)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    zips = lista_zips()
    ufs = {u.lower() for u in a.ufs}
    alvo = sorted(k for k in zips if (not a.turno or k[0] == a.turno) and (not ufs or k[1] in ufs))
    if ufs - {k[1] for k in zips}:
        print("UF sem arquivo no portal:", ", ".join(sorted(ufs - {k[1] for k in zips})))
    print(f"{len(alvo)} arquivo(s) de {len(zips)} publicados", flush=True)

    if a.listar:
        for turno, uf in alvo:
            print(f"[{turno}t {uf.upper()}] {zips[(turno, uf)][0]}")
        return

    def um(chave):
        turno, uf = chave
        arq, url = zips[chave]
        rot = f"[{turno}t {uf.upper()}]"
        pasta = os.path.join(DIR, f"{turno}t")
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(pasta, arq)
        esperado = hash_publicado(url)
        if os.path.exists(destino) and sha512(destino) == esperado:
            msg = "já baixado, hash ok"
        else:
            for tentativa in range(2):  # zip corrompido no caminho: baixa de novo uma vez
                baixa(url, destino)
                if sha512(destino) == esperado:
                    break
                os.remove(destino)
            else:
                raise RuntimeError("hash SHA-512 não confere com o publicado")
            msg = f"ok, {os.path.getsize(destino) / 1e6:.1f} MB, hash ok"
        if a.extrair:
            msg += f", csv {os.path.basename(extrai_csv(destino))}"
        return f"{rot} {msg}"

    inicio, falhas = time.time(), []
    # maiores primeiro (SP, MG, RJ...) para não sobrar um arquivo gigante sozinho no fim
    ordem = "sp mg rj ba rs pr pe ce pa sc go ma am pb es mt rn pi al ms df se ro to ac ap rr zz".split()
    alvo.sort(key=lambda k: (ordem.index(k[1]) if k[1] in ordem else 99, k[0]))
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futuros = {ex.submit(um, k): k for k in alvo}
        for n, f in enumerate(cf.as_completed(futuros), 1):
            turno, uf = futuros[f]
            try:
                print(f"{n}/{len(alvo)} {f.result()}", flush=True)
            except Exception as e:
                print(f"{n}/{len(alvo)} [{turno}t {uf.upper()}] FALHOU: {e}", flush=True)
                falhas.append(f"{turno}t {uf.upper()}")
    print(f"terminou em {time.time() - inicio:.0f}s, pasta {DIR}")

    if falhas:
        print("Falharam:", ", ".join(falhas), "— rode de novo para tentar só esses.")
        sys.exit(1)


if __name__ == "__main__":
    main()
