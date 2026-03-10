from datetime import datetime, timedelta
import os
from typing import Optional

import openpyxl
from fastapi import Depends, FastAPI, HTTPException, Query, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from . import models
from .auth import ALGO, SECRET, create_token, hash_password, verify
from .database import Base, SessionLocal, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Stillus Home - Controle de Estoque")
security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_ANALISTA_EMAIL = os.getenv("ADMIN_ANALISTA_EMAIL", "analista@stillushome.com")
ADMIN_ANALISTA_SENHA = os.getenv("ADMIN_ANALISTA_SENHA", "Analista@2026")
ADMIN_DONO_EMAIL = os.getenv("ADMIN_DONO_EMAIL", "dono@stillushome.com")
ADMIN_DONO_SENHA = os.getenv("ADMIN_DONO_SENHA", "Dono@2026")

ALLOWED_ADMIN_EMAILS = {ADMIN_ANALISTA_EMAIL.lower(), ADMIN_DONO_EMAIL.lower()}


class UsuarioCreate(BaseModel):
    nome: str
    email: str
    senha: str
    role: str = "USER"


class ProdutoCreate(BaseModel):
    nome: str
    sku: str


class CorredorCreate(BaseModel):
    nome: str


class MovimentacaoCreate(BaseModel):
    sku: str
    corredor: str
    tipo: str
    quantidade: int


class ClienteCreate(BaseModel):
    nome: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    documento: Optional[str] = None


class TrocarSenhaInicialPayload(BaseModel):
    senha_atual: str
    nova_senha: str


def db():
    d = SessionLocal()
    try:
        yield d
    finally:
        d.close()


def garantir_schema_usuario():
    with engine.begin() as conn:
        colunas = conn.execute(text("PRAGMA table_info(usuarios)")).fetchall()
        nomes = {c[1] for c in colunas}
        if "must_change_password" not in nomes:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN must_change_password BOOLEAN DEFAULT 0"))


def saldo_produto(dbase: Session, produto_id: int) -> int:
    entradas = dbase.query(func.sum(models.Movimentacao.quantidade)).filter(
        models.Movimentacao.produto_id == produto_id,
        models.Movimentacao.tipo == "ENTRADA",
    ).scalar() or 0

    saidas = dbase.query(func.sum(models.Movimentacao.quantidade)).filter(
        models.Movimentacao.produto_id == produto_id,
        models.Movimentacao.tipo == "SAIDA",
    ).scalar() or 0

    return entradas - saidas


def admin_habilitado(usuario: models.Usuario) -> bool:
    if not usuario:
        return False
    return usuario.role == "ADMIN" and usuario.email.lower() in ALLOWED_ADMIN_EMAILS


def usuario_atual(
    credenciais: HTTPAuthorizationCredentials = Depends(security),
    dbase: Session = Depends(db),
):
    token = credenciais.credentials
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_id = payload.get("user")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token invalido") from exc

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token invalido")

    usuario = dbase.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not usuario or not usuario.ativo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="usuario nao autorizado")
    return usuario


def usuario_operacional(usuario: models.Usuario = Depends(usuario_atual)):
    if getattr(usuario, "must_change_password", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="troca de senha obrigatoria")
    return usuario


def admin_atual(usuario: models.Usuario = Depends(usuario_operacional)):
    if not admin_habilitado(usuario):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="acesso restrito a administradores autorizados")
    return usuario


def garantir_admins_iniciais():
    dbase = SessionLocal()
    try:
        seeds = [
            ("Analista do Software", ADMIN_ANALISTA_EMAIL, ADMIN_ANALISTA_SENHA),
            ("Dono da Empresa", ADMIN_DONO_EMAIL, ADMIN_DONO_SENHA),
        ]

        for nome, email, senha in seeds:
            usuario = dbase.query(models.Usuario).filter(models.Usuario.email == email).first()
            if not usuario:
                usuario = models.Usuario(
                    nome=nome,
                    email=email,
                    senha_hash=hash_password(senha),
                    role="ADMIN",
                    ativo=True,
                    must_change_password=True,
                )
                dbase.add(usuario)
            else:
                usuario.role = "ADMIN"
                usuario.ativo = True

        dbase.commit()
    finally:
        dbase.close()


garantir_schema_usuario()
garantir_admins_iniciais()


