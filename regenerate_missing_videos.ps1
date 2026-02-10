# Regenera vídeos faltantes para completar 3 variantes por post

$python = "D:/projeto_insta_pc/.venv/Scripts/python.exe"
$mainScript = "D:/projeto_insta_pc/main.py"

# Lista de posts incompletos com configurações
$posts = @(
    @{
        Name = "post_004_michael_bibi_hanging_tree"
        TrackId = "michael bibi hanging tree"
        BrollStyle = "nightclub party club vibes"
        Themes = "nightclub,party,club"
        MinVideos = 6
    },
    @{
        Name = "post_010_mr._fingers_can_you_feel_it"
        TrackId = "mr._fingers_can_you_feel_it"
        BrollStyle = "nightclub crowd energy vibes"
        Themes = "nightlife crowd energy"
        MinVideos = 6
    },
    @{
        Name = "post_019_anotr_vertigo_carlita_remix"
        TrackId = "anotr_vertigo_carlita_remix"
        BrollStyle = "nightclub neon lights laser beams"
        Themes = "nightlife light lasers"
        MinVideos = 6
    },
    @{
        Name = "post_020_chris_stussy_desire"
        TrackId = "chris_stussy_desire"
        BrollStyle = "nightclub purple lights mood"
        Themes = "nightlife light purple"
        MinVideos = 6
    },
    @{
        Name = "post_021_blaze_lovelee_dae"
        TrackId = "blaze_lovelee_dae"
        BrollStyle = "luxury bar champagne glasses"
        Themes = "luxury bar champagne"
        MinVideos = 6
    },
    @{
        Name = "post_023_ultra_nate_free"
        TrackId = "ultra_nate_free"
        BrollStyle = "luxury bar freedom celebration"
        Themes = "luxury bar celebration"
        MinVideos = 6
    },
    @{
        Name = "post_025_kerri_chandler_bar_a_thym"
        TrackId = "kerri_chandler_bar_a_thym"
        BrollStyle = "DJ booth turntables hands"
        Themes = "dj booth turntables"
        MinVideos = 6
    }
)

Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host ("=" * 79) -ForegroundColor Cyan
Write-Host "REGENERANDO VÍDEOS FALTANTES" -ForegroundColor Yellow
Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host ("=" * 79) -ForegroundColor Cyan
Write-Host ""

$successCount = 0
$failCount = 0

foreach ($post in $posts) {
    Write-Host "`n[PROCESSANDO] $($post.Name)" -ForegroundColor Cyan
    
    $cmd = @(
        $mainScript,
        "--online",
        "--online-provider", "youtube",
        "--online-track-id", $post.TrackId,
        "--online-broll-style", $post.BrollStyle,
        "--online-broll-min-videos", $post.MinVideos,
        "--online-themes", $post.Themes,
        "--online-post-name", $post.Name,
        "--overwrite"
    )
    
    Write-Host "Executando comando..." -ForegroundColor Gray
    
    & $python @cmd
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[✓] $($post.Name) - SUCESSO" -ForegroundColor Green
        $successCount++
    } else {
        Write-Host "[✗] $($post.Name) - FALHOU (Exit Code: $LASTEXITCODE)" -ForegroundColor Red
        $failCount++
    }
}

Write-Host ""
Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host ("=" * 79) -ForegroundColor Cyan
Write-Host "RESUMO FINAL" -ForegroundColor Yellow
Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host ("=" * 79) -ForegroundColor Cyan
Write-Host "Total de posts: $($posts.Count)" -ForegroundColor White
Write-Host "Sucesso: $successCount" -ForegroundColor Green
Write-Host "Falhas: $failCount" -ForegroundColor Red
Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host ("=" * 79) -ForegroundColor Cyan
