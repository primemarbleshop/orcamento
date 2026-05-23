// ============================================================
// CONFIGURADOR TÉCNICO 2D - Prime Marble Shop
// ============================================================

const ESP = 2;
const CONTENCAO = 2;

const EDGE_COLORS = { fronte:'#e63946', saia:'#2a9d8f', parede:'#6c757d', livre:'#bbb', ilharga:'#d97706' };
const EDGE_NAMES = { fronte:'Parede com fronte', saia:'Acabamento com saia', parede:'Parede sem fronte', livre:'Acabamento sem saia', ilharga:'Ilharga' };
function edgeName(type, side) {
    if (type === 'fronte') return ['/// Parede', 'com fronte' + (side ? ' larg:'+fmt(CFG.bordaAlts[side]) : '')];
    if (type === 'saia') return ['// Acabamento', 'com saia' + (side ? ' larg:'+fmt(CFG.bordaSaiaLarg[side]) : '')];
    if (type === 'ilharga') return ['Ilharga', side ? 'alt:'+fmt(CFG.bordaAlts[side]) : ''];
    if (type === 'parede') return ['Parede', 'sem fronte'];
    return ['Acabamento', 'sem saia'];
}
function drawEdgeLabel(lines, x, y, isVert) {
    const filtered = lines.filter(l => l);
    if (isVert) {
        ctx.save(); ctx.translate(x, y); ctx.rotate(-Math.PI/2);
        filtered.forEach((l, i) => ctx.fillText(l, 0, i * 12));
        ctx.restore();
    } else {
        filtered.forEach((l, i) => ctx.fillText(l, x, y + i * 12));
    }
}

const MODELOS = [
    {id:'toda_molhada', nome:'Bancada Molhada', desc:'Só área da pia',
     mp:'<div class="mp"><div class="mp-m" style="flex:1">M</div></div>'},
    {id:'toda_seca', nome:'Bancada Seca', desc:'Só área de preparo',
     mp:'<div class="mp"><div class="mp-s" style="flex:1">S</div></div>'},
    {id:'molhada_esq_seca_dir', nome:'Molhada + Seca', desc:'Pia na esquerda, fogão na direita',
     mp:'<div class="mp"><div class="mp-m" style="flex:4">M</div><div class="mp-s" style="flex:6">S</div></div>'},
    {id:'molhada_centro_seca_lat', nome:'Seca + Molhada + Seca', desc:'Pia no centro, fogão nas laterais',
     mp:'<div class="mp"><div class="mp-s" style="flex:3">S</div><div class="mp-m" style="flex:4">M</div><div class="mp-s" style="flex:3">S</div></div>'},
    {id:'seca_centro_molhada_lat', nome:'Molhada + Seca + Molhada', desc:'Fogão no centro, pia nas laterais',
     mp:'<div class="mp"><div class="mp-m" style="flex:3">M</div><div class="mp-s" style="flex:4">S</div><div class="mp-m" style="flex:3">M</div></div>'},
    {id:'l_seca_molhada', nome:'Bancada em L Modelo 1', desc:'L com braço abaixo',
     mp:'<div style="max-width:120px;margin:0 auto 8px"><div class="mp" style="margin:0"><div class="mp-m" style="flex:4">M</div><div class="mp-s" style="flex:6">S</div></div><div class="mp-s" style="width:25%;height:18px;border-radius:0 0 2px 2px;font-size:.5rem;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700">S</div></div>'},
    {id:'l_seca_molhada_seca', nome:'Bancada em L Modelo 2', desc:'L com peça lateral inteira',
     mp:'<div style="max-width:120px;margin:0 auto 8px;display:flex;gap:2px"><div class="mp-s" style="width:22%;height:40px;border-radius:2px;font-size:.5rem;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700">S</div><div style="flex:1;display:flex;flex-direction:column;gap:0"><div style="display:flex;gap:2px;height:18px"><div class="mp-m" style="flex:1;border-radius:2px;font-size:.5rem;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700">M</div><div class="mp-s" style="flex:1;border-radius:2px;font-size:.5rem;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700">S</div></div></div></div>'},
];

/* ---------- ESTADO ---------- */
const CFG = {
    produto: 'bancada',
    modelo: 'molhada_esq_seca_dir',
    compSeca: 120, profSeca: 60, compSecaLat: 60, compSecaEsq: 60, profSecaEsq: 60, compSecaDir: 60, profSecaDir: 60,
    compMolhada: 120, profMolhada: 60, compMolhadaLat: 60, compMolhadaEsq: 60, profMolhadaEsq: 60, compMolhadaDir: 60, profMolhadaDir: 60,
    compL: 120, profL: 60,
    compGen: 120, profGen: 55, lavModelo: 'retangular',
    lavRecorteLarg: 70, lavRecorteAlt: 35,
    nichoLarg: 60, nichoAlt: 30, nichoProf: 12,
    nichoFundo: true, nichoAlisar: false, nichoAlisarMedida: 5,
    soleiraLarg: 80, soleiraProf: 15, soleiraQtd: 1,
    soleiras: [{larg: 80, prof: 15, qtd: 1}],
    bordas: { fundo:'fronte', frente:'saia', esquerda:'livre', direita:'livre', direita2:'livre', l_esquerda:'livre', l_fundo:'livre' },
    bordaAlts: { fundo:10, frente:10, esquerda:10, direita:10, direita2:10, l_esquerda:10, l_fundo:10 },
    bordaSaiaLarg: { fundo:5, frente:5, esquerda:5, direita:5, direita2:5, l_esquerda:5, l_fundo:5 },
    cuba: false, cubaQtd: 1,
    cubaLocal:'molhada', tipoCuba:'embutida', cubaComp: 50, cubaLarg: 40, cubaAlt: 20, furoTorneira: false,
    cuba2Local:'seca', tipoCuba2:'embutida', cubaComp2: 50, cubaLarg2: 40, cubaAlt2: 20, furoTorneira2: false,
    cooktop: false, cooktopLocal: 0,
    espelhar: false,
    clienteNome: '', clienteTelefone: '', clienteEndereco: '',
    materialId: '',
};

let materiaisCache = [];
let step = 0;
let produtosSalvos = [];
let canvas, ctx;
let drawnEdges = [];
let zoomLevel = 1;
let panX = 0, panY = 0;
let isPanning = false, panStartX = 0, panStartY = 0;

function getSteps() {
    if (CFG.produto === 'bancada') return ['cliente','produto','modelo','medidas','bordas','acessorios','material','resumo'];
    if (CFG.produto === 'lavatorio') return ['cliente','produto','modelo_lav','medidas','bordas','acessorios','material','resumo'];
    return ['cliente','produto','medidas','material','resumo'];
}

/* ---------- INIT ---------- */
window.addEventListener('DOMContentLoaded', () => {
    canvas = document.getElementById('c2d');
    ctx = canvas.getContext('2d');
    canvas.addEventListener('click', onCanvasClick);
    canvas.addEventListener('wheel', onWheel, {passive:false});
    canvas.addEventListener('mousedown', onPanStart);
    canvas.addEventListener('mousemove', onPanMove);
    canvas.addEventListener('mouseup', onPanEnd);
    canvas.addEventListener('mouseleave', onPanEnd);
    window.addEventListener('resize', onResize);
    onResize();
    renderStep();
});

function onResize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
}

function onWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    zoomLevel = Math.max(0.3, Math.min(5, zoomLevel + delta));
    draw();
}

function onPanStart(e) {
    if (e.button === 0 && e.ctrlKey) { isPanning = true; panStartX = e.clientX - panX; panStartY = e.clientY - panY; e.preventDefault(); }
}
function onPanMove(e) {
    if (!isPanning) return;
    panX = e.clientX - panStartX; panY = e.clientY - panStartY; draw();
}
function onPanEnd() { isPanning = false; }

/* ---------- SEÇÕES ---------- */
function getSections() {
    const md = CFG.modelo;
    const ws = CFG.compSeca, ds = CFG.profSeca;
    const wm = CFG.compMolhada, dm = CFG.profMolhada;
    const secs = [];

    // Regra de layout das bancadas:
    // quando duas ou mais bancadas ficam lado a lado com larguras diferentes,
    // a frente deve permanecer sempre na mesma linha. A diferença de largura
    // deve aparecer para trás, formando o dente no fundo/parede, nunca na frente.
    const alignFront = (row) => {
        if (!row || row.length <= 1) return row;
        const frontY = Math.max(...row.map(s => s.h));
        row.forEach(s => { s.y = frontY - s.h; });
        return row;
    };

    switch(md) {
        case 'toda_molhada':
            secs.push({type:'molhada', x:0, y:0, w:wm, h:dm}); break;
        case 'toda_seca':
            secs.push({type:'seca', x:0, y:0, w:ws, h:ds}); break;
        case 'molhada_esq_seca_dir': {
            const row = [
                {type:'molhada', x:0, y:0, w:wm, h:dm},
                {type:'seca', x:wm, y:0, w:ws, h:ds}
            ];
            alignFront(row); secs.push(...row); break;
        }
        case 'molhada_dir_seca_esq': {
            const row = [
                {type:'molhada', x:0, y:0, w:wm, h:dm},
                {type:'seca', x:wm, y:0, w:ws, h:ds}
            ];
            alignFront(row); secs.push(...row); break;
        }
        case 'molhada_centro_seca_lat': {
            const sle = CFG.compSecaEsq, dle = CFG.profSecaEsq;
            const sld = CFG.compSecaDir, dld = CFG.profSecaDir;
            const row = [
                {type:'seca', x:0, y:0, w:sle, h:dle, label:'SECA ESQ'},
                {type:'molhada', x:sle, y:0, w:wm, h:dm},
                {type:'seca', x:sle+wm, y:0, w:sld, h:dld, label:'SECA DIR'}
            ];
            alignFront(row); secs.push(...row); break;
        }
        case 'seca_centro_molhada_lat': {
            const mle = CFG.compMolhadaEsq, dme = CFG.profMolhadaEsq;
            const mld = CFG.compMolhadaDir, dmd = CFG.profMolhadaDir;
            const row = [
                {type:'molhada', x:0, y:0, w:mle, h:dme, label:'MOLHADA ESQ'},
                {type:'seca', x:mle, y:0, w:ws, h:ds},
                {type:'molhada', x:mle+ws, y:0, w:mld, h:dmd, label:'MOLHADA DIR'}
            ];
            alignFront(row); secs.push(...row); break;
        }
        case 'l_seca_molhada': {
            const row = [
                {type:'molhada', x:0, y:0, w:wm, h:dm},
                {type:'seca', x:wm, y:0, w:ws, h:ds}
            ];
            alignFront(row);
            const frontY = Math.max(...row.map(s => s.y + s.h));
            secs.push(...row);
            // O braço do L deve encostar na frente alinhada da bancada superior.
            secs.push({type:'seca', x:0, y:frontY, w:CFG.profL, h:CFG.compL, isL:true});
            break;
        }
        case 'l_seca_molhada_seca': {
            const row = [
                {type:'molhada', x:CFG.profL, y:0, w:wm, h:dm},
                {type:'seca', x:CFG.profL+wm, y:0, w:ws, h:ds}
            ];
            alignFront(row);
            const backY = Math.min(...row.map(s => s.y));
            secs.push({type:'seca', x:0, y:backY, w:CFG.profL, h:CFG.compL, isL:true});
            secs.push(...row);
            break;
        }
    }
    return secs;
}

