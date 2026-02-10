# Batch processar posts 001-005 com YouTube provider
$python = "D:/projeto_insta_pc/.venv/Scripts/python.exe"
$script = "D:/projeto_insta_pc/main.py"

Write-Host "=== Batch gerando posts 001-005 com YouTube ===" -ForegroundColor Green

# Post 001 - Peggy Gou
Write-Host "`n[1/5] Processando post_001: Peggy Gou - Nanana" -ForegroundColor Cyan
& $python $script --online --online-provider youtube --online-track-id "peggy_gou_nanana" --online-broll-style "nightclub party" --online-broll-min-videos 6 --online-themes city,luxury,nightlife --online-post-name post_001 --overwrite

# Post 002 - Pawsa
Write-Host "`n[2/5] Processando post_002: Pawsa - Groove It" -ForegroundColor Cyan
& $python $script --online --online-provider youtube --online-track-id "pawsa_groove_it" --online-broll-style "club crowd dj" --online-broll-min-videos 6 --online-themes nightlife,dj --online-post-name post_002 --overwrite

# Post 003 - Chris Stussy
Write-Host "`n[3/5] Processando post_003: Chris Stussy - All Night Long" -ForegroundColor Cyan
& $python $script --online --online-provider youtube --online-track-id "chris_stussy_all_night_long" --online-broll-style "night drive city" --online-broll-min-videos 6 --online-themes city,nightlife --online-post-name post_003 --overwrite

# Post 004 - Michael Bibi
Write-Host "`n[4/5] Processando post_004: Michael Bibi - Hanging Tree" -ForegroundColor Cyan
& $python $script --online --online-provider youtube --online-track-id "michael_bibi_hanging_tree" --online-broll-style "underground club" --online-broll-min-videos 6 --online-themes nightlife,abstract --online-post-name post_004 --overwrite

# Post 005 - ANOTR
Write-Host "`n[5/5] Processando post_005: ANOTR - Relax My Eyes" -ForegroundColor Cyan
& $python $script --online --online-provider youtube --online-track-id "anotr_relax_my_eyes" --online-broll-style "lounge luxury" --online-broll-min-videos 6 --online-themes luxury,nightlife --online-post-name post_005 --overwrite

Write-Host "`n=== Todos os posts concluídos! ===" -ForegroundColor Green
