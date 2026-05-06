# Escala de Culto

Sistema Flask para cadastrar membros, coletar disponibilidades e gerar escalas de culto aos sabados.

## Funcionalidades principais

- Painel administrativo protegido por senha.
- Cadastro de membros com WhatsApp unico e disponibilidades.
- Campanhas mensais, com uma campanha ativa por vez.
- Formulario publico que mostra os sabados da campanha ativa.
- Geracao automatica de escala por campanha.
- Historico de campanhas com escala salva.
- Edicao manual da escala e persistencia das alteracoes.
- Limpeza de disponibilidades antigas ao iniciar uma nova campanha.
- Botao para zerar respostas da campanha ativa sem remover membros ou escalas salvas.
- Exportacao CSV e Excel.

## Cadastro unico de membros

Novos membros precisam informar nome completo e WhatsApp com DDD. O sistema normaliza o numero, entao `(11) 99999-9999` e `+55 11 99999-9999` apontam para o mesmo cadastro. Membros antigos sem WhatsApp continuam validos e recebem o numero automaticamente quando responderem pelo formulario publico com o mesmo nome normalizado.

## Configuracao

1. Copie `.env.example` para `.env`.
2. Defina uma senha forte em `ADMIN_PASSWORD`.
3. Defina uma chave longa e aleatoria em `SECRET_KEY`.
4. Opcionalmente, preencha `SUPABASE_URL` e `SUPABASE_KEY` para persistir os dados na nuvem.

Sem `ADMIN_PASSWORD`, o painel administrativo fica bloqueado por seguranca. O formulario publico em `/membro` continua acessivel para os membros enviarem disponibilidade.

## Executar localmente

```bash
pip install -r requirements.txt
python app.py
```

Painel administrativo: `http://localhost:5000/`

Formulario publico: `http://localhost:5000/membro`

## Campanhas e historico

No painel, escolha o mes em **Campanha Ativa** e clique em **Ativar**. Ao gerar a escala, ela fica salva na campanha selecionada. Depois, use a lista de campanhas para reabrir escalas anteriores ou ativar outro mes.

Ao ativar uma campanha pelo seletor de mes, disponibilidades de outros meses sao removidas para evitar duplicidade entre campanhas. Use **Zerar Respostas** quando quiser limpar manualmente as respostas da campanha ativa e reiniciar a coleta do mes.
