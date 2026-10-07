import sys
from pathlib import Path
import pytest
from backend.routing.dijkstra import shortest_path
from backend.routing.graph_builder import adjacency
from backend.routing.risk_router import exposure,validate_point
from backend.app import create_app

def test_dijkstra_cost_and_closure():
    g={1:[(2,{'d':1}),(3,{'d':5})],2:[(3,{'d':1})]}
    p,c=shortest_path(g,1,3,lambda e:e['d']);assert c==2 and len(p)==2
    p,c=shortest_path(g,1,3,lambda e:e['d'] if e['d']>1 else None);assert c==5
    with pytest.raises(ValueError,match='No route'):shortest_path(g,3,1,lambda e:e['d'])

def test_negative_cost_rejected():
    with pytest.raises(ValueError,match='nonnegative'):shortest_path({1:[(2,{})]},1,2,lambda e:-1)

def test_modes_and_direction():
    e={'from_node':1,'to_node':2,'oneway':1,'walk':True,'car':True,'bicycle':False,'tags':{}}
    assert 2 in adjacency([e],'walking')
    assert 2 not in adjacency([e],'car')
    assert not adjacency([e],'bicycle')

def test_unknown_is_not_zero():
    assert exposure({'risks':{}},'kochi')==(100,0,0)
    assert exposure({'risks':{'flood':{'coverage_fraction':.5,'normalised_value':40}}},'kochi')==(70,.5,20)

@pytest.mark.parametrize('point',[[float('nan'),76],[91,0],[0,0],[True,76],['10',76],[]])
def test_invalid_or_outside_point(point):
    with pytest.raises(ValueError):validate_point('kochi',point)

@pytest.fixture
def client():return create_app({'TESTING':True,'SECRET_KEY':'test-only-secret'}).test_client()

def test_csrf_and_pages(client):
    for p in ['/','/map','/dashboard','/shelters','/data','/historical','/methodology','/admin']:
        assert client.get(p).status_code==200
    assert client.post('/api/route',json={}).status_code==403
    with client.session_transaction() as s:token=s['csrf']
    assert client.post('/api/route',json={'region':'unsupported'},headers={'X-CSRF-Token':token}).status_code==400

def test_database_failure_is_explicit(client,monkeypatch):
    import app,mysql.connector
    def failed(*args,**kwargs):raise mysql.connector.Error('test-only connection error',errno=1045)
    monkeypatch.setattr(app,'query',failed)
    r=client.get('/api/status');assert r.status_code==503 and 'no fallback' in r.json['error']

def test_real_comparison_logic_with_test_fixture(monkeypatch):
    # Synthetic graph is isolated unit-test input, never imported or presented as geographic evidence.
    import routing.risk_router as router
    nodes={1:(76.32631,10.0614),2:(76.32731,10.0614),3:(76.32831,10.0614)}
    def edge(i,u,v,d,s):return {'id':i,'osm_way_id':i,'from_node':u,'to_node':v,'distance_m':d,'name':'unit-test edge','oneway':0,'walk':True,'bicycle':True,'car':True,'tags':{'_coords':[nodes[u],nodes[v]]},'risks':{'flood':{'coverage_fraction':1,'normalised_value':s}}}
    edges=[edge(1,1,3,100,100),edge(2,1,2,80,0),edge(3,2,3,80,0)]
    monkeypatch.setattr(router,'load_graph',lambda r:(nodes,edges))
    r=router.compare('kochi',[10.0614,76.32631],[10.0614,76.32831],'walking','flood')
    assert r['shortest']['distance_m']==100 and r['recommended']['distance_m']==160
    assert r['recommended']['risk_index']==0 and r['recommended']['coverage']==1
    r=router.compare('kochi',[10.0614,76.32631],[10.0614,76.32831],'walking','flood',{1:'Closed'})
    assert r['shortest']['distance_m']==160 and r['simulated']
