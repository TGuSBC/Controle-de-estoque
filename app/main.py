from datetime import datetime, timedelta
import os
from typing import Optional

import openpyxl
from fastapi import Depends, FastAPI, HTTPException, Query, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
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
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


ADMIN_ANALISTA_EMAIL = os.getenv("ADMIN_ANALISTA_EMAIL")
ADMIN_ANALISTA_SENHA = os.getenv("ADMIN_ANALISTA_SENHA")

ADMIN_DONO_EMAIL = os.getenv("ADMIN_DONO_EMAIL")
ADMIN_DONO_SENHA = os.getenv("ADMIN_DONO_SENHA")

ALLOWED_ADMIN_EMAILS = {
    (ADMIN_ANALISTA_EMAIL or "").lower(),
    (ADMIN_DONO_EMAIL or "").lower(),
}


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
            conn.execute(
                text(
                    "ALTER TABLE usuarios ADD COLUMN must_change_password BOOLEAN DEFAULT 0"
                )
            )


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token invalido"
        ) from exc

    usuario = dbase.query(models.Usuario).filter(
        models.Usuario.id == user_id
    ).first()

    if not usuario or not usuario.ativo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="usuario nao autorizado"
        )

    return usuario


def usuario_operacional(usuario: models.Usuario = Depends(usuario_atual)):

    if getattr(usuario, "must_change_password", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="troca de senha obrigatoria"
        )

    return usuario


def admin_atual(usuario: models.Usuario = Depends(usuario_operacional)):

    if not admin_habilitado(usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="acesso restrito a administradores"
        )

    return usuario


def garantir_admins_iniciais():

    if not ADMIN_ANALISTA_EMAIL or not ADMIN_ANALISTA_SENHA:
        return

    if not ADMIN_DONO_EMAIL or not ADMIN_DONO_SENHA:
        return

    dbase = SessionLocal()

    try:

        seeds = [
            ("Analista do Software", ADMIN_ANALISTA_EMAIL, ADMIN_ANALISTA_SENHA),
            ("Dono da Empresa", ADMIN_DONO_EMAIL, ADMIN_DONO_SENHA),
        ]

        for nome, email, senha in seeds:

            usuario = dbase.query(models.Usuario).filter(
                models.Usuario.email == email
            ).first()

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
def login(
    email: str = Form(...),
    senha: str = Form(...),
    dbase: Session = Depends(db),
):

    user = dbase.query(models.Usuario).filter(
        models.Usuario.email == email
    ).first()

    if not user or not user.ativo or not verify(senha, user.senha_hash):
        raise HTTPException(
            status_code=401,
            detail="login invalido"
        )

    token = create_token({"user": user.id})

    return {
        "token": token,
        "usuario": {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "role": user.role,
            "admin_autorizado": admin_habilitado(user),
            "must_change_password": bool(
                getattr(user, "must_change_password", False)
            ),
        },
    }


@app.get("/dashboard")
def dashboard(
    dias: int = Query(30, ge=1),
    dbase: Session = Depends(db),
    _: models.Usuario = Depends(usuario_operacional),
):

    data_inicial = datetime.utcnow() - timedelta(days=dias)

    total_produtos = dbase.query(models.Produto).count()

    total_mov = dbase.query(models.Movimentacao).filter(
        models.Movimentacao.created_at >= data_inicial
    ).count()

    mov_entradas = dbase.query(models.Movimentacao).filter(
        models.Movimentacao.created_at >= data_inicial,
        models.Movimentacao.tipo == "ENTRADA"
    ).count()

    mov_saidas = dbase.query(models.Movimentacao).filter(
        models.Movimentacao.created_at >= data_inicial,
        models.Movimentacao.tipo == "SAIDA"
    ).count()

    return {
        "total_produtos": total_produtos,
        "total_movimentacoes": total_mov,
        "dias": dias,
        "grafico": {
            "labels": ["Entradas", "Saidas"],
            "valores": [mov_entradas, mov_saidas]
        }
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

            alertas.append({
                "produto_id": p.id,
                "nome": p.nome,
                "sku": p.sku,
                "saldo": saldo,
                "nivel": nivel,
                "mensagem": f"{p.nome} (SKU: {p.sku}) esta com {saldo} unidades."
            })

    alertas = sorted(alertas, key=lambda a: a["saldo"])

    criticos = len([a for a in alertas if a["nivel"] == "CRITICO"])

    return {
        "total": len(alertas),
        "criticos": criticos,
        "notificacoes": alertas
    }


@app.get("/exportar")
def exportar(
    dbase: Session = Depends(db),
    _: models.Usuario = Depends(usuario_operacional),
):

    wb = openpyxl.Workbook()

    ws = wb.active

    ws.append(["Produto", "SKU"])

    produtos = dbase.query(models.Produto).all()

    for p in produtos:
        ws.append([p.nome, p.sku])

    path = "estoque_export.xlsx"

    wb.save(path)

    return FileResponse(path, filename="estoque.xlsx")


# SERVIR FRONTEND
import os
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")