import json
from datetime import datetime

import httpx
from services.config_service import config_service
from services.search_service import search_service

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_SYSTEM_PROMPT = """Você é um assistente de busca de emails inteligente. O usuário tem ~130 mil emails sincronizados no banco de dados.

Sua função:
1. Entender a pergunta do usuário sobre seus emails
2. Usar as ferramentas de busca disponíveis para encontrar os emails relevantes
3. Responder em português brasileiro (pt-BR) de forma clara e organizada

Regras:
- Sempre use as ferramentas para buscar dados. NUNCA invente informações.
- Ao listar emails, inclua: assunto, remetente, data e o link no formato [Assunto](link)
- O link para abrir o email no app é: #/email/{gmail_id}
- Se a busca retornar vários resultados, resuma os mais relevantes (máximo 10)
- Se não encontrar resultados, sugira buscas alternativas
- Quando o usuário perguntar sobre um remetente, use search_sender ou search_sender_exact
- Para buscas por conteúdo no corpo do email, use search_body_fulltext
- Para perguntas sobre período, use search_date_range ou search_combined com date_from/date_to
- Para perguntas que combinam vários critérios, use search_combined
- Formate datas no formato brasileiro (dd/mm/aaaa)
- Use get_email_detail apenas quando precisar do conteúdo completo de um email específico
- Use get_sender_summary para estatísticas sobre um remetente específico
- Use get_top_senders para listar os remetentes que mais enviam emails (ranking). NÃO use get_sender_summary em loop para isso.
- Use get_email_stats para estatísticas gerais da caixa (total, não lidos, labels, etc.)
- Use execute_sql para consultas complexas que as outras ferramentas não cobrem. Você pode escrever queries SQL SELECT diretamente no PostgreSQL.
- IMPORTANTE: Seja EFICIENTE com as ferramentas. Você tem limite de rounds.
  - Prefira UMA query SQL bem elaborada em vez de várias queries simples.
  - Combine múltiplas análises em uma única query usando CTEs (WITH) quando possível.
  - Após receber o resultado de uma query, PARE e responda ao usuário. NÃO faça queries adicionais desnecessárias.
  - Se a primeira query retornou os dados suficientes, NÃO refine com queries extras. Responda imediatamente.
  - Máximo ideal: 1-3 chamadas de ferramentas por pergunta.
- OBRIGATÓRIO: Use save_query para salvar a consulta SQL SEMPRE que retornar listagens ou dados tabelares. O usuário poderá clicar no link e ver os resultados completos em uma página dedicada com paginação.
  - Formato do link: [Título da Consulta](#/query/{hash})
  - Salve a query SQL usada (ou uma versão sem LIMIT para mostrar todos os resultados) e inclua o link na resposta.
  - Exemplos de quando usar: listagem de emails, rankings de remetentes, estatísticas por período, qualquer resultado com múltiplas linhas.
  - Fluxo: 1) execute a busca/SQL → 2) chame save_query com a SQL correspondente → 3) inclua o link [Texto](#/query/{hash}) na resposta.
  - NÃO pergunte ao usuário se quer ver — sempre inclua o link proativamente.
- Também inclua links simples para filtrar emails quando relevante:
  - Por remetente: [Ver emails](#/emails?sender=email@dominio.com)
  - Por período: [Ver emails](#/emails?date_from=2024-01-01&date_to=2024-01-31)
  - Params disponíveis: sender, subject, date_from, date_to, label, has_attachments, is_read
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_body_fulltext",
            "description": "Busca full-text no corpo dos emails usando PostgreSQL tsvector. Ideal para encontrar emails que mencionam um termo específico no corpo da mensagem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termo de busca (ex: 'nota fiscal', 'reunião amanhã')"},
                    "limit": {"type": "integer", "description": "Máximo de resultados (default: 20)", "default": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_subject_keyword",
            "description": "Busca por palavra-chave no assunto dos emails (case-insensitive). Use para encontrar emails com termos específicos no assunto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Palavra-chave para buscar no assunto"},
                    "limit": {"type": "integer", "description": "Máximo de resultados", "default": 20},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_sender",
            "description": "Busca fuzzy por remetente (nome ou email). Use quando o usuário menciona um remetente mas pode não saber o email exato.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sender": {"type": "string", "description": "Nome ou email do remetente (parcial ok)"},
                    "limit": {"type": "integer", "description": "Máximo de resultados", "default": 20},
                },
                "required": ["sender"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_sender_exact",
            "description": "Busca exata por email do remetente. Use quando você sabe o endereço de email exato.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sender_email": {"type": "string", "description": "Email exato do remetente"},
                    "limit": {"type": "integer", "description": "Máximo de resultados", "default": 20},
                },
                "required": ["sender_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_date_range",
            "description": "Busca emails por período de datas. Use para perguntas como 'emails de janeiro 2024' ou 'emails desta semana'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Data inicial no formato YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "Data final no formato YYYY-MM-DD"},
                    "limit": {"type": "integer", "description": "Máximo de resultados", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_label",
            "description": "Busca emails por label/pasta do Gmail (ex: INBOX, SENT, SPAM, TRASH, CATEGORY_PROMOTIONS, STARRED, etc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Label do Gmail (ex: INBOX, SPAM, CATEGORY_PROMOTIONS)"},
                    "limit": {"type": "integer", "description": "Máximo de resultados", "default": 20},
                },
                "required": ["label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_attachments",
            "description": "Busca emails com anexos, opcionalmente filtrando por nome de arquivo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nome do arquivo anexo (parcial ok)"},
                    "has_attachments": {"type": "boolean", "description": "Filtrar por ter/não ter anexos", "default": True},
                    "limit": {"type": "integer", "description": "Máximo de resultados", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_thread",
            "description": "Busca todos os emails de uma thread/conversa específica pelo thread_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "ID da thread do Gmail"},
                },
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_combined",
            "description": "Busca multi-critério combinando remetente, assunto, corpo, datas, label e anexos. Use para perguntas complexas que envolvem múltiplos filtros.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sender": {"type": "string", "description": "Remetente (parcial ok)"},
                    "subject": {"type": "string", "description": "Palavra-chave no assunto"},
                    "body_keyword": {"type": "string", "description": "Palavra-chave no corpo (full-text)"},
                    "date_from": {"type": "string", "description": "Data inicial (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "Data final (YYYY-MM-DD)"},
                    "label": {"type": "string", "description": "Label do Gmail"},
                    "has_attachments": {"type": "boolean", "description": "Filtrar por anexos"},
                    "limit": {"type": "integer", "description": "Máximo de resultados", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_email_detail",
            "description": "Obtém o conteúdo completo de um email específico (incluindo body). Use apenas quando o usuário quiser ver o conteúdo de um email específico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gmail_id": {"type": "string", "description": "ID do email no Gmail"},
                },
                "required": ["gmail_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sender_summary",
            "description": "Obtém estatísticas resumidas de um remetente: total de emails, primeiro/último email, tamanho total, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sender_email": {"type": "string", "description": "Email exato do remetente"},
                },
                "required": ["sender_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_senders",
            "description": "Retorna os remetentes que mais enviaram emails, ordenados por quantidade. Use para perguntas como 'quem mais me envia emails', 'top remetentes', 'maiores remetentes'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Quantidade de remetentes a retornar (default: 20)", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_email_stats",
            "description": "Retorna estatísticas gerais da caixa de email: total de emails, não lidos, com anexos, remetentes únicos, labels mais usadas, data do email mais antigo/recente. Use para perguntas como 'quantos emails eu tenho', 'resumo da minha caixa', 'estatísticas'.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": """Executa uma query SQL SELECT diretamente no banco PostgreSQL. Use para consultas complexas que as outras ferramentas não cobrem.

