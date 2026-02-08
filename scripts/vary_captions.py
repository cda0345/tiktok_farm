import os
import csv
import random

# Configuration
csv_path = r"d:\projeto_insta_pc\posts_abstract_batch.csv"
a_postar_dir = r"d:\projeto_insta_pc\A_Postar"

# Read CSV data
posts_data = {}
with open(csv_path, mode='r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        posts_data[row['post_num']] = {
            'track': row['track_name'],
            'artist': row['artist']
        }

# Variations templates
templates = [
    "{track} by {artist}. Pure immersion. 🌌",
    "Lost in the sound of {artist} - {track}. ✨",
    "{artist} vibes tonight. Track: {track} 🎧",
    "Deep dive into {track} ({artist}). 🌙",
    "The aesthetic of {track}. {artist} never misses. 🔌",
    "Electronic soul: {artist} - {track}. 🛸",
    "Atmospheric textures for {artist}'s {track}. 🎞️",
    "Current mood: {track} by {artist}. 🌊",
    "Techno textures & {track}. {artist} flow. 🌑",
    "Sonic journey with {artist}. Track ID: {track} ☄️"
]

hashtags = [
    "#melodictechno #electronicmusic #aesthetic #visuals",
    "#abstractart #technovibes #musicvideo #nightlife",
    "#minimaltechno #deeptech #audio-visual #housemusic",
    "#undergroundmusic #synth #motiongraphics #musicproducer",
    "#artistic #mood #electronicculture #djlife"
]

# Get target folders
folders = [f for f in os.listdir(a_postar_dir) if f.startswith("post_1")]

for folder in folders:
    # Extract post number
    parts = folder.split('_')
    if len(parts) < 2:
        continue
    
    post_num = parts[1]
    
    if post_num in posts_data:
        data = posts_data[post_num]
        template = random.choice(templates)
        tag_set = random.choice(hashtags)
        
        new_caption = template.format(track=data['track'], artist=data['artist']) + "\n" + tag_set
        
        caption_file = os.path.join(a_postar_dir, folder, "caption.txt")
        
        with open(caption_file, "w", encoding='utf-8') as cf:
            cf.write(new_caption)
            print(f"Updated caption for {folder}")
    else:
        print(f"Post {post_num} not found in CSV data.")

print("Done!")
