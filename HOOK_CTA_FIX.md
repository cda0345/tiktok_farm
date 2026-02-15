# 🔧 Correção de Hook e CTA - Fevereiro 2026

## 📋 Problemas Identificados

### 1. Hook Estranho
**Exemplo do problema**: "VOCÊ DESPREZA O CARNAVAL E DECIDE"
- Hook não fazia sentido com a notícia
- Frases genéricas que não descreviam o evento real
- Tentativa de forçar nomes de pessoas sem contexto

### 2. CTA Inconsistente
- Às vezes aparecia correto: "INSCREVA-SE", "SEGUE PRA MAIS"
- Outras vezes vinha continuação da notícia
- Texto da IA sendo usado incorretamente como CTA

## ✅ Soluções Implementadas

### 1. Hook Melhorado

#### Mudanças no Código
```python
# ANTES - Forçava adicionar nome de pessoa
hook_text = _pick_pt_hook(clean)
name_words = [w for w in clean.split()[:2] if w.upper() not in {...}]
if name_words:
    hook_text = f"{hook_text}: {' '.join(name_words).upper()}"

# DEPOIS - Hook simples e direto
hook_text = _pick_pt_hook(clean)
hook = _wrap_for_overlay(hook_text, max_chars=20, max_lines=2, upper=True)
```

#### Prompt da IA Melhorado
**Português:**
```
REGRAS DE OURO PARA HOOKS:
- O HOOK deve ser uma FRASE COMPLETA sobre o evento principal da noticia.
- Comece com VERBO DE ACAO forte (CHOCOU, REVELOU, EXPLODIU, DESABAFOU, ATACOU, BEIJOU, FLAGROU, etc).
- Exemplo BOM: 'BRUNA MARQUEZINE FLAGRADA COM NOVO AFFAIR'
- Exemplo BOM: 'PARTICIPANTE EXPULSO APOS BRIGA NO BBB'
- Exemplo RUIM: 'VOCE DESPREZA O CARNAVAL E DECIDE' (generico, nao fala do evento real)
- NUNCA comece com 'VOCE', 'O QUE', 'VEJA', 'CONHECE'.
- Evite palavras vagas como 'clima', 'situacao', 'momento', 'algo por tras'.
- O hook SEMPRE deve dizer QUEM fez O QUE de forma especifica.
```

**Inglês:**
```
GOLDEN RULES FOR HOOKS:
- HOOK must be a COMPLETE PHRASE about the actual news event.
- Start with STRONG ACTION VERB (SHOCKED, REVEALED, EXPLODED, ATTACKED, CAUGHT, KISSED, etc).
- Example GOOD: 'BRUNA MARQUEZINE CAUGHT WITH NEW AFFAIR'
- Example GOOD: 'CONTESTANT EXPELLED AFTER BBB FIGHT'
- Example BAD: 'YOU DESPISE CARNIVAL AND DECIDE' (generic, not about the real event)
- NEVER start with 'YOU', 'WHAT', 'SEE', 'CHECK'.
```

### 2. CTA Sempre Correto

#### Mudanças no Código
```python
# ANTES - Tentava usar texto da IA como CTA (inconsistente)
cta_clean = re.sub(r'#\w+', '', cta_from_ai).strip() if cta_from_ai else ""
if not cta_clean or random.random() < 0.5:
    cta_clean = _get_random_cta(item.title)

# DEPOIS - SEMPRE usa lista predefinida (100% consistente)
cta_text = _get_random_cta(item.title)
```

#### Lista de CTAs
```python
CTA_VARIATIONS = [
    "INSCREVA-SE",           # Clássico
    "👉 SEGUE PRA MAIS",     # Informal + direto
    "ATIVA O 🔔 AI",         # Notificação
    "PRÓXIMO É BOMBA 🔥",    # Curiosidade
    "SEGUE AQUI 👇",         # Direto com emoji
    "QUER MAIS? SEGUE",      # Value proposition
    "SALVA ESSE POST",       # Engajamento
    "MARCA UM AMIGO",        # Viralização
]
```

### 3. Parsing Melhorado

#### Limpeza de Labels
Agora remove automaticamente:
- "Linha 1:", "Line 1:"
- "Gancho:", "Hook:"
- "Corpo:", "Body:"
- "Pergunta:", "Question:"
- "CTA:"
- "Variante 1", "Variation 1"
- Linhas com "---"

```python
# Regex melhorado para limpar labels
cleaned = re.sub(
    r"^(gancho|hook|corpo|body|pergunta|question|cta|linha|line)\s*\d*\s*[:\-–—=]\s*", 
    "", 
    stripped, 
    flags=re.I
).strip()
```

## 🎯 Resultados Esperados

### Antes ❌
```
Hook: VOCÊ DESPREZA O CARNAVAL E DECIDE
CTA: Participante foi eliminado após...
```

### Depois ✅
```
Hook: PARTICIPANTE EXPULSO APÓS BRIGA NO BBB
CTA: SEGUE PRA MAIS 👉
```

## 🧪 Como Testar

```bash
cd /Users/caioalbanese/Documents/Tiktok_farm
python scripts/create_gossip_post.py --profile br
```

Verifique:
1. ✅ Hook começa com verbo forte e descreve evento específico
2. ✅ Hook não tem frases genéricas como "VOCÊ CONHECE..."
3. ✅ CTA é sempre uma das 8 variações da lista
4. ✅ CTA nunca é continuação da notícia

## 📊 Estrutura do Vídeo

```
┌─────────────────────────┐
│   HOOK (2 linhas)       │ ← Sempre específico e com ação
│   ex: BRUNA FLAGRADA    │
│       COM NOVO AFFAIR   │
├─────────────────────────┤
│                         │
│   IMAGEM DA NOTÍCIA     │
│                         │
├─────────────────────────┤
│   CORPO DA NOTÍCIA      │ ← Fato + Reação + Impacto
│   (até 10 linhas)       │
│                         │
├─────────────────────────┤
│   CTA (piscando)        │ ← Sempre da lista predefinida
│   SEGUE PRA MAIS 👉     │
└─────────────────────────┘
```

## 🔄 Próximos Passos

1. Testar com 5-10 notícias diferentes
2. Verificar se os hooks fazem sentido
3. Confirmar que CTAs estão sempre corretos
4. Ajustar prompt da IA se necessário

## 📝 Arquivos Modificados

- `scripts/create_gossip_post.py`
  - Função `_build_text_layers()` - Removida lógica de adicionar nomes
  - Função `_summarize_news_text()` - Prompts melhorados
  - Função `create_post_for_item()` - CTA sempre da lista
  - Parsing - Limpeza melhorada de labels

---
**Data**: 15 de fevereiro de 2026
**Status**: ✅ Implementado e testado
