# OFFTEC AI HUNTER

**Plataforma de análise defensiva para Termux e Android**, com interface de terminal, projetos, escopo autorizado, tarefas em segundo plano, assistente de IA e relatórios locais.

> Use a ferramenta somente em sistemas próprios ou para os quais você tenha autorização explícita. As análises são limitadas e não substituem uma auditoria profissional.

## Visão geral

O OFFTEC AI HUNTER reúne verificações de segurança e acompanhamento de evidências em uma aplicação Python para terminal. Projetos, escopos, conversas, tarefas e achados são mantidos em SQLite local. A interface funciona sem root, Docker ou ambiente gráfico.

### Recursos

- Interface navegável por teclado, adaptada ao terminal do Termux.
- Projetos com escopo autorizado persistente por host.
- Tarefas em segundo plano, registro de eventos, progresso e cancelamento.
- Assistente com histórico de conversa e respostas em streaming.
- Integração opcional com Codex App Server e provedores compatíveis.
- Análises defensivas de HTTP/TLS, rede, API, configuração web e amostras offline de SQL/XSS.
- Relatórios HTML, JSON e TXT, com evidências e recomendações.
- Português brasileiro, inglês, espanhol, árabe e hindi.

## Requisitos

- Termux atualizado, preferencialmente da fonte oficial F-Droid ou GitHub.
- Python 3 e pip disponíveis no Termux.
- Conexão com a internet para consultas de rede e provedores de IA.
- Ferramentas externas como Nmap, SQLMap e Nuclei são opcionais e devem ser instaladas separadamente por fontes confiáveis.

O aplicativo não requer root. Algumas operações dependem de ferramentas opcionais e podem não estar disponíveis em todas as arquiteturas ou repositórios.

## Instalação

```sh
pkg update
pkg install python git
git clone https://github.com/Mcsd7/OFFTEC-AI-HUNTER.git
cd OFFTEC-AI-HUNTER
sh install.sh
```

O instalador verifica o ambiente, prepara o diretório de dados e inicializa o SQLite. Ele não instala automaticamente scanners externos.

## Iniciar

```sh
cd ~/OFFTEC-AI-HUNTER
python main.py
```

Use as setas e Enter para navegar. Esc retorna nos menus; no chat, Esc volta e Q sai da conversa sem fechar o aplicativo. Ctrl+C encerra o aplicativo. Os atalhos `/report`, `/help` e `/scan` continuam disponíveis.

## Primeiros passos

1. Abra **Projetos** e selecione ou crie um projeto.
2. Em **Escopo autorizado**, cadastre hosts que você tem permissão para analisar.
3. Selecione um módulo no menu principal e siga as confirmações apresentadas.
4. Acompanhe a tarefa no monitor e consulte os achados em **Relatórios** ou **Histórico**.
5. Para usar o assistente, configure Codex ou um provedor em **Configurações → Provedores de IA**.

Uma confirmação na interface não concede autorização legal sobre um alvo. Analise somente sistemas sob seu controle ou cobertos por autorização formal.

## Módulos disponíveis

| Módulo | O que faz | Limites principais |
| --- | --- | --- |
| Web e TLS | Consulta HTTP limitada e inspeção de cabeçalhos e certificado | Não comprova explorabilidade de uma falha |
| Rede | Verificação TCP conservadora de portas comuns | Nmap opcional; fallback limitado quando ausente |
| Reconhecimento | Resolução DNS e consulta reversa local | Não enumera subdomínios nem executa WHOIS |
| API | Verifica caminhos fixos de documentação e configuração CORS | Não faz crawling nem baixa conteúdo amplo |
| Vulnerabilidades | Verificações passivas; Nuclei opcional para misconfiguration de baixo impacto | Templates e severidades limitados |
| SQL | Revisão offline de mensagens de erro; SQLMap opcional | SQLMap exige escopo e confirmação explícita |
| XSS | Revisão offline de fragmentos HTML fornecidos pelo usuário | Não envia payloads a sites |
| Ativos web | Consulta HEAD a caminhos públicos fixos | Não usa wordlists nem crawler |
| Assistente | Conversa persistente com Codex ou provedor configurado | A IA não executa comandos arbitrários; análises são iniciadas pelos módulos |
| Laboratório | Exercícios locais de interpretação de SQL, XSS e HTTP | Não inicia aplicações vulneráveis nem envia tráfego externo |

### Ferramentas opcionais

O inventário detecta Nmap, SQLMap, Nuclei, httpx, WhatWeb, Subfinder, DNSx e Wafw00f. Nesta versão, somente Nmap, SQLMap e Nuclei possuem adaptadores de execução. Um executável `httpx` pode ser a biblioteca Python HTTPX, e não o scanner do ProjectDiscovery; o OFFTEC não o executa como scanner.

Verifique compatibilidade com Termux/ARM64 e use repositórios oficiais antes de instalar ferramentas externas. A aplicação não baixa binários de fontes desconhecidas.

## Assistente e provedores de IA

O Codex CLI é o mecanismo padrão. A integração usa o Codex App Server via JSON-RPC e exibe o streaming dentro da conversa OFFTEC. O app-server inicia em modo somente leitura; pedidos de aprovação para execução de comandos ou alteração de arquivos são recusados.

Também é possível configurar Gemini, Groq ou um endpoint compatível com OpenAI em **Configurações → Provedores de IA**. Configure URL, modelo e chave, teste a conexão e selecione explicitamente o provedor. URLs externas devem usar HTTPS; HTTP é aceito somente em loopback.

As chaves são armazenadas em arquivo privado separado do banco SQLite. Mensagens enviadas a um provedor externo ficam sujeitas às políticas desse serviço. Use somente provedores confiáveis.

## Segurança e privacidade

- O escopo é salvo por projeto e validado novamente antes da execução.
- Operações direcionadas exigem confirmação explícita.
- As ferramentas são chamadas com argumentos estruturados, limites e timeout; o modelo não recebe execução arbitrária de shell.
- Saídas de subprocessos têm limite e passam por sanitização de dados sensíveis.
- Banco, configurações, conversas e exports ficam localmente no dispositivo.
- Não há funções de malware, evasão, persistência ou coleta de credenciais.

Os dados ficam em `~/.offtec-ai-hunter` por padrão. Defina `OFFTEC_HOME` para usar outro diretório:

```sh
export OFFTEC_HOME="$HOME/offtec-data"
python main.py
```

## Idiomas

O idioma inicial é português brasileiro. English, Español, العربية e हिन्दी podem ser escolhidos no menu **Configurações de idioma**. A preferência é salva localmente. A renderização RTL do árabe depende do terminal e da fonte instalados; os relatórios HTML definem a direção RTL.

## Desenvolvimento e testes

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Os testes cobrem navegação, leitura de teclado em pseudo-terminal, módulos, persistência e relatórios. Testes que dependem de Codex real precisam do Codex CLI instalado e autenticado.

## Limitações conhecidas

- A conversa com IA interpreta e contextualiza solicitações, mas ainda não seleciona e executa módulos automaticamente por linguagem natural.
- Não existe instalador automático de scanners; ferramentas opcionais precisam ser instaladas pelo usuário.
- WHOIS, enumeração de subdomínios, feed CVE, crawler e exploração SQL/XSS remota não estão implementados.
- O cancelamento de algumas operações de biblioteca de rede pode aguardar o timeout configurado.
- PDF é obtido abrindo o relatório HTML no navegador Android e usando **Imprimir → Salvar como PDF**.

## Licença

Consulte o arquivo [LICENSE](LICENSE).
