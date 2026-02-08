"""
Mapeamento de buscas de b-roll para macro-categorias.
Isso evita baixar o mesmo vídeo múltiplas vezes em pastas diferentes.
"""

# Mapeamento: query de busca -> macro-categoria
BROLL_CATEGORY_MAP = {
    # nightlife_crowd
    "hands up crowd dancing": "nightlife_crowd",
    "hands up crowd dancing loop": "nightlife_crowd",
    "nightclub crowd dancing dj performing": "nightlife_crowd",
    "nightclub crowd dj party": "nightlife_crowd",
    "nightclub crowd energy bass": "nightlife_crowd",
    "nightclub crowd kick": "nightlife_crowd",
    "nightclub crowd side view dancing groove": "nightlife_crowd",
    "nightclub crowd slow motion drop": "nightlife_crowd",
    "nightclub crowd dancing groove": "nightlife_crowd",
    "crowd jumping clapping hands up": "nightlife_crowd",
    "nightclub crowd clapping energy": "nightlife_crowd",
    
    # nightlife_light
    "dim lights silhouettes nightclub": "nightlife_light",
    "nightclub dim lights vibe": "nightlife_light",
    "nightclub silhouettes low light": "nightlife_light",
    "dark techno underground club": "nightlife_light",
    "nightclub elegant dim lights": "nightlife_light",
    
    # dj_booth
    "dj booth pov equalizer": "dj_booth",
    "dj booth pov mixing": "dj_booth",
    "nightclub dj house music": "dj_booth",
    "vinyl record spinning turntable": "dj_booth",
    "vinyl turntable dj hands": "dj_booth",
    "DJ hands on CDJ controller loop": "dj_booth",
    "DJ mixing turntables close up": "dj_booth",
    "turntable vinyl spinning closeup": "dj_booth",
    "vinyl record slow motion turntable": "dj_booth",
    
    # city_drive
    "city nightdrive urban lights": "city_drive",
    "city lights luxury nightlife": "city_drive",
    "night drive city pov": "city_drive",
    "night drive POV": "city_drive",
    
    # luxury_bar
    "luxury lounge cocktail bar": "luxury_bar",
    "luxury rooftop bar cocktail": "luxury_bar",
    "elegant afterhours club atmosphere": "luxury_bar",
    "afterhours club vibe atmosphere": "luxury_bar",
    "nightclub lounge elegant vibes": "luxury_bar",
    "afterhours vibe dim lights": "luxury_bar",
    
    # abstract_aesthetic
    "aesthetic": "abstract_aesthetic",
    "underground afterhours nightclub": "abstract_aesthetic",
    "nightclub party": "abstract_aesthetic",
    "luxury premium details motion": "abstract_aesthetic",
    
    # vintage_retro
    "vintage film grain loop": "vintage_retro",
    "vhs aesthetic textures": "vintage_retro",
    "90s nyc street style": "vintage_retro",
    "vinyl record store aesthetic": "vintage_retro",
    "retro tennis match stylized": "vintage_retro",
    "old tv static noise": "vintage_retro",
    "classic house vintage vibes": "vintage_retro",
}


def get_broll_category(query: str) -> str:
    """
    Retorna a macro-categoria para uma query de busca.
    Se não encontrar, retorna a query normalizada.
    """
    query_normalized = query.strip().lower()
    
    # Busca exata
    if query_normalized in BROLL_CATEGORY_MAP:
        return BROLL_CATEGORY_MAP[query_normalized]
    
    # Busca por keywords
    if "crowd" in query_normalized and ("dancing" in query_normalized or "hands" in query_normalized or "jump" in query_normalized):
        return "nightlife_crowd"
    elif "dim" in query_normalized or "silhouette" in query_normalized or "dark" in query_normalized:
        return "nightlife_light"
    elif "dj" in query_normalized or "vinyl" in query_normalized or "turntable" in query_normalized or "cdj" in query_normalized:
        return "dj_booth"
    elif "drive" in query_normalized or "city" in query_normalized and "night" in query_normalized:
        return "city_drive"
    elif "luxury" in query_normalized or "lounge" in query_normalized or "afterhours" in query_normalized or "elegant" in query_normalized:
        return "luxury_bar"
    elif any(k in query_normalized for k in ["vintage", "retro", "vhs", "90s", "tennis", "classic house"]):
        return "vintage_retro"
    
    # Default: abstract_aesthetic
    return "abstract_aesthetic"
