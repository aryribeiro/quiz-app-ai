Obs.: caso o app esteja no modo "sleeping" (dormindo) ao entrar, basta clicar no botão que estará disponível e aguardar, para ativar o mesmo. 
![print](https://github.com/user-attachments/assets/9c993151-866d-4d10-8bda-a72e25a37153)
# 🧾 Quiz App AI 🤖

Uma aplicação web interativa que gera quizzes de múltipla escolha sobre TI, certificações AWS, DevOps e idiomas — combinando um banco de questões validadas com IA generativa ancorada em fatos verificados.

## 📋 Descrição

Quiz App AI é uma ferramenta educativa desenvolvida com Streamlit e alimentada por IA através da API OpenRouter. Projetada para uso em sala de aula, ela usa uma arquitetura híbrida anti-alucinação: questões de temas AWS vêm prioritariamente de um banco curado e validado por humano, e as questões geradas por IA passam por ancoragem em uma base de conhecimento e por dupla checagem automática antes de chegarem ao aluno.

## ✨ Funcionalidades

- 🎯 Menu de temas prontos: certificações AWS (Cloud Practitioner, AI Practitioner, Developer Associate, Solutions Architect Associate), Docker, Kubernetes, Git e GitHub, Terraform, Inglês e Espanhol — ou tema livre digitado
- 📚 Banco com 51 questões AWS curadas e validadas (zero alucinação), com sorteio e alternativas reembaralhadas a cada quiz
- 🧠 Base de conhecimento com 235 serviços AWS (`servicos.json`) injetada no prompt para ancorar a geração por IA em fatos verificados
- ✅ Dupla checagem: cada questão gerada volta ao modelo para ser respondida às cegas; gabaritos inconsistentes são descartados automaticamente
- 🔒 JSON mode nativo na API — elimina erros de formato na geração
- ⚡ Cache global de 24h compartilhado entre usuários: a turma inteira no mesmo tema consome uma única chamada à API
- 🏷️ Selo de origem em cada questão: "📚 banco validado" ou "🤖 gerada por IA · dupla checagem ✅"
- 🔢 Configuração do número de questões (1-10)
- 📊 Feedback imediato com explicação, pontuação final e opções de refazer ou iniciar novo quiz
- 📅 Relógio ao vivo com data por extenso em português no rodapé

## 🚀 Como instalar

1. Clone este repositório:
```bash
git clone https://github.com/aryribeiro/quiz-app-ai.git
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

1. Escolha um tema no menu suspenso (ou selecione "✏️ Outro tema" e digite o seu)
2. Defina o número de questões (1-10)
3. Clique em "Iniciar Quiz"
4. Responda às questões e leia a explicação de cada resposta
5. Veja sua pontuação final e refaça o quiz ou inicie um novo

## 🧠 Como funciona

O app decide a fonte das questões conforme o tema:

1. **Temas AWS cobertos pelo banco** (ex.: Cloud Practitioner, S3, EC2): as questões são sorteadas do arquivo `questoes_aws.json` — validadas por humano, sem chamada à API e com alternativas reembaralhadas para evitar decoreba.
2. **Temas AWS fora do banco** (ex.: AI Practitioner, Braket): a IA gera questões ancorada nas descrições verificadas do `servicos.json`, instruída a usar exclusivamente esses fatos.
3. **Demais temas** (Docker, Git, idiomas etc.): geração por IA com prompt reforçado (exemplo few-shot, apenas fatos consensuais) em JSON mode.

Toda questão gerada por IA passa por **dupla checagem**: o modelo responde à própria questão sem ver o gabarito e, se a resposta independente divergir, a questão é descartada e reposta. A parte gerada fica em cache global por 24 horas, compartilhado entre todos os usuários do app.

## 📝 Licença

Este projeto está licenciado sob a [MIT License](LICENSE).

## 👨‍💻 Autor

Desenvolvido com ❤️ por Ary Ribeiro
aryribeiro@gmail.com

---

🔧 **Tecnologias utilizadas:**
- Python + Streamlit
- OpenRouter API (gpt-3.5-turbo com JSON mode)
- Banco de questões curadas (`questoes_aws.json`) e base de conhecimento AWS (`servicos.json`)
