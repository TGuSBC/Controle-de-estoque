const API="http://localhost:7007"

async function loadDashboard(){
let r=await fetch(API+"/dashboard")
let d=await r.json()
document.getElementById("total_produtos").innerText=d.total_produtos
document.getElementById("total_mov").innerText=d.total_movimentacoes
}

async function produto(){
await fetch(API+"/produtos",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({nome:document.getElementById("p_nome").value,sku:document.getElementById("p_sku").value})})
alert("Produto cadastrado")
}

async function entrada(){
await fetch(API+"/movimentar",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({sku:e_sku.value,corredor:e_corredor.value,tipo:"ENTRADA",quantidade:parseInt(e_qtd.value)})})
alert("Entrada registrada")
}

async function saida(){
await fetch(API+"/movimentar",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({sku:s_sku.value,corredor:s_corredor.value,tipo:"SAIDA",quantidade:parseInt(s_qtd.value)})})
alert("Saída registrada")
}