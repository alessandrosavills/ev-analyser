import requests
import pandas as pd

api_key = '4ec38734-0579-4f54-a83b-dfec92d7b884'

def get_chargers():
    url = 'https://api.openchargemap.io/v3/poi/'
    params = {
        'output': 'json',
        'countrycode': 'GB',
        'maxresults': 5000,
        'compact': True,
        'verbose': False,
        'key': api_key
    }

    response = requests.get(url, params=params)
    data = response.json()

    chargers = []
    for item in data:
        address = item.get('AddressInfo', {})
        connections = item.get('Connections', [])

        if connections and 'ConnectionType' in connections[0] and connections[0]['ConnectionType'] is not None:
            charger_type = connections[0]['ConnectionType'].get('Title')
        else:
            charger_type = None

        chargers.append({
            'latitude': address.get('Latitude'),
            'longitude': address.get('Longitude'),
            'title': address.get('Title'),
            'operator': item.get('OperatorInfo', {}).get('Title') if item.get('OperatorInfo') else None,
            'status': item.get('StatusType', {}).get('Title'),
            'charger_type': charger_type,
            'num_ports': len(connections)
        })

    df = pd.DataFrame(chargers)
    df.to_csv('chargers.csv', index=False)
    print(f"Saved {len(df)} chargers to chargers.csv")