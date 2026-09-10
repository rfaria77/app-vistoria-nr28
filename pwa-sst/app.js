// =========================================================
// Credenciais do Supabase (REST API)
// =========================================================
const SUPABASE_URL = "https://tohotxqceeapgkmisfyl.supabase.co/rest/v1/";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRvaG90eHFjZWVhcGdrbWlzZnlsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODkwNjUzMjgsImV4cCI6MjEwNDY0MTMyOH0.HanQzLZYMRq2zlW12hi3TPV7408sDaS2kE4_4OVDed8";

// =========================================================
// 1. Registro do Service Worker (Abertura 100% Offline)
// =========================================================
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js')
      .then(() => console.log('Service Worker registrado com sucesso.'))
      .catch((err) => console.error('Falha ao registrar Service Worker:', err));
  });
}

// Monitoramento de Conexão em Tempo Real
window.addEventListener('online', atualizarStatusRede);
window.addEventListener('offline', atualizarStatusRede);

function atualizarStatusRede() {
  const badge = document.getElementById('netStatus');
  if (navigator.onLine) {
    badge.className = 'badge-status online';
    badge.innerText = 'Online';
  } else {
    badge.className = 'badge-status offline';
    badge.innerText = 'Offline (Campo)';
  }
}
atualizarStatusRede();

// =========================================================
// 2. Tabelas Oficiais NR 28 e Motor de Cálculo
// =========================================================
const TABELA_SEGURANCA = {
  "1 a 10":   { "I1": [630, 1120],   "I2": [1121, 1680],  "I3": [1681, 2240],  "I4": [2241, 2792] },
  "11 a 25":  { "I1": [1121, 1400],  "I2": [1401, 1960],  "I3": [1961, 2520],  "I4": [2521, 3360] },
  "26 a 50":  { "I1": [1401, 1680],  "I2": [1681, 2240],  "I3": [2241, 3080],  "I4": [3081, 3920] },
  "51 a 100": { "I1": [1681, 1960],  "I2": [1961, 2520],  "I3": [2521, 3360],  "I4": [3361, 4480] },
  "101 a 250":{ "I1": [1961, 2240],  "I2": [2241, 3080],  "I3": [3081, 3920],  "I4": [3921, 5040] },
  "251 a 500":{ "I1": [2241, 2520],  "I2": [2521, 3360],  "I3": [3361, 4480],  "I4": [4481, 5600] },
  "501 a 1000":{"I1": [2521, 2800],  "I2": [2801, 3920],  "I3": [3921, 5040],  "I4": [5041, 6304] },
  "Mais de 1000":{"I1": [2801, 3360],"I2": [3921, 4480], "I3": [5041, 5600], "I4": [6305, 6708] }
};

const TABELA_MEDICINA = {
  "1 a 10":   { "I1": [378, 630],    "I2": [631, 1120],   "I3": [1121, 1680],  "I4": [1681, 2240] },
  "11 a 25":  { "I1": [631, 840],    "I2": [841, 1400],   "I3": [1401, 1960],  "I4": [1961, 2520] },
  "26 a 50":  { "I1": [841, 1120],   "I2": [1121, 1680],  "I3": [1681, 2240],  "I4": [2241, 3080] },
  "51 a 100": { "I1": [1121, 1400],  "I2": [1401, 1960],  "I3": [1961, 2520],  "I4": [2521, 3360] },
  "101 a 250":{ "I1": [1401, 1680],  "I2": [1681, 2240],  "I3": [2241, 3080],  "I4": [3081, 3920] },
  "251 a 500":{ "I1": [1681, 1960],  "I2": [1961, 2520],  "I3": [2521, 3360],  "I4": [3361, 4480] },
  "501 a 1000":{"I1": [1961, 2240],  "I2": [2241, 3080],  "I3": [3081, 3920],  "I4": [3921, 5040] },
  "Mais de 1000":{"I1": [2241, 2520],"I2": [3081, 3360], "I3": [3921, 4480], "I4": [5041, 5493] }
};

let baseNR28 = [];
let itemSelecionado = null;
let fotosAtuais = [];
let coordenadasGPS = null;