SCHEMA DO BANCO:
- Tabela 'emails':
  - gmail_id (VARCHAR PK), thread_id, subject, sender (nome), sender_email, recipients (TEXT)
  - date (TIMESTAMPTZ), snippet (TEXT), body (TEXT), body_tsv (TSVECTOR - busca full-text em português)
  - labels (TEXT[] - array de labels Gmail: INBOX, SENT, SPAM, TRASH, CATEGORY_PROMOTIONS, STARRED, etc)
  - size_estimate (INTEGER - bytes), has_attachments (BOOLEAN), is_read (BOOLEAN)
  - attachments (JSONB), gmail_link (VARCHAR), account_id (INTEGER FK), user_id (INTEGER FK)

- Tabela 'accounts':
  - id (SERIAL PK), name, email, provider ('gmail'/'imap'), is_active, last_sync_at, sync_status, user_id (INTEGER FK)

- Tabela 'chat_sessions':
  - id (VARCHAR PK), title, messages (JSONB), tools_map (JSONB), created_at, updated_at, user_id (INTEGER FK)

DICAS:
- Full-text search no body: WHERE body_tsv @@ plainto_tsquery('portuguese', 'termo')
- Labels é array: WHERE 'INBOX' = ANY(labels)
- Datas: WHERE date >= '2024-01-01' AND date < '2024-02-01'
- Limite de 100 rows no resultado. Use LIMIT se precisar de menos.
- Apenas SELECT/WITH (CTEs) são permitidos.
- IMPORTANTE: Todas as queries DEVEM filtrar por user_id. O filtro será adicionado automaticamente.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Query SQL SELECT para executar"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_query",
            "description": "Salva uma consulta SQL para o usuário visualizar em página dedicada com paginação. Retorna um hash que pode ser usado em link [texto](#/query/{hash}). Use SEMPRE que fizer análises com dados tabelares, rankings, listagens ou estatísticas que o usuário pode querer explorar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Título descritivo da consulta (ex: 'Top 10 Remetentes', 'Emails por mês 2024')"},
                    "description": {"type": "string", "description": "Descrição curta do que a consulta mostra"},
                    "sql": {"type": "string", "description": "Query SQL SELECT que gera os resultados"},
                },
                "required": ["title", "description", "sql"],
            },
        },
    },
]


