import os
from pathlib import Path

# Mapping of cities to appropriate tracks from the list
# Goal: Match the vibe of the city with the energy/style of the house track
post_configs = [
    # IBIZA - Energy, Party, Classic Vibes
    {"folder": "post_302_ibiza_peggy_gou", "track": "peggy_gou_nanana", "city": "ibiza", "caption": "IBIZA NIGHTS ARE UNREAL. 🌴🌊"},
    {"folder": "post_303_ibiza_fisher", "track": "fisher_losing_it", "city": "ibiza", "caption": "THE BALEARIC ISLAND VIBE. 🔊🔥"},
    {"folder": "post_304_ibiza_stussy", "track": "chris_stussy_desire", "city": "ibiza", "caption": "SUNSET GROOVES IN IBIZA. 🌅🕺"},
    
    # PARIS - Elegant, Deep, Melodic
    {"folder": "post_305_paris_bicep", "track": "bicep_glue", "city": "paris", "caption": "PARISIAN AFTERHOURS ENERGY. 🇫🇷✨"},
    {"folder": "post_306_paris_fred_again", "track": "fred_again.._delilah_(pull_me_out_of_this)", "city": "paris", "caption": "CITY OF LIGHTS AND BEATS. 🕯️🎹"},
    {"folder": "post_307_paris_jan_blomqvist", "track": "jan_blomqvist_the_space_in_between", "city": "paris", "caption": "CHIC NIGHTLIFE VIBES ONLY. 🥂🗼"},
    
    # ROMA - Classic, Soulful, Deep House
    {"folder": "post_308_roma_kerri_chandler", "track": "kerri_chandler_bar_a_thym", "city": "roma", "caption": "ETERNAL CITY ETERNAL GROOVE. 🇮🇹🏛️"},
    {"folder": "post_309_roma_boris_brejcha", "track": "boris_brejcha_gravity", "city": "roma", "caption": "ROME UNDERGROUND SCENE. 🎭🎻"},
    {"folder": "post_310_roma_meduza", "track": "meduza_tell_me_why", "city": "roma", "caption": "ROMAN NIGHTS HIT DIFFERENT. 🌑🛵"},
    
    # BONUS IBIZA - Peak Time
    {"folder": "post_311_ibiza_michael_bibi", "track": "michael_bibi_hanging_tree", "city": "ibiza", "caption": "PURE BALEARIC HOUSE ENERGY. 🧪🧿"},
]

def setup_posts():
    base_posts_dir = Path("posts")
    
    for cfg in post_configs:
        post_dir = base_posts_dir / cfg['folder']
        post_dir.mkdir(parents=True, exist_ok=True)
        
        caption_content = f"{cfg['caption']}\n#housemusic #{cfg['city']} #nightlife #aesthetic #travel\ntrack_id={cfg['track']}\nthemes={cfg['city']}\n"
        
        caption_file = post_dir / "caption.txt"
        caption_file.write_text(caption_content, encoding="utf-8")
        print(f"Created: {cfg['folder']}")

if __name__ == "__main__":
    setup_posts()
