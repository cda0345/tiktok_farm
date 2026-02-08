"""Fix all caption_spec.txt themes to use proper folder names."""
from pathlib import Path

# Mapping from common theme patterns to valid folder names
THEME_MAP = {
    "nightlife": "nightlife_crowd",
    "dj": "dj_booth",
    "crowd": "nightlife_crowd",
    "nightclub": "nightlife_crowd",
    "party": "nightlife_crowd",
    "club": "nightlife_crowd",
    "underground": "abstract_aesthetic",
    "techno": "abstract_aesthetic",
    "city": "city_drive",
    "energy": "nightlife_crowd",
    "bass": "nightlife_crowd",
    "silhouettes": "nightlife_light",
    "dim": "nightlife_light",
    "lights": "nightlife_light",
    "dancing": "nightlife_crowd",
    "dance": "nightlife_crowd",
    "lounge": "luxury_bar",
    "luxury": "luxury_bar",
    "afterhours": "luxury_bar",
    "night drive": "city_drive",
    # Full phrases
    "nightlife crowd energy": "nightlife_crowd",
    "nightlife crowd bass": "nightlife_crowd,dj_booth",
    "nightlife lounge club": "luxury_bar,nightlife_crowd",
    "nightlife crowd dance": "nightlife_crowd",
    "nightlife crowd dancing": "nightlife_crowd",
    "city night drive": "city_drive",
    "nightlife lights crowd": "nightlife_crowd,nightlife_light",
    "nightlife silhouettes dim": "nightlife_light",
    "nightlife luxury afterhours": "luxury_bar,nightlife_light",
}

def fix_themes_line(line: str) -> str:
    """Fix a themes= line to use valid folder names."""
    if not line.startswith("themes="):
        return line
    
    themes_part = line.split("=", 1)[1].strip()
    
    # Check if already valid (has underscores and commas, no spaces except in folder names)
    if "_" in themes_part and "," in themes_part:
        return line
    
    # Try direct mapping first
    if themes_part in THEME_MAP:
        return f"themes={THEME_MAP[themes_part]}"
    
    # Parse individual words/tokens
    tokens = themes_part.replace(",", " ").split()
    
    # Map each token
    mapped = set()
    for token in tokens:
        token_lower = token.lower().strip()
        if token_lower in THEME_MAP:
            result = THEME_MAP[token_lower]
            mapped.update(result.split(","))
    
    # Default if no mapping found
    if not mapped:
        mapped = {"nightlife_crowd", "abstract_aesthetic"}
    
    return f"themes={','.join(sorted(mapped))}"

def main():
    posts_dir = Path("posts")
    
    fixed = 0
    for spec_file in posts_dir.glob("*/caption_spec.txt"):
        lines = spec_file.read_text(encoding="utf-8").splitlines()
        
        new_lines = []
        changed = False
        
        for line in lines:
            if line.startswith("themes="):
                new_line = fix_themes_line(line)
                if new_line != line:
                    print(f"{spec_file.parent.name}:")
                    print(f"  OLD: {line}")
                    print(f"  NEW: {new_line}")
                    changed = True
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        
        if changed:
            spec_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            fixed += 1
    
    print(f"\n✅ Fixed {fixed} files")

if __name__ == "__main__":
    main()