def _serialize_result(obj):
    """Converte objetos não-serializáveis para string."""
    if obj is None:
        return obj
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize_result(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_result(i) for i in obj]
    return str(obj)


def _inject_user_id_sql(query: str, user_id: int) -> str:
    """Inject user_id filter into SQL queries for data isolation.

    Adds WHERE user_id = X to queries on emails, accounts, chat_sessions tables.
    """
    if not user_id:
        return query

    import re

    user_filter = f"user_id = {int(user_id)}"

    # For queries with WHERE clause, add AND user_id = X
    # For queries without WHERE, add WHERE user_id = X before GROUP BY/ORDER BY/LIMIT
    # Handle both simple and CTE queries

    # Simple approach: find FROM <table> and inject filter
    tables_needing_filter = ["emails", "accounts", "chat_sessions"]

    for table in tables_needing_filter:
        # Pattern: FROM table (with optional alias) followed by WHERE or GROUP/ORDER/LIMIT/end
        # Add user_id filter after WHERE or add new WHERE
        pattern_with_where = re.compile(
            rf"(FROM\s+{table}\b[^)]*?)(WHERE\s+)",
            re.IGNORECASE | re.DOTALL,
        )
        pattern_without_where = re.compile(
            rf"(FROM\s+{table}\b(?:\s+\w+)?)((?:\s+(?:GROUP|ORDER|LIMIT|HAVING|UNION|EXCEPT|INTERSECT|$)))",
            re.IGNORECASE | re.DOTALL,
        )

        if pattern_with_where.search(query):
            query = pattern_with_where.sub(
                rf"\1WHERE {user_filter} AND ", query
            )
        elif pattern_without_where.search(query):
            query = pattern_without_where.sub(
                rf"\1 WHERE {user_filter}\2", query
            )

    return query


