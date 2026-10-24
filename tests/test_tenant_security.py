"""Real handlers and memories with local fakes, never a live provider/database."""
import asyncio
import importlib
import sys
import threading
import types
import pytest
from app.session_history import SessionHistory
from app.security_context import private_tools_allowed

@pytest.fixture
def server(monkeypatch):
    sdk = types.ModuleType('supabase')
    sdk.Client = object
    sdk.create_client = lambda *a, **k: pytest.fail('External database access')
    monkeypatch.setitem(sys.modules, 'supabase', sdk)
    database = importlib.import_module('app.database')
    monkeypatch.setattr(database, 'init_db', lambda: None)
    monkeypatch.setattr(threading.Thread, 'start', lambda self: None)
    module = importlib.import_module('app.server')
    module.app.config.update(TESTING=True, SECRET_KEY='local-test-only')
    for name in ('get_produits', 'get_marches', 'get_latest_prices'):
        monkeypatch.setattr(module, name, lambda: [])
    monkeypatch.setattr(module, 'browser_history', SessionHistory())
    monkeypatch.setattr(module, 'run_async', asyncio.run)
    monkeypatch.setattr(module, '_ML_AVAILABLE', True)
    async def answer(message, *args):
        return 'Réponse à ' + message
    monkeypatch.setattr(module, 'ask_agent', answer)
    return module

def test_public_pages_never_load_shared_database_history(server, monkeypatch):
    database = importlib.import_module('app.database')
    monkeypatch.setattr(database, '_get_client', lambda: pytest.fail('Shared history read'))
    a, b = server.app.test_client(), server.app.test_client()
    assert a.post('/chat', data={'message': 'confidentiel-FAITIERE-A'}).status_code == 200
    assert b.post('/chat', data={'message': 'confidentiel-FAITIERE-B'}).status_code == 200
    assert 'confidentiel-FAITIERE-A' in a.get('/').text
    assert 'confidentiel-FAITIERE-A' not in b.get('/').text
    a.delete('/chat/clear')
    assert 'confidentiel-FAITIERE-A' not in a.get('/').text
    assert 'confidentiel-FAITIERE-B' in b.get('/').text

@pytest.mark.parametrize('path,method', [('/engine/memory','get'),('/engine/feedback','post'),
    ('/ml/risk','post'),('/ml/segmentation','post'),('/ml/kpi','post'),('/ml/interpret','post'),
    ('/api/v1/risk','post'),('/api/v1/segmentation','post'),('/api/v1/kpi','get')])
def test_private_analysis_rejects_direct_anonymous_access(server, path, method):
    assert getattr(server.app.test_client(), method)(path).status_code == 401

def test_synthetic_yield_withdrawn(server):
    assert server.app.test_client().post('/ml/crop-yield').status_code == 410

def test_supplied_card_is_not_used_to_write_conversations(server, monkeypatch):
    engine = types.ModuleType('app.agents.engine')
    engine._AGENTSCOPE_AVAILABLE = True
    async def query(message, audience):
        assert not private_tools_allowed.get()
        return {'formatted_response': 'Public', 'agent_type': 'market_intel'}
    engine.process_query = query
    monkeypatch.setitem(sys.modules, 'app.agents.engine', engine)
    client = server.app.test_client()
    assert client.post('/api/v1/agent/chat', json={'message': 'prix du maïs',
        'card_number': 'CARTE-AUTRE-FAITIERE'}).json['response'] == 'Public'
    assert client.post('/api/v1/agent/chat', json=['wrong']).status_code == 400
    assert client.post('/api/v1/agent/chat', json={'message':'x'*4001}).status_code == 400

def test_cache_is_bounded_expires_and_copies_results():
    now = [0]
    history = SessionHistory(capacity=2, max_messages=2, ttl=10, clock=lambda: now[0])
    for text in ('a1','a2','a3'): history.append('A','user',text)
    snapshot = history.read('A')
    assert [r['contenu'] for r in snapshot] == ['a2','a3']
    snapshot[0]['contenu'] = 'mutated'
    assert history.read('A')[0]['contenu'] == 'a2'
    history.append('B','user','b'); history.append('C','user','c')
    assert history.read('A') == []
    now[0] = 11
    assert history.read('B') == []

def test_database_history_fails_closed_without_verified_scope(server, monkeypatch):
    database = importlib.import_module('app.database')
    monkeypatch.setattr(database, '_get_client', lambda: pytest.fail('Unscoped database access'))
    assert database.get_conversations() == []
    with pytest.raises(ValueError): database.clear_conversations()

def test_verified_admin_capability_is_reset_after_call(server, monkeypatch):
    guard = importlib.import_module('app.auth_guard')
    monkeypatch.setattr(guard, '_user_id_from_token', lambda token:'admin')
    class Query:
        def table(self,*args): return self
        def select(self,*args): return self
        def eq(self,*args): return self
        def is_(self,*args): return self
        def limit(self,*args): return self
        def execute(self): return types.SimpleNamespace(data=[{'role':'super_admin'}])
    monkeypatch.setattr(guard,'get_db',lambda:Query())
    @guard.require_super_admin
    def allowed():
        assert private_tools_allowed.get()
        return 'ok'
    with server.app.test_request_context(headers={'Authorization':'Bearer local-test'}):
        assert allowed() == 'ok'
        assert not private_tools_allowed.get()

def test_agents_have_fresh_memory_and_public_toolkit(server, monkeypatch):
    names = {
        'app.tools':['consulter_prix','lister_produits','lister_marches','enregistrer_prevision','analyser_tendance','prevoir_prix'],
        'app.ml_tools':['predire_rendement_cultures','prevoir_volatilite','evaluer_risque_financier','segmenter_agriculteurs','obtenir_kpi_agriculture','consulter_meteo_region','rafraichir_donnees_climat'],
        'app.kobo_tools':['consulter_donnees_terrain','analyser_collecte_terrain','generer_formulaire_prix','generer_formulaire_agriculteur']}
    for path, methods in names.items():
        module = types.ModuleType(path)
        for name in methods:
            def tool(): pass
            tool.__name__ = name
            setattr(module,name,tool)
        monkeypatch.setitem(sys.modules,path,module)
    sys.modules.pop('app.agents.engine',None)
    engine = importlib.import_module('app.agents.engine')
    monkeypatch.setattr(engine,'_AGENTSCOPE_AVAILABLE',True)
    class Toolkit:
        def __init__(self): self.names=[]
        def register_tool_function(self,fn): self.names.append(fn.__name__)
    monkeypatch.setattr(engine,'Toolkit',Toolkit,raising=False)
    monkeypatch.setattr(engine,'InMemoryMemory',list,raising=False)
    monkeypatch.setattr(engine,'_create_model',lambda name:(None,None))
    monkeypatch.setattr(engine,'ReActAgent',lambda **kwargs:kwargs,raising=False)
    a,b=engine._get_agent('coordinator'),engine._get_agent('coordinator')
    assert a['memory'] is not b['memory']
    assert 'consulter_prix' in a['toolkit'].names
    assert not set(names['app.kobo_tools']) & set(a['toolkit'].names)
    assert not {'evaluer_risque_financier','segmenter_agriculteurs','enregistrer_prevision'} & set(a['toolkit'].names)
    capability=private_tools_allowed.set(True)
    try: assert 'consulter_donnees_terrain' in engine._get_agent('coordinator')['toolkit'].names
    finally: private_tools_allowed.reset(capability)
