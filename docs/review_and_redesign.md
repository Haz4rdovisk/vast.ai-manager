# Vast.ai Manager — Full Review, Redesign & UIwizard Prompt

---

## 1. Inventário de Telas (Screen Inventory)

O app possui **9 telas/views** + **3 dialogs** organizados em uma arquitetura de sidebar + stacked views.

| # | Tela | Arquivo | Tipo |
|---|------|---------|------|
| 1 | **Instances** (Landing) | `ui/views/instances_view.py` | Main View |
| 2 | **Instance Card** | `ui/views/instance_card.py` | Component |
| 3 | **Billing Strip** | `ui/views/billing_strip.py` | Component |
| 4 | **Dashboard** (AI Lab) | `lab/views/dashboard_view.py` | Lab View |
| 5 | **Dashboard Card** | `ui/components/instance_dashboard_card.py` | Component |
| 6 | **Discover** (LLMfit) | `lab/views/discover_view.py` | Lab View |
| 7 | **Models** (GGUF Manager) | `lab/views/models_view.py` | Lab View |
| 8 | **Hardware Monitor** | `lab/views/hardware_view.py` + `hardware_card.py` | Lab View |
| 9 | **Monitor** (llama-server) | `lab/views/monitor_view.py` | Lab View |
| 10 | **Configure** (Server Params) | `lab/views/configure_view.py` | Lab View |
| 11 | **Settings Dialog** | `ui/settings_dialog.py` | Dialog |
| 12 | **Update Dialog** | `ui/dialogs.py` | Dialog |

### Componentes Compartilhados
- **NavRail** — Sidebar de navegação (220px fixa)
- **TitleBar** — Barra de título frameless customizada
- **GlassCard** — Superfície principal (card base)
- **StatusPill** — Badge de status colorido
- **MetricTile** — Tile de métrica grande
- **GaugeWidget** — Half-moon gauge customizado (QPainter)
- **NetworkSpeedWidget** — Widget de velocidade de rede
- **ModelConfigForm** — Formulário de configuração de modelo
- **Toast** — Notificação toast empilhável

---

## 2. Review por Tela

### 🖥️ Tela 1: Instances View (Landing Page)
**Arquivo:** [instances_view.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/ui/views/instances_view.py)

**Pontos Positivos:**
- ✅ Boa organização: header → billing → cards → console
- ✅ Atualização automática com intervalo configurável
- ✅ Console drawer para debug

**Problemas Identificados:**
- ❌ **Cabeçalho genérico** — Falta hero section com identidade visual forte
- ❌ **Sem animações** — Cards aparecem sem transição
- ❌ **Empty state básico** — O card "Configure sua API key" é um GlassCard genérico sem apelo visual
- ❌ **Console drawer** sempre visível ocupa espaço precioso — deveria ser colapsável com toggle animado
- ❌ **Sem search/filter** nas instâncias
- ❌ **Sem indicador de loading** durante refresh

---

### 💳 Tela 2: Instance Card
**Arquivo:** [instance_card.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/ui/views/instance_card.py)

**Pontos Positivos:**
- ✅ Estado completo do ciclo de vida (stopped → starting → running → stopping)
- ✅ Métricas live detalhadas (GPU/VRAM/CPU/RAM/Disco)
- ✅ Badge de modelo carregado
- ✅ Endpoint copiável

**Problemas Identificados:**
- ❌ **Progress bars genéricos** — `QProgressBar` básico com 6px, sem personalidade
- ❌ **Sem glassmorphism** — Cards usam `SURFACE_1` opaco, sem blur/translucência
- ❌ **Botões sem ícones** — "Ativar", "Terminal", "Desconectar" são text-only
- ❌ **Sem micro-animações** — Transições de estado são instantâneas
- ❌ **Layout sem respiro** — Todas as informações são empilhadas verticalmente sem visual hierarchy

---

### 📊 Tela 3: Billing Strip
**Arquivo:** [billing_strip.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/ui/views/billing_strip.py)

**Pontos Positivos:**
- ✅ Projeção de 24h/7d/30d é uma feature excelente
- ✅ Smoothing de burn rate

