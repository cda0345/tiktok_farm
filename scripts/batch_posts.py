"""
Batch Post Generator - Processa múltiplos posts em fila
Usage: python batch_posts.py posts_queue.csv
"""
import subprocess
import sys
import csv
from pathlib import Path
from datetime import datetime


def normalize_track_id(track_name: str, artist: str) -> str:
    """Converte track name e artist para track_id formato."""
    combined = f"{artist} {track_name}".lower()
    # Remove caracteres especiais e substitui espaços por underscores
    clean = combined.replace("'", "").replace('"', "").replace(":", "")
    return "_".join(clean.split())


def normalize_post_name(post_num: int, track_name: str, artist: str) -> str:
    """Gera nome do post no formato post_XXX_track_id."""
    track_id = normalize_track_id(track_name, artist)
    return f"post_{post_num:03d}_{track_id}"


def normalize_broll_query(broll_idea: str) -> str:
    """Converte ideia de b-roll para query de busca."""
    # Remove caracteres especiais
    clean = broll_idea.lower().strip()
    return clean.replace(" + ", " ").replace(", ", " ")


def run_post(post_data: dict) -> bool:
    """
    Executa a geração de um post.
    
    Args:
        post_data: dict com keys: post_num, track_name, artist, broll_idea, themes
    
    Returns:
        True se sucesso, False se erro
    """
    post_num = int(post_data['post_num'])
    track_name = post_data['track_name']
    artist = post_data['artist']
    broll_idea = post_data['broll_idea']
    themes = post_data.get('themes', 'nightlife,dj,party')
    min_videos = int(post_data.get('min_videos', 6))
    
    track_id = normalize_track_id(track_name, artist)
    post_name = normalize_post_name(post_num, track_name, artist)
    broll_query = normalize_broll_query(broll_idea)
    
    print(f"\n{'='*80}")
    print(f"🎵 POST {post_num:03d}: {artist} - {track_name}")
    print(f"{'='*80}")
    print(f"Track ID: {track_id}")
    print(f"Post Name: {post_name}")
    print(f"B-roll Query: {broll_query}")
    print(f"Themes: {themes}")
    print(f"Min Videos: {min_videos}")
    print(f"Started: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*80}\n")
    
    # Monta comando usando o Python do ambiente virtual
    venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable
    
    cmd = [
        python_exe,
        str(Path(__file__).parent / "main.py"),
        "--online",
        "--online-provider", "youtube",
        "--online-track-id", track_id,
        "--online-broll-style", broll_query,
        "--online-broll-min-videos", str(min_videos),
        "--online-themes", themes,
        "--online-post-name", post_name,
        "--overwrite"
    ]
    
    try:
        # Executa em primeiro plano (não usa Popen, usa run com herança de stdio)
        result = subprocess.run(cmd, check=True)
        
        print(f"\n{'='*80}")
        print(f"✅ POST {post_num:03d} CONCLUÍDO: {artist} - {track_name}")
        print(f"Finished: {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*80}\n")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n{'='*80}")
        print(f"❌ POST {post_num:03d} FALHOU: {artist} - {track_name}")
        print(f"Error code: {e.returncode}")
        print(f"Finished: {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*80}\n")
        return False
    except KeyboardInterrupt:
        print(f"\n\n{'='*80}")
        print(f"⚠️  INTERROMPIDO PELO USUÁRIO")
        print(f"{'='*80}\n")
        raise


def load_posts_from_csv(csv_path: str) -> list[dict]:
    """
    Carrega posts de um arquivo CSV.
    
    Formato esperado (com header):
    post_num,track_name,artist,broll_idea,themes,min_videos
    6,Your Love,Frankie Knuckles,Booth POV + EQ,dj,booth,nightlife,6
    """
    posts = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            posts.append(row)
    return posts


def main():
    if len(sys.argv) < 2:
        print("❌ Erro: Forneça o arquivo CSV com os posts")
        print(f"Usage: python {Path(__file__).name} posts_queue.csv")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    
    if not Path(csv_path).exists():
        print(f"❌ Erro: Arquivo não encontrado: {csv_path}")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"🚀 BATCH POST GENERATOR")
    print(f"{'='*80}")
    print(f"CSV File: {csv_path}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")
    
    posts = load_posts_from_csv(csv_path)
    total = len(posts)
    
    print(f"📋 Total de posts na fila: {total}\n")
    
    success_count = 0
    failed_count = 0
    failed_posts = []
    
    for i, post_data in enumerate(posts, 1):
        print(f"\n[{i}/{total}] Processando post...")
        
        try:
            success = run_post(post_data)
            if success:
                success_count += 1
            else:
                failed_count += 1
                failed_posts.append(f"Post {post_data['post_num']}: {post_data['artist']} - {post_data['track_name']}")
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Processamento interrompido pelo usuário")
            print(f"Posts processados: {i-1}/{total}")
            sys.exit(1)
    
    # Resumo final
    print(f"\n\n{'='*80}")
    print(f"📊 RESUMO FINAL")
    print(f"{'='*80}")
    print(f"Total de posts: {total}")
    print(f"✅ Sucesso: {success_count}")
    print(f"❌ Falhas: {failed_count}")
    
    if failed_posts:
        print(f"\nPosts que falharam:")
        for post in failed_posts:
            print(f"  - {post}")
    
    print(f"\nFinished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
