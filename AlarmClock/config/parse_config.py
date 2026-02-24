from configparser import ConfigParser
from pathlib import Path
from typing import Optional


def load_hf_token(config_path: Optional[str] = None) -> str:
	"""Load the `hf_token` value from a config.ini file.

	If `config_path` is provided it is used directly; otherwise the function
	searches for `config.ini` in the current `config` folder, the project
	root (one level up), and the parent of that (two levels up).
	"""
	parser = ConfigParser()
	if config_path:
		cfg = Path(config_path)
	else:
		base = Path(__file__).parent
		candidates = [base / "config.ini", base.parent / "config.ini", base.parent.parent / "config.ini"]
		cfg = next((p for p in candidates if p.exists()), None)
	if cfg is None or not cfg.exists():
		raise FileNotFoundError("config.ini not found; pass its path to load_hf_token(config_path=...)")
	parser.read(cfg)

	defaults = {k.lower(): v for k, v in parser.defaults().items()} if parser.defaults() else {}
	for key in ("hf_token", "huggingface_token", "token"):
		if key in defaults:
			return defaults[key]

	sections = parser.sections()
	for section in sections:
		items = {k.lower(): v for k, v in parser.items(section)}
		for key in ("hf_token", "huggingface_token", "token"):
			if key in items:
				return items[key]

	raise KeyError("hf_token not found in config.ini")


if __name__ == "__main__":
	try:
		token = load_hf_token()
		print("hf_token loaded:", token[:4] + "..." if token else "(empty)")
	except Exception as e:
		print("Error loading hf_token:", e)

