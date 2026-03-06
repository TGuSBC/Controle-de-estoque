
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from .database import Base

class Produto(Base):
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    sku = Column(String, unique=True, index=True)
    codigo_barras = Column(String)
    descricao = Column(String)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Corredor(Base):
    __tablename__ = "corredores"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True)
    descricao = Column(String)
    ativo = Column(Boolean, default=True)

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    email = Column(String, unique=True)
    senha_hash = Column(String)
    role = Column(String)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Movimentacao(Base):
    __tablename__ = "movimentacoes"
    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"))
    corredor_id = Column(Integer, ForeignKey("corredores.id"))
    tipo = Column(String)
    quantidade = Column(Integer)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    observacao = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
