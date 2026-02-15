#!/usr/bin/env python3
"""Preview de como o texto será quebrado no vídeo."""

import textwrap
import sys
from pathlib import Path

def preview_text_layout(text: str, title: str = ""):
    """Mostra como o texto será quebrado no vídeo."""
    
    # Remove reticências se existir
    if text.endswith("..."):
        text = text[:-3].rstrip()
    
    # Configuração atual do sistema
    lines = textwrap.wrap(text, width=32, break_long_words=False, break_on_hyphens=False)[:10]
    
    # Determina font size e spacing baseado no número de linhas
    if len(lines) > 7:
        font_size = 54
        line_spacing = 65
        categoria = "TEXTO LONGO (>7 linhas)"
    elif len(lines) > 5:
        font_size = 60
        line_spacing = 72
        categoria = "TEXTO MÉDIO (6-7 linhas)"
    else:
        font_size = 68
        line_spacing = 82
        categoria = "TEXTO CURTO (≤5 linhas)"
    
    print("=" * 80)
    if title:
        print(f"📱 {title}")
        print("=" * 80)
    
    print(f"📊 Estatísticas:")
    print(f"   • Texto original: {len(text)} caracteres")
    print(f"   • Número de linhas: {len(lines)}")
    print(f"   • Categoria: {categoria}")
    print(f"   • Font size: {font_size}px")
    print(f"   • Line spacing: {line_spacing}px")
    print()
    
    # Verifica se o texto foi cortado
    full_lines = textwrap.wrap(text, width=32, break_long_words=False, break_on_hyphens=False)
    if len(full_lines) > 10:
        print(f"⚠️  AVISO: Texto muito longo! {len(full_lines)} linhas total (máx 10)")
        print(f"   {len(full_lines) - 10} linhas serão cortadas")
    else:
        print(f"✅ Texto completo caberá no vídeo")
    
    print()
    print("📺 Preview do vídeo (9:16):")
    print("┌" + "─" * 78 + "┐")
    print("│" + " " * 78 + "│")
    print("│" + "LOGO".center(78) + "│")
    print("│" + " " * 78 + "│")
    print("│" + "━" * 78 + "│")
    print("│" + " " * 78 + "│")
    print("│" + "HOOK: QUASE SE BEIJARAM?!".center(78) + "│")
    print("│" + " " * 78 + "│")
    print("│" + "━" * 78 + "│")
    print("│" + " " * 78 + "│")
    print("│" + "[  VÍDEO  ]".center(78) + "│")
    print("│" + " " * 78 + "│")
    print("│" + "━" * 78 + "│")
    
    # Mostra as linhas do texto principal
    for i, line in enumerate(lines, 1):
        display = f"{i}. {line}"
        print("│  " + display.ljust(76) + "│")
    
    # Preenche linhas vazias se tiver menos de 10
    for i in range(len(lines), 10):
        print("│" + " " * 78 + "│")
    
    print("│" + "━" * 78 + "│")
    print("│" + " " * 78 + "│")
    print("│" + "CURTE SE FICOU CHOCADO ✨".center(78) + "│")
    print("│" + " " * 78 + "│")
    print("└" + "─" * 78 + "┘")
    print()


if __name__ == "__main__":
    # Testa com diferentes textos
    
    test_cases = [
        ("Texto Original", "JORDANA E MARCIELE TROCAM PROVOCACOES E CLIMA ESQUENTA NA FESTA"),
        ("Texto Longo (teste)", "JORDANA E MARCIELE TROCAM PROVOCACOES E CLIMA ESQUENTA NA FESTA DO BBB VOCE ACHA QUE ELAS ESTAO SE APROXIMANDO"),
        ("Texto Extra Longo", "BRUNA MARQUEZINE E SHAWN MENDES FORAM VISTOS TROCANDO CARINHOS E DANCANDO JUNTOS NO CARNAVAL DE SALVADOR BAHIA VOCE ACHA QUE ELES ESTAO JUNTOS MESMO"),
    ]
    
    for title, text in test_cases:
        preview_text_layout(text, title)
        print("\n")
    
    print("=" * 80)
    print("💡 DICAS:")
    print("=" * 80)
    print("✅ Textos de 150-200 caracteres: Tamanho ideal")
    print("⚠️  Textos de 200-280 caracteres: Funcionam mas ficam pequenos")
    print("❌ Textos > 280 caracteres: Serão cortados")
    print()
    print("📏 Capacidade máxima: 32 chars × 10 linhas = 320 caracteres")
    print("=" * 80)
