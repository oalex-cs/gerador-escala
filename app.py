#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Backend Flask para a interface web de geração de escalas de culto.
Reutiliza a lógica do escala_culto.py como módulo.
"""

import json
import csv
import io
import os
import threading
from datetime import datetime
from collections import defaultdict
from typing import List, Tuple, Dict, Set

from dotenv import load_dotenv
load_dotenv()

USE_SUPABASE = False
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client, Client
        supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        USE_SUPABASE = True
        print("[OK] Supabase conectado!")
    except Exception as e:
        print(f"[ERRO] Erro ao conectar no Supabase: {e}")


import pandas as pd
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side
)
from openpyxl.utils import get_column_letter

from flask import Flask, jsonify, request, render_template, Response

app = Flask(__name__)

# --------------------------------------------------------------------------
# Arquivo de dados (JSON simples, sem banco de dados)
# --------------------------------------------------------------------------
DATA_FILE = os.path.join(os.path.dirname(__file__), "membros.json")
db_lock = threading.Lock()

def load_data() -> dict:
    """Carrega os dados da nuvem ou do arquivo local."""
    if USE_SUPABASE:
        try:
            res = supabase_client.table('membros').select('*').execute()
            # res.data is a list of dicts: [{"nome": "...", "disponibilidades": [...]}]
            return {"membros": res.data}
        except Exception as e:
            print(f"Erro ao ler do Supabase: {e}")
            return {"membros": []}

    with db_lock:
        if not os.path.exists(DATA_FILE):
            return {"membros": []}
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_data(data: dict):
    """Salva os dados no arquivo JSON de forma segura com lock."""
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Lógica do algoritmo (copiada de escala_culto.py para desacoplamento)
# --------------------------------------------------------------------------
def build_availability_map(raw: List[Tuple[str, List[str]]]) -> Dict[datetime, Set[str]]:
    avail: Dict[datetime, Set[str]] = defaultdict(set)
    for nome, datas in raw:
        for d_str in datas:
            d = datetime.strptime(d_str, "%Y-%m-%d")
            if d.weekday() != 5:
                raise ValueError(f"{d.date()} não é sábado.")
            avail[d].add(nome)
    return dict(sorted(avail.items()))


MEMBROS_POR_SABADO = 2  # ← altere aqui se quiser mais ou menos


def gerar_escala(disponibilidade: Dict[datetime, Set[str]]) -> List[Tuple[datetime, List[str]]]:
    """
    Algoritmo guloso — seleciona MEMBROS_POR_SABADO membros por sábado.
    Regras:
      • Nenhum membro serve em sábados consecutivos.
      • Preferência para quem já serviu menos vezes (balancear carga).
    """
    escala: List[Tuple[datetime, List[str]]] = []
    contagem: Dict[str, int] = defaultdict(int)
    ultimo_servico: Dict[str, datetime] = {}
    datas = list(disponibilidade.keys())

    for i, data_atual in enumerate(datas):
        # Candidatos disponíveis nesta data
        candidatos = list(disponibilidade[data_atual].copy())

        # Remove quem serviu no sábado imediatamente anterior
        if i > 0:
            data_anterior = datas[i - 1]
            candidatos = [
                n for n in candidatos
                if ultimo_servico.get(n) != data_anterior
            ]

        # Ordena por menor contagem de serviços (balanceamento)
        candidatos.sort(key=lambda n: contagem[n])

        # Seleciona até MEMBROS_POR_SABADO membros
        escolhidos = candidatos[:MEMBROS_POR_SABADO]

        escala.append((data_atual, escolhidos))
        for nome in escolhidos:
            contagem[nome] += 1
            ultimo_servico[nome] = data_atual

    return escala


# --------------------------------------------------------------------------
# Rotas
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/membro")
def membro_form():
    return render_template("membro.html")


@app.route("/api/membros", methods=["GET"])
def get_membros():
    data = load_data()
    return jsonify(data["membros"])


@app.route("/api/membros", methods=["POST"])
def add_membro():
    body = request.get_json()
    nome = (body or {}).get("nome", "").strip()[:50]  # Limite 50 chars
    if not nome:
        return jsonify({"erro": "Nome inválido."}), 400

    if USE_SUPABASE:
        try:
            # tenta inserir. Vai falhar se a chave primaria "nome" ja existir
            supabase_client.table('membros').insert({"nome": nome, "disponibilidades": []}).execute()
            return jsonify({"ok": True, "nome": nome}), 201
        except Exception as e:
            return jsonify({"erro": "Membro já cadastrado ou erro no banco."}), 409
            
    data = load_data()
    # Verifica duplicata (case-insensitive)
    nomes_existentes = [m["nome"].lower() for m in data["membros"]]
    if nome.lower() in nomes_existentes:
        return jsonify({"erro": "Membro já cadastrado."}), 409

    data["membros"].append({"nome": nome, "disponibilidades": []})
    save_data(data)
    return jsonify({"ok": True, "nome": nome}), 201


@app.route("/api/membros/<nome>", methods=["DELETE"])
def delete_membro(nome: str):
    if USE_SUPABASE:
        try:
            supabase_client.table('membros').delete().eq('nome', nome).execute()
            return jsonify({"ok": True})
        except Exception:
            return jsonify({"erro": "Erro ao remover membro na nuvem."}), 500

    data = load_data()
    antes = len(data["membros"])
    data["membros"] = [m for m in data["membros"] if m["nome"] != nome]
    if len(data["membros"]) == antes:
        return jsonify({"erro": "Membro não encontrado."}), 404
    save_data(data)
    return jsonify({"ok": True})


@app.route("/api/membros/<nome>/disponibilidades", methods=["PUT"])
def update_disponibilidades(nome: str):
    body = request.get_json()
    datas = (body or {}).get("disponibilidades", [])

    # Valida que todas são sábados
    for d_str in datas:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d")
            if d.weekday() != 5:
                return jsonify({"erro": f"{d_str} não é sábado."}), 400
        except ValueError:
            return jsonify({"erro": f"Data inválida: {d_str}"}), 400

    if USE_SUPABASE:
        try:
            supabase_client.table('membros').update({"disponibilidades": datas}).eq('nome', nome).execute()
            return jsonify({"ok": True})
        except Exception:
            return jsonify({"erro": "Erro na nuvem."}), 500

    data = load_data()
    for m in data["membros"]:
        if m["nome"] == nome:
            m["disponibilidades"] = datas
            save_data(data)
            return jsonify({"ok": True})

    return jsonify({"erro": "Membro não encontrado."}), 404


@app.route("/api/membro/submit", methods=["POST"])
def submit_membro_form():
    body = request.get_json()
    nome = (body or {}).get("nome", "").strip()[:50]  # Limite 50 chars
    datas = (body or {}).get("disponibilidades", [])

    if not nome:
        return jsonify({"erro": "Nome inválido."}), 400

    # Valida que todas são sábados
    for d_str in datas:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d")
            if d.weekday() != 5:
                return jsonify({"erro": f"{d_str} não é sábado."}), 400
        except ValueError:
            return jsonify({"erro": f"Data inválida: {d_str}"}), 400

    if USE_SUPABASE:
        try:
            supabase_client.table('membros').upsert({"nome": nome, "disponibilidades": datas}).execute()
            return jsonify({"ok": True}), 200
        except Exception as e:
            return jsonify({"erro": f"Erro na nuvem: {e}"}), 500

    data = load_data()
    
    # Procura se o membro já existe
    membro_existente = next((m for m in data["membros"] if m["nome"].lower() == nome.lower()), None)
    
    if membro_existente:
        membro_existente["disponibilidades"] = datas
    else:
        # Cria novo membro
        data["membros"].append({
            "nome": nome,
            "disponibilidades": datas
        })
        
    save_data(data)
    return jsonify({"ok": True}), 200


@app.route("/api/gerar-escala", methods=["POST"])
def api_gerar_escala():
    data = load_data()
    raw = [(m["nome"], m["disponibilidades"]) for m in data["membros"]]

    if not any(datas for _, datas in raw):
        return jsonify({"erro": "Nenhuma disponibilidade cadastrada."}), 400

    try:
        disponibilidade = build_availability_map(raw)
        escala = gerar_escala(disponibilidade)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    resultado = [
        {"data": dt.strftime("%Y-%m-%d"), "membros": membros}
        for dt, membros in escala
    ]
    return jsonify(resultado)


@app.route("/api/exportar-csv", methods=["POST"])
def exportar_csv():
    body = request.get_json()
    escala = body or []

    output = io.StringIO()
    writer = csv.writer(output)
    # Cabeçalho dinâmico baseado na quantidade máxima de membros por linha
    max_membros = max((len(row.get("membros", [])) for row in escala), default=MEMBROS_POR_SABADO)
    header = ["data"] + [f"membro_{i+1}" for i in range(max_membros)]
    writer.writerow(header)
    for row in escala:
        membros_row = row.get("membros", [])
        # Preenche com vazio caso tenha menos que o máximo
        padded = membros_row + [""] * (max_membros - len(membros_row))
        writer.writerow([row["data"]] + padded)

    csv_content = output.getvalue()
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=escala_culto.csv"},
    )


@app.route("/api/exportar-xlsx", methods=["POST"])
def exportar_xlsx():
    """Gera um arquivo Excel (.xlsx) formatado com pandas + openpyxl."""
    body = request.get_json()
    escala = body or []

    if not escala:
        return jsonify({"erro": "Escala vazia."}), 400

    # ------------------------------------------------------------------
    # 1. Monta o DataFrame principal
    # ------------------------------------------------------------------
    dias_semana = {
        0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta",
        4: "Sexta", 5: "Sábado", 6: "Domingo",
    }
    rows = []
    todos_membros: List[str] = []  # para o resumo
    for row in escala:
        dt = datetime.strptime(row["data"], "%Y-%m-%d")
        membros_linha = row.get("membros", [])
        tem_membro = len(membros_linha) > 0

        row_dict: dict = {
            "Data": dt.strftime("%d/%m/%Y"),
            "Dia da Semana": dias_semana[dt.weekday()],
        }
        for idx in range(MEMBROS_POR_SABADO):
            col = f"Membro {idx + 1}"
            val = membros_linha[idx] if idx < len(membros_linha) else "---"
            row_dict[col] = val

        situacao_ok = tem_membro and any(m for m in membros_linha)
        row_dict["Situação"] = "✓ Escalado" if situacao_ok else "⚠ Sem disponível"
        rows.append(row_dict)
        todos_membros.extend(membros_linha)

    df_escala = pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # 2. Monta o DataFrame de resumo (contagem individual por membro)
    # ------------------------------------------------------------------
    from collections import Counter
    contagem_dict = Counter(todos_membros)
    contagem = (
        pd.DataFrame(contagem_dict.items(), columns=["Membro", "Qtd. de Serviços"])
        .sort_values("Qtd. de Serviços", ascending=False)
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------------
    # 3. Escreve para buffer com ExcelWriter
    # ------------------------------------------------------------------
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_escala.to_excel(writer, sheet_name="Escala", index=False, startrow=2)
        contagem.to_excel(writer, sheet_name="Resumo", index=False, startrow=2)

        _formatar_sheet_escala(writer.sheets["Escala"], df_escala)
        _formatar_sheet_resumo(writer.sheets["Resumo"], contagem)

    output.seek(0)
    return Response(
        output.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=escala_culto.xlsx"},
    )


# ------------------------------------------------------------------
# Helpers de formatação Excel
# ------------------------------------------------------------------
def _cor(hex_str: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_str.lstrip("#"))


def _borda_fina() -> Border:
    side = Side(style="thin", color="CCCCCC")
    return Border(left=side, right=side, top=side, bottom=side)


def _formatar_sheet_escala(ws, df: pd.DataFrame):
    # Paleta
    COR_TITULO    = "4F46E5"   # indigo
    COR_HEADER    = "6D28D9"   # roxo
    COR_PAR       = "F5F3FF"   # lavanda claro
    COR_IMPAR     = "FFFFFF"   # branco
    COR_SEM_DISP  = "FEE2E2"   # vermelho claro
    COR_TEXTO_HD  = "FFFFFF"

    # Título mesclado — largura dinâmica baseada no nº de colunas
    num_cols = len(df.columns)
    last_col = get_column_letter(num_cols)
    ws.merge_cells(f"A1:{last_col}1")
    titulo = ws["A1"]
    titulo.value = "📋  Escala de Culto"
    titulo.font = Font(bold=True, size=14, color=COR_TEXTO_HD)
    titulo.fill = _cor(COR_TITULO)
    titulo.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    # Cabeçalhos (linha 3 = startrow=2 + 1)
    header_row = 3
    for col_idx, col_name in enumerate(df.columns, start=1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.value = col_name
        cell.font = Font(bold=True, color=COR_TEXTO_HD, size=11)
        cell.fill = _cor(COR_HEADER)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _borda_fina()
    ws.row_dimensions[header_row].height = 22

    # Detecta colunas de membros (ex: "Membro 1", "Membro 2", ...)
    membro_cols = [c for c in df.columns if c.startswith("Membro")]
    situacao_col_idx = list(df.columns).index("Situação") + 1  # 1-based

    # Dados (a partir da linha 4)
    for row_idx, row in df.iterrows():
        excel_row = row_idx + header_row + 1
        # Sem disponível se todos os membros da linha forem "---" ou vazios
        sem_membro = all(row.get(c, "---") in ("", "---") for c in membro_cols)
        bg = COR_SEM_DISP if sem_membro else (COR_PAR if row_idx % 2 == 0 else COR_IMPAR)
        for col_idx, value in enumerate(row, start=1):
            col_name = df.columns[col_idx - 1]
            cell = ws.cell(row=excel_row, column=col_idx, value=value)
            cell.fill = _cor(bg)
            cell.border = _borda_fina()
            cell.alignment = Alignment(horizontal="center", vertical="center")
            # Membro vazio/--- em vermelho
            if col_name in membro_cols and value in ("", "---"):
                cell.font = Font(color="DC2626", bold=True)
            # Situação ✓ em verde
            if col_idx == situacao_col_idx and not sem_membro:
                cell.font = Font(color="059669", bold=True)
        ws.row_dimensions[excel_row].height = 20

    # Larguras dinâmicas
    col_widths = {"A": 16, "B": 16}  # Data, Dia da Semana
    for i, mc in enumerate(membro_cols):
        col_widths[get_column_letter(3 + i)] = 22
    col_widths[get_column_letter(situacao_col_idx)] = 18
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    # Congelar cabeçalhos
    ws.freeze_panes = "A4"


def _formatar_sheet_resumo(ws, df: pd.DataFrame):
    COR_TITULO  = "4F46E5"
    COR_HEADER  = "6D28D9"
    COR_TOP     = "FEF9C3"   # amarelo top-1
    COR_PAR     = "F5F3FF"
    COR_IMPAR   = "FFFFFF"
    COR_TEXTO_HD = "FFFFFF"

    # Título
    ws.merge_cells("A1:B1")
    titulo = ws["A1"]
    titulo.value = "📊  Resumo de Serviços"
    titulo.font = Font(bold=True, size=14, color=COR_TEXTO_HD)
    titulo.fill = _cor(COR_TITULO)
    titulo.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    # Cabeçalhos
    header_row = 3
    for col_idx, col_name in enumerate(df.columns, start=1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.value = col_name
        cell.font = Font(bold=True, color=COR_TEXTO_HD, size=11)
        cell.fill = _cor(COR_HEADER)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _borda_fina()
    ws.row_dimensions[header_row].height = 22

    # Dados
    for row_idx, row in df.iterrows():
        excel_row = row_idx + header_row + 1
        # destaque para o 1º colocado
        bg = COR_TOP if row_idx == 0 else (COR_PAR if row_idx % 2 == 0 else COR_IMPAR)
        for col_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=excel_row, column=col_idx, value=value)
            cell.fill = _cor(bg)
            cell.border = _borda_fina()
            cell.alignment = Alignment(horizontal="center", vertical="center")
            if row_idx == 0:
                cell.font = Font(bold=True, color="92400E")  # marrom dourado
        ws.row_dimensions[excel_row].height = 20

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 18
    ws.freeze_panes = "A4"


if __name__ == "__main__":
    app.run(debug=True, port=5000)