function getBounds(secs) {
    let x0=Infinity, y0=Infinity, x1=-Infinity, y1=-Infinity;
    secs.forEach(s => { x0=Math.min(x0,s.x); y0=Math.min(y0,s.y); x1=Math.max(x1,s.x+s.w); y1=Math.max(y1,s.y+s.h); });
    return {x0,y0,x1,y1, w:x1-x0, h:y1-y0};
}

/* ============================================================
   DESENHO
   ============================================================ */
function draw() {
    const W = canvas.clientWidth, H = canvas.clientHeight;
    ctx.clearRect(0, 0, W*2, H*2);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, W, H);

    ctx.save();
    const cx = W/2, cy = H/2;
    ctx.translate(cx + panX, cy + panY);
    ctx.scale(zoomLevel, zoomLevel);
    ctx.translate(-cx, -cy);

    if (CFG.produto === 'bancada') drawBancada(W, H);
    else if (CFG.produto === 'lavatorio' && CFG.lavModelo === 'violao') drawLavViolao(W, H);
    else if (CFG.produto === 'lavatorio') drawSimples(W, H, 'LAVATÓRIO', CFG.compGen, CFG.profGen, true);
    else if (CFG.produto === 'nicho') drawNicho(W, H);
    else if (CFG.produto === 'soleira') drawSimples(W, H, 'SOLEIRA', CFG.soleiraLarg, CFG.soleiraProf, false);

    ctx.restore();
    updateInfo();
}

function fitToCanvas(shapeW, shapeH, W, H, margin) {
    const sx = (W - margin * 2) / shapeW;
    const sy = (H - margin * 2) / shapeH;
    const scale = Math.min(sx, sy, 5);
    const ox = (W - shapeW * scale) / 2;
    const oy = (H - shapeH * scale) / 2;
    return {scale, ox, oy};
}

function mirrorSections(sections) {
    const b = getBounds(sections);
    return sections.map(s => ({...s, x: b.w - s.x - s.w}));
}

function drawBancada(W, H) {
    let sections = getSections();
    if (CFG.espelhar) sections = mirrorSections(sections);
    const b = getBounds(sections);
    const {scale, ox, oy} = fitToCanvas(b.w, b.h, W, H, 110);
    sections.forEach(sec => drawSection(sec, scale, ox, oy));
    drawAccessories(sections, scale, ox, oy);
    drawBancadaDims(sections, scale, ox, oy, b);
    drawBancadaEdges(sections, scale, ox, oy, b);

}

function drawSection(sec, sc, ox, oy) {
    const rx = ox + sec.x * sc, ry = oy + sec.y * sc;
    const rw = sec.w * sc, rh = sec.h * sc;

    ctx.fillStyle = sec.type === 'molhada' ? '#dbeafe' : '#f3f4f6';
    ctx.fillRect(rx, ry, rw, rh);

    if (sec.type === 'molhada') {
        const c = CONTENCAO * sc;
        ctx.strokeStyle = '#93c5fd'; ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);
        ctx.strokeRect(rx + c, ry + c, rw - c*2, rh - c*2);
        ctx.setLineDash([]);
    }

    ctx.strokeStyle = '#1f2937'; ctx.lineWidth = 2;
    ctx.strokeRect(rx, ry, rw, rh);

    // label no canto superior esquerdo
    const label = sec.label || (sec.type === 'molhada' ? 'MOLHADA' : 'SECA');
    ctx.fillStyle = '#374151'; ctx.font = 'bold 11px Inter,sans-serif';
    ctx.textAlign = 'left'; ctx.textBaseline = 'top';
    ctx.fillText(label, rx + 6, ry + 5);
    ctx.fillStyle = '#6b7280'; ctx.font = '10px Inter,sans-serif';
    ctx.fillText(sec.w + ' × ' + (sec.labelH || sec.h), rx + 6, ry + 20);
    ctx.textBaseline = 'middle';
}

/* ---------- ACESSÓRIOS ---------- */
function drawOneCuba(rx, ry, rw, rh, sc, comp, larg, alt, tipo, furo, label) {
    const sideM = 5*sc, frontM = 5*sc, backM = 10*sc;
    const maxCW = rw - sideM*2, maxCH = rh - frontM - backM;
    if (maxCW <= 0 || maxCH <= 0) return;
    const cw = Math.min(comp * sc, maxCW);
    const ch = Math.min(larg * sc, maxCH);
    const cx = rx + sideM + (maxCW - cw)/2;
    const cy = ry + rh - frontM - ch;
    ctx.strokeStyle = '#6b7280'; ctx.lineWidth = 1.5;
    ctx.strokeRect(cx, cy, cw, ch);
    ctx.fillStyle = '#9ca3af'; ctx.font = '9px Inter,sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    let tCuba = tipo === 'esculpida' ? 'Cuba esc. '+comp+'×'+larg+'×'+alt : 'Cuba '+tipo;
    if (label) tCuba = label + ': ' + tCuba;
    ctx.fillText(tCuba, cx+cw/2, cy+ch/2);
    if (furo) {
        const torY = cy - (cy - ry)/2;
        ctx.beginPath(); ctx.arc(cx+cw/2, torY, 3, 0, Math.PI*2);
        ctx.strokeStyle = '#374151'; ctx.lineWidth = 1.5; ctx.stroke();
        ctx.fillStyle = '#6b7280'; ctx.font = '8px Inter,sans-serif';
        ctx.fillText('Torneira', cx+cw/2, torY + 10);
    }
}

function drawAccessories(sections, sc, ox, oy) {
    if (CFG.cuba) {
        const cubas = [{local: CFG.cubaLocal, comp: CFG.cubaComp, larg: CFG.cubaLarg, alt: CFG.cubaAlt, tipo: CFG.tipoCuba, furo: CFG.furoTorneira}];
        if (CFG.cubaQtd >= 2) cubas.push({local: CFG.cuba2Local, comp: CFG.cubaComp2, larg: CFG.cubaLarg2, alt: CFG.cubaAlt2, tipo: CFG.tipoCuba2, furo: CFG.furoTorneira2});
        const bySection = {};
        cubas.forEach((c, i) => { (bySection[c.local] = bySection[c.local] || []).push({...c, idx: i}); });
        Object.entries(bySection).forEach(([local, list]) => {
            let sec;
            if (local === 'molhada_esq') sec = sections.find(s => s.type === 'molhada' && s.label && s.label.includes('ESQ'));
            else if (local === 'molhada_dir') sec = sections.find(s => s.type === 'molhada' && s.label && s.label.includes('DIR'));
            else if (local === 'seca_esq') sec = sections.find(s => s.type === 'seca' && s.label && s.label.includes('ESQ'));
            else if (local === 'seca_dir') sec = sections.find(s => s.type === 'seca' && s.label && s.label.includes('DIR'));
            else sec = sections.find(s => s.type === local && !s.isL);
            if (!sec) return;
            const rx = ox + sec.x * sc, ry = oy + sec.y * sc;
            const rw = sec.w * sc, rh = sec.h * sc;
            if (list.length === 1) {
                const c = list[0];
                const label = cubas.length > 1 ? ('Cuba '+(c.idx+1)) : '';
                drawOneCuba(rx, ry, rw, rh, sc, c.comp, c.larg, c.alt, c.tipo, c.furo, label);
            } else {
                const halfW = rw / 2;
                list.forEach((c, i) => {
                    const label = 'Cuba '+(c.idx+1);
                    drawOneCuba(rx + i*halfW, ry, halfW, rh, sc, c.comp, c.larg, c.alt, c.tipo, c.furo, label);
                });
            }
        });
    }
    if (CFG.cooktop) {
        const secas = sections.filter(s => s.type === 'seca');
        const idx = Math.min(CFG.cooktopLocal, secas.length - 1);
        const sec = secas[idx];
        if (sec) {
            let rx = ox + sec.x * sc, ry = oy + sec.y * sc;
            let rw = sec.w * sc, rh = sec.h * sc;

            if (sec.isL) {
                const mainH = Math.max(...sections.filter(s=>!s.isL).map(s=>s.h));
                const freeStart = ry + mainH * sc;
                const freeH = rh - mainH * sc;
                ry = freeStart;
                rh = freeH;
            }

            let cw, ch;
            if (sec.isL) {
                cw = Math.min(35*sc, rw*0.45);
                ch = Math.min(60*sc, rh*0.55);
            } else {
                cw = Math.min(60*sc, rw*0.55);
                ch = Math.min(35*sc, rh*0.45);
            }
            const cx = rx + rw/2 - cw/2, cy = ry + rh/2 - ch/2;
            ctx.strokeStyle = '#6b7280'; ctx.lineWidth = 1.5;
            ctx.strokeRect(cx, cy, cw, ch);
            ctx.fillStyle = '#9ca3af'; ctx.font = '9px Inter,sans-serif';
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            if (sec.isL) {
                ctx.save();
                ctx.translate(cx+cw/2, cy+ch/2);
                ctx.rotate(-Math.PI/2);
                ctx.fillText('Cooktop', 0, 0);
                ctx.restore();
            } else {
                ctx.fillText('Cooktop', cx+cw/2, cy+ch/2);
            }
        }
    }
}

/* ---------- COTAS ---------- */
function drawBancadaDims(sections, sc, ox, oy, b) {
    const main = sections.filter(s => !s.isL);
    const lArm = sections.find(s => s.isL);
    const esp = CFG.espelhar;

    const totalW = Math.max(...sections.map(s => s.x + s.w));
    let dy = oy + b.h * sc + 55;

    if (lArm) {
        // Bancadas em L precisam de cotas horizontais por quebras reais de geometria.
        // Antes, a peça principal acima do braço em L era cotada inteira e a largura
        // do braço era cotada por cima dela, gerando 120 + 120 + 60 no Modelo 1.
        // Agora a cota inferior usa os pontos X reais: ex. 0|60|120|240 => 60|60|120.
        const breakpoints = Array.from(new Set(
            sections.flatMap(s => [roundDim(s.x), roundDim(s.x + s.w)])
        )).sort((a, b) => a - b);

        for (let i = 0; i < breakpoints.length - 1; i++) {
            const xA = breakpoints[i];
            const xB = breakpoints[i + 1];
            if (xB - xA > 0.1) {
                drawHDim(ox + xA * sc, ox + xB * sc, dy, fmt(xB - xA));
            }
        }

        dy += 26;
        drawHDim(ox, ox + totalW * sc, dy, fmt(totalW));
    } else {
        main.forEach(sec => {
            const x1 = ox + sec.x * sc, x2 = x1 + sec.w * sc;
            drawHDim(x1, x2, dy, fmt(sec.w));
        });
        if (main.length > 1) {
            dy += 26;
            drawHDim(ox, ox + totalW * sc, dy, fmt(totalW));
        }
    }

    const depths = [...new Set(main.map(s => s.h))];
    let dx = esp ? ox - 55 : ox + b.w * sc + 55;
    depths.forEach(d => {
        const sec = main.find(s => s.h === d);
        drawVDim(dx, oy + sec.y * sc, oy + (sec.y + sec.h) * sc, fmt(d));
        dx += esp ? -40 : 40;
    });
    if (lArm) {
        const totalH = lArm.y + lArm.h;
        const lDimX = esp ? ox + b.w * sc + 55 : ox - 55;
        drawVDim(lDimX, oy, oy + totalH * sc, fmt(totalH));
    }
}

