#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Backend Flask para a interface web de geração de escalas de culto.
Reutiliza a lógica do escala_culto.py como módulo.
"""

import json
import csv
import hmac
import io
import os
import re
import threading
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from collections import defaultdict
from functools import wraps
from typing import List, Tuple, Dict, Set, Optional

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

from flask import Flask, jsonify, request, render_template, Response, redirect, session, url_for

app = Flask(__name__)

SESSION_SECRET = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY")
if SESSION_SECRET:
    app.config["SECRET_KEY"] = SESSION_SECRET
else:
    app.config["SECRET_KEY"] = os.urandom(32)
    print("[AVISO] SECRET_KEY nao configurada; sessoes serao reiniciadas ao reiniciar o servidor.")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
if os.environ.get("FLASK_ENV") == "production" or os.environ.get("VERCEL"):
    app.config["SESSION_COOKIE_SECURE"] = True

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")


def is_admin_authenticated() -> bool:
    return session.get("admin_logged_in") is True


def safe_next_url(target: Optional[str]) -> str:
    if not target or not target.startswith("/") or target.startswith("//"):
        return url_for("index")
    return target


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if is_admin_authenticated():
            return view_func(*args, **kwargs)

        if request.path.startswith("/api/"):
            return jsonify({"erro": "Autenticacao necessaria."}), 401

        return redirect(url_for("login", next=request.full_path if request.query_string else request.path))

    return wrapper

# --------------------------------------------------------------------------
# Arquivo de dados (JSON simples, sem banco de dados)
# --------------------------------------------------------------------------
DATA_FILE = os.path.join(os.path.dirname(__file__), "membros.json")
db_lock = threading.Lock()

MESES_PT = [
    "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def clean_member_name(nome: object) -> str:
    return re.sub(r"\s+", " ", str(nome or "").strip())[:60]


def normalize_name_key(nome: object) -> str:
    clean = clean_member_name(nome).casefold()
    decomposed = unicodedata.normalize("NFD", clean)
    without_accents = "".join(
        ch for ch in decomposed
        if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def normalize_whatsapp_key(value: object) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]
    return digits


def validate_whatsapp_key(whatsapp_key: str):
    if len(whatsapp_key) not in (10, 11):
        raise ValueError("Informe um WhatsApp com DDD, usando 10 ou 11 digitos.")


def legacy_member_id(member: dict, index: int) -> str:
    source = member.get("nome_key") or clean_member_name(member.get("nome")) or f"membro-{index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"escala-culto:{source}:{index}"))


def normalize_member(member: dict, index: int = 0) -> dict:
    member = dict(member) if isinstance(member, dict) else {}
    nome = clean_member_name(member.get("nome"))
    whatsapp_key = normalize_whatsapp_key(
        member.get("whatsapp_key") or member.get("whatsapp") or member.get("telefone")
    )

    member["nome"] = nome
    member["nome_key"] = normalize_name_key(nome)
    member["whatsapp"] = whatsapp_key
    member["whatsapp_key"] = whatsapp_key
    member["disponibilidades"] = [
        str(d) for d in member.get("disponibilidades", [])
        if isinstance(d, str) and d
    ]
    if not member.get("id"):
        member["id"] = legacy_member_id(member, index)
    return member


def build_member(nome: str, whatsapp_key: str, disponibilidades: Optional[List[str]] = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "nome": clean_member_name(nome),
        "nome_key": normalize_name_key(nome),
        "whatsapp": whatsapp_key,
        "whatsapp_key": whatsapp_key,
        "disponibilidades": sorted(set(disponibilidades or [])),
    }


def find_member_by_whatsapp(members: List[dict], whatsapp_key: str) -> Optional[dict]:
    if not whatsapp_key:
        return None
    return next((m for m in members if m.get("whatsapp_key") == whatsapp_key), None)


def find_member_by_identifier(data: dict, identifier: str) -> Optional[dict]:
    identifier = str(identifier or "")
    whatsapp_key = normalize_whatsapp_key(identifier)
    name_key = normalize_name_key(identifier)

    for member in data["membros"]:
        if member.get("id") == identifier:
            return member

    if whatsapp_key:
        found = find_member_by_whatsapp(data["membros"], whatsapp_key)
        if found:
            return found

    exact_name_matches = [m for m in data["membros"] if m.get("nome") == identifier]
    if len(exact_name_matches) == 1:
        return exact_name_matches[0]

    normalized_name_matches = [m for m in data["membros"] if m.get("nome_key") == name_key]
    if len(normalized_name_matches) == 1:
        return normalized_name_matches[0]

    return None


def resolve_member_for_whatsapp(data: dict, nome: str, whatsapp_key: str, datas: Optional[List[str]] = None) -> Tuple[dict, bool]:
    found = find_member_by_whatsapp(data["membros"], whatsapp_key)
    if found:
        return found, False

    name_key = normalize_name_key(nome)
    legacy_matches = [
        m for m in data["membros"]
        if m.get("nome_key") == name_key and not m.get("whatsapp_key")
    ]
    if len(legacy_matches) == 1:
        legacy_matches[0]["whatsapp"] = whatsapp_key
        legacy_matches[0]["whatsapp_key"] = whatsapp_key
        return legacy_matches[0], False
    if len(legacy_matches) > 1:
        raise ValueError("Existe mais de um membro com esse nome sem WhatsApp. Atualize o cadastro no painel.")

    member = build_member(nome, whatsapp_key, datas)
    data["membros"].append(member)
    return member, True


def schedule_labels_for_members(members: List[dict]) -> Dict[str, str]:
    counts: Dict[str, int] = defaultdict(int)
    for member in members:
        counts[member.get("nome_key", "")] += 1

    labels: Dict[str, str] = {}
    for member in members:
        label = member.get("nome", "")
        if counts.get(member.get("nome_key", ""), 0) > 1:
            suffix = member.get("whatsapp_key", "")[-4:]
            if suffix:
                label = f"{label} ({suffix})"
        labels[member.get("id", label)] = label
    return labels


def normalize_data(data: Optional[dict]) -> dict:
    data = data if isinstance(data, dict) else {}
    data.setdefault("membros", [])
    data.setdefault("campanhas", [])
    data.setdefault("campanha_ativa_id", None)
    data.setdefault("escalas", [])
    data["membros"] = [
        normalize_member(member, index)
        for index, member in enumerate(data.get("membros", []))
        if isinstance(member, dict)
    ]
    return data


def load_local_data() -> dict:
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return normalize_data({})
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return normalize_data(json.load(f))


def save_local_data(data: dict):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(normalize_data(data), f, ensure_ascii=False, indent=2)


def load_data() -> dict:
    """Carrega os dados da nuvem ou do arquivo local."""
    data = load_local_data()
    if USE_SUPABASE:
        try:
            res = supabase_client.table('membros').select('*').execute()
            # res.data is a list of dicts: [{"nome": "...", "disponibilidades": [...]}]
            data["membros"] = res.data
            return normalize_data(data)
        except Exception as e:
            print(f"Erro ao ler do Supabase: {e}")
            data["membros"] = []
            return normalize_data(data)

    return data


def save_data(data: dict):
    """Salva os dados no arquivo JSON de forma segura com lock."""
    save_local_data(data)


def campaign_id_for(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def month_label(year: int, month: int) -> str:
    return f"{MESES_PT[month - 1]} {year}"


def parse_campaign_month(raw: Optional[str]) -> Tuple[int, int]:
    if not raw:
        raise ValueError("Informe o mes da campanha.")
    raw = str(raw)
    try:
        year_str, month_str = raw.split("-", 1)
        year = int(year_str)
        month = int(month_str)
    except ValueError as exc:
        raise ValueError("Mes invalido. Use o formato YYYY-MM.") from exc
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise ValueError("Mes da campanha fora do intervalo permitido.")
    return year, month


def saturdays_for_month(year: int, month: int) -> List[str]:
    current = date(year, month, 1)
    while current.weekday() != 5:
        current += timedelta(days=1)

    dates: List[str] = []
    while current.month == month:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=7)
    return dates


def build_campaign(year: int, month: int) -> dict:
    cid = campaign_id_for(year, month)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return {
        "id": cid,
        "ano": year,
        "mes": month,
        "nome": month_label(year, month),
        "sabados": saturdays_for_month(year, month),
        "status": "arquivada",
        "created_at": now,
        "updated_at": now,
    }


def get_campaign(data: dict, campaign_id: str) -> Optional[dict]:
    return next((c for c in data["campanhas"] if c.get("id") == campaign_id), None)


def get_schedule(data: dict, campaign_id: str) -> Optional[dict]:
    return next((s for s in data["escalas"] if s.get("campanha_id") == campaign_id), None)


def set_active_campaign(data: dict, campaign_id: str):
    data["campanha_ativa_id"] = campaign_id
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for campaign in data["campanhas"]:
        campaign["status"] = "ativa" if campaign.get("id") == campaign_id else "arquivada"
        if campaign.get("id") == campaign_id:
            campaign["updated_at"] = now


def get_or_create_campaign(data: dict, year: int, month: int) -> dict:
    cid = campaign_id_for(year, month)
    campaign = get_campaign(data, cid)
    if campaign:
        return campaign

    campaign = build_campaign(year, month)
    data["campanhas"].append(campaign)
    data["campanhas"].sort(key=lambda c: c.get("id", ""), reverse=True)
    return campaign


def ensure_active_campaign(data: dict) -> dict:
    active_id = data.get("campanha_ativa_id")
    active_campaign = get_campaign(data, active_id) if active_id else None
    if active_campaign:
        set_active_campaign(data, active_campaign["id"])
        return active_campaign

    today = date.today()
    campaign = get_or_create_campaign(data, today.year, today.month)
    set_active_campaign(data, campaign["id"])
    return campaign


def campaign_summary(data: dict, campaign: dict) -> dict:
    schedule = get_schedule(data, campaign["id"])
    campaign_dates = set(campaign.get("sabados", []))
    responses_count = sum(
        1
        for member in data["membros"]
        if any(d in campaign_dates for d in member.get("disponibilidades", []))
    )
    summary = dict(campaign)
    summary["tem_escala"] = schedule is not None
    summary["escala_updated_at"] = schedule.get("updated_at") if schedule else None
    summary["respostas_count"] = responses_count
    return summary


def persist_member_availabilities(members: List[dict]):
    if not USE_SUPABASE:
        return
    for member in members:
        query = supabase_client.table('membros').update({
            "disponibilidades": member.get("disponibilidades", [])
        })
        if member.get("whatsapp_key"):
            query.eq('whatsapp_key', member.get("whatsapp_key")).execute()
        else:
            query.eq('nome', member.get("nome")).execute()


def persist_member_record(member: dict):
    if not USE_SUPABASE:
        return
    payload = {
        "id": member.get("id"),
        "nome": member.get("nome"),
        "nome_key": member.get("nome_key"),
        "whatsapp": member.get("whatsapp"),
        "whatsapp_key": member.get("whatsapp_key"),
        "disponibilidades": member.get("disponibilidades", []),
    }
    supabase_client.table('membros').upsert(payload).execute()


def prune_member_availabilities_to_campaign(data: dict, campaign: dict) -> dict:
    allowed_dates = set(campaign.get("sabados", []))
    changed_members: List[dict] = []
    removed_dates = 0

    for member in data["membros"]:
        before = list(member.get("disponibilidades", []))
        after = [d for d in before if d in allowed_dates]
        if before != after:
            member["disponibilidades"] = after
            changed_members.append(member)
            removed_dates += len(before) - len(after)

    persist_member_availabilities(changed_members)
    return {
        "membros_alterados": len(changed_members),
        "datas_removidas": removed_dates,
    }


def reset_campaign_responses(data: dict, campaign: dict) -> dict:
    campaign_dates = set(campaign.get("sabados", []))
    changed_members: List[dict] = []
    removed_dates = 0

    for member in data["membros"]:
        before = list(member.get("disponibilidades", []))
        after = [d for d in before if d not in campaign_dates]
        if before != after:
            member["disponibilidades"] = after
            changed_members.append(member)
            removed_dates += len(before) - len(after)

    persist_member_availabilities(changed_members)
    return {
        "membros_alterados": len(changed_members),
        "datas_removidas": removed_dates,
    }


def normalize_schedule_items(items: list, campaign: dict) -> List[dict]:
    if not isinstance(items, list):
        raise ValueError("Escala invalida.")

    allowed_dates = set(campaign.get("sabados", []))
    by_date: Dict[str, List[str]] = {}
    for row in items:
        if not isinstance(row, dict):
            raise ValueError("Escala invalida.")
        data_str = row.get("data")
        if data_str not in allowed_dates:
            raise ValueError("A escala contem datas fora da campanha.")
        membros_row = row.get("membros", [])
        if not isinstance(membros_row, list):
            raise ValueError("Membros da escala invalidos.")
        clean_members = []
        for nome in membros_row:
            nome_limpo = str(nome).strip()[:50]
            if nome_limpo:
                clean_members.append(nome_limpo)
        by_date[data_str] = clean_members

    return [
        {"data": data_str, "membros": by_date.get(data_str, [])}
        for data_str in campaign.get("sabados", [])
    ]


def upsert_schedule(data: dict, campaign: dict, items: list) -> dict:
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    schedule = get_schedule(data, campaign["id"])
    normalized_items = normalize_schedule_items(items, campaign)

    if schedule is None:
        schedule = {
            "id": campaign["id"],
            "campanha_id": campaign["id"],
            "nome": f"Escala - {campaign['nome']}",
            "created_at": now,
            "updated_at": now,
            "itens": normalized_items,
        }
        data["escalas"].append(schedule)
    else:
        schedule["nome"] = f"Escala - {campaign['nome']}"
        schedule["updated_at"] = now
        schedule["itens"] = normalized_items

    return schedule


def generate_schedule_for_campaign(data: dict, campaign: dict) -> List[dict]:
    campaign_dates = set(campaign.get("sabados", []))
    member_labels = schedule_labels_for_members(data["membros"])
    raw = [
        (member_labels.get(m.get("id"), m["nome"]), [d for d in m.get("disponibilidades", []) if d in campaign_dates])
        for m in data["membros"]
    ]

    if not any(datas for _, datas in raw):
        raise ValueError("Nenhuma disponibilidade cadastrada para esta campanha.")

    disponibilidade = build_availability_map(raw)
    for data_str in campaign.get("sabados", []):
        disponibilidade.setdefault(datetime.strptime(data_str, "%Y-%m-%d"), set())
    disponibilidade = dict(sorted(disponibilidade.items()))
    escala = gerar_escala(disponibilidade)
    return [
        {"data": dt.strftime("%Y-%m-%d"), "membros": membros}
        for dt, membros in escala
        if dt.strftime("%Y-%m-%d") in campaign_dates
    ]


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
@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = safe_next_url(request.values.get("next"))
    error = None

    if is_admin_authenticated():
        return redirect(next_url)

    if request.method == "POST":
        password = request.form.get("password", "")

        if not ADMIN_PASSWORD:
            error = "Configure ADMIN_PASSWORD no arquivo .env antes de acessar o painel."
        elif hmac.compare_digest(password, ADMIN_PASSWORD):
            session.clear()
            session["admin_logged_in"] = True
            return redirect(next_url)
        else:
            error = "Senha invalida."

    return render_template("login.html", error=error, next_url=next_url, admin_password_configured=bool(ADMIN_PASSWORD))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@admin_required
def index():
    return render_template("index.html")


@app.route("/membro")
def membro_form():
    return render_template("membro.html")


@app.route("/api/membros", methods=["GET"])
@admin_required
def get_membros():
    data = load_data()
    if not USE_SUPABASE:
        save_data(data)
    return jsonify(data["membros"])


@app.route("/api/membros", methods=["POST"])
@admin_required
def add_membro():
    body = request.get_json() or {}
    nome = clean_member_name(body.get("nome"))
    whatsapp_key = normalize_whatsapp_key(body.get("whatsapp") or body.get("telefone"))
    if not nome:
        return jsonify({"erro": "Nome invalido."}), 400

    try:
        validate_whatsapp_key(whatsapp_key)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    data = load_data()
    if find_member_by_whatsapp(data["membros"], whatsapp_key):
        return jsonify({"erro": "WhatsApp ja cadastrado para outro membro."}), 409

    try:
        member, created = resolve_member_for_whatsapp(data, nome, whatsapp_key, [])
        member["nome"] = nome
        member["nome_key"] = normalize_name_key(nome)
        persist_member_record(member)
        save_data(data)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 409
    except Exception as e:
        return jsonify({"erro": f"Erro ao salvar membro: {e}"}), 500

    return jsonify({"ok": True, "membro": member}), 201 if created else 200

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
@admin_required
def delete_membro(nome: str):
    data = load_data()
    member = find_member_by_identifier(data, nome)
    if not member:
        return jsonify({"erro": "Membro nao encontrado."}), 404

    if USE_SUPABASE:
        try:
            query = supabase_client.table('membros').delete()
            if member.get("whatsapp_key"):
                query.eq('whatsapp_key', member.get("whatsapp_key")).execute()
            else:
                query.eq('nome', member.get("nome")).execute()
        except Exception:
            return jsonify({"erro": "Erro ao remover membro na nuvem."}), 500

    data["membros"] = [m for m in data["membros"] if m.get("id") != member.get("id")]
    save_data(data)
    return jsonify({"ok": True})

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
@admin_required
def update_disponibilidades(nome: str):
    body = request.get_json()
    raw_datas = (body or {}).get("disponibilidades", [])
    if not isinstance(raw_datas, list):
        return jsonify({"erro": "Disponibilidades invalidas."}), 400
    datas = sorted(set(str(d) for d in raw_datas))
    for d_str in datas:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d")
            if d.weekday() != 5:
                return jsonify({"erro": f"{d_str} nao e sabado."}), 400
        except ValueError:
            return jsonify({"erro": f"Data invalida: {d_str}"}), 400

    data = load_data()
    member = find_member_by_identifier(data, nome)
    if not member:
        return jsonify({"erro": "Membro nao encontrado."}), 404

    if USE_SUPABASE:
        try:
            query = supabase_client.table('membros').update({"disponibilidades": datas})
            if member.get("whatsapp_key"):
                query.eq('whatsapp_key', member.get("whatsapp_key")).execute()
            else:
                query.eq('nome', member.get("nome")).execute()
        except Exception:
            return jsonify({"erro": "Erro na nuvem."}), 500

    member["disponibilidades"] = datas
    save_data(data)
    return jsonify({"ok": True})

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
    body = request.get_json() or {}
    nome = clean_member_name(body.get("nome"))
    whatsapp_key = normalize_whatsapp_key(body.get("whatsapp") or body.get("telefone"))
    raw_datas = body.get("disponibilidades", [])
    if not isinstance(raw_datas, list):
        return jsonify({"erro": "Disponibilidades invalidas."}), 400
    datas = sorted(set(str(d) for d in raw_datas))

    if not nome:
        return jsonify({"erro": "Nome invalido."}), 400

    try:
        validate_whatsapp_key(whatsapp_key)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    for d_str in datas:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d")
            if d.weekday() != 5:
                return jsonify({"erro": f"{d_str} nao e sabado."}), 400
        except ValueError:
            return jsonify({"erro": f"Data invalida: {d_str}"}), 400

    data = load_data()
    campaign = ensure_active_campaign(data)
    allowed_dates = set(campaign.get("sabados", []))
    if any(d_str not in allowed_dates for d_str in datas):
        return jsonify({"erro": "Envie apenas datas da campanha ativa."}), 400

    try:
        member, _created = resolve_member_for_whatsapp(data, nome, whatsapp_key, datas)
        member["disponibilidades"] = datas
        persist_member_record(member)
        save_data(data)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 409
    except Exception as e:
        return jsonify({"erro": f"Erro ao salvar disponibilidade: {e}"}), 500

    return jsonify({"ok": True, "membro": member}), 200

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

    data = load_data()
    campaign = ensure_active_campaign(data)
    allowed_dates = set(campaign.get("sabados", []))
    if any(d_str not in allowed_dates for d_str in datas):
        return jsonify({"erro": "Envie apenas datas da campanha ativa."}), 400

    if USE_SUPABASE:
        try:
            supabase_client.table('membros').upsert({"nome": nome, "disponibilidades": datas}).execute()
            save_data(data)
            return jsonify({"ok": True}), 200
        except Exception as e:
            return jsonify({"erro": f"Erro na nuvem: {e}"}), 500

    
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


@app.route("/api/campanha-publica", methods=["GET"])
def campanha_publica():
    data = load_data()
    campaign = ensure_active_campaign(data)
    save_data(data)
    return jsonify({"campanha": campaign_summary(data, campaign)})


@app.route("/api/campanhas", methods=["GET"])
@admin_required
def list_campanhas():
    data = load_data()
    active_campaign = ensure_active_campaign(data)
    save_data(data)
    campanhas = [campaign_summary(data, c) for c in data["campanhas"]]
    campanhas.sort(key=lambda c: c.get("id", ""), reverse=True)
    return jsonify({
        "ativa": campaign_summary(data, active_campaign),
        "campanhas": campanhas,
    })


@app.route("/api/campanhas", methods=["POST"])
@admin_required
def create_campanha():
    body = request.get_json() or {}
    raw_month = body.get("mes") or body.get("month")
    if body.get("ano") and isinstance(body.get("mes"), int):
        raw_month = f"{int(body['ano']):04d}-{int(body['mes']):02d}"
    elif not raw_month and body.get("ano") and body.get("mes_numero"):
        raw_month = f"{int(body['ano']):04d}-{int(body['mes_numero']):02d}"

    try:
        year, month = parse_campaign_month(raw_month)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    data = load_data()
    campaign = get_or_create_campaign(data, year, month)
    set_active_campaign(data, campaign["id"])
    limpeza = prune_member_availabilities_to_campaign(data, campaign)
    save_data(data)

    return jsonify({
        "ok": True,
        "ativa": campaign_summary(data, campaign),
        "campanhas": [campaign_summary(data, c) for c in data["campanhas"]],
        "limpeza": limpeza,
    }), 201


@app.route("/api/campanhas/<campaign_id>/ativar", methods=["POST"])
@admin_required
def ativar_campanha(campaign_id: str):
    data = load_data()
    campaign = get_campaign(data, campaign_id)
    if not campaign:
        return jsonify({"erro": "Campanha nao encontrada."}), 404

    set_active_campaign(data, campaign_id)
    save_data(data)
    return jsonify({"ok": True, "ativa": campaign_summary(data, campaign)})


@app.route("/api/campanhas/<campaign_id>/zerar-respostas", methods=["POST"])
@admin_required
def zerar_respostas_campanha(campaign_id: str):
    data = load_data()
    campaign = get_campaign(data, campaign_id)
    if not campaign:
        return jsonify({"erro": "Campanha nao encontrada."}), 404

    limpeza = reset_campaign_responses(data, campaign)
    save_data(data)
    return jsonify({
        "ok": True,
        "campanha": campaign_summary(data, campaign),
        "limpeza": limpeza,
    })


@app.route("/api/campanhas/<campaign_id>/escala", methods=["GET"])
@admin_required
def get_escala_salva(campaign_id: str):
    data = load_data()
    campaign = get_campaign(data, campaign_id)
    if not campaign:
        return jsonify({"erro": "Campanha nao encontrada."}), 404

    schedule = get_schedule(data, campaign_id)
    return jsonify({
        "campanha": campaign_summary(data, campaign),
        "escala": schedule,
    })


@app.route("/api/campanhas/<campaign_id>/escala", methods=["PUT"])
@admin_required
def save_escala_salva(campaign_id: str):
    body = request.get_json() or {}
    data = load_data()
    campaign = get_campaign(data, campaign_id)
    if not campaign:
        return jsonify({"erro": "Campanha nao encontrada."}), 404

    try:
        schedule = upsert_schedule(data, campaign, body.get("itens", []))
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    save_data(data)
    return jsonify({
        "ok": True,
        "campanha": campaign_summary(data, campaign),
        "escala": schedule,
    })


@app.route("/api/campanhas/<campaign_id>/gerar-escala", methods=["POST"])
@admin_required
def gerar_escala_campanha(campaign_id: str):
    data = load_data()
    campaign = get_campaign(data, campaign_id)
    if not campaign:
        return jsonify({"erro": "Campanha nao encontrada."}), 404

    try:
        resultado = generate_schedule_for_campaign(data, campaign)
        schedule = upsert_schedule(data, campaign, resultado)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    save_data(data)
    return jsonify({
        "ok": True,
        "campanha": campaign_summary(data, campaign),
        "escala": schedule,
    })


@app.route("/api/gerar-escala", methods=["POST"])
@admin_required
def api_gerar_escala():
    data = load_data()
    campaign = ensure_active_campaign(data)

    try:
        resultado = generate_schedule_for_campaign(data, campaign)
        upsert_schedule(data, campaign, resultado)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    save_data(data)
    return jsonify(resultado)


@app.route("/api/exportar-csv", methods=["POST"])
@admin_required
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
@admin_required
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
        max_membros = max(
            MEMBROS_POR_SABADO,
            max((len(item.get("membros", [])) for item in escala), default=0),
        )
        for idx in range(max_membros):
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
