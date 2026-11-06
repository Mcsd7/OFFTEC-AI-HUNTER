# OFFTEC AI HUNTER

Central de análise defensiva em Python para Android/Termux, com interface de terminal própria, projetos, escopo autorizado, tarefas em segundo plano, chat interno, persistência SQLite e relatórios. Idioma inicial: português brasileiro. O aplicativo não exige root, Docker nem ambiente gráfico.

## Instalação e inicialização

```sh
pkg update
pkg install python git
cd ~/OFFTEC-AI-HUNTER
sh install.sh
python main.py
```

O instalador não substitui configurações existentes. Os dados ficam em `~/.offtec-ai-hunter` (permissão privada) ou em `OFFTEC_HOME`, se definido. Para executar testes:

```sh
python -m pytest -q
```

Em uma instalação sem pytest, instale as dependências de desenvolvimento com `python -m pip install -r requirements-dev.txt`.

## Interface e idiomas

Use ↑/↓ e Enter para navegar; ←/→ também percorrem opções; Esc retorna de menus; Tab/Shift+Tab alternam entre menu e painel de estado; Ctrl+C encerra a interface e solicita cancelamento das tarefas. `j`/`k` são alternativas apenas em listas. O leitor de teclas reconhece CSI, SS3/aplicação, teclas modificadas e Backtab usando leitura direta de bytes do TTY. Os campos de texto continuam usando a edição normal de linha e não recebem interceptação das setas. No chat, `/q` retorna, `/new` cria conversa, `/rename`, `/delete`, `/export`, `/report`, `/help` e `/scan web URL` estão disponíveis. Para comandos de chat e texto, use o teclado do Termux.

A interface de produção usa Rich/ANSI e leitura do TTY, não widgets Textual. Os testes de navegação com Textual Pilot exercitam o mesmo controlador de foco usado pela interface; os testes de pseudo-terminal acionam também o leitor e o menu reais. Instale as dependências de desenvolvimento antes de executar Pilot.

O menu principal e Configurações incluem **Configurações de idioma**. Português (pt-BR) é o padrão; English, Español, العربية e हिन्दी são persistidos sem remover projetos, mensagens ou histórico. Catálogos UTF-8 ficam em `locales/`. Relatórios usam o idioma selecionado e HTML em árabe define `dir=rtl`; a apresentação RTL na tela depende do emulador e da fonte do Termux. O mecanismo de IA recebe a instrução de idioma. Identificadores, comandos, URLs e nomes de ferramentas permanecem sem tradução.

## Codex CLI

Codex é o mecanismo padrão. O adaptador usa o protocolo JSON-RPC de linhas do `codex app-server --listen stdio://`, detecta versão e autenticação com o CLI instalado e mantém o identificador da thread no registro da conversa. A resposta em streaming aparece dentro do chat OFFTEC; não há terminal Codex separado. Conversas e sessões continuam no projeto após reiniciar.

No Termux testado, o binário Node que acompanha o CLI falhava ao resolver o símbolo nativo `_ZNSt6__ndk113__hash_memoryEPKvm`. O adaptador confirmou o erro e passou a testar automaticamente `libc++_shared.so` do próprio prefixo, usando `LD_PRELOAD` apenas nos processos Codex filhos. Com o preload, `codex --version`, `codex login status` e um turno real pelo app-server foram executados com sucesso neste ambiente. Isso não altera bibliotecas do sistema. Em outra instalação, consulte **Configurações → Estado do Codex** para diagnóstico.

Autentique o CLI pelo processo suportado pelo próprio Codex antes de usar o chat. O app-server é iniciado com sandbox somente leitura, acesso de rede desativado para os turnos e aprovações de comandos/alterações de arquivo recusadas pelo adaptador. A aplicação não concede execução de shell ao modelo. A análise de alvos é realizada pelos módulos explícitos da OFFTEC, sujeitos ao escopo.

## Provedores de IA

Além de Codex, o menu **Configurações → Provedores de IA** permite cadastrar Gemini, Groq e endpoints OpenAI-compatible. URLs devem usar HTTPS; HTTP só é aceito em loopback. A chave é armazenada em arquivo JSON privado separado do SQLite (`secrets.json`, modo 0600 quando suportado), nunca em histórico ou relatório. O endpoint compatível deve implementar `/chat/completions` com SSE. Gemini usa `streamGenerateContent`.

Cadastre a URL, o modelo e a chave; teste a conexão e selecione explicitamente o provedor. Não há troca silenciosa de provedor. Também é possível configurar um endpoint por `OFFTEC_AI_BASE_URL`, `OFFTEC_AI_MODEL` e `OFFTEC_AI_API_KEY`. A chave é armazenada em `secrets.json` com modo 0600 quando suportado. Credenciais enviadas a provedores externos e o histórico da conversa são processados por esse serviço; use somente endpoints confiáveis. Mensagens não são enviadas quando o motor selecionado está indisponível.

## Módulos e status funcional