function roundDim(v) { return Math.round(v * 1000) / 1000; }

function fmt(v) { return (v % 1 === 0 ? v : v.toFixed(1)) + 'cm'; }

function drawHDim(x1, x2, y, text) {
    if (Math.abs(x2 - x1) < 10) return;
    const a = 5;
    ctx.strokeStyle = '#666'; ctx.fillStyle = '#666'; ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(x1, y-10); ctx.lineTo(x1, y+4); ctx.moveTo(x2, y-10); ctx.lineTo(x2, y+4); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(x2, y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x1,y); ctx.lineTo(x1+a,y-3); ctx.lineTo(x1+a,y+3); ctx.fill();
    ctx.beginPath(); ctx.moveTo(x2,y); ctx.lineTo(x2-a,y-3); ctx.lineTo(x2-a,y+3); ctx.fill();
    ctx.fillStyle = '#333'; ctx.font = 'bold 11px Inter,sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    ctx.fillText(text, (x1+x2)/2, y - 3);
}

function drawVDim(x, y1, y2, text) {
    if (Math.abs(y2 - y1) < 10) return;
    const a = 5;
    ctx.strokeStyle = '#666'; ctx.fillStyle = '#666'; ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(x-4, y1); ctx.lineTo(x+10, y1); ctx.moveTo(x-4, y2); ctx.lineTo(x+10, y2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x, y1); ctx.lineTo(x, y2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x,y1); ctx.lineTo(x-3,y1+a); ctx.lineTo(x+3,y1+a); ctx.fill();
    ctx.beginPath(); ctx.moveTo(x,y2); ctx.lineTo(x-3,y2-a); ctx.lineTo(x+3,y2-a); ctx.fill();
    ctx.save();
    ctx.translate(x + 10, (y1+y2)/2);
    ctx.rotate(-Math.PI/2);
    ctx.fillStyle = '#333'; ctx.font = 'bold 11px Inter,sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    ctx.fillText(text, 0, 0);
    ctx.restore();
}

/* ---------- CONTORNO EXTERNO + BORDAS ---------- */
function getContourSegments(sections) {
    // Contorno externo genérico por união de retângulos.
    // Necessário porque agora bancadas lado a lado podem ter larguras diferentes
    // alinhadas pela frente, criando dentes no fundo. A lógica antiga assumia
    // todas as peças com y=0 e quebrava quando a frente ficava alinhada.
    const eps = 0.001;
    const xs = Array.from(new Set(sections.flatMap(s => [roundDim(s.x), roundDim(s.x + s.w)]))).sort((a,b) => a-b);
    const ys = Array.from(new Set(sections.flatMap(s => [roundDim(s.y), roundDim(s.y + s.h)]))).sort((a,b) => a-b);
    const segs = [];
    if (xs.length < 2 || ys.length < 2) return segs;

    const contains = (x, y) => sections.some(s =>
        x > s.x + eps && x < s.x + s.w - eps &&
        y > s.y + eps && y < s.y + s.h - eps
    );

    const bounds = getBounds(sections);
    const sideForVertical = (x, outsideRight, y1, y2) => {
        const esp = !!CFG.espelhar;
        const leftKey = esp ? 'direita' : 'esquerda';
        const rightKey = esp ? 'esquerda' : 'direita';
        const lArm = sections.find(s => s.isL);
        if (lArm) {
            const midY = (y1 + y2) / 2;
            const isLLeft = Math.abs(x - lArm.x) < 0.01 && midY >= lArm.y - 0.01;
            const isLRight = Math.abs(x - (lArm.x + lArm.w)) < 0.01 && midY >= lArm.y - 0.01;
            // Em L espelhado, o acabamento lateral do braço também precisa espelhar.
            // A chave l_fundo representa a lateral externa do braço: esquerda no desenho normal,
            // direita quando espelhado. A frente/saia não pode ficar presa no lado externo errado.
            if (!esp) {
                if (isLLeft) return 'l_fundo';
                if (isLRight) return 'frente';
            } else {
                if (isLRight) return 'l_fundo';
                if (isLLeft) return 'frente';
            }
        }
        if (Math.abs(x - bounds.x0) < 0.01) return leftKey;
        if (Math.abs(x - bounds.x1) < 0.01) return rightKey;
        return outsideRight ? rightKey : leftKey;
    };

    const sideForHorizontal = (y, outsideBelow, x1, x2) => {
        const lArm = sections.find(s => s.isL);
        if (lArm) {
            const midX = (x1 + x2) / 2;
            if (Math.abs(y - (lArm.y + lArm.h)) < 0.01 && midX >= lArm.x - 0.01 && midX <= lArm.x + lArm.w + 0.01) return 'l_esquerda';
        }
        return outsideBelow ? 'frente' : 'fundo';
    };

    // Fronteiras verticais: ocupado de um lado e vazio do outro.
    xs.forEach(x => {
        for (let i = 0; i < ys.length - 1; i++) {
            const y1 = ys[i], y2 = ys[i+1];
            if (y2 - y1 < 0.01) continue;
            const midY = (y1 + y2) / 2;
            const leftOcc = contains(x - eps*10, midY);
            const rightOcc = contains(x + eps*10, midY);
            if (leftOcc === rightOcc) continue;
            if (leftOcc && !rightOcc) {
                // vazio à direita: desenha para baixo para o offset/label sair à direita
                segs.push({x1:x, y1:y1, x2:x, y2:y2, side:sideForVertical(x, true, y1, y2)});
            } else {
                // vazio à esquerda: desenha para cima para o offset/label sair à esquerda
                segs.push({x1:x, y1:y2, x2:x, y2:y1, side:sideForVertical(x, false, y1, y2)});
            }
        }
    });

    // Fronteiras horizontais: ocupado em cima/baixo e vazio no outro lado.
    ys.forEach(y => {
        for (let i = 0; i < xs.length - 1; i++) {
            const x1 = xs[i], x2 = xs[i+1];
            if (x2 - x1 < 0.01) continue;
            const midX = (x1 + x2) / 2;
            const aboveOcc = contains(midX, y - eps*10);
            const belowOcc = contains(midX, y + eps*10);
            if (aboveOcc === belowOcc) continue;
            if (!aboveOcc && belowOcc) {
                // vazio em cima: fundo/parede, desenha esquerda→direita
                segs.push({x1:x1, y1:y, x2:x2, y2:y, side:sideForHorizontal(y, false, x1, x2)});
            } else {
                // vazio embaixo: frente, desenha direita→esquerda para offset sair para baixo
                segs.push({x1:x2, y1:y, x2:x1, y2:y, side:sideForHorizontal(y, true, x1, x2)});
            }
        }
    });

    return segs;
}

function segDrawSide(x1, y1, x2, y2) {
    const dx = x2-x1, dy = y2-y1;
    if (Math.abs(dx) >= Math.abs(dy)) return dx > 0 ? 'top' : 'bottom';
    return dy > 0 ? 'right' : 'left';
}

function drawBancadaEdges(sections, sc, ox, oy, b) {
    drawnEdges = [];
    const segs = getContourSegments(sections);

    // desenha marcas sem labels
    segs.forEach(seg => {
        const px1 = ox + seg.x1 * sc, py1 = oy + seg.y1 * sc;
        const px2 = ox + seg.x2 * sc, py2 = oy + seg.y2 * sc;
        const type = CFG.bordas[seg.side];
        const ds = segDrawSide(seg.x1, seg.y1, seg.x2, seg.y2);
        drawEdgeMark(px1, py1, px2, py2, type, ds, false);
        drawnEdges.push({side:seg.side, x1:px1, y1:py1, x2:px2, y2:py2});
    });

    // labels centralizados por lado
    const sides = ['fundo','frente','esquerda','direita','l_esquerda','l_fundo'];
    sides.forEach(side => {
        const sideSegs = segs.filter(s => s.side === side);
        if (!sideSegs.length) return;
        const preferHorizontal = ['fundo','frente','l_esquerda'].includes(side);
        const preferredSegs = sideSegs.filter(seg => {
            const isHoriz = Math.abs(seg.x2 - seg.x1) >= Math.abs(seg.y2 - seg.y1);
            return preferHorizontal ? isHoriz : !isHoriz;
        });
        // Para frente/saia do L, usa preferencialmente um trecho horizontal.
        // Isso evita o texto "Acabamento com saia" ficar girado em 90° quando há uma perna vertical no L.
        const labelSegs = preferredSegs.length ? preferredSegs : sideSegs;
        let totalLen = 0;
        const pixSegs = labelSegs.map(seg => {
            const px1 = ox + seg.x1 * sc, py1 = oy + seg.y1 * sc;
            const px2 = ox + seg.x2 * sc, py2 = oy + seg.y2 * sc;
            const len = Math.sqrt((px2-px1)**2 + (py2-py1)**2);
            return {px1,py1,px2,py2,len,seg};
        });
        pixSegs.forEach(s => totalLen += s.len);
        let target = totalLen / 2, acc = 0;
        let lx, ly;
        for (const s of pixSegs) {
            if (acc + s.len >= target) {
                const t = (target - acc) / s.len;
                lx = s.px1 + (s.px2 - s.px1) * t;
                ly = s.py1 + (s.py2 - s.py1) * t;
                break;
            }
            acc += s.len;
        }
        const longest = labelSegs.reduce((a, b) => {
            const la = Math.abs(b.x2-b.x1) + Math.abs(b.y2-b.y1);
            const lb = Math.abs(a.x2-a.x1) + Math.abs(a.y2-a.y1);
            return la > lb ? b : a;
        });
        const ds = segDrawSide(longest.x1, longest.y1, longest.x2, longest.y2);
        if (lx == null) return;
        const type = CFG.bordas[side];
        const color = EDGE_COLORS[type];
        let nx=0, ny=0;
        if (ds==='top') ny=-1; else if (ds==='bottom') ny=1;
        else if (ds==='left') nx=-1; else nx=1;
        const isVert = preferHorizontal ? false : (ds === 'left' || ds === 'right');
        const ofsX = nx < 0 ? 32 : 18;
        const ofsY = ny < 0 ? 32 : 18;
        const labelX = lx + nx*ofsX;
        const labelY = ly + ny*ofsY;
        ctx.fillStyle = color; ctx.font = 'bold 10px Inter,sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        drawEdgeLabel(edgeName(type, side), labelX, labelY, isVert);
    });
}

