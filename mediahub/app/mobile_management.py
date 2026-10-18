"""Final focused v0.19 extensions; existing acquisition routes remain authoritative."""
from fastapi import Query
from typing import Literal

from . import main, download_management, ratings_store
from .mobile_management_ui import UI

app = main.app
app.version = '0.19.2'
app.add_event_handler('startup', download_management.initialise)
app.add_api_route('/api/download-management', download_management.listing, methods=['GET'])
app.add_api_route('/api/download-management/{request_id}/attempts', download_management.attempts, methods=['GET'])


async def availability(_: main.CurrentUser, media_type: Literal['movie','tv']=Query('movie')):
    return ratings_store.availability(media_type)


app.add_api_route('/api/ratings/availability', availability, methods=['GET'])
if 'MEDIAHUB_MANAGEMENT_V019' not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace('</body>', UI+'\n</body>')
