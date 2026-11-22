"""Download third-party score sources into prep/sources/ (git-ignored)."""
import subprocess
from pathlib import Path

SOURCES = Path(__file__).resolve().parent.parent / "sources"
WTC_REPO = "https://github.com/humdrum-tools/bach-wtc-fugues"
INVENTIONS_REPO = "https://github.com/humdrum-tools/inventions"
MUSICAL_OFFERING_REPO = "https://github.com/craigsapp/bach-musical-offering"
ART_OF_FUGUE_REPO = "https://github.com/craigsapp/art-of-the-fugue"
# git repositories cloned into sources/<name>; a kern path starting "<name>/" needs it
REPOS = {"bach-wtc-fugues": WTC_REPO, "inventions": INVENTIONS_REPO,
         "bach-musical-offering": MUSICAL_OFFERING_REPO, "art-of-the-fugue": ART_OF_FUGUE_REPO}


def fetch_repo(name: str) -> Path:
    """Clone the source repository ``name`` (a key of REPOS) once; return the clone's path."""
    dest = SOURCES / name
    if not dest.exists():
        SOURCES.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", REPOS[name], str(dest)], check=True)
    return dest


def fetch_wtc_fugues() -> Path:
    """Clone humdrum-tools/bach-wtc-fugues once; return the clone's path."""
    return fetch_repo("bach-wtc-fugues")


def fetch_inventions() -> Path:
    """Clone humdrum-tools/inventions (Inventions and Sinfonias, BWV 772-801) once."""
    return fetch_repo("inventions")


def fetch_musical_offering() -> Path:
    """Clone craigsapp/bach-musical-offering (BWV 1079: the ricercars and the Canon a 4) once."""
    return fetch_repo("bach-musical-offering")


def fetch_art_of_fugue() -> Path:
    """Clone craigsapp/art-of-the-fugue (BWV 1080: the contrapuncti and canons) once."""
    return fetch_repo("art-of-the-fugue")
