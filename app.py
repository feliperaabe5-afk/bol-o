#!/usr/bin/env python3
"""
🏆 Bolão App v4 — Com login/cadastro de usuários e administração de participantes
Rode: python app.py  →  http://localhost:5000
"""

import os
import random
import string
from datetime import datetime

from flask import Flask, jsonify, request, render_template, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao-" + str(random.random()))

# ── Configuração do banco ──────────────────────────────────────────────────────
database_url = os.environ.get("DATABASE_URL", "")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

if not database_url:
    database_url = "sqlite:///" + os.path.join(os.path.dirname(__file__), "bolao.db")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db = SQLAlchemy(app)


# ══ MODELOS ═══════════════════════════════════════════════════════════════════

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.String(20))


class Bolao(db.Model):
    __tablename__ = "boloes"
    codigo = db.Column(db.String(6), primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.Text, default="")
    criado_em = db.Column(db.String(20))
    encerrado = db.Column(db.Boolean, default=False)
    criador_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    participantes = db.relationship("Participante", backref="bolao", cascade="all, delete-orphan")
    partidas = db.relationship("Partida", backref="bolao", cascade="all, delete-orphan")


class Participante(db.Model):
    __tablename__ = "participantes"
    id = db.Column(db.Integer, primary_key=True)
    bolao_codigo = db.Column(db.String(6), db.ForeignKey("boloes.codigo"), nullable=False)
    nome = db.Column(db.String(80), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

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
    resultado = db.Column(db.String(12))

    palpites = db.relationship("Palpite", backref="partida", cascade="all, delete-orphan")


class Palpite(db.Model):
    __tablename__ = "palpites"
    id = db.Column(db.Integer, primary_key=True)
    partida_id = db.Column(db.String(8), db.ForeignKey("partidas.id"), nullable=False)
    nome = db.Column(db.String(80), nullable=False)
    palpite = db.Column(db.String(12), nullable=False)
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

def usuario_atual():
    """Retorna o User logado na sessão, ou None."""
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)

