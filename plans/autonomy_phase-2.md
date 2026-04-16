Implementar Fase 2 do cálculo de autonomia conforme plano abaixo:
Resumo Completo da Conversa e Plano Fase 2
==========================================

* * *

📋 Resumo da Análise Inicial
----------------------------

### Estado Original do Cálculo de Autonomia

* **Função**: `autonomy_hours(balance, burn) = balance / burn`
* **Parâmetros usados**: Apenas `Instance.dph` (custo GPU horário)
* **Filtro**: Apenas instâncias com estado `RUNNING`
* **Limitações identificadas**:
  * Custos de storage (`storage_total_cost`) ignorados
  * Tráfego de rede não considerado
  * Estados de transição (`STARTING`, `STOPPING`) não tratados
  * Sem suavização para flutuações de preço
  * Formatação básica (apenas horas)

* * *

✅ Fase 1: Correções Imediatas (COMPLETA)
----------------------------------------

### Alterações Implementadas

#### 1. `app/billing.py`

* **Novo enum `AutonomyLevel`**: CRITICAL (<1h), LOW (1-6h), MEDIUM (6-24h), GOOD (>24h)
* **`burn_rate()`**: Agora inclui estados `RUNNING` + `STARTING`
* **Nova função `format_autonomy()`**:
  * < 1h → minutos (`~30min`)
  * 1-24h → horas (`~6h`)
  * 24h-7d → dias+horas (`~1d 6h`, `~3d`)
  * ≥ 7d → semanas+dias (`~1w`, `~2w 1d`)

#### 2. `app/theme.py`

* **`autonomy_color()`**: 4 níveis de cor (Vermelho, Laranja #ff9800, Amarelo, Verde)

#### 3. `app/ui/billing_header.py`

* Usa `format_autonomy()` para exibição inteligente

#### 4. `tests/test_billing.py`

* 14 testes passando (9 novos adicionados)

* * *

📝 Plano Fase 2: Cálculo Completo
---------------------------------

### Objetivo

Implementar cálculo de autonomia completo considerando todos os custos e com suavização temporal.

### Escopo da Fase 2

#### 1. Burn Rate Completo (`total_burn_rate()`)

    def total_burn_rate(
        instances: Iterable[Instance], 
        include_storage: bool = True,
        estimated_network_cost_per_hour: float = 0.0
    ) -> float:
        """
        Calcula burn rate completo incluindo:
        - GPU (dph)
        - Storage (storage_total_cost prorrateado por hora, se > cota gratuita ~50GB)
        - Tráfego de rede estimado
        """

**Detalhes:**

* Verificar `Instance.storage_total_cost` e adicionar ao cálculo
* Considerar apenas storage acima da cota gratuita (se aplicável)
* Adicionar parâmetro opcional para custo estimado de rede

#### 2. Suavização do Burn Rate (`BurnRateTracker`)

    class BurnRateTracker:
        def __init__(self, window_size: int = 10):
            self.history: deque[float] = deque(maxlen=window_size)
    
        def update(self, current_burn: float) -> float:
            """Atualiza histórico e retorna média móvel"""
    
        def get_trend(self) -> str:
            """Retorna 'increasing', 'decreasing' ou 'stable'"""

**Detalhes:**

* Manter histórico dos últimos N cálculos (sugestão: 10)
* Calcular média móvel simples
* Detectar tendência (comparar média recente vs antiga)

#### 3. Projeção de Saldo (`project_balance()`)

    def project_balance(
        balance: float, 
        burn_rate: float, 
        hours_ahead: int,
        include_trend_factor: bool = False
    ) -> dict:
        """
        Projeta saldo futuro.
        Returns: {"balance": float, "autonomy_hours": float}
        """

**Detalhes:**

* Calcular saldo após N horas/dias
* Opcional: aplicar fator de tendência (se burn rate está aumentando)

#### 4. Integração com UI

* Atualizar `BillingHeader` para mostrar:
  * Burn rate completo (com storage)
  * Tendência do custo (seta ↑↓→)
  * Projeção de saldo em 24h/7d (opcional, talvez tooltip ou painel separado)

#### 5. Configuração Opcional

Adicionar em `AppConfig`:
    class AppConfig:
        # ... existing fields ...
        include_storage_in_burn_rate: bool = True
        burn_rate_smoothing_window: int = 10

### Arquivos a Modificar (Fase 2)

1. `app/billing.py` - Nova lógica de cálculo
2. `app/models.py` - Configurações opcionais
3. `app/ui/billing_header.py` - UI updates
4. `tests/test_billing.py` - Novos testes

### Critérios de Aceitação Fase 2

* [x]  `total_burn_rate()` inclui storage quando configurado
* [x]  `BurnRateTracker` suaviza flutuações bruscas
* [x]  UI mostra burn rate completo (não apenas GPU)
* [x]  Testes cobrem cenários com storage > cota gratuita
* [x]  Documentação atualizada em `plans/autonomy-calculation-analysis.md`

Contexto: Fase 1 já implementou formatação composta (dias+horas, semanas+dias) e níveis de alerta. Agora precisamos calcular o burn rate completo incluindo storage e adicionar suavização temporal.

**Arquivos relevantes para referência**:

* `app/billing.py` - burn_rate atual
* `app/models.py` - Instance model com storage_total_cost
* `plans/autonomy-calculation-analysis.md` - Análise completa original

### Fase 2 Implementada

Arquivos alterados:

* `app/billing.py`:
  * `total_burn_rate(instances, include_storage=True, estimated_network_cost_per_hour=0.0)` — soma GPU + storage prorrateado (mensal/720h) + rede estimada. Storage respeita cota gratuita (`FREE_STORAGE_GB = 50`) e conta mesmo para instâncias STOPPED.
  * `BurnRateTracker(window_size=10, trend_threshold=0.05)` com média móvel e `get_trend()` comparando metade antiga × recente; enum `BurnRateTrend` expõe setas ↑ / ↓ / →.
  * `project_balance(balance, burn, hours_ahead, include_trend_factor=False, trend=None, trend_multiplier=0.10)` retorna `{"balance", "autonomy_hours", "burn_used"}`.
* `app/models.py`: novos campos em `AppConfig` — `include_storage_in_burn_rate=True`, `burn_rate_smoothing_window=10`, `estimated_network_cost_per_hour=0.0`.
* `app/ui/billing_header.py`: consome `AppConfig`, usa `total_burn_rate` + `BurnRateTracker`, exibe seta de tendência, projeção 24h/7d e tooltip detalhando GPU/storage/rede.
* `app/ui/main_window.py`: passa `config` ao header e chama `billing.apply_config(cfg)` quando as settings são salvas.
* `app/ui/settings_dialog.py`: preserva campos Fase 2 (e `model_runner_template`) ao reconstruir o `AppConfig`.
* `tests/test_billing.py`: +19 testes cobrindo `total_burn_rate`, `BurnRateTracker`, `project_balance`. Suíte total: 57 passed.
