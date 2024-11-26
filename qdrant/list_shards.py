import requests
import flask


PROTOCOL = 'http'
URL = '192.168.0.230'
PORT = 6333
API_KEY = 'some'

app = flask.Flask(__name__, static_folder='/app')


try:
    api_key = API_KEY
    
except:
    headers = {}    

def list_colections(protocol, url, port, headers):
    ready_url = f'{protocol}://{url}:{port}/collections'
    response = requests.request("GET", ready_url, headers=headers)
    collections = []
    try:
        for colection in response.json()['result']['collections']:
            collections.append(colection['name'])
    except Exception as e:
        print(f'some problem with fetching collections -> {e}')        
    print(f'collections in cluster {collections}')
    return collections


def get_shards(protocol, url, port, headers, collections):
    shards_dictionary = {}
    for collection in collections:
        ready_url = f'{protocol}://{url}:{port}/collections/{collection}/cluster'
        response = requests.request("GET", ready_url, headers=headers)
        try:
            shards_dictionary[collection] = {}
            shards_dictionary[collection]['shard_count'] = response.json()['result']['shard_count']
            shards_dictionary[collection]['local_shards'] = response.json()['result']['local_shards']
            shards_dictionary[collection]['remote_shards'] = response.json()['result']['remote_shards']
        except Exception as e:
            print(f'some problem with fetching shards -> {e}')      
    print(shards_dictionary)
    return shards_dictionary


@app.route('/get',methods = ['GET'])
def render_site():
    return flask.render_template('form.html')



@app.route('/post',methods = ['POST'])
def setup_temp():
    try:
        protocol = f"{flask.request.form['protocol']}"
        url = f"{flask.request.form['url']}"
        port = f"{flask.request.form['port']}"
        api_key = f"{flask.request.form['api_key']}"
        headers = {
        'api-key': api_key,
        }
    except Exception as e: 
        print(f'something wrong with getting form {e}')
    try:
        collections = list_colections(protocol, url, port, headers)   
        data = get_shards(protocol, url, port, headers,collections)
    except Exception as e: 
        print(f'something wrong with getting getting stuff from cluster {e}')


    return flask.render_template('result.html',data=data)

    

app.run(host="0.0.0.0", port=5002)