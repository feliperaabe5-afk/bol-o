#!/usr/bin/env python3
"""
🏆 Bolão App v3 — Com banco de dados persistente (SQLite local / PostgreSQL em produção)
Rode: python app.py  →  http://localhost:5000
"""

import os
import random
import string
from datetime import datetime

from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# ── Configuração do banco ──────────────────────────────────────────────────────
# Em produção (Render, Railway, etc.) a variável DATABASE_URL é fornecida
# automaticamente quando você anexa um banco PostgreSQL ao serviço.
# Localmente, sem essa variável, cai automaticamente para SQLite (bolao.db).
database_url = os.environ.get("DATABASE_URL", "")
if database_url.startswith("postgres://"):
    # Render/Heroku usam "postgres://"; SQLAlchemy + psycopg3 exigem "postgresql+psycopg://"
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

if not database_url:
    database_url = "sqlite:///" + os.path.join(os.path.dirname(__file__), "bolao.db")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ══ MODELOS ═══════════════════════════════════════════════════════════════════

class Bolao(db.Model):
    __tablename__ = "boloes"
    codigo = db.Column(db.String(6), primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.Text, default="")
    criado_em = db.Column(db.String(20))
    encerrado = db.Column(db.Boolean, default=False)

    participantes = db.relationship("Participante", backref="bolao", cascade="all, delete-orphan")
    partidas = db.relationship("Partida", backref="bolao", cascade="all, delete-orphan")


class Participante(db.Model):
    __tablename__ = "participantes"
    id = db.Column(db.Integer, primary_key=True)
    bolao_codigo = db.Column(db.String(6), db.ForeignKey("boloes.codigo"), nullable=False)
    nome = db.Column(db.String(80), nullable=False)

    __table_args__ = (db.UniqueConstraint("bolao_codigo", "nome", name="uq_participante_bolao"),)


class Partida(db.Model):
    __tablename__ = "partidas"
    id = db.Column(db.String(8), primary_key=True)
    bolao_codigo = db.Column(db.String(6), db.ForeignKey("boloes.codigo"), nullable=False)
    casa = db.Column(db.String(80), nullable=False)
    visitante = db.Column(db.String(80), nullable=False)
    data = db.Column(db.String(40), default="")
    pontos = db.Column(db.Integer, default=1)
    encerrada = db.Column(db.Boolean, default=False)
    resultado = db.Column(db.String(12))  # "casa" | "visitante" | "empate"

    palpites = db.relationship("Palpite", backref="partida", cascade="all, delete-orphan")


class Palpite(db.Model):
    __tablename__ = "palpites"
    id = db.Column(db.Integer, primary_key=True)
    partida_id = db.Column(db.String(8), db.ForeignKey("partidas.id"), nullable=False)
    nome = db.Column(db.String(80), nullable=False)
    palpite = db.Column(db.String(12), nullable=False)  # "casa" | "visitante" | "empate"
    data = db.Column(db.String(20))

    __table_args__ = (db.UniqueConstraint("partida_id", "nome", name="uq_palpite_partida"),)


with app.app_context():
    db.create_all()


# ── Helpers ───────────────────────────────────────────────────────────────────
def gen_code():
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        c = "".join(random.choices(chars, k=6))
        if not Bolao.query.get(c):
            return c

def gen_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

def now_str():
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def calcular_ranking(bolao: Bolao):
    scores = {}
    for p in bolao.participantes:
        scores[p.nome] = {"nome": p.nome, "pontos": 0, "acertos": 0, "palpites": 0}

    for partida in bolao.partidas:
        if not partida.encerrada:
            continue
        for pal in partida.palpites:
            if pal.nome not in scores:
                scores[pal.nome] = {"nome": pal.nome, "pontos": 0, "acertos": 0, "palpites": 0}
            scores[pal.nome]["palpites"] += 1
            if pal.palpite == partida.resultado:
                scores[pal.nome]["pontos"] += partida.pontos
                scores[pal.nome]["acertos"] += 1

    ranking = sorted(scores.values(), key=lambda x: (-x["pontos"], -x["acertos"], x["nome"]))
    for i, r in enumerate(ranking):
        r["posicao"] = i + 1
    return ranking


# ── Página ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ══ API ═══════════════════════════════════════════════════════════════════════

# ── Bolões ────────────────────────────────────────────────────────────────────
@app.route("/api/boloes", methods=["GET"])
def listar_boloes():
    result = []
    for b in Bolao.query.all():
        n_enc = sum(1 for p in b.partidas if p.encerrada)
        result.append({
            "codigo": b.codigo,
            "nome": b.nome,
            "descricao": b.descricao or "",
            "criado_em": b.criado_em or "",
            "total_participantes": len(b.participantes),
            "total_partidas": len(b.partidas),
            "partidas_encerradas": n_enc,
            "encerrado": b.encerrado,
        })
    result.sort(key=lambda x: x["encerrado"])
    return jsonify(result)


