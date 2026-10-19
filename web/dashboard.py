"""Functional browser workspace preserving the main desktop navigation."""
PAGE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Magazzino Tele - Gestionale</title>
<style>
:root{font-family:system-ui,Arial,sans-serif;color:#1d2938;background:#f4f6f8}
body{margin:0}header{padding:20px 24px;background:#173653;color:white}
header h1{margin:0;font-size:25px}header p{margin:3px 0 0}
nav{background:#fff;padding:12px 24px;display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid #d9e0e8}
button,select,input,textarea{font:inherit;border:1px solid #c5d0da;border-radius:5px;padding:9px}
button{cursor:pointer;background:white}button.primary,button.sel{background:#146098;color:white;border-color:#146098}
button:disabled{opacity:.5;cursor:not-allowed}
main{padding:20px 24px;max-width:1450px;margin:auto}
section{background:white;padding:18px;border:1px solid #d9e0e8;border-radius:8px;margin-bottom:16px}
h2{font-size:20px;margin:0 0 14px}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.tiles button{padding:24px;text-align:left;font-weight:bold;min-height:90px}
.tools{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.tools input{min-width:200px}
.scroll{overflow:auto;max-height:65vh}
table{width:100%;border-collapse:collapse;background:#fff;font-size:14px}
th,td{padding:9px;text-align:left;border:1px solid #dfe5eb;vertical-align:top}
th{background:#e8eff6;white-space:nowrap}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.field{display:grid;gap:5px;font-size:14px}.field>input,.field>select{width:100%;box-sizing:border-box}
#notice{padding:10px 0;white-space:pre-wrap;color:#a43c21}
.secondary{color:#64758a;font-size:14px}.hidden{display:none!important}
.pill{padding:3px 8px;border-radius:15px;background:#e6ecf1}
@media(max-width:600px){main{padding:10px}section{padding:12px}nav{padding:8px}}
</style></head><body>
<header><h1>Magazzino Tele</h1><p>Gestione magazzino e ordini · applicazione indipendente</p></header>
<nav id="nav"></nav>
<main><div id="notice" role="alert"></div>
<section id="home"><h2>Menu principale</h2><div class="tiles" id="tiles"></div>
<p class="secondary">Le anagrafiche partono vuote e possono essere caricate dal database o importate con la funzione dedicata. Nessun dato dimostrativo.</p></section>
<section id="orders" class="hidden"><h2>Ordini registrati</h2>
<div class="tools"><input id="orderSearch" placeholder="Cerca cliente, codice, ordine">
<select id="orderColor"><option value="">Tutti i colori</option></select>
<button onclick="loadOrders()">Cerca / aggiorna</button>
<button class="primary" onclick="navigate('new')">Crea nuovo ordine</button></div>
<div class="scroll"><table><thead><tr><th>ID</th><th>Data</th><th>Nome cliente</th><th>Cod. cliente</th><th>Modello</th><th>Colore</th><th>Qtà</th><th>Evaso</th><th>Azioni</th></tr></thead><tbody id="orderRows"></tbody></table></div>
<p id="orderTotals" class="secondary"></p>
<div class="tools"><button onclick="orderPage=Math.max(0,orderPage-1);loadOrders()">Indietro</button><span id="orderPage"></span>
<button onclick="orderPage++;loadOrders()">Avanti</button></div></section>
<section id="new" class="hidden"><h2>Crea nuovo ordine</h2>
<div class="grid">
<label class="field">Tipo cliente / fornitore<select id="orderKind" onchange="renderCustomerChoices()"><option value="C">Cliente</option><option value="F">Fornitore</option></select></label>
<label class="field">Cliente / fornitore<select id="orderCustomer"></select></label>
<label class="field">Data<input type="date" id="orderDate"></label>
</div><h3>Prodotti dell'ordine</h3>
<div class="tools"><select id="orderProduct" style="max-width:420px"></select>
<label>Quantità <input type="number" min="1" value="1" id="orderQty" style="width:85px"></label>
<button onclick="addLine()">Aggiungi prodotto</button></div>
<div class="scroll"><table><thead><tr><th>Modello</th><th>Colore</th><th>Codice</th><th>Quantità</th><th></th></tr></thead><tbody id="lineRows"></tbody></table></div>
<p id="orderSum"></p><div class="tools"><button class="primary" onclick="saveOrder()">Salva ordine</button><button onclick="navigate('orders')">Annulla</button></div>
<p class="secondary">L'ordine viene scritto in una transazione con tutte le righe. Le quantità del magazzino non vengono modificate automaticamente.</p></section>
<section id="customers" class="hidden"><h2>Gestisci clienti e fornitori</h2>
<div class="grid"><label class="field">Codice univoco (max 10)<input id="customerCode" maxlength="10"></label>
<label class="field">Tipo<select id="customerKind"><option value="C">Cliente</option><option value="F">Fornitore</option></select></label>
<label class="field">Descrizione / ragione sociale<input id="customerName"></label></div>
<div class="tools" style="margin-top:12px"><button class="primary" onclick="saveCustomer()">Aggiungi cliente/fornitore</button>
<input id="customerSearch" placeholder="Filtra anagrafica" oninput="renderCustomers()"></div>
<div class="scroll"><table><thead><tr><th>Codice</th><th>Tipo</th><th>Descrizione</th></tr></thead><tbody id="customerRows"></tbody></table></div></section>
<section id="inventory" class="hidden"><h2>Gestisci inventario</h2><div class="tools">
<input id="stockSearch" placeholder="Filtra modello o colore" oninput="renderInventory()">
<button onclick="loadInventory()">Aggiorna giacenze</button></div>
<div class="scroll"><table><thead><tr><th>Codice prodotto</th><th>Modello</th><th>Colore</th><th>Giacenza</th><th></th></tr></thead><tbody id="stockRows"></tbody></table></div>
<p class="secondary">Inserisci la quantità e premi Salva. Il codice prodotto deve esistere nel catalogo.</p></section>
<section id="catalog" class="hidden"><h2>Anagrafiche prodotti, modelli e colori</h2><p class="secondary">Lettura delle tabelle originali; l'importazione e le modifiche avanzate saranno gestite dalla sezione dedicata.</p>
<div class="tools"><button onclick="showCatalog('models')">Modelli</button><button onclick="showCatalog('colors')">Colori</button><button onclick="showCatalog('products')">Prodotti</button></div>
<div class="scroll"><table><tbody id="catalogRows"></tbody></table></div></section>
<section id="import" class="hidden"><h2>Importazione CSV, XLS, XLSX e ZIP</h2><p>Carica i file Excel delle anagrafiche tramite la funzione di importazione controllata. Nessun dato viene importato automaticamente da GitHub.</p>
<p id="importGuide" class="secondary">Ordine di caricamento: clienti, modelli, colori, prodotti, ordini, magazzino, righe ordine.</p>
<div style="border:1px solid #c6d6e3;border-radius:8px;padding:16px;margin:4px 0 24px;background:#f7fafc">
<h3>Da schede colore Excel a ordini</h3>
<p>Carica uno o più file per colore <strong>.xls / .xlsx</strong>, oppure <strong>excel.zip</strong>. La procedura riconosce gli ordini con quantità positiva, cerca clienti, colori e prodotti già registrati e prepara le nuove anagrafiche con codici obbligatori. Le quantità negative e le formule delle disponibilità non sono ordini.</p>
<div class="tools">
<label>Data di registrazione <input type="date" id="workbookDate"></label>
<input type="file" id="colorOrderFiles" accept=".xls,.xlsx,.zip" multiple>
<button onclick="previewColorOrders()">1. Controlla ordini</button>
<button id="colorApply" disabled class="primary" onclick="applyColorOrders()">2. Conferma e importa</button>
</div>
<p class="secondary">Le intestazioni sono Cod.Cli., NOME, IMP., Q.TA e DESCRITTIVA, oppure MODELLO / CLIENTI / Q.TA. Per i nuovi modelli verrà utilizzata la descrizione esatta degli Excel: controlla l'anteprima. La data DATA EVAS. non viene scambiata per la data dell'ordine.</p>
<pre id="colorOrderPreview" style="white-space:pre-wrap;max-height:480px;overflow:auto"></pre>
</div>
<h3>Carica anagrafiche iniziali (CSV/Excel/ZIP)</h3>
<form id="importForm"><input type="file" id="excelFiles" accept=".csv,.xls,.xlsx,.zip" multiple>
<button type="button" onclick="previewImport()">Controlla file</button>
<button type="button" class="primary" onclick="applyImport()">Importa dopo verifica</button></form>
<pre id="importPreview" style="white-space:pre-wrap"></pre></section>
<section id="sqlBackup" class="hidden"><h2>Backup database SQL</h2>
<p class="secondary">Scarica un file <strong>database-backup.sql</strong> con le sette tabelle e tutti i loro record. Il file contiene dati aziendali: conservarlo sul PC, non pubblicarlo su GitHub.</p>
<div class="tools"><button class="primary" onclick="downloadSQL()">Scarica backup SQL (.sql)</button></div>
<h3>Ripristina da un file SQL</h3>
<p class="secondary">Accettiamo i dump MySQL .sql e le query di inserimento con colonne compatibili, anche quando Windows le chiama «Microsoft SQL Server Query File». Non eseguiamo script arbitrari e non sostituiamo tabelle già popolate. La sintassi T-SQL non compatibile sarà segnalata.</p>
<div class="tools"><input type="file" id="sqlFile" accept=".sql" onchange="sqlReceipt=null"><button onclick="previewSQL()">Verifica backup SQL</button><button class="primary" onclick="restoreSQL()">Importa backup dopo verifica</button></div>
<pre id="sqlSummary" style="white-space:pre-wrap;overflow:auto;max-height:380px"></pre>
</section>
<section id="devReset" class="hidden"><h2>Test temporanei del gestionale</h2><p>Questa funzione riguarda soltanto Magazzino Tele. Prima di svuotare le tabelle salva una copia privata sul server.</p><button onclick="resetTele()">Cancella tutta la memoria</button></section><section id="detail" class="hidden"><h2>Dettaglio ordine</h2><div id="detailText"></div>
<div class="tools"><button onclick="markOrder(true)">Segna evaso</button>
<button onclick="markOrder(false)">Riapri ordine</button><button onclick="navigate('orders')">Torna agli ordini</button></div>
<div class="scroll"><table><thead><tr><th>Modello</th><th>Colore</th><th>Quantità</th><th>Scritta</th><th>Cuscino</th></tr></thead><tbody id="detailRows"></tbody></table></div></section>
</main>
<script>
const views=[['home','Menu principale'],['new','Crea nuovo ordine'],['orders','Gestisci ordini'],
 ['customers','Gestisci clienti'],['inventory','Gestisci inventario'],['catalog','Anagrafiche'],['import','Importa Excel'],['sqlBackup','Backup SQL']];
let catalog={customers:[],colors:[],models:[],products:[]},lines=[],stock=[],orderPage=0,currentOrder=null;
const $=id=>document.getElementById(id);
const text=(el,v)=>el.textContent=v==null?'':String(v);
function cell(tr,v){const td=document.createElement('td');text(td,v);tr.appendChild(td);return td}
function button(label,fn){const b=document.createElement('button');text(b,label);b.onclick=fn;return b}
function setMessage(s){text($('notice'),s)}
async function api(url,opt){let res=await fetch('/api/'+url,opt);let data=await res.json();if(!res.ok)throw Error(data.error||'Operazione non riuscita');return data}
async function loadCatalog(){
 try{catalog=await api('workflow/catalog');renderCustomerChoices();renderProducts();renderCustomers();renderColors();
 }catch(e){setMessage(e.message)}
}
function navigate(view){views.forEach(([id])=>$(id).classList.toggle('hidden',id!==view));
 document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('sel',b.dataset.view===view));
 setMessage('');if(view==='orders')void loadOrders();if(view==='inventory')void loadInventory();if(view==='catalog')showCatalog('models');
 if(view==='new'&&!$('orderDate').value)$('orderDate').value=new Date().toLocaleDateString('sv-SE');
}
views.forEach(([id,label])=>{let b=button(label,()=>navigate(id));b.dataset.view=id;$('nav').appendChild(b)});
views.filter(x=>!['home','catalog','import'].includes(x[0])).forEach(([id,label])=>$('tiles').appendChild(button(label,()=>navigate(id))));
$('tiles').appendChild(button('Importa Excel',()=>navigate('import')));
$('tiles').appendChild(button('Backup SQL',()=>navigate('sqlBackup')));
function choice(select,items,label,id){select.replaceChildren();for(const item of items){let o=document.createElement('option');o.value=id(item);text(o,label(item));select.appendChild(o)}}
function renderCustomerChoices(){const kind=$('orderKind').value;choice($('orderCustomer'),
 catalog.customers.filter(c=>!c.kind||c.kind===kind),c=>c.code+' — '+c.name,c=>c.code)}
function renderProducts(){choice($('orderProduct'),catalog.products,p=>p.model+' / '+p.color+' ('+p.code+')',p=>p.code)}
function renderColors(){choice($('orderColor'),[{name:'Tutti i colori'},...catalog.colors],c=>c.name,c=>c.name==='Tutti i colori'?'':c.name)}
function renderCustomers(){const tbody=$('customerRows');tbody.replaceChildren();const q=$('customerSearch').value.toLowerCase();
 for(const c of catalog.customers.filter(x=>[x.code,x.name].join(' ').toLowerCase().includes(q)).slice(0,500)){
 let tr=document.createElement('tr');[c.code,c.kind,c.name].forEach(x=>cell(tr,x));tbody.appendChild(tr)}}
async function saveCustomer(){
 const code=$('customerCode').value.trim(),name=$('customerName').value.trim(),kind=$('customerKind').value;
 if(!code||!name){setMessage('Inserisci codice e descrizione');return}
 try{await api('clienti',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({'ï»¿codiceunivoco':code,CoF:kind,descrizione:name})});
 $('customerCode').value='';$('customerName').value='';await loadCatalog();setMessage('Cliente inserito');
 }catch(e){setMessage(e.message)}}
function addLine(){
 const product=catalog.products.find(p=>p.code===$('orderProduct').value),quantity=Number($('orderQty').value);
 if(!product||!Number.isInteger(quantity)||quantity<=0){setMessage('Seleziona un prodotto e una quantità positiva');return}
 lines.push({code:product.code,quantity,product});renderLines();setMessage('')}
function renderLines(){let tbody=$('lineRows');tbody.replaceChildren();lines.forEach((r,i)=>{let tr=document.createElement('tr');
 [r.product.model,r.product.color,r.code,r.quantity].forEach(v=>cell(tr,v));
 let td=cell(tr,'');td.appendChild(button('Rimuovi',()=>{lines.splice(i,1);renderLines()}));tbody.appendChild(tr)});
 text($('orderSum'),'Totale pezzi: '+lines.reduce((n,x)=>n+x.quantity,0))}
async function saveOrder(){
 if(!lines.length||!$('orderCustomer').value){setMessage('Seleziona cliente e almeno un prodotto');return}
 if(!window.confirm('Confermi il salvataggio dell’ordine?'))return;
 try{let r=await api('workflow/orders',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({customer:$('orderCustomer').value,date:$('orderDate').value,lines})});
 lines=[];renderLines();navigate('orders');setMessage('Ordine '+r.id+' salvato');
 }catch(e){setMessage(e.message)}}
async function loadOrders(){
 try{let q=encodeURIComponent($('orderSearch').value),color=encodeURIComponent($('orderColor').value);
 let d=await api('workflow/orders?q='+q+'&color='+color+'&page='+orderPage),tbody=$('orderRows');tbody.replaceChildren();
 for(const r of d.rows){let tr=document.createElement('tr');
 [r.id,r.data,r.cliente||'',r.codice_cliente,r.modello,r.colore,r.quantita,r.evaso?'Sì':'No'].forEach(v=>cell(tr,v));
 cell(tr,'').appendChild(button('Apri',()=>void openOrder(r.id)));tbody.appendChild(tr)}
 text($('orderTotals'),'Ordini: '+d.total+' · Evasi: '+d.evasi+' · In lavorazione: '+(d.total-d.evasi));
 text($('orderPage'),'Pagina '+(orderPage+1));setMessage('');
 }catch(e){setMessage(e.message)}}
async function openOrder(id){
 try{currentOrder=await api('workflow/orders/'+id);navigate('detail');
 text($('detailText'),'Ordine '+id+' · Cliente '+currentOrder.customer+' · '+currentOrder.date);
 let tbody=$('detailRows');tbody.replaceChildren();for(const r of currentOrder.lines){let tr=document.createElement('tr');
 [r.model,r.color,r.quantity,r.scritta,r.cuscino].forEach(v=>cell(tr,v));tbody.appendChild(tr)}
 }catch(e){setMessage(e.message)}}
async function markOrder(done){if(!currentOrder)return;
 try{await api('workflow/orders/'+currentOrder.id+'/status',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({evaso:done})});
 navigate('orders');setMessage('Stato ordine aggiornato')}catch(e){setMessage(e.message)}}
async function loadInventory(){try{stock=(await api('workflow/inventory')).rows;renderInventory();setMessage('')}
 catch(e){setMessage(e.message)}}
function renderInventory(){let q=$('stockSearch').value.toLowerCase(),tbody=$('stockRows');tbody.replaceChildren();
 for(const item of stock.filter(x=>(x.model+' '+x.color+' '+x.code).toLowerCase().includes(q)).slice(0,600)){
 let tr=document.createElement('tr');[item.code,item.model,item.color].forEach(x=>cell(tr,x));
 let td=cell(tr,''),input=document.createElement('input');input.type='number';input.value=item.quantity;input.style.width='90px';td.appendChild(input);
 cell(tr,'').appendChild(button('Salva',async()=>{try{await api('workflow/inventory/'+encodeURIComponent(item.code),{
 method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({quantity:Number(input.value)})});
 item.quantity=Number(input.value);setMessage('Giacenza '+item.code+' salvata')}catch(e){setMessage(e.message)}}));
 tbody.appendChild(tr)}}
function showCatalog(which){let tbody=$('catalogRows');tbody.replaceChildren();
 for(const item of catalog[which]||[]){let tr=document.createElement('tr');Object.values(item).forEach(v=>cell(tr,v));tbody.appendChild(tr)}}

let colorToken=null;
$('workbookDate').value=new Date().toLocaleDateString('sv-SE');
function clearColorPreview(){colorToken=null;$('colorApply').disabled=true;text($('colorOrderPreview'),'')}
$('colorOrderFiles').addEventListener('change',clearColorPreview);
$('workbookDate').addEventListener('change',clearColorPreview);
async function uploadColorOrders(apply){
 const files=$('colorOrderFiles').files;
 if(!files.length)throw Error('Seleziona almeno un file Excel per colore');
 if(!$('workbookDate').value)throw Error('Seleziona la data di registrazione');
 const form=new FormData();
 form.append('date',$('workbookDate').value);
 for(const file of files)form.append('files',file);
 if(apply)form.append('preview_token',colorToken||'');
 const response=await fetch('/api/workflow/color-orders/'+(apply?'apply':'preview'),{method:'POST',body:form});
 let result;
 try{result=await response.json()}catch(e){throw Error('Il servizio non ha restituito una risposta valida')}
 if(!response.ok)throw Error(result.error||result.message||'Caricamento fallito');
 text($('colorOrderPreview'),JSON.stringify({nuove_anagrafiche_e_ordini:result.totals,
  gia_importati:result.already_imported,problemi:result.warnings_count,
  segnalazioni:result.warnings,esempi:result.examples,
  file_analizzati:result.source_files,data:result.registration_date},null,2));
 return result;
}
async function previewColorOrders(){
 try{setMessage('');const r=await uploadColorOrders(false);
  colorToken=r.preview_token||null;
  $('colorApply').disabled=!r.validated||!colorToken;
  setMessage(r.blocked?'Anteprima con problemi: correggi o isola i file segnalati. Nessun dato modificato.':
  'Anteprima pronta: controlla i clienti, i modelli, i colori e i conteggi prima della conferma. Nessun dato modificato.');
 }catch(e){clearColorPreview();setMessage(e.message)}
}
async function applyColorOrders(){
 if(!colorToken) {setMessage('Prima controlla gli Excel');return}
 if(!confirm('Confermi la creazione degli ordini e delle anagrafiche mostrate nell’anteprima? Questa operazione modifica il database Magazzino Tele.'))return;
 $('colorApply').disabled=true;
 try{const r=await uploadColorOrders(true);colorToken=null;
  await loadCatalog();setMessage('Importazione effettuata: '+r.totals.orders+' ordini nuovi, '+r.already_imported+' già presenti.');}
 catch(e){setMessage('Importazione non effettuata: '+e.message)}
}

let verifiedImport=false,previewToken=null;
$('excelFiles').addEventListener('change',()=>{verifiedImport=false;previewToken=null;text($('importPreview'),'')});
async function sendFiles(apply){const files=$('excelFiles').files;if(!files.length){setMessage('Seleziona i file Excel');return}
 let form=new FormData();for(const file of files)form.append('files',file);if(apply&&previewToken)form.append('preview_token',previewToken);
 const route='workflow/import'+(apply?'?apply=1':'');
 let r=await fetch('/api/'+route,{method:'POST',body:form});let d=await r.json();
 if(!r.ok)throw Error(d.error||'Importazione non riuscita');
 text($('importPreview'),JSON.stringify(d,null,2));return d}
async function previewImport(){try{const info=await sendFiles(false);verifiedImport=Boolean(info.validated);previewToken=info.preview_token||null;setMessage('Controllo completato: verifica il riepilogo prima di importare')}
 catch(e){setMessage(e.message)}}
async function applyImport(){if(!verifiedImport){setMessage('Esegui prima il controllo degli Excel');return}
 if(!confirm('Importare i file nel database? Nessun dato esistente verrà sovrascritto.'))return;
 try{await sendFiles(true);verifiedImport=false;await loadCatalog();setMessage('Importazione completata')}
 catch(e){setMessage(e.message)}}

let sqlReceipt=null;
function downloadSQL(){
 window.location.href='/api/workflow/sql-backup/export';
}
async function sendSQL(apply){
 const file=$('sqlFile').files[0];
 if(!file){setMessage('Seleziona un file .sql');return}
 const form=new FormData();form.append('file',file);
 if(apply&&sqlReceipt)form.append('preview_token',sqlReceipt);
 const response=await fetch('/api/workflow/sql-backup/'+(apply?'import':'preview'),{method:'POST',body:form});
 const data=await response.json();
 if(!response.ok)throw Error(data.error||'Il backup SQL non è compatibile');
 text($('sqlSummary'),JSON.stringify(data,null,2));
 return data;
}
async function previewSQL(){
 try{const result=await sendSQL(false);sqlReceipt=result.preview_token;
 setMessage('Anteprima SQL riuscita: controlla le tabelle e il numero di record. Nessun dato modificato.');
 }catch(e){sqlReceipt=null;setMessage('Verifica backup: '+e.message)}
}
async function restoreSQL(){
 if(!sqlReceipt){setMessage('Prima usa Verifica backup SQL');return}
 if(!confirm('Confermi l’importazione SQL nelle tabelle attualmente vuote?'))return;
 try{const result=await sendSQL(true);sqlReceipt=null;await loadCatalog();
 setMessage('Backup SQL importato: '+result.total+' righe.');}
 catch(e){setMessage('Ripristino annullato: '+e.message)}
}

async function loadResetStatus(){
 try {const r=await api('workflow/dev-reset/status');$('devReset').classList.toggle('hidden',!r.enabled)}
 catch(e){$('devReset').classList.add('hidden')}
}
async function resetTele(){
 const phrase='CANCELLA MAGAZZINO TELE';
 if(prompt('Vuoi azzerare solo i dati di Magazzino Tele? Verrà salvato un backup. Digita '+phrase)!==phrase)return;
 const code=prompt('Codice temporaneo di manutenzione:');if(!code)return;
 if(!confirm('Confermi la cancellazione di clienti, ordini, prodotti e giacenze dal solo gestionale Tele?'))return;
 try{
  const r=await api('workflow/dev-reset',{method:'POST',headers:{'Content-Type':'application/json','X-Dev-Reset-Token':code},
   body:JSON.stringify({confirm:phrase})});
  await loadCatalog();navigate('home');
  setMessage('Test ripristinato. Record rimossi: '+r.rows_removed+'. Copia privata: '+r.backup);
 }catch(e){setMessage('Operazione annullata: '+e.message)}
}
void loadCatalog();void loadResetStatus();navigate('home');
</script></body></html>"""
