function showTab(id){
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".nav-link").forEach(link => link.classList.remove("active"));
    
    document.getElementById(id).classList.add("active");
    if(event.target) event.target.classList.add("active");
}


