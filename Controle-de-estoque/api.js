const API = "http://localhost:7007"

let token = localStorage.getItem("token")

function authHeaders(json=false){
return {
...(json?{"Content-Type":"application/json"}:{}),
"Authorization":`Bearer ${token}`
}
}

function sair(){
localStorage.removeItem("token")
window.location.href="../login.html"
}

if(!token && !window.location.pathname.includes("login")){
window.location.href="../login.html"
}

async function login(){

let email=document.getElementById("email").value
let senha=document.getElementById("senha").value

if(!email || !senha){
alert("Preencha email e senha")
return
}

let r=await fetch(API+"/login",{
method:"POST",
headers:{"Content-Type":"application/x-www-form-urlencoded"},
body:new URLSearchParams({email,senha})
})

let d=await r.json()

if(!r.ok){
alert(d.detail || "Erro no login")
return
}

token=d.token
localStorage.setItem("token",token)

window.location.href="Controle-de-estoque/index.html"
}

document.querySelector(".navbar-exit")?.addEventListener("click",sair)

async function loadDashboard(){

let r=await fetch(API+"/dashboard",{headers:authHeaders()})

if(!r.ok){
if(r.status==401)sair()
alert("Erro ao carregar dashboard")
return
}

let d=await r.json()

document.getElementById("total_produtos").innerText=d.total_produtos
document.getElementById("total_mov").innerText=d.total_movimentacoes
}

async function produto(){

let nome=document.getElementById("p_nome").value
let sku=document.getElementById("p_sku").value

if(!nome || !sku){
alert("Preencha todos os campos")
return
}

let r=await fetch(API+"/produtos",{
method:"POST",
headers:authHeaders(true),
body:JSON.stringify({nome,sku})
})

if(!r.ok){
let d=await r.json()
alert(d.detail)
return
}

alert("Produto cadastrado")
}

async function entrada(){

let qtd=parseInt(e_qtd.value)

if(isNaN(qtd)||qtd<=0){
alert("Quantidade inválida")
return
}

let r=await fetch(API+"/movimentar",{
method:"POST",
headers:authHeaders(true),
body:JSON.stringify({
sku:e_sku.value,
corredor:e_corredor.value,
tipo:"ENTRADA",
quantidade:qtd
})
})

if(!r.ok){
let d=await r.json()
alert(d.detail)
return
}

alert("Entrada registrada")
loadDashboard()
}

async function saida(){

let qtd=parseInt(s_qtd.value)

if(isNaN(qtd)||qtd<=0){
alert("Quantidade inválida")
return
}

let r=await fetch(API+"/movimentar",{
method:"POST",
headers:authHeaders(true),
body:JSON.stringify({
sku:s_sku.value,
corredor:s_corredor.value,
tipo:"SAIDA",
quantidade:qtd
})
})

if(!r.ok){
let d=await r.json()
alert(d.detail)
return
}

alert("Saída registrada")
loadDashboard()
}

async function carregarNotificacoes(){

let r=await fetch(API+"/notificacoes",{headers:authHeaders()})

if(!r.ok)return

let d=await r.json()

if(d.total>0){
console.log("Notificações:",d.notificacoes)
}
}

if(token){

loadDashboard()

carregarNotificacoes()

setInterval(carregarNotificacoes,30000)

}