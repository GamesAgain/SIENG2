from src.core.configurable.drafts import TECHNIQUE_LABELS

# Display data of the technique cards (the names come from core, the rest is GUI only)
TECHNIQUE_DISPLAY = {
    "lsbpp": {
        "label": TECHNIQUE_LABELS["lsbpp"], "description": "Embed text in PNG",
        "accent": "blue", "hex": "#38BDF8",
    },
    "locomotive": {
        "label": TECHNIQUE_LABELS["locomotive"], "description": "Embed files in PNG",
        "accent": "purple", "hex": "#A78BFA",
    },
    "metadata": {
        "label": TECHNIQUE_LABELS["metadata"], "description": "Hide data in PNG or MP3 metadata",
        "accent": "orange", "hex": "#F59E0F",
    },
}
