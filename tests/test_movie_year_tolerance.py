"""Movie identity is independent of household eligibility and provider coverage."""
import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mediahub.app import watchlist_main, main, runtime, release_identity_main  # noqa: F401
from mediahub.app import release_identity as identity, prowlarr_discovery as discovery
from mediahub.app import release_lifecycle, release_activity, release_search_control as control
from test_birdman_discovery import run_search, CAPS

MOVIE = {'tmdb_id':653712, 'imdb_id':'tt10702148', 'title':'The Killing of Two Lovers',
         'original_title':'The Killing of Two Lovers', 'year':'2021'}
RELEASE = {'title':'The Killing of Two Lovers 2020 1080p WebRip EAC3 5 1 x265-Lootera',
           'size':int(2.15*1024**3), 'seeders':1, 'indexerId':7, 'indexer':'Fixture Movies',
           'guid':'lootera', 'categories':[{'id':2000,'name':'Movies'}]}


@pytest.mark.parametrize('delta,state',[(0,'strong'),(-1,'acceptable'),(1,'acceptable'),(-2,'suspicious'),(2,'suspicious'),(-10,'rejected')])
def test_year_confidence(delta,state):
    match=identity.validate_movie_release(MOVIE,{'title':f'The Killing of Two Lovers {2021+delta} 1080p'})
    assert match.state==state
    assert match.selected_year==2021 and match.release_year==2021+delta
    assert match.year_tolerated==(abs(delta)==1)


@pytest.mark.parametrize('year,kind',[(2019,1),(2018,3),(2024,4)])
def test_verified_regional_years_support_festival_theatrical_and_digital(year,kind):
    movie={**MOVIE,'release_dates':{'AU':[{'release_date':f'{year}-01-01','type':kind}]}}
    match=identity.validate_movie_release(movie,{'title':f'The Killing of Two Lovers {year} 1080p'})
    assert match.eligible and match.year_tolerated and 'TMDb AU' in ' '.join(match.reasons)


@pytest.mark.parametrize('ids',[{'imdbId':'tt10702148'},{'tmdbId':653712}])
def test_verified_ids_override_year_and_title(ids):
    match=identity.validate_movie_release(MOVIE,{'title':'Foreign Distribution Title 2010 1080p',**ids})
    assert match.eligible and match.score==140


@pytest.mark.parametrize('ids',[{'imdbId':'tt9999999'}, {'tmdbId':999},
    {'imdbId':'tt10702148','tmdbId':999}, {'imdbId':'tt10702148','imdb_id':'tt9999999'},
    {'title':RELEASE['title']+' [tmdb-999]'}, {'title':RELEASE['title']+' [imdb-tt9999999]'}])
def test_conflicting_ids_always_win(ids):
    match=identity.validate_movie_release(MOVIE,{**RELEASE,**ids})
    assert match.state=='rejected' and 'identifier' in match.reasons[0]


def test_genuine_remakes_and_same_title_collision():
    movie={'title':'The Thing','year':'1982','imdb_id':'tt0084787'}
    assert not identity.validate_movie_release(movie,{'title':'The Thing 2011 1080p'}).eligible
    assert not identity.validate_movie_release(movie,{'title':'The Thing 1982 1080p','imdbId':'tt0905372'}).eligible
    # IDs distinguish even adjacent-year films, irrespective of the tolerance.
    assert not identity.validate_movie_release(movie,{'title':'The Thing 1983 1080p','imdbId':'tt0905372'}).eligible


@pytest.mark.parametrize('title',["SCHINDLERS_LIST.1993.1080p.x265-GROUP", "Schindler’s List 1994 1080p"])
def test_apostrophes_and_formatting(title):
    assert identity.validate_movie_release({'title':"Schindler's List",'year':'1993'},{'title':title}).eligible