function drawEdgeMark(x1, y1, x2, y2, type, side, showLabel, bordaSide) {
    const color = EDGE_COLORS[type];
    let nx=0, ny=0;
    if (side==='top') ny=-1; else if (side==='bottom') ny=1;
    else if (side==='left') nx=-1; else nx=1;

    const off = 5;
    const mx1=x1+nx*off, my1=y1+ny*off, mx2=x2+nx*off, my2=y2+ny*off;

    ctx.strokeStyle = color;
    ctx.lineWidth = type === 'livre' ? 1 : 3.5;
    if (type === 'livre') ctx.setLineDash([6,4]);
    ctx.beginPath(); ctx.moveTo(mx1,my1); ctx.lineTo(mx2,my2); ctx.stroke();
    ctx.setLineDash([]);

    if (type === 'ilharga') {
        const dx=mx2-mx1, dy=my2-my1;
        const len = Math.sqrt(dx*dx+dy*dy);
        if (len < 1) return;
        const ux=dx/len, uy=dy/len;
        const px=-ny, py=nx;
        ctx.strokeStyle = color; ctx.lineWidth = 1.2;
        for (let t=6; t<len; t+=8) {
            const cx2=mx1+ux*t, cy2=my1+uy*t;
            ctx.beginPath();
            ctx.moveTo(cx2-px*4, cy2-py*4);
            ctx.lineTo(cx2+px*4, cy2+py*4);
            ctx.stroke();
        }
    }

    if (type === 'fronte' || type === 'saia') {
        const dx=mx2-mx1, dy=my2-my1;
        const len = Math.sqrt(dx*dx+dy*dy);
        if (len < 1) return;
        const ux=dx/len, uy=dy/len;
        const px=-ny, py=nx;
        const sp = type==='fronte' ? 12 : 14, ml = 7;
        ctx.strokeStyle = color; ctx.lineWidth = 1.2;
        for (let t=sp; t<len; t+=sp) {
            const cx=mx1+ux*t, cy=my1+uy*t;
            if (type === 'fronte') {
                for (let k=-2; k<=2; k+=2) {
                    ctx.beginPath();
                    ctx.moveTo(cx+ux*k-px*ml/2, cy+uy*k-py*ml/2);
                    ctx.lineTo(cx+ux*k+px*ml/2, cy+uy*k+py*ml/2);
                    ctx.stroke();
                }
            } else {
                ctx.beginPath();
                ctx.moveTo(cx-ux*1.5-px*ml/2, cy-uy*1.5-py*ml/2);
                ctx.lineTo(cx-ux*1.5+px*ml/2, cy-uy*1.5+py*ml/2);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx+ux*1.5-px*ml/2, cy+uy*1.5-py*ml/2);
                ctx.lineTo(cx+ux*1.5+px*ml/2, cy+uy*1.5+py*ml/2);
                ctx.stroke();
            }
        }
    }

    if (showLabel !== false) {
        const isVert = (side === 'left' || side === 'right');
        const ofsX = nx < 0 ? 28 : 16;
        const ofsY = ny < 0 ? 28 : 16;
        const lx = (mx1+mx2)/2 + nx*ofsX;
        const ly = (my1+my2)/2 + ny*ofsY;
        ctx.fillStyle = color; ctx.font = 'bold 10px Inter,sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        drawEdgeLabel(edgeName(type, bordaSide), lx, ly, isVert);
    }
}


/* ---------- PRODUTOS SIMPLES ---------- */
function drawSimples(W, H, titulo, larg, prof, showEdges) {
    const {scale:sc, ox, oy} = fitToCanvas(larg, prof, W, H, 110);
    const rw=larg*sc, rh=prof*sc;
    ctx.fillStyle='#f3f4f6'; ctx.fillRect(ox,oy,rw,rh);
    ctx.strokeStyle='#1f2937'; ctx.lineWidth=2; ctx.strokeRect(ox,oy,rw,rh);
    ctx.fillStyle='#374151'; ctx.font='bold 14px Inter,sans-serif';
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText(titulo, ox+rw/2, oy+rh/2 - 8);
    ctx.fillStyle='#6b7280'; ctx.font='11px Inter,sans-serif';
    ctx.fillText(fmt(larg)+' × '+fmt(prof), ox+rw/2, oy+rh/2+10);
    drawHDim(ox, ox+rw, oy+rh+55, fmt(larg));
    if (CFG.espelhar) drawVDim(ox-55, oy, oy+rh, fmt(prof));
    else drawVDim(ox+rw+55, oy, oy+rh, fmt(prof));
    if (showEdges) {
        drawEdgeMark(ox,oy,ox+rw,oy, CFG.bordas.fundo, 'top', true, 'fundo');
        drawEdgeMark(ox,oy+rh,ox+rw,oy+rh, CFG.bordas.frente, 'bottom', true, 'frente');
        drawEdgeMark(ox,oy,ox,oy+rh, CFG.bordas.esquerda, 'left', true, 'esquerda');
        drawEdgeMark(ox+rw,oy,ox+rw,oy+rh, CFG.bordas.direita, 'right', true, 'direita');
    }

}

function drawNicho(W, H) {
    const l=CFG.nichoLarg, a=CFG.nichoAlt, p=CFG.nichoProf;
    const am = CFG.nichoAlisar ? CFG.nichoAlisarMedida : 0;
    const totalW = l + am*2, totalH = a + am*2;
    const {scale:sc, ox:oxBase, oy:oyBase} = fitToCanvas(totalW, totalH, W, H, 90);

    // alisar
    if (CFG.nichoAlisar) {
        const ax = oxBase, ay = oyBase;
        const aw = totalW*sc, ah = totalH*sc;
        ctx.fillStyle='#e5e7eb'; ctx.fillRect(ax,ay,aw,ah);
        ctx.strokeStyle='#9ca3af'; ctx.lineWidth=1.5; ctx.strokeRect(ax,ay,aw,ah);
        ctx.fillStyle='#9ca3af'; ctx.font='9px Inter,sans-serif';
        ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText('Alisar '+fmt(am), ax+aw/2, ay-10);
    }

    const ox = oxBase + am*sc, oy = oyBase + am*sc;
    const rw=l*sc, rh=a*sc;

    // fundo
    if (CFG.nichoFundo) {
        ctx.fillStyle='#f3f4f6'; ctx.fillRect(ox,oy,rw,rh);
    } else {
        ctx.fillStyle='#ffffff'; ctx.fillRect(ox,oy,rw,rh);
        ctx.setLineDash([6,4]);
        ctx.strokeStyle='#d1d5db'; ctx.lineWidth=1;
        ctx.beginPath();
        ctx.moveTo(ox,oy); ctx.lineTo(ox+rw,oy+rh);
        ctx.moveTo(ox+rw,oy); ctx.lineTo(ox,oy+rh);
        ctx.stroke();
        ctx.setLineDash([]);
    }

    ctx.strokeStyle='#1f2937'; ctx.lineWidth=2; ctx.strokeRect(ox,oy,rw,rh);

    ctx.fillStyle='#374151'; ctx.font='bold 14px Inter,sans-serif';
    ctx.textAlign='center'; ctx.textBaseline='middle';
    let labelY = oy + rh/2 - 16;
    ctx.fillText('NICHO', ox+rw/2, labelY);
    ctx.fillStyle='#6b7280'; ctx.font='11px Inter,sans-serif';
    ctx.fillText('Medida interna: '+fmt(l)+' × '+fmt(a), ox+rw/2, labelY+18);
    ctx.fillText('Prof: '+fmt(p), ox+rw/2, labelY+32);
    const extras = [];
    if (CFG.nichoFundo) extras.push('Com fundo');
    else extras.push('Sem fundo');
    if (CFG.nichoAlisar) extras.push('Alisar: '+fmt(am));
    ctx.fillText(extras.join(' | '), ox+rw/2, labelY+46);
    const outerBottom = oyBase + totalH*sc;
    const outerRight = oxBase + totalW*sc;

    drawHDim(ox, ox+rw, outerBottom+20, fmt(l)+' (int)');
    drawVDim(outerRight+20, oy, oy+rh, fmt(a)+' (int)');
    if (CFG.nichoAlisar) {
        drawHDim(oxBase, oxBase+totalW*sc, outerBottom+45, fmt(totalW)+' (total)');
        drawVDim(outerRight+55, oyBase, oyBase+totalH*sc, fmt(totalH)+' (total)');
    }

}

/* ---------- LAVATÓRIO VIOLÃO ---------- */
function drawLavViolao(W, H) {
    const A = CFG.compGen, B = CFG.profGen;
    const C = CFG.lavRecorteLarg, D = CFG.lavRecorteAlt;
    const esp = CFG.espelhar;

    const {scale:sc, ox, oy} = fitToCanvas(A, B, W, H, 110);
    const rA=A*sc, rB=B*sc, rC=C*sc, rD=D*sc;

    // pontos do contorno (sentido horário)
    let pts;
    if (!esp) {
        pts = [
            {x:ox, y:oy},
            {x:ox+rA, y:oy},
            {x:ox+rA, y:oy+rB-rD},
            {x:ox+rA-rC, y:oy+rB-rD},
            {x:ox+rA-rC, y:oy+rB},
            {x:ox, y:oy+rB},
        ];
    } else {
        pts = [
            {x:ox, y:oy},
            {x:ox+rA, y:oy},
            {x:ox+rA, y:oy+rB},
            {x:ox+rC, y:oy+rB},
            {x:ox+rC, y:oy+rB-rD},
            {x:ox, y:oy+rB-rD},
        ];
    }

    // desenhar forma
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i=1; i<pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();
    ctx.fillStyle = '#f3f4f6'; ctx.fill();
    ctx.strokeStyle = '#1f2937'; ctx.lineWidth = 2; ctx.stroke();

    // recorte tracejado
    ctx.setLineDash([6,4]); ctx.strokeStyle = '#d1d5db'; ctx.lineWidth = 1;
    if (!esp) ctx.strokeRect(ox+rA-rC, oy+rB-rD, rC, rD);
    else ctx.strokeRect(ox, oy+rB-rD, rC, rD);
    ctx.setLineDash([]);

    // mapeamento de segmentos para lados (com direita2 independente)
    // Não espelhado: 0=fundo, 1=direita(sup), 2=frente(recorte horiz), 3=direita2(recorte vert), 4=frente, 5=esquerda
    // Espelhado: 0=fundo, 1=direita, 2=frente, 3=direita2(recorte vert), 4=frente(recorte horiz), 5=esquerda(sup)...
    const sideMap = !esp
        ? ['fundo','direita','frente','direita2','frente','esquerda']
        : ['fundo','direita','frente','direita2','frente','esquerda'];

    const edgeSegs = [];
    for (let i=0; i<pts.length; i++) {
        const p1 = pts[i], p2 = pts[(i+1)%pts.length];
        const ds = segDrawSide(p1.x, p1.y, p2.x, p2.y);
        const side = sideMap[i];
        const type = CFG.bordas[side];
        drawEdgeMark(p1.x, p1.y, p2.x, p2.y, type, ds, false);
        edgeSegs.push({side, ds, p1, p2});
    }

    // labels de borda — cada segmento tem seu label (todos independentes)
    edgeSegs.forEach(seg => {
        const mx = (seg.p1.x+seg.p2.x)/2, my = (seg.p1.y+seg.p2.y)/2;
        const type = CFG.bordas[seg.side];
        const color = EDGE_COLORS[type];
        let nx=0, ny=0;
        if (seg.ds==='top') ny=-1; else if (seg.ds==='bottom') ny=1;
        else if (seg.ds==='left') nx=-1; else nx=1;
        const isVert = (seg.ds==='left'||seg.ds==='right');
        ctx.fillStyle = color; ctx.font = 'bold 10px Inter,sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        const soX = nx < 0 ? 32 : 18;
        const soY = ny < 0 ? 32 : 18;
        drawEdgeLabel(edgeName(type, seg.side), mx+nx*soX, my+ny*soY, isVert);
    });

    // cubas na área sem recorte
    if (CFG.cuba) {
        const areaW = (A-C)*sc;
        let areaLeft = !esp ? ox : ox + rA - areaW;
        const qtd = CFG.cubaQtd >= 2 ? 2 : 1;
        const sliceW = areaW / qtd;
        for (let i = 0; i < qtd; i++) {
            const comp = i===0 ? CFG.cubaComp : CFG.cubaComp2;
            const larg = i===0 ? CFG.cubaLarg : CFG.cubaLarg2;
            const alt = i===0 ? CFG.cubaAlt : CFG.cubaAlt2;
            const tipo = i===0 ? CFG.tipoCuba : CFG.tipoCuba2;
            const furo = i===0 ? CFG.furoTorneira : CFG.furoTorneira2;
            const label = qtd > 1 ? 'Cuba '+(i+1) : '';
            drawOneCuba(areaLeft + i*sliceW, oy, sliceW, rB, sc, comp, larg, alt, tipo, furo, label);
        }
    }

    // label
    ctx.fillStyle = '#374151'; ctx.font = 'bold 11px Inter,sans-serif';
    ctx.textAlign = 'left'; ctx.textBaseline = 'top';
    ctx.fillText('LAVATÓRIO VIOLÃO', ox + 6, oy + 5);
    ctx.fillStyle = '#6b7280'; ctx.font = '10px Inter,sans-serif';
    ctx.fillText(A + ' × ' + B, ox + 6, oy + 20);

    // cotas
    drawHDim(ox, ox+rA, oy-40, fmt(A));

    if (!esp) {
        drawVDim(ox-55, oy, oy+rB, fmt(B));
        drawVDim(ox+rA+55, oy, oy+rB-rD, fmt(B-D));
        drawVDim(ox+rA+55, oy+rB-rD, oy+rB, fmt(D));
        drawHDim(ox, ox+rA-rC, oy+rB+55, fmt(A-C));
        drawHDim(ox+rA-rC, ox+rA, oy+rB+55, fmt(C));
    } else {
        drawVDim(ox+rA+55, oy, oy+rB, fmt(B));
        drawVDim(ox-55, oy, oy+rB-rD, fmt(B-D));
        drawVDim(ox-55, oy+rB-rD, oy+rB, fmt(D));
        drawHDim(ox, ox+rC, oy+rB+55, fmt(C));
        drawHDim(ox+rC, ox+rA, oy+rB+55, fmt(A-C));
    }


}

