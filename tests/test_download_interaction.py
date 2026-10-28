"""Download correlation logging must not retain acquisition/session secrets."""
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from mediahub.app import main, movie_release_endpoint as endpoint


@pytest.mark.parametrize('result,error,outcome',[
    ({'request':{'status':'queued'}}, None, 'completed'),
    (None, HTTPException(409, 'secret-indexer-url'), 'rejected'),
    (None, HTTPException(504, 'secret-indexer-url'), 'timeout_unconfirmed'),
    (None, asyncio.CancelledError(), 'cancelled_unconfirmed'),
])
def test_submission_correlation_and_cleanup_are_redacted(caplog,result,error,outcome):
    principal=main.Principal('private-user','private-name','Private Name','admin',True)
    payload=main.MovieRequestCreate(release_token='private-token-secret')
    request=SimpleNamespace(headers={'X-MediaHub-Correlation-ID':'a'*32})

    async def run(operation,*_args):
        operation.close()
        if error is not None:
            raise error
        return result

    caplog.set_level(logging.INFO)
    with patch.object(endpoint,'_until_disconnected',run):
        if error is not None:
            with pytest.raises(type(error)):
                asyncio.run(endpoint.request_movie(123,payload,principal,request))
        else:
            assert asyncio.run(endpoint.request_movie(123,payload,principal,request)) == result
    logs=caplog.text
    assert 'correlation='+'a'*32 in logs
    assert f'outcome={outcome}' in logs and 'cleanup=complete' in logs
    assert 'selection=exact' in logs and 'tmdb_id=123' in logs
    assert all(secret not in logs for secret in ['private-user','private-name','Private Name','private-token-secret','secret-indexer-url'])


def test_untrusted_correlation_header_is_not_logged(caplog):
    async def run(operation,*_args):
        operation.close()
        return {'status':'queued'}
    caplog.set_level(logging.INFO)
    with patch.object(endpoint,'_until_disconnected',run):
        asyncio.run(endpoint.request_movie(123,main.MovieRequestCreate(),main.Principal('u','u','U','admin',True),
                    SimpleNamespace(headers={'X-MediaHub-Correlation-ID':'private-secret\nforged-log'})))
    assert 'private-secret' not in caplog.text and 'forged-log' not in caplog.text
    assert 'cleanup=complete' in caplog.text


def test_every_composed_inline_script_parses(tmp_path):
    import re
    import subprocess
    scripts=re.findall(r'<script[^>]*>(.*?)</script>',main.INDEX_HTML,re.S)
    assert scripts
    for index,script in enumerate(scripts):
        path=tmp_path/f'composed-{index}.js'
        path.write_text(script)
        result=subprocess.run(['node','--check',str(path)],capture_output=True,text=True,timeout=10)
        assert result.returncode == 0, result.stderr