def test_alternative_title_and_missing_year():
    movie={**MOVIE,'alternative_titles':[{'title':'Two Lovers'}]}
    assert identity.validate_movie_release(movie,{'title':'Two.Lovers.2020.1080p.x265-Lootera'}).eligible
    assert identity.validate_movie_release(MOVIE,{'title':'The Killing of Two Lovers 1080p x265'}).eligible
    assert identity.validate_movie_release({'title':MOVIE['title']},RELEASE).eligible
    assert not identity.validate_movie_release(MOVIE,{'title':'The Killing of Two Lovers Returns 2021 1080p'}).eligible


@pytest.mark.parametrize('changes,eligible', [({},True),({'size':4*1024**3,'title':RELEASE['title'].replace('2020','2021')},False),
    ({'title':RELEASE['title'].replace('1080p','720p')},False),
    ({'title':RELEASE['title'].replace('1080p','')},False),({'seeders':0},False)])
def test_reported_movie_full_filter_chain(changes,eligible):
    async def scenario():
        radarr=type('R',(),{'_request':AsyncMock(return_value=[{'id':21,'name':'Fixture Movies'}])})()
        with patch.object(runtime,'_original_search_movie_releases',AsyncMock(return_value=({'id':88},[],False))), \
             patch.object(runtime,'_prowlarr_search',AsyncMock(return_value=[{**RELEASE,**changes}])), \
             patch.object(main,'configured_clients',return_value=(None,radarr,None)), \
             patch.object(main,'load_options',return_value={}):
            return await release_identity_main.search_movie_releases(MOVIE['tmdb_id'],
                main.ReleaseRules(quality_mode='1080p_only',maximum_size_gb=3,minimum_seeders=1), 'test-user',movie=MOVIE)
    _,releases,_=asyncio.run(scenario())
    assert len(releases)==1 and releases[0]['eligible']==eligible
    assert releases[0]['identity_status']=='accepted'
    assert bool(releases[0].get('release_token'))==eligible
    if not eligible:assert releases[0]['primary_rejection']['category']=='mediahub_policy'


def test_uncertain_selection_cannot_be_submitted():
    async def scenario():
        with pytest.raises(main.HTTPException) as error:
            await runtime.validate_direct_selection({**RELEASE,'title':RELEASE['title'].replace('2020','2019')},main.ReleaseRules(),MOVIE,None)
        assert error.value.status_code==409
    asyncio.run(scenario())


def test_hash_deduplication_preserves_distinct_encodes_and_ids():
    rows=[RELEASE,{**RELEASE,'indexerId':8,'guid':'other-indexer'},
          {**RELEASE,'guid':'different-hash','infoHash':'b'*40},
          {**RELEASE,'title':RELEASE['title'].replace('x265','x264'),'guid':'different-encode','infoHash':'c'*40}]
    rows=[{'infoHash':'a'*40,**row} for row in rows]
    results,trace=run_search(lambda req:httpx.Response(200,json=CAPS if req.url.path.endswith('/indexer') else rows),MOVIE)
    assert len(results)==4 and trace['unique_releases']==4
    assert trace['duplicates_removed']==trace['raw_results']-4
    assert all(row['identity']=='accepted' and row['year_tolerated'] for row in trace['release_exclusions'])
    async def scenario():
        radarr=type('R',(),{'_request':AsyncMock(return_value=[{'id':21,'name':'Fixture Movies'}])})()
        with patch.object(runtime,'_original_search_movie_releases',AsyncMock(return_value=({'id':88},[],False))), \
             patch.object(runtime,'_prowlarr_search',AsyncMock(return_value=results)), \
             patch.object(main,'configured_clients',return_value=(None,radarr,None)), \
             patch.object(main,'load_options',return_value={}):
            return await release_identity_main.search_movie_releases(MOVIE['tmdb_id'],main.ReleaseRules(),'test-user',movie=MOVIE)
    _,releases,_=asyncio.run(scenario())
    assert len(releases)==3