**Problemas Identificados:**
- ❌ **Layout horizontal básico** — Só labels empilhados, sem visual appeal
- ❌ **Sem gráfico de tendência** — Falta um sparkline/mini-chart de gastos
- ❌ **Sem separadores visuais** entre métricas
- ❌ **Autonomia sem progress ring** — Só texto, poderia ter um gauge circular

---

### 🎛️ Tela 4: Dashboard (AI Lab)
**Arquivo:** [dashboard_view.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/lab/views/dashboard_view.py)

**Pontos Positivos:**
- ✅ Multi-instance com cards individuais
- ✅ Auto-probe ao conectar SSH
- ✅ Estado vazio com mensagem útil

**Problemas Identificados:**
- ❌ **Header minimalista demais** — Só "CONTROL CENTER" + "AI Lab Dashboard"
- ❌ **Sem status overview geral** — Total de instâncias, modelos carregados, etc.
- ❌ **InstanceDashboardCard é expandível mas sem animação** — Expand/collapse é instantâneo
- ❌ **Sem skeleton loading** durante syncing
- ❌ **Sem atalhos rápidos** — Poderia ter quick-actions no topo

---

### 🔍 Tela 5: Discover View (LLMfit)
**Arquivo:** [discover_view.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/lab/views/discover_view.py)

**Pontos Positivos:**
- ✅ Busca + filtro por use case
- ✅ Fit level com StatusPill colorido
- ✅ Score com ranking visual

**Problemas Identificados:**
- ❌ **Cards de modelo genéricos** — Sem thumbnail, ícone ou identidade visual
- ❌ **Sem comparação** — Não dá pra comparar 2+ modelos lado a lado
- ❌ **Download button diz "One-Click Download"** mas abre um QMessageBox dizendo "coming soon"
- ❌ **Sem progress de download** quando implementado
- ❌ **Sem visual de VRAM fit** — Deveria ter uma barra visual mostrando espaço necessário vs disponível

---

### 📦 Tela 6: Models View
**Arquivo:** [models_view.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/lab/views/models_view.py)

**Pontos Positivos:**
- ✅ Config drawer embutido no card
- ✅ Launch server integrado
- ✅ Breadcrumbs de navegação

**Problemas Identificados:**
- ❌ **Cards muito altos** — Config drawer faz o card ocupar a tela toda
- ❌ **Sem ícones de tipo** — Todos os GGUFs parecem iguais
- ❌ **Sem indicação de modelo ativo** — Se já tá rodando um servidor, deveria destacar
- ❌ **Preview de comando** é um `QPlainTextEdit` genérico
- ❌ **Sem drag-and-drop** ou upload interface

---

### ⚡ Tela 7: Hardware Monitor
**Arquivo:** [hardware_view.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/lab/views/hardware_view.py) + [hardware_card.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/lab/views/hardware_card.py)

**Pontos Positivos:**
- ✅ GaugeWidget custom com QPainter é bonito
- ✅ Grid responsivo 3x2
- ✅ Animações nos gauges (QPropertyAnimation)
- ✅ Placeholder cards com dashed border

**Problemas Identificados:**
- ❌ **Gauges são half-moon** — Não preenchem bem o espaço circular
- ❌ **Sem histórico temporal** — Só mostra valor instantâneo, sem sparklines de tendência
- ❌ **Sem alertas de threshold** — GPU em 95% não dispara nenhum alerta visual
- ❌ **Footer (temp/uptime)** é muito discreto

---

### 📺 Tela 8: Monitor View (llama-server)
**Arquivo:** [monitor_view.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/lab/views/monitor_view.py)

**Pontos Positivos:**
- ✅ Log viewer com fetch manual
- ✅ Status/Model/Config tiles

**Problemas Identificados:**
- ❌ **Sem auto-refresh do log** — Precisa clicar "Fetch Log" manualmente
- ❌ **Sem métricas de request** — tokens/s, requests served, latency
- ❌ **Sem syntax highlighting** no log
- ❌ **Sem health check visual** — Deveria ter um badge "HEALTHY" ou "DEGRADED"
- ❌ **Sem gráfico de performance** — Tokens/s ao longo do tempo

---

