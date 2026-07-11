import os
import json
import requests
import re
import random
from dotenv import load_dotenv
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

# Carregar chave API do arquivo .env
load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-3.5-turbo"
REQUEST_TIMEOUT = 60  # segundos

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Apelidos comuns -> nome do serviço como consta no servicos.json
SERVICE_ALIASES = {
    "ecs": "elastic container service",
    "eks": "elastic kubernetes service",
    "ecr": "elastic container registry",
    "sns": "simple notification service",
    "sqs": "simple queue service",
    "kms": "key management service",
    "rds": "aurora and rds",
    "aurora": "aurora and rds",
    "ses": "amazon simple email service",
}

# Nomes de serviços que são palavras comuns: só contam como AWS se o tópico
# mencionar "aws"/"amazon" explicitamente (evita falso positivo em "python lambda")
AMBIGUOUS_SERVICES = {
    "lambda", "glue", "athena", "batch", "backup", "connect", "amplify",
    "translate", "polly", "forecast", "personalize", "pinpoint", "inspector",
    "detective", "macie", "chime", "braket", "textract", "kendra",
    "transcribe", "comprehend", "q",
}

# Base de conhecimento: 235 serviços AWS com descrições verificadas
@st.cache_data
def load_servicos():
    try:
        with open(os.path.join(BASE_DIR, "servicos.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

# Banco de questões AWS curadas e validadas por humano
@st.cache_data
def load_banco_aws():
    try:
        with open(os.path.join(BASE_DIR, "questoes_aws.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

# Remove prefixos "Amazon"/"AWS" para facilitar o casamento com o tópico digitado
def _normalize_service_name(name):
    return re.sub(r"^(amazon|aws)\s+", "", name.lower()).strip()

# Detecta se o tópico é sobre AWS e quais serviços foram mencionados
def match_aws_topic(topic):
    t = topic.lower()
    words = set(re.findall(r"[a-z0-9]+", t))
    has_aws_context = "aws" in words or "amazon" in words

    # Resolver apelidos digitados (ex.: "sqs" -> "simple queue service")
    aliased = {SERVICE_ALIASES[w] for w in words if w in SERVICE_ALIASES}

    matched_services = []
    for s in load_servicos():
        name = _normalize_service_name(s["comando"])
        mentioned = re.search(rf"\b{re.escape(name)}\b", t) or name in aliased
        if not mentioned:
            continue
        if name in AMBIGUOUS_SERVICES and not has_aws_context:
            continue
        matched_services.append(s)

    is_aws = has_aws_context or len(matched_services) > 0
    return is_aws, matched_services

# Reembaralha as alternativas de uma questão (evita decoreba de letra e o
# vício do modelo de posicionar a correta sempre na mesma posição)
def shuffle_options(q):
    letters = ["A", "B", "C", "D"]
    correct_text = q["options"][q["answer"]]
    values = list(q["options"].values())
    random.shuffle(values)
    new_options = dict(zip(letters[:len(values)], values))
    new_answer = next(k for k, v in new_options.items() if v == correct_text)
    shuffled = {
        "question": q["question"],
        "options": new_options,
        "answer": new_answer,
        "explanation": q["explanation"],
        "source": q.get("source", "banco"),
    }
    if q.get("verified"):
        shuffled["verified"] = True
    return shuffled

# Subconjunto do banco curado que casa com o tópico (determinístico, sem sorteio)
def bank_subset_for(topic, allow_generic=True):
    banco = load_banco_aws()
    if not banco:
        return []

    t = topic.lower()
    words = set(re.findall(r"[a-z0-9]+", t))
    has_aws_context = "aws" in words or "amazon" in words

    # Casar tags do banco (ex.: "S3", "Route 53") diretamente com o tópico
    matched_tags = set()
    for q in banco:
        for tag in q.get("services", []):
            tag_l = tag.lower()
            if tag_l == "geral":
                continue
            if tag_l in AMBIGUOUS_SERVICES and not has_aws_context:
                continue
            if re.search(rf"\b{re.escape(tag_l)}\b", t):
                matched_tags.add(tag_l)

    if matched_tags:
        return [q for q in banco
                if any(tag.lower() in matched_tags for tag in q.get("services", []))]
    if allow_generic:
        # Tópico AWS genérico (ex.: só "aws"): usa o banco inteiro
        return banco
    # Serviço específico sem questões no banco: deixa a geração ancorada cobrir
    return []

# Sorteia questões do banco curado conforme o tópico pedido
# (sorteio e embaralhamento são POR USUÁRIO, mesmo com cache global da parte IA)
def pick_bank_questions(topic, num, allow_generic=True):
    subset = bank_subset_for(topic, allow_generic)
    if not subset:
        return []
    escolhidas = random.sample(subset, min(num, len(subset)))
    return [shuffle_options(q) for q in escolhidas]

# Monta o bloco de fatos verificados para ancorar a geração por IA
def build_aws_facts(matched_services, max_services=12):
    servicos = load_servicos()
    if not servicos:
        return ""
    base = matched_services if matched_services else random.sample(servicos, min(10, len(servicos)))
    return "\n".join(f"- {s['comando']}: {s['descricao']}" for s in base[:max_services])

# Chamada única à API do OpenRouter em JSON mode (garante saída JSON válida)
def call_openrouter(messages, max_tokens, temperature):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    response = requests.post(API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

# Extrai a lista de questões da resposta do modelo (objeto {"questions": [...]}
# em JSON mode; array puro ou texto com cercas de código como fallback)
def parse_questions_json(content):
    for candidate in (content, clean_json_string(content)):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            for key in ("questions", "questoes"):
                if isinstance(data.get(key), list):
                    return data[key]
            return None
        if isinstance(data, list):
            return data
    return None

# Exemplo few-shot: mostra ao modelo o formato e o nível de qualidade esperados
EXAMPLE_QUESTION = (
    '{"question": "Qual protocolo é usado para transferir páginas web?", '
    '"options": {"A": "FTP", "B": "HTTP", "C": "SMTP", "D": "SSH"}, '
    '"answer": "B", '
    '"explanation": "O HTTP (HyperText Transfer Protocol) é o protocolo padrão para '
    'transferência de páginas web. FTP transfere arquivos, SMTP envia e-mails e SSH dá acesso remoto seguro."}'
)

# Gera um lote de questões via IA; retorna (questões válidas, mensagem de erro)
# Não usa st.error internamente: roda dentro de função cacheada, e elementos
# de UI emitidos ali seriam "replayados" a cada acerto de cache
def generate_batch(topic, n, grounding, avoid=None):
    avoid_txt = ""
    if avoid:
        avoid_txt = ("Não repita nem parafraseie estas questões já usadas: "
                     + " | ".join(q[:80] for q in avoid[:10]) + ". ")

    prompt = grounding + (
        f"Gere {n} questões de múltipla escolha sobre o tópico '{topic}'. "
        "Regras: "
        "1. Pergunta clara e objetiva. "
        "2. Quatro opções (A, B, C, D), todas plausíveis, mas apenas UMA correta. "
        "3. Baseie-se apenas em fatos amplamente estabelecidos e consensuais; "
        "evite números, versões ou limites específicos se não tiver certeza absoluta. "
        "4. A explicação deve justificar a resposta correta e, quando útil, dizer por que as outras estão erradas. "
        "5. Antes de finalizar cada questão, confira se a letra em 'answer' aponta para a alternativa de fato correta. "
        f"{avoid_txt}"
        "Todos os textos em português brasileiro. "
        'Retorne APENAS um objeto JSON no formato {"questions": [...]}, onde cada item tem as chaves '
        '"question", "options", "answer" e "explanation", como neste exemplo: '
        f"{EXAMPLE_QUESTION}"
    )

    try:
        content = call_openrouter(
            [
                {"role": "system", "content": "Você é um professor especialista que elabora questões de múltipla escolha precisas e factualmente corretas, em formato JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=min(400 * n + 200, 4000),
            temperature=0.5,
        )
        quiz_data = parse_questions_json(content)
        if quiz_data is None:
            return [], "A IA retornou um formato inesperado. Tente novamente."
        return validate_quiz_data(quiz_data, n, fill_dummies=False), None
    except Exception as e:
        return [], f"Erro ao gerar quiz: {str(e)}"

# Dupla checagem: o modelo responde às questões geradas ÀS CEGAS (sem ver o
# gabarito, temperatura 0). Só passam as questões em que a resposta independente
# coincide com o gabarito — descarta gabaritos trocados antes de chegarem ao aluno
def verify_generated_questions(questions):
    if not questions:
        return []
    lines = []
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q['question']}")
        for k, v in q["options"].items():
            lines.append(f"{k}) {v}")
    prompt = (
        "Responda às questões de múltipla escolha abaixo com a alternativa correta. "
        'Retorne APENAS um objeto JSON no formato {"answers": {"1": "A", "2": "B"}}.\n\n'
        + "\n".join(lines)
    )
    try:
        content = call_openrouter(
            [
                {"role": "system", "content": "Você é um especialista que responde questões de múltipla escolha com precisão. Responda em JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=30 * len(questions) + 100,
            temperature=0.0,
        )
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, re.DOTALL)
            data = json.loads(m.group(0)) if m else {}
        answers = data.get("answers", {}) if isinstance(data, dict) else {}

        approved = []
        for i, q in enumerate(questions, 1):
            independent = str(answers.get(str(i), "")).strip().upper()[:1]
            if independent == q["answer"]:
                q["verified"] = True
                approved.append(q)
        return approved
    except Exception:
        # A verificação é uma camada extra: se ela falhar, não travamos o quiz
        return questions

# Função para limpar e corrigir JSON inválido
def clean_json_string(json_str):
    # Remover marcadores de código se existirem
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0].strip()
    elif "```" in json_str:
        json_str = json_str.split("```")[1].strip()

    # Corrigir vírgulas finais ilegais em objetos e arrays
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*\]', ']', json_str)

    # Remover caracteres não-JSON no início e fim
    json_str = json_str.strip()
    if json_str.startswith("[") and json_str.endswith("]"):
        return json_str

    # Tentar encontrar o JSON array entre colchetes se o formato estiver corrompido
    match = re.search(r'\[(.*)\]', json_str, re.DOTALL)
    if match:
        return "[" + match.group(1) + "]"

    return json_str

# Função para criar uma questão de exemplo em caso de falha na geração
def create_dummy_question(index):
    return {
        "question": f"Questão exemplo {index} (houve um erro ao gerar a questão real)",
        "options": {
            "A": "Opção A",
            "B": "Opção B",
            "C": "Opção C",
            "D": "Opção D"
        },
        "answer": "A",
        "explanation": "Esta é uma questão de exemplo criada devido a um erro na geração da questão original."
    }

# Função para validar as questões geradas; com fill_dummies=False, questões
# inválidas são simplesmente descartadas (o chamador repõe o déficit)
def validate_quiz_data(quiz_data, num_questions, fill_dummies=True):
    valid_quiz = []

    if isinstance(quiz_data, list):
        for i, question in enumerate(quiz_data):
            if not isinstance(question, dict):
                if fill_dummies:
                    valid_quiz.append(create_dummy_question(i + 1))
                continue

            # Verifica campos obrigatórios
            required_fields = ["question", "options", "answer", "explanation"]
            valid = all(field in question for field in required_fields)

            # Verifica se options é um dicionário com pelo menos 2 opções
            if valid and isinstance(question["options"], dict) and len(question["options"]) >= 2:
                # Normaliza a resposta (ex.: " a) " -> "A") antes de validar
                answer = str(question["answer"]).strip().upper()[:1]
                if answer in question["options"]:
                    corrected = question.copy()
                    corrected["answer"] = answer
                    valid_quiz.append(corrected)
                    continue
            # Questão malformada ou resposta fora das opções: descarta em vez
            # de marcar uma alternativa possivelmente errada como correta
            if fill_dummies:
                valid_quiz.append(create_dummy_question(i + 1))

    # Se temos menos questões do que o solicitado, adiciona questões extras
    if fill_dummies:
        while len(valid_quiz) < num_questions:
            valid_quiz.append(create_dummy_question(len(valid_quiz) + 1))

    # Limita ao número solicitado
    return valid_quiz[:num_questions]

# Exceção usada para NÃO cachear gerações incompletas (st.cache_data não
# guarda o resultado quando a função levanta exceção)
class GenerationIncomplete(Exception):
    def __init__(self, questions, errors):
        self.questions = questions
        self.errors = errors

# Geração via IA com CACHE GLOBAL: compartilhado entre todos os usuários do
# processo por 24h. A turma inteira pedindo o mesmo tema gera UMA chamada à
# API; o sorteio do banco e o embaralhamento continuam individuais por usuário.
@st.cache_data(ttl=86400, max_entries=100, show_spinner=False)
def generate_ai_questions(topic, n):
    is_aws, matched_services = match_aws_topic(topic)

    # Para tópicos AWS, ancorar a geração em fatos verificados (reduz alucinação)
    grounding = ""
    if is_aws:
        facts = build_aws_facts(matched_services)
        if facts:
            grounding = (
                "Use EXCLUSIVAMENTE os fatos abaixo sobre serviços AWS como fonte de verdade. "
                "A resposta correta de cada questão deve ser diretamente verificável nesses fatos. "
                "Não invente características, limites ou números que não estejam listados.\n\n"
                f"FATOS VERIFICADOS:\n{facts}\n\n"
            )

    # Evitar duplicar qualquer questão do banco relacionada ao tema
    # (lista determinística: o cache global vale para todos os usuários)
    avoid_base = [q["question"] for q in
                  bank_subset_for(topic, allow_generic=(len(matched_services) == 0))] if is_aws else []

    # Gerar + dupla checagem, com uma segunda rodada para repor o que for
    # descartado (gabarito inconsistente ou estrutura inválida)
    generated, errors = [], []
    for _ in range(2):
        deficit = n - len(generated)
        if deficit <= 0:
            break
        avoid = avoid_base + [q["question"] for q in generated]
        batch, err = generate_batch(topic, deficit, grounding, avoid=avoid)
        if err:
            errors.append(err)
        generated.extend(verify_generated_questions(batch))

    generated = generated[:n]
    for q in generated:
        q["source"] = "ia"

    if len(generated) < n:
        raise GenerationIncomplete(generated, errors)
    return generated

# Função para gerar quiz: banco curado primeiro (AWS), IA ancorada como complemento
def generate_quiz(topic: str, num_questions: int):
    # Limitar número de questões para evitar sobrecarga na API
    num_questions = min(num_questions, 10)

    # Usar um tópico padrão se estiver em branco
    topic_to_use = "tecnologia da informação geral" if not topic.strip() else topic

    # Detectar tópico AWS e serviços mencionados
    is_aws, matched_services = match_aws_topic(topic_to_use)

    # 1) Fonte primária para AWS: banco de questões validadas
    #    (sem chamada à API, sem risco de alucinação, sorteio novo a cada quiz)
    #    O banco inteiro só entra quando o tópico é AWS genérico; se um serviço
    #    específico foi citado, apenas questões daquele serviço são usadas
    bank_questions = pick_bank_questions(
        topic_to_use, num_questions,
        allow_generic=(len(matched_services) == 0)
    ) if is_aws else []
    if len(bank_questions) >= num_questions:
        return bank_questions[:num_questions]

    # 2) Complemento via IA para o que o banco não cobre (cache global 24h)
    remaining = num_questions - len(bank_questions)
    try:
        generated = generate_ai_questions(topic_to_use.strip().lower(), remaining)
    except GenerationIncomplete as e:
        generated = e.questions
        for msg in e.errors:
            st.error(msg)

    # Embaralhamento individual por usuário (o cache guarda a versão canônica;
    # st.cache_data devolve uma cópia, então mutação aqui é segura)
    generated = [shuffle_options(q) for q in generated]

    # Completar com questões fictícias somente se a geração falhou
    generated += [create_dummy_question(i + 1) for i in range(remaining - len(generated))]

    return bank_questions + generated

# Função para obter data e hora por extenso em português
def get_date_time_ptbr():
    now = datetime.now()

    # Listas de dias da semana e meses em português
    # weekday() retorna 0 para segunda-feira, alinhado com o índice da lista
    dias = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

    day_of_week = dias[now.weekday()]
    date_str = f"{now.day} de {meses[now.month - 1]} de {now.year}"
    time_str = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"

    return f"{day_of_week}, {date_str} às {time_str}"

# Função para resetar o estado do quiz (evita repetição de código)
def reset_quiz(clear_questions=False):
    if clear_questions:
        st.session_state.quiz = []
    st.session_state.current = 0
    st.session_state.score = 0
    st.session_state.show_explanation = False
    st.session_state.quiz_completed = False
    st.session_state.selected_answer = None
    st.session_state.celebrated = False

# Configuração do app Streamlit
st.set_page_config(page_title="Quiz App AI - por Ary Ribeiro", page_icon="🧾", layout="centered")
st.title("🧾 Quiz App AI 🤖")

# Validar a chave da API antes de qualquer coisa
if not API_KEY:
    st.error("⚠️ Chave da API não encontrada. Crie um arquivo `.env` na raiz do projeto com `OPENROUTER_API_KEY=sua_chave_aqui` e reinicie o app.")
    st.stop()

# Inicializar session state
if "quiz" not in st.session_state:
    st.session_state.quiz = []
if "current" not in st.session_state:
    st.session_state.current = 0
if "score" not in st.session_state:
    st.session_state.score = 0
if "show_explanation" not in st.session_state:
    st.session_state.show_explanation = False
if "quiz_completed" not in st.session_state:
    st.session_state.quiz_completed = False
if "selected_answer" not in st.session_state:
    st.session_state.selected_answer = None
if "celebrated" not in st.session_state:
    st.session_state.celebrated = False

# Temas fixos: strings idênticas para todos os usuários -> o cache global
# de geração acerta sempre, reduzindo drasticamente as chamadas à API.
# Os temas AWS são redigidos com os nomes dos serviços para o matching
# direcionar o banco curado e a ancoragem nos fatos certos.
TEMA_LIVRE = "✏️ Outro tema (digitar)"
TEMAS_FIXOS = {
    "AWS Cloud Practitioner": "AWS",
    "AWS AI Practitioner": (
        "AWS inteligência artificial e machine learning: Bedrock, SageMaker, "
        "Rekognition, Comprehend, Polly, Transcribe, Translate, Textract, Kendra, Lex"
    ),
    "AWS Developer Associate": (
        "AWS para desenvolvedores: Lambda, API Gateway, DynamoDB, SQS, SNS, ECS, "
        "Cognito, ElastiCache, CodePipeline, CodeBuild, CloudFormation, X-Ray"
    ),
    "AWS Solutions Architect Associate": (
        "arquitetura na AWS: EC2, S3, VPC, RDS, Aurora, CloudFront, Route 53, "
        "Elastic Load Balancing, Auto Scaling, EBS, EFS, KMS, CloudWatch, IAM"
    ),
    "Docker básico": "Docker básico: contêineres, imagens, Dockerfile, volumes, redes e comandos essenciais",
    "Kubernetes básico": "Kubernetes básico: pods, deployments, services, namespaces e kubectl",
    "Git e GitHub": "Git e GitHub: comandos, branches, merge, pull requests e fluxo de trabalho colaborativo",
    "Terraform": "Terraform: infraestrutura como código, providers, resources, variables, state e comandos essenciais",
    "Inglês": "língua inglesa: vocabulário, gramática e interpretação de frases em nível básico e intermediário",
    "Espanhol": "língua espanhola: vocabulário, gramática e interpretação de frases em nível básico e intermediário",
}

# Sidebar: configuração do quiz
with st.sidebar:
    st.header("Configuração")
    tema_escolhido = st.selectbox(
        "Tema",
        list(TEMAS_FIXOS.keys()) + [TEMA_LIVRE],
        help="Escolha um tema da lista (mais rápido) ou digite o seu"
    )
    if tema_escolhido == TEMA_LIVRE:
        topic = st.text_input("Tópico", "", help="Pode deixar em branco para um quiz geral de TI")
    else:
        topic = TEMAS_FIXOS[tema_escolhido]

    num = st.number_input("Número de questões", min_value=1, max_value=10, value=3,
                           help="Recomendamos no máximo 10 questões para evitar erros")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Iniciar Quiz"):
            with st.spinner("Gerando questões..."):
                quiz_data = generate_quiz(topic, num)
                if quiz_data and len(quiz_data) > 0:
                    reset_quiz()
                    st.session_state.quiz = quiz_data
                    st.rerun()
                else:
                    st.error("Não foi possível gerar o quiz. Tente novamente.")

    with col2:
        if st.button("Atualizar Cache", help="Limpa o cache global de questões geradas por IA (afeta todos os usuários)"):
            generate_ai_questions.clear()
            st.success("Cache global limpo. O próximo quiz gerará questões novas.")

# Exibir quiz
if st.session_state.quiz and len(st.session_state.quiz) > 0:
    total = len(st.session_state.quiz)

    if st.session_state.quiz_completed:
        # Exibir resultados finais
        st.progress(1.0)
        # Balões apenas uma vez, não a cada rerun da tela final
        if not st.session_state.celebrated:
            st.balloons()
            st.session_state.celebrated = True

        score_percentage = (st.session_state.score / total) * 100
        st.success(f"Quiz finalizado! Sua pontuação: {st.session_state.score}/{total} ({score_percentage:.1f}%)")

        col1, col2 = st.columns(2)
        with col1:
            # Refaz o MESMO quiz (mesmas questões), zerando o placar
            if st.button("🔁 Refazer este Quiz"):
                reset_quiz()
                st.rerun()
        with col2:
            # Descarta as questões atuais para gerar um quiz novo na sidebar
            if st.button("🆕 Novo Quiz"):
                reset_quiz(clear_questions=True)
                st.rerun()

    elif st.session_state.current < total:
        # Exibir a barra de progresso
        st.progress((st.session_state.current + 1) / total)
        st.write(f"Progresso: {st.session_state.current + 1}/{total}")

        # Exibir pergunta atual
        q = st.session_state.quiz[st.session_state.current]
        st.subheader(f"Pergunta {st.session_state.current + 1}")
        # Origem da questão: banco validado por humano ou gerada por IA
        if q.get("source") == "banco":
            st.caption("📚 Questão do banco validado")
        elif q.get("source") == "ia":
            selo = "🤖 Questão gerada por IA"
            if q.get("verified"):
                selo += " · aprovada em dupla checagem ✅"
            st.caption(selo)
        st.write(q["question"])

        options = q.get("options", {})
        if options:
            # index=None para não ter opção pré-selecionada;
            # desabilitado após responder, para deixar claro que a resposta foi registrada
            choice = st.radio(
                "Selecione uma opção:",
                [f"{k}. {v}" for k, v in options.items()],
                key=f"q{st.session_state.current}",
                index=None,
                disabled=st.session_state.show_explanation
            )

            if not st.session_state.show_explanation:
                if st.button("Responder", key="submit", disabled=choice is None):
                    selected = choice.split(".")[0]
                    st.session_state.selected_answer = selected
                    if selected == q["answer"]:
                        st.session_state.score += 1
                    st.session_state.show_explanation = True
                    st.rerun()
            else:
                # Feedback renderizado a partir do session_state: persiste em
                # qualquer rerun até o usuário avançar para a próxima pergunta
                if st.session_state.selected_answer == q["answer"]:
                    st.success("Correto! ✅")
                else:
                    correct = q["answer"]
                    st.error(f"Incorreto ❌ Resposta correta: {correct}. {options[correct]}")
                st.write(f"**Explicação:** {q['explanation']}")

                if st.session_state.current + 1 < total:
                    if st.button("Próxima pergunta", key="next"):
                        st.session_state.current += 1
                        st.session_state.show_explanation = False
                        st.session_state.selected_answer = None
                        st.rerun()
                else:
                    if st.button("Finalizar Quiz", key="finish"):
                        st.session_state.quiz_completed = True
                        st.rerun()
    else:
        st.error("Índice de questão inválido. Reinicie o quiz.")
        if st.button("Reiniciar Quiz"):
            reset_quiz(clear_questions=True)
            st.rerun()

# Rodapé com data e hora por extenso (valor inicial renderizado pelo servidor)
st.markdown(f"""
<div id="footer-relogio">
    {get_date_time_ptbr()}
</div>
""", unsafe_allow_html=True)

# Relógio ao vivo: JS injetado no documento pai atualiza o rodapé a cada segundo
# (st.markdown não executa <script>, por isso usamos components.html)
components.html("""
<script>
    const dias = ["Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"];
    const meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
    function atualizarRelogio() {
        const el = window.parent.document.getElementById("footer-relogio");
        if (!el) return;
        const agora = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        el.textContent = dias[agora.getDay()] + ", " + agora.getDate() + " de " + meses[agora.getMonth()] +
            " de " + agora.getFullYear() + " às " + pad(agora.getHours()) + ":" + pad(agora.getMinutes()) + ":" + pad(agora.getSeconds());
    }
    atualizarRelogio();
    setInterval(atualizarRelogio, 1000);
</script>
""", height=0)

st.markdown("""
<style>
    .main {
        margin-bottom: 50px; /* Espaço para o rodapé fixo */
    }
    .block-container {
        padding-top: 1rem;
        padding-bottom: 3rem; /* Padding inferior para o rodapé */
    }
    /* Rodapé fixo com suporte a tema claro e escuro */
    #footer-relogio {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background-color: #f0f2f6;
        color: #333333;
        padding: 10px;
        text-align: center;
        font-size: 18px;
        border-top: 1px solid #e0e0e0;
        z-index: 999;
    }
    @media (prefers-color-scheme: dark) {
        #footer-relogio {
            background-color: #262730;
            color: #fafafa;
            border-top: 1px solid #3d3d4d;
        }
    }
    /* Esconde completamente todos os elementos da barra padrão do Streamlit */
    header {display: none !important;}
    footer {display: none !important;}
    #MainMenu {display: none !important;}
    /* Remove qualquer espaço em branco adicional */
    div[data-testid="stAppViewBlockContainer"] {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    div[data-testid="stVerticalBlock"] {
        gap: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    /* Remove quaisquer margens extras */
    .element-container {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }
</style>
""", unsafe_allow_html=True)