| Módulo | Operação disponível | Dependências e limites |
|---|---|---|
| Web e SSL/TLS | Requisição HTTP HEAD sem redirecionamento; cabeçalhos, identificação limitada e inspeção TLS/certificado | Biblioteca padrão; timeout limitado; não confirma explorabilidade |
| SQL | Revisão offline de mensagens de erro; perfil controlado do SQLMap quando instalado | SQLMap não é incluído; exige escopo e confirmação explícita |
| Reconhecimento | Resolução DNS e consulta reversa local | Não executa enumeração de subdomínios ou WHOIS |
| Vulnerabilidades | Verificação passiva de configuração; templates Nuclei de misconfiguration info/low se disponível | Nuclei é opcional; correlação CVE/versionamento não é alegada sem evidência |
| API | HEAD em três caminhos fixos de documentação e verificação CORS de origem de teste | Tráfego ao alvo exige escopo e confirmação; conteúdo não é baixado |
| Rede | Nmap com TCP connect, 20 portas comuns e limites conservadores | Se Nmap faltar, fallback TCP de dez portas; não requer root |
| XSS | Revisão offline de fragmento HTML fornecido pelo usuário | Não envia payload nem valida contexto remoto |
| Diretórios/ativos | HEAD em quatro caminhos públicos fixos | Sem crawler/wordlist; escopo e confirmação obrigatórios |
| Assistente IA | Chat persistente, contexto de projeto, streaming Codex/provedor e análise de saída colada | Requer CLI autenticado ou provedor configurado |
| Relatórios | HTML, JSON e TXT, com achados, escopo, método, ferramenta, evidência, severidade, confiança e recomendações | PDF: abra o HTML no navegador Android e use Imprimir → Salvar como PDF |
| Laboratório | Exercícios offline de SQL, XSS e HTTP com evidências locais | Não inicia serviço vulnerável nem envia tráfego externo |
| Projetos/histórico/configurações | CRUD de projetos, hosts permitidos, conversas, tarefas e relatórios | Persistência SQLite local |

O inventário detecta Nmap, SQLMap, Nuclei, httpx, WhatWeb, Subfinder, DNSx e Wafw00f. Só Nmap, SQLMap e Nuclei têm adaptadores de execução nesta versão. O comando `httpx` encontrado em algumas instalações pode ser a ferramenta Python HTTPX, não o scanner ProjectDiscovery; a aplicação não o executa como scanner. Os demais utilitários aparecem como detectados/ausentes sem alegar integração funcional. Instale ferramentas opcionais somente por fontes confiáveis e confira compatibilidade ARM64/Termux.

## Escopo e segurança

Cada projeto mantém uma lista exata de hosts autorizados. Para uma operação direcionada, a interface exige confirmação explícita e `TaskManager` revalida o host antes da execução; uma suborigem não herda automaticamente a autorização do domínio pai. A IA não pode expandir escopo. O perfil Nmap usa TCP connect, SQLMap usa risk 1/level 1/uma thread/atraso de 1 s/timeout de 5 s, e Nuclei é restrito a tags de misconfiguration e severidade info/low sem interactsh. Requisições Python têm timeout e limites fixos. Saídas de subprocessos são limitadas e sanitizadas.

Use somente alvos próprios ou com autorização formal. Não há recursos de stealth, persistência, roubo de credenciais ou exploração destrutiva. Cancelamento via monitor de tarefas/Ctrl+C solicita interrupção; uma operação de biblioteca de rede pode levar até seu timeout para retornar.

## Armazenamento e dependências

O SQLite é criado/migrado de forma aditiva em `OFFTEC_HOME` ou `~/.offtec-ai-hunter`; projetos, escopos, conversas, mensagens, sessões Codex, tarefas, eventos, achados, relatórios e configurações são persistidos. A seleção de idioma fica em settings. Tokens não ficam no SQLite. Exports de conversa ficam em `exports/` com permissão privada quando suportada.

Python padrão é suficiente para iniciar. Rich (`requirements.txt`) habilita painéis e tabelas aprimorados; a interface ANSI continua disponível se Rich não puder ser instalado. Não há dependência de Textual, pois o controle de teclado cru e o diagnóstico do Termux precisam funcionar também sem ela. PDF depende da função de impressão do navegador Android.

## Diagnóstico

```sh
sh install.sh
python -m pytest -q
```

O instalador verifica Termux/arquitetura, Python/pip/Git, cria diretórios privados, inicializa banco e idioma, consulta Codex e lista ferramentas detectadas. A indisponibilidade de Codex não impede módulos locais nem provedores alternativos. Veja o estado real em Configurações; estado não testado não é apresentado como conectado.

## Limitações conhecidas

- A renderização RTL depende de suporte bidirecional do terminal; o HTML árabe tem atributo RTL.
- PDF é exportado pelo fluxo de impressão do Android a partir do HTML, não por biblioteca PDF incluída.
- WHOIS, enumeração de subdomínios, CVE feed, crawler e serviço de laboratório não estão implementados nesta versão e não são apresentados como ativos.
- Catálogos, banco e testes são independentes de serviços externos; o teste real Codex requer CLI instalado e login local.
