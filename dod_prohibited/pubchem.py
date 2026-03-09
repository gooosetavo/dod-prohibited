"""Client for fetching and caching PubChem compound data."""

import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_PROPERTIES = "MolecularFormula,MolecularWeight,IUPACName,InChIKey,CanonicalSMILES"
_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov"


def conformer_embed_html(cid: int, name: str = "") -> str:
    """Return an iframe HTML string for the PubChem 3D conformer viewer."""
    url = f"{_BASE_URL}/compound/{cid}#section=3D-Conformer&embed=true"
    title = f"{name} 3D conformer" if name else f"CID {cid} 3D conformer"
    return (
        '<div style="overflow-x:auto;width:100%;">'
        f'<iframe src="{url}" loading="lazy" title="{title}" '
        f'style="width:100%;min-width:600px;height:500px;border:none;display:block;"></iframe>'
        '</div>'
    )


class PubChemClient:
    """Fetches and caches PubChem compound properties."""

    def __init__(self, cache_dir: Path = Path(".cache/pubchem")):
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def get_properties(self, cid: int) -> Optional[Dict[str, Any]]:
        """Return cached or freshly fetched compound properties for a PubChem CID."""
        cache_file = self.cache_dir / f"{cid}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        url = f"{_BASE_URL}/rest/pug/compound/cid/{cid}/property/{_PROPERTIES}/JSON"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())
            props = data["PropertyTable"]["Properties"][0]
            cache_file.write_text(json.dumps(props))
            # time.sleep(0.25)
            return props
        except Exception as e:
            logger.warning(f"PubChem property fetch failed for CID {cid}: {e}")
            return None