// Carrega base JSON local
fetch('./itens_nr28.json')
  .then(res => res.json())
  .then(data => {
    baseNR28 = data;
    console.log(`Base NR 28 carregada localmente: ${baseNR28.length} itens.`);
  })
  .catch(err => console.error('Erro ao ler itens_nr28.json:', err));

// Obtém coordenadas de GPS pelo sensor local do aparelho
if ('geolocation' in navigator) {
  navigator.geolocation.getCurrentPosition(
    (pos) => { coordenadasGPS = { lat: pos.coords.latitude, lon: pos.coords.longitude }; },
    (err) => { console.warn('GPS não obtido:', err.message); },
    { enableHighAccuracy: true, timeout: 5000 }
  );
}

function calcularValoresMulta(grau, faixa, tipo) {
  const tabela = tipo === 'M' ? TABELA_MEDICINA : TABELA_SEGURANCA;
  return (tabela[faixa] && tabela[faixa][grau]) ? tabela[faixa][grau] : [0, 0];
}

function formatarBRL(val) {
  return val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

// =========================================================
// 3. Busca Local Instantânea da NR (Sem Internet)
// =========================================================
function buscarNormaLocal() {
  const termo = document.getElementById('buscaTexto').value.toLowerCase().trim();
  if (!termo || baseNR28.length === 0) return;

  const palavras = termo.split(' ').filter(p => p.length > 2);
  let melhorItem = null;
  let maiorPontuacao = 0;

  baseNR28.forEach(it => {
    let score = 0;
    const textoCompleto = `${it.nr} ${it.item} ${it.descricao} ${it.categoria}`.toLowerCase();
    palavras.forEach(p => { if (textoCompleto.includes(p)) score++; });
    if (score > maiorPontuacao) {
      maiorPontuacao = score;
      melhorItem = it;
    }
  });

  if (melhorItem && maiorPontuacao > 0) {
    itemSelecionado = melhorItem;
    const faixa = document.getElementById('faixaFunc').value;
    const [vMin, vMax] = calcularValoresMulta(melhorItem.infracao, faixa, melhorItem.tipo);

    document.getElementById('normaTitulo').innerText = `${melhorItem.nr} (Item ${melhorItem.item}) - ${melhorItem.categoria}`;
    document.getElementById('normaDesc').innerText = melhorItem.descricao;
    document.getElementById('normaMulta').innerText = `Multa NR 28: ${formatarBRL(vMin)} a ${formatarBRL(vMax)} (Grau ${melhorItem.infracao})`;
    document.getElementById('cardNorma').style.display = 'block';

    if (!document.getElementById('descCenario').value) {
      document.getElementById('descCenario').value = `Constatada irregularidade referente a: ${melhorItem.descricao}.`;
    }
    if (!document.getElementById('acaoCorretiva').value) {
      document.getElementById('acaoCorretiva').value = `Adequar as condições de trabalho conforme requisitos da ${melhorItem.nr} (Item ${melhorItem.item}).`;
    }
  } else {
    alert('Nenhum item correspondente encontrado na base local.');
  }
}

// =========================================================
// 4. Carimbo Forense na Câmera via HTML5 Canvas
// =========================================================
function processarFoto(event) {
  const arquivo = event.target.files[0];
  if (!arquivo) return;

  const leitor = new FileReader();
  leitor.onload = function(e) {
    const img = new Image();
    img.onload = function() {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');

      const MAX_LARGURA = 1280;
      let w = img.width;
      let h = img.height;

      if (w > MAX_LARGURA) {
        h = (h * MAX_LARGURA) / w;
        w = MAX_LARGURA;
      }
      canvas.width = w;
      canvas.height = h;

      ctx.drawImage(img, 0, 0, w, h);

      // Tarja preta forense inferior
      const barraAltura = Math.max(34, h * 0.065);
      ctx.fillStyle = '#0F172A';
      ctx.fillRect(0, h - barraAltura, w, barraAltura);

      // Texto com Data, Hora e Coordenadas do GPS local
      const agora = new Date().toLocaleString('pt-BR');
      const gpsTxt = coordenadasGPS ? ` | GPS: ${coordenadasGPS.lat.toFixed(5)}, ${coordenadasGPS.lon.toFixed(5)}` : ' | GPS: Localização Não Obtida';
      const textoForense = `REGISTRO FORENSE SST: ${agora}${gpsTxt}`;

      ctx.fillStyle = '#FFFFFF';
      ctx.font = 'bold 15px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.textBaseline = 'middle';
      ctx.fillText(textoForense, 15, h - barraAltura / 2);

      const fotoFinalBase64 = canvas.toDataURL('image/jpeg', 0.85);
      fotosAtuais.push(fotoFinalBase64);
      renderizarMiniaturas();
    };
    img.src = e.target.result;
  };
  leitor.readAsDataURL(arquivo);
}

function renderizarMiniaturas() {
  const container = document.getElementById('previewFotos');
  container.innerHTML = '';
  fotosAtuais.forEach((foto, idx) => {
    const thumb = document.createElement('img');
    thumb.src = foto;
    thumb.className = 'photo-thumb';
    container.appendChild(thumb);
  });
}

// =========================================================
// 5. Banco IndexedDB (Persistência 100% Offline no Celular)
// =========================================================
let db = null;
const reqDB = indexedDB.open('SST_Campo_DB', 1);

reqDB.onupgradeneeded = function(e) {
  db = e.target.result;
  if (!db.objectStoreNames.contains('apontamentos')) {
    db.createObjectStore('apontamentos', { keyPath: 'id', autoIncrement: true });
  }
};

reqDB.onsuccess = function(e) {
  db = e.target.result;
  carregarApontamentosDoBanco();
};

function salvarApontamento() {
  if (!itemSelecionado) {
    alert('Localize ou selecione uma NR primeiro.');
    return;
  }

  const faixa = document.getElementById('faixaFunc').value;
  const status = document.getElementById('statusItem').value;
  const [vMin, vMax] = calcularValoresMulta(itemSelecionado.infracao, faixa, itemSelecionado.tipo);

  const novoRegistro = {
    empresa: document.getElementById('empresa').value,
    faixa_func: faixa,
    status: status,
    nr: itemSelecionado.nr,
    item_nr: itemSelecionado.item,
    descricao: itemSelecionado.descricao,
    categoria: itemSelecionado.categoria,
    infracao: itemSelecionado.infracao,
    tipo: itemSelecionado.tipo,
    valor_min: vMin,
    valor_max: vMax,
    descricao_cenario: document.getElementById('descCenario').value,
    acao_corretiva: document.getElementById('acaoCorretiva').value,
    imagens: [...fotosAtuais],
    criado_em: new Date().toISOString()
  };

  const tx = db.transaction(['apontamentos'], 'readwrite');
  const store = tx.objectStore('apontamentos');
  store.add(novoRegistro);

  tx.oncomplete = function() {
    alert('Apontamento salvo no celular com sucesso!');
    fotosAtuais = [];
    document.getElementById('previewFotos').innerHTML = '';
    document.getElementById('descCenario').value = '';
    document.getElementById('acaoCorretiva').value = '';
    document.getElementById('cardNorma').style.display = 'none';
    itemSelecionado = null;
    carregarApontamentosDoBanco();
  };
}

function carregarApontamentosDoBanco() {
  const tx = db.transaction(['apontamentos'], 'readonly');
  const store = tx.objectStore('apontamentos');
  const req = store.getAll();

  req.onsuccess = function() {
    const itens = req.result || [];
    renderizarListaApontamentos(itens);
    calcularTotaisKPI(itens);
  };
}

function renderizarListaApontamentos(itens) {
  const container = document.getElementById('listaItens');
  document.getElementById('countItens').innerText = itens.length;
  container.innerHTML = '';

  itens.forEach((it) => {
    const card = document.createElement('div');
    card.className = 'item-card';
    const tagCor = it.status === 'Conformidade' ? '#10B981' : '#EF4444';

    card.innerHTML = `
      <div style="font-weight:700; color:${tagCor};">
        ${it.status === 'Conformidade' ? '✅ Boa Prática' : '⚠️ Não Conformidade'} - ${it.nr} (${it.item_nr})
      </div>
      <div style="font-size:0.85rem; margin-top:2px;"><b>Infração:</b> ${it.descricao}</div>
      <div style="font-size:0.80rem; color:#64748B;">Impacto: ${formatarBRL(it.valor_max)} | Fotos: ${it.imagens.length}</div>
    `;
    container.appendChild(card);
  });
}

function calcularTotaisKPI(itens) {
  let totMulta = 0;
  let totEcon = 0;

  itens.forEach(it => {
    if (it.status === 'Não Conformidade') {
      totMulta += it.valor_max;
    } else {
      totEcon += it.valor_max;
    }
  });

  document.getElementById('totMulta').innerText = formatarBRL(totMulta);
  document.getElementById('totEcon').innerText = formatarBRL(totEcon);
}

// =========================================================
// 6. Sincronização em Lote com Supabase (Ao Recuperar Sinal)
// =========================================================
async function sincronizarComSupabase() {
  if (!navigator.onLine) {
    alert('Aparelho sem conexão com a internet. Conecte-se ao Wi-Fi ou ative os dados móveis para sincronizar.');
    return;
  }

  const tx = db.transaction(['apontamentos'], 'readonly');
  const store = tx.objectStore('apontamentos');
  const req = store.getAll();

  req.onsuccess = async function() {
    const itens = req.result || [];
    if (itens.length === 0) {
      alert('Nenhum apontamento pendente para sincronização.');
      return;
    }

    const btn = document.getElementById('btnSincronizar');
    btn.disabled = true;
    btn.innerText = 'Sincronizando...';

    // O envio dos dados armazenados para as tabelas do Supabase
    // será executado no Passo 4 através das chaves de API.
    alert(`Pronto para enviar ${itens.length} registro(s) para a nuvem!`);
    btn.disabled = false;
    btn.innerText = '🔄 Sincronizar com a Nuvem';
  };

  // =========================================================
// 6. Sincronização em Lote com Supabase (Ao Recuperar Sinal)
// =========================================================
async function sincronizarComSupabase() {
  if (!navigator.onLine) {
    alert('Aparelho sem conexão com a internet. Conecte-se ao Wi-Fi ou dados móveis.');
    return;
  }

  const tx = db.transaction(['apontamentos'], 'readonly');
  const store = tx.objectStore('apontamentos');
  const req = store.getAll();

  req.onsuccess = async function() {
    const itens = req.result || [];
    if (itens.length === 0) {
      alert('Nenhum apontamento pendente para sincronização.');
      return;
    }

    const btn = document.getElementById('btnSincronizar');
    btn.disabled = true;
    btn.innerText = '⏳ Sincronizando...';

    try {
      const empresa = document.getElementById('empresa').value;
      const faixa = document.getElementById('faixaFunc').value;

      // Monta o payload no formato esperado pela tabela rascunhos
      const payload = {
        usuario: 'inspetor_campo',
        empresa: empresa,
        inspetor: 'Equipe Campo (Offline)',
        faixa_func: faixa,
        dados_json: itens,
        atualizado_em: new Date().toISOString()
      };

      const resposta = await fetch(`${SUPABASE_URL}/rest/v1/rascunhos`, {
        method: 'POST',
        headers: {
          'apikey': SUPABASE_ANON_KEY,
          'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
          'Content-Type': 'application/json',
          'Prefer': 'resolution=merge-duplicates'
        },
        body: JSON.stringify(payload)
      });

      if (!resposta.ok) {
        throw new Error(`Falha no envio: ${resposta.statusText}`);
      }

      alert(`✅ Sucesso! ${itens.length} apontamento(s) sincronizados com o Supabase.`);

      // Limpa os apontamentos locais já sincronizados
      const txClear = db.transaction(['apontamentos'], 'readwrite');
      txClear.objectStore('apontamentos').clear();
      txClear.oncomplete = () => {
        carregarApontamentosDoBanco();
      };

    } catch (err) {
      console.error('Erro na sincronização:', err);
      alert(`❌ Erro ao sincronizar: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.innerText = '🔄 Sincronizar com a Nuvem';
    }
  };
}
}