### ⚙️ Tela 9: Configure View
**Arquivo:** [configure_view.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/lab/views/configure_view.py)

**Pontos Positivos:**
- ✅ Preview do comando completo
- ✅ Todos os parâmetros expostos (context, ngl, threads, batch, etc.)

**Problemas Identificados:**
- ❌ **Layout de formulário vertical genérico** — Parece um settings dialog, não um UI profissional
- ❌ **Sem presets** — "Fast", "Quality", "Balanced" para configuração rápida
- ❌ **Sem estimativa de VRAM** — Não mostra quanto VRAM vai usar com esses params
- ❌ **Sem slider visual** para context length (128 → 131072 em SpinBox não é intuitivo)

---

### 🔧 Tela 10: Settings Dialog
**Arquivo:** [settings_dialog.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/ui/settings_dialog.py)

**Pontos Positivos:**
- ✅ Test connection funcional
- ✅ Browse para SSH key

**Problemas Identificados:**
- ❌ **Dialog antigo QFormLayout** — Sem design moderno
- ❌ **Sem tabs/sections** — Tudo misturado
- ❌ **Script inicial** tem um `QPlainTextEdit` genérico, sem syntax highlighting

---

### 🧭 NavRail (Sidebar)
**Arquivo:** [nav_rail.py](file:///c:/Users/Pc_Lu/Desktop/vastai-app/app/ui/components/nav_rail.py)

**Problemas Identificados:**
- ❌ **Só 3 itens** — Instances, Dashboard, Hardware. Faltam: Discover, Models, Monitor, Configure
- ❌ **Sem ícones reais** — Usa Unicode chars (☰, ◈, ⏳) que não renderizam bonito
- ❌ **Sem collapse/expand**
- ❌ **Sem avatar/user info** no topo
- ❌ **Sem badge de notificação**
- ❌ **Falta seção "MANAGEMENT" vs "LAB"** para grupo visual

---

## 3. Novas Funcionalidades Propostas

### 🔥 Priority 1: Core Experience

| Feature | Descrição |
|---------|-----------|
| **Marketplace Browser** | Navegar e alugar novas instâncias direto do app (search + filters + rent) |
| **Cost Analytics Page** | Dashboard de gastos com gráficos de barras/linhas por dia/semana/mês |
| **Model Download Manager** | Progress bars de download reais com pause/resume/cancel |
| **Real-time Chat Playground** | Chat interface para testar o modelo rodando na instância |
| **Instance Templates** | Salvar configurações favoritas de setup (docker image + scripts + model) para deploy rápido |

### ⚡ Priority 2: Power Features

| Feature | Descrição |
|---------|-----------|
| **Multi-Instance Benchmark** | Rodar benchmark automatizado em várias instâncias e comparar tok/s |
| **Alert System** | Notificações configuráveis (VRAM > 90%, balance < $5, instance crashed) |
| **Token Usage Tracker** | Contabilizar tokens processados por modelo/instância |
| **SSH Key Manager** | Gerenciar múltiplas SSH keys com easy-setup |
| **Log Streaming** | WebSocket-based log streaming com syntax highlight e search |
| **Auto-Shutdown Rules** | Desligar instância automaticamente após N horas idle |

### 🎨 Priority 3: Polish & UX

| Feature | Descrição |
|---------|-----------|
| **Onboarding Wizard** | Welcome flow para novos usuários (API key → SSH → first instance) |
| **Global Command Palette** | `Ctrl+K` modal para acesso rápido a qualquer ação |
| **Keyboard Shortcuts Panel** | `Ctrl+?` para mostrar todos os atalhos |
| **Dark/Light Theme Toggle** | Embora dark-first, ter opção |
| **Export Config** | Exportar/importar configurações completas |

---

## 4. Design System — Premium Black Glassmorphism

### 🎨 Paleta de Cores

```
BACKGROUNDS
├── bg-void:      #030508      (deepest black)
├── bg-deep:      #070A0F      (base canvas)
├── bg-base:      #0B0F17      (sidebar/header)
├── surface-1:    rgba(15, 20, 30, 0.65)   (card, with BLUR)
├── surface-2:    rgba(22, 28, 42, 0.55)   (raised card, with BLUR)
├── surface-3:    rgba(30, 38, 55, 0.50)   (input bg, with BLUR)
└── glass-hover:  rgba(40, 50, 70, 0.40)   (hover overlay)

BORDERS
├── border-glow:  rgba(124, 92, 255, 0.15)  (accent border subtle)
├── border-low:   rgba(255,255,255, 0.04)   (structural)
├── border-med:   rgba(255,255,255, 0.08)   (interactive)
└── border-hi:    rgba(255,255,255, 0.14)   (focus/active)

ACCENT SYSTEM
├── primary:      #7C5CFF → #9B83FF   (hover)
├── glow:         rgba(124,92,255, 0.25)  (ambient glow)
├── gradient:     linear-gradient(135deg, #7C5CFF, #5AA0FF)
└── accent-text:  #B3A0FF  (soft accent for inline text)

STATUS
├── success:      #3BD488 → shadow rgba(59,212,136, 0.20)
├── warning:      #F4B740 → shadow rgba(244,183,64, 0.15)
├── error:        #F0556A → shadow rgba(240,85,106, 0.15)
├── info:         #4EA8FF → shadow rgba(78,168,255, 0.15)
└── live:         #19C37D → pulsing glow animation

TEXT
├── text-hero:    #FFFFFF  (display headings)
├── text-hi:      #F1F4FA  (titles/values)
├── text:         #C7CEDC  (body)
├── text-mid:     #6B7590  (labels/hints)
└── text-low:     #3D4560  (disabled/dividers)
```

### 🔮 Glassmorphism Tokens

```css
/* Card Level 1 — Primary Surface */
.glass-card {
    background: rgba(15, 20, 30, 0.65);
    backdrop-filter: blur(24px) saturate(1.3);
    -webkit-backdrop-filter: blur(24px) saturate(1.3);
    border: 1px solid rgba(255,255,255, 0.06);
    border-radius: 16px;
    box-shadow: 
        0 8px 32px rgba(0,0,0, 0.40),
        inset 0 1px 0 rgba(255,255,255, 0.04);
}

/* Card Level 2 — Raised / Focused */
.glass-card-raised {
    background: rgba(22, 28, 42, 0.55);
    backdrop-filter: blur(20px) saturate(1.2);
    border: 1px solid rgba(255,255,255, 0.08);
    border-radius: 16px;
    box-shadow:
        0 12px 48px rgba(0,0,0, 0.50),
        inset 0 1px 0 rgba(255,255,255, 0.06);
}

/* Accent Glow on hover */
.glass-card:hover {
    border-color: rgba(124, 92, 255, 0.20);
    box-shadow:
        0 8px 32px rgba(0,0,0, 0.40),
        0 0 20px rgba(124, 92, 255, 0.08),
        inset 0 1px 0 rgba(255,255,255, 0.06);
}

/* Sidebar */
.nav-rail {
    background: rgba(8, 11, 18, 0.85);
    backdrop-filter: blur(30px);
    border-right: 1px solid rgba(255,255,255, 0.04);
}

/* Input Fields */
.glass-input {
    background: rgba(20, 26, 38, 0.60);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255, 0.06);
    border-radius: 12px;
    color: #F1F4FA;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.glass-input:focus {
    border-color: rgba(124, 92, 255, 0.50);
    box-shadow: 0 0 16px rgba(124, 92, 255, 0.12);
}

/* Status Pills */
.status-pill {
    background: rgba(20, 26, 38, 0.50);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255, 0.06);
    border-radius: 999px;
    padding: 5px 14px;
    font-size: 11px;
    font-weight: 600;
}

/* Primary Button */
.btn-primary {
    background: linear-gradient(135deg, #7C5CFF 0%, #5A8AFF 100%);
    border: none;
    border-radius: 12px;
    padding: 12px 24px;
    color: white;
    font-weight: 700;
    box-shadow: 0 4px 20px rgba(124, 92, 255, 0.30);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.btn-primary:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 28px rgba(124, 92, 255, 0.45);
}

/* Ghost Button */
.btn-ghost {
    background: transparent;
    border: 1px solid rgba(255,255,255, 0.08);
    border-radius: 12px;
    color: #C7CEDC;
    transition: all 0.2s ease;
}
.btn-ghost:hover {
    background: rgba(255,255,255, 0.04);
    border-color: rgba(255,255,255, 0.14);
}
```

### 🖋️ Tipografia

```
DISPLAY:    Inter (700), 28px — Page titles only
TITLE:      Inter (600), 16px — Card titles, section names
BODY:       Inter (400), 14px — Default text
LABEL:      Inter (600), 11px, tracking 1.5px, UPPERCASE — Eyebrows/categories
MONO:       JetBrains Mono (400), 13px — Code/values/endpoints
SMALL:      Inter (400), 12px — Secondary info
```

### ✨ Animações

```
TRANSITIONS
├── card-enter:    fadeIn 300ms + translateY(12px→0) ease-out
├── card-hover:    border-glow 200ms ease
├── gauge-sweep:   arc fill 800ms cubic-bezier(0.4, 0, 0.2, 1)
├── pill-pulse:    scale(1→1.04→1) 2s infinite (for LIVE status)
├── sidebar-hover: bg-color 150ms ease
├── page-switch:   opacity 250ms + translateX(8px→0) ease-out
├── skeleton:      shimmer gradient 1.5s infinite
└── toast-enter:   slideDown 300ms + opacity ease-out
```

---

## 5. UIwizard Prompt

> [!IMPORTANT]
> O prompt abaixo deve ser copiado integralmente para o UIwizard gerar as telas.

---

```
Design a premium, ultra-modern desktop application called "Vast.ai Manager" — a cloud GPU management & AI inference dashboard for power users.

BRAND IDENTITY:
- App name: "VAST.AI" in the sidebar with a sparkle icon (✦)
- Tagline: "Remote AI Lab"
- Feel: Elite hacker tool meets enterprise SaaS — think Stripe Dashboard × Arc Browser × Warp Terminal

DESIGN SYSTEM:
- Style: Deep black glassmorphism with frosted glass panels, purple (#7C5CFF) accent, blue-purple gradients
- Background: Ultra-deep black (#030508 to #070A0F) with a subtle radial gradient glow of purple at center
- Cards: Semi-transparent frosted glass (rgba(15,20,30,0.65)) with backdrop-blur(24px), 1px white-4% border, 16px radius, soft black shadow + top inset white highlight
- Typography: Inter for UI, JetBrains Mono for code/values. White (#F1F4FA) for titles, grey (#6B7590) for labels
- Buttons: Primary = gradient purple→blue with glow shadow. Ghost = transparent with 1px border
- Status colors: Green #3BD488, Yellow #F4B740, Red #F0556A, Blue #4EA8FF, Live green #19C37D with pulse animation
- Icons: Use minimal line icons (Lucide/Phosphor style), 20px
- Micro-animations everywhere: hover lifts, glow borders, smooth gauge sweeps, skeleton loaders

LAYOUT:
- Frameless desktop window (no OS chrome) with custom title bar (minimize, maximize, close on top-right)
- Left sidebar (240px) with app name at top, navigation items with icons, version footer at bottom
- Main content area with views that switch on sidebar click
- Sidebar navigation items: Instances, Dashboard, Hardware, Discover, Models, Monitor, Analytics, Settings

GENERATE THESE 8 SCREENS:

--- SCREEN 1: INSTANCES (Landing Page) ---
Full-width view with:
- Top: "My Instances" title (large, Inter 24px bold white) + "3 active" badge + refresh interval dropdown + refresh button + gear icon
- Below title: Billing Strip card (raised glass) with 4 metrics in a row:
  • BALANCE: "$47.83" in large bold white
  • BURN RATE: "$0.38/h ↓" with trend arrow
  • AUTONOMY: "5d 2h" with colored ring indicator (green)
  • TODAY: "$4.21"
  • Below: Projection text "24h → $38.71 · 7d → $32.52 · 30d → $0.00"
- Below: List of Instance Cards, each card is a glass panel with:
  • Top-left: Status pill ("● Active · Connected" in green, or "○ Stopped" in grey)
  • Top-right: GPU label "RTX 4090 · 24 GB VRAM"
  • Title: "Instance #12345" or custom label, large bold
  • Right of title: "$0.25/h" in purple accent mono font
  • Subtitle: "pytorch/pytorch:2.1 · active for 3h 42m" in muted grey
  • Detail line: "📍 US-West · 🖥 host #8192 · 🧠 AMD EPYC 7543 (32c) · CUDA ≤ 12.4 · PCIe Gen 4 · ⚡ 99.2%"
  • When connected: 5 metric bars (GPU, VRAM, CPU, RAM, Disk) with colored thin progress bars (6px height, rounded) and monospace values on the right
  • Endpoint: "🔗 http://127.0.0.1:11434" with Copy button
  • Model badge: "🤖 Qwen2.5-Coder-32B-Q5_K_M.gguf" in a pill
  • Action row: [Activate/Connect] primary button, [Open Lab] ghost, [Terminal] ghost, [Disconnect] ghost, spacer, [Deactivate] red danger button
- Bottom: Collapsible console drawer with dark terminal background, monospace font, log messages

--- SCREEN 2: DASHBOARD (AI Lab Control Center) ---
Glass cards for each connected instance:
- Header bar: Health dot (green/yellow/red) + GPU name title (e.g. "RTX A6000") + "Instance #12345" subtitle + SSH pill ("SSH Connected" green) + "Details ▾" expand button
- Expanded body reveals:
  • 3 metric tiles: LLMfit (READY ✓), llama.cpp (READY ✓), Files (3 GGUF)
  • Hardware specs box: "CPU: AMD EPYC 7543 (32 cores) • RAM: 128GB • VRAM: 48GB"
  • Action bar: [⚡ Setup Everything], [✦ Discover Models], [☰ Installed Models], [◴ Monitor] buttons
- Empty state: Glass card with centered sparkle icon, "Awaiting Active Connections" title, helpful message

--- SCREEN 3: HARDWARE MONITOR ---
Hero title: "Hardware Monitoring" (display size, bold)
Subtitle: "Real-time telemetry for all active remote instances"
Responsive grid of Instance Hardware Cards, each containing:
- 6 gauges in a 3×2 grid, each gauge wrapped in a raised glass sub-card:
  • Row 1: CPU Load (half-circle gauge), RAM Usage, Disk /work
  • Row 2: GPU Load, VRAM Usage, Network I/O (up/down arrows with speeds)
  • Each gauge: thick arc track (16px), colored fill arc (green→yellow→red), big value in center (24pt), label below (UPPERCASE 9pt), subtext "(used / total GB)" in mono
- Card header: "Instance #12345" title + GPU name
- Card footer: "GPU Temp: 62°C" left, "Uptime: 3h 42m" right
- Empty slots: Dashed border placeholder with sparkle icon and "Connect a remote machine to see live metrics here"

--- SCREEN 4: DISCOVER MODELS ---
Breadcrumb: "← Back · Dashboard > Instance #12345 > Discover Models"
Header: "LLMFIT" eyebrow + "Model Recommendations" title
Controls: Search input (glass) + Use Case dropdown (All, General, Coding, Reasoning, Chat, Multimodal, Embedding) + Refresh button
Status: "LLMfit active ✔ · Showing models ranked for this machine's specific hardware" in green
Model cards list, each card:
- Title (bold, 14pt): "Qwen2.5-Coder-32B-Instruct"
- Fit pill: "PERFECT" green / "GOOD" blue / "MARGINAL" yellow / "TOO TIGHT" red
- Meta line: "Alibaba · 32.5B · Q5_K_M · Coding · ~28 tok/s"
- Score: "Rank Score: 1850" in purple accent bold
- VRAM fit bar: visual bar showing estimated VRAM usage vs available (NEW FEATURE)
- Download button: "One-Click Download" primary button (disabled if TOO TIGHT)

--- SCREEN 5: MODELS (GGUF Manager) ---
Breadcrumb: "← Back · Dashboard > Instance #12345 > Models"
Header: "REMOTE FILES" eyebrow + "Manage Models & Inference" title
Action bar: [↻ Rescan] + [✦ Discover More]
Model cards:
- Title: "Qwen2.5-Coder-32B-Q5_K_M.gguf" (bold 13pt)
- Size pill: "21.4 GB" blue
- Path: monospace grey small
- Actions: [⚙ Configure] toggle button, [Delete] ghost, spacer, [▶ Launch Server] primary button
- Expanded config drawer with glass background:
  • Grid of controls: Context Size, GPU Layers, Threads, Batch Size, Parallel Requests, Flash Attention toggle
  • Advanced: Extra Args input, KV Cache dropdown, Repeat Penalty
  • Command Preview: dark terminal-style box with the full command
  • [↩ Save Config] button

--- SCREEN 6: MONITOR (llama-server) ---
Header: "SERVER" eyebrow + "Monitor llama-server"
3 metric tiles: Status (RUNNING / green), Model (filename), Config (summary)
Action bar: [■ Stop Server] red, [↻ Restart], [⚙ Reconfigure], spacer, [Fetch Log] ghost
Performance metrics (NEW): Request count, avg latency, tokens/s gauge
Log card: Full-height glass card with monospace dark terminal log viewer, auto-scroll, search

--- SCREEN 7: ANALYTICS (NEW) ---
Header: "ANALYTICS" eyebrow + "Cost & Usage Intelligence"
Time range selector: [24h] [7d] [30d] [Custom]
Cards:
- Spending Chart: Area chart showing hourly/daily costs with purple gradient fill
- Instance Breakdown: Horizontal bar chart showing cost per instance
- Summary tiles: Total Spent, Avg Daily, Peak Hour, Tokens Processed
- Usage table: Instance name, Hours Active, Total Cost, Avg $/h, Models Used

--- SCREEN 8: SETTINGS ---
Full glass card settings page (not a dialog):
- Sections with clear visual separation:
  • CONNECTION: API Key (password input with eye toggle), Test Connection button with status
  • SSH: Key path with browse, passphrase cache toggle
  • BEHAVIOR: Refresh interval, Default port, Auto-connect toggle, Terminal preference
  • AUTOMATION: On-connect script with syntax-highlighted editor
  • ABOUT: Version, links

COMMON ELEMENTS ON ALL SCREENS:
- Title bar: Transparent, window controls (−, □, ✕) on the far right, draggable area
- Sidebar: Active item highlighted with purple left border + surface-2 background
- Toast notifications: Slide down from top-right, glass style, auto-dismiss
- All interactive elements have hover states with subtle glow
- Loading states use skeleton shimmer animation (not spinners)
- Smooth page transitions (fade + slide)

RESOLUTION: 1440×900 desktop, retina quality
STYLE: Figma-quality mockup, pixel-perfect, production-ready
MOOD: Premium, professional, dark, futuristic — like a control center for a space station
```

---

## 6. Resumo da Revisão

### Problemas Globais do Design Atual

| Categoria | Problema | Impacto |
|-----------|----------|---------|
| **Glass** | Cards são opacos (`SURFACE_1`), sem blur ou translucência | App parece flat/genérico |
| **Animação** | Zero transições entre telas, zero micro-animações | App parece estático/morto |
| **Icons** | Unicode chars (☰, ◈, ⏳) em vez de ícones reais | Aspecto amador |
| **Hierarchy** | Falta respiro visual, spacing inconsistente | UI densa e confusa |
| **NavRail** | Só 3 itens, sem ícones, sem agrupamento | Subnavegação escondida |
| **Loading** | Sem skeletons, sem shimmer, sem feedback visual | Usuário não sabe se carregou |
| **Empty States** | Genéricos e sem personalidade | Primeira impressão fraca |
| **Inputs** | SpinBox/ComboBox nativos sem estilização premium | Quebra a identidade visual |

### O que já está BOM e deve ser preservado

- ✅ Arquitetura controller + workers + store é sólida
- ✅ GaugeWidget com QPainter é um diferencial
- ✅ Billing com projeção e burn rate smoothing é excelente
- ✅ Multi-instance architecture funciona bem
- ✅ Tema unificado com design tokens em `theme.py`
- ✅ Frameless window com native resize é premium