@app.post("/login")
def login(email: str = Form(...), senha: str = Form(...), dbase: Session = Depends(db)):
    user = dbase.query(models.Usuario).filter(models.Usuario.email == email).first()
    if not user or not user.ativo or not verify(senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="login invalido")

    token = create_token({"user": user.id})
    return {
        "token": token,
        "usuario": {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "role": user.role,
            "admin_autorizado": admin_habilitado(user),
            "must_change_password": bool(getattr(user, "must_change_password", False)),
        },
    }


@app.get("/me")
def me(usuario: models.Usuario = Depends(usuario_atual)):
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "email": usuario.email,
        "role": usuario.role,
        "admin_autorizado": admin_habilitado(usuario),
        "must_change_password": bool(getattr(usuario, "must_change_password", False)),
    }


@app.post("/trocar-senha-inicial")
def trocar_senha_inicial(data: TrocarSenhaInicialPayload, dbase: Session = Depends(db), usuario: models.Usuario = Depends(usuario_atual)):
    if not getattr(usuario, "must_change_password", False):
        raise HTTPException(status_code=400, detail="troca inicial nao obrigatoria")

    if not verify(data.senha_atual, usuario.senha_hash):
        raise HTTPException(status_code=400, detail="senha atual invalida")

    if len(data.nova_senha) < 8:
        raise HTTPException(status_code=400, detail="nova senha deve ter pelo menos 8 caracteres")

    if data.nova_senha == data.senha_atual:
        raise HTTPException(status_code=400, detail="a nova senha deve ser diferente da atual")

    usuario.senha_hash = hash_password(data.nova_senha)
    usuario.must_change_password = False
    dbase.commit()

    return {"msg": "senha alterada com sucesso"}


@app.post("/usuarios")
def criar_usuario(data: UsuarioCreate, dbase: Session = Depends(db), _: models.Usuario = Depends(admin_atual)):
    existente = dbase.query(models.Usuario).filter(models.Usuario.email == data.email).first()
    if existente:
        raise HTTPException(status_code=400, detail="email ja cadastrado")

    role = data.role.upper()
    if role not in {"USER", "ADMIN"}:
        raise HTTPException(status_code=400, detail="role invalida")

    if role == "ADMIN" and data.email.lower() not in ALLOWED_ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="apenas os admins oficiais podem ter role ADMIN")

    usuario = models.Usuario(
        nome=data.nome,
        email=data.email,
        senha_hash=hash_password(data.senha),
        role=role,
        ativo=True,
        must_change_password=False,
    )
    dbase.add(usuario)
    dbase.commit()

    return {"msg": "usuario criado"}


@app.post("/produtos")
def criar_produto(data: ProdutoCreate, dbase: Session = Depends(db), _: models.Usuario = Depends(usuario_operacional)):
    existente = dbase.query(models.Produto).filter(models.Produto.sku == data.sku).first()
    if existente:
        raise HTTPException(status_code=400, detail="sku ja cadastrado")

    produto = models.Produto(nome=data.nome, sku=data.sku)
    dbase.add(produto)
    dbase.commit()
    return {"msg": "produto criado"}


@app.post("/corredores")
def criar_corredor(data: CorredorCreate, dbase: Session = Depends(db), _: models.Usuario = Depends(usuario_operacional)):
    existente = dbase.query(models.Corredor).filter(models.Corredor.nome == data.nome).first()
    if existente:
        raise HTTPException(status_code=400, detail="corredor ja cadastrado")

    corredor = models.Corredor(nome=data.nome)
    dbase.add(corredor)
    dbase.commit()
    return {"msg": "corredor criado"}


@app.post("/movimentar")
def movimentar(data: MovimentacaoCreate, dbase: Session = Depends(db), usuario: models.Usuario = Depends(usuario_operacional)):
    produto = dbase.query(models.Produto).filter(models.Produto.sku == data.sku).first()
    if not produto:
        raise HTTPException(status_code=404, detail="produto nao encontrado")

    cor = dbase.query(models.Corredor).filter(models.Corredor.nome == data.corredor).first()
    if not cor:
        raise HTTPException(status_code=404, detail="corredor nao encontrado")

    tipo = data.tipo.upper()
    if tipo not in {"ENTRADA", "SAIDA"}:
        raise HTTPException(status_code=400, detail="tipo invalido")

    if data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="quantidade deve ser maior que zero")

    if tipo == "SAIDA":
        saldo = saldo_produto(dbase, produto.id)
        if saldo < data.quantidade:
            raise HTTPException(status_code=400, detail="estoque insuficiente")

    mov = models.Movimentacao(
        produto_id=produto.id,
        corredor_id=cor.id,
        tipo=tipo,
        quantidade=data.quantidade,
        usuario_id=usuario.id,
    )
    dbase.add(mov)
    dbase.commit()

    return {"msg": "movimentacao registrada"}


