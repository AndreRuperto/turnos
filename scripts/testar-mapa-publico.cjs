/**
 * Verificação pública do mapa usando um contexto Chromium sem cookies nem login.
 * Verifica estado real das fotos e simula indisponibilidade do TSE para
 * comprovar a alternativa visual. Capturas ficam em test-results/.
 *
 * Execute no diretório do projeto após instalar playwright e Chromium:
 *   node scripts/testar-mapa-publico.cjs
 */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const URL_MAPA = process.env.MAPA_URL || 'https://1e2turnos.up.railway.app/mapa.html';
const OUT = path.join(process.cwd(), 'test-results');
fs.mkdirSync(OUT, { recursive: true });

async function estados(page) {
  return page.locator('.nat .cd').evaluateAll((cards) =>
    cards.map((card) => {
      const img = card.querySelector('img.photo');
      const fallback = card.querySelector('span[aria-label^="Foto indisponível"]');
      const nome = card.querySelector('.n')?.textContent?.trim() || img?.alt || '';
      return {
        nome,
        status: fallback ? 'fallback' : img?.complete && img?.naturalWidth > 0 ? 'foto-carregada' : 'imagem-nao-resolvida',
        largura: img?.naturalWidth || 0,
        fallback: fallback?.getAttribute('aria-label') || null,
      };
    })
  );
}

async function esperarFotos(page) {
  await page.waitForFunction(() => {
    const cards = [...document.querySelectorAll('.nat .cd')];
    return cards.length === 2 && cards.every((card) => {
      const img = card.querySelector('img.photo');
      return !!card.querySelector('span[aria-label^="Foto indisponível"]') ||
        !!(img && img.complete && img.naturalWidth > 0);
    });
  }, { timeout: 30000 });
}

async function abrirMapa(browser, { bloquearTse = false } = {}) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, locale: 'pt-BR' });
  const page = await context.newPage();
  const erros = [];
  page.on('pageerror', (error) => erros.push(error.message));
  if (bloquearTse) {
    await page.route(/https:\/\/divulgacandcontas\.tse\.jus\.br\//, (route) =>
      route.abort('blockedbyclient'));
  }
  const response = await page.goto(URL_MAPA, { waitUntil: 'domcontentloaded', timeout: 45000 });
  assert.equal(response?.status(), 200, 'O mapa público deve responder HTTP 200');
  await page.locator('.nat .vs .cd').first().waitFor({ state: 'visible', timeout: 20000 });
  assert.match(await page.title(), /Mapa Eleitoral|Eleiç/i);
  await esperarFotos(page);
  const fotos = await estados(page);
  assert.equal(fotos.length, 2);
  assert(fotos.every((f) => f.status !== 'imagem-nao-resolvida'), 'Não pode haver foto quebrada e sem fallback');
  const file = path.join(OUT, bloquearTse ? 'mapa-tse-bloqueado.png' : 'mapa-publico.png');
  await page.screenshot({ path: file, animations: 'disabled' });
  if (bloquearTse) {
    assert(fotos.every((f) => f.status === 'fallback'), 'O bloqueio do TSE deve renderizar duas alternativas');
  }
  console.log(JSON.stringify({
    modo: bloquearTse ? 'sem acesso ao TSE' : 'visitante público',
    url: URL_MAPA,
    fotos,
    errosJavascript: erros,
    captura: file,
  }, null, 2));
  await context.close();
  return fotos;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const real = await abrirMapa(browser);
    const simulado = await abrirMapa(browser, { bloquearTse: true });
    console.log('PASSOU: mapa público acessível e fallback TSE funcional.');
    console.log('Fotos no acesso real:', real.map((f) => `${f.nome}=${f.status}`).join(', '));
    console.log('Fallback forçado:', simulado.map((f) => `${f.nome}=${f.status}`).join(', '));
  } finally {
    await browser.close();
  }
})().catch((err) => {
  console.error('FALHOU:', err.stack || err.message);
  process.exitCode = 1;
});
