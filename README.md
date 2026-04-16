# Vast.ai Manager

App desktop local (Windows) para gerenciar suas instâncias já existentes na Vast.ai.
Construído com **PySide6** e o **vastai Python SDK** oficial.

Foco: ligar/desligar instâncias, abrir conexão SSH automaticamente, visualizar métricas e créditos.
**Não cria e não destrói instâncias** — apenas gerencia as que você já tem.

---

## Funcionalidades

- 💰 Saldo, taxa de gasto atual e autonomia estimada no topo
- 📊 Gasto diário aproximado (cálculo local)
- 🖥️ Lista de instâncias em cards, com métricas ao vivo: GPU / CPU / RAM / Disco / Rede / Temp
- ▶️ **Ativar** uma instância parada com um clique
- 🔗 **Conexão automática** — ao ativar, o túnel SSH sobe sozinho
- 🔘 **Abrir Terminal** — abre uma sessão SSH no Windows Terminal (fallback cmd.exe)
- 🔌 **Desconectar** / **Desativar** com confirmação
- 📝 Painel de logs de ações e falhas
- 🌑 Visual dark, clean, sem dependências pesadas

---

## Requisitos

- **Windows 10/11** (Linux/macOS funcionam na maior parte, mas o terminal launcher é otimizado para Windows)
- **Python 3.10 ou superior**
- **OpenSSH client** habilitado
  - Win+R → `optionalfeatures` → marque "Cliente OpenSSH"
  - Ou: `Settings → Apps → Optional features → Add → OpenSSH Client`
- Sua **chave SSH** já registrada na Vast.ai
- Opcional: **Windows Terminal** (instala da Microsoft Store) — melhora o visual de `Abrir Terminal`

---

## Instalação

```bash
# 1. Entre na pasta do projeto
cd vastai-app

# 2. (Opcional, mas recomendado) Crie um venv
python -m venv .venv
.venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt
```

**Dependências instaladas:**
- `PySide6` — GUI Qt6
- `vastai` — SDK oficial da Vast.ai
- `qtawesome` — ícones
- `pytest` — testes unitários

---

## Como rodar

```bash
python main.py
```

