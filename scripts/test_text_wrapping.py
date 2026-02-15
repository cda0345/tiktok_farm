#!/usr/bin/env python3
"""Teste para verificar quebra de texto nos posts de fofoca."""

import textwrap

# Textos de exemplo que costumavam ser cortados
test_texts = [
    "JORDANA E MARCIELE TROCAM PROVOCACOES E CLIMA ESQUENTA NA FESTA VOCE ACHA QUE ELAS SE BEIJARAM",
    "BRUNA MARQUEZINE E SHAWN MENDES FORAM VISTOS TROCANDO CARINHOS E DANCANDO JUNTOS NO CARNAVAL DE SALVADOR BAHIA VOCE ACHA QUE ELES ESTAO JUNTOS MESMO",
    "ELIMINACAO BOMBÁSTICA NO BBB BROTHERS FICAM CHOCADOS COM RESULTADO DA VOTACAO",
    "TRETA PESADA ENTRE PARTICIPANTES CLIMA FICOU TENSO NA CASA",
]

print("=" * 70)
print("TESTE DE QUEBRA DE TEXTO - CONFIGURAÇÃO ANTIGA (width=28, max 9 linhas)")
print("=" * 70)

for i, text in enumerate(test_texts, 1):
    print(f"\n📝 Teste {i}:")
    print(f"Texto original: {text}")
    print(f"Tamanho: {len(text)} caracteres\n")
    
    # Configuração antiga
    lines_old = textwrap.wrap(text, width=28, break_long_words=False, break_on_hyphens=False)[:9]
    print(f"ANTIGA (28 chars, 9 linhas): {len(lines_old)} linhas")
    for j, line in enumerate(lines_old, 1):
        print(f"  {j}. {line}")
    
    if len(lines_old) == 9 and len(textwrap.wrap(text, width=28, break_long_words=False, break_on_hyphens=False)) > 9:
        print("  ⚠️ TEXTO CORTADO!")

print("\n" + "=" * 70)
print("TESTE DE QUEBRA DE TEXTO - CONFIGURAÇÃO NOVA (width=32, max 10 linhas)")
print("=" * 70)

for i, text in enumerate(test_texts, 1):
    # Remove reticências se existir
    if text.endswith("..."):
        text = text[:-3].rstrip()
    
    print(f"\n📝 Teste {i}:")
    print(f"Texto: {text}")
    print(f"Tamanho: {len(text)} caracteres\n")
    
    # Configuração nova
    lines_new = textwrap.wrap(text, width=32, break_long_words=False, break_on_hyphens=False)[:10]
    print(f"NOVA (32 chars, 10 linhas): {len(lines_new)} linhas")
    for j, line in enumerate(lines_new, 1):
        print(f"  {j}. {line}")
    
    if len(lines_new) == 10 and len(textwrap.wrap(text, width=32, break_long_words=False, break_on_hyphens=False)) > 10:
        print("  ⚠️ TEXTO AINDA MUITO LONGO (mais de 10 linhas)")
    else:
        print("  ✅ TEXTO COMPLETO")

print("\n" + "=" * 70)
print("RESUMO")
print("=" * 70)
print("✅ Melhorias aplicadas:")
print("  • Width aumentado: 28 → 32 caracteres por linha")
print("  • Linhas máximas: 9 → 10 linhas")
print("  • Remoção automática de '...' no final")
print("  • Font size ajustado: 56→54, 62→60 para textos longos")
print("  • Line spacing reduzido: 68→65, 75→72 para mais texto")
print("=" * 70)
