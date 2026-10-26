import json
from pathlib import Path
print(json.dumps(json.loads(Path('/root/harbour-maintenance-validation.json').read_text()),indent=2))
