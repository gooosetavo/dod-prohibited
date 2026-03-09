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
        '<div style="width:100%;aspect-ratio:4/3;max-height:500px;">'
        f'<iframe src="{url}" loading="lazy" title="{title}" '
        f'style="width:100%;height:100%;border:none;display:block;"></iframe>'
        '</div>'
    )


class PubChemClient:
    """Fetches and caches PubChem compound properties."""

    def __init__(self, cache_dir: Path = Path(".cache/pubchem")):
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def get_properties(self, cid: int) -> Optional[Dict[str, Any]]:
        """Return cached or freshly fetched compound properties for a PubChem CID.

        The returned dict includes a ``has_3d_conformer`` boolean key indicating
        whether PubChem has a 3D conformer for this compound.
        """
        cache_file = self.cache_dir / f"{cid}.json"
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                # If the cache entry already has the conformer flag, use it as-is.
                if "has_3d_conformer" in cached:
                    return cached
                # Older cache entries lack the flag — fall through to re-check.
            except (json.JSONDecodeError, OSError):
                pass

        props_url = f"{_BASE_URL}/rest/pug/compound/cid/{cid}/property/{_PROPERTIES}/JSON"
        try:
            with urllib.request.urlopen(props_url, timeout=15) as resp:
                data = json.loads(resp.read())
            props = data["PropertyTable"]["Properties"][0]
        except Exception as e:
            logger.warning(f"PubChem property fetch failed for CID {cid}: {e}")
            return None

        # Check whether a 3D conformer exists for this compound.
        conformer_url = f"{_BASE_URL}/rest/pug/compound/cid/{cid}/conformers/JSON"
        try:
            with urllib.request.urlopen(conformer_url, timeout=15) as resp:
                resp.read()
            props["has_3d_conformer"] = True
        except Exception:
            props["has_3d_conformer"] = False

        cache_file.write_text(json.dumps(props))
        return props