def login_obrigatorio(f):
    """Decorator: exige sessão ativa."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"erro": "Faça login para continuar."}), 401
        return f(*args, **kwargs)
    return wrapper


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


# ══ AUTENTICAÇÃO ══════════════════════════════════════════════════════════════

@app.route("/api/cadastrar", methods=["POST"])
def cadastrar():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    senha = data.get("senha") or ""

    if len(username) < 3:
        return jsonify({"erro": "Usuário deve ter pelo menos 3 caracteres."}), 400
    if len(senha) < 4:
        return jsonify({"erro": "Senha deve ter pelo menos 4 caracteres."}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"erro": "Esse usuário já existe."}), 400

    u = User(
        username=username,
        senha_hash=generate_password_hash(senha),
        criado_em=now_str(),
    )
    db.session.add(u)
    db.session.commit()

    session["user_id"] = u.id
    session["username"] = u.username
    return jsonify({"ok": True, "username": u.username}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    senha = data.get("senha") or ""

    u = User.query.filter_by(username=username).first()
    if not u or not check_password_hash(u.senha_hash, senha):
        return jsonify({"erro": "Usuário ou senha incorretos."}), 401

    session["user_id"] = u.id
    session["username"] = u.username
    return jsonify({"ok": True, "username": u.username})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/eu", methods=["GET"])
def eu():
    u = usuario_atual()
    if not u:
        return jsonify({"logado": False})
    return jsonify({"logado": True, "username": u.username})


# ══ API BOLÕES ════════════════════════════════════════════════════════════════

@app.route("/api/boloes", methods=["GET"])
@login_obrigatorio
def listar_boloes():
    u = usuario_atual()
    result = []
    for b in Bolao.query.filter_by(criador_id=u.id).all():
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
@login_obrigatorio
def criar_bolao():
    u = usuario_atual()
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
        criador_id=u.id,
    )
    db.session.add(b)
    db.session.commit()
    return jsonify({"codigo": codigo}), 201


@app.route("/api/boloes/<cod>", methods=["GET"])
def ver_bolao(cod):
    # Visível para qualquer usuário logado (necessário para participantes entrarem)
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Bolão não encontrado."}), 404
    n_enc = sum(1 for p in b.partidas if p.encerrada)
    u = usuario_atual()
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
        "sou_criador": bool(u and b.criador_id == u.id),
    })


@app.route("/api/boloes/<cod>", methods=["DELETE"])
@login_obrigatorio
def deletar_bolao(cod):
    u = usuario_atual()
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Não encontrado."}), 404
    if b.criador_id != u.id:
        return jsonify({"erro": "Apenas o criador pode deletar este bolão."}), 403
    db.session.delete(b)
    db.session.commit()
    return jsonify({"ok": True})


# ── Bolões em que o usuário participa ─────────────────────────────────────────
@app.route("/api/meus-boloes-participando", methods=["GET"])
@login_obrigatorio
def meus_boloes_participando():
    u = usuario_atual()
    participacoes = Participante.query.filter_by(user_id=u.id).all()
    result = []
    for part in participacoes:
        b = part.bolao
        if not b:
            continue
        n_enc = sum(1 for p in b.partidas if p.encerrada)
        result.append({
            "codigo": b.codigo,
            "nome": b.nome,
            "descricao": b.descricao or "",
            "total_participantes": len(b.participantes),
            "total_partidas": len(b.partidas),
            "partidas_encerradas": n_enc,
            "encerrado": b.encerrado,
            "meu_nome": part.nome,
        })
    result.sort(key=lambda x: x["encerrado"])
    return jsonify(result)



@app.route("/api/boloes/<cod>/entrar", methods=["POST"])
@login_obrigatorio
def entrar(cod):
    u = usuario_atual()
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Bolão não encontrado."}), 404
    if b.encerrado:
        return jsonify({"erro": "Bolão encerrado."}), 400

    # já está no bolão?
    ja_existe = Participante.query.filter_by(bolao_codigo=b.codigo, user_id=u.id).first()
    if ja_existe:
        return jsonify({"ok": True, "nome": ja_existe.nome, "ja_inscrito": True}), 200

    # nome = username da conta
    nome = u.username
    existe_nome = Participante.query.filter_by(bolao_codigo=b.codigo, nome=nome).first()
    if existe_nome:
        # nome ocupado por outro user — usa username + id curto
        nome = f"{u.username}_{u.id}"

    db.session.add(Participante(bolao_codigo=b.codigo, nome=nome, user_id=u.id))
    db.session.commit()
    return jsonify({"ok": True, "nome": nome, "ja_inscrito": False}), 201


@app.route("/api/boloes/<cod>/participantes/<nome>", methods=["DELETE"])
@login_obrigatorio
def deletar_participante(cod, nome):
    u = usuario_atual()
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Bolão não encontrado."}), 404
    if b.criador_id != u.id:
        return jsonify({"erro": "Apenas o criador do bolão pode remover participantes."}), 403

    participante = Participante.query.filter_by(bolao_codigo=b.codigo, nome=nome).first()
    if not participante:
        return jsonify({"erro": "Participante não encontrado."}), 404

    # remove também os palpites desse participante em todas as partidas do bolão
    partida_ids = [p.id for p in b.partidas]
    if partida_ids:
        Palpite.query.filter(
            Palpite.nome == nome,
            Palpite.partida_id.in_(partida_ids)
        ).delete(synchronize_session=False)

    db.session.delete(participante)
    db.session.commit()
    return jsonify({"ok": True})


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
@login_obrigatorio
def criar_partida(cod):
    u = usuario_atual()
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Não encontrado."}), 404
    if b.criador_id != u.id:
        return jsonify({"erro": "Apenas o criador pode adicionar partidas."}), 403

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
@login_obrigatorio
def deletar_partida(cod, pid):
    u = usuario_atual()
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Não encontrado."}), 404
    if b.criador_id != u.id:
        return jsonify({"erro": "Apenas o criador pode remover partidas."}), 403
    p = Partida.query.filter_by(id=pid, bolao_codigo=cod.upper()).first()
    if not p:
        return jsonify({"erro": "Não encontrado."}), 404
    db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/boloes/<cod>/partidas/<pid>/resultado", methods=["POST"])
@login_obrigatorio
def definir_resultado(cod, pid):
    u = usuario_atual()
    b = Bolao.query.get(cod.upper())
    if not b:
        return jsonify({"erro": "Não encontrado."}), 404
    if b.criador_id != u.id:
        return jsonify({"erro": "Apenas o criador pode definir resultados."}), 403
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
@login_obrigatorio
def registrar_palpite(cod, pid):
    u = usuario_atual()
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
    # só o dono da conta vinculada a esse "nome" pode palpitar por ele
    if participante.user_id and participante.user_id != u.id:
        return jsonify({"erro": "Este nome pertence a outro usuário."}), 403

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
