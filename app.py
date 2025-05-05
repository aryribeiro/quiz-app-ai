import os
import json
import requests
import re
import time
import hashlib
from dotenv import load_dotenv
import streamlit as st
from datetime import datetime
import locale

# Configurar o locale para português do Brasil
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except:
        try:
            locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil')
        except:
            pass  # Se todas as tentativas falharem, usaremos uma abordagem manual

# Carregar chave API do arquivo .env
load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "gpt-3.5-turbo"

# Função para criar um hash único para cada tema + número de questões
def get_cache_key(topic, num_questions):
    return hashlib.md5(f"{topic}_{num_questions}".encode()).hexdigest()

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

# Função para criar e verificar uma questão de múltipla escolha
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

# Função para validar e corrigir as questões geradas
def validate_quiz_data(quiz_data, num_questions):
    valid_quiz = []
    
    # Se o quiz_data não for uma lista ou estiver vazio, retorna questões fictícias
    if not isinstance(quiz_data, list) or len(quiz_data) == 0:
        for i in range(num_questions):
            valid_quiz.append(create_dummy_question(i+1))
        return valid_quiz
    
    # Verifica cada questão e corrige se necessário
    for i, question in enumerate(quiz_data):
        if not isinstance(question, dict):
            valid_quiz.append(create_dummy_question(i+1))
            continue
            
        # Verifica campos obrigatórios
        required_fields = ["question", "options", "answer", "explanation"]
        valid = all(field in question for field in required_fields)
        
        # Verifica se options é um dicionário com pelo menos 2 opções
        if valid and isinstance(question["options"], dict) and len(question["options"]) >= 2:
            # Verifica se a resposta existe nas opções
            if question["answer"] in question["options"]:
                valid_quiz.append(question)
            else:
                # Se a resposta não existir nas opções, corrige para a primeira opção
                corrected = question.copy()
                corrected["answer"] = list(question["options"].keys())[0]
                valid_quiz.append(corrected)
        else:
            valid_quiz.append(create_dummy_question(i+1))
    
    # Se temos menos questões do que o solicitado, adiciona questões extras
    while len(valid_quiz) < num_questions:
        valid_quiz.append(create_dummy_question(len(valid_quiz)+1))
    
    # Limita ao número solicitado
    return valid_quiz[:num_questions]

# Função para gerar quiz via OpenRouter
def generate_quiz(topic: str, num_questions: int):
    # Limitar número de questões para evitar sobrecarga na API
    num_questions = min(num_questions, 10)
    
    # Usar um tópico padrão se estiver em branco
    topic_to_use = "tecnologia da informação geral" if not topic.strip() else topic
    
    # Verificar se já temos este quiz em cache
    cache_key = get_cache_key(topic_to_use, num_questions)
    if "quiz_cache" not in st.session_state:
        st.session_state.quiz_cache = {}
    
    # Se temos no cache e não estamos forçando atualização, use o cache
    if cache_key in st.session_state.quiz_cache and not st.session_state.get("force_refresh", False):
        return st.session_state.quiz_cache[cache_key]
    
    # Resetar flag de atualização forçada
    st.session_state.force_refresh = False
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = (
        f"Gere {num_questions} questões de múltipla escolha sobre o tópico '{topic_to_use}'. "
        "Para cada questão, forneça: "
        "1. A pergunta clara e objetiva "
        "2. Quatro opções de resposta (A, B, C, D) "
        "3. A letra da opção correta (A, B, C ou D) "
        "4. Uma explicação curta da resposta "
        "Retorne um array JSON onde cada elemento tem as chaves: 'question', 'options' (com opções A, B, C, D), "
        "'answer' (letra da opção correta), e 'explanation'. "
        "Todos os textos devem estar em português brasileiro. "
        "Evite usar caracteres especiais, formatação ou espaços adicionais. "
        "Forneça apenas o array JSON puro sem texto explicativo adicional."
    )
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Você é um assistente útil que gera questões de múltipla escolha em formato JSON puro. Não inclua explicações ou texto fora do JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # Limpar e corrigir o JSON recebido
        cleaned_content = clean_json_string(content)
        
        # Tentar fazer parse do JSON
        try:
            quiz_data = json.loads(cleaned_content)
            # Validar e corrigir o quiz
            valid_quiz = validate_quiz_data(quiz_data, num_questions)
            
            # Salvar no cache
            st.session_state.quiz_cache[cache_key] = valid_quiz
            return valid_quiz
            
        except json.JSONDecodeError as json_err:
            st.error(f"Erro ao processar JSON: {str(json_err)}")
            st.code(cleaned_content)
            
            # Criar quiz fictício em caso de erro
            dummy_quiz = [create_dummy_question(i+1) for i in range(num_questions)]
            st.session_state.quiz_cache[cache_key] = dummy_quiz
            return dummy_quiz
            
    except Exception as e:
        st.error(f"Erro ao gerar quiz: {str(e)}")
        # Criar quiz fictício em caso de erro
        dummy_quiz = [create_dummy_question(i+1) for i in range(num_questions)]
        st.session_state.quiz_cache[cache_key] = dummy_quiz
        return dummy_quiz

