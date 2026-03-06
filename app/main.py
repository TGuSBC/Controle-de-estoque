
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from .database import SessionLocal, engine, Base
from . import models
from .auth import hash_password, verify, create_token
from fastapi.responses import FileResponse
import openpyxl

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Stillus Home - Controle de Estoque")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def db():
    d = SessionLocal()
    try:
        yield d
    finally:
        d.close()

@app.post("/login")
def login(email: str, senha: str, db: Session = Depends(db)):
    user = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if not user or not verify(senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="login inválido")
    token = create_token({"user": user.id})
    return {"token": token}

@app.post("/usuarios")
def criar_usuario(nome:str,email:str,senha:str,role:str,db:Session=Depends(db)):
    u=models.Usuario(nome=nome,email=email,senha_hash=hash_password(senha),role=role)
    db.add(u)
    db.commit()
    return {"msg":"usuario criado"}

@app.post("/produtos")
def criar_produto(nome:str,sku:str,db:Session=Depends(db)):
    p=models.Produto(nome=nome,sku=sku)
    db.add(p)
    db.commit()
    return {"msg":"produto criado"}

@app.post("/corredores")
def criar_corredor(nome:str,db:Session=Depends(db)):
    c=models.Corredor(nome=nome)
    db.add(c)
    db.commit()
    return {"msg":"corredor criado"}

@app.post("/movimentar")
def movimentar(sku:str,corredor:str,tipo:str,quantidade:int,db:Session=Depends(db)):

    produto=db.query(models.Produto).filter(models.Produto.sku==sku).first()
    if not produto:
        raise HTTPException(404,"produto não encontrado")

    cor=db.query(models.Corredor).filter(models.Corredor.nome==corredor).first()
    if not cor:
        raise HTTPException(404,"corredor não encontrado")

    if tipo=="SAIDA":
        entradas=db.query(func.sum(models.Movimentacao.quantidade)).filter(models.Movimentacao.produto_id==produto.id,models.Movimentacao.tipo=="ENTRADA").scalar() or 0
        saidas=db.query(func.sum(models.Movimentacao.quantidade)).filter(models.Movimentacao.produto_id==produto.id,models.Movimentacao.tipo=="SAIDA").scalar() or 0
        saldo=entradas-saidas
        if saldo<quantidade:
            raise HTTPException(400,"estoque insuficiente")

    m=models.Movimentacao(produto_id=produto.id,corredor_id=cor.id,tipo=tipo,quantidade=quantidade,usuario_id=1)
    db.add(m)
    db.commit()

    return {"msg":"movimentação registrada"}

@app.get("/dashboard")
def dashboard(db:Session=Depends(db)):

    total_produtos=db.query(models.Produto).count()
    total_mov=db.query(models.Movimentacao).count()

    ultimas=db.query(models.Movimentacao).order_by(models.Movimentacao.id.desc()).limit(5).all()

    return {
        "total_produtos":total_produtos,
        "total_movimentacoes":total_mov,
        "ultimas":[m.id for m in ultimas]
    }

@app.get("/exportar")
def exportar(db:Session=Depends(db)):

    wb=openpyxl.Workbook()
    ws=wb.active
    ws.append(["Produto","SKU"])

    produtos=db.query(models.Produto).all()

    for p in produtos:
        ws.append([p.nome,p.sku])

    path="estoque_export.xlsx"
    wb.save(path)

    return FileResponse(path,filename="estoque.xlsx")