@app.get("/dashboard")
def dashboard(
    dias: int = Query(30, ge=1),
    dbase: Session = Depends(db),
    _: models.Usuario = Depends(usuario_operacional),
):
    data_inicial = datetime.utcnow() - timedelta(days=dias)

    total_produtos = dbase.query(models.Produto).filter(models.Produto.created_at >= data_inicial).count()
    total_mov = dbase.query(models.Movimentacao).filter(models.Movimentacao.created_at >= data_inicial).count()
    mov_entradas = dbase.query(models.Movimentacao).filter(
        models.Movimentacao.created_at >= data_inicial,
        models.Movimentacao.tipo == "ENTRADA",
    ).count()
    mov_saidas = dbase.query(models.Movimentacao).filter(
        models.Movimentacao.created_at >= data_inicial,
        models.Movimentacao.tipo == "SAIDA",
    ).count()

    ultimas = dbase.query(models.Movimentacao).filter(
        models.Movimentacao.created_at >= data_inicial
    ).order_by(models.Movimentacao.id.desc()).limit(5).all()

    return {
        "total_produtos": total_produtos,
        "total_movimentacoes": total_mov,
        "dias": dias,
        "ultimas": [m.id for m in ultimas],
        "grafico": {
            "labels": ["Entradas", "Saidas"],
            "valores": [mov_entradas, mov_saidas],
        },
    }


@app.get("/notificacoes")
def notificacoes(
    limite: int = Query(50, ge=0),
    dbase: Session = Depends(db),
    _: models.Usuario = Depends(usuario_operacional),
):
    produtos = dbase.query(models.Produto).all()
    alertas = []

    for p in produtos:
        saldo = saldo_produto(dbase, p.id)
        if saldo <= limite:
            nivel = "CRITICO" if saldo <= 20 else "ATENCAO"
            alertas.append(
                {
                    "produto_id": p.id,
                    "nome": p.nome,
                    "sku": p.sku,
                    "saldo": saldo,
                    "limite": limite,
                    "nivel": nivel,
                    "mensagem": f"{p.nome} (SKU: {p.sku}) esta com {saldo} unidades.",
                }
            )

    alertas = sorted(alertas, key=lambda a: a["saldo"])
    criticos = len([a for a in alertas if a["nivel"] == "CRITICO"])

    return {
        "total": len(alertas),
        "criticos": criticos,
        "limite": limite,
        "notificacoes": alertas,
    }


@app.post("/clientes")
def criar_cliente(data: ClienteCreate, dbase: Session = Depends(db), _: models.Usuario = Depends(admin_atual)):
    if data.email:
        existente_email = dbase.query(models.Cliente).filter(models.Cliente.email == data.email).first()
        if existente_email:
            raise HTTPException(status_code=400, detail="email de cliente ja cadastrado")

    if data.documento:
        existente_doc = dbase.query(models.Cliente).filter(models.Cliente.documento == data.documento).first()
        if existente_doc:
            raise HTTPException(status_code=400, detail="documento de cliente ja cadastrado")

    cliente = models.Cliente(
        nome=data.nome,
        email=data.email,
        telefone=data.telefone,
        documento=data.documento,
        ativo=True,
    )
    dbase.add(cliente)
    dbase.commit()
    dbase.refresh(cliente)

    return {
        "id": cliente.id,
        "nome": cliente.nome,
        "email": cliente.email,
        "telefone": cliente.telefone,
        "documento": cliente.documento,
        "created_at": cliente.created_at,
    }


@app.get("/clientes")
def listar_clientes(dbase: Session = Depends(db), _: models.Usuario = Depends(admin_atual)):
    clientes = dbase.query(models.Cliente).order_by(models.Cliente.id.desc()).all()
    return [
        {
            "id": c.id,
            "nome": c.nome,
            "email": c.email,
            "telefone": c.telefone,
            "documento": c.documento,
            "ativo": c.ativo,
            "created_at": c.created_at,
        }
        for c in clientes
    ]


@app.get("/exportar")
def exportar(dbase: Session = Depends(db), _: models.Usuario = Depends(usuario_operacional)):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Produto", "SKU"])

    produtos = dbase.query(models.Produto).all()

    for p in produtos:
        ws.append([p.nome, p.sku])

    path = "estoque_export.xlsx"
    wb.save(path)

    return FileResponse(path, filename="estoque.xlsx")