@app.route("/api/boloes", methods=["POST"])
def criar_bolao():
    data = request.get_json(force=True)
    nome = (data.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome é obrigatório."}), 400

    codigo = gen_code()
    b = Bolao(
        codigo=codigo,
        nome=nome,
        descricao=(data.get("descricao") or "").strip(),
        criado_em=now_str(),
        encerrado=False,
    )
    db.session.add(b)
    db.session.commit()
    return jsonify({"codigo": codigo}), 201


@app.route("/api/boloes/<cod>", methods=["GET"])
def ver_bolao(cod):
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Bolão não encontrado."}), 404
    n_enc = sum(1 for p in b.partidas if p.encerrada)
    return jsonify({
        "codigo": b.codigo,
        "nome": b.nome,
        "descricao": b.descricao or "",
        "criado_em": b.criado_em or "",
        "participantes": [p.nome for p in b.participantes],
        "total_participantes": len(b.participantes),
        "total_partidas": len(b.partidas),
        "partidas_encerradas": n_enc,
        "encerrado": b.encerrado,
    })


@app.route("/api/boloes/<cod>", methods=["DELETE"])
def deletar_bolao(cod):
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Não encontrado."}), 404
    db.session.delete(b)
    db.session.commit()
    return jsonify({"ok": True})


# ── Participantes ─────────────────────────────────────────────────────────────
@app.route("/api/boloes/<cod>/entrar", methods=["POST"])
def entrar(cod):
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Bolão não encontrado."}), 404
    if b.encerrado:
        return jsonify({"erro": "Bolão encerrado."}), 400

    data = request.get_json(force=True)
    nome = (data.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome é obrigatório."}), 400

    existe = Participante.query.filter_by(bolao_codigo=b.codigo, nome=nome).first()
    if existe:
        return jsonify({"erro": f'"{nome}" já está no bolão.'}), 400

    db.session.add(Participante(bolao_codigo=b.codigo, nome=nome))
    db.session.commit()
    return jsonify({"ok": True, "nome": nome}), 201


# ── Partidas ──────────────────────────────────────────────────────────────────
@app.route("/api/boloes/<cod>/partidas", methods=["GET"])
def listar_partidas(cod):
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Não encontrado."}), 404

    nome_participante = request.args.get("participante", "")
    partidas = []
    for p in b.partidas:
        meu_palpite = None
        if nome_participante:
            pal = Palpite.query.filter_by(partida_id=p.id, nome=nome_participante).first()
            if pal:
                meu_palpite = pal.palpite
        partidas.append({
            "id": p.id,
            "casa": p.casa,
            "visitante": p.visitante,
            "data": p.data or "",
            "pontos": p.pontos,
            "encerrada": p.encerrada,
            "resultado": p.resultado,
            "total_palpites": len(p.palpites),
            "meu_palpite": meu_palpite,
        })
    partidas.sort(key=lambda x: (x["encerrada"], x["data"] or ""))
    return jsonify(partidas)


@app.route("/api/boloes/<cod>/partidas", methods=["POST"])
def criar_partida(cod):
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Não encontrado."}), 404

    data = request.get_json(force=True)
    casa = (data.get("casa") or "").strip()
    visitante = (data.get("visitante") or "").strip()
    if not casa or not visitante:
        return jsonify({"erro": "Times são obrigatórios."}), 400
    try:
        pontos = int(data.get("pontos", 1))
        if pontos < 1:
            pontos = 1
    except (TypeError, ValueError):
        pontos = 1

    pid = gen_id()
    p = Partida(
        id=pid,
        bolao_codigo=b.codigo,
        casa=casa,
        visitante=visitante,
        data=(data.get("data") or "").strip(),
        pontos=pontos,
        encerrada=False,
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({"id": pid}), 201


@app.route("/api/boloes/<cod>/partidas/<pid>", methods=["DELETE"])
def deletar_partida(cod, pid):
    p = Partida.query.filter_by(id=pid, bolao_codigo=cod.upper()).first()
    if not p:
        return jsonify({"erro": "Não encontrado."}), 404
    db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/boloes/<cod>/partidas/<pid>/resultado", methods=["POST"])
def definir_resultado(cod, pid):
    p = Partida.query.filter_by(id=pid, bolao_codigo=cod.upper()).first()
    if not p:
        return jsonify({"erro": "Não encontrado."}), 404
    data = request.get_json(force=True)
    resultado = data.get("resultado")
    if resultado not in ("casa", "visitante", "empate"):
        return jsonify({"erro": "Resultado deve ser 'casa', 'visitante' ou 'empate'."}), 400
    p.resultado = resultado
    p.encerrada = True
    db.session.commit()
    return jsonify({"ok": True})


# ── Palpites ──────────────────────────────────────────────────────────────────
@app.route("/api/boloes/<cod>/partidas/<pid>/palpite", methods=["POST"])
def registrar_palpite(cod, pid):
    p = Partida.query.filter_by(id=pid, bolao_codigo=cod.upper()).first()
    if not p:
        return jsonify({"erro": "Não encontrado."}), 404
    if p.encerrada:
        return jsonify({"erro": "Partida já encerrada."}), 400

    data = request.get_json(force=True)
    nome = (data.get("nome") or "").strip()
    palpite = data.get("palpite")
    if not nome:
        return jsonify({"erro": "Nome é obrigatório."}), 400
    if palpite not in ("casa", "visitante", "empate"):
        return jsonify({"erro": "Palpite inválido."}), 400

    participante = Participante.query.filter_by(bolao_codigo=cod.upper(), nome=nome).first()
    if not participante:
        return jsonify({"erro": f'"{nome}" não está no bolão. Entre primeiro.'}), 400

    existente = Palpite.query.filter_by(partida_id=pid, nome=nome).first()
    if existente:
        existente.palpite = palpite
        existente.data = now_str()
    else:
        db.session.add(Palpite(partida_id=pid, nome=nome, palpite=palpite, data=now_str()))
    db.session.commit()
    return jsonify({"ok": True}), 201


# ── Ranking ───────────────────────────────────────────────────────────────────
@app.route("/api/boloes/<cod>/ranking", methods=["GET"])
def ranking(cod):
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Não encontrado."}), 404
    return jsonify(calcular_ranking(b))


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"🏆  Bolão App rodando na porta {port}")
    print(f"📦  Banco de dados: {'PostgreSQL (produção)' if 'postgresql' in database_url else 'SQLite (local: bolao.db)'}")
    app.run(debug=debug, host="0.0.0.0", port=port)
