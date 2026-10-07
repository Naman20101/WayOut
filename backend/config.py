"""Configuration contains no passwords. Use .env for this machine."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

REGIONS = {
 'kochi': {'name':'Kochi / Ernakulam','short':'Kochi','country':'India',
           'lat':10.0614,'lon':76.32631,'hazard':'flood',
           'subtitle':'Along the Periyar','epsg':32643,
           'srtm_tiles':['N09E076','N10E076']},
 'kathmandu': {'name':'Kathmandu Valley','short':'Kathmandu','country':'Nepal',
               'lat':27.701692,'lon':85.320597,'hazard':'earthquake',
               'subtitle':'Across the urban valley','epsg':32645,
               'srtm_tiles':['N27E085']},
 'tokyo': {'name':'Eastern Tokyo','short':'Tokyo','country':'Japan',
           'lat':35.696111,'lon':139.813889,'hazard':'earthquake',
           'subtitle':'Sumida, Koto & beyond','epsg':32654,
           'srtm_tiles':['N35E139']},
}

ELEVATION_BANDS = {
    'kochi':     (5.0, 50.0),
    'kathmandu': (1280.0, 1420.0),
    'tokyo':     (-2.0, 25.0),
}

DISCLAIMER = ('WAYOUT is an educational disaster-planning prototype. Risk '
              'calculations are based on historical and publicly available '
              'datasets and may be incomplete, outdated, or inaccurate. '
              'During an actual emergency, always follow instructions from '
              'official authorities.')

def db_config():
    return {'host':os.getenv('MYSQL_HOST','127.0.0.1'),
            'port':int(os.getenv('MYSQL_PORT','3306')),
            'user':os.getenv('MYSQL_USER','wayout'),
            'password':os.getenv('MYSQL_PASSWORD',''),
            'database':os.getenv('MYSQL_DATABASE','wayout'),
            'connection_timeout':5}

def earthdata_token():
    return os.getenv('EARTHDATA_TOKEN','').strip() or None
