from flask import Flask, render_template, url_for, abort, request
from rdflib import Graph, Namespace, URIRef, BNode
from rdflib.namespace import RDF, RDFS, FOAF, OWL
from rdflib.term import BNode
from collections import defaultdict
from SPARQLWrapper import SPARQLWrapper, JSON
import os

app = Flask(__name__)

BASE = Namespace("http://example.org/mybase#")

g = Graph()
g.parse("turtledata/local_data.ttl", format="turtle")

def get_label(node):
    label = None
    # Try rdfs:label
    
    for _, _, o in g.triples((node, RDFS.label, None)):
        label = o
        break
    if label is not None:
        return str(label)
    # Try foaf:name
    for _, _, o in g.triples((node, FOAF.name, None)):
        label = o
        break
    if label is not None:
        return str(label)
    # Fallback to local name
    if isinstance(node, URIRef):
        if '#' in node:
            return node.split('#')[-1]
        else:
            return node.split('/')[-1]
    elif isinstance(node, BNode):
        return "Anonymous Node"
    else:
        return str(node)

def process_node(node, visited=None):
    if visited is None:
        visited = set()
    if node in visited:
        return {'type': 'circular', 'value': ' '}
    
    visited.add(node)
    if isinstance(node, BNode):
        properties = defaultdict(list)
        for p, o in g.predicate_objects(node):
            prop_label = get_label(p) or p.n3(g.namespace_manager)
            obj = process_node(o, visited)
            properties[prop_label].append(obj)
        return {'type': 'bnode', 'properties': properties}

    elif isinstance(node, URIRef):
        label = get_label(node)
        if "wikidata.org" in node:
            return {
                'type': 'uri',
                'value': label,
                'uri': str(node)  
            }
        entity_id = node.split('#')[-1] if '#' in node else node.split('/')[-1]
        return {
            'type': 'uri',
            'value': label,
            'uri': url_for('entity', entity_id=entity_id)
        }

    else:
        return {'type': 'literal', 'value': str(node)}

def get_entities_of_type(rdf_type):
    q = """
    SELECT ?s WHERE {
        ?s rdf:type %s .
    }
    """ % rdf_type.n3()
    results = g.query(q)
    return [str(row.s) for row in results]
    
@app.route('/', methods=['GET', 'POST'])
def index():
    query = request.args.get('q', '').strip()  
    if query:
        matching_uris = []
        for s, p, o in g.triples((None, RDFS.label, None)):
            if not isinstance(s, BNode) and query.lower() in str(o).lower():
                matching_uris.append((str(s), str(o)))  
        persons = [{'uri': uri, 'name': label, 'id': uri.split('#')[-1]} for uri, label in matching_uris]
    else:
        person_uris = get_entities_of_type(BASE.CabinetAppointee)
        persons = []
        for uri in person_uris:
            if isinstance(URIRef(uri), BNode):
                continue
            label = get_label(URIRef(uri))
            name = label if label else uri.split('#')[-1]
            entity_id = uri.split('#')[-1]
            persons.append({'uri': uri, 'name': name, 'id': entity_id})

    return render_template('index.html', persons=persons, query=query)

def fetch_wikidata_info(wikidata_uri):
    """Fetch additional information from Wikidata for a given Wikidata URI."""
    wikidata_id = wikidata_uri.split('/')[-1]
    query = f"""
    SELECT ?property ?propertyLabel ?value ?valueLabel WHERE {{
      wd:{wikidata_id} ?property ?value .
      ?property rdfs:label ?propertyLabel .
      OPTIONAL {{ ?value rdfs:label ?valueLabel . FILTER (lang(?valueLabel) = "en") }}
      FILTER (lang(?propertyLabel) = "en")
    }}
    LIMIT 50
    """
    url = "https://query.wikidata.org/sparql"
    headers = {
        "Accept": "application/sparql-results+json"
    }
    response = requests.get(url, headers=headers, params={"query": query})
    
    if response.status_code == 200:
        try:
            data = response.json()
            results = data.get('results', {}).get('bindings', [])
            wikidata_info = defaultdict(list)
            for result in results:
                prop = result['propertyLabel']['value']
                val = result.get('valueLabel', {}).get('value', result.get('value', {}).get('value', 'Unknown Value'))
                wikidata_info[prop].append(val)
            return wikidata_info
        except Exception as e:
            print(f"Error parsing Wikidata response: {e}")
            return {}
    else:
        print(f"Failed to fetch Wikidata data: {response.status_code}")
        return {}

@app.route('/entity/<path:entity_id>')
def entity(entity_id):
    uri = BASE[entity_id]
    if (uri, None, None) not in g:
        uri = RDFS[entity_id]
        if (uri, None, None) not in g:
            abort(404)

    entity_data = {'label': get_label(uri), 'properties': defaultdict(list), 'sameAs': []}
    for p, o in g.predicate_objects(uri):
        prop_label = get_label(p) or p.n3(g.namespace_manager)
        if p == OWL.sameAs:
            entity_data['sameAs'].append(o)
        obj = process_node(o)
        entity_data['properties'][prop_label].append(obj)
    
    thewikidata_id = None
    for sameas_uri in entity_data.get('sameAs', []):
        if isinstance(sameas_uri, URIRef) and str(sameas_uri).startswith('http://www.wikidata.org/entity/'):
            thewikidata_id = str(sameas_uri).split('/')[-1]

    if thewikidata_id:
        sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
        sparql.setReturnFormat(JSON)
        prefixes = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX wikibase: <http://wikiba.se/ontology#>
        PREFIX bd: <http://www.bigdata.com/rdf#>
        """
        query = prefixes + """
            SELECT ?property ?propertyLabel ?value ?valueLabel WHERE {
              wd:%s ?prop ?value .
              ?property wikibase:directClaim ?prop .
              SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
            } LIMIT 30
            """ % thewikidata_id
        sparql.setQuery(query)
        
        try:
            results = sparql.query().convert()
            for result in results["results"]["bindings"]:
                prop = "wikidata:" + result["propertyLabel"]["value"] 
                val = result.get("valueLabel", {}).get("value", result["value"]["value"])
                entity_data['properties'][prop].append({'type': 'literal', 'value': val})
        except Exception as e:
            print(f"Error querying Wikidata for {thewikidata_id}: {e}")
    
    return render_template('entity.html', entity=entity_data)


if __name__ == '__main__':
    app.run()
