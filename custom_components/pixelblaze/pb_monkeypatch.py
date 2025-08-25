# monkeypatch for https://github.com/zranger1/pixelblaze-client/pull/24
# Remove once that is merged and released

import re
if not hasattr(re, "T"):
    try:
        re.T = re.TEMPLATE  # closest semantic
    except Exception:
        re.T = 0            # harmless fallback

from pixelblaze import Pixelblaze
