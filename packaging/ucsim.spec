# PyInstaller spec for the Windows desktop app:  pyinstaller packaging/ucsim.spec --noconfirm
# (run `npm run build` in web/ first so web/dist exists)
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
ICON = ROOT / "packaging" / "icon.ico"

datas = [
    (str(ROOT / "ucsim" / "config"), "ucsim/config"),
    (str(ROOT / "ucsim" / "priors"), "ucsim/priors"),
    (str(ROOT / "ucsim" / "geo" / "data"), "ucsim/geo/data"),
    (str(ROOT / "web" / "dist"), "web/dist"),
    (str(ROOT / "web" / "public" / "geo"), "web/public/geo"),
    (str(ROOT / "ucsim" / "llm" / "prompts"), "ucsim/llm/prompts"),
]
hidden = collect_submodules("uvicorn") + collect_submodules("ucsim.engine") + collect_submodules("ucsim.api") + collect_submodules("ucsim.llm") + collect_submodules("mcp.server") + collect_submodules("mcp.shared") + ["ucsim.updater", "ucsim._build_version", "ucsim.llm.mcp_server", "anyio._backends._asyncio",
    "ucsim.analysis.query", "ucsim.analysis.explain", "ucsim.analysis.person", "ucsim.population.build",
    "scipy.special", "scipy.spatial", "scipy.stats", "yaml", "orjson",
]
try:
    hidden += collect_submodules("webview")
except Exception:
    pass

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hidden,
    excludes=["pyarrow", "duckdb", "pandas", "matplotlib", "IPython", "pytest", "notebook", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ProvoOremSimulator",
    console=False,
    icon=str(ICON) if ICON.exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ProvoOremSimulator")