Na primeira execução:
1. O app abre a tela de **Configurações** automaticamente
2. Cole sua **API key da Vast.ai** (você encontra em https://cloud.vast.ai/account/)
3. Clique em **Testar conexão** → deve aparecer "✓ Conectado. Saldo atual: $X.XX"
4. Clique em **Salvar**
5. Suas instâncias aparecem na tela principal

---

## Onde a API key fica salva

Arquivo: `%USERPROFILE%\.vastai-app\config.json`

Exemplo:
```json
{
  "api_key": "c8a3...",
  "refresh_interval_seconds": 30,
  "default_tunnel_port": 11434,
  "terminal_preference": "auto",
  "auto_connect_on_activate": true,
  "schema_version": 1
}
```

> **Atenção:** nesta primeira versão a API key é salva em texto puro. Se for preocupação, proteja o arquivo via permissões do NTFS ou use uma API key limitada (somente leitura + start/stop). A estrutura de config está preparada para ganhar criptografia em uma versão futura.

---

## Fluxo típico de uso

1. Abra o app — veja saldo, instâncias e métricas
2. Em uma instância parada, clique **Ativar**
   - Card vira "Ativando..." → depois "Conectando..." → por fim "● Conectado"
   - O túnel SSH é aberto em background em `http://127.0.0.1:11434`
   - O endereço fica visível no card, com botão **Copiar**
3. Clique em **Abrir Terminal** quando quiser SSH interativo
4. Ao fim, clique **Desconectar** ou **Desativar** (confirma antes de desligar)

---

## Testes

```bash
python -m pytest tests/ -v
```

25 testes unitários cobrem: models, config, parsing da API da Vast, math de billing, command builders SSH/tunnel.

---

## Estrutura

```
vastai-app/
├── main.py                      # Entry point
├── requirements.txt
├── README.md
├── app/
│   ├── config.py                # Load/save JSON config
│   ├── models.py                # Instance, TunnelStatus, AppConfig
│   ├── theme.py                 # Palette + QSS stylesheet
│   ├── billing.py               # Burn rate, autonomy, daily tracker
│   ├── services/
│   │   ├── vast_service.py      # Vast SDK wrapper
│   │   └── ssh_service.py       # SSH subprocess manager
│   ├── workers/
│   │   ├── list_worker.py       # Polling de instâncias (QThread)
│   │   ├── action_worker.py     # Start/stop (QThread)
│   │   └── tunnel_starter.py    # Espera instância + abre túnel (QThread)
│   └── ui/
│       ├── main_window.py
│       ├── settings_dialog.py
│       ├── billing_header.py
│       ├── instance_card.py
│       ├── metric_bar.py
│       ├── toast.py
│       └── log_panel.py
├── tests/                       # 25 testes unitários
└── docs/superpowers/
    ├── specs/2026-04-14-vastai-manager-design.md
    └── plans/2026-04-14-vastai-manager.md
```

---

## Empacotamento (gerar .exe standalone)

Para distribuir sem exigir Python instalado:

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name "Vast.ai Manager" ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtWidgets ^
    main.py
```

O executável aparece em `dist\Vast.ai Manager\Vast.ai Manager.exe`.

> Dica: se quiser um único `.exe`, troque `--windowed` por `--windowed --onefile`. Fica ~100 MB por causa do Qt embutido.

---

## Limitações conhecidas (v1)

- **Sem criptografia da API key** — fica em texto puro no `config.json`.
- **Gasto de hoje é aproximado** — calculado localmente a cada refresh (delta × dph). Reinicia ao reabrir o app. O histórico real está no painel da Vast.
- **Um túnel por instância** — a porta local é a mesma do arquivo de config (default 11434). Para 2 instâncias simultâneas com a mesma porta haveria colisão; rode uma ativa por vez com túnel no default.
- **Timeout fixo de 90s** para aguardar a instância virar `running` após Ativar. Se sua máquina demora mais (imagem muito grande), tente **Tentar novamente** após o timeout.
- **Não cria nem destrói instâncias** — fora do escopo desta versão. Use o painel da Vast para isso.
- **Não mostra offers / marketplace.** Idem.
- **Reconexão automática** depois de queda do túnel é manual (clique em Tentar novamente). Evita loops infinitos quando há problema persistente.
- **Tray icon não implementado** na v1 (estrutura pronta para v2).

---

## Próximos passos (seguros, incrementais)

1. **Porta de túnel por instância** — hoje é global, pode virar um campo opcional por card.
2. **Criptografia simples da API key** — ex: Windows DPAPI (sem dependência extra no Windows).
3. **Sparkline de GPU util** nos cards (histórico in-memory dos últimos N pontos via QPainter).
4. **System tray** — menu rápido para ativar/desativar sem abrir a janela principal.
5. **Retry automático com backoff** do túnel quando cai (1 tentativa já existe, dá pra dar 2 com espera).
6. **Export/import de config** para migrar entre máquinas.
7. **Internacionalização** — textos hoje em PT-BR, dá pra extrair para `.ts` e suportar EN.

---

## Solução de problemas

**"SSH não encontrado"** → habilite o OpenSSH em Optional Features (ver Requisitos).

**"Porta 11434 ocupada"** → troque em `⚙ Configurações → Porta local padrão`.

**API key inválida** → gere uma nova em https://cloud.vast.ai/account/ e cole em Configurações.

**Túnel cai sozinho** → veja a mensagem no painel de log (canto inferior). Geralmente é Wi-Fi instável ou a instância sem disco. Clique em **Tentar novamente**.

**App não abre** → rode `python main.py` no terminal e compartilhe o traceback.

---

## Licença

Projeto pessoal / uso interno. Adapte como preferir.
