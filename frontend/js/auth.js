async function login(){

const email=document.getElementById("email").value
const senha=document.getElementById("senha").value

const r=await fetch("http://localhost:7007/login",{

method:"POST",

headers:{
"Content-Type":"application/x-www-form-urlencoded"
},

body:new URLSearchParams({
email,
senha
})

})

const data=await r.json()

localStorage.setItem("token",data.token)

window.location="dashboard.html"

}