class AgentService:

    def _execute_tool(self, tool_name: str, arguments: dict, user_id: int = None):
        """Execute a tool with user_id injected for data isolation."""

        # Tools that accept user_id parameter
        user_filtered_tools = {
            "search_body_fulltext": search_service.search_body_fulltext,
            "search_subject_keyword": search_service.search_subject_keyword,
            "search_sender": search_service.search_sender,
            "search_sender_exact": search_service.search_sender_exact,
            "search_date_range": search_service.search_date_range,
            "search_by_label": search_service.search_by_label,
            "search_attachments": search_service.search_attachments,
            "search_thread": search_service.search_thread,
            "search_combined": search_service.search_combined,
            "get_email_detail": search_service.get_email_detail,
            "get_sender_summary": search_service.get_sender_summary,
            "get_top_senders": search_service.get_top_senders,
            "get_email_stats": search_service.get_email_stats,
        }

        # Tools without user_id filtering
        plain_tools = {
            "save_query": search_service.save_query,
        }

        fn = user_filtered_tools.get(tool_name)
        if fn:
            try:
                arguments["user_id"] = user_id
                result = fn(**arguments)
                return _serialize_result(result)
            except Exception as e:
                return {"error": str(e)}

        if tool_name == "execute_sql":
            try:
                sql = arguments.get("query", "")
                if user_id:
                    sql = _inject_user_id_sql(sql, user_id)
                result = search_service.execute_sql(sql)
                return _serialize_result(result)
            except Exception as e:
                return {"error": str(e)}

        fn = plain_tools.get(tool_name)
        if fn:
            try:
                result = fn(**arguments)
                return _serialize_result(result)
            except Exception as e:
                return {"error": str(e)}

        return {"error": f"Tool '{tool_name}' não encontrada"}

    async def chat(self, messages: list[dict], user_id: int = None) -> dict:
        user_config = config_service.get_user_ai_raw(user_id) if user_id else {"api_key": "", "model": "anthropic/claude-sonnet-4", "system_prompt": ""}
        api_key = user_config["api_key"]
        model = user_config["model"] or "anthropic/claude-sonnet-4"

        if not api_key:
            return {
                "response": "Erro: API Key do OpenRouter não configurada. Vá em Configurações para definir a chave.",
                "tools_used": [],
                "model": None,
            }

        system_prompt = user_config["system_prompt"] or DEFAULT_SYSTEM_PROMPT
        now = datetime.now()
        date_context = f"\n\nData e hora atual: {now.strftime('%d/%m/%Y %H:%M')} ({now.strftime('%A')})."
        date_context += f" Use esta data como referência para 'hoje', 'esta semana', 'este mês', etc."
        conversation = [{"role": "system", "content": system_prompt + date_context}] + messages
        tools_used = []
        model_used = model

        async with httpx.AsyncClient(timeout=120.0) as client:
            for _round in range(15):
                payload = {
                    "model": model,
                    "messages": conversation,
                    "tools": TOOLS,
                    "temperature": 0.1,
                }

                resp = await client.post(
                    OPENROUTER_BASE_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if resp.status_code != 200:
                    error_text = resp.text
                    return {
                        "response": f"Erro na API do OpenRouter ({resp.status_code}): {error_text}",
                        "tools_used": tools_used,
                        "model": model_used,
                    }

                data = resp.json()
                choice = data["choices"][0]
                msg = choice["message"]
                model_used = data.get("model", model)

                # If the model wants to call tools
                if msg.get("tool_calls"):
                    conversation.append(msg)

                    for tool_call in msg["tool_calls"]:
                        fn_name = tool_call["function"]["name"]
                        try:
                            fn_args = json.loads(tool_call["function"]["arguments"])
                        except json.JSONDecodeError:
                            fn_args = {}

                        result = self._execute_tool(fn_name, fn_args, user_id=user_id)
                        tools_used.append({"tool": fn_name, "args": fn_args})

                        conversation.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        })
                    continue

                # Model returned final text response
                return {
                    "response": msg.get("content", ""),
                    "tools_used": tools_used,
                    "model": model_used,
                }

        return {
            "response": "O agente atingiu o limite de rounds de ferramentas. Tente uma pergunta mais específica.",
            "tools_used": tools_used,
            "model": model_used,
        }


agent_service = AgentService()