/* ---------- CANVAS CLICK ---------- */
function onCanvasClick(e) {
    const steps = getSteps();
    if (steps[step] !== 'bordas') return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    let closest = null, minD = 25;
    drawnEdges.forEach(edge => {
        const d = ptLineDist(x, y, edge.x1, edge.y1, edge.x2, edge.y2);
        if (d < minD) { minD = d; closest = edge; }
    });
    if (closest) {
        const isLateral = ['esquerda','direita','direita2','l_esquerda','l_fundo'].includes(closest.side);
        const types = isLateral ? ['fronte','saia','parede','livre','ilharga'] : ['fronte','saia','parede','livre'];
        const cur = types.indexOf(CFG.bordas[closest.side]);
        const newType = types[(cur+1) % types.length];
        setBorda(closest.side, newType);
    }
}

function ptLineDist(px,py,x1,y1,x2,y2) {
    const dx=x2-x1, dy=y2-y1;
    const len2 = dx*dx+dy*dy;
    if (len2===0) return Math.sqrt((px-x1)**2+(py-y1)**2);
    let t = ((px-x1)*dx+(py-y1)*dy)/len2;
    t = Math.max(0, Math.min(1, t));
    const cx=x1+t*dx, cy=y1+t*dy;
    return Math.sqrt((px-cx)**2+(py-cy)**2);
}

/* ============================================================
   STEPS UI
   ============================================================ */
function renderStep() {
    const steps = getSteps();
    const sb = document.getElementById('sideBody');
    const name = steps[step];
    const sideHeader = document.querySelector('.side-header');
    if (sideHeader) sideHeader.classList.toggle('mobile-compact', step > 0);
    updateStepBar();
    const btnBack = document.getElementById('btnBack');
    const btnNext = document.getElementById('btnNext');
    btnBack.classList.toggle('hidden', step === 0);
    const isResumo = steps[step] === 'resumo';
    const btnContinuar = document.getElementById('btnContinuar');
    if (isResumo) {
        btnNext.textContent = 'Finalizar';
        btnContinuar.classList.remove('hidden');
    } else {
        btnNext.textContent = 'Continuar';
        btnContinuar.classList.add('hidden');
    }
    switch(name) {
        case 'cliente': renderCliente(sb); break;
        case 'produto': renderProduto(sb); break;
        case 'modelo': renderModelo(sb); break;
        case 'modelo_lav': renderModeloLav(sb); break;
        case 'medidas': renderMedidas(sb); break;
        case 'bordas': renderBordas(sb); break;
        case 'acessorios': renderAcessorios(sb); break;
        case 'material': renderMaterial(sb); break;
        case 'resumo': renderResumo(sb); break;
    }
    draw();
}

function prodIcon(id) {
    const s = 'xmlns="http://www.w3.org/2000/svg" width="40" height="28" viewBox="0 0 40 28"';
    if (id === 'bancada') return `<svg ${s}><rect x="1" y="4" width="24" height="12" rx="1" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.2"/><rect x="25" y="2" width="14" height="14" rx="1" fill="#f3f4f6" stroke="#d1d5db" stroke-width="1.2"/><ellipse cx="13" cy="10" rx="6" ry="4" fill="none" stroke="#6b7280" stroke-width="0.8"/><line x1="1" y1="18" x2="39" y2="18" stroke="#e63946" stroke-width="2"/></svg>`;
    if (id === 'lavatorio') return `<svg ${s}><rect x="4" y="4" width="32" height="16" rx="1" fill="#f3f4f6" stroke="#1f2937" stroke-width="1.2"/><ellipse cx="20" cy="12" rx="8" ry="5" fill="none" stroke="#6b7280" stroke-width="0.8"/><circle cx="20" cy="4" r="1.5" fill="#374151"/><line x1="4" y1="22" x2="36" y2="22" stroke="#2a9d8f" stroke-width="2"/></svg>`;
    if (id === 'nicho') return `<svg ${s}><rect x="6" y="3" width="28" height="22" rx="1" fill="#e5e7eb" stroke="#9ca3af" stroke-width="1.2"/><rect x="10" y="6" width="20" height="16" rx="0" fill="#f9fafb" stroke="#1f2937" stroke-width="1.2"/></svg>`;
    return `<svg ${s}><rect x="3" y="10" width="34" height="8" rx="1" fill="#f3f4f6" stroke="#1f2937" stroke-width="1.2"/></svg>`;
}
function renderProduto(sb) {
    const prods = [
        {id:'bancada', nome:'Bancada', desc:'Pia, fogão e área de preparo'},
        {id:'lavatorio', nome:'Lavatório', desc:'Lavatório com cuba'},
        {id:'nicho', nome:'Nicho', desc:'Para banheiro ou cozinha'},
        {id:'soleira', nome:'Soleira / Peitoril', desc:'Porta ou janela'},
    ];
    sb.innerHTML = `
        <div class="step-title">O que você precisa?</div>
        <div class="step-desc">Escolha o tipo de peça em pedra que deseja configurar.</div>
        <div class="cards">${prods.map(p => `
            <div class="card ${CFG.produto===p.id?'on':''}" onclick="pick('produto','${p.id}')">
                <span class="ico">${prodIcon(p.id)}</span>
                <span class="name">${p.nome}</span>
                <span class="hint">${p.desc}</span>
            </div>`).join('')}
        </div>`;
}

function lavIcon(id) {
    const s = 'xmlns="http://www.w3.org/2000/svg" width="44" height="28" viewBox="0 0 44 28"';
    if (id === 'retangular') return `<svg ${s}><rect x="4" y="6" width="36" height="16" rx="1" fill="#f3f4f6" stroke="#1f2937" stroke-width="1.2"/></svg>`;
    return `<svg ${s}><path d="M4,6 H40 V18 H22 V24 H4 Z" fill="#f3f4f6" stroke="#1f2937" stroke-width="1.2"/><rect x="22" y="18" width="18" height="6" fill="none" stroke="#d1d5db" stroke-width="0.8" stroke-dasharray="3,2"/></svg>`;
}
function renderModeloLav(sb) {
    const modelos = [
        {id:'retangular', nome:'Retangular', desc:'Bancada reta simples'},
        {id:'violao', nome:'Lavatório Violão', desc:'Formato L com recorte frontal e cuba'},
    ];
    sb.innerHTML = `
        <div class="step-title">Modelo do Lavatório</div>
        <div class="step-desc">Escolha o formato da bancada do banheiro.</div>
        ${togHtml('espelhar', 'Espelhar desenho', 'Inverte o lado esquerdo/direito')}
        <div class="cards">${modelos.map(m => `
            <div class="card ${CFG.lavModelo===m.id?'on':''}" onclick="pick('lavModelo','${m.id}')">
                <span class="ico">${lavIcon(m.id)}</span>
                <span class="name">${m.nome}</span>
                <span class="hint">${m.desc}</span>
            </div>`).join('')}
        </div>`;
}

function renderModelo(sb) {
    sb.innerHTML = `
        <div class="step-title">Qual o formato?</div>
        <div class="step-desc">Selecione como será distribuída sua bancada.</div>
        ${togHtml('espelhar', 'Espelhar desenho', 'Inverte o lado esquerdo/direito da bancada')}
        <div class="cards">${MODELOS.map(m => `
            <div class="card ${CFG.modelo===m.id?'on':''}" onclick="pick('modelo','${m.id}')">
                ${m.mp}
                <span class="name">${m.nome}</span>
                <span class="hint">${m.desc}</span>
            </div>`).join('')}
        </div>
`;
}

