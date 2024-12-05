from rdflib import Graph, Namespace, Literal
from SPARQLWrapper import SPARQLWrapper, JSON
# Define Namespaces
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")
BASE = Namespace("http://example.org/mybase#")

def query_wikidata(label):
    """
    Query Wikidata to find the corresponding entity for a given label.
    """
    sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
    query = f"""
    SELECT ?item WHERE {{
      ?item rdfs:label "{label}"@en.
    }}
    LIMIT 1
    """
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    bindings = results.get("results", {}).get("bindings", [])
    if bindings:
        return bindings[0]["item"]["value"]  # Return the URI of the Wikidata item
    return None

def enrich_with_wikidata(input_file, output_file):
    """
    Process the Turtle file and add owl:sameAs links to Wikidata entities.
    """
    g = Graph()
    g.parse(input_file, format="turtle")

    updated_graph = Graph()
    updated_graph += g 

    for s, p, o in g.triples((None, RDFS.label, None)):
        if isinstance(o, Literal):
            label = str(o)
            wikidata_uri = query_wikidata(label)
            if wikidata_uri:
                print(f"Linking {label} to {wikidata_uri}")
                updated_graph.add((s, OWL.sameAs, Literal(wikidata_uri)))


    updated_graph.serialize(destination=output_file, format="turtle")
    print(f"Updated Turtle file saved to {output_file}")

input_turtle_file = "other_output.ttl"  
output_turtle_file = "output.ttl" 

enrich_with_wikidata(input_turtle_file, output_turtle_file)