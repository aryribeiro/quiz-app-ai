# 🧾 Quiz App AI 🤖

Uma aplicação web interativa que gera quizzes de múltipla escolha sobre qualquer tópico usando IA generativa.

## 📋 Descrição

Quiz App AI é uma ferramenta educativa desenvolvida com Streamlit e alimentada por IA através da API OpenRouter. O aplicativo permite gerar questões de múltipla escolha personalizadas sobre qualquer tema de interesse, tornando o aprendizado mais dinâmico e interativo.

## ✨ Funcionalidades

- 🎯 Geração de quizzes personalizados sobre qualquer tópico de TI
- 🔢 Configuração do número de questões (1-10)
- 💾 Sistema de cache para reduzir chamadas à API
- ✅ Validação e verificação automática de respostas
- 📊 Pontuação final com estatísticas de desempenho
- 🌐 Interface limpa e intuitiva
- 📅 Exibição de data e hora em português no rodapé

## 🚀 Como instalar

1. Clone este repositório:
```bash
git clone https://github.com/seu-usuario/quiz-app-ai.git
cd quiz-app-ai
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Crie um arquivo `.env` na raiz do projeto com sua chave API:
```
OPENROUTER_API_KEY=sua_chave_api_aqui
```

## 🏃‍♂️ Como executar

Execute o aplicativo com o seguinte comando:
```bash
streamlit run app.py
```

O aplicativo estará disponível em `http://localhost:8501`

## 🔧 Configuração

Para usar esta aplicação, você precisará:

1. Criar uma conta em [OpenRouter](https://openrouter.ai/)
2. Obter uma chave de API
3. Adicionar esta chave ao arquivo `.env`

## 🖥️ Exemplo de uso

1. Escolha um tópico de interesse no campo "Tópico" (ou deixe em branco para um quiz geral de TI)
2. Defina o número de questões (1-10)
3. Clique em "Iniciar Quiz"
4. Responda às questões selecionando as opções
5. Veja sua pontuação final ao término do quiz

## 🧠 Como funciona

O aplicativo utiliza a API OpenRouter para acessar modelos de linguagem avançados que geram questões de múltipla escolha sobre o tópico solicitado. O sistema valida as respostas recebidas, garantindo que todas as questões tenham o formato correto antes de apresentá-las ao usuário.

## 📝 Licença

Este projeto está licenciado sob a [MIT License](LICENSE).

## 👨‍💻 Autor

Desenvolvido com ❤️ por Ary Ribeiro
aryribeiro@gmail.com

---

🔧 **Tecnologias utilizadas:**
- Python
- Streamlit
- OpenRouter API (acesso a modelos de IA)
- Locale (para formatação de data e hora em português)