function renderMedidas(sb) {
    const md = CFG.modelo;
    const hasSeca = md !== 'toda_molhada';
    const hasMolhada = md !== 'toda_seca';
    const isL = md.startsWith('l_');

    let html = '<div class="step-title">Medidas</div><div class="step-desc">Informe as dimensões em centímetros.</div>';

    if (CFG.produto === 'bancada') {
        if (hasSeca && md !== 'molhada_centro_seca_lat') {
            html += '<div style="color:#9ca3af;font-size:.75rem;font-weight:600;margin:10px 0 6px">⬜ Seca</div><div class="row2">';
            html += fgInput('Comprimento', 'compSeca');
            html += fgInput('Largura', 'profSeca');
            html += '</div>';
        }
        if (md === 'molhada_centro_seca_lat') {
            html += '<div style="color:#9ca3af;font-size:.75rem;font-weight:600;margin:10px 0 6px">⬜ Seca (esquerda)</div><div class="row2">';
            html += fgInput('Comprimento', 'compSecaEsq');
            html += fgInput('Largura', 'profSecaEsq');
            html += '</div>';
            html += '<div style="color:#9ca3af;font-size:.75rem;font-weight:600;margin:10px 0 6px">⬜ Seca (direita)</div><div class="row2">';
            html += fgInput('Comprimento', 'compSecaDir');
            html += fgInput('Largura', 'profSecaDir');
            html += '</div>';
        }
        if (hasMolhada && md !== 'seca_centro_molhada_lat') {
            html += '<div style="color:#60a5fa;font-size:.75rem;font-weight:600;margin:10px 0 6px">🟦 Molhada</div><div class="row2">';
            html += fgInput('Comprimento', 'compMolhada');
            html += fgInput('Largura', 'profMolhada');
            html += '</div>';
        }
        if (md === 'seca_centro_molhada_lat') {
            html += '<div style="color:#60a5fa;font-size:.75rem;font-weight:600;margin:10px 0 6px">🟦 Molhada (esquerda)</div><div class="row2">';
            html += fgInput('Comprimento', 'compMolhadaEsq');
            html += fgInput('Largura', 'profMolhadaEsq');
            html += '</div>';
            html += '<div style="color:#60a5fa;font-size:.75rem;font-weight:600;margin:10px 0 6px">🟦 Molhada (direita)</div><div class="row2">';
            html += fgInput('Comprimento', 'compMolhadaDir');
            html += fgInput('Largura', 'profMolhadaDir');
            html += '</div>';
        }
        if (isL) {
            html += '<div style="color:#9ca3af;font-size:.75rem;font-weight:600;margin:10px 0 6px">↳ Bancada L</div><div class="row2">';
            html += fgInput('Comprimento', 'compL');
            html += fgInput('Largura', 'profL');
            html += '</div>';
        }


    } else if (CFG.produto === 'lavatorio') {
        html += '<div class="row2">';
        html += fgInput('Comprimento total', 'compGen');
        html += fgInput('Largura total', 'profGen');
        html += '</div>';
        if (CFG.lavModelo === 'violao') {
            html += '<div style="color:#e63946;font-size:.75rem;font-weight:600;margin:10px 0 6px">Recorte frontal</div><div class="row2">';
            html += fgInput('Largura do recorte', 'lavRecorteLarg');
            html += fgInput('Altura do recorte', 'lavRecorteAlt');
            html += '</div>';
        }
    } else if (CFG.produto === 'nicho') {
        html += '<div style="color:#9ca3af;font-size:.72rem;font-weight:500;margin:0 0 6px">Medidas internas</div>';
        html += '<div class="row2">';
        html += fgInput('Largura interna', 'nichoLarg');
        html += fgInput('Altura interna', 'nichoAlt');
        html += '</div>';
        html += fgInput('Profundidade interna', 'nichoProf');
        html += togHtml('nichoFundo', 'Com fundo', 'Nicho com peça de fundo em pedra');
        html += togHtml('nichoAlisar', 'Com alisar', 'Moldura ao redor do nicho');
        if (CFG.nichoAlisar) {
            html += '<div class="tog-extra" style="display:block">';
            html += fgInput('Medida do alisar', 'nichoAlisarMedida');
            html += '</div>';
        }
    } else if (CFG.produto === 'soleira') {
        if (!CFG.soleiras || CFG.soleiras.length === 0) CFG.soleiras = [{larg: 80, prof: 15, qtd: 1}];
        CFG.soleiras.forEach((s, i) => {
            html += `<div style="color:#9ca3af;font-size:.75rem;font-weight:600;margin:10px 0 6px">Peça ${i+1}${CFG.soleiras.length > 1 ? ' <span onclick="removeSoleira('+i+')" style="color:#ef4444;cursor:pointer;margin-left:8px">✕ Remover</span>' : ''}</div>`;
            html += '<div class="row2">';
            html += `<div class="fgroup"><label>Largura</label><input type="number" value="${s.larg}" onchange="updSoleira(${i},'larg',this.value)"></div>`;
            html += `<div class="fgroup"><label>Profundidade</label><input type="number" value="${s.prof}" onchange="updSoleira(${i},'prof',this.value)"></div>`;
            html += '</div>';
            html += `<div class="fgroup"><label>Quantidade</label><input type="number" value="${s.qtd}" min="1" onchange="updSoleira(${i},'qtd',this.value)"></div>`;
        });
        html += `<div style="margin-top:10px"><button type="button" onclick="addSoleira()" style="background:#fede27;color:#1e1e1e;border:none;border-radius:6px;padding:8px 16px;font-weight:600;cursor:pointer;font-size:.8rem">+ Adicionar medida</button></div>`;
    }
    sb.innerHTML = html;
}

function fgInput(label, key) {
    return `<div class="fgroup"><label>${label}</label>
        <input type="number" step="0.1" min="1" value="${CFG[key]}"
         onchange="updVal('${key}',parseFloat(this.value)||0)"
         onkeyup="if(event.key==='Enter'){updVal('${key}',parseFloat(this.value)||0)}"
         placeholder="cm"></div>`;
}

function renderBordas(sb) {
    const isViolao = CFG.produto === 'lavatorio' && CFG.lavModelo === 'violao';
    const isL = CFG.produto === 'bancada' && CFG.modelo && CFG.modelo.startsWith('l_');
    const esp = CFG.espelhar;
    const lblEsq = esp ? 'Direita' : 'Esquerda';
    const lblDir = esp ? 'Esquerda' : 'Direita';
    const sides = [
        {key:'fundo', label:'Fundo (traseira)', desc:'', lateral:false},
        {key:'frente', label:'Frente', desc:'', lateral:false},
    ];
    if (!isL || CFG.modelo === 'l_seca_molhada') {
        sides.push({key:'esquerda', label:lblEsq, desc:'', lateral:true});
    }
    sides.push({key:'direita', label: isViolao ? lblDir+' (superior)' : lblDir, desc:'', lateral:true});
    if (isViolao) {
        sides.push({key:'direita2', label:lblDir+' (recorte)', desc:'', lateral:true});
    }
    if (isL) {
        sides.push({key:'l_esquerda', label:'L Frente', desc:'', lateral:true});
        sides.push({key:'l_fundo', label: esp ? 'L Direita' : 'L Esquerda', desc:'', lateral:true});
    }
    const baseTypes = ['fronte','saia','parede','livre'];

    let html = '<div class="step-title">Bordas e Acabamentos</div>';
    html += '<div class="step-desc">Defina o acabamento de cada lado. Clique no desenho para alterar rapidamente.</div>';

    sides.forEach(s => {
        const types = (s.lateral && !isViolao) ? ['fronte','saia','parede','livre','ilharga'] : baseTypes;
        const bt = CFG.bordas[s.key];
        html += `<div class="edge-row"><div class="edge-label">${s.label}</div>${s.desc?'<div style="font-size:.65rem;color:#666">'+s.desc+'</div>':''}`;
        html += '<div class="edge-opts">';
        types.forEach(t => {
            html += `<button class="edge-opt t-${t} ${CFG.bordas[s.key]===t?'on':''}" onclick="setBorda('${s.key}','${t}')">${EDGE_NAMES[t]}</button>`;
        });
        html += '</div>';
        if (bt === 'fronte') {
            html += `<div class="edge-extra"><div class="fgroup" style="margin:0"><label>Largura do Fronte</label>
                <input type="number" step="0.1" min="1" value="${CFG.bordaAlts[s.key]}"
                 onchange="CFG.bordaAlts['${s.key}']=parseFloat(this.value)||1;draw();renderStep()"
                 placeholder="cm"></div></div>`;
        } else if (bt === 'saia') {
            html += `<div class="edge-extra"><div class="fgroup" style="margin:0"><label>Largura da Saia</label>
                <input type="number" step="0.1" min="1" value="${CFG.bordaSaiaLarg[s.key]}"
                 onchange="CFG.bordaSaiaLarg['${s.key}']=parseFloat(this.value)||1;draw();renderStep()"
                 placeholder="cm"></div></div>`;
        } else if (bt === 'ilharga') {
            html += `<div class="edge-extra"><div class="fgroup" style="margin:0"><label>Altura da Ilharga</label>
                <input type="number" step="0.1" min="1" value="${CFG.bordaAlts[s.key]}"
                 onchange="CFG.bordaAlts['${s.key}']=parseFloat(this.value)||1;draw();renderStep()"
                 placeholder="cm"></div></div>`;
        }
        html += '</div>';
    });

    sb.innerHTML = html;
}

function cubaFormHtml(num, isBancada, hasSeca, hasMolhada) {
    const sfx = num === 1 ? '' : '2';
    const localKey = num === 1 ? 'cubaLocal' : 'cuba2Local';
    const tipoKey = num === 1 ? 'tipoCuba' : 'tipoCuba2';
    const compKey = num === 1 ? 'cubaComp' : 'cubaComp2';
    const largKey = num === 1 ? 'cubaLarg' : 'cubaLarg2';
    const altKey = num === 1 ? 'cubaAlt' : 'cubaAlt2';
    const furoKey = num === 1 ? 'furoTorneira' : 'furoTorneira2';
    const tipo = CFG[tipoKey];
    let h = '';
    if (CFG.cubaQtd >= 2) h += `<div style="color:#d4a017;font-size:.78rem;font-weight:600;margin:8px 0 4px">Cuba ${num}</div>`;
    if (isBancada && hasSeca && hasMolhada) {
        const md = CFG.modelo;
        h += `<div class="fgroup"><label>Posição</label><select onchange="updVal('${localKey}',this.value)">`;
        if (md === 'seca_centro_molhada_lat') {
            h += `<option value="molhada_esq" ${CFG[localKey]==='molhada_esq'?'selected':''}>Molhada Esquerda</option>`;
            h += `<option value="molhada_dir" ${CFG[localKey]==='molhada_dir'?'selected':''}>Molhada Direita</option>`;
            h += `<option value="seca" ${CFG[localKey]==='seca'?'selected':''}>Na Seca</option>`;
        } else if (md === 'molhada_centro_seca_lat') {
            h += `<option value="molhada" ${CFG[localKey]==='molhada'?'selected':''}>Na Molhada</option>`;
            h += `<option value="seca_esq" ${CFG[localKey]==='seca_esq'?'selected':''}>Seca Esquerda</option>`;
            h += `<option value="seca_dir" ${CFG[localKey]==='seca_dir'?'selected':''}>Seca Direita</option>`;
        } else {
            h += `<option value="molhada" ${CFG[localKey]==='molhada'?'selected':''}>Na Molhada</option>`;
            h += `<option value="seca" ${CFG[localKey]==='seca'?'selected':''}>Na Seca</option>`;
        }
        h += '</select></div>';
    }
    h += `<div class="fgroup"><label>Tipo</label><select onchange="updVal('${tipoKey}',this.value)">`;
    ['embutida','sobreposta','esculpida'].forEach(t => {
        h += `<option value="${t}" ${tipo===t?'selected':''}>${t[0].toUpperCase()+t.slice(1)}</option>`;
    });
    h += '</select></div>';
    if (tipo === 'esculpida') {
        h += '<div class="row2">';
        h += fgInput('Comprimento', compKey);
        h += fgInput('Largura', largKey);
        h += '</div>';
        h += fgInput('Altura', altKey);
    }
    h += togHtml(furoKey, 'Furo de torneira', 'Furo na pedra para a torneira');
    return h;
}

