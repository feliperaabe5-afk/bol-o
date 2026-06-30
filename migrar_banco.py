#!/usr/bin/env python3
"""
Script de migração: adiciona ao bolao.db as colunas novas usadas pela
versão atual do app (sistema de login), sem apagar nenhum dado existente.

Como usar:
    python migrar_banco.py

Rode este script UMA VEZ, na mesma pasta onde está o app.py e o bolao.db.
É seguro rodar mais de uma vez — ele só adiciona colunas que ainda não existem.
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "bolao.db")

# (tabela, coluna, definição SQL da coluna)
COLUNAS_NOVAS = [
    ("boloes",       "criador_id", "INTEGER"),
    ("participantes", "user_id",   "INTEGER"),
]


def coluna_existe(cur, tabela, coluna):
    cur.execute(f"PRAGMA table_info({tabela})")
    colunas = [row[1] for row in cur.fetchall()]
    return coluna in colunas


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Não encontrei o arquivo {DB_PATH}.")
        print("   Coloque este script na mesma pasta do bolao.db (junto com o app.py).")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    alguma_alteracao = False

    for tabela, coluna, tipo in COLUNAS_NOVAS:
        # confere se a tabela existe antes de mexer nela
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
        )
        if not cur.fetchone():
            print(f"⚠️  Tabela '{tabela}' não existe ainda, pulando.")
            continue

        if coluna_existe(cur, tabela, coluna):
            print(f"✅ {tabela}.{coluna} já existe, nada a fazer.")
            continue

        print(f"➕ Adicionando coluna {coluna} ({tipo}) na tabela {tabela}...")
        cur.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        alguma_alteracao = True

    if alguma_alteracao:
        conn.commit()
        print("\n🎉 Migração concluída com sucesso! Seus dados foram mantidos.")
    else:
        print("\n✅ Banco já estava atualizado, nenhuma alteração necessária.")

    conn.close()


if __name__ == "__main__":
    main()
