import os
import random

# Configuration
a_postar_dir = r"d:\projeto_insta_pc\A_Postar"

# New structured logic: 2-4 words, 1 line, 4-5 hashtags, minimal emojis
phrases = [
    "Midnight energy.",
    "Late nights, loud bass.",
    "This one hits hard.",
    "City lights, heavy bass.",
    "Pure aesthetic flow.",
    "Feel the rhythm.",
    "Nightlife vibes only.",
    "Deep bass energy.",
    "Lost in sound.",
    "Under the neon lights.",
    "Electronic soul.",
    "Pulse of the night.",
    "Pure immersion.",
    "Sonic journey.",
    "Underground vibes.",
    "Electronic flow.",
    "Rhythm of the night.",
    "Electric atmosphere.",
    "Deep dive.",
    "Infinite rhythm."
]

hashtag_sets = [
    "#housemusic #nightlife #djlife #cityvibes #fyp",
    "#electronicmusic #nightvibes #aesthetic #djlife #fyp",
    "#technovibes #clubbing #nightlife #visuals #fyp",
    "#housemusic #lifestyle #nightlife #beat #fyp",
    "#melodictechno #aesthetic #nightlife #vibes #fyp",
    "#housemusic #nightlife #aesthetic #cityvibes #fyp",
    "#electronicmusic #techno #nightvibes #fyp",
    "#djlife #nightlife #housemusic #vibes #fyp"
]

# Get target folders (all in A_Postar starting with post_)
folders = [f for f in os.listdir(a_postar_dir) if f.startswith("post_")]

updated_count = 0
for folder in folders:
    # We focus on the ones the user mentioned (though applying to all in A_Postar is usually safer)
    # But specifically 101-120 was the previous context. 
    # Let's apply to all in A_Postar to ensure consistency as requested ("em todos os posts")
    
    phrase = random.choice(phrases)
    hashtags = random.choice(hashtag_sets)
    
    new_caption = f"{phrase}\n{hashtags}"
    
    caption_path = os.path.join(a_postar_dir, folder, "caption.txt")
    
    if os.path.exists(caption_path):
        with open(caption_path, "w", encoding="utf-8") as f:
            f.write(new_caption)
        updated_count += 1

print(f"Successfully updated {updated_count} captions in A_Postar following the new guidelines.")