function renderAcessorios(sb) {
    const md = CFG.modelo;
    const hasSeca = md !== 'toda_molhada';
    const hasMolhada = md !== 'toda_seca';
    const isBancada = CFG.produto === 'bancada';

    if (md === 'seca_centro_molhada_lat') {
        ['cubaLocal','cuba2Local'].forEach(k => {
            if (CFG[k] === 'molhada') CFG[k] = 'molhada_esq';
        });
    } else if (md === 'molhada_centro_seca_lat') {
        ['cubaLocal','cuba2Local'].forEach(k => {
            if (CFG[k] === 'seca') CFG[k] = 'seca_esq';
        });
    } else {
        ['cubaLocal','cuba2Local'].forEach(k => {
            if (CFG[k] === 'molhada_esq' || CFG[k] === 'molhada_dir') CFG[k] = 'molhada';
            if (CFG[k] === 'seca_esq' || CFG[k] === 'seca_dir') CFG[k] = 'seca';
        });
    }

    let html = '<div class="step-title">Acessórios</div><div class="step-desc">Adicione recortes e furos na sua peça.</div>';

    html += togHtml('cuba', 'Cuba', 'Recorte para a pia');
    if (CFG.cuba) {
        html += '<div class="tog-extra" style="display:block">';
        html += `<div class="fgroup"><label>Quantidade de cubas</label><select onchange="updVal('cubaQtd',parseInt(this.value))">`;
        html += `<option value="1" ${CFG.cubaQtd===1?'selected':''}>1 Cuba</option>`;
        html += `<option value="2" ${CFG.cubaQtd===2?'selected':''}>2 Cubas</option>`;
        html += '</select></div>';
        html += cubaFormHtml(1, isBancada, hasSeca, hasMolhada);
        if (CFG.cubaQtd >= 2) {
            html += cubaFormHtml(2, isBancada, hasSeca, hasMolhada);
        }
        html += '</div>';
    }

    if (isBancada && hasSeca) {
        html += togHtml('cooktop', 'Cooktop', 'Recorte para o fogão (na seca)');
        if (CFG.cooktop) {
            const secas = getSections().filter(s => s.type === 'seca');
            if (secas.length > 1) {
                html += '<div class="tog-extra" style="display:block"><div class="fgroup"><label>Posição do cooktop</label><select onchange="updVal(\'cooktopLocal\',parseInt(this.value))">';
                secas.forEach((s, i) => {
                    let nome;
                    if (s.isL) nome = 'Seca (L)';
                    else if (s.label) nome = s.label.charAt(0) + s.label.slice(1).toLowerCase();
                    else nome = 'Seca' + (secas.filter(x=>!x.isL).length>1 ? ' ('+(i+1)+')' : '');
                    html += `<option value="${i}" ${CFG.cooktopLocal===i?'selected':''}>${nome}</option>`;
                });
                html += '</select></div></div>';
            }
        }
    }

    sb.innerHTML = html;
}

function renderResumo(sb) {
    let html = '<div class="step-title">Resumo do Projeto</div><div class="step-desc">Confira os detalhes antes de finalizar.</div>';
    html += '<table class="resumo-table">';
    const add = (l,v) => html += `<tr><td>${l}</td><td>${v}</td></tr>`;
    add('Cliente', CFG.clienteNome);
    add('Telefone', CFG.clienteTelefone);
    if (CFG.clienteEndereco) add('Endereço', CFG.clienteEndereco);
    const matSel = materiaisCache.find(m => m.id === CFG.materialId);
    if (matSel) add('Material', matSel.nome);
    const prodNomes = {bancada:'Bancada', lavatorio:'Lavatório', nicho:'Nicho', soleira:'Soleira/Peitoril'};
    add('Produto', prodNomes[CFG.produto]);

    if (CFG.produto === 'bancada') {
        const modNome = MODELOS.find(m => m.id === CFG.modelo);
        add('Modelo', modNome ? modNome.nome : CFG.modelo);
        const md = CFG.modelo;
        if (md === 'molhada_centro_seca_lat') {
            add('Seca Esq', fmt(CFG.compSecaEsq)+' × '+fmt(CFG.profSecaEsq));
            add('Seca Dir', fmt(CFG.compSecaDir)+' × '+fmt(CFG.profSecaDir));
        } else if (md !== 'toda_molhada') {
            add('Seca', fmt(CFG.compSeca)+' × '+fmt(CFG.profSeca));
        }
        if (md === 'seca_centro_molhada_lat') {
            add('Molhada Esq', fmt(CFG.compMolhadaEsq)+' × '+fmt(CFG.profMolhadaEsq));
            add('Molhada Dir', fmt(CFG.compMolhadaDir)+' × '+fmt(CFG.profMolhadaDir));
        } else if (md !== 'toda_seca') {
            add('Molhada', fmt(CFG.compMolhada)+' × '+fmt(CFG.profMolhada));
        }
        if (md.startsWith('l_')) add('Bancada L', fmt(CFG.compL)+' × '+fmt(CFG.profL));
        add('Espessura', fmt(ESP));
        const bSides = md.startsWith('l_') ? ['fundo','frente','direita'] : ['fundo','frente','esquerda','direita'];
        const bLabels = {fundo:'Fundo',frente:'Frente',esquerda:'Esquerda',direita:'Direita'};
        if (md.startsWith('l_')) { bSides.push('l_esquerda','l_fundo'); bLabels['l_esquerda']='L Esquerda'; bLabels['l_fundo']='L Fundo'; }
        bSides.forEach(k => {
            const bt = CFG.bordas[k];
            let val = EDGE_NAMES[bt];
            if (bt==='fronte') val += ' — larg:'+fmt(CFG.bordaAlts[k]);
            else if (bt==='saia') val += ' — larg:'+fmt(CFG.bordaSaiaLarg[k]);
            else if (bt==='ilharga') val += ' — alt:'+fmt(CFG.bordaAlts[k]);
            add(bLabels[k], val);
        });
        if (CFG.cuba) {
            let c1 = CFG.tipoCuba + ' (na ' + CFG.cubaLocal + ')';
            if (CFG.tipoCuba === 'esculpida') c1 += ' '+fmt(CFG.cubaComp)+'×'+fmt(CFG.cubaLarg)+'×'+fmt(CFG.cubaAlt);
            add(CFG.cubaQtd>=2?'Cuba 1':'Cuba', c1);
            if (CFG.furoTorneira) add(CFG.cubaQtd>=2?'Torneira 1':'Torneira', 'Sim');
            if (CFG.cubaQtd >= 2) {
                let c2 = CFG.tipoCuba2 + ' (na ' + CFG.cuba2Local + ')';
                if (CFG.tipoCuba2 === 'esculpida') c2 += ' '+fmt(CFG.cubaComp2)+'×'+fmt(CFG.cubaLarg2)+'×'+fmt(CFG.cubaAlt2);
                add('Cuba 2', c2);
                if (CFG.furoTorneira2) add('Torneira 2', 'Sim');
            }
        }
        if (CFG.cooktop) add('Cooktop', 'Sim');
    } else if (CFG.produto === 'lavatorio') {
        add('Modelo', CFG.lavModelo === 'violao' ? 'Lavatório Violão' : 'Retangular');
        add('Medidas', fmt(CFG.compGen)+' × '+fmt(CFG.profGen));
        if (CFG.lavModelo === 'violao') {
            add('Recorte frontal', fmt(CFG.lavRecorteLarg)+' × '+fmt(CFG.lavRecorteAlt));
        }
        const lavSides = ['fundo','frente','esquerda','direita'];
        const lavLabels = {fundo:'Fundo',frente:'Frente',esquerda:'Esquerda',direita:'Direita'};
        if (CFG.lavModelo === 'violao') { lavSides.push('direita2'); lavLabels['direita2']='Direita (recorte)'; }
        lavSides.forEach(k => {
            const bt = CFG.bordas[k];
            let val = EDGE_NAMES[bt];
            if (bt==='fronte') val += ' — larg:'+fmt(CFG.bordaAlts[k]);
            else if (bt==='saia') val += ' — larg:'+fmt(CFG.bordaSaiaLarg[k]);
            else if (bt==='ilharga') val += ' — alt:'+fmt(CFG.bordaAlts[k]);
            add(lavLabels[k], val);
        });
        if (CFG.cuba) {
            let c1 = CFG.tipoCuba;
            if (CFG.tipoCuba === 'esculpida') c1 += ' '+fmt(CFG.cubaComp)+'×'+fmt(CFG.cubaLarg)+'×'+fmt(CFG.cubaAlt);
            add(CFG.cubaQtd>=2?'Cuba 1':'Cuba', c1);
            if (CFG.furoTorneira) add(CFG.cubaQtd>=2?'Torneira 1':'Torneira', 'Sim');
            if (CFG.cubaQtd >= 2) {
                let c2 = CFG.tipoCuba2;
                if (CFG.tipoCuba2 === 'esculpida') c2 += ' '+fmt(CFG.cubaComp2)+'×'+fmt(CFG.cubaLarg2)+'×'+fmt(CFG.cubaAlt2);
                add('Cuba 2', c2);
                if (CFG.furoTorneira2) add('Torneira 2', 'Sim');
            }
        }
        if (CFG.espelhar) add('Espelhado', 'Sim');
    } else if (CFG.produto === 'nicho') {
        add('Medidas internas', fmt(CFG.nichoLarg)+'×'+fmt(CFG.nichoAlt));
        add('Profundidade', fmt(CFG.nichoProf));
        add('Fundo', CFG.nichoFundo ? 'Sim' : 'Não');
        if (CFG.nichoAlisar) add('Alisar', fmt(CFG.nichoAlisarMedida));
    } else {
        if (CFG.soleiras && CFG.soleiras.length > 0) {
            CFG.soleiras.forEach((s, i) => {
                const prefix = CFG.soleiras.length > 1 ? `Peça ${i+1}: ` : '';
                add(prefix + 'Medidas', fmt(s.larg)+'×'+fmt(s.prof));
                add(prefix + 'Quantidade', s.qtd);
            });
        } else {
            add('Medidas', fmt(CFG.soleiraLarg)+'×'+fmt(CFG.soleiraProf));
            add('Quantidade', CFG.soleiraQtd);
        }
    }

    html += '</table>';
    html += '<div class="info" style="margin-top:16px"><b>Próximo passo:</b> Ao finalizar, um orçamento será gerado com base nessas especificações.</div>';
    sb.innerHTML = html;
}

function renderCliente(sb) {
    sb.innerHTML = `
        <div class="step-title">Seus Dados</div>
        <div class="step-desc">Preencha seus dados para gerar o orçamento.</div>
        <div class="fgroup"><label>Nome completo *</label>
            <input type="text" value="${CFG.clienteNome}" placeholder="Seu nome"
             oninput="CFG.clienteNome=this.value"
             style="width:100%;padding:8px 12px;border:1px solid #2a2a40;border-radius:8px;background:#1a1a2e;color:#e8e8e8;font-size:0.85rem"></div>
        <div class="fgroup"><label>Telefone *</label>
            <input type="tel" value="${CFG.clienteTelefone}" placeholder="(00) 00000-0000"
             oninput="CFG.clienteTelefone=this.value"
             style="width:100%;padding:8px 12px;border:1px solid #2a2a40;border-radius:8px;background:#1a1a2e;color:#e8e8e8;font-size:0.85rem"></div>
        <div class="fgroup"><label>Endereço *</label>
            <input type="text" value="${CFG.clienteEndereco}" placeholder="Rua, número, bairro, cidade"
             oninput="CFG.clienteEndereco=this.value"
             style="width:100%;padding:8px 12px;border:1px solid #2a2a40;border-radius:8px;background:#1a1a2e;color:#e8e8e8;font-size:0.85rem"></div>
        <div class="info"><b>*</b> Campos obrigatórios para gerar seu orçamento.</div>`;
}