# Função para obter data e hora por extenso em português
def get_date_time_ptbr():
    now = datetime.now()
    
    # Lista de dias da semana e meses em português
    dias = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    
    # Usar sempre a implementação manual para garantir que esteja em português
    # O índice weekday() retorna 0 para segunda-feira, então usamos (now.weekday() + 6) % 7 para que 0 seja domingo
    day_index = (now.weekday() + 1) % 7  # Converter para domingo=0, segunda=1, etc.
    day_of_week = dias[day_index]
    date_str = f"{now.day} de {meses[now.month-1]} de {now.year}"
    time_str = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
    
    return f"{day_of_week}, {date_str} às {time_str}"

# Configuração do app Streamlit
st.set_page_config(page_title="Quiz App AI - por Ary Ribeiro", page_icon="🧾", layout="centered")
st.title("🧾 Quiz App AI 🤖")

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
if "selected_option" not in st.session_state:
    st.session_state.selected_option = None

# Sidebar: configuração do quiz
with st.sidebar:
    st.header("Configuração")
    topic = st.text_input("Tópico", "", help="Pode deixar em branco para um quiz geral de TI")
    num = st.number_input("Número de questões", min_value=1, max_value=10, value=3, 
                           help="Recomendamos no máximo 10 questões para evitar erros")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Iniciar Quiz"):
            with st.spinner("Gerando questões..."):
                quiz_data = generate_quiz(topic, num)
                if quiz_data and len(quiz_data) > 0:
                    st.session_state.quiz = quiz_data
                    st.session_state.current = 0
                    st.session_state.score = 0
                    st.session_state.show_explanation = False
                    st.session_state.quiz_completed = False
                    st.session_state.selected_option = None
                    st.rerun()
                else:
                    st.error("Não foi possível gerar o quiz. Tente novamente.")
    
    with col2:
        if st.button("Atualizar Cache"):
            st.session_state.force_refresh = True
            st.success("Cache será atualizado na próxima execução")

# Exibir quiz
if st.session_state.quiz and len(st.session_state.quiz) > 0:
    # Verificar se o índice atual é válido
    if st.session_state.current < len(st.session_state.quiz):
        # Exibir a barra de progresso corretamente
        if st.session_state.quiz_completed:
            progress = st.progress(1.0)  # 100% completo
        else:
            progress = st.progress((st.session_state.current + 1) / len(st.session_state.quiz))
        st.write(f"Progresso: {st.session_state.current + 1}/{len(st.session_state.quiz)}")
        
        # Exibir pergunta atual
        if not st.session_state.quiz_completed:
            q = st.session_state.quiz[st.session_state.current]
            st.subheader(f"Pergunta {st.session_state.current + 1}")
            st.write(q["question"])
            
            options = q.get("options", {})
            if options:
                # Usar None como valor padrão para não ter opção pré-selecionada
                choice = st.radio(
                    "Selecione uma opção:", 
                    [f"{k}. {v}" for k, v in options.items()], 
                    key=f"q{st.session_state.current}",
                    index=None  # Isso fará com que nenhuma opção seja pré-selecionada
                )
                
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    if not st.session_state.show_explanation:
                        if st.button("Responder", key="submit", disabled=choice is None):
                            selected = choice.split(".")[0]
                            if selected == q["answer"]:
                                st.success("Correto! ✅")
                                st.session_state.score += 1
                            else:
                                correct = q["answer"]
                                st.error(f"Incorreto ❌ Resposta correta: {correct}. {options[correct]}")
                            st.session_state.show_explanation = True
                            st.write(f"**Explicação:** {q['explanation']}")
                
                with col2:
                    if st.session_state.show_explanation:
                        if st.session_state.current + 1 < len(st.session_state.quiz):
                            if st.button("Próxima pergunta", key="next"):
                                st.session_state.current += 1
                                st.session_state.show_explanation = False
                                st.rerun()
                        else:
                            if st.button("Finalizar Quiz", key="finish"):
                                st.session_state.quiz_completed = True
                                st.rerun()
        else:
            # Exibir resultados finais
            st.balloons()
            score_percentage = (st.session_state.score / len(st.session_state.quiz)) * 100
            st.success(f"Quiz finalizado! Sua pontuação: {st.session_state.score}/{len(st.session_state.quiz)} ({score_percentage:.1f}%)")
            
            # Botão para reiniciar
            if st.button("Iniciar Novo Quiz"):
                # Não limpamos o cache, apenas o estado atual
                st.session_state.current = 0
                st.session_state.score = 0
                st.session_state.show_explanation = False
                st.session_state.quiz_completed = False
                st.rerun()
    else:
        st.error("Índice de questão inválido. Reinicie o quiz.")
        if st.button("Reiniciar Quiz"):
            st.session_state.quiz = []
            st.session_state.current = 0
            st.session_state.score = 0
            st.session_state.show_explanation = False
            st.session_state.quiz_completed = False
            st.rerun()

# Adicionar data e hora por extenso no rodapé
data_hora_atual = get_date_time_ptbr()
st.markdown(f"""
<div style="position: fixed; bottom: 0; left: 0; right: 0; background-color: #f0f2f6; padding: 10px; text-align: center; font-size: 18px; border-top: 1px solid #e0e0e0;">
    {data_hora_atual}
</div>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    .main {
        background-color: #ffffff;
        color: #333333;
        margin-bottom: 50px; /* Adicionar espaço para o rodapé */
    }
    .block-container {
        padding-top: 1rem;
        padding-bottom: 3rem; /* Aumentar padding inferior para o rodapé */
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