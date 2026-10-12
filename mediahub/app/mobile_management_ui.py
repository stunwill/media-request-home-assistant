"""Compose small, separately maintainable management assets into ingress HTML."""
from pathlib import Path

_assets = Path(__file__).with_name('assets')
UI = '<!-- MEDIAHUB_MANAGEMENT_V019 --><style>'+(_assets/'management.css').read_text()+'</style><script>'+(_assets/'management.js').read_text()+'</script>'
