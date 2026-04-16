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
