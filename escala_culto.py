#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Escala automática de serviço de culto (apenas aos sábados)

Requisitos:
* Cada pessoa pode servir no máximo uma vez a cada dois sábados
  (não pode haver serviços em sábados consecutivos para o mesmo membro).
* Só são considerados os sábados informados nas disponibilidades.
* A saída é um CSV com colunas: data, nome_do_membro

Como usar:
    1. Edite a constante `DISPONIBILIDADES` abaixo.
    2. Rode: python escala_culto.py
"""

import csv
from datetime import datetime
from collections import defaultdict
from typing import List, Tuple, Dict, Set

# ----------------------------------------------------------------------
# 👉 1️⃣  PREENCHE AQUI AS DISPONIBILIDADES
# Cada tupla: ("Nome", ["YYYY-MM-DD", "YYYY-MM-DD", ...])
# Só inclua datas que sejam realmente sábados.
# ----------------------------------------------------------------------
DISPONIBILIDADES: List[Tuple[str, List[str]]] = [
    ("Ana",   ["2026-05-02", "2026-05-16", "2026-05-30"]),
    ("Bruno", ["2026-05-02", "2026-05-09", "2026-05-23"]),
    ("Carla", ["2026-05-09", "2026-05-23", "2026-06-06"]),
    ("Daniel",["2026-05-16", "2026-05-30", "2026-06-13"]),
    ("Eva",   ["2026-05-02", "2026-05-23", "2026-06-06"]),
    # ← adicione quantas pessoas/quais datas precisar
]

# ----------------------------------------------------------------------
# 👉 2️⃣  FUNÇÕES AUXILIARES
# ----------------------------------------------------------------------
def parse_dates(date_strs: List[str]) -> Set[datetime]:
    """Converte lista de strings 'YYYY-MM-DD' para objetos datetime."""
    return {datetime.strptime(d, "%Y-%m-%d") for d in date_strs}


def build_availability_map(
    raw: List[Tuple[str, List[str]]]
) -> Dict[datetime, Set[str]]:
    """
    Cria um dicionário:
        chave → data do sábado (datetime)
        valor → conjunto de nomes que estão disponíveis nessa data
    """
    avail: Dict[datetime, Set[str]] = defaultdict(set)
    for nome, datas in raw:
        for d in parse_dates(datas):
            if d.weekday() != 5:
                raise ValueError(f"{d.date()} não é sábado.")
            avail[d].add(nome)
    return dict(sorted(avail.items()))


def gerar_escala(
    disponibilidade: Dict[datetime, Set[str]]
) -> List[Tuple[datetime, str]]:
    """
    Algoritmo guloso simples:
    * percorre os sábados em ordem cronológica
    * para cada data, escolhe um membro disponível que NÃO tenha servido
      no sábado imediatamente anterior (regra “um a cada dois sábados”)
    * se houver mais de um candidato, prefere quem já serviu menos vezes
      (para balancear a carga)
    """
    escala: List[Tuple[datetime, str]] = []
    contagem: Dict[str, int] = defaultdict(int)
    ultimo_servico: Dict[str, datetime] = {}
    datas = list(disponibilidade.keys())
    for i, data_atual in enumerate(datas):
        candidatos = disponibilidade[data_atual].copy()
        if i > 0:
            data_anterior = datas[i - 1]
            for nome, ultima in ultimo_servico.items():
                if ultima == data_anterior and nome in candidatos:
                    candidatos.remove(nome)
        if not candidatos:
            escala.append((data_atual, "---"))
            continue
        escolhido = min(candidatos, key=lambda n: contagem[n])
        escala.append((data_atual, escolhido))
        contagem[escolhido] += 1
        ultimo_servico[escolhido] = data_atual
    return escala


def salvar_csv(escala: List[Tuple[datetime, str]], caminho: str = "escala_culto.csv"):
    """Grava a escala em CSV (colunas: data, membro)."""
    with open(caminho, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["data", "membro"])
        for data, membro in escala:
            writer.writerow([data.strftime("%Y-%m-%d"), membro])
    print(f"✅ Escala salva em '{caminho}'")


def imprimir_escala(escala: List[Tuple[datetime, str]]):
    """Mostra a escala formatada no terminal."""
    print("\nEscala de culto (sábados)\n" + "-" * 30)
    for data, membro in escala:
        print(f"{data.strftime('%Y-%m-%d')}  →  {membro}")
    print("-" * 30 + "\n")

# ----------------------------------------------------------------------
# 👉 3️⃣  EXECUÇÃO PRINCIPAL
# ----------------------------------------------------------------------
def main():
    disponibilidade = build_availability_map(DISPONIBILIDADES)
    escala = gerar_escala(disponibilidade)
    imprimir_escala(escala)
    salvar_csv(escala)


if __name__ == "__main__":
    main()