function renderMaterial(sb) {
    let html = '<div class="step-title">Material</div><div class="step-desc">Digite o nome da pedra desejada (mínimo 3 letras).</div>';
    if (materiaisCache.length === 0) {
        html += '<div style="color:#999;font-size:.8rem;padding:20px;text-align:center">Carregando materiais...</div>';
        sb.innerHTML = html;
        fetch('/api/materiais').then(r=>r.json()).then(data=>{
            materiaisCache = data;
            renderMaterial(sb);
        }).catch(()=>{ sb.innerHTML += '<div style="color:#d4a017">Erro ao carregar materiais.</div>'; });
        return;
    }
    const matSel = materiaisCache.find(m => m.id === CFG.materialId);
    const matNome = matSel ? matSel.nome : (CFG._materialBusca || '');
    html += `<div class="fgroup"><label>Nome do material <span>*</span></label>
        <input type="text" id="matBusca" value="${matNome}" placeholder="Ex: Branco Siena, Preto São Gabriel..."
         style="width:100%;padding:10px 12px;border:1px solid #2a2a40;border-radius:8px;background:#1a1a2e;color:#e8e8e8;font-size:0.85rem"></div>`;
    html += '<div id="matResultados"></div>';
    if (matSel) {
        html += `<div style="margin-top:10px;padding:10px 14px;background:#22c55e18;border:1px solid #22c55e44;border-radius:8px;font-size:0.82rem;color:#4ade80">
            ✓ Selecionado: <b>${matSel.nome}</b></div>`;
    }
    sb.innerHTML = html;
    const inp = document.getElementById('matBusca');
    inp.addEventListener('input', function() {
        CFG._materialBusca = this.value;
        const q = this.value.trim().toLowerCase();
        const box = document.getElementById('matResultados');
        if (q.length < 3) { box.innerHTML = ''; CFG.materialId = ''; return; }
        const matches = materiaisCache.filter(m => m.nome.toLowerCase().includes(q));
        if (matches.length === 0) {
            box.innerHTML = '<div style="color:#999;font-size:.78rem;padding:8px">Nenhum material encontrado.</div>';
            CFG.materialId = '';
            return;
        }
        box.innerHTML = '<div class="cards cols1">' + matches.map(m =>
            `<div class="card ${CFG.materialId==m.id?'on':''}" onclick="CFG.materialId=${m.id};CFG._materialBusca='${m.nome.replace(/'/g,"\\'")}';renderStep()">
                <span class="name">${m.nome}</span>
            </div>`
        ).join('') + '</div>';
    });
    if (matNome.length >= 3 && !matSel) inp.dispatchEvent(new Event('input'));
}

function finalizarOrcamento() {
    const btnNext = document.getElementById('btnNext');
    btnNext.textContent = 'Enviando...';
    btnNext.disabled = true;
    const desenhoData = canvas.toDataURL('image/png');
    const payload = {...CFG, produtosExtras: produtosSalvos, desenho: desenhoData};
    fetch('/api/configurador-orcamento', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            const sb = document.getElementById('sideBody');
            sb.innerHTML = `
                <div style="text-align:center;padding:30px 10px">
                    <div style="font-size:2rem;margin-bottom:16px">&#10003;</div>
                    <div class="step-title" style="color:#22c55e">Orcamento Enviado!</div>
                    <div class="step-desc" style="margin-top:8px">Codigo: <b style="color:#d4a017">${data.codigo}</b></div>
                    <div class="step-desc">Clique abaixo para enviar o orcamento para a loja!</div>
                    <div style="margin-top:20px">
                        <a class="btn btn-next" href="https://wa.me/5521993811591?text=${encodeURIComponent('Olá, segue meu orçamento: https://primemarbleshop.com.br/orcamento/' + data.token)}" target="_blank" style="max-width:240px;margin:0 auto;display:block;text-decoration:none">Enviar Orcamento</a>
                    </div>
                    <div style="margin-top:10px">
                        <button class="btn btn-back" onclick="location.reload()" style="max-width:200px;margin:0 auto">Novo Orcamento</button>
                    </div>
                </div>`;
            document.getElementById('btnBack').classList.add('hidden');
            document.getElementById('btnContinuar').classList.add('hidden');
            btnNext.classList.add('hidden');
        } else {
            mostrarAviso('Erro: ' + (data.error || 'Tente novamente.'));
            btnNext.textContent = 'Finalizar';
            btnNext.disabled = false;
        }
    })
    .catch(() => {
        mostrarAviso('Erro de conexao. Tente novamente.');
        btnNext.textContent = 'Finalizar';
        btnNext.disabled = false;
    });
}

/* ---------- HELPERS ---------- */
function togHtml(key, label, hint) {
    return `<div class="tog ${CFG[key]?'on':''}" onclick="toggleOpt('${key}')">
        <div><div class="tl">${label}</div><div class="th">${hint}</div></div>
        <div class="sw"></div></div>`;
}

function pick(key, val) {
    CFG[key] = val;
    if (key === 'produto' || key === 'modelo') { zoomLevel = 1; panX = 0; panY = 0; }
    if (key === 'modelo' || key === 'lavModelo') {
        CFG.compSeca = 120; CFG.profSeca = 60;
        CFG.compMolhada = 120; CFG.profMolhada = 60;
        CFG.compSecaLat = 60; CFG.compSecaEsq = 60; CFG.profSecaEsq = 60;
        CFG.compSecaDir = 60; CFG.profSecaDir = 60;
        CFG.compMolhadaLat = 60; CFG.compMolhadaEsq = 60; CFG.profMolhadaEsq = 60;
        CFG.compMolhadaDir = 60; CFG.profMolhadaDir = 60;
        CFG.compL = 120; CFG.profL = 60;
        CFG.bordas = { fundo:'fronte', frente:'saia', esquerda:'livre', direita:'livre', direita2:'livre', l_esquerda:'livre', l_fundo:'livre' };
        CFG.bordaAlts = { fundo:10, frente:10, esquerda:10, direita:10, direita2:10, l_esquerda:10, l_fundo:10 };
        CFG.bordaSaiaLarg = { fundo:5, frente:5, esquerda:5, direita:5, direita2:5, l_esquerda:5, l_fundo:5 };
        CFG.cuba = false; CFG.cubaQtd = 1;
        CFG.cubaLocal = val === 'seca_centro_molhada_lat' ? 'molhada_esq' : 'molhada';
        CFG.cuba2Local = val === 'seca_centro_molhada_lat' ? 'molhada_dir' : 'seca';
        CFG.cooktop = false; CFG.cooktopLocal = 0;
        CFG.espelhar = false;
    }
    renderStep();
}

function addSoleira() {
    CFG.soleiras.push({larg: 80, prof: 15, qtd: 1});
    renderStep();
}
function removeSoleira(i) {
    CFG.soleiras.splice(i, 1);
    renderStep();
}
function updSoleira(i, key, val) {
    CFG.soleiras[i][key] = parseFloat(val) || 0;
    draw(); renderStep();
}

function setBorda(side, type) {
    CFG.bordas[side] = type;
    if (type === 'ilharga') CFG.bordaAlts[side] = 92;
    else if (type === 'fronte') CFG.bordaAlts[side] = 10;
    else if (type === 'saia') CFG.bordaSaiaLarg[side] = 5;
    draw(); renderStep();
}

function toggleOpt(key) {
    CFG[key] = !CFG[key];
    renderStep();
}

function updVal(key, val) {
    CFG[key] = val;
    draw(); renderStep();
}

function updateStepBar() {
    const steps = getSteps();
    document.getElementById('stepsBar').innerHTML = steps.map((_, i) =>
        `<div class="stp ${i<step?'done':''} ${i===step?'cur':''}"></div>`).join('');
}

function updateInfo() {
    document.getElementById('vInfo').style.display = 'none';
}

function goNext() {
    const steps = getSteps();
    if (steps[step] === 'cliente') {
        if (!CFG.clienteNome.trim() || !CFG.clienteTelefone.trim() || !CFG.clienteEndereco.trim()) {
            mostrarAviso('Preencha nome, telefone e endereço para continuar.');
            return;
        }
    }
    if (steps[step] === 'material' && !CFG.materialId) {
        mostrarAviso('Selecione um material para continuar.');
        return;
    }
    if (step < steps.length - 1) { step++; renderStep(); }
    else { finalizarOrcamento(); }
}

function goBack() {
    if (step > 0) { step--; renderStep(); }
}

function continuarOrcamento() {
    if (!produtosSalvos) produtosSalvos = [];
    const desenhoSnap = canvas.toDataURL('image/png');
    produtosSalvos.push(JSON.parse(JSON.stringify({
        produto: CFG.produto,
        modelo: CFG.modelo,
        lavModelo: CFG.lavModelo,
        compMolhada: CFG.compMolhada, profMolhada: CFG.profMolhada,
        compSeca: CFG.compSeca, profSeca: CFG.profSeca, compSecaLat: CFG.compSecaLat,
        compSecaEsq: CFG.compSecaEsq, profSecaEsq: CFG.profSecaEsq,
        compSecaDir: CFG.compSecaDir, profSecaDir: CFG.profSecaDir,
        compL: CFG.compL, profL: CFG.profL,
        compMolhadaLat: CFG.compMolhadaLat,
        compMolhadaEsq: CFG.compMolhadaEsq, profMolhadaEsq: CFG.profMolhadaEsq,
        compMolhadaDir: CFG.compMolhadaDir, profMolhadaDir: CFG.profMolhadaDir,
        compGen: CFG.compGen, profGen: CFG.profGen,
        lavRecorteLarg: CFG.lavRecorteLarg, lavRecorteAlt: CFG.lavRecorteAlt,
        nichoLarg: CFG.nichoLarg, nichoAlt: CFG.nichoAlt, nichoProf: CFG.nichoProf,
        nichoFundo: CFG.nichoFundo, nichoAlisar: CFG.nichoAlisar, nichoAlisarMedida: CFG.nichoAlisarMedida,
        soleiraLarg: CFG.soleiraLarg, soleiraProf: CFG.soleiraProf, soleiraQtd: CFG.soleiraQtd,
        soleiras: CFG.soleiras ? JSON.parse(JSON.stringify(CFG.soleiras)) : null,
        bordas: {...CFG.bordas}, bordaAlts: {...CFG.bordaAlts}, bordaSaiaLarg: {...CFG.bordaSaiaLarg},
        cuba: CFG.cuba, cubaQtd: CFG.cubaQtd, cubaLocal: CFG.cubaLocal,
        tipoCuba: CFG.tipoCuba, cubaComp: CFG.cubaComp, cubaLarg: CFG.cubaLarg, cubaAlt: CFG.cubaAlt,
        cuba2Local: CFG.cuba2Local, tipoCuba2: CFG.tipoCuba2, cubaComp2: CFG.cubaComp2, cubaLarg2: CFG.cubaLarg2, cubaAlt2: CFG.cubaAlt2,
        furoTorneira: CFG.furoTorneira, furoTorneira2: CFG.furoTorneira2,
        cooktop: CFG.cooktop, cooktopLocal: CFG.cooktopLocal,
        espelhar: CFG.espelhar,
        materialId: CFG.materialId,
        desenho: desenhoSnap
    })));
    CFG.produto = '';
    CFG.modelo = '';
    CFG.cuba = false; CFG.cooktop = false;
    CFG.bordas = { fundo:'fronte', frente:'saia', esquerda:'livre', direita:'livre', direita2:'livre', l_esquerda:'livre', l_fundo:'livre' };
    CFG.bordaAlts = { fundo:10, frente:10, esquerda:10, direita:10, direita2:10, l_esquerda:10, l_fundo:10 };
    CFG.bordaSaiaLarg = { fundo:5, frente:5, esquerda:5, direita:5, direita2:5, l_esquerda:5, l_fundo:5 };
    step = getSteps().indexOf('produto');
    renderStep();
}