def test_partial_auth_failure_keeps_successful_results():
    def handler(req):
        if req.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
        return httpx.Response(401) if 'categories' in req.url.params else httpx.Response(200,json=[RELEASE])
    results,trace=run_search(handler,MOVIE)
    assert len(results)==1 and trace['prowlarr_status']=='partial' and trace['failed_queries']


@pytest.mark.parametrize('value,expected',[('9',9),('100',10),('-1',1),('nan',8),('bad',8)])
def test_configurable_bounded_query_timeout(monkeypatch,value,expected):
    monkeypatch.setenv('MEDIAHUB_PROWLARR_QUERY_SECONDS',value)
    assert discovery.query_seconds()==expected


def test_final_diagnostics_count_unique_candidates_and_join_by_identity():
    async def scenario():
        async def candidates(*args,**kwargs):
            control.discovery_diagnostics.get().update({'raw_results':9,'duplicates_removed':6,
                'title_mismatches':1,'category_exclusions':0,'release_exclusions':[
                    {'candidate_id':'one','release':'same title','source':'same indexer','status':'candidate'},
                    {'candidate_id':'two','release':'same title','source':'same indexer','status':'candidate'}]})
            return {'releases':[
                {'candidate_id':'one','title':'same title','eligible':True},
                {'candidate_id':'two','title':'same title','eligible':False,'policy_rejections':['Too big'],
                 'primary_rejection':{'category':'mediahub_policy'},'rejection_details':[{'category':'mediahub_policy'}]}]}
        with patch.object(release_lifecycle,'movie_details',AsyncMock(return_value={'lifecycle':{'state':'released_unknown'}})), \
             patch.object(release_activity,'movie_releases',candidates):
            return await release_lifecycle.release_search(123,main.ReleaseRules(),main.Principal('id','user','User','admin',True))
    trace=asyncio.run(scenario())['discovery_diagnostics']
    assert trace['final_unique_candidates']==3
    assert trace['final_candidate_counts']=={'eligible':1,'identity':1,'category':0,'mediahub_policy':1}
    assert [row['status'] for row in trace['release_exclusions']]==['eligible','excluded']
    assert trace['release_exclusions'][1]['reasons']==['Too big']


def test_distinct_over_limit_releases_are_not_collapsed_by_title():
    async def scenario():
        radarr=type('R',(),{'_request':AsyncMock(return_value=[{'id':21,'name':'Fixture Movies'}])})()
        rows=[{**RELEASE,'size':4*1024**3,'guid':guid} for guid in ('first','second')]
        with patch.object(runtime,'_original_search_movie_releases',AsyncMock(return_value=({'id':88},[],False))), \
             patch.object(runtime,'_prowlarr_search',AsyncMock(return_value=rows)), \
             patch.object(main,'configured_clients',return_value=(None,radarr,None)), \
             patch.object(main,'load_options',return_value={}):
            return await release_identity_main.search_movie_releases(MOVIE['tmdb_id'],main.ReleaseRules(), 'test-user',movie=MOVIE)
    _,releases,_=asyncio.run(scenario())
    assert len(releases)==2 and not any(item['eligible'] for item in releases)


def test_failed_prowlarr_does_not_discard_successful_radarr_results():
    async def scenario():
        with patch.object(runtime,'_original_search_movie_releases',AsyncMock(return_value=({'id':88},[{'title':'Radarr result'}],False))), \
             patch.object(runtime,'_prowlarr_search',AsyncMock(side_effect=main.HTTPException(503,'Credentials rejected'))), \
             patch.object(main,'configured_clients',return_value=(None,type('R',(),{})(),None)), \
             patch.object(main,'load_options',return_value={}):
            return await runtime._search_movie_releases(MOVIE['tmdb_id'],main.ReleaseRules(),'test-user',movie=MOVIE)
    _,releases,_=asyncio.run(scenario())
    assert releases==[{'title':'Radarr result'}]
