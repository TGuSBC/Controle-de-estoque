async function carregar(){

const r=await fetch("http://localhost:7007/dashboard")

const d=await r.json()

document.getElementById("produtos").innerText=d.total_produtos
document.getElementById("mov").innerText=d.total_movimentacoes

}

carregar()