# 🎯 Sistema de CTAs (Call-to-Action) - V2 Temático

## 📊 Mudança de Estratégia (v2 - Fev 2026)

Análise dos **3 posts de maior performance** revelou que CTAs genéricos ("INSCREVA-SE", "SEGUE PRA MAIS") performam pior que CTAs **temáticos e emocionais**.

### Posts Top-Performers (referência):
| Post | CTA | Tipo |
|------|-----|------|
| Travadinha (Bruna+Shawn) | "COMENTA O QUE ACHOU!" | Engajamento direto |
| Ana Paula BBB | "SALVA ESSE POST" | Bookmark |
| Babu BBB | "CURTE SE GOSTA DE EMOCAO NO BBB" | Condicional temático |

### Padrão Identificado:
- ✅ CTAs que pedem **AÇÃO ESPECÍFICA** (comenta, salva, curte)
- ✅ CTAs que **CONECTAM COM O TEMA** da notícia
- ✅ CTAs que criam **VÍNCULO EMOCIONAL** com o espectador
- ❌ CTAs genéricos ("INSCREVA-SE", "SEGUE PRA MAIS") → baixo engajamento

## 📋 CTAs Temáticos Implementados

### BBB / Reality
- "CURTE SE GOSTA DE EMOCAO NO BBB"
- "COMENTA QUEM VOCE APOIA!"
- "SALVA PRA ACOMPANHAR O BBB"
- "QUEM MERECE SAIR? COMENTA!"
- "CURTE SE CONCORDA!"

### Separação / Traição
- "COMENTA SE JA SABIA!"
- "ACHA QUE VOLTA? COMENTA!"
- "CURTE SE FICOU CHOCADO!"
- "COMENTA O QUE ACHOU!"

### Namoro / Casal
- "COMENTA SE SHIPPA!"
- "COMBINAM? COMENTA!"
- "CURTE SE APROVA O CASAL!"

### Treta / Polêmica
- "QUEM TEM RAZAO? COMENTA!"
- "CURTE SE FICOU CHOCADO!"
- "FOI JUSTO? COMENTA!"

### Carnaval
- "COMENTA O QUE ACHOU!"
- "CURTE SE AMOU O LOOK!"
- "ARRASOU OU ERROU? COMENTA!"

### Genérico (fallback)
- "COMENTA O QUE ACHOU!"
- "SALVA ESSE POST"
- "MARCA QUEM PRECISA VER ISSO"
- "CONTA NOS COMENTARIOS!"
- "MANDA PRO AMIGO QUE AMA FOFOCA"

## 🔄 Como Funciona

### Seleção em 2 Camadas
1. **IA gera CTA contextual** (linha 5 do script) → preferido se válido (5-45 chars)
2. **Fallback temático** → detecta tema da notícia e seleciona CTA adequado

```python
def _get_random_cta(seed_text: str = "", headline: str = "") -> str:
    theme = _detect_news_theme(headline or seed_text)
    cta_pool = CTA_BY_THEME.get(theme, CTA_VARIATIONS_GENERIC)
    # Seleção determinística baseada no hash
    ...
```

## 🎨 Características Visuais

### Animação Piscante
- **Duração:** 1.4 segundos de ciclo
- **Visível:** 0.7 segundos (50% do tempo)
- **Posição:** 90% da altura da tela (parte inferior)
- **Tamanho:** 53px (legível mas não intrusivo)
- **Cor:** Branco com 88% de opacidade

---

**Status:** ✅ V2 Temático implementado
**Versão:** 2.0 - Fevereiro 2026
**Base:** Análise dos 3 posts de maior performance do canal
